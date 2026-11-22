"""Mutabakat karşılaştırmasının testleri.

Kural: Keycloak doğruluk kaynağıdır (karar sitesi, `rail-4-keycloak.md`, 5. bölüm).
Komut yalnız farkı raporlar. Hiçbir kaydı değiştirmez.
"""

from __future__ import annotations

import unittest

from identity_sync.mapping import Organization, Tenant, UserSnapshot
from identity_sync.reconcile import Difference, Identity, compare, expected_identities

ISSUER = "http://kimlik.localhost:6110/realms/platform"
ORG = Organization(id="o-1", alias="kiraci1")
OTHER = Organization(id="o-2", alias="baska")
TENANTS = (Tenant(name="kiraci1", base_url="http://kiraci1.localhost:6111", organization="kiraci1"),)


def user(subject: str, *, orgs=(ORG,), verified: bool = True, enabled: bool = True) -> UserSnapshot:
    return UserSnapshot(
        subject=subject,
        email=f"{subject}@example.test",
        email_verified=verified,
        enabled=enabled,
        first_name="",
        last_name="",
        organizations=tuple(orgs),
    )


def identity(subject: str, *, email: str | None = None, enabled: bool = True, issuer: str = ISSUER) -> Identity:
    return Identity(issuer=issuer, subject=subject, email=email or f"{subject}@example.test", enabled=enabled)


class ExpectedTest(unittest.TestCase):
    def test_only_enabled_verified_members_are_expected(self) -> None:
        users = [
            user("a"),
            user("b", verified=False),
            user("c", enabled=False),
            user("d", orgs=()),
            user("e", orgs=(OTHER,)),
        ]

        press, tenants = expected_identities(users, issuer=ISSUER, tenants=TENANTS)

        self.assertEqual([i.subject for i in press], ["a", "e"])
        self.assertEqual([i.subject for i in tenants["kiraci1"]], ["a"])


class CompareTest(unittest.TestCase):
    def test_equal_sides_have_no_difference(self) -> None:
        self.assertEqual(compare([identity("a")], [identity("a")], target="press"), [])

    def test_missing_user(self) -> None:
        self.assertEqual(compare([identity("a")], [], target="press"), [Difference("press", "a", "missing")])

    def test_unexpected_enabled_user(self) -> None:
        self.assertEqual(compare([], [identity("z")], target="kiraci1"), [Difference("kiraci1", "z", "unexpected")])

    def test_disabled_leftover_is_not_a_difference(self) -> None:
        # Kapatılan kullanıcı sitede kapalı kayıt olarak kalır. Bu beklenen sonuçtur (X-11).
        self.assertEqual(compare([], [identity("z", enabled=False)], target="kiraci1"), [])

    def test_email_mismatch(self) -> None:
        actual = [identity("a", email="eski@example.test")]
        self.assertEqual(compare([identity("a")], actual, target="kiraci1"), [Difference("kiraci1", "a", "email_mismatch")])

    def test_email_compare_ignores_case(self) -> None:
        actual = [identity("a", email="A@Example.test")]
        self.assertEqual(compare([identity("a")], actual, target="kiraci1"), [])

    def test_expected_user_disabled_on_target(self) -> None:
        actual = [identity("a", enabled=False)]
        self.assertEqual(compare([identity("a")], actual, target="kiraci1"), [Difference("kiraci1", "a", "disabled")])

    def test_other_issuer_is_unexpected(self) -> None:
        actual = [identity("a", issuer="http://baska.example.test/realms/x")]
        self.assertEqual(
            compare([identity("a")], actual, target="press"),
            [Difference("press", "a", "missing"), Difference("press", "a", "unexpected")],
        )

    def test_difference_does_not_carry_email(self) -> None:
        (difference,) = compare([identity("a")], [identity("a", email="eski@example.test")], target="press")
        self.assertNotIn("example.test", repr(difference))

    def test_result_order_is_stable(self) -> None:
        expected = [identity("b"), identity("a")]
        self.assertEqual([d.subject for d in compare(expected, [], target="press")], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
