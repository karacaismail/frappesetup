"""Test yardımcıları. Yalnız Python'un kendi kitaplığını kullanır."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KLASOR = Path(__file__).resolve().parents[1]
REALM_DOSYASI = KLASOR / "realm" / "platform-realm.json"
KULLANICI_DOSYASI = KLASOR / "realm" / "dev-users" / "platform-users-0.json"
PAROLA_LISTESI = KLASOR / "realm" / "password-blacklists" / "yaygin-parolalar.txt"
ORNEK_ENV = KLASOR / ".env.example"


def realm_oku() -> dict:
    with REALM_DOSYASI.open(encoding="utf-8") as dosya:
        return json.load(dosya)


def kullanicilari_oku() -> dict:
    with KULLANICI_DOSYASI.open(encoding="utf-8") as dosya:
        return json.load(dosya)


def ortam(ad: str) -> str:
    deger = os.environ.get(ad, "")
    if not deger:
        raise KeyError(f"{ad} ortam değişkeni boş. Testi bin/kc-dev.sh test ile çalıştırın.")
    return deger


def canli_var_mi() -> bool:
    return bool(os.environ.get("KC_PUBLIC_URL"))


class HttpYanit:
    def __init__(self, durum: int, govde: bytes, basliklar: dict):
        self.durum = durum
        self.govde = govde
        self.basliklar = basliklar

    def json(self):
        return json.loads(self.govde.decode("utf-8"))


def istek(yontem: str, adres: str, *, form: dict | None = None, govde: dict | None = None,
          belirtec: str | None = None, basliklar: dict | None = None) -> HttpYanit:
    veri = None
    ust = dict(basliklar or {})
    if form is not None:
        veri = urllib.parse.urlencode(form).encode("ascii")
        ust["Content-Type"] = "application/x-www-form-urlencoded"
    elif govde is not None:
        veri = json.dumps(govde).encode("utf-8")
        ust["Content-Type"] = "application/json"
    if belirtec:
        ust["Authorization"] = f"Bearer {belirtec}"
    ist = urllib.request.Request(adres, data=veri, method=yontem, headers=ust)
    try:
        with urllib.request.urlopen(ist, timeout=30) as yanit:
            return HttpYanit(yanit.status, yanit.read(), dict(yanit.headers))
    except urllib.error.HTTPError as hata:
        return HttpYanit(hata.code, hata.read(), dict(hata.headers))


def belirtec_ucu(realm: str = "platform") -> str:
    return f"{ortam('KC_PUBLIC_URL')}/realms/{realm}/protocol/openid-connect/token"


def istemci_belirteci(istemci: str, sir: str, kapsam: str | None = None) -> HttpYanit:
    form = {"grant_type": "client_credentials", "client_id": istemci, "client_secret": sir}
    if kapsam is not None:
        form["scope"] = kapsam
    return istek("POST", belirtec_ucu(), form=form)


def yonetici_belirteci() -> str:
    yanit = istek(
        "POST",
        belirtec_ucu("master"),
        form={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": ortam("KC_BOOTSTRAP_ADMIN_USERNAME"),
            "password": ortam("KC_BOOTSTRAP_ADMIN_PASSWORD"),
        },
    )
    if yanit.durum != 200:
        raise RuntimeError(f"Yönetici belirteci alınamadı: {yanit.durum}")
    return yanit.json()["access_token"]


def admin(yol: str, belirtec: str, yontem: str = "GET", govde: dict | None = None) -> HttpYanit:
    return istek(yontem, f"{ortam('KC_PUBLIC_URL')}/admin/realms/platform{yol}", belirtec=belirtec, govde=govde)


def jwt_govdesi(jwt: str) -> dict:
    parcalar = jwt.split(".")
    if len(parcalar) != 3:
        raise ValueError("Belirteç üç parçalı değil")
    govde = parcalar[1] + "=" * (-len(parcalar[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(govde).decode("utf-8"))
