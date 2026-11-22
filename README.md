# TradeAIBot

Kripto para analizi, backtest, tarama ve otomatik alım-satım için **web arayüzünden yönetilen** bot platformu.

- Docker Compose ile tek komutta çalışır.
- Botları web'den başlatır, durdurur ve canlı izler.
- Stratejileri kod yazmadan, görsel kural oluşturucuyla tanımlar.
- Varsayılan olarak **test (paper)** modunda çalışır; canlı işlem tek bir aç/kapat anahtarıyla yönetilir.
- Grafikli dashboard: kümülatif K/Z, kazanma oranı, günlük K/Z, mod dağılımı ve bot bazlı sparkline'lar.
- İşlemler ve sinyaller SQLite ledger'ında tutulur; hesap sonuçları izlenebilir.
- Tmux, systemd, Redis veya Node.js gerekmez.

---

## Hızlı Başlangıç (Docker)

1. Ortam dosyasını oluşturun:

   ```bash
   cp .env.example .env
   ```

2. `.env` içinde en az şunları düzenleyin:

   ```env
   ADMIN_USER=admin
   ADMIN_PASSWORD=guclu-bir-sifre
   ```

3. Başlatın:

   ```bash
   docker compose up -d --build
   ```

4. Tarayıcıda açın: <http://localhost:8080> (portu değiştirdiyseniz
   `.env` içindeki `TRADEAI_PORT` değerini kullanın, ör. <http://localhost:8089>).
   Aynı yerel ağdaki başka cihazlardan `http://<bu-makinenin-ip-adresi>:<port>`
   ile erişebilirsiniz (ör. <http://192.168.1.21:8090>).

5. İlk girişten sonra **Ayarlar → Şifre değiştir** ile şifreyi güncelleyin.

> Port **`.env` → `TRADEAI_PORT`** ile belirlenir (varsayılan `8080`). Hem container
> içindeki uvicorn hem host port eşlemesi bu değeri kullanır; değiştirdikten sonra
> `docker compose up -d` yeterlidir (yeniden derleme gerekmez).
>
> Yayın adresi **`.env` → `TRADEAI_BIND`** ile belirlenir. Varsayılan **`0.0.0.0`**
> tüm ağ arayüzlerini dinler; yani panel yerel ağdaki telefon/tablet/diğer
> bilgisayarlardan erişilebilir. Yalnızca bu makineden erişmek için
> `TRADEAI_BIND=127.0.0.1` yapın.
>
> **Güvenlik:** panel HTTP (şifresiz) çalışır. Güvenilmeyen ağlara (kafe Wi-Fi,
> misafir ağı) açmayın; internetten erişim için VPN veya HTTPS'li ters proxy
> kullanın. Windows'ta ilk erişimde güvenlik duvarı izni gerekebilir:
>
> ```powershell
> New-NetFirewallRule -DisplayName "TradeAIBot 8090" -Direction Inbound `
>   -Protocol TCP -LocalPort 8090 -Action Allow -Profile Private
> ```

> **Aynı tarayıcıda iki panel** (ör. remote `localhost:8089` + yerel `localhost:8080`)
> açacaksanız: tarayıcı çerezleri **port ayrımı yapmaz**, aynı adlı çerez ikinci
> girişte birincinin üzerine yazılır ve iki panel birbirinin oturumunu düşürür.
> Çözüm: ya panelleri farklı ana makine adlarıyla açın (`http://127.0.0.1:8080` ve
> `http://localhost:8089`), ya da her örneğe `.env` içinde farklı çerez adı verin:
>
> ```bash
> TRADEAI_COOKIE_NAME=tradeai_remote   # uzak sunucuda
> ```
>
> Değişiklikten sonra `docker compose up -d` (yeniden derleme gerekmez). Giriş
> yapmış oturumlar yeni çerez adıyla bir kez yeniden giriş ister.

### Çoklu varlık: altın, gümüş, hisse ve TEFAS (yalnızca test)

Backtest, tarama, analiz ve AI eğitimi artık Binance kripto dışındaki
varlıklarla da çalışır. **Canlı/paper bot işlemleri yalnızca Binance kripto
sembolleriyle sınırlıdır**; bu varlıklar gerçek emir göndermez.

| Varlık | Sembol örneği | Kaynak | Sınır |
|---|---|---|---|
| Kripto | `BTCUSDT` | Binance | Tüm Binance geçmişi |
| Altın | `XAUUSD` | Yahoo `GC=F` | Günlükde on yıllar |
| Gümüş | `XAGUSD` | Yahoo `SI=F` | Günlükde on yıllar |
| ABD hissesi | `AAPL`, `MSFT` | Yahoo | Günlükde on yıllar |
| BIST hissesi | `GARAN.IS`, `THYAO.IS` | Yahoo | Günlükde on yıllar |
| TEFAS fonu | `TEFAS:AFT` | TEFAS | Günlük, en fazla 5 yıl |

Arayüzde her formda **Varlık** ve **Sembol** ayrı seçilir. Sembol alanının
yanındaki **Ara** düğmesi arama penceresini açar:

- Sembol kodu veya şirket/fon adı ile arar (`garanti`, `altın`, `AFT`, `bitcoin`).
- Sonuçlar varlık sınıfına göre filtrelenebilir; her satırda **canlı/test**
  etiketi ve sağlayıcı bilgisi görünür.
- Yazarken öneri listesi açılır; Enter ilk öneriyi seçer.
- Tarama ve piyasa analizinde **Ekle** ile birden çok sembol listeye eklenir.

Periyot alanına `45m`, `2h`, `3d`, `1w`, `1M`, `1y` gibi serbest değer yazılabilir:

- Kaynak periyodu istenenden küçükse veri otomatik yeniden örneklenir
  (open=ilk, high=max, low=min, close=son, hacim=toplam).
- Kaynak periyodu istenenden büyükse açık hata verilir.
- Yahoo intraday geçmişi sınırlıdır (1m ~7 gün, 5-30m ~60 gün, 1h ~730 gün).
- TEFAS yalnızca günlük NAV verir; `open=high=low=close`, hacim 0 kabul edilir.
  High/low/hacim kullanan stratejilerde sonuçlar yanıltıcı olabilir.

Veriler `Data/market/<sağlayıcı>/<sembol>/<periyot>.csv` altında önbelleklenir.
Ağ hatasında son önbellek kullanılır. API:

- `GET /api/market/symbols` — hazır sembol kataloğu ve periyotlar
- `GET /api/market/history?symbol=XAUUSD&period=1d&limit=3000` — veri önizleme
  ve kalite raporu
- `POST /api/market/cache/clear` — önbelleği temizle

### AI eğitimi (dashboard)

AI modeli eğitimi **panelden** yapılır: `AI Eğitimi` sekmesi. Önerilen yol tek
anahtardır:

**Otomatik öğrenme** → coin, periyot, öğrenme tarzı (Temkinli / Dengeli / Agresif)
ve kaç saatte bir çalışacağını seç → anahtarı aç → **Şimdi öğren** ile ilk turu başlat.

**Modeli eğit** düğmesi tek karar noktasıdır: tüm ayarlar tek kartta toplanmıştır.
Model, **Local_Min_Max'ın dip/zirve noktalarına yaklaşmayı** ve **al-tut'u geçmeyi**
hedefler. Sistem birkaç mimariyi validation uyumuyla dener, en iyisini tam eğitimle
doğrular ve aynı modeli yerinde günceller. Adaylar daha iyi değilse mevcut model
korunur; bu bir hata değildir. Eski ayrıntılı ekranlar “Uzman ayarları” altına taşındı.
Ayrıntı: `LOCAL_MIN_MAX_HEDEFI.md`.

> Docker'da eğitim hızı için BLAS/OpenMP iş parçacıkları varsayılan **2** ile
> sınırlanır (`TRADEAI_THREADS`). Aksi halde düşük CPU kotasında kütüphaneler
> birbirini ezerek eğitimi dakikalarca uzatabiliyor.

**Nesiller boyu eğit** düğmesi, seçilen sayıda nesli art arda eğitir. Her nesil
önceki modelin ağırlıklarından **sıcak başlangıç** yapar; seçim validation
skoruyla, test ise yalnızca seçilen nesil için bir kez çalışır. Böylece her
eğitim sıfırdan başlamaz ve kabul edilen model gerilemez.

**Fiyat verisi** kartından veriyi bir kez çekip sabitleyebilirsin; sonraki
eğitimler borsaya istek atmadan aynı kopyayı kullanır. İndikatörler bu sabit
veriden yeniden hesaplanır.

Panelde **AI Eğitimi → Model mimarisi** kartından motoru (sinir ağı / gradient
boosting), gizli katmanları, aktivasyonu, dropout/L2'yi, çıktı biçimini
(AL+SAT / nötr-dip-zirve / gelecek getiri) ve kullanılacak **özellik gruplarını**
kendin seçebilirsin. Seçilmeyen özellik grubu modele hiç girmez; böylece hangi
bilginin gerçekten işe yaradığını ölçebilirsin.

Her turda model kendi kendini eğitir, **5 tura kadar** eğitim kümesindeki
işlemleri "erken / geç / zamanında" olarak analiz eder, hatalı zamanlamadaki
örneklerin ağırlığını düşürüp ideal dip/zirve örneklerini güçlendirir ve yeniden
eğitir. Tur seçimi validation ile yapılır; test yalnızca bir kez görülür.
Ardından walk-forward ile test edilir ve aşırı öğrenme kapısından geçirilir. Yeni model mevcut modelden belirgin iyiyse otomatik aktifleşir;
değilse mevcut model korunur. Hata olursa sonraki tur daha uzun beklemeyle tekrar
dener. Kapanan AI işlemleri sonraki eğitimlerde sınırlı oranda ders olarak kullanılır.

İnce ayar isteyenler için "Gelişmiş: elle eğitim" bölümü açılabilir. Titiz zaman
serisi protokolü her iki yolda da aynıdır:

- Özellikler yalnızca karar anına kadar olan kapanmış mumlardan üretilir.
- Etiketler sonraki N mumun lehte/hilaf hareketinden türetilir.
- Veri karıştırılmaz: **%70 öğrenme / %30 test**. Öğrenmenin son %15'i
  eşik ve tur seçimi (validation) için ayrılır; test hiçbir seçimde kullanılmaz.
- Bölmeler arasında etiket ufku kadar **embargo** bırakılır.
- Eşikler yalnızca validation'da seçilir; test bir kez değerlendirilir.
- Aşırı öğrenme kapısı: test getirisi eğitimin çok küçük bir parçasıysa,
  walk-forward katları tutarsızsa veya edge negatifse model aktifleşmez.

`AI_ENABLED=true` (Ayarlar → Sistem) olmadan eğitim başlatılamaz. Eski
TensorFlow/Keras tabanlı `AI.py` artık kullanılmıyor; yeni hat
`app/ai/` altındadır. Ayrıntılı protokol: `AI_TRAINING.md`.

---

## Yerel Geliştirme

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8080
```

Testler:

```bash
pip install pytest
pytest tests -q
```

---

## Mimari

```
app/
  main.py              FastAPI uygulaması + statik arayüz
  config.py            .env ve çalışma ayarları (tek kaynak)
  db.py                SQLite şeması, WAL, atomik yazım
  security.py          scrypt şifre, oturum, CSRF, kilit
  supervisor.py        bot alt süreçleri, heartbeat, restart
  bot_runner.py        tek bot süreci
  engine.py            alım-satım motoru (paper + live)
  job_runner.py        backtest / tarama / analiz işleri
  ai_worker.py         AI profili kuyruk işçisi
  strategies/
    registry.py        indikatör kataloğu + normalizasyon
    compiler.py        görsel kural → çalıştırılabilir strateji
    builtin.py         mevcut Stratejiler.py köprüsü
    service.py         strateji CRUD + sürümleme
  api/                 REST endpoint'leri
core/                  mevcut hesaplama modülleri (uyumluluk katmanı)
web/                   bağımlılıksız HTML/CSS/JS arayüz
Data/                  kalıcı veri + tradeai.db
Log/                   uygulama ve bot logları
state/                 bot başına atomik JSON durum
```

### Süreç modeli

- Web API, botları `Supervisor` üzerinden ayrı Python süreçleri olarak başlatır.
- Her bot periyodik heartbeat yazar; web durumu buradan okur.
- Durdurma: stop dosyası + `SIGTERM`; süreç açık pozisyonu güvenli kapatır.
- Çökme: bot bazında otomatik yeniden başlatma (varsayılan açık).
- Uygulama yeniden başlarsa çalışması gereken botlar geri alınır.

---

## Web Arayüzü

| Sayfa | İşlev |
|-------|-------|
| Dashboard | Grafikler, aktif tarama/işler, tarama sonuçları, çalışan botlar, pozisyonlar, K/Z, son olaylar |
| Botlar | Bot oluştur/başlat/durdur, tek tıkla mod değiştir, loglar; **anlık K/Z ve açık pozisyon durumu (5 sn)** |
| Stratejiler | Hazır + özel strateji kütüphanesi, görsel kural oluşturucu, tek tek backtest ve **tümünü karşılaştırma** |
| Tarama | Seçilen stratejilerle anlık BUY/SELL taraması; coin listesi seçilebilir |
| Coin Listeleri | Kendi coin listelerini oluştur/düzenle/sil, hazır listeler (Top 10, Layer 1, DeFi & L2, Meme); taramada ve botta tek seçimle kullan |
| Analiz | İndikatör değerleri, destek/direnç, piyasa, aylık sonuç, coinlist |
| İşlem Geçmişi | Grafikler, filtrelenebilir ledger, özet, CSV indirme; **satıra tıklayınca alış/satış grafiği** (giriş–çıkış noktaları, K/Z, satış sonrası fiyat hareketi) |
| Ayarlar | İşlem, risk, limitler, Binance, bildirimler, coin listesi, güvenlik |
| Sistem | CPU/RAM/disk, bot kaynak kullanımı |

### CLI → Web eşlemesi

Eski `main.py` menüsündeki tüm işlevler web'e taşındı. CLI hâlâ fallback olarak çalışır:

```bash
python main.py
```

| Eski menü | Yeni yer |
|-----------|----------|
| 0 Veri seti | Analiz |
| 1 Backtest kaydet | Analiz → Strateji analizi |
| 2 İndikatör test | Analiz |
| 3 Backtest grafik | Stratejiler → Backtest |
| 4 Tarama | Tarama |
| 5 Trade | Botlar |
| 6–7 Coin değerleri | Analiz |
| 8 Cihaz | Sistem |
| 9 Piyasa durumu | Analiz |
| 10, 12 Coinlist | Ayarlar / Analiz |
| 11, 19 İşlem analizi | İşlem Geçmişi |
| 13–14 Strategys | Analiz → Strateji analizi |
| 15 Buy verenler | Tarama |
| 16 Destek/direnç | Analiz |
| 17–18, 23 Pozisyon kapatma | Ayarlar → Tehlikeli işlemler |
| 20–22 Grafik/aylık/hedef | Dashboard / Analiz |
| 24–25 AI | AI profili |

---

## Görsel Strateji Oluşturucu

Stratejiler → **Yeni Strateji** ekranı sade bir akışa sahiptir:

1. **Şablon seç** (opsiyonel) — RSI, EMA kesişimi, Bollinger, MACD, trend, SuperTrend, RSI+Hacim, **Karma (A ve B) veya (C ve D)** veya boş başla.
2. **Strateji adı** gir.
3. **Ne zaman AL?** — “Hızlı ekle” düğmeleriyle hazır kurallar (RSI düşük, EMA'yı yukarı kes, alt bandın altında…) veya boş kural ekle.
4. **Ne zaman SAT?** — aynı mantıkla satış kuralları.
5. **Test et** — son mumda kuralların sağlanıp sağlanmadığını gör; kaydet.

Her kural tek satırda okunur biçimde gösterilir: `RSI(14) < 30`, `kapanış ↗ EMA(50)`.
Altındaki özet paneli tüm mantığı düz cümle olarak yazar:

> **AL** — kapanış ↗ EMA(50) VE ADX(14) > 25  
> **SAT** — kapanış ↘ EMA(50)

Kurallar arasındaki ilişki tek tıkla seçilir: **Tümü sağlanmalı (VE)** / **Herhangi biri (VEYA)**.
Alt grup eklemek için **+ VE grubu** / **+ VEYA grubu** düğmeleri kullanılır. Böylece
`(A ve B) veya (C ve D)` gibi karma koşullar iç içe gruplarla görsel olarak kurulur; her grubun
mantığı ayrı seçilir ve özet panelinde parantezlerle gösterilir.

Strateji, güvenli bir JSON DSL olarak saklanır; `eval` kullanılmaz.

```json
{
  "name": "RSI Dip + EMA Trend",
  "buy": {
    "logic": "AND",
    "conditions": [
      {
        "left": {"type": "indicator", "id": "RSI", "params": {"length": 14}, "output": "value"},
        "op": "lt",
        "right": {"type": "constant", "value": 30}
      },
      {
        "left": {"type": "price", "field": "close"},
        "op": "crosses_above",
        "right": {"type": "indicator", "id": "EMA", "params": {"length": 50}, "output": "value"}
      }
    ]
  },
  "sell": {
    "logic": "OR",
    "conditions": [
      {
        "left": {"type": "indicator", "id": "RSI", "params": {"length": 14}, "output": "value"},
        "op": "gt",
        "right": {"type": "constant", "value": 70}
      }
    ]
  }
}
```

- Operandlar: fiyat, hacim, indikatör, sabit, offset, matematik.
- Operatörler: karşılaştırma, kesişim, yön, aralık, yüzde değişim, N mum içinde.
- Mantık: AND / OR / NOT ve iç içe gruplar.
- Tüm indikatör çıktıları giriş uzunluğuna normalize edilir.
- Değerlendirme her zaman **kapanmış mum** üzerinde yapılır.
- Backtest ve canlı bot **aynı derleyiciyi** kullanır (parity testi).

### Strateji yönetimi: düzenle, kopyala, arşivle, sil

Kütüphanedeki her kartta işlem düğmeleri vardır:

| Düğme | Ne yapar |
|---|---|
| **Düzenle** | Görsel kuralları açar (hazır stratejilerde kopya oluşturur). |
| **Backtest** | Seçili periyotta geçmiş testi çalıştırır. |
| **Kopyala** | Aynı tanımdan yeni bir strateji üretir. |
| **Arşivle / Aktifleştir** | Listeden gizler/gösterir; kayıt korunur. |
| **Sil** | **Kalıcı silme.** Strateji, sürüm geçmişi ve backtest kayıtları silinir. Geri alınamaz. |

- Silme işlemi onay ister; `DELETE /api/strategies/custom/{id}` uç noktası kullanılır.
- Strateji **çalışan bir bot tarafından kullanılıyorsa** silme engellenir ve hangi botların
  kullandığı söylenir. `?force=true` ile yine de silinir (o botlar bu stratejiyle
  başlatılamaz).
- **Hazır (kod tabanlı) stratejiler silinemez**; `Arşivle` ile listeden gizlenir. Kalıcı olarak
  kaldırmak istiyorsanız `Kopyala` ile kendi listeye alıp düzenleyebilirsiniz.

### Tüm stratejileri karşılaştır

Stratejiler sayfasındaki **Tümünü Karşılaştır** düğmesi, kütüphanedeki *tüm* hazır ve özel
stratejileri **aynı fiyat serisiyle** tek işte backtest eder ve sıralanabilir bir tablo üretir.

- Girdiler: coin, periyot (15m/1h/4h/1d), nakit, mum sayısı (3.000 – 250.000). Mum sayısı
  seçenekleri ve sonuç başlığı, seçilen periyoda göre **kapsanan süreyi** ("≈ 2 yıl 3 ay") ve
  gerçek tarih aralığını gösterir.
- Sütunlar: getiri %, al-tut %, **fark** (getiri − al-tut), maksimum düşüş %, Calmar, işlem
  sayısı, kazanma %. Sütun başlığına tıklayınca sıralama değişir (varsayılan: farka göre azalan).
- Her satıra tıklayınca o stratejinin tek başına backtest raporu (fiyat grafiği, işaretli
  işlemler, pozisyon süreleri, yıllık tablo, işlem listesi) aynı pencerede açılır;
  **← Karşılaştırmaya dön** ile tabloya dönülür.
- Veri **bir kez** çekilip tüm stratejilerle paylaşılır; bu yüzden toplu karşılaştırma, aynı
  testi tek tek çalıştırmaktan çok daha hızlıdır.
- Tek bir strateji hata verirse yalnız o satır kırmızı hata mesajı gösterir, tablo bozulmaz.
- API: `POST /api/strategies/backtest-all` → `backtest_all` işi (`coin`, `period`, `limit`,
  `cash`, `include_archived`, isteğe bağlı `keys`).

### İndikatör kataloğu (ilk sürüm)

EMA, SMA, Bollinger, RSI, MACD, ATR, ADX, SuperTrend, Stochastic RSI, Ichimoku, Donchian, CCI, MFI, Momentum, Parabolic SAR, Hacim SMA, RSI Bollinger, **Tillson T3**, **QQE MOD**.

### Tillson T3
Tim Tillson'ın T3 göstergesi: `(high + low + 2 × close) / 4` kaynağına uygulanan 6 katmanlı EMA'nın
hacim faktörü katsayılarıyla ağırlıklı toplamı. Varsayılan periyot 8, hacim faktörü 0.7.
Çıktılar: `value` (T3 çizgisi), `direction` (1 yükseliyor / -1 düşüyor / 0 yatay), `slope`.

### QQE MOD
İki QQE katmanı (birincil 6/5/3.0, ikincil 6/5/1.61) ve trend çizgisinin 50 merkezine göre
hesaplanan Bollinger bantlarını (50 periyot, 0.35 çarpan) birleştirir. Alım sinyali, ikincil RSI
eşiği aşarken birincil RSI'ın üst bandı geçmesiyle; satım sinyali simetrik olarak alt bantla oluşur.
Çıktılar: `signal` (1 al / -1 sat / 0 yok), `direction`, `trend`, `rsi`, `centered`, `upper`,
`lower`, `secondary_rsi`, `secondary_trend`, `secondary_centered`, `histogram` ve `hist_state`.

**Histogram renkleri** (Pine ile aynı):
| Durum | Koşul | Anlam |
|---|---|---|
| 🔵 **mavi** (`hist_state = blue`) | ikincil RSI − 50 > eşik **ve** birincil RSI − 50 > üst bant | QQE alım sinyali |
| 🔴 **kırmızı** (`red`) | ikincil RSI − 50 < −eşik **ve** birincil RSI − 50 < alt bant | QQE satım sinyali |
| ⚪ **gri** (`gray`) | \|ikincil RSI − 50\| > eşik ama birincil onay yok | eşik aşıldı, sinyal değil |
| — **yok** (`none`) | eşik içinde | Pine'da çizilmez (na) |

> QQE varsayılan `bb_length=50` olduğu için gereken ısınma **150 mum**'dur; strateji
> doğrulaması bu değeri otomatik hesaplar.

---

## Bot Oluşturma

Botlar → **Yeni Bot** ekranı beş adımlı bir akıştır:

1. **Çalışma modu** — Test (paper) veya Canlı. Canlı seçmek için üst çubuktaki canlı işlem anahtarının açık olması yeterlidir.
2. **Bot kimliği** — ad, zaman dilimi (chip olarak), başlangıç nakdi, maksimum pozisyon yüzdesi.
3. **Coinler** — popüler coinler tek tıkla seçilir; başka sembol yazılıp eklenebilir. **Coin listesi** açılır menüsünden kayıtlı bir liste seçilirse listenin coinleri tek tıkla eklenir. Boş bırakılırsa `Data/coin_list.txt` tamamı izlenir.
4. **Stratejiler** — özel ve hazır stratejiler kart olarak listelenir; özel stratejilerin AL/SAT kuralları kart üzerinde görünür. Birden fazla strateji seçilebilir.
5. **Risk koruması** — dinamik/sabit/destek stop, kâr al, maksimum mum, EMA50 ve BB filtreleri, çökmede otomatik yeniden başlatma.

Alt bardaki özet, kaydetmeden önce tüm seçimleri tek satırda gösterir:

> **TEST** — 15m · 100 USDT · %100 pozisyon · BTCUSDT, ETHUSDT · 1 strateji

Botlar sayfasındaki **Hızlı Bot** düğmesi, mantıklı varsayılanlarla (1h, 100 USDT, BTC/ETH, ilk strateji) formu önceden doldurur; tek tıkla kaydedip başlatabilirsiniz.

Bot kartında durum, mod, nakit, K/Z, işlem sayısı, sparkline ve açık pozisyon görünür.
Mod rozetine tıklayarak botu **tek tıkla test ↔ canlı** arasında değiştirebilirsiniz.
**Loglar** penceresi botun canlı çıktısını ve son olayları (bilgi / uyarı / hata) birlikte gösterir.

### Botu kopyalama

Bot kartındaki **Kopyala** düğmesi, botun **adını, periyodunu ve kurallarını** (stratejiler,
risk koruması, filtreler, coinler / coin listesi, maksimum pozisyon yüzdesi) yeni bir bota taşır.
Kopya **sıfırdan başlar**:

| Taşınır | Taşınmaz |
|---|---|
| Ad (istediğiniz gibi değiştirilebilir), periyot | İşlem geçmişi ve K/Z istatistikleri |
| Stratejiler ve kuralları | Açık/kapalı pozisyonlar |
| Risk koruması ve filtreler | Sinyal, olay ve bot logları |
| Coin listesi, başlangıç nakdi, mod | Durum dosyası (`state/<bot_id>.json`) |

Yeni bot **durdurulmuş** olarak oluşturulur; başlangıç nakdi ve sıfır K/Z ile Botlar
sayfasından başlatılır. Kaynak bot canlıysa kopya da canlı moda geçer ve canlı işlem
anahtarının açık olması gerekir; kopya canlı açıkken oluşturulursa onay istenir.

### Anlık K/Z ve pozisyon durumu

Bot kartları **5 saniyede bir** kendini günceller (sayfa yenilenmeden):

| Gösterge | Anlamı |
|---|---|
| **Nakit** | Botun kullanılabilir USDT bakiyesi |
| **Toplam K/Z** | Gerçekleşen + **anlık açık pozisyon** K/Z'si (nakit + pozisyon değeri − başlangıç) |
| **Anlık (açık)** | Açık pozisyonun şu andaki gerçekleşmemiş K/Z'si (USDT) |
| **Portföy değeri** | Nakit + pozisyonun güncel değeri |

Pozisyon şeridinde: coin, adet, giriş fiyatı, **güncel fiyat**, **K/Z %**, **stop seviyesi** ve
stopa **uzaklık %**, pozisyondaki mum sayısı.

### Manuel (harici) satış takibi — canlı mod

Canlı modda **borsa gerçeği yerel kayda göre önceliklidir**. Bot, 30 saniyede bir (ve her mumda)
bakiyeyi kontrol eder:

| Durum | Botun yaptığı |
|---|---|
| Coin **tamamen** elle satılmış (bakiye 0 veya toz) | Pozisyon **kapatılır**, işlem geçmişine `manuel` nedenli SAT yazılır, nakit borsadaki gerçek USDT ile eşitlenir, bekleme süresi başlar |
| Coin **kısmen** elle satılmış | Kalan miktar yerel kayda işlenir, satılan kısım `manuel` olarak geçmişe eklenir |
| **Harici alım** yapılmış (yereldekinden fazla bakiye) | Varsayılan olarak **yalnızca uyarı** verilir; pozisyon değişmez (Ayarlar > İşlem > *Harici alımları benimse* açılırsa miktar güncellenir) |
| Bakiye okunamazsa | Pozisyona dokunulmaz (geçici ağ hatasında yanlış kapanış olmaz) |
| Test (paper) modu | Etkilenmez — sanal bakiye kullanılır |

Gerçekleşen fiyat, nakit artışından (borsadaki USDT − yerel nakit) hesaplanır; bu değer
referans fiyattan aşırı sapıyorsa (transfer/komisyon vb.) son bilinen fiyata düşülür. Satışta
bildirim ve olay kaydı (`MANUEL SATIŞ algılandı…`) üretilir; İşlem Geçmişi'nde neden
**manuel satış** etiketiyle kırmızı gösterilir.

- Güncel fiyat **Binance public ticker**'ından alınır (4 saniye önbellek). Ağ hatasında botun
  son mum kapanış fiyatına düşer; hangi kaynağın kullanıldığı şeritte **canlı / mum** olarak yazar.
- Üst çubuktaki **Toplam K/Z** de artık gerçekleşmemiş K/Z'yi içerir; üzerine gelince
  gerçekleşen + anlık dağılımı görünür.
- Aynı değerler dashboard'daki **Toplam K/Z** kartında ve bot özet satırlarında da gösterilir.
- API: `GET /api/bots` her bot için `state.unrealized_pnl`, `state.total_pnl`, `state.equity` ve
  `state.position.last_price`, `unrealized_pnl_pct`, `stop_price`, `stop_distance_pct`,
  `price_source` alanlarını döndürür.

**Risk kuralları canlıda backtest ile aynıdır.** Bot oluştururken strateji tanımındaki `risk`
bloğu (ATR stop, takipli stop, kâr koruma, bekleme) otomatik devralınır; bot kartında
"Risk: stop 35×ATR (en çok %15) · bekleme 10 mum" satırı etkin kuralları gösterir. Eski kayıtlarda yalnızca
4 boolean saklanmış olsa bile motor stratejiden devralır, böylece canlı işlem backtest'i birebir izler.

### Emir dayanıklılığı: alınamadı / satılamadı

Emir kararları **emirden önce** kalıcı olarak yazılır (`state.pending_exit`). Böylece:

| Durum | Botun yaptığı |
|---|---|
| Satış emri reddedildi (bakiye, filtre, 429, 5xx) | Pozisyon ve nakit **değişmez**; karar kaydedilir, `EXIT_RETRY_SECONDS` (varsayılan 5 sn) sonra **mum beklemeden** tekrar denenir. 3 denemeden sonra Telegram uyarısı gider. |
| Panelden "Sat" istendi, emir reddedildi | İstek dosyası **silinmez**; bot düzelene kadar tekrar dener. Kartta `satış bekliyor` rozeti görünür. |
| Emir yanıtı gelmedi (timeout) | Aynı `clientOrderId` ile en fazla 3 deneme yapılır; önce emir durumu sorgulanır. Gerçekleşmişse **çift emir gönderilmez**. |
| Alım reddedildi | Pozisyon açılmaz, nakit değişmez; sonraki mumda sinyal sürerse yeniden denenir. Hata Telegram'a gider. |
| DB yazımı başarısız (paper) | Satış kaydı yazılamazsa nakit/pozisyon **güncellenmez** → aynı mumda ikinci kez satılmaz. |
| Adet hesabı | Borsa `LOT_SIZE.stepSize` değerine göre **aşağı** yuvarlanır; `minNotional`, `maxQty` ve `minQty` kontrol edilir. Canlı alım `quoteOrderQty` (USDT) ile yapılır, fiyat sıçrasa bile bakiye aşılmaz. |
| Bakiye okunamazsa | Emir gönderilmez; hata loglanır ve bildirilir. |
| Birden fazla canlı bot | Emirler dosya kilidiyle (`state/live_account.lock`) sıraya konur; her bot **yalnızca kendi kaydındaki nakdi** harcar. Hesap paylaşılıyorsa Ayarlar > İşlem > *Binance hesabı birden fazla botla paylaşılıyor* işaretlenir (nakit mutabakatı hesap toplamıyla kıyaslanmaz). |
| Çalışırken nakit kayması | `RECONCILE_SECONDS` (varsayılan 300 sn) aralığında borsa bakiyesiyle karşılaştırılır; `RECONCILE_TOLERANCE_PCT` aşılırsa uyarı verilir. *Mutabakat farkında botu durdur* açıksa bot `reconciliation_required` ile durur. |
| Bot süreci çöker | Supervisor 5 kez yeniden başlatır. **Borsada koruyucu emir** (Ayarlar > İşlem) açıksa pozisyon borsa tarafında da korunur: kâr al hedefi varsa **OCO** (stop + kâr al), yoksa `STOP_LOSS_LIMIT`. Bot bu emirleri stop taşındıkça (en fazla 30 sn'de bir) günceller; kapanışta iptal eder. Emir borsada dolmuşsa işlem `stop` / `kâr al` nedeniyle kaydedilir. |
| Geçersiz API anahtarı (401 / -2015) | Sonsuz denenmez; bot hata durumuna geçer ve Telegram'a bildirilir. |

Satış emri başarısız olduğunda borsadaki koruyucu stop iptal edilmişse **geri kurulur**; pozisyon
korumasız bırakılmaz.

Çökmüş botlar (yeniden başlatma açıksa) uygulama/container yeniden başladığında **otomatik geri
getirilir** ve önceki hata mesajı temizlenir.

### Stop nasıl hesaplanır? (`max_stop_pct`)

`stop = giriş − (stop_atr × ATR)` — ATR(14), giriş mumundaki ortalama gerçek aralıktır ve
pozisyon boyunca sabit kalır.

Sorun: ATR **coin'in oynaklığına** bağlıdır. BTC'de ATR fiyatın ~%0,5'i iken 35×ATR ≈ %15-20
makul; ama ATR fiyatın %3'ü olan bir coinde (ör. DODO 15m) 35×ATR stopu **%97 aşağıya** atar:
`0.03126 − 35×0.00086 = 0.00104`. Bu stop çalışmaz; pratikte "coin sıfırlanmadıkça tut" olur.

Bu yüzden **`max_stop_pct`** üst sınırı vardır: `stop = max(giriş − stop_atr×ATR, giriş × (1 − max_stop_pct/100))`.
15m Kısa Vade Pro'da `max_stop_pct = 15`, yani stop **girişten en fazla %15 aşağıda** olabilir.
Aynı kural hem backtest hem canlı motorda uygulanır; bot kartında "(en çok %15)" olarak görünür.

Ölçüm (15m, 100.000 mum, BTC/XRP/SOL/DODO): sınırsız stop toplam fark 141 ama **en kötü coin
+4,7**; %15 tavanla toplam 96 ama **en kötü coin +14,5** ve ortalama düşüş aynı. Yani biraz
getiri karşılığında stop gerçekten işlevli hâle gelir. (%8 çok sık stop tetikleyip kötüleşiyor,
%20 ise yüksek oynaklıklı coinde hâlâ etkisiz.)

---

## Coin Listeleri

**Coin Listeleri** sayfasından istediğiniz coin gruplarını bir kez oluşturup saklayabilirsiniz.
Her liste bir ad ve coin sembollerinden oluşur (virgül/boşlukla ayrılır, sembol otomatik büyük harfe çevrilir).

- **Hazır listeler:** Top 10, Layer 1, DeFi & L2, Meme. Salt-okunurdur; **Kopyala** ile kendi listenize dönüştürüp düzenleyebilirsiniz.
- **Kendi listeleriniz:** oluştur, yeniden adlandır, coin ekle/çıkar, sil. Aynı ad iki kez kullanılamaz.
- **Bu listeyle tara:** Tarama sayfasına geçer ve ilgili listeyi seçer.
- **Bu listeyle bot oluştur:** Bot formunu listenin coinleriyle önceden doldurur.

Liste seçimi **kayıt anındaki coinleri sabitler**: bir bot oluşturulduktan sonra listeyi değiştirseniz bile botun izlediği coinler değişmez,
böylece çalışan bir botun evreni kendiliğinden değişmez. Taramada ise liste, tarama başlatılırken okunur.

Ayarlar → **Coin listesi** sekmesindeki `Data/coin_list.txt` ise "hiç coin seçilmezse" kullanılan genel evrendir; coin listeleri bunun alternatifidir.

---

## İşlem Modları

### Test (paper) — varsayılan
- Gerçek emir gönderilmez.
- Fiyat, komisyon ve slippage simüle edilir.
- Bakiye ve K/Z yerel ledger'da tutulur.

### Canlı (live) — tek anahtar
1. Üst çubuktaki **Canlı işlem** anahtarını aç
2. Botun mod rozetine tıkla → **Canlı**

Sunucu izni de panelden yönetilir: **Ayarlar → İşlem → Canlı işlem sunucu izni**. `.env` düzenlemek gerekmez.

Anahtar kapatıldığında çalışan tüm canlı botlar güvenli şekilde durdurulur. Canlıya geçişte bot önce durdurulur; açık pozisyon varsa geçiş reddedilir. Başlangıçta Binance bakiyesi ile yerel ledger karşılaştırılır; uyuşmazlıkta bot `reconciliation_required` durumuna geçer.

---

## Veri Tutarlılığı

- SQLite tek doğruluk kaynağıdır (`Data/tradeai.db`, WAL).
- `trades`, `positions`, `pnl_snapshots`, `signal_events` tabloları tutulur.
- Her sinyalin koşul dökümü ve indikatör değerleri kaydedilir.
- Bot state dosyaları atomik yazılır (`tempfile + os.replace`).
- Strateji sürümü bot başlatılırken sabitlenir; güncelleme çalışan botu etkilemez.
- Tüm işlemler `clientOrderId` ile izlenebilir (live).

---

### Hazır: T3 + QQE Pro

*Tillson T3 & QQE MOD* stratejisinin optimize edilmiş sürümü (`T3 + QQE Pro`).

| Bileşen | Ayar |
|---|---|
| T3 | periyot **48**, hacim faktörü **0.7** |
| QQE MOD | RSI **9**, yumuşatma 5, faktör 3.0, eşik 3.0, ikincil 9/5/1.61, BB 50 / 0.35 |
| AL | T3 bu mumda yukarı döndü (önceki mum yukarı değil) **ve** QQE sinyali 1 **ve** ADX ≥ 22 **ve** hacim ≥ 20 mum ortalaması |
| SAT | kapanış **üst üste iki mum** T3 çizgisinin altında |

BTCUSDT, gerçek motor, %0.1 komisyon + %0.05 kayma:

| Periyot | Veri | Eski (v1) | **Yeni (v3)** | Al-tut |
|---|---|---|---|---|
| 15m | 20.000 mum | -3.61%* | **+9.44%** (35 işlem, pf 2.28, dd %6) | +1.3% |
| 1h | 20.000 mum | -2.99%* | **+65.72%** (37 işlem, kazanma %49, pf 3.03, dd %6.6) | +25.1% |
| 4h | 12.000 mum | -9.09%* | **+139.21%** (24 işlem, kazanma %50, pf 4.24, dd %10.3) | +94.0% |
| 1d | 3.371 mum | +11.43%* | **+251.76%** (10 işlem, pf 6.3, dd %29.3) | +568.4% |

\* Eski sürüm 1.000 mumluk pencerede ölçülmüştü.

**Son dönem penceresi** (son 5.000 mum; 1d için son 3.000):

| Periyot | Yeni (v3) | Al-tut |
|---|---|---|
| 15m | -4.85% | -0.5% |
| 1h | **+12.78%** | +2.1% |
| 4h | **+47.72%** | +12.5% |
| 1d | **+317.71%** | +1062.7% |

> 15m son dönemde zayıf (yatay/choppy piyasa). Bu strateji **1h ve 4h** için en iyi
> sonucu veriyor. Bot oluştururken risk korumalarını (dinamik stop / kâr al) açık tutun.
> Uzun vadede **al-tut'u geçmek** için aşağıdaki `T3 + QQE Pro Max` sürümünü kullanın.

### Hazır: T3 + QQE Pro Max (al-tut'u geçen sürüm)

`T3 + QQE Pro`'nun uzun vadeli, iz süren sürümü. Hedef: **al-tut'tan daha yüksek getiri,
daha düşük düşüş**. Üç fark:

| Bileşen | Ayar |
|---|---|
| Giriş | Pro ile aynı: T3 (48 / 0.7) yukarı dönüşü + QQE (RSI 9) sinyali |
| Rejim filtresi | fiyat **EMA200 üzerinde** değilse alım yok (ayı piyasasında nakitte bekler) |
| Çıkış | **Chandelier**: son 100 mumun zirvesi − 12 × ATR(14). Trendi erken bırakmaz |

BTCUSDT, gerçek motor, %0.1 komisyon + %0.05 kayma; al-tut aynı başlangıç mumundan ölçülür:

| Periyot | Veri | Pro Max | Al-tut | Maks. düşüş (strateji / al-tut) | İşlem |
|---|---|---|---|---|---|
| 1h | 10.000 mum | **-9.60%** | -34.01% | 19.2% / 49.8% | 17 |
| 4h | 12.000 mum | **+126.52%** | +61.60% | 57.7% / 77.0% | 16 |
| 1d | 3.400 mum | +1338.82% | +1344.37% | **53.6%** / 76.6% | 4 |

> 1h'de al-tut'tan **24 puan** daha iyi ve düşüşün yarısı; 4h'de getiriyi **2 katına**
> çıkarıp düşüşü 19 puan azaltıyor; 1d'de getiri başa baş ama düşüş 23 puan daha düşük.
> 15m için tasarlanmadı (kısa vadeli gürültüde 12×ATR iz çok geniş kalır); 15m'de
> `T3 + QQE Pro` veya `Tillson T3 & QQE MOD` kullanın.

**Neden al-tut'u geçiyor?** Al-tut her düşüşü sonuna kadar taşır (düşüş %77). Pro Max
EMA200 altında nakitte bekler ve trend bittiğinde Chandelier ile çıkar; aynı boğa
hareketini yakalarken ayı piyasasının büyük kısmından korunur.

> Uzun backtestler artık hızlı: kural motoru operand serilerini mum başına yeniden
> kurmuyor (O(n²) → O(n)); 10.000+ mumluk testler saniyeler içinde tamamlanıyor.

### Hazır: Trend Sürücü (al-tut'u en net geçen strateji)

Uzun vadeli trend takibi. Amaç: **boğa piyasasında piyasada kal, ayı piyasasında nakitte bekle.**
Pro Max'tan farkı, giriş için T3/QQE dönüşünü beklememesi — trend sürdüğü sürece pozisyonda kalır.

| Bileşen | Ayar |
|---|---|
| Rejim | fiyat **EMA200 üzerinde** değilse alım yok |
| AL | SuperTrend(**40**, 4.0) yukarı **veya** RSI(14) ≤ 45 (boğa rejiminde geri çekilme alımı) |
| SAT | kapanış **üst üste iki mum** EMA200'ün %2 altında |

BTCUSDT, gerçek motor, %0.1 komisyon + %0.05 kayma, **tüm geçmiş**, al-tut aynı mumdan ölçülür:

| Periyot | Veri | Trend Sürücü | Al-tut | Fark | Maks. düşüş (strateji / al-tut) | İşlem | CAGR (strateji / al-tut) |
|---|---|---|---|---|---|---|---|
| 1h | 20.000 mum | **+48.08%** | +24.17% | +23.9 | **30.8%** / 53.7% | 47 | 19.4% / 10.3% |
| 4h | 20.000 mum | **+1506.79%** | +426.48% | **+1080.3** | **49.9%** / 81.4% | 74 | 36.8% / 20.6% |
| 1d | 3.371 mum | **+1675.10%** | +1344.37% | +330.7 | **46.4%** / 76.6% | 19 | 46.1% / 42.2% |
| 15m | 20.000 mum | -10.66% | -1.00% | -9.7 | 26.5% / 29.7% | 23 | — |

> 1h, 4h ve 1d'de **hem daha yüksek getiri hem daha düşük düşüş**. 4h'de getiriyi 3.5 katına
> çıkarıp düşüşü 31 puan azaltıyor; 1d'de getiri +331 puan, düşüş 30 puan daha az.
> **15m için tasarlanmadı** (kısa vadeli gürültüde trend filtresi sürekli kesilir); 15m'de
> `T3 + QQE Pro` kullanın.

**Neden al-tut'u geçiyor?** Al-tut her düşüşü sonuna kadar taşır (%77–81 düşüş). Trend Sürücü
EMA200 altında nakitte bekler, trend bittiğinde iki mumluk teyitle çıkar; aynı boğa hareketini
yakalarken ayı piyasasının büyük kısmından korunur. Sonuç: daha yüksek getiri **ve** yarı yarıya düşüş.

**Dürüst yanı:** trend takibi güçlü boğa yıllarında (2020, 2023, 2024) al-tut'un gerisinde kalır;
sert düşüş yıllarında (2018, 2022, 2026) büyük fark atar. Backtest sonucundaki **yıl bazında**
tablo bunu açıkça gösterir. Tek bir yıla değil, tüm geçmişe ve düşüş derinliğine bakın.

### Hazır: Sadece Yükseliş (en az işlem, yalnızca güçlü yükseliş)

Amaç: **sadece yükselişte işleme gir, yatayda ve düşüşte girme, olabildiğince az işlem.**
Trend Sürücü sürekli piyasada kalırken bu strateji yalnızca **yerleşik güçlü yükseliş** onaylandığında girer.

| Bileşen | Ayar |
|---|---|
| AL | fiyat **EMA200'ün %10 üzerinde** **ve** EMA50 > EMA200 **ve** EMA200 son **150 mumda yükseliyor** |
| SAT | fiyat **EMA200 altında** **ve** EMA200 son **150 mumda düşüyor** (ikisi birden) |
| Yatay | EMA200 eğimi düzleşince giriş yok; bant yüzünden EMA200 etrafındaki zıplamalar elenir |
| Düşüş | EMA200 eğimi negatife dönüp fiyat altına inince çıkar; ayıda nakitte bekler |

BTCUSDT, gerçek motor, %0.1 komisyon + %0.05 kayma, tüm geçmiş:

| Periyot | Veri | Sadece Yükseliş | Al-tut | Fark | İşlem | Maks. düşüş (strateji / al-tut) |
|---|---|---|---|---|---|---|
| 4h | 20.000 mum | **+1335.62%** | +502.15% | **+833.5** | **19** | **60.7%** / 81.4% |
| 1d | 3.372 mum | **+1391.45%** | +1325.03% | +66.4 | **3** | **53.1%** / 76.6% |
| 1h | 20.000 mum | +23.07% | +22.74% | +0.3 | **2** | **14.4%** / 53.7% |
| 15m | 20.000 mum | -1.05% | -2.24% | +1.2 | **1** | **4.4%** / 29.7% |

> **4h önerilir:** getiri 2.7 katına çıkıyor, işlem yalnızca 19, düşüş 21 puan daha az.
> 1d'de getiri al-tut ile başabaş ama düşüş 23 puan daha düşük ve sadece 3 işlem.
> 1h/15m'de neredeyse hiç işlem yapmaz (yılda 0-1) — bu bir hata değil, tasarım gereği:
> kısa periyotta "yerleşik yükseliş" koşulu nadiren sağlanır.

**Genelleme:** 8 coin (BTC, ETH, SOL, BNB, XRP, ADA, DOGE, AVAX) × 4h/1d = 16 seride
**11'inde al-tut'u geçiyor**; 4h'de medyan fark **+1793 puan**. Tek coin'e özel değil.
XRP tek belirgin istisna (-322 puan, 4h).

**Neden al-tut'u geçiyor?** Al-tut %81 düşüşü sonuna kadar taşır. Bu strateji yükseliş
rejimi bozulunca (EMA200 eğimi negatif + fiyat altında) nakde geçer. 2018, 2022, 2025 ve
2026'da al-tut'tan önde; 2020/2023/2024 boğa yıllarında geride. Backtest'teki **yıl bazında**
tablo bunu gösterir.

#### 4h erken giriş sürümü: `Sadece Yükseliş 4h`

`Sadece Yükseliş` çok katı olduğu için trend başlangıcını kaçırabiliyor (%10 bant + 150 mum eğim).
4 saatlik grafik için daha erken giren sürüm ayrı kayıtlıdır:

| Bileşen | Ayar |
|---|---|
| AL | fiyat **EMA200'ün %2 üzerinde** **ve** EMA50 > EMA200 **ve** EMA200 son **50 mumda yükseliyor** |
| SAT | fiyat **EMA200 altında** **ve** EMA200 son **50 mumda düşüyor** |

BTCUSDT 4h, tüm geçmiş (20.000 mum): **+1297.94%** vs al-tut **+502.15%** (**+795.8** puan),
**40 işlem**, düşüş **51.9%** / 81.4%. Son 3 yılda 16 işlem (yılda ~5).
Bant %0–%8 aralığının tamamında al-tut'u geçer; yani tek bir parametre değerine bağlı değil.

**Neden işlem açmıyorsa?** İki kural da "yükseliş rejimi" ister. Fiyat EMA200'ün altındaysa
veya EMA200 düşüyorsa strateji **bilerek** nakitte bekler. Örneğin 2026-11 itibarıyla BTC
~74.9k, EMA200 ~76.5k ve EMA200 düşüşte: bu bir ayı/düzeltme rejimidir, giriş yoktur.
Bu davranış hata değil, "düşüşte işleme girme" kuralının sonucudur. Giriş anını görmek için
stratejide **Test et** (preview) ekranındaki üç AL koşulunun değerlerine bakın.

### Walk-forward: hangi strateji gerçekten işe yarıyor?

Önceki turlarda yapılan hata: **aynı veride** parametre arayıp en iyi backtest'i seçmek.
Bu, görülmemiş dönemde çöken "aşırı-uyum" üretir. Bu yüzden ayrı bir test yapıldı:

- **Seçim dönemi (in-sample):** 2018–2022
- **Test dönemi (out-of-sample):** 2023–2026 — bu dönem seçimde hiç kullanılmadı
- 8 coin × 4h/1d = 16 seri, komisyon + kayma dahil

Sonuç (al-tut'a göre medyan fark):

| Strateji ailesi | In-sample | **Out-of-sample** | Yorum |
|---|---|---|---|
| Trend (EMA200 eğimi) | +163 | **−58** | Aşırı-uyum: geçmişte iyi, gelecekte zayıf |
| Kanal kırılımı (55) | +93 | **−76** | Aynı sorun |
| Boğada dip alımı (RSI) | −187 | −108 | Baştan zayıf |
| RSI 50 kesişimi | +122 | −112 | Aşırı-uyum |

**Dürüst sonuç:** basit kurallarla **boğa piyasasında al-tut'u geçmek mümkün değil.**
2023–2024 güçlü boğaydı; orada piyasada kalmak her zaman kazanır. Bir kural setinin
al-tut'u geçtiğini iddia ediyorsa ya aşırı-uyumdur ya da o dönem boğa değildi.

### EMA Trend Kesişimi (BTC'de ayarlandı, XRP'de doğrulandı)

**Metodoloji:** Ayarlar **yalnızca BTCUSDT** üzerinde yapıldı. Sonra strateji **hiç
görülmemiş XRPUSDT** üzerinde test edildi. Bu, aynı veride parametre arayıp "güzel
backtest" üretmenin önüne geçer.

| Bileşen | Ayar |
|---|---|
| AL | **EMA(35) > EMA(60)** **ve** fiyat **EMA200 üzerinde** |
| SAT | **EMA(35) < EMA(60)** |

BTCUSDT 4h, gerçek motor, tüm geçmiş (komisyon + kayma dahil):

| Coin | İşlem | Strateji | Al-tut | Fark | CAGR (strat / al-tut) | Calmar | Maks. düşüş |
|---|---|---|---|---|---|---|---|
| **BTCUSDT** (ayar) | 96 | **+1525.4%** | +477.5% | **+1047.9** | **37.0% / 21.9%** | **0.66 / 0.27** | **56.2%** / 81.4% |
| **XRPUSDT** (test) | 98 | **+1374.5%** | +272.2% | **+1102.2** | **38.6% / 17.3%** | **0.71 / 0.20** | **54.0%** / 84.5% |

**Neden bu sefer gerçek?** Çünkü sonuç tek bir parametre çiftine bağlı değil:
fast EMA **20–45** ve slow EMA **45–80** aralığının **tamamı** hem BTC'de hem XRP'de
al-tut'u geçiyor. Yani parametre ızgarasında geniş bir "plato" var — bu, aşırı-uyumun
tam tersi.

**8 coinde 4h doğrulaması (7/8 al-tut'u geçti):**

| Coin | Strateji | Al-tut | Fark | Düşüş (strat / al-tut) |
|---|---|---|---|---|
| BTC | +1525.4% | +477.5% | +1047.9 | 56% / 81% |
| ETH | +4048.2% | +205.4% | +3842.8 | 55% / 94% |
| SOL | +9571.1% | +4148.5% | +5422.6 | 79% / 97% |
| BNB | +4539.0% | +6423.6% | −1884.6 | 65% / 78% |
| XRP | +1374.5% | +272.2% | +1102.2 | 54% / 85% |
| ADA | +1983.5% | +6.3% | +1977.2 | 81% / 95% |
| DOGE | +4485.4% | +2725.5% | +1759.9 | 88% / 93% |
| AVAX | +8214.7% | +212.8% | +8001.9 | 75% / 96% |

**Dürüst sınırlar:**
- **4 saatlik** için tasarlandı. 1 günlükte XRP'de al-tut'u geçemez; kullanmayın.
- Boğa yıllarında (2023, 2024) al-tut'un gerisinde kalır; düşüş yıllarında (2018, 2022, 2026)
  büyük fark atar. Yıllık tablo bunu gösterir.
- BNB tek istisna: mutlak getirisi yüksek (+4539%) ama al-tut'un altında.
- İşlem sayısı yüksektir (yılda ~10). Düşük işlem istiyorsanız `Kırılım Takipçisi`
  veya `Sadece Yükseliş` kullanın; onlar daha az işlem yapar ama getirisi daha düşük.

### Kırılım Takipçisi (walk-forward'dan geçen sürüm)

Sağlamlık testinde komşu parametrelerde de tutarlı kalan tek kurgu:

| Bileşen | Ayar |
|---|---|
| AL | fiyat **son 100 mumun zirvesini** kırar **ve** EMA200 üzerinde |
| SAT | fiyat **son 10 mumun dibinin** altına iner |

BTCUSDT, gerçek motor, tüm geçmiş:

| Periyot | Getiri | Al-tut | Düşüş (strateji / al-tut) | Calmar (strat / al-tut) | İşlem |
|---|---|---|---|---|---|
| 4h | **+641.32%** | +477.51% | **30.5%** / 81.4% | **0.83** / 0.27 | 108 |
| 1d | +451.67% | +1325.03% | **58.1%** / 76.6% | 0.43 / 0.55 | 19 |

**Rejim testi (al-tut'u geçtiği seri sayısı):**

| Dönem | Medyan strateji | Medyan al-tut | Al-tut'u geçtiği |
|---|---|---|---|
| 2017–2026 (tam) | +747.5% | +425.7% | 10/16 |
| 2023–2026 (OOS) | +60.5% | +128.9% | 7/16 |
| **2025–2026 (mevcut düşüş)** | **−11.2%** | **−53.5%** | **14/16** |

**Bu ne anlama geliyor?**
- **Boğa piyasasında:** al-tut'un gerisinde kalır (piyasada tam kalmıyor).
- **Düşüş piyasasında:** al-tut'u 14/16 seride geçer ve anaparayı büyük ölçüde korur.
- **Risk ayarlı:** 4h'de Calmar 0.83 vs 0.27 — yani birim risk başına 3 kat daha iyi.

Yani "her zaman daha çok kazandıran" bir strateji yok; **daha az kaybettiren** bir strateji var.
Uzun vadede fark, düşüşlerden korunmaktan gelir.

### Her stratejinin en iyi zaman dilimi

Her strateji **BTCUSDT** üzerinde 15m / 1h / 4h / 1d periyotlarında ölçüldü
(20.000 mum, gerçek motor, komisyon + kayma). En iyi periyot, **al-tut'a göre fark**
(+ düşüş kazancı) en yüksek olan periyottur. Sonuçlar kütüphane kartlarında
**"en iyi 4h"** gibi bir etiketle gösterilir; etiketin üzerine gelince tüm periyotların
getirisi/al-tut farkı görünür.

| Strateji | En iyi | Al-tut'a göre fark |
|---|---|---|
| EMA Trend Kesişimi | **4h** | +1025 |
| Trend Sürücü | **4h** | +1007 |
| Sadece Yükseliş | **4h** | +836 |
| Sadece Yükseliş 4h | **4h** | +798 |
| Kırılım Takipçisi | **4h** | +141 |
| T3 + QQE Pro Max | **4h** | −242 (düşüş %46 vs %82; risk ayarlı daha iyi) |
| T3 + QQE Pro | **1h** | −1463 |
| Super_Trend (hazır) | **1h** | +29 |
| Tillson T3 & QQE MOD | **1d** | +49 |
| TSO (hazır) | **1d** | +654 |
| VAMA (hazır) | **15m** | +11 |
| Diğer hazır stratejiler (BB_*, MACD, CCI_ATR, DMI, FDI, VMI…) | 15m | negatif (al-tut'un gerisinde) |
| Local_Min_Max (hazır) | ölçülemedi | aşırı/uçuk sonuç — güvenilmez |

> **Not:** "zayıf" etiketli stratejiler kendi en iyi periyodunda bile al-tut'un gerisinde
> kalır. Yani o stratejiler bu veri setinde kârlı değil; etiket yalnızca "en az kötü"
> periyodu gösterir.

Etiketler `strategy_timeframes` ayarında saklanır. Strateji kurallarını değiştirdikten
sonra ölçümü yenilemek için `measure_timeframes` betiğini çalıştırın.

### Risk kuralları: stop, takipli stop, kâr al, kâr koruma

**Tüm risk ayarları paneldedir:** Botlar → Yeni bot / Düzenle → adım 5 **Risk koruması**.
Aç/kapat anahtarlarının altındaki **Sayısal kurallar** alanında stop, takipli stop,
kâr al, kâr koruma ve cooldown değerleri bot bazında girilir (`0` = kapalı).
Backtest ve canlı bot **aynı** değerleri kullanır; backtest formu boş bırakılırsa
botun/stratejinin risk bloğu uygulanır.

| Ayar | Anlamı |
|---|---|
| `stop_atr` | Girişten **n × ATR(14)** aşağıda sabit stop |
| `max_stop_pct` | ATR stopun girişten en fazla **%n** aşağıda olması (felaket koruması) |
| `trail_atr` | Pozisyonun **mum zirvesinden (high)** n × ATR aşağıda takipli stop (kârı kilitler) |
| `trail_after_pct` | Takipli stop ancak kâr **%n**'yi aştıktan sonra devreye girer (erken pullback'te kesmez) |
| `profit_exit_donchian` | **Kâr koruma:** pozisyon kârdayken **n mumluk Donchian dibi** kırılırsa çık |
| `take_profit_atr` | Girişten **n × ATR** yukarıda kâr al |
| `take_profit_pct` | Girişten **%n** yukarıda kâr al |
| `breakeven_pct` | Kâr **%n**'yi geçince stop en az giriş fiyatına çekilir |
| `partial_tp_pct` | Kâr **%n**'ye ulaşınca pozisyonun bir kısmı satılır; kalan takibe devam eder |
| `partial_tp_fraction` | Kısmi satışta satılacak oran (0,5 = yarısı); kısmi hedef sonrası stop girişe çekilir |
| `risk_per_trade_pct` | Pozisyon boyutu stop mesafesine göre: stop vurulursa kaybedilecek nakit **%n** (`0` = nakit × pozisyon yüzdesi) |
| `static_stop_pct` | `static_stop` açıkken sabit stop yüzdesi (varsayılan %2,5) |
| `cooldown` | Çıkıştan sonra **n mum boyunca yeni giriş yok** (komisyon erozyonunu önler) |
| `cooldown_min_loss_pct` | Cooldown yalnızca çıkış K/Z'si **-%n** veya daha kötüyse uygulanır (`0` = her çıkışta) |

- Birincil çıkışlar **stop, takipli stop, breakeven, kâr al, kâr koruma ve sinyaldir**. **Zaman limiti tamamen kaldırıldı.**
- **Kâr al (ATR/yüzde) artık canlı/paper botlarda da uygulanır**; daha önce yalnızca backtest'te çalışıyordu.
  Panelde "Kâr al" anahtarı kapatılırsa sayısal hedefler devre dışı kalır.
- Eski **ortalama K/Z tabanlı kâr al** kaldırıldı (kârın büyük kısmını geri veriyordu); yerine
  takipli stop, Donchian kâr koruma, breakeven ve kısmi kâr hedefleri var.
- **Destek / dinamik / sabit stop artık backtest'te de aynı kurallarla çalışır.** Destek stop
  yalnızca son **300 mumu** tarar (`support_lookback`) ve seviyeler her **10 mumda** bir
  yenilenir (`support_refresh`); arada saklanan seviye her mumda kontrol edilir.
- Stop ve kâr hedefi **mum içi high/low** ile kontrol edilir (sadece kapanış değil) ve çıkış
  **seviye fiyatından** yapılır (backtest ve canlı aynı; ikisinde de kayma uygulanır).
- Aynı mumda hem stop hem kâr hedefi vurulursa **stop önceliklidir** (kötümser varsayım).
- Kısmi kâr sonrası kalan pozisyonun stopu en az girişe çekilir; böylece kalan kısım zarara dönemez.
- `cooldown` olmadan stop sonrası aynı sinyal hemen yeniden girer; bu yüzden zorunludur.
- Backtest sonucunda **pozisyon süreleri** kartı: ortalama/medyan/en uzun tutuş (gün-saat),
  uygulanan risk kuralları ve **çıkış nedenleri** (sinyal, stop, takipli stop, kâr koruma).
- Bot oluştururken risk alanı boş bırakılırsa **stratejinin kendi risk bloğu** devralınır.

#### Neden geç çıkıyordu? (ve çözümü)

Pozisyon yalnızca **20 mumluk Donchian dibi** veya **SuperTrend dönüşü** ile kapanıyordu.
Bu ikisi de trendin **döndüğünü onaylayan yavaş sinyaller**: zirve yaptıktan sonra fiyatın
20 mumun dibinin altına inmesini bekliyorlar. Sonuç: kârın büyük kısmı zirveden sonra geri
veriliyordu (4h BTC'de işlem başına ortalama **%7,6**, XRP'de **%12,7** geri veriliyordu;
zirveden çıkışa kadar ortalama **18 / 25 mum** geçiyordu).

**Çözüm — kâr koruma (`profit_exit_donchian`):** pozisyon kârdayken daha kısa vadeli
**Donchian(10)** dibi kırılırsa çıkılır. Kural yalnızca **kârdayken** devreye girdiği için
trend sürerken pozisyonu kesmez; sadece kârı geri vermeye başlayınca hızlıca kapatır.
Kırılımın **yeni** olması gerekir (önceki kapanış bandın üstünde, bu kapanış altında).

Tüm geçmiş, üretim motoru, kâr koruma **kapalı → açık**:

| Strateji | Getiri (kapalı → açık) | Maks. düşüş | İşlem | Kazanma | Ort. tutuş |
|---|---|---|---|---|---|
| 4h BTC | **+2546% → +2166%** | **%51,4 → %44,0** | 135 → 155 | %42 → %54 | 57,7 → **43,2 mum** |
| 4h XRP | **+1503% → +2410%** | %62,7 → %65,9 | 115 → 130 | %33 → %44 | 54,0 → **41,8 mum** |
| 1d BTC | +1139% → **+1261%** | %51,0 → %53,0 | 42 → 46 | %48 → %50 | 34,2 → **26,2 gün** |
| 1d XRP | +195% → **+303%** | %70,7 → %70,7 | 40 → 40 | %33 → %35 | 19,1 → 19,1 gün |

Yorumu dürüstçe: **3/4 durumda getiri arttı**, 4h BTC'de getiri bir miktar düştü ama düşüş
7,4 puan azaldı ve kazanma oranı %42 → %54 oldu (risk ayarlı getiri/Calmar daha iyi).
Bu yüzden 4h ve 1d stratejilerinde açık. **1h ve 15m'de kapatıldı:** orada hızlı çıkış
gürültüyle sürekli tetiklenip getiriyi yok ediyordu (1h BTC +3372% → +761%, 15m +68% → negatif).

**Not:** kâr koruma çıkışları tabloda `profit-exit` olarak, canlı botta `kâr-koruma` olarak görünür.

**Kütüphanedeki diğer stratejiler:** `risk` bloğu eklemek her stratejide mümkündür. Tam geçmişte
denenip **kazançlı çıkan tek ek durum** `T3 + QQE Pro Max` (4h) oldu: 5×ATR stop +
**Donchian(30)** kâr koruma. BTC düşüşü %82 → %46 (getiri +480% → +532%), XRP getirisi
+1238% → **+2457%** (düşüş %69 → %65). Diğerlerine dokunulmadı: `1h` ve `15m` kısa vadede
kâr koruma getiriyi yok ediyor; `Tillson T3` (1d) ve `T3 + QQE Pro` (1h) stratejilerinde
stop/kâr koruma ölçülen getiriyi düşürüyor (kendi çıkış sinyalleri zaten yeterince hızlı).

### Dört periyot için stop'lu stratejiler (zaman limiti yok)

**Tasarım:** birincil çıkışlar **stop, takipli stop, kâr koruma ve sinyal**dir. **Zaman limiti kaldırıldı** —
pozisyon yalnızca sinyal veya stop ile kapanır. Her stratejide çıkış sonrası **10 mum bekleme
(cooldown)** vardır; bu olmadan aynı sinyal hemen yeniden girip komisyon erozyonu yaratıyordu.

Kısa periyotlarda **dar stop zararlı**: 15m/1h gürültüsünde sürekli tetiklenip kârı yok ediyor.
Bu yüzden 15m ve 1h'de geniş "felaket koruması" stopları kullanılıyor ve kâr koruma kapalı.

| Periyot | Strateji | Giriş | Stop / takipli | BTC | XRP | Ort. tutuş |
|---|---|---|---|---|---|---|
| **4h** | **4h Kırılım Swing** | son 20 mum zirvesi + EMA200 üstü | **5×ATR stop** + **kâr koruma Donchian(10)** | **+2166%** vs +774% | **+2410%** vs +245% | **7,2 gün** |
| **1h** | 1h Kısa Vade | SuperTrend(20, ×5) yukarı + EMA200 | 20×ATR stop + **25×ATR takipli** | **+3372%** vs +1618% | **+1161%** vs +84% | 27–41 gün |
| **15m** | 15m Kısa Vade | SuperTrend(10, ×5) yukarı + EMA200 + **RSI(14)<70** | 30×ATR stop (felaket koruması) | **+1042%** vs +734% | **+876%** vs +308% | 14–19 gün |
| **1d** | 1d Kırılım Pozisyon | son 20 gün zirvesi | 2×ATR stop + **8×ATR takipli** + **kâr koruma Donchian(10)** | **+1261%** vs +1192% | **+303%** vs +114% | 26 / 19 gün |

BTCUSDT/XRPUSDT, **tüm geçmiş**, gerçek motor, %0.1 komisyon + %0.05 kayma.

**Düşüş (BTC / XRP):** 4h 44%/66% · 1h 63%/77% · 15m 57%/76% · 1d 53%/71%
— hepsi al-tut'un (83–85%) belirgin altında.

**Dürüst değerlendirme:**

- **4h Kırılım Swing açık ara en iyi.** İki coinde de al-tut'u 3–10 kat geçer, düşüş yarı yarıya az,
  ortalama tutuş **7,2 gün**. **Bunu kullanın.**
- **1h** iki coinde de al-tut'u büyük farkla geçer (BTC +3372% vs +1618%, XRP +1161% vs +84%). Tutuş 27–41 gün.
- **15m** RSI(14)<70 giriş filtresi eklendikten sonra iki coinde de al-tut'u belirgin geçer
  (BTC +307, XRP +568 puan) ve düşüş **6–9 puan** azalır (işlem sayısı da azalır: 96→92 / 77→73).
  Filtre, trendin sonuna (aşırı alım) denk gelen geç girişleri eler. 250.000 mumla değerlendirin;
  kısa pencerede sonuç negatife dönebilir.
- **1d** artık iki coinde de al-tut'un önünde (BTC +1261% vs +1192%, XRP +303% vs +114%),
  düşüş 30 puan az. Günlükte al-tut'u geçmek için yıllarca tutmak gerekir; takipli stop bunu
  26/19 güne indiriyor.
- Çıkış dağılımı (4h BTC): **65 kâr koruma / 81 sinyal / 9 stop** — kâr koruma en sık çıkış nedeni,
  stop ise gerçekten nadiren tetikleniyor.

**Coin'e özel 15m sürümleri (uzun deneme sonucu):** 15m'de BTC ve XRP farklı davranıyor.
Paylaşılan **15m Kısa Vade** dengeli bırakıldı (iki coinde de al-tut'u geçer); yanına iki uzman
sürüm eklendi. Her biri üç ayrı pencerede (son 1,4 yıl / son 2,8 yıl / tam geçmiş) ölçüldü.

| Strateji | Ek giriş koşulu | Tam geçmiş | Son 2,8 yıl | İşlem |
|---|---|---|---|---|
| 15m Kısa Vade (paylaşılan) | — | BTC **+1039%** / XRP **+874%** | +65 / +92 | 92 / 73 |
| **15m Kısa Vade (BTC)** | Bollinger `percent_b` < 0,9 | BTC **+1191%** (dd %57) | **+72%** (al-tut +59) | 90 |
| **15m Dip Alım (XRP)** | kapanış < EMA50 (trende geri çekilme) | XRP **+1734%** (dd %70) | **+126%** (al-tut +76) | 73 |

- **15m Kısa Vade (BTC)** Bollinger filtresi BTC'de üç pencerede de temel sürümden iyi; XRP'de son
  dönemde eşit, tam geçmişte bir miktar geride (+769% vs +874%). BTC botlarında bunu kullanın.
- **15m Dip Alım (XRP)** XRP'de üç pencerede de temel sürümden iyi ve daha az işlem yapıyor
  (son 2,8 yıl +126%, düşüş %53). **BTC'de zayıftır** (tam geçmiş +741%, son 2,8 yıl al-tut'un
  altında) — BTC botlarında kullanmayın.
- Reddedilenler (tek coinde iyi, diğerinde kötü → aşırı uyum): hızlı SuperTrend ile çıkış,
  EMA200 mesafesi/eğimi filtreleri, hacim eşiği (0,7'de keskin tepe), MACD/ADX/RSI momentum
  onayları, stop 25/35×ATR, RSI 60/65.

### 15m Kısa Vade Pro (genel 15m sürümü)

| Kural | Ne yapar |
|---|---|
| **AL** — SuperTrend(10, ×5) yukarı + fiyat EMA200 üstünde + RSI(14)<70 + **RSI(2)<20** + **BB percent_b < 0,7** | Yükseliş trendindeki dibi alır; dip bandın alt kısmında olmalı |
| **SAT** — SuperTrend aşağı dönünce | Trend dönüşünde çıkar |
| **STOP** — **35×ATR, en fazla %15** + 10 mum bekleme | Yalnız felaket koruması; yüksek oynaklıklı coinlerde stop %97'ye inmesin diye tavan var |

**Sürüm karşılaştırması** (BTC/XRP, tam geçmiş 250.000 mum):

| Sürüm | BTC fark | XRP fark | En zayıf bacak | Not |
|---|---|---|---|---|
| v1 — RSI(2) dibi | +288 | +608 | +288 | temel |
| v2 — + percent_b<0,5, stop30 | +205 | **+883** | +205 | **en yüksek toplam** (1.088) |
| **v3 — percent_b<0,7, stop35** | **+422** | +544 | **+422** | **en dengeli (seçili)** |
| **v4 — + stop tavanı %15** | sürüm 4 | — | — | **stop işlevli hâle geldi (canlıda uygulanan)** |

**v3 sonucu (tam geçmiş):** BTC **+1146%** (al-tut +724%, düşüş **%55 vs %77**, Calmar 0,78),
XRP **+851%** (al-tut +306%, düşüş %76 vs %85). 6 coin × 150.000 mum: 5/6 seride al-tut'u geçer;
hold-out (AVAX, DOT): 2/2. v2 toplam farkı en yüksek sürüm olarak sürüm geçmişinde duruyor.

- Temel `15m Kısa Vade` (v8) ile BTC'de eşdeğer, **XRP'de daha iyi** (+914% vs +874%).
- Coin'e özel sürümler hâlâ daha yüksek getiri verir: XRP → `15m Dip Alım (XRP)` (+1734%),
  BTC → `15m Kısa Vade (BTC)` (+1191%).
- 15m gürültülü olduğu için sonucu **250.000 mumla** değerlendirin; kısa pencerede al-tut öne geçebilir.

### Genel Dip-Trend (tek kural seti, birçok coin)

**Amaç:** tek bir stratejiyle farklı coin'lerde çalışmak; **dipten al, tepe dönüşünde sat,
beklenmedik düşüşte erken dur.**

| Kural | Ne yapar |
|---|---|
| **AL (dip)** — **SuperTrend(10, ×5) yukarı** + **RSI(2) < 20** + fiyat **EMA200 üstünde** | Yükseliş trendindeki kısa vadeli aşırı satımı (dibi) alır |
| **AL (geri giriş)** — **SuperTrend yeniden yukarı dönerse** + EMA200 üstünde | Çıkıştan sonra trend devam ederse kaçırmaz |
| **SAT** — **SuperTrend aşağı dönünce** | Tepe dönüşünde çıkar; trendi erken bırakmaz |
| **STOP** — **5×ATR** + çıkış sonrası 10 mum bekleme | Beklenmedik düşüşte fazla kaybettirmeden çıkar |

Ölçüm: **6 coin** (BTC, ETH, SOL, XRP, ADA, DOGE) × 3 periyot = 18 seri, gerçek motor:

| Periyot | Al-tut'u geçen | Kârlı seri | Örnek (BTC) |
|---|---|---|---|
| **1h** | **6/6** | — | +50% vs +9% · düşüş %36 vs %54 |
| **4h** | **4/6** | — | +812% vs +367% · düşüş %65 vs %81 |
| 1d | 1/6 | — | +492% vs +1260% |
| **Toplam** | **11/18** | **13/18** | medyan fark **+38** · medyan Calmar **0,24** |

**Hold-out uyarısı (önemli):** Ayarda **hiç kullanılmayan** BNB ve LINK'te (1h/4h) strateji
yalnızca **1/4** seride al-tut'u geçti. Güçlü boğa koşularında (BNB 4h al-tut +5886%) nakitte
kalıyor. Yani 11/18 sonucu **görülmemiş coinlere genellenmiyor**; kural seti ayar setine
uydurulmuş durumda (overfit). Bu yüzden:

- Bunu **ana strateji olarak değil**, 1h/4h'de **düşük düşüşlü bir yardımcı/deneme** olarak kullanın.
- Yüksek getiri için periyoda özel `4h Kırılım Swing`, `1h Kısa Vade`, `1d Kırılım Pozisyon`
  veya coin'e özel stratejiler gerekir.
- Bu aile (dip al → tepede sat → erken stop) **6 tur, 250+ varyant** ile denendi: tek kural
  setiyle en iyi 11/18, hold-out'ta 1/4. Daha fazla parametre kurcalamak overfit'i büyütüyor;
  bu yüzden burada duruldu.

### Genel Trend Takipçisi (önerilen genel strateji)

Dip ailesinin hold-out'ta çöktüğü yerde, trend takibi genelleniyor. Tek kural seti, 10 coin:

| Kural | Ne yapar |
|---|---|
| **AL** — kapanış, **önceki mumun DONCHIAN(20) üst bandını** yukarı keser **VE** fiyat **EMA200 üstünde** | Yükseliş trendinde 20 mumluk zirve kırılımına katılır |
| **SAT** — kapanış **EMA200 altına** inerse | Trend bozulunca çıkar (tepeden sonra, trend dönüşünde) |
| **STOP** — **5×ATR** + çıkış sonrası 10 mum bekleme | Beklenmedik düşüşte fazla kaybettirmeden çıkar |

Ölçüm: **10 coin** (6 ayar + **4 hold-out**: AVAX, DOT, BNB, LINK) × 1h/4h/1d = **30 seri**:

| Set | Al-tut'u geçen | Kârlı seri | Medyan fark |
|---|---|---|---|
| Ayar (6 coin) | 11/18 | 14/18 | **+108** |
| **Hold-out (4 coin)** | **8/12** | 7/12 | **+69** |
| **Toplam** | **19/30** | **21/30** | +88 |

- **4h en güçlü:** BTC **+2655%** (al-tut +367%, düşüş %39 vs %81), ETH +2451%, SOL +15701%,
  ADA +1676%, DOGE +3960%, XRP +170%; hold-out'ta AVAX +3743%, DOT +369%, LINK +2003%,
  BNB +2187% — **4h'de 4/4 hold-out coini kârlı**.
- **1h karışık:** ADA/DOGE/XRP al-tut'u geçer; BTC/ETH/BNB geride.
- **1d karışık:** ADA/SOL/AVAX/DOT/LINK iyi; BTC/XRP/BNB al-tut'un gerisinde.
- **15m'de önerilmez** (1.678 işlem, −95%).
- En güçlü boğa koşularında (BNB 4h al-tut +5929%) trende geç girdiği için geride kalır; karşılığında
  düşüş al-tut'un ~%80'i ve medyan fark hem ayar hem hold-out setinde **pozitif** (yani genelleniyor).

### Backtest: al ve tut karşılaştırması

Her backtest sonucunda **"hiç satmasaydım ne olurdu?"** ölçüsü de hesaplanır:

- Başlangıç mumunda alış (komisyon + kayma dahil), son mumda değerleme
- Getiri (%), son portföy değeri (USDT), maksimum düşüş (%), başlangıç/bitiş fiyatı
- Strateji getirisi ile fark (puan) ve "hangisi daha iyi" değerlendirmesi
- **CAGR** (yıllık bileşik getiri) ve **Calmar** (CAGR / maks. düşüş) — risk ayarlı karşılaştırma
- **Yıl bazında** tablo: her yıl strateji, al-tut ve fark
- Bakiye grafiğinde **gri kesikli çizgi** al-tut eğrisini gösterir

**Grafikte işlem noktaları:** Sonuç ekranında **"Fiyat ve işlem noktaları"** grafiği vardır.

- **Fare tekerleği** ile imlecin olduğu yere doğru yakınlaşır/uzaklaşır
- **Sürükle** (sol tuş) ile zaman ekseninde kaydırılır
- **＋ / − / Sıfırla** düğmeleri de aynı işi yapar
- Yakınlaştıkça **mum grafiği** (açılış/yüksek/düşük/kapanış) çizilir; uzakta çizgi görünümü
- Her işlem **numaralı üçgenle** işaretlenir: **▲ yeşil** = alım, **▼** = satım
- **Satış üçgeninin rengi çıkış nedenini söyler:**

  | Renk | Neden |
  |---|---|
  | 🔴 kırmızı `#fb7185` | **sinyal satışı** (strateji çıkış sinyali) |
  | 🟠 turuncu `#f97316` | **stop / takipli stop** |
  | 🩵 camgöbeği `#22d3ee` | **kâr koruma** (Donchian kırılımı) |
  | 🟢 yeşil `#34d399` | **kâr al** |
  | ⚪ gri `#94a3b8` | **test sonu** (pozisyon kapanmadan bitti) |

- Grafiğin üstünde **renk açıklaması (legend)** ve yalnızca o backtest'te kullanılan nedenler görünür
- Üçgenin üzerine gelince **işlem no, tarih, fiyat, K/Z ve çıkış nedeni** görünür
- Alım ile satım arasındaki **ince çizgi** o işlemi birleştirir; çizgi rengi çıkış nedeninin rengidir
- Alt eksende **tarih etiketleri**, üstte görünen işlem/mum sayısı ve görünüm tipi yazar
- **İşlemler tablosunda satıra tıklayınca** grafik o işleme yakınlaşır (iç içe girmiş işlemleri
  tek tek incelemek için)
- Bakiye eğrisinde de aynı numaralı ▲/▼ işaretleri bulunur

**Varsayılan pencere 20.000 mumdur.** Trend stratejileri kısa pencerede anlamlı ölçülemez;
3.000 mumluk 1h dilimi yalnızca ~4 aydır ve orada al-tut önde görünebilir. Seçenekler:
3.000 / 5.000 / 10.000 / 20.000 / 50.000 / 100.000 / **250.000** mum. API tarafında 1.000
üstü istekler otomatik sayfalanır (en fazla 250.000 mum). Seçtiğiniz sayının gerçekten
geldiğini **veri raporundan** doğrulayın.

---

### Sayfa geçişleri (yönlendirme güvencesi)

Sayfa geçişlerinde **aynı anda yalnızca bir sayfa render edilir**:

- `route()` serileştirilmiştir (`state.routeBusy`). Render sürerken yeni bir gezinme gelirse istek
  birleştirilir ve render bitince **en son hedef** çizilir; iki render aynı anda `#content`'e yazamaz.
- Her gezinmede eski içerik **beklemeden** temizlenir (`Yükleniyor…`), böylece önceki sayfa takılı kalmaz.
- Arka plan yenilemeleri (dashboard 15 sn, botlar 15 sn, anlık K/Z 5 sn, iş monitörü 4 sn) render
  sürerken **devre dışıdır**; botlar sayfası için tek bir yenileme timer'ı vardır (çift timer yok).
- Render hata verse bile görünüm işaretlenir (`state.renderedView`), sonraki geçiş doğru karar verir.

Bu davranış `tests/test_frontend_routing.py` ile korunur (serileştirme bayrakları, senkron temizlik,
tek timer, `routeBusy` kontrolleri, eski `innerHTML` yamasının kaldırılmış olması).

## Regresyon testi (snapshot)

**Sistem → Regresyon testi** bölümü, koddaki bir değişikliğin çıktıları bozup bozmadığını
kanıtlar. Bir kez **referans kaydı** oluşturulur; sonra her değişiklikten sonra **Doğrula**
denir.

Kayda girenler (varsayılan 20.000 mum):

| İçerik | Ayrıntı |
|---|---|
| **Fiyat geçmişi** | open/high/low/close/volume/opendate + SHA-256 (dosya bozulursa yakalanır) |
| **İndikatör değerleri** | Katalogdaki **tüm** indikatörler, varsayılan parametrelerle, **tüm çıktılarıyla** (ör. BB: upper/middle/lower/width/percent_b) |
| **Strateji sinyalleri** | Tüm özel (arşiv dahil) + hazır stratejiler; her mum için AL/SAT sinyali + sürüm/pin bilgisi |
| **Meta** | Python/numpy/pandas sürümleri, tarih, not |

Doğrulama, kayıtlı fiyatları kullanarak her şeyi yeniden üretir ve **birebir** karşılaştırır
(varsayılan tolerans `1e-12`; sadece float ilişkilendirme gürültüsünü yok sayar). Fark varsa:

- **hangi indikatör/strateji**, kaç değerde, **ilk hangi mumda**,
- **beklenen** ve **şimdiki** değer,
- stratejilerde AL/SAT ayrımı

raporlanır. Örnek gerçek test: `SMA` formülüne %0,00001 sapma eklendiğinde sistem
`SMA(length=20)`, `VOLUME_SMA(length=20)` ve `VOLUME_SMA(...).ratio` olarak **tam olarak
etkilenen üç indikatörü** ilk mum `19` ile gösterdi; kod geri alınınca doğrulama yeniden
"birebir aynı" oldu.

- Kayıt 20.000 mum için ~6,8 MB (gzip) ve ~40 sn; doğrulama ~30 sn. İkisi de **iş kuyruğunda**
  çalışır, ilerleme yüzdesi gösterilir.
- Kütüphane sürümü değiştiyse (ör. numpy) sonuçta **uyarı** olarak listelenir; bu, gerçek kod
  hatasıyla karışmaması için.
- Dosyalar `Data/snapshots/` altında tutulur; arayüzden silinebilir.

## Yedekleme ve geri yükleme

**Sistem → Yedekleme** bölümü varsayılan olarak **minimal** bir `.zip` arşivi üretir:
yalnızca sistemin çalışması için gerekli olanlar.

| İçerik | Açıklama |
|---|---|
| `tradeai.db` | **Botlar, stratejiler, ayarlar, coin listeleri**, işlemler (tutarlı kopya) |
| `Data/.secret_key` | Panelde şifreli saklanan ayarların (API anahtarları vb.) anahtarı |
| `Data/coin_list.txt` | Eski/uyumluluk coin listesi |
| `Data/Strategy/strategys.json` | Eski/uyumluluk strateji dosyası |
| `state/<bot_id>.json` | Yalnızca **mevcut botların** açık pozisyon/nakit durumu |

Varsayılan olarak **girmez** (isteğe bağlı kutular / CLI bayrakları ile eklenir):

| Seçenek | İçerik | CLI |
|---|---|---|
| Regresyon kayıtları | `Data/snapshots/` (genelde MB'larca) | `--snapshots` |
| AI modelleri | `Data/Model/` | `--models` |
| Büyük veri dosyaları | `.csv/.xlsx/.parquet` (boyut sınırı yok) | `--datasets` |
| Bot logları | `Log/bots/` | `--logs` |
| `.env` | API anahtarları (düz metin) | `--env` |

Böylece `Data/` altındaki GB'lık geçmiş dökümler, model dosyaları, regresyon
kayıtları ve alakasız dosyalar yedeğe girmez; tipik arşiv ~8 MB (DB sıkışmış).

> `Data/.secret_key` yedeğe dahildir; panelde kayıtlı şifreli API anahtarlarının
> çözülebilmesi için gereklidir. Arşivi paylaşırken bunu göz önünde bulundurun.

- Yedekler **`Data/backups/`** altında tutulur. Bu klasör host'a mount edilir,
  yani `docker compose up -d` / yeniden derleme yedeği silmez.
- Arşivler arayüzden **indirilebilir**, **yüklenebilir** ve silinebilir.
  Bilgisayarınızdaki `.zip` dosyasını **Sistem → Yedekleme → Yükle** ile gönderin;
  `docker cp` gerekmez. Aynı adda arşiv varsa yükleme `409` ile reddedilir
  (önce eskiyi silin veya dosyayı yeniden adlandırın).
- Oluşturma ve geri yükleme **iş kuyruğunda** çalışır; ilerleme gösterilir.
- Geri yükleme kullanıcıları da değiştirdiği için **oturum kapanır**; yedekteki
  kullanıcı bilgileriyle yeniden giriş yapılır.

**Sıfırdan kurulumda yedekten dönme** (tamamen web):

1. Yeni makinede `docker compose up -d --build` ile açın, `.env`'de yalnızca
   `ADMIN_PASSWORD` ve `TRADEAI_PORT` belirleyin (`TRADEAI_SECRET_KEY` boş kalsın;
   yedekteki `Data/.secret_key` kullanılır).
2. Giriş yapın → **Sistem → Yedekleme → Yükle** ile `.zip` dosyasını gönderin.
3. Listede **Geri yükle** → onaylayın. Botlar durdurulur, önce `pre-restore_*.zip`
   güvenlik yedeği alınır.
4. Oturum kapanırsa **yedekteki admin kullanıcı/şifresiyle** giriş yapın.
5. **Botlar** sayfasından botları başlatın.

**Geri yükleme** (arayüzdeki *Geri yükle* veya CLI):

1. Çalışan tüm botlar durdurulur (DB değiştirilirken bozulmayı önler).
2. Mevcut veri otomatik olarak `pre-restore_*.zip` güvenlik yedeğine alınır;
   yanlış yedek seçilirse geri dönülebilir.
3. SQLite `-wal/-shm/-journal` dosyaları temizlenir, arşiv açılır.
4. Yedekteki botlar `stopped` işaretlenir; **Botlar** sayfasından yeniden başlatılır.

```bash
# Container içinde
docker exec -it tradeai python -m app.backup create --note "v4 öncesi"
docker exec -it tradeai python -m app.backup list
docker exec -it tradeai python -m app.backup restore <dosya>.zip
docker exec -it tradeai python -m app.backup where    # klasör yolu

# Yedeği bilgisayara al / geri koy
docker cp tradeai:/app/Data/backups/<dosya>.zip .
docker cp <dosya>.zip tradeai:/app/Data/backups/
```

Güvenlik: arşiv adları dizin dışına çıkamaz (`..`, alt dizin reddedilir) ve
geri yükleme zip-slip içeren arşivleri reddeder. Yükleme geçici `.part` dosyasına
yazılır; yalnızca geçerli ZIP (en az `tradeai.db` veya `Data/`) kabul edilir ve
4 GB üstü yüklemeler reddedilir. Davranış `tests/test_backup.py` ile korunur
(19 test: içerik, DB bütünlüğü, güvenlik yedeği, bot durdurma, zip-slip,
kendi kendini yedeklememe, minimal kapsam, yükleme doğrulama/limit/çakışma).

## İstatistikleri sıfırlama

**Ayarlar → Güvenlik → Tehlikeli işlemler** ve **İşlem geçmişi** sayfasındaki
**İstatistikleri sıfırla** düğmesi, birikmiş istatistikleri temizler. Şifre ve
`SIFIRLA` onay metni zorunludur; tüm botlar için ya da tek bir bot seçilerek yapılır.

Silinenler:

| Veri | Açıklama |
|---|---|
| İşlem geçmişi | `trades` → K/Z, kazanma oranı, coin/bot grafikleri sıfırlanır |
| Kapanmış pozisyonlar | `positions` (`status<>'open'`) |
| K/Z grafik verileri | `pnl_snapshots` |
| Sinyal geçmişi | `signal_events` |
| Olay/log geçmişi | `events` |
| Bitmiş iş kayıtları | `jobs` (yalnızca tüm botlar sıfırlanırken) |

Korunanlar: **açık pozisyonlar ve nakit**, stratejiler, ayarlar, coin listeleri.
Botların birikmiş K/Z sayacı (`total_realized_pnl`) 0'lanır; sayacın yeniden
yazılmaması için hedef botlar **durdurulur** ve sonra Botlar sayfasından başlatılır.
Sıfırlama işlemi denetim için tek bir olay kaydı bırakır. Davranış
`tests/test_reset_stats.py` ile korunur.

## Performans
Ölçümler gerçek motorla yapıldı (250.000 mumluk backtest, Docker içinde):

| Ölçüm | Önce | Sonra | Kazanç |
|---|---|---|---|
| 250k mum backtest | **85 sn** | **6,3 sn** | **13,5×** |
| 4 strateji / 20-50k mum toplam | 5,5 sn | 3,2 sn | 1,7× |
| Bot süreci belleği | 235 MB | **106 MB** | −%55 |
| Web süreci belleği | 182 MB | **128 MB** | −%30 |

Yapılanlar (hepsi dil değişmeden, Python'da):

1. **Operand önbelleği**: her koşulda `json.dumps` ile anahtar üretiliyordu (3 milyon çağrı) →
   `id(operand)` anahtarına geçildi. Tek başına ~35 sn.
2. **Backtest'te detay metni üretilmemesi**: `evaluate_at(detail=False)`. Okunur koşul
   açıklamaları yalnızca sinyal kaydederken/preview'de üretilir.
3. **Kısa devre**: AND'de ilk `false`, OR'de ilk `true` sonrası kalan koşullar hesaplanmaz
   (indikatörler saf olduğu için sonuç değişmez).
4. **Bollinger std**: pencere başına `np.std` döngüsü (O(n·w)) → kümülatif toplamla O(n).
5. **Super Trend**: pandas `DataFrame` + satır satır `.iloc` erişimi → numpy.
6. **matplotlib tembel yükleme**: bot grafik çizmediği hâlde her süreçte yükleniyordu (−25 MB/süreç).
7. **Önceki mum değerleri** yalnızca kesişim/trend operatörlerinde hesaplanır.

**Doğruluk garantisi:** Optimizasyonlar `tests/test_perf_correctness.py` ile korunur —
Bollinger ve SuperTrend **referans (saf) uygulamalarla** 1e-9 toleransla karşılaştırılır;
kısa devre ile detaylı modun aynı sinyali verdiği ve operand önbelleğinin tek hesaplama
yaptığı da test edilir. Ek olarak 10 vakalık altın referans (backtest çıktısının SHA-256'sı
dahil) değişikliklerden önce/sonra birebir aynı çıktı.

**Rust/Go'ya taşımak gerekir mi?** Bu iş yükünde hayır: bot CPU'su %0,2 (mum kapanışını
bekliyor), darboğaz dil değil algoritmaydı. Kalan Python maliyeti yorumlayıcı katmanıdır ve
yukarıdaki düzeltmelerle 13,5× kazanç sağlandı; yeniden yazım test edilmiş pariteyi
(backtest = canlı) bozma riski taşır.

## Güvenlik

- `scrypt` ile şifre hash'i (ek bağımlılık yok).
- Sunucu tarafı oturum + `HttpOnly`, `SameSite=Lax` cookie.
- Durum değiştiren isteklerde CSRF token zorunlu.
- 5 hatalı girişte 15 dakika hesap kilidi.
- Tehlikeli manuel işlemlerde (tümünü kapat / full nakit) şifre tekrar doğrulaması.
- Varsayılan olarak yalnızca yerel arayüze yayın.

---

## Karşılaştırma operatörleri

| Operatör | Anlamı | Formül |
|----------|--------|--------|
| `>` / `≥` / `<` / `≤` | Basit karşılaştırma | `a op b` (bu mum) |
| `=` / `≠` | Eşitlik | `a == b` (bu mum) |
| **Yukarı keser** | Bu mum yukarıda, önceki mum aşağıda/eşit | `a > b` **ve** `a_prev ≤ b_prev` |
| **Aşağı keser** | Bu mum aşağıda, önceki mum yukarıda/eşit | `a < b` **ve** `a_prev ≥ b_prev` |
| Yükseliyor / Düşüyor | Kendi önceki değerine göre | `a > a_prev` / `a < a_prev` |

**Eşitlik durumları (Yukarı keser):**
- **Önceki mumda eşitlik** (`a_prev == b_prev`) → kesişme **gerçekleşir** (koşul `≤` olduğu için).
- **Bu mumda eşitlik** (`a == b`) → kesişme **gerçekleşmez** (koşul `basit >` olduğu için).
- Bu mumda eşitlik olup sonraki mumda yukarı çıkarsa, kesişme **sonraki mumda** sayılır.

## Önceki mum değerini kullanma

Değer türü seçicisinde **Önceki mum** seçeneği vardır: bir indikatör, fiyat veya sayıyı
N mum önceki değeriyle karşılaştırır (`offset` operandı, `shift = 1..50`).

```
kapanış > kapanış (1 mum önce)          → fiyat önceki mumdan yüksek
RSI(14) > RSI(14) (1 mum önce)          → RSI önceki muma göre yükseldi
EMA(50) > EMA(50) (3 mum önce)          → EMA 3 mum önceye göre yüksek
```

Hızlı ekle çubuğundaki **+ Önceki mum** düğmesi tek tıkla böyle bir kural ekler; ayrıca
“Fiyat önceki mumdan yüksek/düşük” ve “RSI önceki mumdan yüksek/düşük” hazır kuralları vardır.

---

## Ayarlar (panelden)

Her şey **Ayarlar** sayfasından yönetilir; `.env` düzenlemek gerekmez. Panelden
kaydedilen değerler SQLite'ta tutulur ve **anında** geçerli olur (botlar dahil).

| Sekme | İçerik |
|-------|--------|
| İşlem | Canlı işlem sunucu izni, varsayılan mod, bakiye, test komisyon/kayma |
| Risk | Dinamik/sabit/destek stop, kâr al, maksimum mum varsayılanları |
| Strateji limitleri | Periyot başına en fazla strateji sayısı |
| Binance | API anahtarı/gizli anahtar (şifreli), ana parite, bağlantı testi |
| Bildirimler | E-posta + Telegram anahtarları ve test gönderimi |
| Sistem | Otomatik yeniden başlatma, heartbeat, iş limiti, AI |
| Coin listesi | İzlenen coinler |
| Güvenlik | Şifre değiştirme ve tehlikeli manuel işlemler |

Gizli değerler (API secret, e-posta şifresi, Telegram token) panelde **şifreli**
saklanır ve arayüzde yalnızca maskeli önizleme gösterilir. Boş bırakılan gizli
alan mevcut değeri korur; **Kaldır** düğmesiyle silinir.

`.env` yalnızca ilk varsayılanlar ve altyapı (port, secret key, admin) içindir.

---

## Ortam Değişkenleri

Tam liste için `.env.example` dosyasına bakın. Bunlar yalnızca **ilk varsayılan**
ve altyapı içindir; normal kullanımda panelden değiştirilir:

| Değişken | Açıklama |
|----------|----------|
| `ADMIN_USER` / `ADMIN_PASSWORD` | İlk yönetici hesabı |
| `TRADEAI_SECRET_KEY` | Oturum ve gizli ayar şifrelemesi |
| `TRADEAI_PORT` | Web portu (varsayılan 8080; `docker-compose.yml` host eşlemesi ve healthcheck aynı değeri kullanır) |
| `LIVE_TRADING_ENABLED` | Canlı işlem başlangıç izni (panelden değiştirilir) |
| `PAPER_FEE` / `PAPER_SLIPPAGE` | Test modu maliyetleri |
| `DEFAULT_CASH` | Yeni bot varsayılan nakdi |
| `BOT_AUTO_RESTART` | Çökmede otomatik başlatma |
| `MAX_JOBS` | Eşzamanlı ağır iş limiti |
| `AI_ENABLED` | AI profili |
| `EXIT_RETRY_SECONDS` | Başarısız satışın tekrar deneme aralığı (varsayılan 5 sn) |
| `RECONCILE_SECONDS` / `RECONCILE_TOLERANCE_PCT` | Çalışırken borsa mutabakatı sıklığı ve toleransı |
| `RECONCILE_STOP_ON_MISMATCH` | Mutabakat farkında botu durdur |
| `ADOPT_EXTERNAL_BUY` | Harici alımları botun pozisyonuna kat |
| `SHARED_ACCOUNT` | Aynı Binance hesabı birden fazla botla kullanılıyor |
| `EXCHANGE_PROTECTIVE_STOP` | Pozisyonu borsada OCO/stop emriyle koru |
| `LIVE_LOCK_STALE_SECONDS` | Hesap kilidinin bayatlama süresi |
---

## Eski dosyalar

`main.py`, `Trade.py`, `Tarama.py`, `Backtest.py`, `AI.py` gibi mevcut modüller korunmuştur. Yeni uygulama hesaplama katmanını (`Indikator`, `Stratejiler`) doğrudan kullanır. Süreç yönetimi `Supervisor` ile yapıldığından `Tmux/` ve systemd dosyaları kaldırılmıştır.

## Lisans / Uyarı

Bu yazılım yatırım tavsiyesi değildir. Canlı işlem kullanmadan önce uzun süre test modunda doğrulayın. Kripto varlıklar yüksek risk içerir.
