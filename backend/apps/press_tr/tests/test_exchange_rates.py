"""G-10: the Turkish lira price comes from the daily US dollar rate.

The product owner decided on 24 November 2026 that the lira price is computed from a rate. The
main source is the TCMB forex selling rate (ForexSelling). ECB is the fallback. The tests never
reach the network: ``requests`` is replaced with a stub that serves the sample files in
``fixtures/exchange_rates``. ``frappe`` is replaced with an in-memory stub.
"""

import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from plan_stubs import APP_ROOT, FakeFrappe, Rejected, load

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "exchange_rates"
TCMB = "https://www.tcmb.gov.tr/kurlar/today.xml"
ECB = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
DOCTYPE = "PTR Exchange Rate"
TUESDAY, MONDAY, SATURDAY = date(2026, 11, 24), date(2026, 11, 23), date(2026, 11, 21)


class FakeRequestException(Exception):
	pass


class FakeResponse:
	def __init__(self, body, status_code=200):
		self.body, self.status_code = body, status_code

	def iter_content(self, chunk_size=1):
		for start in range(0, len(self.body), chunk_size):
			yield self.body[start : start + chunk_size]

	def close(self):
		pass

	def __enter__(self):
		return self

	def __exit__(self, *_exc):
		self.close()


class FakeRequests:
	"""Serve one answer per URL. An answer is bytes, a ``FakeResponse`` or an exception."""

	RequestException = FakeRequestException

	def __init__(self, answers=None):
		self.answers = answers or {}
		self.calls = []

	def get(self, url, **kwargs):
		self.calls.append((url, kwargs))
		answer = self.answers.get(url, FakeRequestException("down"))
		if isinstance(answer, Exception):
			raise answer
		return answer if isinstance(answer, FakeResponse) else FakeResponse(answer)


def sample(name):
	return (FIXTURES / name).read_bytes()


class RateCase(unittest.TestCase):
	def setUp(self):
		self.fake = FakeFrappe(self)
		self.fake.today = TUESDAY
		self.fake.records["Has Role"] = {
			"r1": {"role": "System Manager", "parenttype": "User", "parent": "ops@example.test"},
			"r2": {"role": "System Manager", "parenttype": "User", "parent": "Administrator"},
			"r3": {"role": "Press User", "parenttype": "User", "parent": "customer@example.test"},
		}
		self.requests = FakeRequests()
		self.errors, self.mails = [], []
		(self.rates,) = load(
			self, self.fake, "press_tr.exchange_rates", extra_modules={"requests": self.requests}
		)
		import sys

		frappe = sys.modules["frappe"]
		frappe.log_error = lambda title=None, message=None, **_kw: self.errors.append(title)
		frappe.sendmail = lambda **kwargs: self.mails.append(kwargs)

	def serve(self, tcmb=None, ecb=None):
		self.requests.answers = {
			url: answer for url, answer in ((TCMB, tcmb), (ECB, ecb)) if answer is not None
		}

	def stored(self):
		return self.fake.records.get(DOCTYPE, {})

	def store(self, source, day, rate):
		self.fake.records.setdefault(DOCTYPE, {})[f"{source}-{day.isoformat()}"] = {
			"source": source,
			"rate_date": day,
			"rate": rate,
		}


class SourceTest(RateCase):
	def test_tcmb_forex_selling_rate_is_used(self):
		self.serve(tcmb=sample("tcmb-today.xml"), ecb=sample("ecb-daily.xml"))
		rate = self.rates.update_rate()
		self.assertEqual(
			(rate["source"], rate["rate_date"], rate["rate"]), ("TCMB", TUESDAY, Decimal("41.3088"))
		)
		self.assertEqual([url for url, _kwargs in self.requests.calls], [TCMB])
		self.assertEqual(
			self.stored(),
			{
				"TCMB-2026-11-24": {
					"doctype": DOCTYPE,
					"name": "TCMB-2026-11-24",
					"source": "TCMB",
					"rate_date": TUESDAY,
					"rate": "41.3088",
				}
			},
		)
		self.assertEqual((self.errors, self.mails), ([], []))

	def test_ecb_is_used_when_tcmb_is_down(self):
		self.serve(ecb=sample("ecb-daily.xml"))
		rate = self.rates.update_rate()
		# 43.3125 TRY per euro divided by 1.05 USD per euro.
		self.assertEqual((rate["source"], rate["rate"]), ("ECB", Decimal("41.2500")))
		self.assertEqual([url for url, _kwargs in self.requests.calls], [TCMB, ECB])
		self.assertIn("ECB-2026-11-24", self.stored())
		self.assertEqual(self.mails, [])

	def test_last_known_rate_is_used_and_admins_are_told_when_both_are_down(self):
		self.store("TCMB", MONDAY, "41.1000")
		self.serve()
		self.assertIsNone(self.rates.update_rate())
		self.assertEqual(list(self.stored()), ["TCMB-2026-11-23"])
		current = self.rates.current_rate()
		self.assertEqual((current["rate"], current["rate_date"]), (Decimal("41.1000"), MONDAY))
		self.assertEqual(len(self.errors), 1)
		self.assertEqual(len(self.mails), 1)
		self.assertEqual(self.mails[0]["recipients"], ["ops@example.test"])

	def test_weekend_uses_the_last_published_rate(self):
		self.fake.today = SATURDAY
		self.store("TCMB", date(2026, 11, 20), "41.3088")
		self.serve(tcmb=sample("tcmb-friday.xml"))
		rate = self.rates.update_rate()
		self.assertEqual(rate["rate_date"], date(2026, 11, 20))
		# The Friday rate is not written twice.
		self.assertEqual(list(self.stored()), ["TCMB-2026-11-20"])
		self.assertFalse(self.rates.current_rate()["stale"])
		self.assertEqual(self.mails, [])

	def test_rate_older_than_three_days_shows_a_warning(self):
		self.store("TCMB", date(2026, 11, 20), "41.3088")
		self.fake.today = MONDAY
		self.assertFalse(self.rates.current_rate()["stale"])
		self.assertIsNone(self.rates.rate_warning(self.rates.current_rate()))
		self.fake.today = TUESDAY
		current = self.rates.current_rate()
		self.assertTrue(current["stale"])
		self.assertIn("older than 3 days", self.rates.rate_warning(current))

	def test_tcmb_rate_wins_over_ecb_on_the_same_day(self):
		self.store("ECB", TUESDAY, "41.2500")
		self.store("TCMB", TUESDAY, "41.3088")
		self.assertEqual(self.rates.current_rate()["source"], "TCMB")
		self.store("ECB", date(2026, 11, 25), "41.5000")
		self.assertEqual(self.rates.current_rate()["source"], "TCMB")


class SafetyTest(RateCase):
	def test_only_two_fixed_addresses_are_called(self):
		self.assertEqual(self.rates.SOURCE_URLS, {"TCMB": TCMB, "ECB": ECB})
		with self.assertRaises(ValueError):
			self.rates.download("https://example.test/today.xml")
		self.assertEqual(self.requests.calls, [])

	def test_request_has_a_timeout_no_redirects_and_streams(self):
		self.serve(tcmb=sample("tcmb-today.xml"))
		self.rates.update_rate()
		_url, kwargs = self.requests.calls[0]
		self.assertEqual(kwargs["timeout"], self.rates.TIMEOUT)
		self.assertTrue(all(0 < part <= 10 for part in self.rates.TIMEOUT))
		self.assertIs(kwargs["allow_redirects"], False)
		self.assertIs(kwargs["stream"], True)

	def test_redirect_is_a_failure(self):
		self.serve(tcmb=FakeResponse(b"", status_code=302), ecb=sample("ecb-daily.xml"))
		self.assertEqual(self.rates.update_rate()["source"], "ECB")

	def test_large_answer_is_a_failure(self):
		big = sample("tcmb-today.xml") + b" " * self.rates.MAX_BYTES
		self.serve(tcmb=big, ecb=sample("ecb-daily.xml"))
		self.assertEqual(self.rates.update_rate()["source"], "ECB")

	def test_entity_declaration_is_rejected(self):
		self.serve(tcmb=sample("tcmb-entity.xml"), ecb=sample("ecb-daily.xml"))
		self.assertEqual(self.rates.update_rate()["source"], "ECB")
		with self.assertRaises(ValueError):
			self.rates.parse_tcmb(sample("tcmb-entity.xml"))

	def test_lowercase_doctype_is_rejected(self):
		body = sample("tcmb-today.xml").replace(b"<Tarih_Date ", b"<!doctype x><Tarih_Date ", 1)
		with self.assertRaises(ValueError):
			self.rates.parse_tcmb(body)

	def test_non_positive_rate_is_rejected(self):
		body = sample("tcmb-today.xml").replace(b"<ForexSelling>41.3088<", b"<ForexSelling>0<", 1)
		with self.assertRaises(ValueError):
			self.rates.parse_tcmb(body)


class RoundingTest(RateCase):
	def test_commercial_rounding_rounds_half_away_from_zero(self):
		self.assertEqual(self.rates.commercial_round(Decimal("12.345")), Decimal("12.35"))
		self.assertEqual(self.rates.commercial_round(Decimal("12.335")), Decimal("12.34"))
		self.assertEqual(self.rates.commercial_round(Decimal("-12.345")), Decimal("-12.35"))

	def test_lira_price_uses_the_rate(self):
		self.assertEqual(self.rates.to_try(400, Decimal("41.3088")), Decimal("16523.52"))
		self.assertEqual(self.rates.to_try("0.5", Decimal("41.3089")), Decimal("20.65"))


class PanelPriceTest(RateCase):
	def setUp(self):
		super().setUp()
		(self.plans,) = load(self, self.fake, "press_tr.plans", extra_modules={"requests": self.requests})

	def test_panel_shows_lira_prices_with_the_rate(self):
		self.store("TCMB", TUESDAY, "41.3088")
		plans = {plan["name"]: plan for plan in self.plans.public_plans()}
		self.assertEqual(plans["press-tr-starter"]["price_try"], Decimal("16523.52"))
		self.assertEqual(plans["press-tr-growth"]["price_try"], Decimal("30981.60"))
		self.assertIsNone(plans["press-tr-enterprise"]["price_try"])
		self.assertEqual(plans["press-tr-trial"]["price_try"], Decimal("0.00"))
		starter = plans["press-tr-starter"]
		self.assertEqual(
			starter["try_rate"], {"rate": Decimal("41.3088"), "rate_date": TUESDAY, "source": "TCMB"}
		)
		self.assertIsNone(starter["rate_warning"])
		self.assertEqual(starter["currency"], "USD")

	def test_panel_warns_after_three_days(self):
		self.store("TCMB", date(2026, 11, 20), "41.3088")
		starter = self.plans.public_plans()[0]
		self.assertIn("older than 3 days", starter["rate_warning"])
		self.assertEqual(starter["price_try"], Decimal("16523.52"))

	def test_panel_has_no_lira_price_before_the_first_rate(self):
		starter = self.plans.public_plans()[0]
		self.assertIsNone(starter["price_try"])
		self.assertIsNone(starter["try_rate"])
		self.assertIn("No Turkish lira rate", starter["rate_warning"])


class InvoiceRateTest(RateCase):
	def invoice(self, before=None, **values):
		doc = self.fake.get_doc({"doctype": "Invoice", "status": "Draft", "total": 100, **values})
		doc.get_doc_before_save = lambda: before
		return doc

	def test_draft_invoice_has_no_rate(self):
		self.store("TCMB", TUESDAY, "41.3088")
		doc = self.invoice()
		self.rates.set_invoice_rate(doc)
		self.assertIsNone(doc.get("try_exchange_rate"))

	def test_invoice_takes_the_rate_of_its_day_when_it_is_issued(self):
		self.store("TCMB", MONDAY, "41.1000")
		self.store("TCMB", TUESDAY, "41.3088")
		doc = self.invoice(
			before=SimpleNamespace(get=lambda field: "Draft" if field == "status" else None),
			status="Unpaid",
			total="123.45",
		)
		self.rates.set_invoice_rate(doc)
		self.assertEqual(doc.try_exchange_rate, "41.3088")
		self.assertEqual(doc.try_exchange_rate_date, TUESDAY)
		self.assertEqual(doc.try_exchange_rate_source, "TCMB")
		self.assertEqual(doc.try_total, "5099.57")

	def test_rate_never_changes_after_the_invoice_is_issued(self):
		self.store("TCMB", TUESDAY, "41.3088")
		issued = {
			"status": "Unpaid",
			"try_exchange_rate": "41.3088",
			"try_exchange_rate_date": TUESDAY,
			"try_exchange_rate_source": "TCMB",
		}
		before = SimpleNamespace(get=issued.get)
		self.store("TCMB", date(2026, 11, 25), "42.0000")
		self.fake.today = date(2026, 11, 25)
		doc = self.invoice(before=before, **{**issued, "status": "Paid"})
		self.rates.set_invoice_rate(doc)
		self.assertEqual(doc.try_exchange_rate, "41.3088")
		self.assertEqual(doc.try_total, "4130.88")
		doc = self.invoice(before=before, **{**issued, "try_exchange_rate": "42.0000"})
		with self.assertRaises(Rejected):
			self.rates.set_invoice_rate(doc)

	def test_invoice_without_any_rate_is_not_blocked(self):
		doc = self.invoice(
			before=SimpleNamespace(get=lambda field: "Draft" if field == "status" else None), status="Unpaid"
		)
		self.rates.set_invoice_rate(doc)
		self.assertIsNone(doc.get("try_exchange_rate"))
		self.assertEqual(len(self.errors), 1)


class RateRecordTest(unittest.TestCase):
	def test_rate_doctype_keeps_date_source_and_value(self):
		path = APP_ROOT / "press_tr/press_billing/doctype/ptr_exchange_rate/ptr_exchange_rate.json"
		doc = json.loads(path.read_text(encoding="utf-8"))
		self.assertEqual(doc["name"], DOCTYPE)
		self.assertEqual(doc["module"], "Press Billing")
		fields = {field["fieldname"]: field for field in doc["fields"]}
		self.assertEqual(set(fields), {"rate_date", "source", "rate"})
		self.assertEqual(fields["source"]["options"], "TCMB\nECB")
		self.assertTrue(all(field.get("reqd") and field.get("read_only") for field in fields.values()))
		self.assertEqual(
			doc["permissions"], [{"role": "System Manager", "read": 1, "report": 1, "export": 1}]
		)
		self.assertIn("Press Billing", (APP_ROOT / "press_tr/modules.txt").read_text().splitlines())

	def test_hooks_schedule_one_daily_fetch(self):
		(hooks,) = load(self, FakeFrappe(self), "press_tr.hooks")
		self.assertEqual(hooks.scheduler_events, {"daily": ["press_tr.exchange_rates.update_rate"]})

	def test_hooks_lock_the_invoice_rate(self):
		(hooks,) = load(self, FakeFrappe(self), "press_tr.hooks")
		self.assertEqual(
			hooks.doc_events["Invoice"], {"validate": "press_tr.exchange_rates.set_invoice_rate"}
		)
		self.assertIn(DOCTYPE, hooks.ai_write_closed_doctypes)


if __name__ == "__main__":
	unittest.main()
