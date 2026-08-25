#!/usr/bin/env python3
"""Offline validation fixture for the proposed iris forced-command protocol.

It deliberately has no network or token support. A future broker must consume
only validated requests plus a separate, one-time human approval record.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from typing import NoReturn, cast

SERVER_ID = 162472190
ALLOWED = {
    "status": {},
    "poweron": {},
    "shutdown": {},
    "change_type": {"server_type": {"cpx22", "cx43"}, "upgrade_disk": False},
}


def reject(reason: str) -> NoReturn:
    raise ValueError(reason)


def parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        reject(f"{field} must be an RFC3339 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        reject(f"{field} is not RFC3339")
    if parsed.tzinfo is None:
        reject(f"{field} must include timezone")
    return parsed.astimezone(UTC)


def canonical_bytes(request: dict[str, object]) -> bytes:
    return json.dumps(request, sort_keys=True, separators=(",", ":")).encode()


def validate(request: object, now: datetime) -> str:
    if not isinstance(request, dict):
        reject("request must be an object")
    record = cast(dict[str, object], request)
    expected = {"version", "request_id", "operation", "server_id", "not_before", "expires_at", "approval_id"}
    if set(record) - expected - {"server_type", "upgrade_disk"}:
        reject("unknown field")
    if record.get("version") != 1:
        reject("unsupported version")
    request_id = record.get("request_id")
    if not isinstance(request_id, str) or len(request_id) < 16:
        reject("invalid request_id")
    approval_id = record.get("approval_id")
    if not isinstance(approval_id, str) or len(approval_id) < 16:
        reject("invalid approval_id")
    if record.get("server_id") != SERVER_ID:
        reject("wrong server_id")
    operation = record.get("operation")
    if operation not in ALLOWED:
        reject("operation not allowed")

    not_before = parse_time(record.get("not_before"), "not_before")
    expires_at = parse_time(record.get("expires_at"), "expires_at")
    if expires_at <= not_before or expires_at - not_before > timedelta(minutes=15):
        reject("invalid approval lifetime")
    if now < not_before or now >= expires_at:
        reject("approval inactive or expired")

    if operation == "change_type":
        if record.get("server_type") not in {"cpx22", "cx43"}:
            reject("server_type not allowed")
        if record.get("upgrade_disk") is not False:
            reject("upgrade_disk must be false")
    elif "server_type" in record or "upgrade_disk" in record:
        reject("arguments not permitted for operation")

    return hashlib.sha256(canonical_bytes(record)).hexdigest()


def main() -> int:
    try:
        request = json.load(sys.stdin)
        request_hash = validate(request, datetime.now(UTC))
    except (ValueError, json.JSONDecodeError) as error:
        print(f"REJECT {error}", file=sys.stderr)
        return 2
    print(f"ACCEPT request_sha256={request_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
