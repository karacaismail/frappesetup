#!/bin/sh
# ProPR web girişi için GitHub uygulamasının istemci sırrını gizli olarak alır.
# Sır ekrana yazılmaz. Sır yalnız ProPR'ın 0600 izinli .env dosyasına yazılır.
# Kullanım: set-oauth-secret.sh <CLIENT_ID>
# Client ID ilk argümandan ya da GH_OAUTH_CLIENT_ID ortam değişkeninden okunur.
set -eu
ENV_FILE="$HOME/Library/Application Support/ProPR Desktop/local-runtime/.env"
CLIENT_ID="${1:-${GH_OAUTH_CLIENT_ID:-}}"
if [ -z "$CLIENT_ID" ]; then
  echo "Client ID gerekli. Kullanım: set-oauth-secret.sh <CLIENT_ID>" >&2
  exit 2
fi
exec /usr/bin/python3 -I -c '
import getpass, os, re, sys
path, client_id = sys.argv[1], sys.argv[2]
if not re.fullmatch(r"[A-Za-z0-9._-]{8,100}", client_id):
    sys.exit("Client ID biçimi beklenmedik. Hiçbir şey değişmedi.")
secret = None
for attempt in range(3):
    raw = getpass.getpass("GitHub istemci sırrını yapıştırın, sonra Enter tuşuna basın: ")
    value = raw.replace("\x1b[200~", "").replace("\x1b[201~", "").strip()
    if re.fullmatch(r"[0-9a-f]{40}", value):
        secret = value
        break
    print("Bu değer istemci sırrına benzemiyor. Sır 40 karakter olmalı. Yeniden deneyin.")
if secret is None:
    sys.exit("Sır alınamadı. Hiçbir şey değişmedi.")
values = {
    "PROPR_WEB_AUTH_MODE": "github",
    "GH_OAUTH_CLIENT_ID": client_id,
    "GH_OAUTH_CALLBACK_URL": "http://localhost:4000/api/auth/github/callback",
    "GH_OAUTH_CLIENT_SECRET": secret,
}
lines = open(path, encoding="utf-8").read().split("\n")
seen = set()
for i, line in enumerate(lines):
    m = re.match(r"^\s*([A-Z_]+)=", line)
    if m and m.group(1) in values:
        lines[i] = m.group(1) + "=" + values[m.group(1)]
        seen.add(m.group(1))
for key, value in values.items():
    if key not in seen:
        lines.append(key + "=" + value)
tmp = path + ".tmp"
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
os.replace(tmp, path)
print("Tamam. Sır kaydedildi. Bu sekme şimdi kapanacak.")
' "$ENV_FILE" "$CLIENT_ID"
