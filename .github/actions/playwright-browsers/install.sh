#!/usr/bin/env bash
# Playwright sistem bağımlılıkları + tarayıcılar.
# Ölçüm (23 Kasım 2026): `playwright install --with-deps` adımı 42 sn ile 1453 sn arasında sürdü;
# süre apt ayna sunucusunun hızına bağlıydı (bir koşuda `apt-get update` 24 dk takıldı).
# Önbellek varsa .deb dosyaları ağsız kurulur; `apt-get update` hiç çalışmaz.
# Paket kümesi `--with-deps` ile aynıdır (görsel referansların yazı tipleri dahil): önbellek
# yalnız `playwright install-deps` komutunun indirdiği dosyalardır.
#
# 24 Kasım 2026 bulgusu (AJA-364): `apt-get install --no-download` arşiv klasörü dışındaki
# .deb dosyalarını kurmaz ("Unable to fetch some archives"). Önbellek bu yüzden hiç
# kullanılmadı; her iş ağdan kurdu. Yavaş aynaya düşen iş (234 kB/s) 20 dakikada bitmedi.
# Çözüm: dosyalar önce apt arşiv klasörüne kopyalanır, kurulum oradan yapılır.
set -euo pipefail

BROWSERS=(chromium firefox webkit)
DEBS="$HOME/.cache/pw-debs"
ARCHIVES=/var/cache/apt/archives
MIRRORS=/etc/apt/apt-mirrors.txt
# Bir ağ denemesinin süre sınırı ve deneme sayısı. İş sınırı 20 dk; testler yaklaşık 4 dk.
NET_ATTEMPT_SECONDS="${PW_APT_ATTEMPT_SECONDS:-240}"
NET_ATTEMPTS="${PW_APT_ATTEMPTS:-3}"
# Süre dolunca süreçlere önce TERM gider; bu kadar saniye sonra KILL gider.
KILL_AFTER="${PW_APT_KILL_AFTER_SECONDS:-15}"
# Yeni denemeden önce apt kilidinin bırakılması en çok bu kadar beklenir.
LOCK_WAIT="${PW_APT_LOCK_WAIT_SECONDS:-60}"
# 24 Kasım 2026 bulgusu (AJA-382): GNU `timeout` yalnız kendi süreç grubunu durdurdu.
# `sudo` komutu ayrı bir oturumda (pty) çalıştırır; içteki `apt-get` grupta değildi.
# Süre dolunca `apt-get` çalışmayı sürdürdü ve dpkg kilidini tuttu. Sonraki denemeler
# "Could not get lock /var/lib/dpkg/lock-frontend" hatasıyla hemen düştü.
# Bu yüzden süre dolunca apt ve dpkg süreçleri adlarıyla da durdurulur.
APT_PROC_PATTERN='^(/usr/bin/)?(apt-get|apt|dpkg)( |$)|^/usr/lib/apt/methods/'
APT_LOCK_FILES="/var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock /var/lib/apt/lists/lock"

# Ağ yavaşsa beklemek yerine zaman aşımı ve yeniden deneme; indirilen paketler silinmesin.
# Kesilen bir denemeden sonra dpkg kilidi için bir süre beklenir.
sudo tee /etc/apt/apt.conf.d/80playwright-ci >/dev/null <<'EOF'
Acquire::Retries "5";
Acquire::http::Timeout "30";
Acquire::https::Timeout "30";
DPkg::Lock::Timeout "120";
APT::Keep-Downloaded-Packages "true";
Binary::apt-get::APT::Keep-Downloaded-Packages "true";
EOF

list_archives() {
  find "$ARCHIVES" -maxdepth 1 -name '*.deb' -printf '%f\n' | sort
}

# Önbellekten kopyalanan ve kurulum bozulunca geri silinecek dosyalar.
COPIED=()

install_from_cache() {
  shopt -s nullglob
  local files=("$DEBS"/*.deb)
  shopt -u nullglob
  ((${#files[@]})) || return 1
  echo "apt paketleri önbellekten kuruluyor (${#files[@]} dosya)"
  local f name targets=()
  for f in "${files[@]}"; do
    name=$(basename "$f")
    if [ ! -e "$ARCHIVES/$name" ]; then
      sudo cp "$f" "$ARCHIVES/$name"
      COPIED+=("$name")
    fi
    targets+=("$ARCHIVES/$name")
  done
  # Eski sürüme inme istenirse apt -y ile durur (--allow-downgrades yok); ağdan kurulum başlar.
  sudo apt-get install -y --no-install-recommends --no-download "${targets[@]}"
}

undo_cache_copy() {
  local name
  for name in "${COPIED[@]}"; do
    sudo rm -f "$ARCHIVES/$name"
  done
  COPIED=()
  # Yarım kalan dpkg işi varsa tamamlanır; ağdan kurulum temiz durumdan başlar.
  sudo dpkg --configure -a || true
}

# Ayna listesindeki ilk aynayı sona alır. Yavaş ama yanıt veren ayna apt'ye hata
# vermez; apt bir sonraki aynaya kendiliğinden geçmez.
demote_first_mirror() {
  [ -s "$MIRRORS" ] || return 0
  local tmp
  tmp=$(mktemp)
  awk 'NF { line[++n] = $0 }
       END {
         for (i = 2; i <= n + 1; i++) {
           l = (i <= n) ? line[i] : line[1]
           sub(/priority:[0-9]+/, "priority:" (i - 1), l)
           print l
         }
       }' "$MIRRORS" > "$tmp"
  echo "apt ayna sırası değişti:"
  cat "$tmp"
  sudo cp "$tmp" "$MIRRORS"
  rm -f "$tmp"
}

# Komutu kendi süreç grubunda çalıştırır. Süre dolunca grubu durdurur ve 124 döner.
run_with_deadline() {
  local secs="$1" pid rc=0 start
  shift
  set -m
  "$@" &
  pid=$!
  set +m
  start=$SECONDS
  while kill -0 "$pid" 2>/dev/null; do
    if ((SECONDS - start >= secs)); then
      kill -TERM -- "-$pid" 2>/dev/null || true
      start=$SECONDS
      while kill -0 "$pid" 2>/dev/null && ((SECONDS - start < KILL_AFTER)); do sleep 1; done
      kill -KILL -- "-$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      return 124
    fi
    sleep 1
  done
  wait "$pid" || rc=$?
  return "$rc"
}

# Süreç grubunun dışında kalan apt ve dpkg süreçlerini durdurur.
stop_apt_processes() {
  local start
  sudo pkill -TERM -f "$APT_PROC_PATTERN" 2>/dev/null || true
  start=$SECONDS
  while pgrep -f "$APT_PROC_PATTERN" >/dev/null 2>&1 && ((SECONDS - start < KILL_AFTER)); do
    sleep 1
  done
  sudo pkill -KILL -f "$APT_PROC_PATTERN" 2>/dev/null || true
}

# apt ya da dpkg çalışıyorsa veya bir apt kilidi tutuluyorsa başarılı döner.
apt_busy() {
  local f
  pgrep -f "$APT_PROC_PATTERN" >/dev/null 2>&1 && return 0
  command -v fuser >/dev/null 2>&1 || return 1
  for f in $APT_LOCK_FILES; do
    if [ -e "$f" ] && sudo fuser "$f" >/dev/null 2>&1; then
      return 0
    fi
  done
  return 1
}

wait_for_apt_lock() {
  local start=$SECONDS
  while apt_busy; do
    if ((SECONDS - start >= LOCK_WAIT)); then
      echo "apt kilidi ${LOCK_WAIT} sn içinde bırakılmadı" >&2
      return 1
    fi
    sleep 1
  done
}

install_from_network() {
  local before="$1" after attempt rc
  echo "apt paketleri ağdan kuruluyor"
  for ((attempt = 1; attempt <= NET_ATTEMPTS; attempt++)); do
    echo "ağ denemesi $attempt/$NET_ATTEMPTS (süre sınırı ${NET_ATTEMPT_SECONDS} sn)"
    rc=0
    run_with_deadline "$NET_ATTEMPT_SECONDS" npx playwright install-deps "${BROWSERS[@]}" || rc=$?
    [ "$rc" -eq 0 ] && break
    echo "ağ denemesi $attempt başarısız (çıkış kodu $rc)"
    stop_apt_processes
    if ((attempt == NET_ATTEMPTS)); then
      echo "apt paketleri $NET_ATTEMPTS denemede kurulamadı" >&2
      return "$rc"
    fi
    wait_for_apt_lock || return 1
    # Yarım kalan kurulum varsa tamamlanır; yeni deneme temiz durumdan başlar.
    sudo dpkg --configure -a || true
    demote_first_mirror
  done
  after=$(mktemp)
  list_archives > "$after"
  # apt dosya zamanını sunucudan aldığı için zaman yerine ad listesi karşılaştırılır.
  rm -rf "$DEBS"
  mkdir -p "$DEBS"
  comm -13 "$before" "$after" | while IFS= read -r f; do cp "$ARCHIVES/$f" "$DEBS/"; done
  echo "önbelleğe alınacak paket sayısı: $(find "$DEBS" -name '*.deb' | wc -l)"
}

main() {
  local before
  before=$(mktemp)
  list_archives > "$before"
  # DEBS_HIT: "true" tam anahtar, "false" eski imajın anahtarı, boş değer önbellek yok.
  if [ -n "${DEBS_HIT:-}" ]; then
    if [ "$DEBS_HIT" != "true" ]; then
      echo "apt önbelleği tam anahtarla gelmedi; eski imajın paketleri deneniyor"
    fi
    if install_from_cache; then
      return 0
    fi
    echo "önbellekten kurulum olmadı; ağdan kurulacak"
    undo_cache_copy
  fi
  install_from_network "$before"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main
  # Önbellekte tarayıcı varsa bu komut yalnız doğrular; yoksa indirir.
  npx playwright install "${BROWSERS[@]}"
fi
