#!/usr/bin/env bash
# Keycloak geliştirme ortamını yönetir. Sahibi kimlik-realm işidir.
# Kullanım: bin/kc-dev.sh <config|up|down|restart|logs|ps|exec|test|realm-sil|tunel|tunel-kapat>
# Portlar PANE_PORT değişkeninden türer. Keycloak P, Mailpit ekranı P+6 portunu alır.
set -euo pipefail

KLASOR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$(cd "$KLASOR/../.." && pwd)"
COMPOSE_DOSYASI="$BACKEND/dev/compose.keycloak.yaml"
ENV_DOSYASI="$KLASOR/.env"
PROJE="${COMPOSE_PROJECT_NAME:-fs-kimlik-realm}"
BAGLAM="${DOCKER_CONTEXT:-colima-factory}"

if [ -z "${PANE_PORT:-}" ]; then
  echo "PANE_PORT boş. Örnek: PANE_PORT=5070 $0 up" >&2
  exit 2
fi

rastgele() { python3 -c 'import secrets; print(secrets.token_urlsafe(24))'; }

env_hazirla() {
  if [ -f "$ENV_DOSYASI" ]; then
    return
  fi
  echo ".env yok. .env.example dosyasından üretiliyor." >&2
  while IFS= read -r satir; do
    case "$satir" in
      *=degistir-*) printf '%s=%s\n' "${satir%%=*}" "$(rastgele)" ;;
      *) printf '%s\n' "$satir" ;;
    esac
  done < "$KLASOR/.env.example" > "$ENV_DOSYASI"
  chmod 600 "$ENV_DOSYASI"
}

ortam_yukle() {
  env_hazirla
  set -a
  # shellcheck disable=SC1090
  . "$ENV_DOSYASI"
  set +a
  export KC_PORT="$PANE_PORT"
  export KC_PUBLIC_URL="http://kimlik.localhost:$PANE_PORT"
  export MAILPIT_UI_PORT="$((PANE_PORT + 6))"
  export ATONOTA_SITE_KIRACI1_URL="http://kiraci1.localhost:$((PANE_PORT + 1))"
  export ATONOTA_PRESS_URL="http://press.localhost:$((PANE_PORT + 3))"
}

compose() {
  docker --context "$BAGLAM" compose -p "$PROJE" -f "$COMPOSE_DOSYASI" "$@"
}

TUNEL_PID="$KLASOR/.tunel.pid"

tunel_ac() {
  # Colima'nın port yönlendirmesi bozulursa yeni portlar ana makineye açılmaz.
  # Bu komut sanal makineye ayrı bir ssh bağlantısı açar ve iki portu ana makineye taşır.
  # Colima'nın kendi bağlantısına dokunmaz. Yalnız bu Mac'teki Colima kurulumu için geçerlidir.
  local lima_ad="${COLIMA_LIMA_AD:-colima-factory}"
  local ssh_conf="$HOME/.colima/_lima/$lima_ad/ssh.config"
  if [ ! -f "$ssh_conf" ]; then
    echo "Colima ssh ayarı yok: $ssh_conf" >&2
    exit 1
  fi
  if [ -f "$TUNEL_PID" ] && kill -0 "$(cat "$TUNEL_PID")" 2>/dev/null; then
    echo "Tünel zaten açık (pid $(cat "$TUNEL_PID"))."
    return
  fi
  local port anahtar
  port="$(awk '/^ *Port /{print $2; exit}' "$ssh_conf")"
  anahtar="$(awk '/^ *IdentityFile /{gsub(/"/,"",$2); print $2; exit}' "$ssh_conf")"
  ssh -F /dev/null -o IdentityFile="$anahtar" -o IdentitiesOnly=yes -o BatchMode=yes \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o NoHostAuthenticationForLocalhost=yes \
    -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -S none -N \
    -L "127.0.0.1:$KC_PORT:127.0.0.1:$KC_PORT" -L "127.0.0.1:$MAILPIT_UI_PORT:127.0.0.1:$MAILPIT_UI_PORT" \
    -p "$port" "127.0.0.1" </dev/null >/dev/null 2>&1 &
  echo $! > "$TUNEL_PID"
  sleep 2
  if ! kill -0 "$(cat "$TUNEL_PID")" 2>/dev/null; then
    echo "Tünel açılamadı." >&2
    rm -f "$TUNEL_PID"
    exit 1
  fi
  echo "Tünel açık: $KC_PUBLIC_URL ve http://127.0.0.1:$MAILPIT_UI_PORT (pid $(cat "$TUNEL_PID"))"
}

tunel_kapat() {
  if [ -f "$TUNEL_PID" ]; then
    kill "$(cat "$TUNEL_PID")" 2>/dev/null || true
    rm -f "$TUNEL_PID"
    echo "Tünel kapandı."
  fi
}

komut="${1:-}"
shift || true
ortam_yukle

case "$komut" in
  config) compose config "$@" ;;
  up) compose up -d --build --wait "$@" ;;
  down) tunel_kapat; compose down "$@" ;;
  restart) compose restart "$@" ;;
  logs) compose logs "$@" ;;
  ps) compose ps "$@" ;;
  exec) compose exec "$@" ;;
  test) (cd "$KLASOR/tests" && python3 -I -m unittest discover -s . -v "$@") ;;
  tunel) tunel_ac ;;
  tunel-kapat) tunel_kapat ;;
  realm-sil)
    # Realm'i siler, imajı yeniden derler ve Keycloak'ı yeniden kurar. Böylece realm dosyası yeniden içe alınır.
    belirtec="$(curl -fsS -X POST "$KC_PUBLIC_URL/realms/master/protocol/openid-connect/token" \
      -d grant_type=password -d client_id=admin-cli \
      --data-urlencode "username=$KC_BOOTSTRAP_ADMIN_USERNAME" \
      --data-urlencode "password=$KC_BOOTSTRAP_ADMIN_PASSWORD" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
    curl -fsS -o /dev/null -w 'realm silindi: %{http_code}\n' -X DELETE "$KC_PUBLIC_URL/admin/realms/platform" -H "Authorization: Bearer $belirtec"
    compose up -d --build --force-recreate --wait keycloak
    ;;
  *)
    echo "Kullanım: $0 <config|up|down|restart|logs|ps|exec|test|realm-sil|tunel|tunel-kapat>" >&2
    exit 2
    ;;
esac
