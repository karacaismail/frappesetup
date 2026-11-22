"""HTTP acceptance tests on a dedicated test-kabuk.localhost site only.

Run the local bench web process first. Fixtures use synthetic accounts.
The tests commit fixtures because real HTTP requests use separate transactions.
"""

import http.client
import json
import os
import secrets
import unittest
from http.cookies import SimpleCookie
from urllib.parse import urlencode

import frappe

SITE = "test-kabuk.localhost"
DOCTYPE = "Kabuk Test Record"
READER = "kabuk-reader@example.test"
PRIVILEGED = "kabuk-privileged@example.test"


class ShellHTTPFixture(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.site = os.environ.get("KABUK_TEST_SITE", SITE)
		if cls.site != SITE:
			raise RuntimeError("Use the isolated test-kabuk.localhost site.")
		frappe.init(site=cls.site, sites_path=os.getcwd())
		frappe.connect()
		if not frappe.conf.allow_tests:
			raise RuntimeError("Tests are disabled on this site.")
		frappe.set_user("Administrator")
		cls.password = secrets.token_urlsafe(30)
		for name in ("Kabuk Test Reader", "Kabuk Test Privileged"):
			if not frappe.db.exists("Role", name):
				frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 0}).insert()
		if not frappe.db.exists("DocType", DOCTYPE):
			frappe.get_doc(
				{
					"doctype": "DocType",
					"name": DOCTYPE,
					"module": "Kabuk",
					"custom": 1,
					"fields": [
						{
							"fieldname": "title",
							"fieldtype": "Data",
							"label": "Title",
							"description": "Public title.",
						},
						{
							"fieldname": "private_note",
							"fieldtype": "Data",
							"label": "Private note",
							"permlevel": 1,
							"description": "Restricted note.",
						},
						{
							"fieldname": "private_section",
							"fieldtype": "Section Break",
							"label": "Private section",
							"permlevel": 1,
							"description": "Restricted layout.",
						},
					],
					"permissions": [
						{"role": "Kabuk Test Reader", "read": 1, "write": 1, "create": 1},
						{"role": "Kabuk Test Privileged", "read": 1, "write": 1},
						{"role": "Kabuk Test Privileged", "permlevel": 1, "read": 1, "write": 1},
					],
				}
			).insert()
		for email, roles in (
			(READER, ["Kabuk Test Reader"]),
			(PRIVILEGED, ["Kabuk Test Reader", "Kabuk Test Privileged"]),
		):
			if not frappe.db.exists("User", email):
				doc = frappe.get_doc(
					{
						"doctype": "User",
						"email": email,
						"first_name": "Sample",
						"last_name": "Reader",
						"user_type": "Website User",
						"send_welcome_email": 0,
						"roles": [{"role": role} for role in roles],
						"new_password": cls.password,
					}
				)
				doc.insert()
			else:
				from frappe.utils.password import update_password

				update_password(email, cls.password)
				doc = frappe.get_doc("User", email)
				doc.set("roles", [{"role": role} for role in roles])
				doc.save()
		for title, hidden, restricted in (
			("Kabuk Visible", 0, False),
			("Kabuk Hidden", 1, False),
			("Kabuk Restricted", 0, True),
		):
			if not frappe.db.exists("Workspace", title):
				frappe.get_doc(
					{
						"doctype": "Workspace",
						"name": title,
						"title": title,
						"label": title,
						"module": "Kabuk",
						"public": 1,
						"is_hidden": hidden,
						"content": "[]",
						"roles": [{"role": "Kabuk Test Privileged"}] if restricted else [],
					}
				).insert()
		for title, owner in (("Kabuk Reader Private", READER), ("Kabuk Other Private", PRIVILEGED)):
			if not frappe.db.exists("Workspace", title):
				frappe.get_doc(
					{
						"doctype": "Workspace",
						"title": title,
						"label": title,
						"module": "Kabuk",
						"public": 0,
						"for_user": owner,
						"content": "[]",
					}
				).insert()
		frappe.db.commit()
		frappe.clear_cache()
		frappe.db.commit()
		cls.reader_sid = cls.login(READER)
		cls.privileged_sid = cls.login(PRIVILEGED)

	@classmethod
	def tearDownClass(cls):
		frappe.destroy()

	@classmethod
	def request(cls, path, sid=None, method="GET", data=None, headers=None):
		connection = http.client.HTTPConnection(
			"127.0.0.1", int(os.environ.get("KABUK_TEST_PORT", "8000")), timeout=30
		)
		request_headers = {"Host": cls.site, "Accept": "application/json"}
		if sid:
			request_headers["Cookie"] = "sid=" + sid
		if data is not None:
			request_headers["Content-Type"] = "application/x-www-form-urlencoded"
			data = urlencode(data)
		request_headers.update(headers or {})
		try:
			connection.request(method, path, body=data, headers=request_headers)
			response = connection.getresponse()
			return response.status, dict(response.getheaders()), response.read()
		finally:
			connection.close()

	@classmethod
	def login(cls, user):
		cookies = SimpleCookie()
		connection = http.client.HTTPConnection(
			"127.0.0.1", int(os.environ.get("KABUK_TEST_PORT", "8000")), timeout=30
		)
		try:
			connection.request(
				"POST",
				"/api/method/login",
				body=urlencode({"usr": user, "pwd": cls.password}),
				headers={"Host": cls.site, "Content-Type": "application/x-www-form-urlencoded"},
			)
			response = connection.getresponse()
			for name, value in response.getheaders():
				if name.lower() == "set-cookie":
					cookies.load(value)
			response.read()
			if response.status != 200 or "sid" not in cookies:
				raise RuntimeError("Synthetic session creation failed.")
			return cookies["sid"].value
		finally:
			connection.close()

	def metadata(self, sid, headers=None):
		return self.request(
			"/api/method/platform_core.api.meta.get_doctype?" + urlencode({"doctype": DOCTYPE}),
			sid,
			headers=headers,
		)
