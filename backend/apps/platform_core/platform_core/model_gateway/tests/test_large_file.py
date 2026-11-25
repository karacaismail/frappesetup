"""Large file jobs: page text, chunk plan, chunk dispatch and single-chunk retry (G-156)."""

import json
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from platform_core.model_gateway import adapters, gateway, large_file, ledger, policy, routing


def _model(context_size, *, prices=True, price="1", currency="USD", name="fixture-model"):
	return SimpleNamespace(
		name=name,
		context_size=context_size,
		prices_known=int(prices),
		input_price=price,
		output_price=price,
		cost_currency=currency,
		enabled=1,
		output_tokens_per_second=200,
		capabilities="[]",
		model_id=name,
		provider="fixture-provider",
	)


def _target(api, account, model):
	return gateway.Target(
		SimpleNamespace(
			name=api,
			account=account,
			enabled=1,
			health_status="healthy",
			priority=0,
			weight=1,
			allowed_models="[]",
			base_url="https://provider.example.test",
			auth_type="api_key",
		),
		SimpleNamespace(name=account, enabled=1, has_monthly_budget=0, currency="USD"),
		SimpleNamespace(name="fixture-provider", enabled=1),
		model,
	)


class FakePage:
	def __init__(self, text):
		self.text = text

	def extract_text(self):
		return self.text


class PageTextTests(unittest.TestCase):
	def test_text_is_read_page_by_page_and_scanned_pages_use_ocr(self):
		pages = [FakePage("first page"), FakePage("  "), FakePage("third page")]
		ocr = Mock(return_value="recognized text")
		self.assertEqual(large_file.page_texts(pages, ocr), ["first page", "recognized text", "third page"])
		ocr.assert_called_once_with(1, pages[1])

	def test_scanned_page_without_ocr_step_stops_the_job(self):
		with self.assertRaises(policy.Denied) as failure:
			large_file.page_texts([FakePage("")], None)
		self.assertEqual(failure.exception.code, "ocr_unavailable")


class PlanTests(unittest.TestCase):
	instruction = "Summarize the fixture text."

	def test_chunks_follow_page_boundaries_and_model_context_size(self):
		pages = ["a" * 300, "b" * 300, "c" * 300, "d" * 300]
		small = large_file.plan(pages, [_target("api-1", "acc-1", _model(1100))], self.instruction, 64)
		large = large_file.plan(pages, [_target("api-1", "acc-1", _model(2400))], self.instruction, 64)
		self.assertGreater(len(small.chunks), len(large.chunks))
		for chunk in small.chunks + large.chunks:
			text = "\n".join(pages[chunk.first_page : chunk.last_page + 1])
			self.assertEqual(chunk.text, text)

	def test_smallest_context_size_of_the_route_sets_the_chunk_size(self):
		pages = ["a" * 300] * 4
		mixed = large_file.plan(
			pages,
			[
				_target("api-1", "acc-1", _model(4000, name="large")),
				_target("api-2", "acc-2", _model(1100, name="small")),
			],
			self.instruction,
			64,
		)
		only_small = large_file.plan(pages, [_target("api-2", "acc-2", _model(1100))], self.instruction, 64)
		self.assertEqual(len(mixed.chunks), len(only_small.chunks))

	def test_every_chunk_fits_the_context_with_the_output_limit(self):
		target = _target("api-1", "acc-1", _model(1100))
		result = large_file.plan(["x" * 2500, "y" * 10], [target], self.instruction, 64)
		for chunk in result.chunks:
			messages = large_file.messages(self.instruction, chunk.text)
			payload = json.dumps([messages, [], None], ensure_ascii=False).encode()
			self.assertLessEqual(len(payload) + 64, 1100)
		joined = "".join(chunk.text for chunk in result.chunks).replace("\n", "")
		self.assertEqual(joined, "x" * 2500 + "y" * 10)

	def test_chunk_count_and_cost_are_known_before_any_provider_call(self):
		target = _target("api-1", "acc-1", _model(1100, price="2"))
		with patch.object(adapters, "complete") as send:
			result = large_file.plan(["a" * 300] * 4, [target], self.instruction, 64)
		send.assert_not_called()
		self.assertEqual(result.chunk_count, len(result.chunks))
		self.assertGreater(result.chunk_count, 1)
		# Each chunk reserves the model context and the output limit.
		self.assertEqual(
			result.estimated_cost, Decimal(2) * (1100 + 64) * result.chunk_count / ledger.MILLION
		)
		self.assertEqual(result.currency, "USD")

	def test_cost_is_unknown_when_any_price_is_unknown(self):
		result = large_file.plan(
			["a" * 300],
			[
				_target("api-1", "acc-1", _model(1100)),
				_target("api-2", "acc-2", _model(1100, prices=False, name="unpriced")),
			],
			self.instruction,
			64,
		)
		self.assertIsNone(result.estimated_cost)

	def test_cost_is_unknown_when_currencies_differ(self):
		result = large_file.plan(
			["a" * 300],
			[
				_target("api-1", "acc-1", _model(1100)),
				_target("api-2", "acc-2", _model(1100, currency="EUR", name="euro")),
			],
			self.instruction,
			64,
		)
		self.assertIsNone(result.estimated_cost)

	def test_context_without_room_for_text_is_rejected(self):
		with self.assertRaises(policy.Denied) as failure:
			large_file.plan(["a"], [_target("api-1", "acc-1", _model(80))], self.instruction, 64)
		self.assertEqual(failure.exception.code, "context_too_small")


class UsageTagTests(unittest.TestCase):
	def test_usage_log_records_file_job_and_chunk_order(self):
		captured = {}

		def get_doc(values):
			captured.update(values)
			return Mock(name="log")

		with (
			patch.object(ledger.frappe, "get_doc", side_effect=get_doc),
			patch.object(ledger.frappe, "db", Mock()),
			patch.object(ledger.frappe, "session", SimpleNamespace(user="fixture")),
			patch.object(ledger, "now_datetime"),
		):
			ledger.begin(
				"route",
				SimpleNamespace(name="api"),
				SimpleNamespace(name="acc"),
				SimpleNamespace(name="prov"),
				_model(1100),
				cost=None,
				tokens=10,
				file_job="job-1",
				chunk_index=3,
			)
		self.assertEqual((captured["file_job"], captured["chunk_index"]), ("job-1", 3))

	def test_chunk_reservation_passes_job_and_order_to_the_usage_log(self):
		account = SimpleNamespace(name="acc", enabled=1, has_monthly_budget=0, currency="USD")
		api = SimpleNamespace(name="api", account="acc", modified="initial", enabled=1)
		target = SimpleNamespace(account=account, api=api, model=_model(1100), provider=Mock())
		request = policy.Request([{"role": "user", "content": "test"}], [], None, 12)
		with (
			patch.object(gateway.frappe, "db", Mock()),
			patch.object(gateway.frappe, "session", SimpleNamespace(user="fixture")),
			patch.object(gateway, "scoped_lock"),
			patch.object(gateway, "lock_row", side_effect=[account, api, SimpleNamespace(enabled=1)]),
			patch.object(ledger, "remaining", return_value=None),
			patch.object(ledger, "api_quota", return_value=True),
			patch.object(ledger, "site_quota", return_value=True),
			patch.object(ledger, "begin", return_value="log") as begin,
		):
			gateway._reserve(None, target, request, tag=gateway.ChunkTag("job-1", 3))
		self.assertEqual(begin.call_args.kwargs["file_job"], "job-1")
		self.assertEqual(begin.call_args.kwargs["chunk_index"], 3)


class RateLimitTests(unittest.TestCase):
	def test_chunk_on_a_rate_limited_account_moves_to_another_account(self):
		model = _model(1100)
		first = _target("api-a1", "account-a", model)
		same_account = _target("api-a2", "account-a", model)
		other_account = _target("api-b1", "account-b", model)
		ordered = [first, same_account, other_account]
		sent = []

		def choose(targets, route, request):
			chosen = ordered if len(targets) > 1 else targets
			return [(routing.Candidate(t.api.name, t.model.name), t) for t in chosen]

		def endpoint(target):
			return SimpleNamespace(name=target.api.name)

		def provider(endpoint, *args, **kwargs):
			sent.append(endpoint.name)
			if endpoint.name.startswith("api-a"):
				raise adapters.GatewayError("rate_limit", may_be_billed=False)
			return {"text": "ok", "usage": {"input": 1, "output": 1}}

		cache = Mock()
		cache.get.return_value = None
		request = policy.Request([{"role": "user", "content": "chunk"}], [], None, 12)
		with (
			patch.object(gateway, "_choose", side_effect=choose),
			patch.object(
				gateway, "_target", side_effect=lambda api, model: {t.api.name: t for t in ordered}[api]
			),
			patch.object(gateway.Target, "endpoint", endpoint),
			patch.object(gateway.policy, "outbound", side_effect=lambda base, oauth, route, req: req),
			patch.object(gateway, "_reserve", return_value="log"),
			patch.object(gateway, "_set_health"),
			patch.object(gateway.frappe, "cache", cache),
			patch.object(ledger, "is_pending", return_value=True),
			patch.object(ledger, "finish"),
			patch.object(adapters, "complete", side_effect=provider),
		):
			result = gateway._dispatch(None, ordered, request, float("inf"))
		self.assertEqual(result["text"], "ok")
		self.assertEqual(sent, ["api-a1", "api-b1"])


class FakeJob:
	"""In-memory stand-in for a PLT AI File Job document."""

	def __init__(self, statuses):
		self.name = "job-1"
		self.owner = "fixture@example.test"
		self.route = "fixture-route"
		self.instruction = "Summarize."
		self.output_limit = 64
		self.status = "completed"
		self.chunks = [
			SimpleNamespace(
				name=f"chunk-{index}",
				chunk_index=index,
				content=f"text {index}",
				status=status,
				failure_code=None,
				result=None,
			)
			for index, status in enumerate(statuses)
		]


class RetryTests(unittest.TestCase):
	def _run(self, job, provider, function, *args):
		store = {chunk.name: chunk for chunk in job.chunks}

		def set_value(doctype, name, values, *rest, **kwargs):
			target = job if doctype == large_file.JOB else store[name]
			for key, value in values.items():
				setattr(target, key, value)

		db = Mock()
		db.set_value.side_effect = set_value
		with (
			patch.object(large_file, "_job", return_value=job),
			patch.object(large_file, "_lock_chunk", side_effect=lambda name: store[name]),
			patch.object(large_file.frappe, "db", db),
			patch.object(large_file.frappe, "enqueue") as enqueue,
			patch.object(large_file.gateway, "complete_chunk", side_effect=provider) as send,
		):
			function(*args)
		return send, enqueue

	def test_failed_chunk_does_not_stop_the_others(self):
		job = FakeJob(["queued", "queued", "queued"])

		def provider(route, tag, messages, limit):
			if tag.index == 1:
				raise policy.Denied(503, "provider_unavailable")
			return {"text": f"answer {tag.index}"}

		send, _ = self._run(job, provider, large_file.run_job, "job-1")
		self.assertEqual(send.call_count, 3)
		self.assertEqual([chunk.status for chunk in job.chunks], ["done", "failed", "done"])
		self.assertEqual(job.chunks[1].failure_code, "provider_unavailable")
		self.assertEqual(job.status, "failed")

	def test_retry_sends_only_the_failed_chunk_again(self):
		job = FakeJob(["done", "failed", "done"])
		job.status = "failed"
		with (
			patch.object(large_file, "_job", return_value=job),
			patch.object(large_file, "_require_owner"),
			patch.object(large_file, "_lock_chunk", side_effect=lambda name: job.chunks[1]),
			patch.object(large_file.frappe, "db", Mock()),
			patch.object(large_file.frappe, "enqueue") as enqueue,
		):
			large_file.retry_chunk("job-1", 1)
		enqueue.assert_called_once()
		self.assertEqual(enqueue.call_args.kwargs["chunk_index"], 1)
		job.chunks[1].status = "queued"

		send, _ = self._run(
			job, lambda route, tag, messages, limit: {"text": "answer"}, large_file.run_chunk, "job-1", 1
		)
		send.assert_called_once()
		self.assertEqual(send.call_args.args[1], gateway.ChunkTag("job-1", 1))
		self.assertEqual([chunk.status for chunk in job.chunks], ["done", "done", "done"])
		self.assertEqual(job.status, "completed")

	def test_chunk_that_did_not_fail_cannot_be_retried(self):
		job = FakeJob(["done", "failed"])
		with (
			patch.object(large_file, "_job", return_value=job),
			patch.object(large_file, "_require_owner"),
			patch.object(large_file, "_lock_chunk", side_effect=lambda name: job.chunks[0]),
			patch.object(large_file.frappe, "db", Mock()),
			patch.object(large_file.frappe, "enqueue") as enqueue,
			self.assertRaises(policy.Denied) as failure,
		):
			large_file.retry_chunk("job-1", 0)
		self.assertEqual(failure.exception.code, "chunk_not_failed")
		enqueue.assert_not_called()


if __name__ == "__main__":
	unittest.main()
