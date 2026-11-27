#!/usr/bin/env bash
# Cloudflare istemci sertifikasını telefonun anlayacağı PKCS#12 (.p12) dosyasına
# çevirir. Cloudflare panelinden indirdiğiniz iki dosyayı kullanır:
#
#   cert.pem  → istemci sertifikası (public)
#   key.pem   → istemci özel anahtarı (yalnızca bir kez gösterilir!)
#
# Kullanım:
#   ./scripts/client_cert_to_p12.sh cert.pem key.pem tradeai-telefon.p12 "Telefon"
#
# Sonra .p12 dosyasını telefona kopyalayıp kurun (docs/CLOUDFLARE_TUNNEL.md).
# Dosyayı e-posta/mesajla göndermeyin; USB, AirDrop veya kendi dosya sunucunuzu
# kullanın. Kurulumdan sonra .p12 dosyasını bilgisayardan silin.
set -euo pipefail

CERT="${1:-cert.pem}"
KEY="${2:-key.pem}"
OUT="${3:-tradeai-client.p12}"
NAME="${4:-TradeAIBot}"

if [[ ! -f "$CERT" ]]; then
  echo "HATA: sertifika bulunamadı: $CERT" >&2
  exit 1
fi
if [[ ! -f "$KEY" ]]; then
  echo "HATA: özel anahtar bulunamadı: $KEY" >&2
  exit 1
fi
if [[ -e "$OUT" ]]; then
  echo "HATA: $OUT zaten var; üzerine yazmamak için silin veya farklı ad verin." >&2
  exit 1
fi

# Telefonlar PEM'i değil PKCS#12'yü (tek dosya + parola) kurar.
# -legacy: Android 9 ve öncesi eski şifreleme bekler; yeni Android/iOS ikisini de okur.
read -r -s -p "P12 parolası (en az 8 karakter, telefonda istenecek): " PASS
echo
read -r -s -p "Parolayı tekrar girin: " PASS2
echo
if [[ "$PASS" != "$PASS2" ]]; then
  echo "HATA: parolalar eşleşmiyor" >&2
  exit 1
fi
if [[ ${#PASS} -lt 8 ]]; then
  echo "HATA: parola en az 8 karakter olmalı" >&2
  exit 1
fi

openssl pkcs12 -export \
  -in "$CERT" \
  -inkey "$KEY" \
  -name "$NAME" \
  -out "$OUT" \
  -passout "pass:$PASS" \
  -legacy 2>/dev/null || \
openssl pkcs12 -export \
  -in "$CERT" \
  -inkey "$KEY" \
  -name "$NAME" \
  -out "$OUT" \
  -passout "pass:$PASS"

chmod 600 "$OUT"
echo
echo "Hazır: $OUT"
echo "Doğrulama (parola sorulacak):"
openssl pkcs12 -in "$OUT" -info -noout && echo "  ✓ geçerli PKCS#12"
echo
echo "Sonraki adımlar:"
echo "  1) Sertifikayı CLOUDFLARE'DE ETKİNLEŞTİRİN (SSL/TLS → Client Certificates"
echo "     → Hosts → hostname ekleyin) ve WAF kuralı sertifikasız isteği engellesin."
echo "  2) .p12 dosyasını telefona aktarıp kurun (Android: Ayarlar → Güvenlik →"
echo "     Şifreleme ve kimlik bilgileri → Sertifika yükle → VPN ve uygulama"
echo "     kullanıcı sertifikası)."
echo "  3) Tarayıcıda siteyi açın; sertifika seçimi istenirse TradeAIBot'u seçin."
echo "  4) Kurulumdan sonra .p12 dosyasını bilgisayardan SİLİN."
