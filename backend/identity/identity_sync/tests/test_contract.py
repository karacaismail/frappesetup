"""Check that the contract and server agree (SZ-3).

The tests validate real requests and responses against the schemas in the OpenAPI file.
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

from identity_sync.auth import reject_all

from . import fakes
from .contract_tools import load_yaml, schema_errors
from .fakes import ORG_ID, REALM_ID, SUBJECT, keycloak_user
from .test_server import EVENT, EXECUTE_TOKEN, OPERATOR_TOKEN, PREVIEW_TOKEN, ServerCase, fake_verifier

ROOT = pathlib.Path(__file__).resolve().parents[3]
CONTRACT = load_yaml((ROOT / "contracts" / "identity_sync.openapi.yaml").read_text(encoding="utf-8"))
SERVER_SOURCE = (ROOT / "identity" / "identity_sync" / "identity_sync" / "server.py").read_text(encoding="utf-8")
METHODS = ("get", "post", "put", "delete", "patch")


def operations() -> dict[tuple[str, str], dict]:
    found = {}
    for path, item in CONTRACT["paths"].items():
        for method in METHODS:
            if method in item:
                found[(method.upper(), path)] = item[method]
    return found


def response_schema(method: str, path: str, status: int) -> dict:
    response = operations()[(method, path)]["responses"][str(status)]
    if "$ref" in response:
        response = CONTRACT["components"]["responses"][response["$ref"].rsplit("/", 1)[-1]]
    return response["content"]["application/json"]["schema"]


def request_schema(method: str, path: str) -> dict:
    return operations()[(method, path)]["requestBody"]["content"]["application/json"]["schema"]


class DocumentationTest(unittest.TestCase):
    def test_contract_lists_operations(self) -> None:
        self.assertEqual(len(operations()), 12)

    def test_every_operation_is_documented(self) -> None:
        # Every endpoint has a summary, description and destructive-action flag (`docs/sozlesmeler.md`, section 10).
        for key, operation in operations().items():
            with self.subTest(operation=key):
                self.assertTrue(operation.get("summary"))
                self.assertGreater(len(operation.get("description", "")), 40)
                self.assertIn(operation.get("x-durum"), ("uygulandi", "planlandi"))
                self.assertIsInstance(operation.get("x-yikici"), bool)
                self.assertIn(
                    operation.get("x-yurutme"), ("yalniz-okur", "otomatik", "yalniz-onay-katmani", "press-only")
                )

    def test_write_operations_are_reserved_for_the_approval_layer(self) -> None:
        # Every human-initiated write endpoint requires approval fields and is marked accordingly.
        for key, operation in operations().items():
            if operation.get("x-durum") != "uygulandi" or operation["x-yurutme"] != "yalniz-onay-katmani":
                continue
            with self.subTest(operation=key):
                schemas = CONTRACT["components"]["schemas"]
                request = schemas[request_schema(*key)["$ref"].rsplit("/", 1)[-1]]
                if key == ("POST", "/v1/operations/{operation_id}/resolve"):
                    # This one writes only the service's own journal, never a target.
                    # It has no preview. The approval layer is still the only caller.
                    self.assertIs(operation["x-yikici"], False)
                    self.assertIn("403", operation["responses"])
                    continue
                preview, execute = (schemas[option["$ref"].rsplit("/", 1)[-1]] for option in request["oneOf"])
                # The caller explicitly selects the mode. Execution requires approval fields.
                self.assertIs(preview["properties"]["dry_run"]["const"], True)
                self.assertIs(execute["properties"]["dry_run"]["const"], False)
                for name in ("dry_run", "preview_digest", "approval_id"):
                    self.assertIn(name, execute["required"])
                self.assertIn("403", operation["responses"])
                self.assertIn("409", operation["responses"])

    def test_token_operations_document_401_and_403(self) -> None:
        for key, operation in operations().items():
            if operation.get("security") == [{"serviceToken": []}] and operation["x-durum"] == "uygulandi":
                with self.subTest(operation=key):
                    self.assertIn("401", operation["responses"])
                    self.assertIn("403", operation["responses"])

    def test_error_enum_covers_every_code_the_server_sends(self) -> None:
        sent = set(re.findall(r'\{"error": "([a-z_]+)"\}', SERVER_SOURCE))
        documented = set(CONTRACT["components"]["schemas"]["Error"]["properties"]["error"]["enum"])
        self.assertGreaterEqual(len(sent), 8)
        self.assertEqual(sent - documented, set())
        self.assertEqual(documented - sent, set())

    def test_examples_match_the_request_schema(self) -> None:
        media = operations()[("POST", "/v1/events")]["requestBody"]["content"]["application/json"]
        self.assertGreaterEqual(len(media["examples"]), 4)
        for name, example in media["examples"].items():
            with self.subTest(example=name):
                self.assertEqual(schema_errors(example["value"], media["schema"], CONTRACT), [])



class TargetReplyTest(unittest.TestCase):
    """The fake targets follow the real target contracts. Their replies match the Target schemas.

    Sources: contracts/press_tr.openapi.yaml (0.1.0) and contracts/platform_core-kimlik.openapi.yaml (0.2.0).
    """

    ISSUER = "http://identity.localhost:6110/realms/platform"

    def setUp(self) -> None:
        self.press, self.tenant = fakes.FakePress(), fakes.FakeTenant()
        self.addCleanup(self.press.close)
        self.addCleanup(self.tenant.close)

    def post(self, site: fakes.FakeServer, path: str, body: dict) -> tuple[int, object]:
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            site.url + path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def assert_matches(self, reply: tuple[int, object], schema_name: str) -> None:
        self.assertEqual(reply[0], 200)
        schema = CONTRACT["components"]["schemas"][schema_name]
        self.assertEqual(schema_errors(reply[1], schema, CONTRACT), [])

    def identity(self, **extra: object) -> dict:
        return {"issuer": self.ISSUER, "subject": SUBJECT, **extra}

    def test_press_replies(self) -> None:
        team = self.identity(email="ayse@example.test", email_verified=True, organization_id=ORG_ID)
        self.assert_matches(self.post(self.press, fakes.PRESS_ENSURE_TEAM, team), "TargetEnsureTeamResult")
        one = self.identity(organization_id=ORG_ID)
        self.assert_matches(self.post(self.press, fakes.PRESS_REMOVE_MEMBER, one), "TargetRemoveTeamMemberResult")
        every = self.identity(all_organizations=True)
        self.assert_matches(self.post(self.press, fakes.PRESS_REMOVE_MEMBER, every), "TargetRemoveTeamMemberResult")

    def test_press_rejects_requests_outside_its_contract(self) -> None:
        bad_requests = (
            (fakes.PRESS_ENSURE_TEAM, self.identity(email="ayse@example.test", organization_id=ORG_ID)),
            (fakes.PRESS_REMOVE_MEMBER, self.identity()),
            (fakes.PRESS_REMOVE_MEMBER, self.identity(organization_id=ORG_ID, all_organizations=True)),
            (fakes.PRESS_REMOVE_MEMBER, self.identity(organization_id="")),
            (fakes.PRESS_REMOVE_MEMBER, self.identity(organization_id=None)),
            (fakes.PRESS_REMOVE_MEMBER, self.identity(all_organizations=False)),
        )
        for path, body in bad_requests:
            with self.subTest(body=body):
                self.assertEqual(self.post(self.press, path, body)[0], 400)

    def test_tenant_replies(self) -> None:
        user = self.identity(email="ayse@example.test", email_verified=True, enabled=True)
        self.assert_matches(self.post(self.tenant, fakes.TENANT_PROVISION, user), "TargetProvisionResult")
        disable = self.identity(enabled=False)
        self.assert_matches(self.post(self.tenant, fakes.TENANT_SET_ENABLED, disable), "TargetSetEnabledResult")
        rename = self.identity(new_email="yeni@example.test")
        self.assert_matches(self.post(self.tenant, fakes.TENANT_CHANGE_EMAIL, rename), "TargetChangeEmailResult")

    def test_tenant_error_names(self) -> None:
        unknown = self.identity(enabled=False)
        self.assertEqual(self.post(self.tenant, fakes.TENANT_SET_ENABLED, unknown), fakes.frappe_error(404, "IdentityNotFound"))
        self.post(self.tenant, fakes.TENANT_PROVISION, self.identity(email="ayse@example.test", email_verified=True, enabled=True))
        other_email = self.identity(email="yeni@example.test", email_verified=True, enabled=True)
        self.assertEqual(self.post(self.tenant, fakes.TENANT_PROVISION, other_email), fakes.frappe_error(409, "EmailMismatch"))
        extra_field = self.identity(enabled=False, tenant="tenant1")
        self.assertEqual(self.post(self.tenant, fakes.TENANT_SET_ENABLED, extra_field)[0], 400)

    def test_unclear_replies_do_not_match_any_target_schema(self) -> None:
        unclear = ({"message": {"status": "queued"}}, {"message": None}, {"exc": "x"}, {}, None)
        for name, schema in CONTRACT["components"]["schemas"].items():
            if not name.startswith("Target"):
                continue
            for body in unclear:
                with self.subTest(schema=name, body=body):
                    self.assertNotEqual(schema_errors(body, schema, CONTRACT), [])


class TranslationTest(unittest.TestCase):
    """The contract's source text is English. The Turkish text lives in translations/tr.csv.

    The file follows the Frappe layout: source, translation, context. The context names the
    place of the text in the contract.
    """

    TRANSLATIONS = ROOT / "identity" / "identity_sync" / "translations" / "tr.csv"

    def contract_texts(self) -> dict[str, str]:
        texts: dict[str, str] = {}

        def walk(node: object, path: str) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    here = f"{path}.{key}" if path else str(key)
                    if key in ("summary", "description") and isinstance(value, str):
                        texts[here] = value
                    else:
                        walk(value, here)
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]")

        walk(CONTRACT, "")
        return texts

    def rows(self) -> list[list[str]]:
        import csv

        with self.TRANSLATIONS.open(encoding="utf-8", newline="") as handle:
            return list(csv.reader(handle))

    def test_contract_source_text_has_no_turkish_letters(self) -> None:
        turkish = re.compile("[\u00e7\u00c7\u011f\u011e\u0131\u0130\u00f6\u00d6\u015f\u015e\u00fc\u00dc]")
        offenders = [path for path, text in self.contract_texts().items() if turkish.search(text)]
        self.assertEqual(offenders, [])

    def test_every_contract_text_has_a_turkish_translation_with_context(self) -> None:
        texts = self.contract_texts()
        rows = self.rows()
        self.assertTrue(all(len(row) == 3 for row in rows))
        by_context = {row[2]: row for row in rows}
        self.assertEqual(len(by_context), len(rows))
        self.assertEqual(set(by_context), {f"identity_sync.openapi.yaml: {path}" for path in texts})
        for path, text in texts.items():
            source, translation, _context = by_context[f"identity_sync.openapi.yaml: {path}"]
            with self.subTest(path=path):
                # The source column is exactly the contract text, so the two cannot drift apart.
                self.assertEqual(source, text)
                self.assertTrue(translation.strip())


class ImplementationTest(ServerCase):
    def test_implemented_operations_need_credentials_and_planned_ones_do_not_exist(self) -> None:
        self.start_server(reject_all)
        for (method, path), operation in operations().items():
            with self.subTest(operation=(method, path)):
                body = b"{}" if method == "POST" else None
                concrete = path.replace("{tenant}", "tenant1").replace("{operation_id}", "onay-1")
                status, _reply = self.call(method, concrete, body)
                if path == "/healthz":
                    self.assertEqual(status, 200)
                elif operation["x-durum"] == "uygulandi":
                    # An unauthenticated request gets 401 at every protected endpoint.
                    self.assertEqual(status, 401)
                else:
                    self.assertEqual(status, 404)


class SchemaTest(ServerCase):
    """Real requests and responses conform to the schemas."""

    def assert_response(self, reply: tuple[int, object], method: str, path: str, expected_status: int) -> object:
        status, body = reply
        self.assertEqual(status, expected_status)
        self.assertEqual(schema_errors(body, response_schema(method, path, status), CONTRACT), [])
        return body

    def assert_request(self, payload: object, method: str, path: str) -> None:
        self.assertEqual(schema_errors(payload, request_schema(method, path), CONTRACT), [])

    def test_health(self) -> None:
        self.assert_response(self.call("GET", "/healthz"), "GET", "/healthz", 200)

    def test_event_envelope_and_results(self) -> None:
        self.assert_request(EVENT, "POST", "/v1/events")
        self.assert_response(self.post_event(dry_run=True), "POST", "/v1/events", 200)
        self.assert_response(self.post_event(), "POST", "/v1/events", 202)
        self.assert_response(self.post_event(), "POST", "/v1/events", 202)  # duplicate
        self.assert_response(self.post_event({"id": "x"}), "POST", "/v1/events", 400)
        self.assert_response(self.call("POST", "/v1/events", b"{}"), "POST", "/v1/events", 401)

    def test_keycloak_formats_are_accepted_requests(self) -> None:
        user_event = {"id": "k-1", "time": 1, "type": "VERIFY_EMAIL", "realmId": REALM_ID, "userId": SUBJECT}
        admin_event = {
            "id": "k-2",
            "time": 2,
            "realmId": REALM_ID,
            "operationType": "UPDATE",
            "resourceType": "USER",
            "resourcePath": f"users/{SUBJECT}",
        }
        membership = {**admin_event, "id": "k-3", "operationType": "CREATE", "resourceType": "ORGANIZATION_MEMBERSHIP"}
        membership["resourcePath"] = f"organizations/{ORG_ID}/members"
        for payload in (user_event, admin_event, membership):
            with self.subTest(payload=payload["id"]):
                self.assert_request(payload, "POST", "/v1/events")
                self.assert_response(self.post_event(payload), "POST", "/v1/events", 202)

    def test_rejected_bodies_do_not_match_the_request_schema(self) -> None:
        for payload in ({"id": "e-1", "kind": "user"}, {**EVENT, "kind": "system"}, {**EVENT, "user_id": ".."}):
            with self.subTest(payload=payload):
                self.assertNotEqual(schema_errors(payload, request_schema("POST", "/v1/events"), CONTRACT), [])
                self.assertEqual(self.post_event(payload)[0], 400)

    def test_unknown_and_dead_lettered_results(self) -> None:
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (202, {"message": {"status": "queued"}}))
        body = self.assert_response(self.post_event(), "POST", "/v1/events", 202)
        self.assertEqual(body["status"], "unknown")
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        body = self.assert_response(self.post_event({**EVENT, "id": "e-2"}), "POST", "/v1/events", 202)
        self.assertEqual(body["status"], "dead_lettered")

        listing = self.assert_response(
            self.call("GET", "/v1/dead-letters", None, self.bearer(OPERATOR_TOKEN)), "GET", "/v1/dead-letters", 200
        )
        self.assertEqual(sorted(letter["state"] for letter in listing["dead_letters"]), ["failed", "unknown"])

    def test_replay(self) -> None:
        path = "/v1/dead-letters/replay"
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, (503, None))
        self.post_event()
        self.stack.tenant.on("POST", fakes.TENANT_PROVISION, fakes.DONE)

        preview_request = {"dry_run": True}
        self.assert_request(preview_request, "POST", path)
        preview = self.assert_response(self.post_json(path, preview_request, OPERATOR_TOKEN), "POST", path, 200)
        execute_request = {"dry_run": False, "preview_digest": preview["preview_digest"], "approval_id": "onay-1"}
        self.assert_request(execute_request, "POST", path)
        self.assert_response(self.post_json(path, execute_request, PREVIEW_TOKEN), "POST", path, 403)
        stale = {**execute_request, "preview_digest": "0" * 64, "approval_id": "onay-0"}
        self.assert_response(self.post_json(path, stale), "POST", path, 409)
        self.assert_response(self.post_json(path, execute_request, OPERATOR_TOKEN), "POST", path, 200)
        # The same approval a second time: 409 approval_used.
        used = self.assert_response(self.post_json(path, execute_request, OPERATOR_TOKEN), "POST", path, 409)
        self.assertEqual(used, {"error": "approval_used"})
        self.assert_response(self.post_json(path, {}), "POST", path, 400)
        # The body rejected by the server also fails schema validation.
        for rejected in ({}, {"dry_run": False}, {"dry_run": False, "approval_id": "onay-1"}, {"dry_run": "true"}):
            with self.subTest(rejected=rejected):
                self.assertNotEqual(schema_errors(rejected, request_schema("POST", path), CONTRACT), [])
                self.assertEqual(self.post_json(path, rejected)[0], 400)
        self.assert_response(self.call("POST", path, b"{}"), "POST", path, 401)

    def test_invitation(self) -> None:
        path = "/v1/invitations"
        kc = self.stack.keycloak
        kc.on("GET", f"{kc.admin}/users", (200, []))
        request = {"email": "davetli@example.test", "organization_id": ORG_ID, "dry_run": True}

        self.assert_request(request, "POST", path)
        preview = self.assert_response(self.post_json(path, request, PREVIEW_TOKEN), "POST", path, 200)
        self.assert_response(self.post_json(path, {"email": "x"}), "POST", path, 400)
        execute = {**request, "dry_run": False, "preview_digest": preview["preview_digest"], "approval_id": "onay-1"}
        self.assert_request(execute, "POST", path)
        self.assert_response(self.post_json(path, execute, PREVIEW_TOKEN), "POST", path, 403)
        self.assert_response(self.post_json(path, {**execute, "preview_digest": "0" * 64}), "POST", path, 409)
        without_approval = {**request, "dry_run": False}
        self.assertNotEqual(schema_errors(without_approval, request_schema("POST", path), CONTRACT), [])
        self.assertEqual(self.post_json(path, without_approval)[0], 400)
        kc.on("GET", f"{kc.admin}/users", (500, None))
        self.assert_response(self.post_json(path, request), "POST", path, 502)

    def test_reconcile(self) -> None:
        path = "/v1/reconcile"
        kc, issuer = self.stack.keycloak, self.stack.issuer
        kc.add_user(keycloak_user(subject="closed-1", email="closed@example.test", enabled=False), [])
        kc.serve_directory()
        self.stack.tenant.seed_user(issuer, "closed-1", "closed@example.test")
        # The member from the base setup is in sync.
        self.stack.press.seed_member(issuer, SUBJECT, "ayse@example.test", ORG_ID)
        self.stack.tenant.seed_user(issuer, SUBJECT, "ayse@example.test")

        preview_request = {"dry_run": True}
        self.assert_request(preview_request, "POST", path)
        preview = self.assert_response(self.post_json(path, preview_request, OPERATOR_TOKEN), "POST", path, 200)
        self.assertEqual([d["kind"] for d in preview["differences"]], ["closed_in_keycloak"])
        execute = {"dry_run": False, "preview_digest": preview["preview_digest"], "approval_id": "onay-m1"}
        self.assert_request(execute, "POST", path)
        self.assert_response(self.post_json(path, execute, PREVIEW_TOKEN), "POST", path, 403)
        stale = {**execute, "preview_digest": "0" * 64, "approval_id": "onay-m0"}
        self.assert_response(self.post_json(path, stale), "POST", path, 409)
        done = self.assert_response(self.post_json(path, execute), "POST", path, 200)
        self.assertEqual([r["status"] for r in done["results"]], ["done", "done"])
        self.assert_response(self.post_json(path, execute), "POST", path, 409)
        for rejected in ({}, {"dry_run": False}, {"dry_run": "true"}):
            with self.subTest(rejected=rejected):
                self.assertNotEqual(schema_errors(rejected, request_schema("POST", path), CONTRACT), [])
                self.assert_response(self.post_json(path, rejected), "POST", path, 400)
        self.assert_response(self.call("POST", path, b"{}"), "POST", path, 401)

    def test_reconcile_finishes_an_account_deleted_in_keycloak(self) -> None:
        # The delete event was lost. The local account is already disabled.
        path = "/v1/reconcile"
        issuer = self.stack.issuer
        self.stack.keycloak.serve_directory()
        self.stack.press.seed_member(issuer, SUBJECT, "ayse@example.test", ORG_ID)
        self.stack.tenant.seed_user(issuer, SUBJECT, "ayse@example.test")
        self.stack.tenant.seed_user(issuer, "gone-1", "gone@example.test", enabled=False)

        preview = self.assert_response(self.post_json(path, {"dry_run": True}, OPERATOR_TOKEN), "POST", path, 200)
        self.assertEqual([(d["target"], d["kind"]) for d in preview["differences"]], [("tenant1", "deleted_in_keycloak")])
        self.assertEqual(preview["previews"][-1]["operation"], "tenant.anonymize_user")
        execute = {"dry_run": False, "preview_digest": preview["preview_digest"], "approval_id": "onay-g1"}
        done = self.assert_response(self.post_json(path, execute), "POST", path, 200)
        (job,) = done["results"]
        self.assertEqual((job["operation"], job["status"]), ("account_deletion", "done"))
        self.assertRegex(job["target"], r"^del-[0-9a-f]{40}$")
        self.assertTrue(self.stack.tenant.user_of(issuer, "gone-1")["anonymized"])

    def test_paged_lists(self) -> None:
        from identity_sync.events import Event

        store = self.stack.app.store
        for number in range(3):
            failed = Event(id=f"e-{number}", kind="user", type="VERIFY_EMAIL", realm="platform", time=1, user_id=SUBJECT)
            store.add_dead_letter(failed, "tenant.provision tenant1: HTTP 503")
            store.operation_begin(f"o-{number}", "invite_user", ORG_ID, ["s1"])
        bearer = self.bearer(OPERATOR_TOKEN)
        for path, key in (("/v1/dead-letters", "dead_letters"), ("/v1/operations", "operations")):
            with self.subTest(path=path):
                first = self.assert_response(self.call("GET", path + "?limit=2", None, bearer), "GET", path, 200)
                self.assertEqual((len(first[key]), first["next_offset"]), (2, 2))
                last = self.assert_response(self.call("GET", path + "?limit=2&offset=2", None, bearer), "GET", path, 200)
                self.assertEqual((len(last[key]), "next_offset" in last), (1, False))
                names = [p["$ref"].rsplit("/", 1)[1] for p in CONTRACT["paths"][path]["get"]["parameters"]]
                self.assertEqual(names, ["Limit", "Offset"])
        limit = CONTRACT["components"]["parameters"]["Limit"]["schema"]
        self.assertEqual((limit["minimum"], limit["maximum"], limit["default"]), (1, 500, 100))
        self.assertNotEqual(schema_errors({"dead_letters": [], "next_offset": 0}, CONTRACT["components"]["schemas"]["DeadLetterList"], CONTRACT), [])

    def test_identity_list_pages_match_the_target_schema(self) -> None:
        schema = CONTRACT["components"]["schemas"]["TargetIdentityList"]
        issuer = self.stack.issuer
        for number in range(3):
            self.stack.press.seed_member(issuer, f"u-{number}", f"u{number}@example.test", ORG_ID)
            self.stack.tenant.seed_user(issuer, f"u-{number}", f"u{number}@example.test")
        for site, path in ((self.stack.press, fakes.PRESS_LIST), (self.stack.tenant, fakes.TENANT_LIST)):
            with self.subTest(path=path):
                import urllib.request

                request = urllib.request.Request(site.url + path + "?start=0&page_length=2")
                with urllib.request.urlopen(request, timeout=10) as response:
                    body = json.loads(response.read())
                self.assertEqual(schema_errors(body, schema, CONTRACT), [])
                self.assertEqual((len(body["message"]["identities"]), body["message"]["has_next_page"]), (2, True))
                self.assertEqual(set(body["message"]["identities"][0]), {"issuer", "subject", "enabled"})
        self.assertNotEqual(schema_errors({"message": []}, schema, CONTRACT), [])

    def test_every_difference_kind_is_in_the_contract(self) -> None:
        import inspect

        from identity_sync import reconcile

        documented = set(CONTRACT["components"]["schemas"]["Difference"]["properties"]["kind"]["enum"])
        used = set(re.findall(r'"([a-z_]+)"', inspect.getsource(reconcile))) & {
            "missing",
            "disabled",
            "email_mismatch",
            "closed_in_keycloak",
            "deleted_in_keycloak",
            "unexpected",
            "unverified_in_keycloak",
            "missing_team_membership",
            "unexpected_team_membership",
            "foreign_issuer",
        }
        self.assertEqual(len(used), 10)
        self.assertEqual(documented, used)

    def test_session_revoke(self) -> None:
        from .test_server import SESSION_TOKEN

        path, sid = "/v1/sessions/revoke", "55555555-5555-4555-8555-555555555555"
        kc = self.stack.keycloak
        kc.add_session(SUBJECT, sid)
        request = {"sid": sid, "subject": SUBJECT}

        self.assert_request(request, "POST", path)
        self.assert_response(self.post_json(path, request, SESSION_TOKEN), "POST", path, 200)
        self.assert_response(self.post_json(path, request, PREVIEW_TOKEN), "POST", path, 403)
        stranger = {"sid": sid, "subject": "yok-boyle-kullanici"}
        self.assert_request(stranger, "POST", path)
        self.assert_response(self.post_json(path, stranger, SESSION_TOKEN), "POST", path, 403)
        for rejected in ({}, {"sid": sid}, {"sid": "..", "subject": SUBJECT}, {**request, "user": "x"}):
            with self.subTest(rejected=rejected):
                self.assertNotEqual(schema_errors(rejected, request_schema("POST", path), CONTRACT), [])
                self.assert_response(self.post_json(path, rejected, SESSION_TOKEN), "POST", path, 400)
        self.assert_response(self.call("POST", path, b"{}"), "POST", path, 401)
        kc.add_session(SUBJECT, sid)
        kc.on("DELETE", f"{kc.admin}/sessions/{sid}", (500, None))
        self.assert_response(self.post_json(path, request, SESSION_TOKEN), "POST", path, 502)

    def test_login_providers(self) -> None:
        from .test_server import OTHER_SITE_TOKEN, SESSION_TOKEN

        path = "/v1/login-providers"
        kc = self.stack.keycloak
        kc.add_identity_provider("google", display_name="Google")
        kc.add_identity_provider("tenant1-sso", display_name="Tenant One SSO", organization_id=ORG_ID)
        body = self.assert_response(self.call("GET", path, None, self.bearer(SESSION_TOKEN)), "GET", path, 200)
        self.assertEqual([row["alias"] for row in body["providers"]], ["google", "tenant1-sso"])
        self.assert_response(self.call("GET", path, None, self.bearer(PREVIEW_TOKEN)), "GET", path, 403)
        self.assert_response(self.call("GET", path, None, self.bearer(OTHER_SITE_TOKEN)), "GET", path, 403)
        self.assert_response(self.call("GET", path), "GET", path, 401)
        kc.on("GET", f"{kc.admin}/identity-provider/instances", (500, None))
        # The platform list is kept for a short time. A new server starts with an empty store.
        self.start_server(fake_verifier)
        self.assert_response(self.call("GET", path, None, self.bearer(SESSION_TOKEN)), "GET", path, 502)

    def test_linked_accounts(self) -> None:
        from .test_server import SESSION_TOKEN

        path = "/v1/linked-accounts"
        kc = self.stack.keycloak
        kc.add_identity_provider("google", display_name="Google")
        kc.link_account(SUBJECT, "google", "ayse.ornek@elsewhere.example.test")
        kc.add_credential(SUBJECT, "password")
        request = {"subject": SUBJECT}

        self.assert_request(request, "POST", path)
        body = self.assert_response(self.post_json(path, request, SESSION_TOKEN), "POST", path, 200)
        self.assertEqual(body, {"providers": [{"alias": "google", "display_name": "Google", "linked": True}], "local_sign_in_methods": 1})
        self.assert_response(self.post_json(path, request, PREVIEW_TOKEN), "POST", path, 403)
        stranger = {"subject": "00000000-0000-4000-8000-000000000000"}
        self.assert_request(stranger, "POST", path)
        self.assert_response(self.post_json(path, stranger, SESSION_TOKEN), "POST", path, 403)
        for rejected in ({}, {"subject": "a/b"}, {**request, "user": "x"}):
            with self.subTest(rejected=rejected):
                self.assertNotEqual(schema_errors(rejected, request_schema("POST", path), CONTRACT), [])
                self.assert_response(self.post_json(path, rejected, SESSION_TOKEN), "POST", path, 400)
        self.assert_response(self.call("POST", path, b"{}"), "POST", path, 401)
        kc.on("GET", f"{kc.admin}/users/{SUBJECT}/credentials", (500, None))
        self.assert_response(self.post_json(path, request, SESSION_TOKEN), "POST", path, 502)

    def test_account_deletion(self) -> None:
        from .test_server import NOW, PRESS_TOKEN

        path = "/v1/account-deletions"
        issuer = self.stack.issuer
        self.stack.tenant.seed_user(issuer, SUBJECT, "ayse@example.test")
        self.stack.tenant.on("POST", fakes.TENANT_ANONYMIZE, (503, None))
        request = {"issuer": issuer, "subject": SUBJECT, "reauthenticated_at": NOW - 10}

        self.assert_request(request, "POST", path)
        self.assert_response(self.post_json(path, request, PREVIEW_TOKEN), "POST", path, 403)
        stale = {**request, "reauthenticated_at": NOW - 301}
        self.assert_request(stale, "POST", path)
        refused = self.assert_response(self.post_json(path, stale, PRESS_TOKEN), "POST", path, 403)
        self.assertEqual(refused, {"error": "reauthentication_required"})
        queued = self.assert_response(self.post_json(path, request, PRESS_TOKEN), "POST", path, 200)
        self.assertEqual(queued["status"], "dead_lettered")
        for rejected in ({}, {"issuer": issuer, "subject": SUBJECT}, {**request, "subject": ".."}, {**request, "dry_run": True}):
            with self.subTest(rejected=rejected):
                self.assertNotEqual(schema_errors(rejected, request_schema("POST", path), CONTRACT), [])
                self.assert_response(self.post_json(path, rejected, PRESS_TOKEN), "POST", path, 400)
        self.assert_response(self.call("POST", path, b"{}"), "POST", path, 401)
        # The queued request is listed with its own event kind.
        self.assert_response(
            self.call("GET", "/v1/dead-letters", None, self.bearer(OPERATOR_TOKEN)), "GET", "/v1/dead-letters", 200
        )

    def test_proposed_target_replies_match_the_target_schemas(self) -> None:
        tenant, press = fakes.FakeTenant(), fakes.FakePress()
        self.addCleanup(tenant.close)
        self.addCleanup(press.close)
        issuer = self.stack.issuer
        tenant.seed_user(issuer, SUBJECT, "ayse@example.test")
        press.seed_member(issuer, SUBJECT, "ayse@example.test", ORG_ID)
        identity = {"issuer": issuer, "subject": SUBJECT}
        cases = (
            (tenant, fakes.TENANT_REVOKE_INSTALLATIONS, "TargetRevokeUserInstallationsResult"),
            (tenant, fakes.TENANT_ANONYMIZE, "TargetAnonymizeUserResult"),
            (press, fakes.PRESS_ANONYMIZE, "TargetAnonymizeUserResult"),
        )
        for site, target_path, schema_name in cases:
            with self.subTest(path=target_path):
                self.assertIn(target_path.rsplit(".", 1)[-1], ("revoke_user_installations", "anonymize_user"))
                status, body = TargetReplyTest.post(self, site, target_path, identity)
                self.assertEqual(status, 200)
                self.assertEqual(schema_errors(body, CONTRACT["components"]["schemas"][schema_name], CONTRACT), [])
        unknown = {"issuer": issuer, "subject": "yok-boyle-kullanici"}
        schema = CONTRACT["components"]["schemas"]["TargetAnonymizeUserResult"]
        for site, target_path in ((tenant, fakes.TENANT_ANONYMIZE), (press, fakes.PRESS_ANONYMIZE)):
            with self.subTest(path=target_path):
                status, body = TargetReplyTest.post(self, site, target_path, unknown)
                self.assertEqual((status, body), (200, {"message": {"anonymized": True, "found": False}}))
                self.assertEqual(schema_errors(body, schema, CONTRACT), [])
        self.assertNotEqual(schema_errors({"message": {"anonymized": True}}, schema, CONTRACT), [])

    def test_operations(self) -> None:
        kc = self.stack.keycloak
        kc.on("GET", f"{kc.admin}/users", (200, []))
        kc.on("POST", f"{kc.admin}/users", (201, None, {"Location": f"{kc.url}{kc.admin}/users/yeni-kullanici"}))
        kc.on("POST", f"{kc.admin}/organizations/{ORG_ID}/members", (500, None))
        invitation = {"email": "davetli@example.test", "organization_id": ORG_ID}
        _status, preview = self.post_json("/v1/invitations", {**invitation, "dry_run": True})
        execute = {**invitation, "dry_run": False, "preview_digest": preview["preview_digest"], "approval_id": "onay-1"}
        self.assert_response(self.post_json("/v1/invitations", execute), "POST", "/v1/invitations", 502)

        listing = self.assert_response(
            self.call("GET", "/v1/operations", None, self.bearer(OPERATOR_TOKEN)), "GET", "/v1/operations", 200
        )
        self.assertEqual([s["status"] for s in listing["operations"][0]["steps"]], ["done", "failed", "pending"])
        path, template = "/v1/operations/onay-1/resolve", "/v1/operations/{operation_id}/resolve"
        request = {"resolution": "abandoned"}
        self.assertEqual(schema_errors(request, request_schema("POST", template), CONTRACT), [])
        self.assert_response(self.post_json(path, request, PREVIEW_TOKEN), "POST", template, 403)
        self.assert_response(self.post_json(path, {"resolution": "x"}), "POST", template, 400)
        self.assert_response(self.post_json(path, request), "POST", template, 200)
        self.assert_response(self.post_json(path, request), "POST", template, 404)
        self.assert_response(self.call("POST", path, b"{}"), "POST", template, 401)

    def test_common_errors_use_the_error_schema(self) -> None:
        error = CONTRACT["components"]["schemas"]["Error"]
        for reply in (self.call("GET", "/yok"), self.call("GET", "/v1/events"), self.post_event({"dolgu": "x" * 70000})):
            with self.subTest(status=reply[0]):
                self.assertIn(reply[0], (404, 405, 413))
                self.assertEqual(schema_errors(reply[1], error, CONTRACT), [])


class ContractToolsTest(unittest.TestCase):
    """Tests for the small YAML reader itself."""

    def test_reads_the_constructs_the_contract_uses(self) -> None:
        text = (
            'a: 1\nb: "iki"\nc: [x, "y", 3]\nd:\n  - p: true\n    q: null\n  - $ref: "#/r"\n'
            "e: |\n  ilk satır\n\n  üçüncü: satır\nf:\n  g: 1.5\n"
        )
        self.assertEqual(
            load_yaml(text),
            {
                "a": 1,
                "b": "iki",
                "c": ["x", "y", 3],
                "d": [{"p": True, "q": None}, {"$ref": "#/r"}],
                "e": "ilk satır\n\nüçüncü: satır\n",
                "f": {"g": 1.5},
            },
        )

    def test_unsupported_yaml_fails_loudly(self) -> None:
        for text in ("a: &anchor 1\n", "a: {b: 1}\n", "a: 1\na: 2\n", "a: >\n  x\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                load_yaml(text)

    def test_schema_checker_catches_violations(self) -> None:
        root = {"defs": {"id": {"type": "string", "pattern": "^[a-z]+$"}}}
        schema = {
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"$ref": "#/defs/id"}, "n": {"type": "integer"}, "s": {"enum": ["a", "b"]}},
            "additionalProperties": False,
        }
        self.assertEqual(schema_errors({"id": "abc", "n": 1, "s": "a"}, schema, root), [])
        for bad in ({}, {"id": "ABC"}, {"id": "a", "n": True}, {"id": "a", "s": "c"}, {"id": "a", "x": 1}, []):
            with self.subTest(bad=bad):
                self.assertNotEqual(schema_errors(bad, schema, root), [])

    def test_contract_is_valid_json_shaped_data(self) -> None:
        self.assertEqual(json.loads(json.dumps(CONTRACT))["openapi"], "3.1.0")


if __name__ == "__main__":
    unittest.main()
