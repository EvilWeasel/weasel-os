#!/usr/bin/env python3
"""Stdio MCP client for optional evaluator; no key, capture, or desktop actions."""
import argparse
import json
import sys
import threading
from decisiond import VERSION, client_call

QUESTION = {
    'type': 'object',
    'properties': {
        'type': {'type': 'string', 'enum': ['predicate', 'choice']},
        'name': {'type': 'string', 'pattern': '^[A-Za-z0-9_.:-]{1,128}$'},
        'instructions': {'type': 'string', 'minLength': 1, 'maxLength': 2048},
        'choices': {'type': 'array', 'minItems': 2, 'maxItems': 16, 'items': {
            'type': 'object', 'properties': {
                'value': {'type': 'string', 'pattern': '^[A-Za-z0-9_.:-]{1,64}$'},
                'description': {'type': 'string', 'minLength': 1, 'maxLength': 256}},
            'required': ['value', 'description'], 'additionalProperties': False}},
    },
    'required': ['type', 'instructions'], 'additionalProperties': False,
}
SCHEMA = {
    'type': 'object', 'properties': {
        'task_id': {'type': 'string', 'pattern': '^[A-Za-z0-9_.:-]{1,128}$'},
        'observation_id': {'type': 'string', 'pattern': '^[A-Za-z0-9_.:-]{1,128}$'},
        'text': {'type': 'string', 'minLength': 1, 'maxLength': 8192},
        'question': QUESTION,
        'image_path': {'type': 'string', 'description': 'Explicit existing PNG/JPEG private crop. No capture is performed.'},
        'request_id': {'type': 'string', 'pattern': '^[A-Za-z0-9_.:-]{1,128}$', 'description': 'Use a stable unique ID for this exact observation/question; duplicates return the old receipt, without dispatch.'},
        'timeout_ms': {'type': 'integer', 'minimum': 500, 'maximum': 15000, 'default': 8000},
    }, 'required': ['task_id', 'observation_id', 'text', 'question'], 'additionalProperties': False,
}
TOOLS = [
    {'name': 'desktop_decide', 'description': 'Optional paid typed UI predicate or choice among explicit safe candidates. Supplies evidence only; never captures, clicks, types, plans actions, or authorizes execution. If the optional daemon is off or budget halted, do not retry it repeatedly: use normal model reasoning and the independent desktop actor. Reobserve/verify through that actor. Choices do not guarantee safety. Native probabilities are model estimates.', 'inputSchema': SCHEMA, 'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': True}},
    {'name': 'desktop_decision_status', 'description': 'Read local optional evaluator capability, budget reservations and halt state; no model request.', 'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}, 'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False}},
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--socket', required=True)
    args = parser.parse_args()
    output_lock = threading.Lock()
    pending_lock = threading.Lock()
    pending = {}
    limit = threading.BoundedSemaphore(4)

    def emit(value):
        with output_lock:
            sys.stdout.write(json.dumps(value, separators=(',', ':')) + '\n')
            sys.stdout.flush()

    def error(ident, code, message):
        emit({'jsonrpc': '2.0', 'id': ident, 'error': {'code': code, 'message': message}})

    def call(ident, params, canceled):
        try:
            if canceled.is_set():
                error(ident, -32800, 'Canceled before local dispatch')
                return
            name = params.get('name')
            arguments = params.get('arguments', {})
            if name == 'desktop_decision_status' and arguments == {}:
                request = {'schema_version': VERSION, 'op': 'status'}
            elif name == 'desktop_decide' and isinstance(arguments, dict) and not set(arguments) - set(SCHEMA['properties']):
                request = {**arguments, 'schema_version': VERSION, 'op': 'decide'}
            else:
                error(ident, -32602, 'Invalid optional evaluator tool or arguments')
                return
            result = client_call(args.socket, request)
            if canceled.is_set():
                error(ident, -32800, 'Canceled; a paid evaluation may already have been dispatched. No desktop actions exist in this service.')
                return
            emit({'jsonrpc': '2.0', 'id': ident, 'result': {'content': [{'type': 'text', 'text': json.dumps(result, separators=(',', ':'))}], 'isError': result.get('status') not in {'ok'}}})
        except (FileNotFoundError, ConnectionRefusedError, PermissionError) as exc:
            result = {'schema_version': VERSION, 'status': 'capability_unavailable', 'error': 'optional_decisions_daemon_unavailable', 'error_class': type(exc).__name__, 'retryable': False, 'automatic_retries': False, 'api_dispatched_by_this_request': False, 'guidance': 'Continue using fresh desktop_observe/desktop_semantic and normal model reasoning. Explicitly start the optional evaluator only within the authorized persisted job budget. Do not keep retrying this unavailable capability.'}
            emit({'jsonrpc': '2.0', 'id': ident, 'result': {'content': [{'type': 'text', 'text': json.dumps(result, separators=(',', ':'))}], 'isError': True}})
        except Exception as exc:
            # Keep upstream bodies, prompts, paths, exception messages and keys out.
            error(ident, -32603, 'Optional evaluator unavailable: ' + type(exc).__name__)
        finally:
            with pending_lock:
                pending.pop(ident, None)
            limit.release()

    for line in sys.stdin:
        if len(line.encode()) > 65536:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                continue
            ident = request.get('id')
            method = request.get('method')
            params = request.get('params', {})
            if method == 'notifications/cancelled':
                with pending_lock:
                    event = pending.get(params.get('requestId'))
                if event:
                    event.set()
                continue
            if ident is None:
                continue
            if not isinstance(ident, (str, int)) or isinstance(ident, bool) or not isinstance(params, dict):
                error(ident if isinstance(ident, (str, int)) else None, -32600, 'Invalid JSON-RPC request')
            elif method == 'initialize':
                protocol = params.get('protocolVersion', '2024-11-05')
                if protocol not in {'2024-11-05', '2025-03-26', '2025-06-18'}:
                    protocol = '2025-06-18'
                emit({'jsonrpc': '2.0', 'id': ident, 'result': {'protocolVersion': protocol, 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'weasel-optional-ui-decisions', 'version': VERSION}}})
            elif method == 'ping':
                emit({'jsonrpc': '2.0', 'id': ident, 'result': {}})
            elif method == 'tools/list':
                emit({'jsonrpc': '2.0', 'id': ident, 'result': {'tools': TOOLS}})
            elif method == 'tools/call':
                with pending_lock:
                    duplicate = ident in pending
                    if not duplicate and limit.acquire(blocking=False):
                        event = threading.Event()
                        pending[ident] = event
                    else:
                        event = None
                if event is None:
                    error(ident, -32000, 'Duplicate request ID or bounded local queue full')
                else:
                    threading.Thread(target=call, args=(ident, params, event), daemon=True).start()
            else:
                error(ident, -32601, 'Method not found')
        except (ValueError, TypeError):
            error(None, -32700, 'Parse error')


if __name__ == '__main__':
    main()
