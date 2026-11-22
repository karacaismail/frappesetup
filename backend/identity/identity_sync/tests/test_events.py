"""Olay zarfının ve Keycloak biçiminden çevirinin testleri.

Zarfın kaynağı `contracts/identity_sync.openapi.yaml` dosyasıdır.
Keycloak alan adlarının kaynağı Keycloak 26.8.2 Admin REST API belgesidir.
"""

from __future__ import annotations

import unittest

from identity_sync.events import Event, EventError, from_keycloak, is_handled, parse_event

SUB = "11111111-1111-4111-8111-111111111111"
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
        # USER_DELETE bir yönetici olayıdır. `user` türüyle gelirse servis işlemez.
        parsed = parse_event(
            {"id": "e-1", "kind": "user", "type": "USER_DELETE", "realm": "platform", "time": 5, "user_id": SUB}
        )
        self.assertFalse(is_handled(parsed))


class FromKeycloakTest(unittest.TestCase):
    def test_user_event(self) -> None:
        envelope = from_keycloak(
            {
                "id": "k-1",
                "time": 1795000000000,
                "type": "VERIFY_EMAIL",
                "realmId": "platform",
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
        envelope = from_keycloak(
            {
                "id": "k-2",
                "time": 7,
                "realmId": "platform",
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
        envelope = from_keycloak(
            {
                "id": "k-3",
                "time": 8,
                "realmId": "platform",
                "operationType": "DELETE",
                "resourceType": "ORGANIZATION_MEMBERSHIP",
                "resourcePath": f"organizations/{ORG}/members/{SUB}",
            }
        )
        self.assertEqual(envelope["type"], "ORGANIZATION_MEMBERSHIP_DELETE")
        self.assertEqual(envelope["user_id"], SUB)
        self.assertEqual(envelope["organization_id"], ORG)

    def test_admin_membership_create_has_no_user(self) -> None:
        # Keycloak 26.8.2 üye ekleme olayında yola kullanıcı kimliğini yazmaz.
        # Kaynak: OrganizationMemberResource.java, `resourcePath(session.getContext().getUri())`.
        envelope = from_keycloak(
            {
                "id": "k-4",
                "time": 8,
                "realmId": "platform",
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
            "realmId": "platform",
            "operationType": "DELETE",
            "resourceType": "USER",
            "resourcePath": f"users/{SUB}",
        }
        first, second = from_keycloak(payload), from_keycloak(dict(payload))
        self.assertEqual(first["id"], second["id"])
        self.assertNotEqual(first["id"], from_keycloak({**payload, "time": 10})["id"])

    def test_rejects_unknown_shape(self) -> None:
        with self.assertRaises(EventError):
            from_keycloak({"hello": "world"})


if __name__ == "__main__":
    unittest.main()
