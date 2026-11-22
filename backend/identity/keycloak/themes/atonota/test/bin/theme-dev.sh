#!/usr/bin/env bash
# Tema deneme ortamını yönetir. Sahibi kimlik-tema işidir.
# Kullanım: theme-dev.sh up | build | sync | tunnel | tunnel-close | down | env
#   up    Container'ları var olan imajla açar. Keycloak hazır olana kadar bekler.
#   build İmajı derler. Disk dar olduğu için yalnız imaj yokken çalıştırın.
#   sync  Tema dosyalarını çalışan container'a kopyalar. Yeniden derleme gerekmez.
#         "sync login", "sync email" ya da "sync account" yalnız o bölümü kopyalar.
#   tunnel Keycloak ve Mailpit portlarını ssh tüneliyle bu bilgisayara taşır.
#   tunnel-close Tüneli kapatır.
#   down  Tüneli ve container'ları kapatır. Birimleri silmez.
#   env   .env dosyasını üretir ve yolunu yazar.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
theme="$(cd "$here/.." && pwd)"
env_file="$here/.env"
# The shared "factory" disk is nearly full (backend/AGENTS.md, "Disk dar").
# FS_COLIMA_PROFILE=default starts the environment in the "colima" profile instead.
if [[ "${FS_COLIMA_PROFILE:-factory}" == "default" ]]; then
  export DOCKER_CONTEXT="${DOCKER_CONTEXT:-colima}"
  lima_name="${COLIMA_LIMA_NAME:-colima}"
else
  export DOCKER_CONTEXT="${DOCKER_CONTEXT:-colima-factory}"
  lima_name="${COLIMA_LIMA_NAME:-colima-factory}"
fi

# Prints the value of one variable from the .env file.
env_value() {
  sed -n "s/^$1=//p" "$env_file" | head -n 1
}

# Adds a variable to an existing .env file when an older file does not have it yet.
ensure_env() {
  if ! grep -q "^$1=" "$env_file"; then
    echo "$1=$2" >> "$env_file"
  fi
}

write_env() {
  if [[ -f "$env_file" ]]; then
    ensure_env IDENTITY_BRAND_NAME "Sample Brand"
    ensure_env IDENTITY_ACCOUNT_DELETION_URL "http://press.localhost:$(( $(env_value KC_PORT) + 3 ))/account/delete"
    ensure_env IDENTITY_TEST_PASSWORD "$(openssl rand -hex 16)"
    ensure_env IDENTITY_TEST_TOTP_SECRET "$(openssl rand -hex 16)"
    return
  fi
  local base="${PANE_PORT:-3950}"
  umask 077
  {
    echo "KC_PORT=$base"
    echo "KC_PUBLIC_URL=http://localhost:$base"
    echo "MAILPIT_UI_PORT=$((base + 1))"
    echo "KC_BOOTSTRAP_ADMIN_USERNAME=tema-admin"
    echo "KC_BOOTSTRAP_ADMIN_PASSWORD=$(openssl rand -hex 16)"
    # The brand name shown by the themes. The test value differs from the theme name on purpose.
    echo "IDENTITY_BRAND_NAME=Sample Brand"
    # The deletion page belongs to Press. In this environment the address is only a link target.
    echo "IDENTITY_ACCOUNT_DELETION_URL=http://press.localhost:$((base + 3))/account/delete"
    # Secrets of the made-up test users. The tests read them from this file. They are never printed.
    echo "IDENTITY_TEST_PASSWORD=$(openssl rand -hex 16)"
    echo "IDENTITY_TEST_TOTP_SECRET=$(openssl rand -hex 16)"
  } > "$env_file"
}

# Writes new random secrets for the made-up test users. Each start of the environment gets its own values.
# The values go only into the .env file (mode 600). They are never printed.
rotate_test_secrets() {
  local kept
  kept="$(grep -v -E '^IDENTITY_TEST_(PASSWORD|TOTP_SECRET)=' "$env_file" || true)"
  umask 077
  {
    printf '%s\n' "$kept"
    echo "IDENTITY_TEST_PASSWORD=$(openssl rand -hex 16)"
    echo "IDENTITY_TEST_TOTP_SECRET=$(openssl rand -hex 16)"
  } > "$env_file"
}

compose() { docker compose --env-file "$env_file" -f "$here/compose.yaml" "$@"; }

tunnel_pid="$here/.tunnel.pid"

tunnel_open() {
  # colima-factory profilinin port yönlendirmesi bozuk. Yeni portlar bu bilgisayara açılmaz.
  # Bu işlev sanal makineye ayrı bir ssh bağlantısı açar. Colima'nın kendi bağlantısına dokunmaz.
  # The .env file is read value by value. It is not sourced, because a value may contain spaces.
  local KC_PORT MAILPIT_UI_PORT KC_PUBLIC_URL
  KC_PORT="$(env_value KC_PORT)"
  MAILPIT_UI_PORT="$(env_value MAILPIT_UI_PORT)"
  KC_PUBLIC_URL="$(env_value KC_PUBLIC_URL)"
  local ssh_conf="$HOME/.colima/_lima/$lima_name/ssh.config"
  if [[ ! -f "$ssh_conf" ]]; then
    echo "Colima ssh config is missing: $ssh_conf" >&2
    exit 1
  fi
  if [[ -f "$tunnel_pid" ]] && kill -0 "$(cat "$tunnel_pid")" 2>/dev/null; then
    echo "The tunnel is already open."
    return
  fi
  local port key
  port="$(awk '/^ *Port /{print $2; exit}' "$ssh_conf")"
  key="$(awk '/^ *IdentityFile /{gsub(/"/,"",$2); print $2; exit}' "$ssh_conf")"
  ssh -F /dev/null -o IdentityFile="$key" -o IdentitiesOnly=yes -o BatchMode=yes \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o NoHostAuthenticationForLocalhost=yes \
    -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -S none -N \
    -L "127.0.0.1:$KC_PORT:127.0.0.1:$KC_PORT" -L "127.0.0.1:$MAILPIT_UI_PORT:127.0.0.1:$MAILPIT_UI_PORT" \
    -p "$port" 127.0.0.1 </dev/null >/dev/null 2>&1 &
  echo $! > "$tunnel_pid"
  sleep 2
  if ! kill -0 "$(cat "$tunnel_pid")" 2>/dev/null; then
    rm -f "$tunnel_pid"
    echo "The tunnel could not be opened." >&2
    exit 1
  fi
  echo "The tunnel is open: $KC_PUBLIC_URL and http://127.0.0.1:$MAILPIT_UI_PORT"
}

tunnel_close() {
  if [[ -f "$tunnel_pid" ]]; then
    # Numara başka bir sürece geçmiş olabilir. Yalnız ssh süreci kapatılır.
    local pid
    pid="$(cat "$tunnel_pid")"
    if ps -p "$pid" -o comm= 2>/dev/null | grep -q ssh; then
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$tunnel_pid"
  fi
}

case "${1:-}" in
  env)
    write_env
    echo "$env_file"
    ;;
  up)
    write_env
    rotate_test_secrets
    # The image is reused when it exists. Building needs disk space, so it is a separate, explicit command.
    compose up -d --no-build --wait
    ;;
  build)
    write_env
    compose build
    ;;
  sync)
    write_env
    cid="$(compose ps -q keycloak)"
    # İkinci değer yalnız bir bölümü kopyalar: sync login ya da sync email.
    case "${2:-}" in
      "" | login | email | account) ;;
      *)
        echo "Only login, email or account can be copied." >&2
        exit 2
        ;;
    esac
    parts=(login email account)
    if [[ -n "${2:-}" ]]; then parts=("$2"); fi
    for part in "${parts[@]}"; do
      docker exec -u 0 "$cid" rm -rf "/opt/keycloak/themes/atonota/$part"
      docker cp "$theme/$part" "$cid:/opt/keycloak/themes/atonota/$part"
    done
    ;;
  tunnel)
    write_env
    tunnel_open
    ;;
  tunnel-close)
    tunnel_close
    ;;
  down)
    write_env
    tunnel_close
    compose down
    ;;
  *)
    echo "Usage: theme-dev.sh up | build | sync | tunnel | tunnel-close | down | env" >&2
    exit 2
    ;;
esac
