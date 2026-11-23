#!/usr/bin/env bash
# Playwright sistem bağımlılıkları + tarayıcılar.
# Ölçüm (23 Kasım 2026): `playwright install --with-deps` adımı 42 sn ile 1453 sn arasında sürdü;
# süre apt ayna sunucusunun hızına bağlıydı (bir koşuda `apt-get update` 24 dk takıldı).
# Önbellek varsa .deb dosyaları ağsız kurulur; `apt-get update` hiç çalışmaz.
# Paket kümesi `--with-deps` ile aynıdır (görsel referansların yazı tipleri dahil).
set -euo pipefail

BROWSERS=(chromium firefox webkit)
DEBS="$HOME/.cache/pw-debs"
ARCHIVES=/var/cache/apt/archives

# Ağ yavaşsa beklemek yerine zaman aşımı ve yeniden deneme; indirilen paketler silinmesin.
sudo tee /etc/apt/apt.conf.d/80playwright-ci >/dev/null <<'EOF'
Acquire::Retries "5";
Acquire::http::Timeout "30";
Acquire::https::Timeout "30";
APT::Keep-Downloaded-Packages "true";
Binary::apt-get::APT::Keep-Downloaded-Packages "true";
EOF

install_from_cache() {
  shopt -s nullglob
  local files=("$DEBS"/*.deb)
  shopt -u nullglob
  ((${#files[@]})) || return 1
  echo "apt paketleri önbellekten kuruluyor (${#files[@]} dosya)"
  sudo apt-get install -y --no-install-recommends --no-download "${files[@]}"
}

install_from_network() {
  echo "apt paketleri ağdan kuruluyor"
  local before after
  before=$(mktemp)
  after=$(mktemp)
  find "$ARCHIVES" -maxdepth 1 -name '*.deb' -printf '%f\n' | sort > "$before"
  npx playwright install-deps "${BROWSERS[@]}"
  find "$ARCHIVES" -maxdepth 1 -name '*.deb' -printf '%f\n' | sort > "$after"
  # apt dosya zamanını sunucudan aldığı için zaman yerine ad listesi karşılaştırılır.
  rm -rf "$DEBS"
  mkdir -p "$DEBS"
  comm -13 "$before" "$after" | while IFS= read -r f; do cp "$ARCHIVES/$f" "$DEBS/"; done
  echo "önbelleğe alınacak paket sayısı: $(find "$DEBS" -name '*.deb' | wc -l)"
}

if [ "${DEBS_HIT:-}" = "true" ] && install_from_cache; then
  :
else
  install_from_network
fi

# Önbellekte tarayıcı varsa bu komut yalnız doğrular; yoksa indirir.
npx playwright install "${BROWSERS[@]}"
