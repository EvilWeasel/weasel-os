#!/usr/bin/env python3
"""Offline fault/budget/protocol verification. No network, API, key-store or GUI."""
import contextlib
import io
import json
import os
import pathlib
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import decisiond as d
from benchmark import summarize


QUESTION = {'type': 'predicate', 'name': 'ready', 'instructions': 'Is the local fixture ready?'}


def request(ident='one', **extra):
    return {'schema_version': d.VERSION, 'op': 'decide', 'request_id': ident, 'task_id': 'test', 'observation_id': 'obs1', 'text': 'Status: ready', 'question': QUESTION, **extra}


class FakeTransport:
    def __init__(self, response=None, error=None):
        self.calls = 0
        self.response = response or {'answers': [{'type': 'predicate', 'name': 'ready', 'probability': .99}], 'usage': {'input_tokens': 169, 'output_tokens': 0, 'total_tokens': 169}}
        self.error = error

    def post(self, endpoint, body, timeout):
        self.calls += 1
        if self.error:
            raise self.error
        return 200, self.response


class Tests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='optional-decisions-offline-')
        self.path = pathlib.Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def service(self, **kw):
        ledger = d.Ledger(self.path, 'test-job', kw.pop('max_calls', 200), kw.pop('budget', 10_000_000), kw.pop('prior', 0))
        self.addCleanup(ledger.db.close)
        transport = FakeTransport(**kw)
        return d.Service(ledger, transport), transport

    def test_request_receipt_replay_and_payload_conflict(self):
        service, transport = self.service()
        first = service.handle(request())
        again = service.handle(request())
        conflict = service.handle(request(text='Status: different'))
        self.assertEqual(first['status'], 'ok')
        self.assertEqual(first['estimated_cost_usd'], '0.0000169')
        self.assertTrue(again['cached_receipt'])
        self.assertEqual(conflict['error'], 'request_id_payload_conflict')
        self.assertEqual(transport.calls, 1)

    def test_call_and_budget_cap_persist_across_restart(self):
        service, transport = self.service(max_calls=3, budget=100_000, prior=1)
        self.assertEqual(service.handle(request('allowed'))['status'], 'ok')
        self.assertEqual(service.handle(request('blocked'))['error'], 'job_request_or_budget_cap_reached')
        restarted = d.Service(d.Ledger(self.path, 'test-job', 3, 100_000, 1), FakeTransport())
        self.addCleanup(restarted.ledger.db.close)
        self.assertEqual(restarted.handle(request('new'))['error'], 'job_request_or_budget_cap_reached')
        self.assertEqual(transport.calls, 1)
        with self.assertRaises(d.Refusal):
            d.Ledger(self.path, 'test-job', 200, 10_000_000, 0)

    def test_uncertain_transport_is_not_retried_and_cap_is_retained(self):
        service, transport = self.service(error=TimeoutError('SECRET_TEST_MARKER'))
        first = service.handle(request())
        second = service.handle(request())
        self.assertEqual(first['status'], 'uncertain')
        self.assertTrue(second['cached_receipt'])
        self.assertEqual(transport.calls, 1)
        self.assertNotIn('SECRET_TEST_MARKER', json.dumps(first))
        self.assertEqual(service.ledger.snapshot()['reserved_usd'], .05)

    def test_uncertain_prior_dispatch_will_not_replay(self):
        service, transport = self.service()
        service.ledger.reserve('crashed', 'fingerprint', 'decisions')
        with self.assertRaises(d.Refusal) as caught:
            service.ledger.reserve('crashed', 'fingerprint', 'decisions')
        self.assertEqual(caught.exception.code, 'prior_dispatch_uncertain_do_not_replay')
        self.assertEqual(transport.calls, 0)

    def test_unexpected_cost_halts_same_job_persistently(self):
        service, transport = self.service(response={'answers': [{'type': 'predicate', 'name': 'ready', 'probability': .9}], 'usage': {'input_tokens': 1_000_000, 'output_tokens': 0}})
        first = service.handle(request())
        self.assertEqual(first['status'], 'uncertain')
        self.assertTrue(service.ledger.snapshot()['halted'])
        restarted = d.Service(d.Ledger(self.path, 'test-job', 200, 10_000_000), FakeTransport())
        self.addCleanup(restarted.ledger.db.close)
        self.assertEqual(restarted.handle(request('new'))['error'], 'job_halted_review_ledger_before_new_requests')
        self.assertEqual(transport.calls, 1)

    def test_no_score_no_action_no_unbounded_evidence_or_timeout(self):
        service, transport = self.service()
        for value in [request(question={**QUESTION, 'type': 'score'}), request(op='click'), request(text='x' * 8193), request(timeout_ms=15001)]:
            self.assertEqual(service.handle(value)['status'], 'failed')
        self.assertEqual(transport.calls, 0)

    def test_choice_identity_and_distribution_validation(self):
        question = {'type': 'choice', 'name': 'candidate', 'instructions': 'Select existing matching record', 'choices': [{'value': 'A17', 'description': 'Brücke'}, {'value': 'B24', 'description': 'Wiese'}]}
        good = {'answers': [{'type': 'choice', 'name': 'candidate', 'choice': 'A17', 'probabilities': [{'value': 'A17', 'probability': .8}, {'value': 'B24', 'probability': .2}]}]}
        self.assertEqual(d.parse_answer('decisions', question, good)['choice'], 'A17')
        good['answers'][0]['choice'] = 'DELETE_ALL'
        with self.assertRaises(d.Refusal):
            d.parse_answer('decisions', question, good)
        with self.assertRaises(d.Refusal):
            d.finite_probability(float('nan'))

    def test_explicit_images_only_under_private_root(self):
        crop = self.path / 'crop.png'
        # Header is sufficient for offline bounded dimensions validator, not a
        # claim this synthetic header is an API-valid rendered PNG.
        crop.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + (32).to_bytes(4, 'big') + (16).to_bytes(4, 'big'))
        _, metadata = d.load_image(str(crop), [self.path])
        self.assertEqual(metadata['width'], 32)
        with self.assertRaises(d.Refusal):
            d.load_image(str(crop), [])
        self.path.chmod(0o755)
        with self.assertRaises(d.Refusal):
            d.load_image(str(crop), [self.path])
        self.path.chmod(0o700)

    def test_bounded_timeout_and_no_late_post_after_stalled_connect(self):
        release = threading.Event()

        class Connection:
            def __init__(self, *a, **kw):
                self.sock = None
                self.calls = 0
                self.timeout = None
            def connect(self):
                release.wait(2)
            def request(self, *a, **kw):
                self.calls += 1
            def close(self):
                pass

        connection = Connection()
        with patch.object(d.http.client, 'HTTPSConnection', return_value=connection):
            transport = d.HTTPSKeepalive('fixture-placeholder')
            started = time.monotonic()
            with self.assertRaises(d.Refusal):
                transport.post('decisions', {}, .03)
            self.assertLess(time.monotonic() - started, .3)
            with self.assertRaises(d.Refusal) as caught:
                transport.post('decisions', {}, .03)
            self.assertEqual(caught.exception.code, 'previous_transport_pending_no_new_dispatch')
            release.set()
            transport.worker.join(1)
        self.assertEqual(connection.calls, 0)

    def test_keepalive_success_reuses_one_connection_without_retry(self):
        class Sock:
            def settimeout(self, value):
                pass
        class Response:
            status = 200
            def read(self, limit):
                return b'{"answers":[]}'
        class Connection:
            def __init__(self, *a, **kw):
                self.sock = None
                self.calls = 0
            def connect(self):
                self.sock = Sock()
            def request(self, *a, **kw):
                self.calls += 1
            def getresponse(self):
                return Response()
            def close(self):
                pass
        connection = Connection()
        with patch.object(d.http.client, 'HTTPSConnection', return_value=connection) as factory:
            transport = d.HTTPSKeepalive('fixture-placeholder')
            transport.post('decisions', {}, 1)
            transport.post('responses', {}, 1)
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(connection.calls, 2)

    def test_unix_service_and_stdio_mcp_status_without_api(self):
        service, transport = self.service()
        path = self.path / 'decision.sock'
        with d.Server(str(path), d.Handler) as server:
            server.service = service
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            script = pathlib.Path(__file__).with_name('mcp.py')
            process = subprocess.Popen(['python3', str(script), '--socket', str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                for ident, method, params in [(1, 'initialize', {'protocolVersion': '2025-06-18'}), (2, 'tools/list', {}), (3, 'tools/call', {'name': 'desktop_decision_status', 'arguments': {}})]:
                    process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params}) + '\n')
                    process.stdin.flush()
                    result = json.loads(process.stdout.readline())
                    self.assertEqual(result['id'], ident)
                    self.assertIn('result', result)
                status = json.loads(result['result']['content'][0]['text'])
                self.assertFalse(status['input_actions'])
                self.assertEqual(status['ledger']['calls_reserved'], 0)
            finally:
                process.stdin.close()
                process.wait(2)
                process.stdout.close()
                process.stderr.close()
                server.shutdown()
                thread.join(1)
        self.assertEqual(transport.calls, 0)

    def test_benchmark_excludes_wrong_outcomes_from_latency_ratio(self):
        rows = [
            {'repeat': 0, 'endpoint': 'decisions', 'cold': True, 'correct': True, 'receipt': {'status': 'ok', 'cached_receipt': False, 'timing': {'total_ms': 100}}},
            {'repeat': 0, 'endpoint': 'responses', 'cold': True, 'correct': True, 'receipt': {'status': 'ok', 'cached_receipt': False, 'timing': {'total_ms': 200}}},
            {'repeat': 1, 'endpoint': 'decisions', 'cold': False, 'correct': False, 'receipt': {'status': 'ok', 'cached_receipt': False, 'timing': {'total_ms': 1}}},
            {'repeat': 1, 'endpoint': 'responses', 'cold': False, 'correct': True, 'receipt': {'status': 'ok', 'cached_receipt': False, 'timing': {'total_ms': 200}}},
        ]
        result = summarize(rows)
        self.assertEqual(result['comparable_correct_pairs'], 1)
        self.assertEqual(result['median_responses_to_decisions_ratio'], 2)
        self.assertIsNone(result['decisions']['warm_median_ms'])
        self.assertIsNone(result['responses']['warm_p95_ms'])

    def test_benchmark_dry_run_does_not_connect_to_missing_socket(self):
        process = subprocess.run(['python3', str(pathlib.Path(__file__).with_name('benchmark.py')), '--socket', str(self.path / 'missing.sock'), '--case', str(self.path / 'missing-case.json'), '--output', str(self.path / 'missing-output.json')], capture_output=True, text=True, timeout=2)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(json.loads(process.stdout)['status'], 'not_executed')
        self.assertFalse((self.path / 'missing-output.json').exists())

    def test_proposal_sigterm_cleans_owned_socket_without_api(self):
        path = self.path / 'signal.sock'
        script = pathlib.Path(__file__).with_name('decisiond.py')
        # A deliberate inert placeholder is not a real credential. The only
        # request is local status; the transport never receives a POST.
        env = {'PATH': os.environ.get('PATH', ''), 'OPENAI_API_KEY': 'fixture-placeholder'}
        process = subprocess.Popen(['python3', str(script), 'serve', '--socket', str(path), '--state-dir', str(self.path / 'signal-state'), '--job-id', 'offline-signal'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            ready = json.loads(process.stdout.readline())
            self.assertEqual(ready['status'], 'ready')
            self.assertEqual(d.client_call(path, {'schema_version': d.VERSION, 'op': 'status'})['ledger']['calls_reserved'], 0)
            process.terminate()
            self.assertEqual(process.wait(3), 0)
            self.assertFalse(path.exists())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(2)
            process.stdout.close()
            process.stderr.close()

    def test_mcp_daemon_off_returns_capability_unavailable_without_retry(self):
        script = pathlib.Path(__file__).with_name('mcp.py')
        process = subprocess.Popen(['python3', str(script), '--socket', str(self.path / 'off.sock')], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            started = time.monotonic()
            process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call', 'params': {'name': 'desktop_decision_status', 'arguments': {}}}) + '\n')
            process.stdin.flush()
            response = json.loads(process.stdout.readline())
            elapsed = time.monotonic() - started
            result = json.loads(response['result']['content'][0]['text'])
            self.assertEqual(result['status'], 'capability_unavailable')
            self.assertFalse(result['retryable'])
            self.assertFalse(result['api_dispatched_by_this_request'])
            self.assertLess(elapsed, 1)
        finally:
            process.stdin.close()
            process.wait(2)
            process.stdout.close()
            process.stderr.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
