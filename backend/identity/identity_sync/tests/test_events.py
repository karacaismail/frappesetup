"""Tests for the event envelope and conversion from the Keycloak format.

The envelope is defined in `contracts/identity_sync.openapi.yaml`.
Keycloak field names come from the Keycloak 26.8.2 Admin REST API documentation.
"""

from __future__ import annotations

import unittest

from identity_sync.events import Event, EventError, from_keycloak, is_handled, parse_event

SUB = "11111111-1111-4111-8111-111111111111"
REALM_ID = "7c9e6679-7425-40de-944b-e07fc1f90ae7"


def translate(payload):
    return from_keycloak(payload, realm_id=REALM_ID, realm="platform")
ORG = "22222222-2222-4222-8222-222222222222"


class ParseEventTest(unittest.TestCase):
    def test_parses_envelope(self) -> None:
        parsed = parse_event(
            {"id": "e-1", "kind": "user", "type": "VERIFY_EMAIL", "realm": "platform", "time": 5, "user_id": SUB}
        )
        self.assertEqual(
            parsed,
            Event(id="e-1", kind="user", type="VERIFY_EMAIL", realm="platform", time=5, user_id=SUB),
        )

    def test_drops_fields_the_service_does_not_need(self) -> None:
        parsed = parse_event(
            {
                "id": "e-1",
                "kind": "user",
                "type": "UPDATE_EMAIL",
                "realm": "platform",
                "time": 5,
                "user_id": SUB,
                "details": {"updated_email": "yeni@example.test"},
                "ipAddress": "192.0.2.1",
            }
        )
        self.assertNotIn("example.test", repr(parsed))
        self.assertNotIn("192.0.2.1", repr(parsed))

    def test_rejects_missing_required_field(self) -> None:
        for missing in ("id", "kind", "type", "realm", "time"):
            payload = {"id": "e-1", "kind": "user", "type": "REGISTER", "realm": "platform", "time": 5, "user_id": SUB}
            del payload[missing]
            with self.subTest(missing=missing), self.assertRaises(EventError):
                parse_event(payload)

    def test_rejects_wrong_shapes(self) -> None:
        base = {"id": "e-1", "kind": "user", "type": "REGISTER", "realm": "platform", "time": 5, "user_id": SUB}
        for bad in (
            [],
            "metin",
            {**base, "kind": "system"},
            {**base, "time": "dün"},
            {**base, "time": True},
            {**base, "id": ""},
            {**base, "id": "x" * 129},
            {**base, "user_id": 5},
            {**base, "user_id": ".."},
            {**base, "user_id": "a/b"},
            {**base, "user_id": "a b"},
        ):
            with self.subTest(bad=bad), self.assertRaises(EventError):
                parse_event(bad)

    def test_handled_event_needs_user_id(self) -> None:
        with self.assertRaises(EventError):
            parse_event({"id": "e-1", "kind": "user", "type": "REGISTER", "realm": "platform", "time": 5})

    def test_membership_event_needs_organization_id(self) -> None:
        with self.assertRaises(EventError):
            parse_event(
                {
                    "id": "e-1",
                    "kind": "admin",
                    "type": "ORGANIZATION_MEMBERSHIP_CREATE",
                    "realm": "platform",
                    "time": 5,
                    "user_id": SUB,
                }
            )

    def test_unhandled_type_parses_without_user(self) -> None:
        parsed = parse_event({"id": "e-1", "kind": "user", "type": "LOGIN", "realm": "platform", "time": 5})
        self.assertFalse(is_handled(parsed))

    def test_kind_and_type_must_match(self) -> None:
        # USER_DELETE is an admin event. The service does not process it with kind `user`.
        parsed = parse_event(
            {"id": "e-1", "kind": "user", "type": "USER_DELETE", "realm": "platform", "time": 5, "user_id": SUB}
        )
        self.assertFalse(is_handled(parsed))


class FromKeycloakTest(unittest.TestCase):
    def test_user_event(self) -> None:
        envelope = translate(
            {
                "id": "k-1",
                "time": 1795000000000,
                "type": "VERIFY_EMAIL",
                "realmId": REALM_ID,
                "clientId": "press",
                "userId": SUB,
                "ipAddress": "192.0.2.1",
                "details": {"email": "ayse@example.test"},
            }
        )
        self.assertEqual(
            envelope,
            {
                "id": "k-1",
                "kind": "user",
                "type": "VERIFY_EMAIL",
                "realm": "platform",
                "time": 1795000000000,
                "user_id": SUB,
            },
        )

    def test_admin_user_update(self) -> None:
        envelope = translate(
            {
                "id": "k-2",
                "time": 7,
                "realmId": REALM_ID,
                "operationType": "UPDATE",
                "resourceType": "USER",
                "resourcePath": f"users/{SUB}",
                "representation": '{"email":"ayse@example.test"}',
            }
        )
        self.assertEqual(
            envelope,
            {"id": "k-2", "kind": "admin", "type": "USER_UPDATE", "realm": "platform", "time": 7, "user_id": SUB},
        )

    def test_admin_organization_membership(self) -> None:
        envelope = translate(
            {
                "id": "k-3",
                "time": 8,
                "realmId": REALM_ID,
                "operationType": "DELETE",
                "resourceType": "ORGANIZATION_MEMBERSHIP",
                "resourcePath": f"organizations/{ORG}/members/{SUB}",
            }
        )
        self.assertEqual(envelope["type"], "ORGANIZATION_MEMBERSHIP_DELETE")
        self.assertEqual(envelope["user_id"], SUB)
        self.assertEqual(envelope["organization_id"], ORG)

    def test_admin_membership_create_has_no_user(self) -> None:
        # Keycloak 26.8.2 omits the user ID from the path in member-addition events.
        # Kaynak: OrganizationMemberResource.java, `resourcePath(session.getContext().getUri())`.
        envelope = translate(
            {
                "id": "k-4",
                "time": 8,
                "realmId": REALM_ID,
                "operationType": "CREATE",
                "resourceType": "ORGANIZATION_MEMBERSHIP",
                "resourcePath": f"organizations/{ORG}/members",
            }
        )
        self.assertEqual(envelope["organization_id"], ORG)
        self.assertNotIn("user_id", envelope)
        with self.assertRaises(EventError):
            parse_event(envelope)

    def test_admin_event_without_id_gets_a_stable_id(self) -> None:
        payload = {
            "time": 9,
            "realmId": REALM_ID,
            "operationType": "DELETE",
            "resourceType": "USER",
            "resourcePath": f"users/{SUB}",
        }
        first, second = translate(payload), translate(dict(payload))
        self.assertEqual(first["id"], second["id"])
        self.assertNotEqual(first["id"], translate({**payload, "time": 10})["id"])

    def test_realm_id_is_mapped_to_configured_realm_name(self) -> None:
        # Keycloak puts the internal ID in `realmId`. The name is `platform` (EventBuilder.java, 26.8.2).
        envelope = translate({"id": "k-1", "time": 1, "type": "REGISTER", "realmId": REALM_ID, "userId": SUB})
        self.assertEqual(envelope["realm"], "platform")

    def test_other_realm_id_never_maps_to_configured_name(self) -> None:
        for other in ("baska-kimlik", "platform", "", None):
            with self.subTest(other=other):
                envelope = translate({"id": "k-1", "time": 1, "type": "REGISTER", "realmId": other, "userId": SUB})
                self.assertNotEqual(envelope["realm"], "platform")

    def test_unconfigured_realm_id_is_an_error(self) -> None:
        with self.assertRaises(EventError):
            from_keycloak(
                {"id": "k-1", "time": 1, "type": "REGISTER", "realmId": "platform", "userId": SUB},
                realm_id="",
                realm="platform",
            )

    def test_rejects_unknown_shape(self) -> None:
        with self.assertRaises(EventError):
            translate({"hello": "world"})


if __name__ == "__main__":
    unittest.main()
