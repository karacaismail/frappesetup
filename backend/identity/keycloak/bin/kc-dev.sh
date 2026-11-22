#!/usr/bin/env bash
# Keycloak geliştirme ortamını yönetir. Sahibi kimlik-realm işidir.
# Kullanım: bin/kc-dev.sh <config|up|build|down|restart|logs|ps|exec|test|tunel|tunel-kapat|prod-check|realm-reload|realm-delete-only|realm-sil>
# Portlar PANE_PORT değişkeninden türer. Keycloak P, Mailpit ekranı P+6 portunu alır.
set -euo pipefail

KLASOR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$(cd "$KLASOR/../.." && pwd)"
COMPOSE_DOSYASI="$BACKEND/dev/compose.keycloak.yaml"
# Tests may point to their own environment file with made-up values.
ENV_DOSYASI="${KC_ENV_FILE:-$KLASOR/.env}"
PROJE="${COMPOSE_PROJECT_NAME:-fs-kimlik-realm}"
# Profil FS_COLIMA_PROFILE değişkeninden seçilir (backend/AGENTS.md, "Disk dar"). Değer "default" ise colima profili kullanılır.
if [ "${FS_COLIMA_PROFILE:-factory}" = "default" ]; then
  BAGLAM="${DOCKER_CONTEXT:-colima}"
  LIMA_DEFAULT="colima"
else
  BAGLAM="${DOCKER_CONTEXT:-colima-factory}"
  LIMA_DEFAULT="colima-factory"
fi

if [ -z "${PANE_PORT:-}" ]; then
  echo "PANE_PORT boş. Örnek: PANE_PORT=5070 $0 up" >&2
  exit 2
fi

rastgele() { python3 -c 'import secrets; print(secrets.token_urlsafe(24))'; }

example_line() {
  case "$1" in
    *=degistir-*) printf '%s=%s\n' "${1%%=*}" "$(rastgele)" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

env_hazirla() {
  if [ ! -f "$ENV_DOSYASI" ]; then
    echo ".env yok. .env.example dosyasından üretiliyor." >&2
    while IFS= read -r satir; do
      example_line "$satir"
    done < "$KLASOR/.env.example" > "$ENV_DOSYASI"
    chmod 600 "$ENV_DOSYASI"
    return
  fi
  # Örnek dosyaya sonradan eklenen anahtarlar .env dosyasına da eklenir. Var olan değerler değişmez.
  local satir anahtar
  while IFS= read -r satir; do
    case "$satir" in
      [A-Z]*=*) anahtar="${satir%%=*}" ;;
      *) continue ;;
    esac
    if ! grep -q "^${anahtar}=" "$ENV_DOSYASI"; then
      echo ".env dosyasına yeni anahtar eklendi: $anahtar" >&2
      example_line "$satir" >> "$ENV_DOSYASI"
    fi
  done < "$KLASOR/.env.example"
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

# Opens one ssh connection to the Colima VM that carries the given ports to this Mac.
# Usage: ssh_tunel <pid file> <port>... Colima's own connection is not touched.
ssh_tunel() {
  local pid_file="$1"; shift
  local lima_ad="${COLIMA_LIMA_AD:-$LIMA_DEFAULT}"
  local ssh_conf="$HOME/.colima/_lima/$lima_ad/ssh.config"
  local port anahtar forwards=() p
  port="$(awk '/^ *Port /{print $2; exit}' "$ssh_conf")"
  anahtar="$(awk '/^ *IdentityFile /{gsub(/"/,"",$2); print $2; exit}' "$ssh_conf")"
  for p in "$@"; do forwards+=(-L "127.0.0.1:$p:127.0.0.1:$p"); done
  ssh -F /dev/null -o IdentityFile="$anahtar" -o IdentitiesOnly=yes -o BatchMode=yes \
    -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o NoHostAuthenticationForLocalhost=yes \
    -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -S none -N \
    "${forwards[@]}" -p "$port" "127.0.0.1" </dev/null >/dev/null 2>&1 &
  echo "$!" > "$pid_file"
}

tunel_ac() {
  # Colima'nın port yönlendirmesi bozulursa yeni portlar ana makineye açılmaz.
  # Bu komut sanal makineye ayrı bir ssh bağlantısı açar ve iki portu ana makineye taşır.
  # Colima'nın kendi bağlantısına dokunmaz. Yalnız bu Mac'teki Colima kurulumu için geçerlidir.
  local lima_ad="${COLIMA_LIMA_AD:-$LIMA_DEFAULT}"
  local ssh_conf="$HOME/.colima/_lima/$lima_ad/ssh.config"
  if [ ! -f "$ssh_conf" ]; then
    echo "Colima ssh ayarı yok: $ssh_conf" >&2
    exit 1
  fi
  if [ -f "$TUNEL_PID" ] && kill -0 "$(cat "$TUNEL_PID")" 2>/dev/null; then
    echo "Tünel zaten açık (pid $(cat "$TUNEL_PID"))."
    return
  fi
  ssh_tunel "$TUNEL_PID" "$KC_PORT" "$MAILPIT_UI_PORT"
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
  config)
    case "$#:${1:-}" in
      0:) compose config --no-interpolate --no-env-resolution ;;
      1:--quiet) compose config --quiet ;;
      *) echo "Usage: $0 config [--quiet]" >&2; exit 2 ;;
    esac
    ;;
  # İmaj varsa yeniden kullanılır. Realm ya da eklenti değişince imajı "build" komutuyla derleyin.
  up) compose up -d --wait "$@" ;;
  build) compose build "$@" ;;
  down) tunel_kapat; compose down "$@" ;;
  restart) compose restart "$@" ;;
  logs) compose logs "$@" ;;
  ps) compose ps "$@" ;;
  exec) compose exec "$@" ;;
  test) (cd "$KLASOR/tests" && python3 -I -m unittest discover -s . -v "$@") ;;
  tunel) tunel_ac ;;
  tunel-kapat) tunel_kapat ;;
  prod-check)
    # Merge review E1 and O7: start the "prod" image target the way production would, without the
    # development compose settings. 1) A plain HTTP event address must stop Keycloak. 2) With an HTTPS
    # address the magic link side doors are off. The containers are removed at the end.
    prod_tag="fs-keycloak-atonota:prod-$KC_PORT"
    prod_port="$((PANE_PORT + 8))"
    prod_name="${PROJE}-prod-check"
    prod_tunnel_pid="$KLASOR/.tunel-prod.pid"
    docker --context "$BAGLAM" build -q --target prod -t "$prod_tag" "$KLASOR" >/dev/null
    # Merge review O5: the secret goes to docker by variable name only, never as a value on the command line.
    export KC_SPI_EVENTS_LISTENER__WEBHOOK__SECRET="$IDENTITY_SYNC_WEBHOOK_SECRET"
    # Usage: prod_run <container name> <event URL> [extra docker run arguments...]
    prod_run() {
      local name="$1" url="$2"
      shift 2
      docker --context "$BAGLAM" run -d --name "$name" --env-file "$ENV_DOSYASI" \
        -e KC_HTTP_ENABLED=true -e KC_HOSTNAME="http://127.0.0.1:$prod_port" -e KC_HEALTH_ENABLED=true \
        -e KC_DB=dev-file -e ATONOTA_SITE_KIRACI1_URL -e ATONOTA_PRESS_URL \
        -e KC_SPI_EVENTS_LISTENER__WEBHOOK__SECRET \
        -e KC_SPI_EVENTS_LISTENER__WEBHOOK__URL="$url" "$@" "$prod_tag" start --import-realm >/dev/null
    }
    prod_cleanup() {
      docker --context "$BAGLAM" rm -f "$prod_name-http" "$prod_name" >/dev/null 2>&1 || true
      if [ -f "$prod_tunnel_pid" ]; then kill "$(cat "$prod_tunnel_pid")" 2>/dev/null || true; rm -f "$prod_tunnel_pid"; fi
    }
    trap prod_cleanup EXIT
    prod_cleanup
    prod_run "$prod_name-http" "http://identity-sync.example.test/v1/events"
    PROD_HTTP_REFUSED=no
    for _ in $(seq 1 90); do
      if [ "$(docker --context "$BAGLAM" inspect -f '{{.State.Running}}' "$prod_name-http")" = "false" ]; then
        # Read the log first: with pipefail, "grep -q" closing the pipe early would report a failure.
        prod_log="$(docker --context "$BAGLAM" logs "$prod_name-http" 2>&1)"
        if printf '%s' "$prod_log" | grep -q "webhook URL must use https"; then
          PROD_HTTP_REFUSED=yes
        fi
        break
      fi
      sleep 2
    done
    echo "Plain HTTP event address refused: $PROD_HTTP_REFUSED"
    prod_run "$prod_name" "https://identity-sync.example.test/v1/events" -p "127.0.0.1:$prod_port:8080"
    # Colima's port forwarding does not carry new ports (backend/AGENTS.md, known issue 2).
    curl -fs -o /dev/null --max-time 2 "http://127.0.0.1:$prod_port/" 2>/dev/null || ssh_tunel "$prod_tunnel_pid" "$prod_port"
    prod_ready=no
    for _ in $(seq 1 90); do
      if prod_status="$(curl -fs -o /dev/null --max-time 2 -w '%{http_code}' \
        "http://127.0.0.1:$prod_port/realms/platform")" && [ "$prod_status" = 200 ]; then
        prod_ready=yes
        break
      fi
      sleep 2
    done
    if [ "$prod_ready" != yes ]; then
      echo "Production Keycloak did not become ready." >&2
      exit 1
    fi
    (cd "$KLASOR/tests" && PROD_KC_URL="http://127.0.0.1:$prod_port" PROD_HTTP_REFUSED="$PROD_HTTP_REFUSED" \
      python3 -I -m unittest discover -s . -p 'test_production_image.py' -v "$@")
    ;;
  realm-reload)
    # Loads the realm file without an image build: the file is copied into the running container, the
    # realm is deleted and the container restarts, so --import-realm imports the file again.
    # This deletes all data of the development realm. The confirmation flag is required.
    if [ "${1:-}" != "--yes" ]; then
      echo "This deletes the platform realm and all its data. To confirm: $0 realm-reload --yes" >&2
      exit 2
    fi
    # A changed environment recreates the container first (without waiting: a broken realm file in the
    # old container must not block the fix). docker cp also works on a stopped container.
    compose up -d --no-start keycloak
    container_id="$(compose ps -a -q keycloak)"
    if [ -z "$container_id" ]; then
      echo "There is no Keycloak container. Create it first: $0 up" >&2
      exit 1
    fi
    docker --context "$BAGLAM" cp "$KLASOR/realm/platform-realm.json" "$container_id:/opt/keycloak/data/import/platform-realm.json"
    docker --context "$BAGLAM" cp "$KLASOR/realm/dev-users/platform-users-0.json" "$container_id:/opt/keycloak/data/import/platform-users-0.json"
    compose up -d --wait --no-recreate keycloak
    "$0" realm-delete-only --yes
    # The container must not be recreated: a new container would import the realm file baked into the image.
    compose restart keycloak
    compose up -d --wait --no-recreate keycloak
    ;;
  realm-delete-only)
    # Deletes the platform realm through the Admin API. The confirmation flag is required.
    [ "${1:-}" = "--yes" ] || { echo "Confirmation flag required: --yes" >&2; exit 2; }
    # The password and the admin token reach curl through a config on stdin, never on the command line.
    admin_token="$(printf 'data-urlencode = "username=%s"\ndata-urlencode = "password=%s"\n' "$KC_BOOTSTRAP_ADMIN_USERNAME" "$KC_BOOTSTRAP_ADMIN_PASSWORD" \
      | curl -fsS -K - -X POST "$KC_PUBLIC_URL/realms/master/protocol/openid-connect/token" \
      -d grant_type=password -d client_id=admin-cli | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
    printf 'header = "Authorization: Bearer %s"\n' "$admin_token" \
      | curl -fsS -K - -o /dev/null -w 'realm deleted: %{http_code}\n' -X DELETE "$KC_PUBLIC_URL/admin/realms/platform"
    ;;
  realm-sil)
    # Realm'i siler ve Keycloak'ı var olan imajla yeniden kurar. Böylece imajdaki realm dosyası yeniden içe alınır.
    # Realm dosyası değiştiyse önce "build" komutunu çalıştırın.
    # Bu komut geliştirme realm'indeki bütün veriyi siler. Onay bayrağı zorunludur.
    if [ "${1:-}" != "--evet" ]; then
      echo "Bu komut platform realm'ini ve içindeki bütün veriyi siler. Onaylamak için: $0 realm-sil --evet" >&2
      exit 2
    fi
    "$0" realm-delete-only --yes
    compose up -d --force-recreate --wait keycloak
    ;;
  *)
    echo "Kullanım: $0 <config|up|build|down|restart|logs|ps|exec|test|tunel|tunel-kapat|prod-check|realm-reload|realm-delete-only|realm-sil>" >&2
    exit 2
    ;;
esac
