"""The manual performance measurement (PROJE-KAYDI.md, O-31).

The limits come from the project record: p95 of the server time is at most 500 ms for a
read endpoint and at most 1 second for a write endpoint. The measurement itself is started
by hand (`python3 -m tests.measure`). These tests run a short version of it, so the command
cannot rot, and check that it reports a broken limit instead of hiding it.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest

from . import measure


class MeasurementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = measure.run(samples=12, concurrency=20, users=200)

    def test_limits_are_the_ones_of_the_project_record(self) -> None:
        self.assertEqual((measure.READ_LIMIT_MS, measure.WRITE_LIMIT_MS), (500, 1000))
        self.assertEqual((measure.DEFAULT_SAMPLES, measure.DEFAULT_CONCURRENCY, measure.DEFAULT_USERS), (50, 20, 200))

    def test_three_endpoints_are_measured_with_their_kind(self) -> None:
        kinds = {row["endpoint"]: (row["kind"], row["limit_ms"]) for row in self.report["endpoints"]}
        self.assertEqual(
            kinds,
            {
                "POST /v1/sessions/revoke": ("write", 1000),
                "POST /v1/account-deletions": ("write", 1000),
                "POST /v1/reconcile (preview)": ("read", 500),
            },
        )

    def test_every_call_succeeded_and_is_counted(self) -> None:
        for row in self.report["endpoints"]:
            with self.subTest(endpoint=row["endpoint"]):
                self.assertEqual((row["calls"], row["errors"]), (12, 0))
                self.assertEqual((row["concurrent_requests"], row["concurrent_errors"]), (20, 0))
                self.assertEqual(row["concurrent_error_rate"], 0.0)
                self.assertGreater(row["concurrent_wait_p95_ms"], 0)
                self.assertGreater(row["p95_ms"], 0)
                self.assertGreaterEqual(row["p95_ms"], row["p50_ms"])

    def test_measured_values_are_within_the_limits(self) -> None:
        for row in self.report["endpoints"]:
            with self.subTest(endpoint=row["endpoint"]):
                self.assertLessEqual(row["p95_ms"], row["limit_ms"])
                self.assertTrue(row["within_limit"])
        self.assertTrue(self.report["passed"])

    def test_sample_data_is_the_size_the_project_record_asks_for(self) -> None:
        self.assertEqual(self.report["sample_data"]["keycloak_users"], 200)
        self.assertEqual(self.report["targets"], "fake")

    def test_percentile_is_the_nearest_rank(self) -> None:
        values = [float(number) for number in range(1, 101)]
        self.assertEqual((measure.percentile(values, 95), measure.percentile(values, 50)), (95.0, 50.0))
        self.assertEqual(measure.percentile([7.0], 95), 7.0)

    def test_broken_limit_fails_the_command(self) -> None:
        # A limit nobody can meet: the command must say so and exit with 1.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = measure.main(["--samples", "3", "--concurrency", "2", "--users", "5", "--read-limit-ms", "0", "--write-limit-ms", "0"])
        report = json.loads(out.getvalue())
        self.assertEqual((code, report["passed"]), (1, False))
        self.assertFalse(any(row["within_limit"] for row in report["endpoints"]))

    def test_errors_fail_the_command_even_when_it_is_fast(self) -> None:
        report = measure.judge(
            [{"endpoint": "x", "kind": "read", "p95_ms": 1.0, "errors": 0, "concurrent_errors": 1, "concurrent_requests": 20}],
            read_limit_ms=500,
            write_limit_ms=1000,
        )
        self.assertFalse(report["passed"])
        self.assertEqual(report["endpoints"][0]["concurrent_error_rate"], 0.05)
