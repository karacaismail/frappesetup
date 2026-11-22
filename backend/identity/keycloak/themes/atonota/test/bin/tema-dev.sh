#!/usr/bin/env bash
# Tema deneme ortamını yönetir. Sahibi kimlik-tema işidir.
# Kullanım: tema-dev.sh up | sync | tunel | tunel-kapat | down | env
#   up    İmajı derler ve container'ları açar. Keycloak hazır olana kadar bekler.
#   sync  Tema dosyalarını çalışan container'a kopyalar. Yeniden derleme gerekmez.
#         "sync login", "sync email" ya da "sync account" yalnız o bölümü kopyalar.
#   tunel Keycloak ve Mailpit portlarını ssh tüneliyle bu bilgisayara taşır.
#   tunel-kapat Tüneli kapatır.
#   down  Tüneli ve container'ları kapatır. Birimleri silmez.
#   env   .env dosyasını üretir ve yolunu yazar.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
theme="$(cd "$here/.." && pwd)"
env_file="$here/.env"
export DOCKER_CONTEXT="${DOCKER_CONTEXT:-colima-factory}"

write_env() {
  if [[ -f "$env_file" ]]; then return; fi
  local base="${PANE_PORT:-3950}"
  umask 077
  {
    echo "KC_PORT=$base"
    echo "KC_PUBLIC_URL=http://localhost:$base"
    echo "MAILPIT_UI_PORT=$((base + 1))"
    echo "KC_BOOTSTRAP_ADMIN_USERNAME=tema-admin"
    echo "KC_BOOTSTRAP_ADMIN_PASSWORD=$(openssl rand -hex 16)"
  } > "$env_file"
}

compose() { docker compose --env-file "$env_file" -f "$here/compose.yaml" "$@"; }

tunnel_pid="$here/.tunel.pid"

tunnel_open() {
  # colima-factory profilinin port yönlendirmesi bozuk. Yeni portlar bu bilgisayara açılmaz.
  # Bu işlev sanal makineye ayrı bir ssh bağlantısı açar. Colima'nın kendi bağlantısına dokunmaz.
  # shellcheck disable=SC1090
  . "$env_file"
  local ssh_conf="$HOME/.colima/_lima/${COLIMA_LIMA_AD:-colima-factory}/ssh.config"
  if [[ ! -f "$ssh_conf" ]]; then
    echo "Colima ssh ayarı yok: $ssh_conf" >&2
    exit 1
  fi
  if [[ -f "$tunnel_pid" ]] && kill -0 "$(cat "$tunnel_pid")" 2>/dev/null; then
    echo "Tünel zaten açık."
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
    echo "Tünel açılamadı." >&2
    exit 1
  fi
  echo "Tünel açık: $KC_PUBLIC_URL ve http://127.0.0.1:$MAILPIT_UI_PORT"
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
    compose up -d --build --wait
    ;;
  sync)
    write_env
    cid="$(compose ps -q keycloak)"
    # İkinci değer yalnız bir bölümü kopyalar: sync login ya da sync email.
    case "${2:-}" in
      "" | login | email | account) ;;
      *)
        echo "Yalnız login, email ya da account kopyalanır." >&2
        exit 2
        ;;
    esac
    for part in ${2:-login email account}; do
      docker exec -u 0 "$cid" rm -rf "/opt/keycloak/themes/atonota/$part"
      docker cp "$theme/$part" "$cid:/opt/keycloak/themes/atonota/$part"
    done
    ;;
  tunel)
    write_env
    tunnel_open
    ;;
  tunel-kapat)
    tunnel_close
    ;;
  down)
    write_env
    tunnel_close
    compose down
    ;;
  *)
    echo "Kullanım: tema-dev.sh up | sync | tunel | tunel-kapat | down | env" >&2
    exit 2
    ;;
esac
