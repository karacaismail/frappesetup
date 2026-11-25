"""G-10: the daily US dollar to Turkish lira rate.

The product owner decided on 24 November 2026 that the lira price is computed from a rate. The
main source is the TCMB forex selling rate (ForexSelling). When TCMB fails, the ECB reference
rates give the rate as TRY per euro divided by USD per euro. Google is never used.

Frappe's own scheduler runs ``update_rate`` once a day (``scheduler_events`` in hooks.py). Each
rate used is kept in a ``PTR Exchange Rate`` record with its date, source and value. When both
sources fail, the last known rate stays in use and System Managers get an email.

Only the two fixed addresses in ``SOURCE_URLS`` are called. They are constants, not settings.
Each request has a timeout, follows no redirect and reads at most ``MAX_BYTES``. The XML is read
with expat directly: a DOCTYPE, an entity declaration or an external entity stops the parser, so
no entity is ever expanded or fetched. This is the method defusedxml uses.

The product owner fixed the rate checks on 25 November 2026. They are constants, not settings.
A rate must lie from ``MIN_RATE`` to ``MAX_RATE`` lira per US dollar. It may move at most
``MAX_DEVIATION`` from the newest record. Without a record only the range is checked. A rate out
of range, a larger move, a decimal error or a future date is a source failure: the next source is
tried. A larger move also sends System Managers an email, even when ECB gives a usable rate.
"""

import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from xml.parsers import expat

import frappe

DOCTYPE = "PTR Exchange Rate"
OPERATOR_ROLE = "System Manager"
SOURCE_URLS = {
	"TCMB": "https://www.tcmb.gov.tr/kurlar/today.xml",
	"ECB": "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
}
SOURCE_ORDER = ("TCMB", "ECB")
# (connect, read) seconds. The whole download also stops after DEADLINE seconds.
TIMEOUT = (5, 10)
DEADLINE = 20
MAX_BYTES = 256 * 1024
STALE_DAYS = 3
RATE_PLACES = Decimal("0.0001")
MONEY_PLACES = Decimal("0.01")
XML_DECLARATION = re.compile(rb"\A\s*<\?xml[^>]*?encoding=[\"']([A-Za-z0-9_-]+)[\"'][^>]*\?>")
ALLOWED_ENCODINGS = {"utf-8", "iso-8859-9", "windows-1254"}
INVOICE_FIELDS = ("try_exchange_rate", "try_exchange_rate_date", "try_exchange_rate_source")
# G-10 rate checks, fixed by the product owner. Lira per one US dollar, limits included.
MIN_RATE = Decimal("1")
MAX_RATE = Decimal("500")
# The largest allowed move from the newest record, 15 percent. Exactly 15 percent is allowed.
MAX_DEVIATION = Decimal("0.15")


def commercial_round(amount: Decimal, places: Decimal = MONEY_PLACES) -> Decimal:
	"""Frappe's "Commercial Rounding": a half rounds away from zero."""
	return Decimal(amount).quantize(places, rounding=ROUND_HALF_UP)


def to_try(price_usd, rate) -> Decimal:
	return commercial_round(Decimal(str(price_usd)) * Decimal(str(rate)))


class RateSourceError(ValueError):
	"""A source did not answer with a usable rate."""


class RateDeviationError(RateSourceError):
	"""The rate moved more than ``MAX_DEVIATION`` from the newest record."""

	def __init__(self, source: str, rate: Decimal, last: dict):
		super().__init__("Exchange rate moved more than the allowed deviation.")
		self.source, self.rate, self.last = source, rate, last


def download(url: str) -> bytes:
	if url not in SOURCE_URLS.values():
		raise ValueError("Exchange rate address is not allowed.")
	# Imported here so that the plan list works where requests is not installed.
	import requests

	try:
		return _read(requests, url)
	except requests.RequestException as exc:
		raise RateSourceError(type(exc).__name__) from exc


def _read(requests, url: str) -> bytes:
	started = time.monotonic()
	with requests.get(
		url,
		timeout=TIMEOUT,
		allow_redirects=False,
		stream=True,
		headers={"Accept": "application/xml"},
	) as response:
		if response.status_code != 200:
			raise RateSourceError(f"Exchange rate source answered {response.status_code}.")
		body = bytearray()
		for chunk in response.iter_content(chunk_size=16384):
			body += chunk
			if len(body) > MAX_BYTES:
				raise RateSourceError("Exchange rate answer is too large.")
			if time.monotonic() - started > DEADLINE:
				raise RateSourceError("Exchange rate download took too long.")
	return bytes(body)


@dataclass
class Node:
	"""One XML element. ``tag`` has no namespace."""

	tag: str
	attrib: dict
	children: list = field(default_factory=list)
	text: str = ""

	def all(self, tag):
		return [child for child in self.children if child.tag == tag]

	def child_text(self, tag):
		found = self.all(tag)
		return found[0].text.strip() if found else None


def _refuse(*_args):
	raise ValueError("Exchange rate answer declares a DOCTYPE or an entity.")


def parse_xml(body: bytes) -> Node:
	"""Parse a small XML answer. A DOCTYPE or an entity declaration is refused."""
	declaration = XML_DECLARATION.match(body)
	encoding = declaration.group(1).decode("ascii").lower() if declaration else "utf-8"
	if encoding not in ALLOWED_ENCODINGS:
		raise ValueError("Exchange rate answer has an unexpected encoding.")
	text = body.decode(encoding)
	if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
		_refuse()
	# The text is already decoded, so the declaration with its encoding is removed.
	text = re.sub(r"\A\s*<\?xml[^>]*\?>", "", text)

	parser = expat.ParserCreate(namespace_separator="}")
	parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
	parser.StartDoctypeDeclHandler = _refuse
	parser.EntityDeclHandler = _refuse
	parser.UnparsedEntityDeclHandler = _refuse
	parser.ExternalEntityRefHandler = _refuse
	stack, roots = [], []

	def start(name, attrib):
		node = Node(name.rsplit("}", 1)[-1], dict(attrib))
		(stack[-1].children if stack else roots).append(node)
		stack.append(node)

	def end(_name):
		stack.pop()

	def characters(chunk):
		if stack:
			stack[-1].text += chunk

	parser.StartElementHandler = start
	parser.EndElementHandler = end
	parser.CharacterDataHandler = characters
	try:
		parser.Parse(text, True)
	except expat.ExpatError as exc:
		raise ValueError("Exchange rate answer is not valid XML.") from exc
	if len(roots) != 1:
		raise ValueError("Exchange rate answer has no single root.")
	return roots[0]


def _positive(raw_number) -> Decimal:
	try:
		number = Decimal(str(raw_number).strip())
	except (InvalidOperation, AttributeError) as exc:
		raise ValueError("Exchange rate is not a number.") from exc
	if not number.is_finite() or number <= 0:
		raise ValueError("Exchange rate must be above zero.")
	return number


def parse_tcmb(body: bytes) -> tuple[date, Decimal]:
	root = parse_xml(body)
	if root.tag != "Tarih_Date":
		raise ValueError("TCMB answer has an unexpected shape.")
	day = datetime.strptime(root.attrib.get("Tarih", ""), "%d.%m.%Y").date()
	for currency in root.all("Currency"):
		if currency.attrib.get("CurrencyCode") == "USD":
			unit = _positive(currency.child_text("Unit"))
			selling = _positive(currency.child_text("ForexSelling"))
			return day, commercial_round(selling / unit, RATE_PLACES)
	raise ValueError("TCMB answer has no US dollar rate.")


def parse_ecb(body: bytes) -> tuple[date, Decimal]:
	root = parse_xml(body)
	days = [cube for outer in root.all("Cube") for cube in outer.all("Cube") if "time" in cube.attrib]
	if len(days) != 1:
		raise ValueError("ECB answer has an unexpected shape.")
	cube = days[0]
	rates = {row.attrib.get("currency"): row.attrib.get("rate") for row in cube.all("Cube")}
	if "USD" not in rates or "TRY" not in rates:
		raise ValueError("ECB answer has no US dollar or Turkish lira rate.")
	day = date.fromisoformat(cube.attrib["time"])
	return day, commercial_round(_positive(rates["TRY"]) / _positive(rates["USD"]), RATE_PLACES)


PARSERS = {"TCMB": parse_tcmb, "ECB": parse_ecb}


def _record(source: str, day: date, rate: Decimal) -> dict:
	"""Keep the rate. No role may create this record, so only Administrator writes it.

	Frappe's scheduler and ``bench execute`` both run as Administrator.
	"""
	name = f"{source}-{day.isoformat()}"
	if not frappe.db.exists(DOCTYPE, name):
		frappe.get_doc({"doctype": DOCTYPE, "source": source, "rate_date": day, "rate": str(rate)}).insert(
			set_name=name
		)
	return {"source": source, "rate_date": day, "rate": rate}


def _mail_admins(title: str, message: str) -> None:
	users = frappe.get_all(
		"Has Role", filters={"role": OPERATOR_ROLE, "parenttype": "User"}, fields=["parent"]
	)
	recipients = sorted({row["parent"] for row in users} - {"Administrator", "Guest"})
	if recipients:
		frappe.sendmail(recipients=recipients, subject=title, message=message)


def _alert_admins(failures: list[str]) -> None:
	title = frappe._("Turkish lira rate could not be updated", context="press_tr")
	message = frappe._("TCMB and ECB did not answer. The last known rate stays in use.", context="press_tr")
	frappe.log_error(title=title, message="\n".join([message, *failures]))
	_mail_admins(title, message)


def _alert_deviation(deviations: list[RateDeviationError]) -> None:
	title = frappe._("Turkish lira rate deviation", context="press_tr")
	message = frappe._(
		"A source gave a rate that moved more than 15 percent. The rate was not recorded.",
		context="press_tr",
	)
	lines = [
		f"{error.source}: {error.rate} ({error.last['source']} {error.last['rate_date'].isoformat()}: "
		f"{error.last['rate']})"
		for error in deviations
	]
	frappe.log_error(title=title, message="\n".join([message, *lines]))
	_mail_admins(title, "\n".join([message, *lines]))


def check_rate(source: str, day: date, rate: Decimal, last) -> None:
	"""Refuse a rate dated in the future, out of range or too far from the newest record."""
	if day > frappe.utils.getdate():
		raise RateSourceError("Exchange rate date is in the future.")
	if not MIN_RATE <= rate <= MAX_RATE:
		raise RateSourceError("Exchange rate is out of range.")
	if last is not None and abs(rate - last["rate"]) > last["rate"] * MAX_DEVIATION:
		raise RateDeviationError(source, rate, last)


def _fetch(source: str, last) -> tuple[date, Decimal]:
	try:
		day, rate = PARSERS[source](download(SOURCE_URLS[source]))
	except ArithmeticError as exc:
		# A decimal error, for example a rate of 1E40 that cannot be rounded.
		raise RateSourceError("Exchange rate is not a usable number.") from exc
	check_rate(source, day, rate, last)
	return day, rate


def update_rate():
	"""Fetch today's rate. Frappe's scheduler calls this once a day.

	TCMB publishes no rate on weekends and holidays. Its file then still holds the last bulletin,
	so that date is kept and no record is written twice.
	"""
	failures, deviations, recorded = [], [], None
	last = current_rate()
	for source in SOURCE_ORDER:
		try:
			day, rate = _fetch(source, last)
		except RateDeviationError as exc:
			deviations.append(exc)
			failures.append(f"{source}: {type(exc).__name__}")
			continue
		except ValueError as exc:
			failures.append(f"{source}: {type(exc).__name__}")
			continue
		recorded = _record(source, day, rate)
		break
	if deviations:
		_alert_deviation(deviations)
	if recorded is None:
		_alert_admins(failures)
	return recorded


def _as_date(day_or_text) -> date:
	if isinstance(day_or_text, datetime):
		return day_or_text.date()
	return day_or_text if isinstance(day_or_text, date) else date.fromisoformat(str(day_or_text))


def current_rate(on=None):
	"""Return the newest rate dated on or before ``on``. TCMB wins over ECB on the same date."""
	day = _as_date(on) if on else frappe.utils.getdate()
	rows = frappe.get_all(
		DOCTYPE,
		filters={"rate_date": ["<=", day]},
		fields=["source", "rate_date", "rate"],
		order_by="rate_date desc",
		limit=len(SOURCE_ORDER),
	)
	if not rows:
		return None
	row = max(rows, key=lambda row: (_as_date(row["rate_date"]), row["source"] == "TCMB"))
	rate_date = _as_date(row["rate_date"])
	return {
		"source": row["source"],
		"rate_date": rate_date,
		"rate": Decimal(str(row["rate"])),
		"stale": (day - rate_date).days > STALE_DAYS,
	}


def rate_warning(rate):
	if rate is None:
		return frappe._("No Turkish lira rate is recorded yet.", context="press_tr")
	if rate["stale"]:
		return frappe._(
			"The Turkish lira rate is older than 3 days. Rate date: {0}.", context="press_tr"
		).format(rate["rate_date"].isoformat())
	return None


def set_invoice_rate(doc, method=None):
	"""Fix the rate when an invoice leaves Draft. The rate never changes after that.

	The rate is the newest one on the day the invoice is issued. The lira total follows the dollar
	total with that fixed rate and Commercial Rounding. A Draft invoice has no rate: its three rate
	fields and the lira total are cleared, so only this function writes the rate.
	"""
	before = doc.get_doc_before_save()
	was_draft = before is None or before.get("status") == "Draft"
	if doc.get("status") == "Draft" and was_draft:
		for fieldname in (*INVOICE_FIELDS, "try_total"):
			setattr(doc, fieldname, None)
		return
	if not was_draft and before.get("try_exchange_rate"):
		if any(str(doc.get(field) or "") != str(before.get(field) or "") for field in INVOICE_FIELDS):
			frappe.throw(frappe._("You cannot change the invoice exchange rate.", context="press_tr"))
	elif was_draft:
		rate = current_rate()
		if rate is None:
			frappe.log_error(
				title=frappe._("Invoice has no Turkish lira rate", context="press_tr"),
				message=str(doc.get("name") or ""),
			)
			return
		doc.try_exchange_rate = str(rate["rate"])
		doc.try_exchange_rate_date = rate["rate_date"]
		doc.try_exchange_rate_source = rate["source"]
	if doc.get("try_exchange_rate"):
		doc.try_total = str(to_try(doc.get("total") or 0, doc.try_exchange_rate))
