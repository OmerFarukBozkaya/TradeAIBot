# Cloudflare Tunnel + backend erişim kapısı (cihaz anahtarı)

Amaç: TradeAIBot paneline **dış ağdan yalnızca yetkili cihazlardan** erişmek.
Anahtar (ya da sertifika) yoksa kişi **hiçbir sayfayı göremez** ve Türkçe
"Buraya erişim yetkiniz yok" uyarısı alır.

İki yol var; **A) cihaz anahtarı** Cloudflare'de hiçbir kural gerektirmez ve
önerilen yoldur:

| | Cloudflare ayarı | Telefonda gereken | Engellenen |
|---|---|---|---|
| **A. Cihaz anahtarı** (önerilen) | **Yok** | Bir kez `tk_...` yazmak | Anahtarsız her istek (sayfa + API) |
| B. İstemci sertifikası | 1 Transform Rule | `.p12` kurulumu | Sertifikasız istek |

Kurulum sırası: tüneli kur → `.env`'de kapıyı aç → **yerel ağda** anahtarı
oluştur → telefonda bir kez gir.

> **Neden A?** Cloudflare Tunnel TLS'i edge'de bitirir; uygulamaya istek
> sertifikasız HTTP olarak ulaşır. Yani backend, "sertifika var mıydı?"
> bilgisini **tek başına göremez**. Anahtar ise her istekte sunucuda
> doğrulanabildiği için Cloudflare'de hiçbir ayar gerekmez.

---

## 1. Seçeneklerin karşılaştırması

| Yöntem | Plan | Not |
|---|---|---|
| **Backend cihaz anahtarı** | Ücretsiz, **Cloudflare ayarı yok** | Bu rehberin A yolu; sunucu tarafında anahtar doğrulanır |
| **Zone-level Client Certificates** (SSL/TLS → Client Certificates) | Ücretsiz (100 sertifika) | Sertifika Cloudflare'de üretilir; backend'in görmesi için ayrıca **Transform Rule** gerekir (B yolu) |
| Access mTLS (Zero Trust → Service credentials) | **Ücretli** | Ücretsiz planda yok |
| Cloudflare Access (e-posta OTP) | Ücretsiz (50 kullanıcı) | İsteğe bağlı ikinci katman (10. adım) |

**Ek katman:** A yolunun üzerine Access e-posta OTP eklenebilir →
"anahtar + tek kullanımlık kod + panel şifresi".

---

## 2. Mimari

```
Telefon (cihaz anahtarı çerezi)
      │  HTTPS
      ▼
Cloudflare edge  (yalnız TLS; erişim kararı origin'de verilir)
      │  Tunnel (dışa giden bağlantı, port açılmaz)
      ▼
cloudflared konteyneri
      │  http://tradeai:8089 (docker iç ağı)
      ▼
TradeAIBot ── erişim kapısı: anahtar yoksa 403 + "erişim yetkiniz yok"
           └─ geçerliyse giriş ekranı + oturum çerezi (ikinci katman)
```

- Modem/router'da **port yönlendirme yok**, dış IP'de **açık port yok**.
- Tunnel yalnızca **dışa** bağlantı kurar.
- Anahtar + panel şifresi birlikte gerekir: anahtar çalınsa bile şifre
  olmadan giriş yapılamaz.
- Yerel ağ (`192.168.x`) erişimi kapıdan muaftır; evde normal çalışır.

---

## 3. Cloudflare Tunnel oluşturma

1. Cloudflare paneli → **Zero Trust** → **Networks** → **Tunnels** →
   **Create a tunnel** → **Cloudflared**.
2. Tünele ad verin (ör. `tradeai`). Kurulum ekranında **token**'ı kopyalayın
   (`eyJhIjoi...` ile başlar). Token'ı kimseyle paylaşmayın; repoya yazmayın.
3. **Public Hostname** ekleyin:
   - Subdomain: `tradeai`
   - Domain: kendi alan adınız (ör. `studiowl.com.tr`)
   - Service: **HTTP** → `tradeai:<TRADEAI_PORT>`
     (`.env` içindeki `TRADEAI_PORT`; bu sunucuda **8089**, varsayılan 8080.
     Konteyner içi porttur, dışarıya publish edilen port değil.)
   - (Ek ayar gerekmez; TLS'i Cloudflare sonlandırır.)
4. Kaydedin. Tünel "Inactive" görünür; konteyner başlayınca "Healthy" olur.

> Origin'e `https` ile gitmek istemiyorsanız HTTP doğrudur; trafik zaten
> Cloudflare ile sizin sunucunuz arasındaki şifreli tünelden geçer.

---

## 4. Sunucuda tunnel'ı başlatma

Tunnel **aynı `docker-compose.yml`** içinde, `tunnel` profiliyle tanımlı.
Profil verilmezse başlamaz (varsayılan kurulum değişmez).

```bash
cd ~/TradeAIBot

# .env içine token (yalnız sunucuda, git'e girmesin)
grep -q '^TUNNEL_TOKEN=' .env 2>/dev/null || echo 'TUNNEL_TOKEN=' >> .env
# sonra .env dosyasını düzenleyip token'ı yapıştırın:
nano .env

# yalnız panel + tunnel
docker compose --profile tunnel up -d

# AI da açıksa ikisini birlikte
docker compose --profile ai --profile tunnel up -d

docker logs -f tradeai-tunnel     # "Registered tunnel connection" görmelisiniz
```

Tunnel'ı kapatmak (panel yerel ağda çalışmaya devam eder):

```bash
docker compose --profile tunnel stop cloudflared
```

Kontrol (kapı henüz kapalıyken):

```bash
curl -sI https://tradeai.studiowl.com.tr | head -5   # 200: henüz kapı yok
```

> **Sıra önemli:** Hostname açıldığı anda site dışarıya erişilebilir olur.
> Hemen 6. adımdaki kapıyı açın; sonra yerel ağdan anahtar üretin. Arada
> panelde canlı işlem anahtarını kapalı tutun.

Bu sunucuya özel not: `.env` içinde `TRADEAI_PORT=8089` olduğu için tunnel
hedefi `http://tradeai:8089` olur ve panel dışarıdan `https://tradeai.studiowl.com.tr`
adresinde, publish edilen 8089 portundan bağımsız çalışır.

---

## 5. (B yolu, isteğe bağlı) İstemci sertifikası oluşturma

> **A yolunu (cihaz anahtarı) kullanacaksan bu bölümü atla.** Sertifika
> yöntemi yalnızca 6-B'yi kuracaksan gerekir.

1. Cloudflare paneli → alan adınız → **SSL/TLS** → **Client Certificates**.
2. **Create Client Certificate**:
   - **Use Cloudflare generated key pair** seçin (en kolay; anahtarı siz
     saklamak zorunda kalmazsınız).
   - Common Name: `telefon-omer` gibi tanınır bir ad (cihaz bazlı seçin).
   - Validity: 10 yıl (mobil için pratiktir; yine de yılda bir yenilemek iyi
     olur).
3. **Create** → açılan ekranda **certificate (PEM)** ve **private key**'i
   indirin. **Özel anahtar yalnızca bu ekranda gösterilir**; kaybolursa yeni
   sertifika üretmeniz gerekir.
4. **Hosts** bölümü → **Edit** → `tradeai.studiowl.com.tr` ekleyin.
   **Bu adım zorunlu:** Cloudflare'e "bu hostname'de istemci sertifikası
   doğrula" der.
   Aynı sayfada **Create mTLS Rule** düğmesi de bu adımdan sonra işe yarar.

> Her cihaz için ayrı sertifika üretin (`telefon-omer`, `ipad-omer`…). Telefon
> kaybolursa yalnız o sertifikayı **Revoke** edersiniz; diğerleri çalışmaya
> devam eder.

### Sertifikayı telefona uygun formata çevirme

Telefonlar PEM değil **PKCS#12 (.p12)** kurar. Repodaki betik bunu yapar:

```bash
# Linux/macOS/WSL
./scripts/client_cert_to_p12.sh cert.pem key.pem tradeai-telefon.p12 "Telefon"
# Windows PowerShell alternatifi:
#   openssl pkcs12 -export -in cert.pem -inkey key.pem -name "Telefon" -out tradeai-telefon.p12
```

Betik parola sorar (en az 8 karakter). Bu parola telefonda kurulum sırasında
istenir.

> **Aktarım güvenliği:** `.p12` dosyasını e-posta/WhatsApp ile göndermeyin.
> USB kablosu, AirDrop veya kendi yerel dosya paylaşımınızı kullanın.
> Kurulumdan sonra bilgisayardaki `.p12`, `cert.pem`, `key.pem` dosyalarını
> silin (sertifika telefondadır; yeniden gerekirse panelden yeni üretin).

---

## 6. Erişimi backend'de kısıtlama (Cloudflare'de kural **gerekmez**)

### Önce net olalım: sertifika backend'de görülemez

Cloudflare Tunnel TLS'i **edge'de** sonlandırır. Uygulamaya istek `http://` ve
sertifikasız olarak ulaşır; ``request.client`` sertifikası diye bir bilgi
yoktur. Yani **Cloudflare'de hiçbir ayar yapmadan** "sertifikası olmayanı
engelle" teknik olarak mümkün değildir — sunucu, sertifika verilip
verilmediğini göremez.

İki gerçek seçenek var:

| Yol | Cloudflare ayarı | Ne engellenir |
|---|---|---|
| **A. Cihaz anahtarı (önerilen)** | **Hiçbiri** | Anahtarı olmayan her istek: panel, API, statik dosya — hepsi |
| B. Sertifika başlığı | 1 Transform Rule | Sertifikasız istek (Cloudflare yine doğrular) |

A yolu senin istediğin şeyi yapar: dış ağdan gelen, anahtarı olmayan cihaz
**hiçbir sayfaya ulaşamaz** ve Türkçe "Buraya erişim yetkiniz yok" sayfası
görür. Cloudflare'de WAF/Security rule, Client Certificate, Hosts — hiçbiri
gerekmez.

---

### A. Cihaz anahtarı (Cloudflare'de ayar yok)

Kapı **yalnızca senin hostname'inde** çalışır; başka siteler etkilenmez.
Yerel ağ erişimi bozulmaz.

**1) `.env`:**

```env
REMOTE_ACCESS_MODE=key
REMOTE_ACCESS_HOST=tradeai.studiowl.com.tr
REMOTE_ALLOW_LAN=true
```

**2) Yeniden başlat:**

```bash
docker compose --profile tunnel up -d
```

**3) Yerel ağdan anahtar oluştur** (telefon değil, evdeki bilgisayar):

1. `http://192.168.1.100:8089` ile panele gir (normal şifrenle).
2. Tarayıcıda `http://192.168.1.100:8089/setup/device` adresini aç.
3. Cihaz adı yaz (ör. `Telefon`) → **Yeni anahtar oluştur**.
4. Ekranda `tk_...` ile başlayan anahtar **yalnızca bir kez** görünür.
   Kopyala (bu sayfa dış ağdan açılamaz; güvenlik gereği).

**4) Telefonda bir kez gir:**

1. Dış ağdayken `https://tradeai.studiowl.com.tr` aç → "Buraya erişim
   yetkiniz yok" sayfası gelir (beklenen davranış).
2. Sayfadaki **"Cihaz anahtarı ile giriş yap"** bağlantısına dokun
   (`/device-login`).
3. `tk_...` anahtarını yapıştır → **Giriş yap**.
4. Anahtar telefonda **1 yıl** hatırlanır (HttpOnly çerez). Artık doğrudan
   panel açılır; sonra normal kullanıcı adı/şifre ile oturum açarsın.

**5) Kontrol:**

```bash
# Anahtarsız → 403 + "erişim yetkiniz yok"
curl -s https://tradeai.studiowl.com.tr | grep -o "erişim yetkiniz yok"

# Anahtarla → 200
curl -sI https://tradeai.studiowl.com.tr -H "X-Device-Key: tk_..."
```

> **API istemcileri** için anahtar `X-Device-Key: tk_...` başlığıyla da
> gönderilebilir.

**Anahtar yönetimi** (`/setup/device`, yalnız yerel ağ):

- Her cihaz için ayrı anahtar → telefon kaybolursa yalnız onu **İptal et**.
- İptal anında geçersiz olur (her istekte veritabanından doğrulanır).
- Anahtarlar **yalnızca SHA-256 özeti** olarak saklanır; ham anahtar DB'de yok.
- Son kullanım zamanı ve IP kaydedilir; panelde görünür.
- 10 hatalı denemeden sonra o IP 5 dakika kilitlenir.
- Engellenen istekler olay kaydına yazılır (IP dakikada en fazla 1 satır).

**Kapı neyi engeller:** `/`, `/static/*`, tüm `/api/*` (sağlık kontrolü ve
`/device-login` hariç). Yani anahtarsız biri HTML'i de, API'yi de göremez.

---

### B. Sertifika başlığı (1 Cloudflare Transform Rule)

Sertifikayı **Cloudflare'in doğrulamasını** ve sonucu bir başlıkla uygulamaya
iletmesini istiyorsan (WAF kuralı değil, Transform Rule):

1. **SSL/TLS → Client Certificates** → `Create Client Certificate` → **Hosts**
   bölümüne `tradeai.studiowl.com.tr` ekle.
2. **Rules → Transform Rules → Modify Request Header** → **Create rule**:
   - Rule name: `TradeAI cert header`
   - If: `http.host eq "tradeai.studiowl.com.tr"`
   - Then: **Set static** header `cf-client-cert-verified` = `true`
     *(dinamik değer gerekiyorsa `cf.tls_client_auth.cert_verified` alanını
     dinamik olarak ata)*
3. `.env`:

```env
REMOTE_ACCESS_MODE=cert-or-key
REMOTE_ACCESS_HOST=tradeai.studiowl.com.tr
REMOTE_CERT_HEADER=cf-client-cert-verified
```

4. Yeniden başlat. Sertifikasız istek artık backend'de 403 alır.

> **Dürüst uyarı:** Bu yolda başlığı Cloudflare yazdığı için, yalnızca
> doğrulanmış sertifikada `true` yazdığından emin olmak **senin**
> sorumluluğundadır. Ayrıca başlık adı tahmin edilebilir; origin'e doğrudan
> erişim kapalı olmalı (port yönlendirme yok). Bu yüzden A yolu daha
> dayanıklıdır: anahtar sırsızdır ve her istekte doğrulanır.


---

## 7. Telefona erişim

### A yolu (cihaz anahtarı) — en basit

1. Evdeki ağda `http://192.168.1.100:8089/setup/device` adresini aç, `Telefon`
   adıyla anahtar oluştur, `tk_...` değerini kopyala.
2. Telefonda `https://tradeai.studiowl.com.tr/device-login` aç, anahtarı yaz.
3. Bitti — anahtar 1 yıl hatırlanır. Uygulama kurulumu gerekmez.

> Anahtarı kimseyle paylaşma. Telefon değişirse yeni anahtar oluştur, eskisini
> `/setup/device` sayfasından iptal et.

### B yolu (istemci sertifikası)

Yalnızca 6-B'yi kurduysan gerekir.

#### Android (Chrome)

1. `.p12` dosyasını telefona kopyalayın.
2. **Ayarlar** → **Güvenlik** (bazı modellerde *Şifreleme ve kimlik bilgileri*)
   → **Sertifika yükle** → **VPN ve uygulama kullanıcı sertifikası**.
   *(Sadece "CA sertifikası" seçmeyin; o sunucu sertifikaları içindir ve
   istemci kimliği olarak çalışmaz.)*
3. Dosyayı seçin, `.p12` parolasını girin, sertifikaya ad verin.
4. Chrome'da `https://tradeai.studiowl.com.tr` açın. Sertifika seçimi sorulursa
   `Telefon` sertifikasını seçin. (İlk seferde "her zaman kullan" seçeneği
   varsa işaretleyin.)

#### iPhone / iPad (Safari)

1. `.p12` dosyasını AirDrop veya Dosyalar ile cihaza aktarın, dokunup
   **Yükle** deyin (parolayı girin).
2. **Ayarlar** → **Genel** → **VPN ve Cihaz Yönetimi** → profili **Yükle**.
3. Safari'de siteyi açın; istemci sertifikası otomatik sunulur.
   *(İstemci sertifikası için "Sertifika Güven Ayarları" gerekmez; o ayar
   yalnızca **CA/root** güveni içindir.)*

#### Masaüstü tarayıcı (isteğe bağlı)

- Chrome/Edge: `Ayarlar → Gizlilik ve güvenlik → Güvenlik → Sertifikaları
  yönet → Kişisel → İçe aktar` (.p12).
- Firefox kendi deposunu kullanır: `Ayarlar → Gizlilik → Sertifikaları gör`.

---

## 8. İlk giriş ve panel ayarları

Erişim kapısı kurulduktan sonra:

1. Panelde güçlü bir **ADMIN_PASSWORD** olduğundan emin olun
   (`Ayarlar → Güvenlik`'ten değiştirilebilir).
2. `.env` içinde:

```env
REMOTE_ACCESS_MODE=key                        # veya cert-or-key
REMOTE_ACCESS_HOST=tradeai.studiowl.com.tr
REMOTE_ALLOW_LAN=true
TRADEAI_COOKIE_SECURE=true      # HTTPS'te çerezi Secure yapar (otomatik tespit de var)
TRADEAI_TRUST_PROXY=true        # Cloudflare/nginx başlıklarına güven
TRADEAI_BIND=192.168.1.100      # yalnız yerel ağ arayüzü (aşağıya bakın)
```

3. `docker compose --profile tunnel up -d` ile yeniden başlatın (tunnel
   kullanıyorsanız; yalnız panel için `docker compose up -d`).

> **Önemli:** Uygulama `X-Forwarded-Proto: https` gördüğünde çerezi otomatik
> `Secure` işaretler ve HSTS gönderir. Yine de `TRADEAI_COOKIE_SECURE=true`
> açık bırakmak, yapılandırma hatasına karşı ek güvencedir. Yerel ağda HTTP ile
> girerken Secure çerez gönderilmez; bu yüzden yerel erişimde `http://192.168.1.100:8089`
> kullanmaya devam edebilirsiniz (oturum ayrı çerez adıyla tutulur).

---

## 9. Sıkılaştırma kontrol listesi

- [ ] **Port yönlendirme yok.** Modemde 8080/8089 için forward/UPnP kapatın.
      Dış IP'den `http://<ip>:8089` erişilemediğini doğrulayın.
- [ ] **Docker portu yerel ağa bağlı.** `TRADEAI_BIND=192.168.1.100`
      (veya `127.0.0.1`; o zaman LAN'dan giremezsiniz, tunnel çalışmaya devam
      eder çünkü cloudflared docker iç ağından bağlanır).
- [ ] **Erişim kapısı aktif** ve test edildi: anahtarsız/sertifikasız istek 403
      ve "erişim yetkiniz yok" sayfası.
- [ ] **Anahtar/sertifika cihaz bazlı**; kaybolan cihazın anahtarı **İptal**.
- [ ] **`REMOTE_ACCESS_HOST`** yalnız senin hostname'ini içeriyor (başka
      siteler kilitlenmesin).
- [ ] **Tunnel token'ı** yalnız `.env`'de, dosya izni `chmod 600 .env`,
      git'e eklenmemiş (`.gitignore` kontrol).
- [ ] **Canlı işlem** yalnız gerektiğinde açık; dışarıdayken kapalı tutun.
- [ ] **Yedek**: `Data/` ve `.env` şifreli yedekte; anahtar yeniden
      üretilebilir ama DB geri dönmez.
- [ ] **Güncelleme**: `cloudflared` imajını ara ara `pull` edin.
- [ ] **Olay kaydı**: panelde `Uzaktan erişim engellendi` satırlarını ara ara
      gözden geçirin (`/api/events`).

---

## 10. İki faktör daha (isteğe bağlı, ücretsiz)

Anahtar (ya da sertifika) + şifre yeterli değilse Cloudflare Access ekleyin
(50 kullanıcıya kadar ücretsiz):

1. **Zero Trust → Access → Applications → Add self-hosted**.
2. Hostname: `tradeai.studiowl.com.tr`.
3. Policy: **Allow** → Include → **Emails** → yalnız kendi e-posta adresiniz.
4. Login method: **One-time PIN** (e-posta ile kod).
5. Uygulamayı kaydedin.

Artık sıra: cihaz anahtarı/sertifika → e-posta kodu → panel şifresi.
Telefonda kod için e-posta uygulamanız açık olmalı.

---

## 11. Anahtar / sertifika yenileme ve iptal

### A yolu (cihaz anahtarı)

- **Yenileme:** `/setup/device` → yeni anahtar oluştur → telefonda
  `/device-login`'de bir kez gir → eskisini **İptal et**.
- **Cihaz kaybı:** listede ilgili anahtarın **İptal et** düğmesi. Etki
  **anında**: her istekte veritabanından doğrulandığı için o cihaz bir daha
  giremez.
- **Tümünü kilitle:** tüm anahtarları iptal et. Yerel ağdan yeni anahtar
  üretebilirsin.

### B yolu (istemci sertifikası)

- **Yenileme:** SSL/TLS → Client Certificates → yeni sertifika → Hosts'ta
  değiştirmeye gerek yok (aynı hostname) → yeni `.p12`'yi telefona kur →
  eskiyi **Revoke**.
- **Cihaz kaybı:** ilgili sertifikayı **Revoke** edin. Cloudflare bir sonraki
  TLS el sıkışmasında reddeder; backend de `cert_verified` başlığı `false`
  olduğu için isteği engeller.

### Genel

- **Tüm erişimi kapatmak:** tunnel'ı durdurun
  (`docker compose --profile tunnel stop cloudflared`) veya
  `REMOTE_ACCESS_MODE=off` yapıp yeniden başlatın.
- **Yalnız bir hostname'i kilitlemek:** `REMOTE_ACCESS_HOST` listesinden çıkarın
  (diğer siteler etkilenmez).

---

## 12. Sorun giderme

| Belirti | Olası neden / çözüm |
|---|---|
| `1033 Argo Tunnel error` | cloudflared çalışmıyor: `docker logs tradeai-tunnel`; token doğru mu? |
| Dış ağda herkes giriyor | `REMOTE_ACCESS_MODE` hâlâ `off` ya da `REMOTE_ACCESS_HOST` boş. `.env`'i düzeltip yeniden başlat. |
| Yerel ağda da "erişim yetkiniz yok" | `REMOTE_ALLOW_LAN=false` olabilir ya da istek `cf-ray` başlığıyla geliyor (tünel üzerinden). LAN'dan doğrudan `http://192.168.1.100:8089` kullan. |
| `/setup/device` "yalnızca yerel ağda açılabilir" diyor | Dış ağdan/tünel üzerinden açılmış. Evdeki ağdan dene. |
| `/setup/device` giriş ekranına atıyor | Panelde oturum yok. Önce normal şifreyle panele gir, sonra bu adresi aç. |
| Anahtarı girdim ama yine engelliyor | Anahtar iptal edilmiş ya da `.env`'de farklı hostname var. `/setup/device` listesinden kontrol et. |
| "Çok fazla deneme" | 10 hatalı denemeden sonra IP 5 dk kilitlenir; bekle veya sunucuyu yeniden başlat. |
| Girişte sürekli login ekranı | Çerez `Secure` ama HTTP kullanılıyor ya da `X-Forwarded-Proto` yok; `TRADEAI_TRUST_PROXY=true` ve HTTPS URL kullanın. |
| B yolu: `cf.tls_client_auth` alanı listede yok | **Hosts** eklemesi eksik (5. adım). Ekleyip sayfayı yenileyin. |
| B yolu: sertifika soruluyor ama 403 | Yanlış sertifika seçildi/süresi geçmiş; `curl --cert/--key` ile test edin. |

---

## 13. Test komutları (özet)

**A yolu (cihaz anahtarı):**

```bash
# 1) Anahtarsız → 403 + "erişim yetkiniz yok"
curl -s https://tradeai.studiowl.com.tr | grep -o "erişim yetkiniz yok"

# 2) API de kapalı olmalı
curl -s -o /dev/null -w "%{http_code}\n" https://tradeai.studiowl.com.tr/api/bots   # 403

# 3) Anahtarla → 200
curl -sI https://tradeai.studiowl.com.tr -H "X-Device-Key: tk_..." | head -1

# 4) Sağlık kontrolü muaf
curl -s https://tradeai.studiowl.com.tr/api/health                                  # {"ok":true...}

# 5) Doğrudan origin erişilememeli (LAN dışından)
curl -m 5 http://<sunucu-dış-ip>:8089/ || echo "dışarıdan erişim yok (doğru)"

# 6) Tunnel sağlığı
docker logs --tail 20 tradeai-tunnel
```

**B yolu (sertifika):**

```bash
curl -sI https://tradeai.studiowl.com.tr | head -1                                # 403
curl -sI https://tradeai.studiowl.com.tr --cert cert.pem --key key.pem | head -1  # 200
```

Bu kontroller geçiyorsa dış ağdan **yalnızca yetkili cihaz** girebilir; diğerleri
"Buraya erişim yetkiniz yok" sayfasını görür ve hiçbir veriye ulaşamaz.
