"""Check the O-31 write latency budget with 50 isolated accounts."""

import unittest
from math import ceil
from time import perf_counter
from typing import ClassVar

from test_identity_http import IdentityHttpTest

SAMPLE_COUNT = 50
WRITE_BUDGET_SECONDS = 1.0


class TimedIdentityHttpTest(IdentityHttpTest):
	durations: ClassVar[list[float]] = []

	def call(self, method, body, token=None, extra_headers=None):
		started = perf_counter()
		result = super().call(method, body, token, extra_headers)
		if method == "anonymize_user" and result[0] == 200:
			self.durations.append(perf_counter() - started)
		return result


def main() -> int:
	test_name = "test_anonymize_user_preserves_linked_records_on_retry"
	tests = unittest.TestSuite(TimedIdentityHttpTest(test_name) for _iteration in range(SAMPLE_COUNT))
	if not unittest.TextTestRunner().run(tests).wasSuccessful():
		return 1

	durations = TimedIdentityHttpTest.durations
	if len(durations) != 2 * SAMPLE_COUNT:
		print(f"Expected {2 * SAMPLE_COUNT} successful responses, got {len(durations)}.")
		return 1
	rank = ceil(0.95 * SAMPLE_COUNT) - 1
	first = sorted(durations[::2])[rank]
	repeat = sorted(durations[1::2])[rank]
	print(f"Anonymization p95: {first:.3f}s. Repeat p95: {repeat:.3f}s.")
	if first > WRITE_BUDGET_SECONDS:
		print(f"Anonymization p95 exceeds {WRITE_BUDGET_SECONDS:.3f}s.")
		return 1
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
