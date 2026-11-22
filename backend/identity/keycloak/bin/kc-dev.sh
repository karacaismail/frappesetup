#!/usr/bin/env bash
# Keycloak geliştirme ortamını yönetir. Sahibi kimlik-realm işidir.
# Kullanım: bin/kc-dev.sh <config|build|up|down|restart|logs|ps|exec|test|realm-sil|tunel|tunel-kapat>
# Portlar PANE_PORT değişkeninden türer. Keycloak P, Mailpit ekranı P+6 portunu alır.
set -euo pipefail

KLASOR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$(cd "$KLASOR/../.." && pwd)"
COMPOSE_DOSYASI="$BACKEND/dev/compose.keycloak.yaml"
ENV_DOSYASI="$KLASOR/.env"
PROJE="${COMPOSE_PROJECT_NAME:-fs-kimlik-realm}"
# Profil FS_COLIMA_PROFILE değişkeninden seçilir (backend/AGENTS.md, "Disk dar"). Değer "default" ise colima profili kullanılır.
if [ "${FS_COLIMA_PROFILE:-factory}" = "default" ]; then
  BAGLAM="${DOCKER_CONTEXT:-colima}"
  LIMA_VARSAYILAN="colima"
else
  BAGLAM="${DOCKER_CONTEXT:-colima-factory}"
  LIMA_VARSAYILAN="colima-factory"
fi

if [ -z "${PANE_PORT:-}" ]; then
  echo "PANE_PORT boş. Örnek: PANE_PORT=5070 $0 up" >&2
  exit 2
fi

rastgele() { python3 -c 'import secrets; print(secrets.token_urlsafe(24))'; }

ornek_satiri() {
  case "$1" in
    *=degistir-*) printf '%s=%s\n' "${1%%=*}" "$(rastgele)" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

env_hazirla() {
  if [ ! -f "$ENV_DOSYASI" ]; then
    echo ".env yok. .env.example dosyasından üretiliyor." >&2
    while IFS= read -r satir; do
      ornek_satiri "$satir"
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
      ornek_satiri "$satir" >> "$ENV_DOSYASI"
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

tunel_ac() {
  # Colima'nın port yönlendirmesi bozulursa yeni portlar ana makineye açılmaz.
  # Bu komut sanal makineye ayrı bir ssh bağlantısı açar ve iki portu ana makineye taşır.
  # Colima'nın kendi bağlantısına dokunmaz. Yalnız bu Mac'teki Colima kurulumu için geçerlidir.
  local lima_ad="${COLIMA_LIMA_AD:-$LIMA_VARSAYILAN}"
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
  realm-yenile)
    # Disk dar olduğu için imaj derlenmez (backend/AGENTS.md, "Disk dar"). Realm dosyası çalışan container'a
    # kopyalanır, realm silinir ve container yeniden başlar. --import-realm dosyayı yeniden içe alır.
    # Bu komut geliştirme realm'indeki bütün veriyi siler. Onay bayrağı zorunludur.
    if [ "${1:-}" != "--evet" ]; then
      echo "Bu komut platform realm'ini ve içindeki bütün veriyi siler. Onaylamak için: $0 realm-yenile --evet" >&2
      exit 2
    fi
    # Ortam değişkeni değiştiyse container önce yeni ayarla kurulur. Kopyalama ondan sonra yapılır.
    compose up -d --wait keycloak
    kc_kimlik="$(compose ps -q keycloak)"
    if [ -z "$kc_kimlik" ]; then
      echo "Keycloak çalışmıyor. Önce: $0 up" >&2
      exit 1
    fi
    docker --context "$BAGLAM" cp "$KLASOR/realm/platform-realm.json" "$kc_kimlik:/opt/keycloak/data/import/platform-realm.json"
    docker --context "$BAGLAM" cp "$KLASOR/realm/dev-users/platform-users-0.json" "$kc_kimlik:/opt/keycloak/data/import/platform-users-0.json"
    "$0" realm-sil-yalniz --evet
    # The container must not be recreated: a new container would import the realm file baked into the image.
    compose restart keycloak
    compose up -d --wait --no-recreate keycloak
    ;;
  realm-sil-yalniz)
    [ "${1:-}" = "--evet" ] || { echo "Onay bayrağı gerekli: --evet" >&2; exit 2; }
    belirtec="$(printf 'data-urlencode = "username=%s"\ndata-urlencode = "password=%s"\n' "$KC_BOOTSTRAP_ADMIN_USERNAME" "$KC_BOOTSTRAP_ADMIN_PASSWORD" \
      | curl -fsS -K - -X POST "$KC_PUBLIC_URL/realms/master/protocol/openid-connect/token" \
      -d grant_type=password -d client_id=admin-cli | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
    printf 'header = "Authorization: Bearer %s"\n' "$belirtec" \
      | curl -fsS -K - -o /dev/null -w 'realm silindi: %{http_code}\n' -X DELETE "$KC_PUBLIC_URL/admin/realms/platform"
    ;;
  realm-sil)
    # Realm'i siler ve Keycloak'ı var olan imajla yeniden kurar. Böylece imajdaki realm dosyası yeniden içe alınır.
    # Realm dosyası değiştiyse önce "build" komutunu çalıştırın.
    # Bu komut geliştirme realm'indeki bütün veriyi siler. Onay bayrağı zorunludur.
    if [ "${1:-}" != "--evet" ]; then
      echo "Bu komut platform realm'ini ve içindeki bütün veriyi siler. Onaylamak için: $0 realm-sil --evet" >&2
      exit 2
    fi
    # Parola komut satırında görünmesin diye curl'e standart girdiden verilir.
    belirtec="$(printf 'data-urlencode = "username=%s"\ndata-urlencode = "password=%s"\n' "$KC_BOOTSTRAP_ADMIN_USERNAME" "$KC_BOOTSTRAP_ADMIN_PASSWORD" \
      | curl -fsS -K - -X POST "$KC_PUBLIC_URL/realms/master/protocol/openid-connect/token" \
      -d grant_type=password -d client_id=admin-cli | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
    # The admin token is passed through a curl config on stdin so it never appears in the process list.
    printf 'header = "Authorization: Bearer %s"\n' "$belirtec" \
      | curl -fsS -K - -o /dev/null -w 'realm silindi: %{http_code}\n' -X DELETE "$KC_PUBLIC_URL/admin/realms/platform"
    compose up -d --force-recreate --wait keycloak
    ;;
  *)
    echo "Kullanım: $0 <config|build|up|down|restart|logs|ps|exec|test|realm-sil|realm-yenile|tunel|tunel-kapat>" >&2
    exit 2
    ;;
esac
