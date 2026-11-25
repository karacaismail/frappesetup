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

from platform_core.model_gateway import gateway, ledger, policy
from platform_core.model_gateway.policy import Denied

JOB = "PLT AI File Job"
CHUNK = "PLT AI File Chunk"
QUEUE = "long"
PAGE_SEPARATOR = "\n"
# The longest JSON escape of one character is six bytes (\u001f).
MIN_CHUNK_BYTES = 8
MAX_INSTRUCTION_BYTES = 16 * 1024


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


def plan(pages, targets, instruction, limit):
	"""Cut page texts into chunks and estimate their cost without contacting a provider."""
	active, budget = _budget(instruction, targets, limit)
	chunks = _chunks(pages, budget)
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


def _lock_chunk(name):
	return gateway.lock_row(CHUNK, name, ("name", "status", "content"))


def _commit():
	frappe.db.commit()  # nosemgrep


def create_job(route, file, instruction, limit=1024):
	"""Record a file job and queue its text extraction. No provider is called."""
	policy.require_user()
	gateway._require_clean_transaction()
	if not (
		isinstance(instruction, str)
		and instruction.strip()
		and len(instruction.encode("utf-8")) <= MAX_INSTRUCTION_BYTES
		and type(limit) is int
		and 1 <= limit <= policy.MAX_OUTPUT
	):
		raise Denied(400, "invalid_request")
	route, _ = gateway.route_targets(route)
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
		from pypdf import PdfReader

		path = frappe.get_doc("File", job.source_file).get_full_path()
		texts = page_texts(PdfReader(path).pages, _ocr_step(path))
		_, targets = gateway.route_targets(job.route)
		result = plan(texts, targets, job.instruction, job.output_limit)
	except Denied as failure:
		frappe.db.set_value(JOB, job.name, {"status": "failed", "failure_code": failure.code})
		_commit()
		return
	except frappe.PermissionError:
		frappe.db.set_value(JOB, job.name, {"status": "failed", "failure_code": "permission_denied"})
		_commit()
		return
	except Exception:
		frappe.db.rollback()
		frappe.log_error("Large file text step failed")
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
		result = gateway.complete_chunk(
			job.route, tag, messages(job.instruction, row.content), job.output_limit
		)
	except Denied as failure:
		values = {"status": "failed", "failure_code": failure.code}
	except frappe.PermissionError:
		values = {"status": "failed", "failure_code": "permission_denied"}
	except Exception:
		frappe.db.rollback()
		frappe.log_error("Large file chunk failed")
		values = {"status": "failed", "failure_code": "internal_error"}
	else:
		values = {"status": "done", "failure_code": None, "result": result["text"]}
	frappe.db.set_value(CHUNK, row.name, values)
	_commit()


def _settle(name):
	statuses = [chunk.status for chunk in _job(name).chunks]
	if any(status in {"queued", "running"} for status in statuses):
		status = "running"
	elif any(status == "failed" for status in statuses):
		status = "failed"
	else:
		status = "completed"
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
				"status": chunk.status,
				"failure_code": chunk.failure_code,
			}
			for chunk in job.chunks
		],
	}
