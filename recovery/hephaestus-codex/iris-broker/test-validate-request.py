#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest
from datetime import UTC, datetime, timedelta

SPEC = importlib.util.spec_from_file_location(
    "validate_request", pathlib.Path(__file__).with_name("validate-request.py")
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load validate-request.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ValidationTests(unittest.TestCase):
    def request(self, **overrides):
        now = datetime.now(UTC)
        value = {
            "version": 1,
            "request_id": "request-0123456789",
            "approval_id": "approval-0123456789",
            "operation": "change_type",
            "server_id": 162472190,
            "server_type": "cx43",
            "upgrade_disk": False,
            "not_before": (now - timedelta(minutes=1)).isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        }
        value.update(overrides)
        return value

    def test_accepts_fixed_keep_disk_change(self):
        self.assertEqual(len(MODULE.validate(self.request(), datetime.now(UTC))), 64)

    def test_rejects_wrong_server(self):
        with self.assertRaisesRegex(ValueError, "wrong server_id"):
            MODULE.validate(self.request(server_id=1), datetime.now(UTC))

    def test_rejects_disk_upgrade(self):
        with self.assertRaisesRegex(ValueError, "upgrade_disk"):
            MODULE.validate(self.request(upgrade_disk=True), datetime.now(UTC))

    def test_rejects_arbitrary_operation(self):
        with self.assertRaisesRegex(ValueError, "operation not allowed"):
            MODULE.validate(self.request(operation="delete"), datetime.now(UTC))

    def test_rejects_expired_approval(self):
        with self.assertRaisesRegex(ValueError, "approval inactive or expired"):
            MODULE.validate(
                self.request(
                    not_before=(datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
                    expires_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                ),
                datetime.now(UTC),
            )


if __name__ == "__main__":
    unittest.main()
