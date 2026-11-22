"""Mutabakat karşılaştırması.

Bu modül saftır. Ağa ve diske dokunmaz. Yalnız farkı hesaplar. Hiçbir kaydı değiştirmez.
Keycloak doğruluk kaynağıdır (karar sitesi, `rail-4-keycloak.md`, 5. bölüm).
Fark kaydı e-posta taşımaz. Kullanıcıyı `sub` kimliğiyle anar.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

from identity_sync.mapping import Tenant, UserSnapshot


@dataclass(frozen=True)
class Identity:
    """Bir hedefteki kullanıcı kaydı."""

    issuer: str
    subject: str
    email: str
    enabled: bool


@dataclass(frozen=True)
class Difference:
    """`kind` şu değerlerden biridir: missing, unexpected, email_mismatch, disabled."""

    target: str
    subject: str
    kind: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def expected_identities(
    users: Iterable[UserSnapshot], *, issuer: str, tenants: Sequence[Tenant]
) -> tuple[list[Identity], dict[str, list[Identity]]]:
    """Keycloak'a göre Press'te ve her kiracıda olması gereken kullanıcıları döner.

    Yalnız açık, e-postası doğrulanmış ve bir Organization üyesi olan kullanıcı beklenir.
    """
    press: list[Identity] = []
    per_tenant: dict[str, list[Identity]] = {tenant.name: [] for tenant in tenants}
    for user in users:
        if not (user.enabled and user.email_verified and user.organizations):
            continue
        identity = Identity(issuer=issuer, subject=user.subject, email=user.email, enabled=True)
        press.append(identity)
        aliases = {org.alias for org in user.organizations}
        for tenant in tenants:
            if tenant.organization in aliases:
                per_tenant[tenant.name].append(identity)
    return press, per_tenant


def compare(expected: Iterable[Identity], actual: Iterable[Identity], *, target: str) -> list[Difference]:
    """Beklenen ile hedefteki kayıtları karşılaştırır. Sonuç `sub` sırasına göre dizilir."""
    wanted = {(i.issuer, i.subject): i for i in expected}
    found = {(i.issuer, i.subject): i for i in actual}
    differences: list[tuple[str, int, Difference]] = []
    for key, identity in wanted.items():
        other = found.get(key)
        if other is None:
            kind = "missing"
        elif not other.enabled:
            kind = "disabled"
        elif other.email.lower() != identity.email.lower():
            kind = "email_mismatch"
        else:
            continue
        differences.append((identity.subject, 0, Difference(target, identity.subject, kind)))
    for key, identity in found.items():
        # Kapalı kayıt beklenen bir kalıntıdır (X-11). Açık kayıt ise farktır.
        if key not in wanted and identity.enabled:
            differences.append((identity.subject, 1, Difference(target, identity.subject, "unexpected")))
    return [difference for _subject, _rank, difference in sorted(differences, key=lambda item: item[:2])]
