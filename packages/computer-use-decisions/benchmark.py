#!/usr/bin/env python3
"""PREPARED ONLY: paired paid evaluations through local daemon, never desktop input."""
import argparse
import hashlib
import json
import os
import pathlib
import statistics
import time
from decisiond import VERSION, client_call, load_image


def save(path, result):
    temporary = path.with_suffix('.pending')
    with open(temporary, 'w', encoding='utf-8') as file:
        os.chmod(temporary, 0o600)
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)


def summarize(rows):
    summary = {}
    for endpoint in ['decisions', 'responses']:
        good = [row for row in rows if row['endpoint'] == endpoint and row['receipt'].get('status') == 'ok' and row.get('correct') is True and not row['receipt'].get('cached_receipt')]
        warm = [row['receipt']['timing']['total_ms'] for row in good if not row['cold']]
        cold = [row['receipt']['timing']['total_ms'] for row in good if row['cold']]
        summary[endpoint] = {
            'attempts': len([row for row in rows if row['endpoint'] == endpoint]),
            'correct_fresh_successes': len(good), 'warm_samples': len(warm),
            'cold_ms': cold, 'warm_median_ms': statistics.median(warm) if warm else None,
            'warm_slowest_ms': max(warm) if warm else None,
            'warm_p95_ms': sorted(warm)[max(0, int(len(warm) * .95 + .999999) - 1)] if len(warm) >= 20 else None,
            'p95_policy': 'Reported only with at least 20 successful correct fresh warm observations',
        }
    paired = []
    for repeat in sorted({row['repeat'] for row in rows}):
        pair = [row for row in rows if row['repeat'] == repeat]
        if len(pair) == 2 and all(row.get('correct') is True and row['receipt'].get('status') == 'ok' and not row['receipt'].get('cached_receipt') for row in pair):
            by_endpoint = {row['endpoint']: row['receipt']['timing']['total_ms'] for row in pair}
            paired.append(by_endpoint['responses'] / by_endpoint['decisions'])
    summary['comparable_correct_pairs'] = len(paired)
    summary['median_responses_to_decisions_ratio'] = statistics.median(paired) if paired else None
    summary['actual_billed_usd'] = None
    summary['probability_comparison_limit'] = 'Responses probability is generated JSON; Decisions probability is native typed output. Compare correct threshold outcome and latency, not calibration.'
    return summary


def main():
    parser = argparse.ArgumentParser(description='Paid if executed. Explicit --execute required. No retries.')
    parser.add_argument('--socket', required=True)
    parser.add_argument('--case', required=True, help='Private local JSON {text,question,expected,image_path?}; not copied into results')
    parser.add_argument('--output', required=True)
    parser.add_argument('--repeat', type=int, default=10)
    parser.add_argument('--timeout-ms', type=int, default=8000)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'status': 'not_executed', 'required': '--execute', 'planned_calls': 2 * args.repeat}))
        return
    if not 1 <= args.repeat <= 30 or not 500 <= args.timeout_ms <= 15000:
        parser.error('Bounded repeat/timeout required')
    source = pathlib.Path(args.case).resolve(strict=True)
    if source.stat().st_uid != os.getuid() or source.stat().st_mode & 0o077:
        parser.error('Case must be owned private file')
    case = json.loads(source.read_text(encoding='utf-8'))
    if case.get('question', {}).get('type') == 'predicate' and not isinstance(case.get('expected'), bool):
        parser.error('Predicate requires expected boolean')
    if case.get('question', {}).get('type') == 'choice' and case.get('expected') not in [x.get('value') for x in case['question'].get('choices', [])]:
        parser.error('Choice requires expected candidate ID')
    output = pathlib.Path(args.output)
    if not output.is_absolute() or output.exists():
        parser.error('Use a new absolute output path; old runs are preserved')
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.parent.stat().st_uid != os.getuid() or output.parent.stat().st_mode & 0o077:
        parser.error('Output directory must be private')
    image_fingerprint = None
    if case.get('image_path'):
        image_path = pathlib.Path(case['image_path']).resolve(strict=True)
        _, image_fingerprint = load_image(str(image_path), [image_path.parent])
    evidence_hash = hashlib.sha256(json.dumps({'text': case['text'], 'question': case['question'], 'image': image_fingerprint}, sort_keys=True).encode()).hexdigest()
    run_id = 'bench-' + str(time.time_ns())
    report = {'schema_version': VERSION, 'run_id': run_id, 'status': 'running', 'evidence_sha256': evidence_hash, 'image': image_fingerprint, 'expected': case['expected'], 'planned_repeats': args.repeat, 'rows': [], 'actual_billed_usd': None, 'desktop_actions': False, 'automatic_retries': False, 'before': client_call(args.socket, {'schema_version': VERSION, 'op': 'status'})}
    save(output, report)
    try:
        for repeat in range(args.repeat):
            # Alternate order to reduce first/warm/order bias. First endpoint call
            # is cold relative to this run; provider/server prior warmth is unknown.
            order = ['decisions', 'responses'] if repeat % 2 == 0 else ['responses', 'decisions']
            for endpoint in order:
                if case.get('image_path'):
                    _, current = load_image(case['image_path'], [pathlib.Path(case['image_path']).resolve().parent])
                    if current != image_fingerprint:
                        raise RuntimeError('Image changed; do not compare different evidence')
                request = {'schema_version': VERSION, 'op': 'decide' if endpoint == 'decisions' else 'benchmark_responses', 'task_id': run_id, 'observation_id': 'frozen-' + evidence_hash[:32], 'request_id': run_id + '-' + str(repeat) + '-' + endpoint, 'text': case['text'], 'question': case['question'], 'timeout_ms': args.timeout_ms}
                if case.get('image_path'):
                    request['image_path'] = case['image_path']
                receipt = client_call(args.socket, request)
                answer = receipt.get('answer', {})
                outcome = answer.get('probability', -1) >= .5 if case['question']['type'] == 'predicate' else answer.get('choice')
                correct = receipt.get('status') == 'ok' and outcome == case['expected']
                report['rows'].append({'repeat': repeat, 'endpoint': endpoint, 'cold': repeat == 0, 'correct': correct, 'receipt': receipt})
                report['summary'] = summarize(report['rows'])
                save(output, report)
                if receipt.get('status') != 'ok':
                    report['status'] = 'stopped_after_failure_no_retry'
                    return
        report['status'] = 'completed'
    except (KeyboardInterrupt, Exception) as error:
        report['status'] = 'interrupted' if isinstance(error, KeyboardInterrupt) else 'stopped_after_local_failure'
        report['error_class'] = type(error).__name__
    finally:
        report['summary'] = summarize(report['rows'])
        try:
            report['after'] = client_call(args.socket, {'schema_version': VERSION, 'op': 'status'})
        except Exception:
            report['after'] = {'status': 'unavailable'}
        save(output, report)
        print(json.dumps({'status': report['status'], 'rows': len(report['rows']), 'output': str(output)}))


if __name__ == '__main__':
    main()
