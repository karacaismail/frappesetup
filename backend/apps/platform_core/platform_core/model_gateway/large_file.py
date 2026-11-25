"""Large file jobs: server-side page text, chunk plan and chunk dispatch (G-156).

A large PDF never goes to a provider as a file. The server reads its text page by page.
Scanned pages use the OCR step of this platform server. The text is cut at page
boundaries to fit the smallest context size of the route. Each chunk then goes
through the gateway, which masks it (G-90) and picks an account. The user starts
the job; it runs on the background queue and has no schedule.
"""

import json
from dataclasses import dataclass

import frappe
from frappe.utils import add_to_date, now_datetime
from pypdf import PdfReader

from platform_core.model_gateway import gateway, ledger, policy
from platform_core.model_gateway.policy import Denied

JOB = "PLT AI File Job"
CHUNK = "PLT AI File Chunk"
QUEUE = "long"
PAGE_SEPARATOR = "\n"
# The longest JSON escape of one character is six bytes (\u001f).
MIN_CHUNK_BYTES = 8
MAX_INSTRUCTION_BYTES = 16 * 1024
# Safe defaults. Site settings model_gateway_file_max_pages and model_gateway_file_max_chunks
# replace them; a missing setting keeps the default, an invalid one stops the job.
DEFAULT_MAX_PAGES = 1000
DEFAULT_MAX_CHUNKS = 200
# How long chunk text may wait. A planned job that is not started and a chunk whose worker
# stopped would keep their text forever. Site settings model_gateway_file_planned_ttl and
# model_gateway_file_running_ttl replace these values in seconds.
# The running limit is far above one model call: gateway.MAX_ROUTE_SECONDS is 60 seconds.
DEFAULT_PLANNED_TTL = 24 * 60 * 60
DEFAULT_RUNNING_TTL = 60 * 60
CLEANUP_ROLE = "System Manager"


@dataclass(frozen=True)
class Chunk:
	index: int
	first_page: int
	last_page: int
	text: str


@dataclass(frozen=True)
class Plan:
	chunks: list
	estimated_cost: object
	currency: str | None

	@property
	def chunk_count(self):
		return len(self.chunks)


def _clean(text):
	# Lone surrogates from broken PDF text cannot be encoded for the provider.
	return text.encode("utf-8", "replace").decode("utf-8")


def page_texts(pages, ocr):
	"""Return one text per page. A page without text goes to the OCR step."""
	texts = []
	for index, page in enumerate(pages):
		text = page.extract_text() or ""
		if not text.strip():
			if ocr is None:
				raise Denied(422, "ocr_unavailable")
			text = ocr(index, page) or ""
		texts.append(_clean(text))
	return texts


def messages(instruction, text):
	return [{"role": "system", "content": instruction}, {"role": "user", "content": text}]


def _size(text):
	"""Bytes the text adds to the JSON request body."""
	return len(json.dumps(text, ensure_ascii=False).encode("utf-8")) - 2


def _budget(instruction, targets, limit):
	active = [target for target in targets if target.active]
	if not active:
		raise Denied(503, "provider_unavailable")
	context = min(target.model.context_size or 0 for target in active)
	overhead = len(json.dumps([messages(instruction, ""), [], None], ensure_ascii=False).encode("utf-8"))
	budget = min(context - limit, policy.MAX_BYTES) - overhead
	if budget < MIN_CHUNK_BYTES:
		raise Denied(400, "context_too_small")
	return active, budget


def _split(text, budget):
	"""Cut one page that is larger than a chunk, preferably at a space."""
	parts, start, size, space = [], 0, 0, None
	index = 0
	while index < len(text):
		step = _size(text[index])
		if size + step > budget:
			cut = space + 1 if space is not None and space + 1 > start else index
			parts.append(text[start:cut])
			start, space = cut, None
			size = _size(text[start:index])
			continue
		size += step
		if text[index].isspace():
			space = index
		index += 1
	parts.append(text[start:])
	return parts


def _chunks(pages, budget):
	chunks, current, first, size = [], [], 0, 0
	separator = _size(PAGE_SEPARATOR)

	def flush(last):
		if current:
			chunks.append(Chunk(len(chunks), first, last, PAGE_SEPARATOR.join(current)))

	for number, text in enumerate(pages):
		page_size = _size(text)
		if page_size > budget:
			flush(number - 1)
			current = []
			for part in _split(text, budget):
				chunks.append(Chunk(len(chunks), number, number, part))
			size = 0
			continue
		extra = page_size + (separator if current else 0)
		if current and size + extra > budget:
			flush(number - 1)
			current, size, extra = [], 0, page_size
		if not current:
			first = number
		current.append(text)
		size += extra
	flush(len(pages) - 1)
	return chunks


def _estimate(chunks, targets, instruction, limit):
	"""Return the largest reservation over the route targets, or None if unknown."""
	currencies = {target.model.cost_currency for target in targets}
	if len(currencies) != 1:
		return None, None
	total = 0
	for chunk in chunks:
		request = policy.Request(messages(instruction, chunk.text), [], None, limit)
		costs = [
			ledger.price(target.model, gateway.input_token_bound(target.model, request), limit)
			for target in targets
		]
		if any(cost is None for cost in costs):
			return None, None
		total += max(costs)
	return total, currencies.pop()


def _bytes(text):
	return len(text.encode("utf-8"))


def _setting(key, default):
	configured = frappe.conf.get(key)
	if configured is None:
		return default
	if type(configured) is not int or configured < 1:
		raise Denied(503, "invalid_setting")
	return configured


def plan(pages, targets, instruction, limit, max_chunks=None):
	"""Cut page texts into chunks and estimate their cost without contacting a provider."""
	active, budget = _budget(instruction, targets, limit)
	chunks = _chunks(pages, budget)
	if max_chunks is not None and len(chunks) > max_chunks:
		raise Denied(413, "file_too_large")
	cost, currency = _estimate(chunks, active, instruction, limit)
	return Plan(chunks, cost, currency)


def _ocr_step(path):
	hooks = frappe.get_hooks("model_gateway_ocr")
	if not hooks:
		return None
	recognize = frappe.get_attr(hooks[-1])
	return lambda index, page: recognize(path, index, page)


def _job(name):
	if not gateway._valid_name(name):
		raise Denied(400, "invalid_request")
	try:
		return frappe.get_doc(JOB, name)
	except frappe.DoesNotExistError:
		raise frappe.PermissionError from None


def _require_owner(job):
	policy.require_user()
	if job.owner != frappe.session.user and policy.MANAGERS.isdisjoint(frappe.get_roles()):
		raise frappe.PermissionError


def _source_texts(job, count=None):
	"""Read the page texts of the job file, optionally only the first pages."""
	path = frappe.get_doc("File", job.source_file).get_full_path()
	pages = PdfReader(path).pages
	if len(pages) > _setting("model_gateway_file_max_pages", DEFAULT_MAX_PAGES):
		raise Denied(413, "file_too_large")
	if count is not None:
		pages = pages[:count]
	return page_texts(pages, _ocr_step(path))


def _chunk_text(job, chunk):
	"""Cut the chunk again from the file. Its stored text is removed after each attempt."""
	texts = _source_texts(job, chunk.last_page)
	_route, targets = gateway.route_targets(job.route)
	_active, budget = _budget(job.instruction, targets, job.output_limit)
	for candidate in _chunks(texts, budget):
		if candidate.index == chunk.chunk_index:
			found = (candidate.first_page + 1, candidate.last_page + 1, _bytes(candidate.text))
			if found == (chunk.first_page, chunk.last_page, chunk.byte_count):
				return candidate.text
			break
	raise Denied(409, "source_changed")


def _log_failure(title, error):
	# Only the error class is written. A Frappe traceback may hold local variables with chunk text.
	frappe.log_error(title, type(error).__name__)


def _lock_chunk(name):
	return gateway.lock_row(CHUNK, name, ("name", "status", "content"))


def _commit():
	frappe.db.commit()  # nosemgrep


def _expire_stale():
	"""Fail jobs and chunks that waited too long and remove their text.

	There is no schedule. The entry functions call this first, and a System Manager
	can call expire_stale_jobs by hand.
	"""
	now = now_datetime()
	planned_before = add_to_date(
		now, seconds=-_setting("model_gateway_file_planned_ttl", DEFAULT_PLANNED_TTL)
	)
	running_before = add_to_date(
		now, seconds=-_setting("model_gateway_file_running_ttl", DEFAULT_RUNNING_TTL)
	)
	expired = 0
	for name in frappe.get_all(
		JOB, filters={"status": "planned", "modified": ["<", planned_before]}, pluck="name"
	):
		row = gateway.lock_row(JOB, name, ("name", "status", "modified"))
		if row.status == "planned" and row.modified < planned_before:
			frappe.db.set_value(JOB, name, {"status": "failed", "failure_code": "expired"})
			frappe.db.set_value(CHUNK, {"parenttype": JOB, "parent": name}, {"content": None})
			expired += 1
		_commit()
	lost = set()
	for chunk in frappe.get_all(
		CHUNK,
		filters={"parenttype": JOB, "status": "running", "modified": ["<", running_before]},
		fields=["name", "parent"],
	):
		row = gateway.lock_row(CHUNK, chunk.name, ("name", "status", "modified"))
		if row.status == "running" and row.modified < running_before:
			values = {"status": "failed", "failure_code": "worker_lost", "content": None}
			frappe.db.set_value(CHUNK, chunk.name, values)
			lost.add((chunk.parent, chunk.name))
		_commit()
	for parent in sorted({parent for parent, _name in lost}):
		_settle(parent)
	return {"expired_jobs": expired, "lost_chunks": len(lost)}


def expire_stale_jobs():
	"""Run the cleanup by hand. Only a System Manager may call it."""
	policy.require_user()
	if CLEANUP_ROLE not in frappe.get_roles():
		raise frappe.PermissionError
	gateway._require_clean_transaction()
	return _expire_stale()


def create_job(route, file, instruction, limit=1024):
	"""Record a file job and queue its text extraction. No provider is called."""
	policy.require_user()
	gateway._require_clean_transaction()
	_expire_stale()
	if not (
		isinstance(instruction, str)
		and instruction.strip()
		and len(instruction.encode("utf-8")) <= MAX_INSTRUCTION_BYTES
		and type(limit) is int
		and 1 <= limit <= policy.MAX_OUTPUT
	):
		raise Denied(400, "invalid_request")
	route, _targets = gateway.route_targets(route)
	source = gateway._document("File", file)
	if not frappe.has_permission("File", "read", doc=source):
		raise frappe.PermissionError
	if not (source.file_name or "").lower().endswith(".pdf"):
		raise Denied(400, "unsupported_file")
	# Internal record of an authorized request. Callers cannot set its fields directly.
	job = frappe.get_doc(
		{
			"doctype": JOB,
			"route": route.name,
			"source_file": source.name,
			"instruction": instruction,
			"output_limit": limit,
			"status": "preparing",
		}
	).insert(ignore_permissions=True)
	_commit()
	frappe.enqueue(
		"platform_core.model_gateway.large_file.prepare_job",
		queue=QUEUE,
		file_job=job.name,
		enqueue_after_commit=True,
	)
	return job.name


def prepare_job(file_job):
	"""Queue step: read the PDF page by page and store the chunk plan."""
	job = _job(file_job)
	if job.status != "preparing":
		return
	try:
		texts = _source_texts(job)
		_route, targets = gateway.route_targets(job.route)
		max_chunks = _setting("model_gateway_file_max_chunks", DEFAULT_MAX_CHUNKS)
		result = plan(texts, targets, job.instruction, job.output_limit, max_chunks)
	except Denied as failure:
		frappe.db.set_value(JOB, job.name, {"status": "failed", "failure_code": failure.code})
		_commit()
		return
	except frappe.PermissionError:
		frappe.db.set_value(JOB, job.name, {"status": "failed", "failure_code": "permission_denied"})
		_commit()
		return
	except Exception as error:
		frappe.db.rollback()
		_log_failure("Large file text step failed", error)
		frappe.db.set_value(JOB, job.name, {"status": "failed", "failure_code": "unreadable_file"})
		_commit()
		return
	job.chunks = []
	for chunk in result.chunks:
		job.append(
			"chunks",
			{
				"chunk_index": chunk.index,
				"first_page": chunk.first_page + 1,
				"last_page": chunk.last_page + 1,
				"content": chunk.text,
				"byte_count": _bytes(chunk.text),
				"status": "planned",
			},
		)
	job.update(
		{
			"status": "planned",
			"chunk_count": result.chunk_count,
			"estimate_known": int(result.estimated_cost is not None),
			"estimated_cost": result.estimated_cost or 0,
			"currency": result.currency,
		}
	)
	job.save(ignore_permissions=True)
	_commit()


def start_job(file_job):
	"""Queue every planned chunk after the user has seen the count and the cost."""
	job = _job(file_job)
	_require_owner(job)
	gateway._require_clean_transaction()
	_expire_stale()
	job = _job(file_job)
	if job.status != "planned":
		raise Denied(409, "job_not_planned")
	for chunk in job.chunks:
		frappe.db.set_value(CHUNK, chunk.name, {"status": "queued"})
	frappe.db.set_value(JOB, job.name, {"status": "queued"})
	_commit()
	frappe.enqueue(
		"platform_core.model_gateway.large_file.run_job",
		queue=QUEUE,
		file_job=job.name,
		enqueue_after_commit=True,
	)


def _send(job, chunk):
	row = _lock_chunk(chunk.name)
	if row.status != "queued":
		_commit()
		return
	frappe.db.set_value(CHUNK, row.name, {"status": "running"})
	_commit()
	tag = gateway.ChunkTag(job.name, chunk.chunk_index)
	try:
		text = row.content or _chunk_text(job, chunk)
		result = gateway.complete_chunk(job.route, tag, messages(job.instruction, text), job.output_limit)
	except Denied as failure:
		values = {"status": "failed", "failure_code": failure.code}
	except frappe.PermissionError:
		values = {"status": "failed", "failure_code": "permission_denied"}
	except Exception as error:
		frappe.db.rollback()
		_log_failure("Large file chunk failed", error)
		values = {"status": "failed", "failure_code": "internal_error"}
	else:
		values = {"status": "done", "failure_code": None, "result": result["text"]}
	# The text is kept only until the attempt ends. A retry cuts it again from the file.
	values["content"] = None
	frappe.db.set_value(CHUNK, row.name, values)
	_commit()


def _settle(name):
	chunks = _job(name).chunks
	statuses = [chunk.status for chunk in chunks]
	if any(status in {"queued", "running"} for status in statuses):
		status = "running"
	elif any(status == "failed" for status in statuses):
		status = "failed"
	else:
		status = "completed"
	if status != "running":
		# A finished job keeps no chunk text, only order, pages, byte count and state.
		for chunk in chunks:
			if chunk.content:
				frappe.db.set_value(CHUNK, chunk.name, {"content": None})
	frappe.db.set_value(JOB, name, {"status": status})
	_commit()


def run_job(file_job):
	"""Queue step: send every queued chunk. A failed chunk does not stop the others."""
	job = _job(file_job)
	frappe.db.set_value(JOB, job.name, {"status": "running"})
	_commit()
	for chunk in job.chunks:
		if chunk.status == "queued":
			_send(job, chunk)
	_settle(job.name)


def run_chunk(file_job, chunk_index):
	"""Queue step: send one chunk again."""
	job = _job(file_job)
	for chunk in job.chunks:
		if chunk.chunk_index == chunk_index:
			_send(job, chunk)
	_settle(job.name)


def retry_chunk(file_job, chunk_index):
	"""Queue only the given failed chunk. Finished chunks are not sent again."""
	job = _job(file_job)
	_require_owner(job)
	_expire_stale()
	chunk = None
	if type(chunk_index) is int:
		chunk = next((item for item in job.chunks if item.chunk_index == chunk_index), None)
	if chunk is None:
		raise Denied(404, "chunk_not_found")
	row = _lock_chunk(chunk.name)
	if row.status != "failed":
		_commit()
		raise Denied(409, "chunk_not_failed")
	frappe.db.set_value(CHUNK, row.name, {"status": "queued", "failure_code": None})
	frappe.db.set_value(JOB, job.name, {"status": "running"})
	_commit()
	frappe.enqueue(
		"platform_core.model_gateway.large_file.run_chunk",
		queue=QUEUE,
		file_job=job.name,
		chunk_index=chunk_index,
		enqueue_after_commit=True,
	)


def job_status(file_job):
	"""Return the plan and progress. The chunk count and estimate exist before the start."""
	job = _job(file_job)
	_require_owner(job)
	_expire_stale()
	job = _job(file_job)
	return {
		"name": job.name,
		"status": job.status,
		"failure_code": job.failure_code,
		"chunk_count": job.chunk_count,
		"estimated_cost": str(job.estimated_cost) if job.estimate_known else None,
		"currency": job.currency if job.estimate_known else None,
		"chunks": [
			{
				"index": chunk.chunk_index,
				"first_page": chunk.first_page,
				"last_page": chunk.last_page,
				"byte_count": chunk.byte_count,
				"status": chunk.status,
				"failure_code": chunk.failure_code,
			}
			for chunk in job.chunks
		],
	}
