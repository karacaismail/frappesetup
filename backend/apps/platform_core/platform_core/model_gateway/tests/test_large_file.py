"""Large file jobs: page text, chunk plan, chunk dispatch and single-chunk retry (G-156)."""

import json
import unittest
from datetime import datetime, timedelta
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
		self.source_file = "fixture-file"
		self.chunks = [
			SimpleNamespace(
				name=f"chunk-{index}",
				chunk_index=index,
				first_page=index + 1,
				last_page=index + 1,
				byte_count=len(f"text {index}"),
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

		send, _enqueue = self._run(job, provider, large_file.run_job, "job-1")
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
			patch.object(large_file, "_expire_stale"),
			patch.object(large_file, "_lock_chunk", side_effect=lambda name: job.chunks[1]),
			patch.object(large_file.frappe, "db", Mock()),
			patch.object(large_file.frappe, "enqueue") as enqueue,
		):
			large_file.retry_chunk("job-1", 1)
		enqueue.assert_called_once()
		self.assertEqual(enqueue.call_args.kwargs["chunk_index"], 1)
		job.chunks[1].status = "queued"

		send, _enqueue = self._run(
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
			patch.object(large_file, "_expire_stale"),
			patch.object(large_file, "_lock_chunk", side_effect=lambda name: job.chunks[0]),
			patch.object(large_file.frappe, "db", Mock()),
			patch.object(large_file.frappe, "enqueue") as enqueue,
			self.assertRaises(policy.Denied) as failure,
		):
			large_file.retry_chunk("job-1", 0)
		self.assertEqual(failure.exception.code, "chunk_not_failed")
		enqueue.assert_not_called()


class PreparingJob(FakeJob):
	"""A job in the preparing step. It records whether chunk rows were written."""

	def __init__(self):
		super().__init__([])
		self.status = "preparing"
		self.failure_code = None
		self.saved = False

	def append(self, field, values):
		self.chunks.append(SimpleNamespace(**values))

	def update(self, values):
		for key, value in values.items():
			setattr(self, key, value)

	def save(self, **kwargs):
		self.saved = True


def _store_db(job):
	def set_value(doctype, name, values, *rest, **kwargs):
		if doctype == large_file.JOB:
			target = job
		else:
			target = next(chunk for chunk in job.chunks if chunk.name == name)
		for key, new_value in values.items():
			setattr(target, key, new_value)

	db = Mock()
	db.set_value.side_effect = set_value
	return db


class LimitTests(unittest.TestCase):
	"""A very large PDF is refused before any chunk row exists (AJA-725, finding 3)."""

	def _prepare(self, pages, conf, context=1100):
		job = PreparingJob()
		reader = SimpleNamespace(pages=[FakePage(text) for text in pages])
		source = SimpleNamespace(get_full_path=lambda: "/fixture/file.pdf")
		targets = [_target("api-1", "acc-1", _model(context))]
		with (
			patch.object(large_file, "_job", return_value=job),
			patch.object(large_file, "PdfReader", return_value=reader),
			patch.object(large_file.frappe, "get_doc", return_value=source),
			patch.object(large_file.frappe, "get_hooks", return_value=[]),
			patch.object(large_file.frappe, "conf", conf),
			patch.object(large_file.frappe, "db", _store_db(job)),
			patch.object(large_file.gateway, "route_targets", return_value=("fixture-route", targets)),
		):
			large_file.prepare_job("job-1")
		return job

	def test_file_with_too_many_pages_is_refused_without_chunk_rows(self):
		job = self._prepare(["page"] * 4, {"model_gateway_file_max_pages": 3})
		self.assertEqual((job.status, job.failure_code), ("failed", "file_too_large"))
		self.assertEqual(job.chunks, [])
		self.assertFalse(job.saved)

	def test_file_with_too_many_chunks_is_refused_without_chunk_rows(self):
		job = self._prepare(["a" * 300] * 4, {"model_gateway_file_max_chunks": 1})
		self.assertEqual((job.status, job.failure_code), ("failed", "file_too_large"))
		self.assertEqual(job.chunks, [])
		self.assertFalse(job.saved)

	def test_the_limits_follow_the_site_setting(self):
		pages = ["a" * 300] * 4
		allowed = self._prepare(
			pages, {"model_gateway_file_max_pages": 4, "model_gateway_file_max_chunks": 4}
		)
		self.assertEqual(allowed.status, "planned")
		self.assertTrue(allowed.saved)
		self.assertGreater(len(allowed.chunks), 1)
		fewer_pages = self._prepare(pages, {"model_gateway_file_max_pages": 3})
		self.assertEqual(fewer_pages.failure_code, "file_too_large")
		fewer_chunks = self._prepare(pages, {"model_gateway_file_max_chunks": len(allowed.chunks) - 1})
		self.assertEqual(fewer_chunks.failure_code, "file_too_large")

	def test_safe_defaults_apply_without_a_setting(self):
		self.assertEqual(self._prepare(["page"] * large_file.DEFAULT_MAX_PAGES, {}).status, "planned")
		refused = self._prepare(["page"] * (large_file.DEFAULT_MAX_PAGES + 1), {})
		self.assertEqual(refused.failure_code, "file_too_large")

	def test_invalid_setting_fails_closed(self):
		for setting in (0, -1, "100", 2.5, True):
			with self.subTest(setting=setting):
				job = self._prepare(["page"], {"model_gateway_file_max_pages": setting})
				self.assertEqual((job.status, job.failure_code), ("failed", "invalid_setting"))
				self.assertEqual(job.chunks, [])

	def test_planned_chunks_keep_their_byte_count(self):
		job = self._prepare(["ç" * 10, "b" * 5], {})
		self.assertEqual(
			[chunk.byte_count for chunk in job.chunks], [len(chunk.content.encode()) for chunk in job.chunks]
		)


class TextRetentionTests(unittest.TestCase):
	"""Chunk text lives only while the job runs (AJA-725, finding 2)."""

	def _run(self, job, provider, function, *args, rebuilt=None):
		store = {chunk.name: chunk for chunk in job.chunks}
		with (
			patch.object(large_file, "_job", return_value=job),
			patch.object(large_file, "_lock_chunk", side_effect=lambda name: store[name]),
			patch.object(large_file, "_source_texts", return_value=rebuilt or []) as source,
			patch.object(large_file.frappe, "db", _store_db(job)),
			patch.object(large_file.frappe, "enqueue"),
			patch.object(large_file.frappe, "log_error") as log_error,
			patch.object(large_file.gateway, "complete_chunk", side_effect=provider) as send,
		):
			function(*args)
		return send, log_error, source

	def _texts(self, job):
		return [chunk.content for chunk in job.chunks]

	def test_no_chunk_text_remains_after_a_successful_job(self):
		job = FakeJob(["queued", "queued", "queued"])
		self._run(job, lambda route, tag, messages, limit: {"text": "answer"}, large_file.run_job, "job-1")
		self.assertEqual(job.status, "completed")
		self.assertEqual(self._texts(job), [None, None, None])
		self.assertEqual([chunk.byte_count for chunk in job.chunks], [6, 6, 6])
		self.assertEqual([chunk.result for chunk in job.chunks], ["answer"] * 3)

	def test_no_chunk_text_remains_after_a_failed_job(self):
		job = FakeJob(["queued", "queued", "queued"])

		def provider(route, tag, messages, limit):
			if tag.index == 1:
				raise policy.Denied(503, "provider_unavailable")
			return {"text": "answer"}

		self._run(job, provider, large_file.run_job, "job-1")
		self.assertEqual(job.status, "failed")
		self.assertEqual(self._texts(job), [None, None, None])

	def test_a_finished_job_clears_text_its_chunks_still_hold(self):
		job = FakeJob(["done", "failed", "queued"])
		self._run(job, lambda route, tag, messages, limit: {"text": "answer"}, large_file.run_job, "job-1")
		self.assertEqual(self._texts(job), [None, None, None])

	def test_text_of_a_running_job_stays_until_its_chunk_is_answered(self):
		job = FakeJob(["queued", "queued"])
		seen = []

		def provider(route, tag, messages, limit):
			seen.append(self._texts(job))
			return {"text": "answer"}

		self._run(job, provider, large_file.run_job, "job-1")
		self.assertEqual(seen, [["text 0", "text 1"], [None, "text 1"]])

	def test_chunk_text_is_not_written_to_the_error_log(self):
		job = FakeJob(["queued"])

		def provider(route, tag, messages, limit):
			raise RuntimeError(messages[1]["content"])

		_send, log_error, _source = self._run(job, provider, large_file.run_job, "job-1")
		log_error.assert_called_once()
		logged = repr(log_error.call_args)
		self.assertNotIn("text 0", logged)
		# A message is given, so Frappe does not add a traceback with local variables.
		self.assertTrue(log_error.call_args.args[1:] or log_error.call_args.kwargs.get("message"))
		self.assertEqual(self._texts(job), [None])

	def test_retry_rebuilds_the_text_from_the_file_and_does_not_store_it(self):
		job = FakeJob(["done", "failed"])
		job.status = "failed"
		for chunk in job.chunks:
			chunk.content, chunk.byte_count = None, 600
		job.chunks[1].status = "queued"
		targets = [_target("api-1", "acc-1", _model(1100))]
		with patch.object(large_file.gateway, "route_targets", return_value=("fixture-route", targets)):
			send, _log, source = self._run(
				job,
				lambda route, tag, messages, limit: {"text": "answer"},
				large_file.run_chunk,
				"job-1",
				1,
				rebuilt=["a" * 600, "b" * 600],
			)
		source.assert_called_once_with(job, 2)
		self.assertEqual(send.call_args.args[2][1]["content"], "b" * 600)
		self.assertEqual(job.chunks[1].status, "done")
		self.assertEqual(self._texts(job), [None, None])

	def test_retry_refuses_text_that_no_longer_matches_the_plan(self):
		job = FakeJob(["done", "queued"])
		for chunk in job.chunks:
			chunk.content, chunk.byte_count = None, 600
		targets = [_target("api-1", "acc-1", _model(1100))]
		with patch.object(large_file.gateway, "route_targets", return_value=("fixture-route", targets)):
			send, _log, _source = self._run(
				job,
				lambda route, tag, messages, limit: {"text": "answer"},
				large_file.run_chunk,
				"job-1",
				1,
				rebuilt=["a" * 600, "c" * 500],
			)
		send.assert_not_called()
		self.assertEqual((job.chunks[1].status, job.chunks[1].failure_code), ("failed", "source_changed"))


NOW = datetime(2026, 11, 25, 12, 0, 0)


class ExpiryStore:
	"""In-memory jobs and chunks with modified times, queried like the database."""

	def __init__(self):
		self.jobs = {}

	def add(self, name, status, age, chunks):
		job = FakeJob([chunk_status for chunk_status, _age in chunks])
		job.name, job.status, job.failure_code = name, status, None
		job.chunk_count, job.estimate_known, job.estimated_cost, job.currency = len(chunks), 0, 0, None
		job.modified = NOW - timedelta(seconds=age)
		for chunk, (_status, chunk_age) in zip(job.chunks, chunks, strict=True):
			chunk.name = f"{name}-{chunk.chunk_index}"
			chunk.parent, chunk.parenttype = name, large_file.JOB
			chunk.modified = NOW - timedelta(seconds=chunk_age)
		self.jobs[name] = job
		return job

	def _rows(self, doctype):
		if doctype == large_file.JOB:
			return list(self.jobs.values())
		return [chunk for job in self.jobs.values() for chunk in job.chunks]

	def _row(self, doctype, name):
		return next(row for row in self._rows(doctype) if row.name == name)

	@staticmethod
	def _matches(row, filters):
		for key, expected in filters.items():
			value = getattr(row, key)
			if isinstance(expected, list):
				operator, operand = expected
				if operator != "<":
					raise AssertionError(operator)
				if not value < operand:
					return False
			elif value != expected:
				return False
		return True

	def get_all(self, doctype, filters=None, fields=None, pluck=None, **kwargs):
		rows = [row for row in self._rows(doctype) if self._matches(row, filters or {})]
		if pluck:
			return [getattr(row, pluck) for row in rows]
		return [SimpleNamespace(**{field: getattr(row, field) for field in fields}) for row in rows]

	def set_value(self, doctype, name, values, value=None, **kwargs):
		if not isinstance(values, dict):
			values = {values: value}
		if isinstance(name, dict):
			rows = [row for row in self._rows(doctype) if self._matches(row, name)]
		else:
			rows = [self._row(doctype, name)]
		for row in rows:
			for key, new_value in values.items():
				setattr(row, key, new_value)

	def lock_row(self, doctype, name, fields):
		return self._row(doctype, name)

	def db(self):
		db = Mock()
		db.set_value.side_effect = self.set_value
		return db


class ExpiryTests(unittest.TestCase):
	"""Chunk text of a job that never started or a worker that stopped is removed (AJA-741)."""

	HOUR = 60 * 60
	DAY = 24 * HOUR

	def setUp(self):
		self.store = ExpiryStore()
		self.conf = {}
		self.roles = ["System Manager"]
		patches = [
			patch.object(large_file, "now_datetime", return_value=NOW),
			patch.object(large_file.frappe, "conf", self.conf),
			patch.object(large_file.frappe, "get_all", side_effect=self.store.get_all),
			patch.object(large_file.frappe, "db", self.store.db()),
			patch.object(large_file.frappe, "enqueue"),
			patch.object(large_file.frappe, "get_roles", side_effect=lambda *args: self.roles),
			patch.object(large_file.gateway, "lock_row", side_effect=self.store.lock_row),
			patch.object(large_file.gateway, "_require_clean_transaction"),
			patch.object(large_file.policy, "require_user"),
			patch.object(large_file, "_job", side_effect=lambda name: self.store.jobs[name]),
			patch.object(large_file, "_require_owner"),
		]
		for item in patches:
			item.start()
			self.addCleanup(item.stop)

	def _texts(self, job):
		return [chunk.content for chunk in job.chunks]

	def test_planned_job_older_than_a_day_fails_as_expired_without_text(self):
		job = self.store.add("old", "planned", self.DAY + 1, [("planned", self.DAY + 1)] * 2)
		large_file.expire_stale_jobs()
		self.assertEqual((job.status, job.failure_code), ("failed", "expired"))
		self.assertEqual(self._texts(job), [None, None])

	def test_planned_job_younger_than_a_day_keeps_its_state_and_text(self):
		job = self.store.add("new", "planned", self.DAY - 60, [("planned", self.DAY - 60)] * 2)
		large_file.expire_stale_jobs()
		self.assertEqual((job.status, job.failure_code), ("planned", None))
		self.assertEqual(self._texts(job), ["text 0", "text 1"])

	def test_chunk_running_longer_than_an_hour_fails_as_worker_lost(self):
		job = self.store.add("job", "running", self.HOUR + 1, [("done", 10), ("running", self.HOUR + 1)])
		job.chunks[0].content = None
		large_file.expire_stale_jobs()
		chunk = job.chunks[1]
		self.assertEqual((chunk.status, chunk.failure_code), ("failed", "worker_lost"))
		self.assertEqual(self._texts(job), [None, None])
		# No other chunk is running, so the job is settled as failed.
		self.assertEqual(job.status, "failed")

	def test_job_with_another_running_chunk_stays_running(self):
		job = self.store.add(
			"job", "running", self.HOUR + 1, [("running", self.HOUR + 1), ("running", 60), ("queued", 60)]
		)
		large_file.expire_stale_jobs()
		self.assertEqual([chunk.status for chunk in job.chunks], ["failed", "running", "queued"])
		self.assertEqual(job.status, "running")
		self.assertEqual(self._texts(job), [None, "text 1", "text 2"])

	def test_chunk_running_less_than_an_hour_is_not_touched(self):
		job = self.store.add("job", "running", 60, [("running", self.HOUR - 60)])
		large_file.expire_stale_jobs()
		self.assertEqual((job.chunks[0].status, job.chunks[0].content), ("running", "text 0"))
		self.assertEqual(job.status, "running")

	def test_lost_chunk_can_be_retried(self):
		job = self.store.add("job", "running", self.HOUR + 1, [("done", 10), ("running", self.HOUR + 1)])
		large_file.expire_stale_jobs()
		large_file.retry_chunk("job", 1)
		self.assertEqual(job.chunks[1].status, "queued")
		self.assertIsNone(job.chunks[1].failure_code)
		large_file.frappe.enqueue.assert_called_once()
		self.assertEqual(large_file.frappe.enqueue.call_args.kwargs["chunk_index"], 1)

	def test_the_waiting_times_follow_the_site_settings(self):
		self.conf.update({"model_gateway_file_planned_ttl": 60, "model_gateway_file_running_ttl": 30})
		planned = self.store.add("planned", "planned", 61, [("planned", 61)])
		running = self.store.add("running", "running", 31, [("running", 31)])
		large_file.expire_stale_jobs()
		self.assertEqual(planned.failure_code, "expired")
		self.assertEqual(running.chunks[0].failure_code, "worker_lost")

	def test_invalid_waiting_time_setting_fails_closed(self):
		for key in ("model_gateway_file_planned_ttl", "model_gateway_file_running_ttl"):
			for setting in (0, -1, "3600", 2.5, True):
				with self.subTest(key=key, setting=setting):
					self.conf.clear()
					self.conf[key] = setting
					with self.assertRaises(policy.Denied) as failure:
						large_file.expire_stale_jobs()
					self.assertEqual(failure.exception.code, "invalid_setting")

	def test_only_a_system_manager_can_start_the_cleanup_by_hand(self):
		job = self.store.add("old", "planned", self.DAY + 1, [("planned", self.DAY + 1)])
		for roles in (["PLT AI User"], ["PLT AI Manager"]):
			with self.subTest(roles=roles):
				self.roles = roles
				with self.assertRaises(large_file.frappe.PermissionError):
					large_file.expire_stale_jobs()
				self.assertEqual(job.status, "planned")
		self.roles = ["System Manager"]
		self.assertEqual(large_file.expire_stale_jobs(), {"expired_jobs": 1, "lost_chunks": 0})

	def test_start_refuses_an_expired_job(self):
		job = self.store.add("old", "planned", self.DAY + 1, [("planned", self.DAY + 1)])
		with self.assertRaises(policy.Denied) as failure:
			large_file.start_job("old")
		self.assertEqual(failure.exception.code, "job_not_planned")
		self.assertEqual((job.status, job.failure_code), ("failed", "expired"))
		large_file.frappe.enqueue.assert_not_called()

	def test_status_runs_the_cleanup_first(self):
		self.store.add("old", "planned", self.DAY + 1, [("planned", self.DAY + 1)])
		status = large_file.job_status("old")
		self.assertEqual((status["status"], status["failure_code"]), ("failed", "expired"))

	def test_retry_runs_the_cleanup_first(self):
		job = self.store.add("job", "running", self.HOUR + 1, [("running", self.HOUR + 1)])
		large_file.retry_chunk("job", 0)
		self.assertEqual(job.chunks[0].status, "queued")

	def test_create_runs_the_cleanup_first(self):
		job = self.store.add("old", "planned", self.DAY + 1, [("planned", self.DAY + 1)])
		with (
			patch.object(large_file.gateway, "route_targets", side_effect=policy.Denied(404, "stop_here")),
			self.assertRaises(policy.Denied),
		):
			large_file.create_job("route", "file", "Summarize.", 64)
		self.assertEqual(job.failure_code, "expired")


if __name__ == "__main__":
	unittest.main()
