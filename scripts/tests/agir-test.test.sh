#!/usr/bin/env bash
# scripts/agir-test için testler. Testler gerçek /usr/bin/lockf ile koşar.
# Çalıştırma: bash scripts/tests/agir-test.test.sh
# Testler geçici bir kilit klasörü kullanır. Ortak kilit klasörüne dokunmaz.
set -u

KOK=$(cd "$(dirname "$0")/../.." && pwd)
BETIK="$KOK/scripts/agir-test"
GECICI=$(mktemp -d "${TMPDIR:-/tmp}/agir-test-deneme.XXXXXX")
BASARISIZ=0
GECEN=0

temizle() {
  # Testin başlattığı süreç gruplarını kapatır.
  for p in $(jobs -p); do kill -9 -- "-$p" 2>/dev/null || kill -9 "$p" 2>/dev/null; done
  rm -rf "$GECICI"
}
trap temizle EXIT
set -m  # Her arka plan işi kendi süreç grubunda koşar.

gec() { GECEN=$((GECEN + 1)); echo "geçti: $1"; }
kal() { BASARISIZ=$((BASARISIZ + 1)); echo "KALDI: $1"; }

# Ortam değişkenlerini temiz başlatır.
unset AGIR_TEST_YER GITHUB_ACTIONS CI
export AGIR_TEST_BEKLEME_SN=1

# Yardımcı komut: başladığını yazar, bırakma dosyası gelene kadar bekler.
YARDIMCI="$GECICI/is.sh"
cat > "$YARDIMCI" <<'SH'
#!/usr/bin/env bash
ad=$1; klasor=$2
echo "$$ ${AGIR_TEST_YER:-yok}" > "$klasor/basladi-$ad"
while [ ! -e "$klasor/birak-$ad" ]; do sleep 0.1; done
exit 0
SH
chmod +x "$YARDIMCI"

bekle_dosya() { # dosya, saniye
  local i=0
  while [ ! -e "$1" ] && [ "$i" -lt $(($2 * 10)) ]; do sleep 0.1; i=$((i + 1)); done
  [ -e "$1" ]
}

[ -x "$BETIK" ] || { kal "betik var ve çalıştırılabilir"; echo "Sonuç: $GECEN geçti, $BASARISIZ kaldı."; exit 1; }

# 1. Üç süreç: yalnız ikisi koşar, üçüncüsü bekler ve mesaj yazar.
T1="$GECICI/t1"; mkdir -p "$T1/kilit"
export AGIR_TEST_KILIT_KLASORU="$T1/kilit"
for ad in a b c; do
  "$BETIK" "$YARDIMCI" "$ad" "$T1" > "$T1/cikti-$ad" 2>&1 &
  echo $! > "$T1/pid-$ad"
  sleep 0.3
done
sleep 2
basl=$(ls "$T1" | grep -c '^basladi-')
[ "$basl" -eq 2 ] && gec "üç süreçten yalnız ikisi koşar" || kal "üç süreçten yalnız ikisi koşar (koşan: $basl)"
[ ! -e "$T1/basladi-c" ] && gec "üçüncü süreç bekler" || kal "üçüncü süreç bekler"
grep -q "Test sırası bekleniyor" "$T1/cikti-c" && gec "bekleyen süreç mesaj yazar" || kal "bekleyen süreç mesaj yazar"
yerler="$(cut -d' ' -f2 "$T1/basladi-a") $(cut -d' ' -f2 "$T1/basladi-b")"
[ "$yerler" = "yer-1 yer-2" ] && gec "AGIR_TEST_YER yerin adıdır" || kal "AGIR_TEST_YER yerin adıdır ($yerler)"
grep -q "pid=" "$T1/kilit/yer-1" && grep -q "basladi=" "$T1/kilit/yer-1" \
  && gec "kilit dosyasında iş bilgisi var" || kal "kilit dosyasında iş bilgisi var"

# 2. kill -9 ile ölen sürecin kilidi boşalır, bekleyen başlar.
kill -9 -- "-$(cat "$T1/pid-a")" 2>/dev/null
bekle_dosya "$T1/basladi-c" 8 && gec "kill -9 sonrası bekleyen süreç başlar" || kal "kill -9 sonrası bekleyen süreç başlar"
touch "$T1/birak-b" "$T1/birak-c"
wait "$(cat "$T1/pid-b")"; rc_b=$?
wait "$(cat "$T1/pid-c")"; rc_c=$?
[ "$rc_b" -eq 0 ] && [ "$rc_c" -eq 0 ] && gec "koşan süreçler 0 ile biter" || kal "koşan süreçler 0 ile biter ($rc_b $rc_c)"
[ -e "$T1/kilit/yer-1" ] && [ -e "$T1/kilit/yer-2" ] && gec "kilit dosyaları iş bitince silinmez" || kal "kilit dosyaları iş bitince silinmez"

# Kilit dolu tutan yardımcı: iki yeri de doldurur.
doldur() { # klasör
  for ad in x y; do
    "$BETIK" "$YARDIMCI" "$ad" "$1" > /dev/null 2>&1 &
    echo $! > "$1/pid-$ad"
  done
  bekle_dosya "$1/basladi-x" 5; bekle_dosya "$1/basladi-y" 5
}
bosalt() { touch "$1/birak-x" "$1/birak-y"; wait "$(cat "$1/pid-x")" "$(cat "$1/pid-y")" 2>/dev/null; }

# 3. GITHUB_ACTIONS=true iken kilit alınmaz. CI=1 iken alınır.
T3="$GECICI/t3"; mkdir -p "$T3/kilit"; export AGIR_TEST_KILIT_KLASORU="$T3/kilit"
doldur "$T3"
cikti=$(GITHUB_ACTIONS=true "$BETIK" sh -c 'echo "yer=${AGIR_TEST_YER:-yok}"' 2>&1)
[ "$cikti" = "yer=yok" ] && gec "GITHUB_ACTIONS=true iken komut hemen koşar" || kal "GITHUB_ACTIONS=true iken komut hemen koşar ($cikti)"
CI=1 "$BETIK" true > "$T3/cikti-ci" 2>&1 &
pid_ci=$!
sleep 1.5
if kill -0 "$pid_ci" 2>/dev/null && grep -q "Test sırası bekleniyor" "$T3/cikti-ci"; then
  gec "CI=1 iken kilit atlanmaz"
else
  kal "CI=1 iken kilit atlanmaz"
fi
kill -9 -- "-$pid_ci" 2>/dev/null; wait "$pid_ci" 2>/dev/null

# 4. AGIR_TEST_YER varken iç içe çağrı beklemez.
cikti=$(AGIR_TEST_YER=yer-1 "$BETIK" sh -c 'echo "yer=$AGIR_TEST_YER"' 2>&1)
[ "$cikti" = "yer=yer-1" ] && gec "AGIR_TEST_YER varken iç içe çağrı beklemez" || kal "AGIR_TEST_YER varken iç içe çağrı beklemez ($cikti)"
bosalt "$T3"

# 5. Çıkış kodu aynen döner. 75 "yer dolu" sanılmaz.
T5="$GECICI/t5"; mkdir -p "$T5/kilit"; export AGIR_TEST_KILIT_KLASORU="$T5/kilit"
"$BETIK" sh -c 'echo kostu >> "$1"; exit 75' _ "$T5/sayac" > "$T5/cikti" 2>&1; rc=$?
[ "$rc" -eq 75 ] && gec "test 75 ile biterse betik 75 döner" || kal "test 75 ile biterse betik 75 döner ($rc)"
[ "$(wc -l < "$T5/sayac" | tr -d ' ')" = 1 ] && ! grep -q "bekleniyor" "$T5/cikti" \
  && gec "75 kodu yer dolu sanılmaz" || kal "75 kodu yer dolu sanılmaz"
"$BETIK" sh -c 'exit 3'; rc=$?
[ "$rc" -eq 3 ] && gec "başka çıkış kodu aynen döner" || kal "başka çıkış kodu aynen döner ($rc)"
"$BETIK" true; rc=$?
[ "$rc" -eq 0 ] && gec "başarılı komut 0 döner" || kal "başarılı komut 0 döner ($rc)"

# 6. Kilit klasörü HOME değişkenine bakmaz.
grep -q 'id -un' "$BETIK" && ! grep -Eq '\$HOME|\$\{HOME' "$BETIK" \
  && gec "klasör kullanıcı adından bulunur" || kal "klasör kullanıcı adından bulunur"

echo "Sonuç: $GECEN geçti, $BASARISIZ kaldı."
[ "$BASARISIZ" -eq 0 ]
