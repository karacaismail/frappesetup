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

# Creates one random value. Stops the script when the generator fails or prints nothing usable.
# The value goes into the named variable. It is never printed.
random_value() {
  local __target="$1" __value
  if ! __value="$(openssl rand -hex 16)" || [[ ! "$__value" =~ ^[0-9a-f]{32}$ ]]; then
    echo "Could not create a random test value. The settings file was not changed." >&2
    exit 1
  fi
  printf -v "$__target" '%s' "$__value"
}

# Replaces the .env file in one step. The new content is complete before the old file is touched.
replace_env() {
  local tmp
  umask 077
  tmp="$(mktemp "$here/.env.XXXXXX")"
  if ! printf '%s\n' "$1" > "$tmp" || ! mv -f "$tmp" "$env_file"; then
    rm -f "$tmp"
    echo "Could not write the settings file." >&2
    exit 1
  fi
}

# Writes the .env file. Every start of the environment gets new secrets for the made-up test users.
# All random values are created and checked first. The file changes only when every value exists.
write_env() {
  local test_password test_totp_secret admin_password content
  random_value test_password
  random_value test_totp_secret
  if [[ -f "$env_file" ]]; then
    content="$(grep -v -E '^IDENTITY_TEST_(PASSWORD|TOTP_SECRET)=' "$env_file" || true)"
    if ! grep -q '^IDENTITY_BRAND_NAME=' <<< "$content"; then
      content+=$'\n'"IDENTITY_BRAND_NAME=Sample Brand"
    fi
    if ! grep -q '^IDENTITY_ACCOUNT_DELETION_URL=' <<< "$content"; then
      content+=$'\n'"IDENTITY_ACCOUNT_DELETION_URL=http://press.localhost:$(( $(env_value KC_PORT) + 3 ))/account/delete"
    fi
  else
    local base="${PANE_PORT:-3950}"
    random_value admin_password
    content="KC_PORT=$base
KC_PUBLIC_URL=http://localhost:$base
MAILPIT_UI_PORT=$((base + 1))
KC_BOOTSTRAP_ADMIN_USERNAME=theme-admin
KC_BOOTSTRAP_ADMIN_PASSWORD=$admin_password
IDENTITY_BRAND_NAME=Sample Brand
IDENTITY_ACCOUNT_DELETION_URL=http://press.localhost:$((base + 3))/account/delete"
  fi
  content+=$'\n'"IDENTITY_TEST_PASSWORD=$test_password"
  content+=$'\n'"IDENTITY_TEST_TOTP_SECRET=$test_totp_secret"
  replace_env "$content"
}

# Makes sure the .env file exists without changing the secrets of a running environment.
ensure_env_file() {
  if [[ ! -f "$env_file" ]]; then
    write_env
  fi
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
    ensure_env_file
    echo "$env_file"
    ;;
  up)
    # A start writes new secrets for the made-up test users.
    write_env
    # The image is reused when it exists. Building needs disk space, so it is a separate, explicit command.
    compose up -d --no-build --wait
    ;;
  build)
    ensure_env_file
    compose build
    ;;
  sync)
    ensure_env_file
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
    ensure_env_file
    tunnel_open
    ;;
  tunnel-close)
    tunnel_close
    ;;
  down)
    ensure_env_file
    tunnel_close
    compose down
    ;;
  *)
    echo "Usage: theme-dev.sh up | build | sync | tunnel | tunnel-close | down | env" >&2
    exit 2
    ;;
esac
