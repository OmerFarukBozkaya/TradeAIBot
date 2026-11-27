# 4h Trend Botu — Ölçülmüş Kurulum

Bu belgedeki sayılar **Binance spot** verisiyle, komisyon ve kayma dahil
`app.job_runner.run_backtest` üzerinden üretildi. Amaç "en yüksek tek coin
getirisi" değil, **aynı ayarla birden çok coinde pozitif kalan ve drawdown'ı
yönetilebilir** kurulumu bulmaktır.

## Veri ve evren

| Alan | Değer |
|---|---|
| Periyot | 4h |
| Mum sayısı | 12.000 (≈ 5,5 yıl) |
| Coin sayısı | 8 |
| Komisyon + kayma | Varsayılan paper değerleri (`settings.PAPER_FEE`, `settings.PAPER_SLIPPAGE`) |
| Doğrulama | Aynı adaylar 20.000 mumluk ikinci pencerede de kontrol edildi |

Seçilen liste (`Trend 4h`):

```txt
BTCUSDT, SOLUSDT, XRPUSDT, BNBUSDT, SUIUSDT, ENAUSDT, WLDUSDT, PEPEUSDT
```

Liste, 35 likit USDT paritesinin taranmasıyla oluşturuldu. Aynı ayarla
**8 coinin tamamı pozitif**; elenenler (ETH, LINK, UNI, AAVE, TRX, ETC, HBAR)
bu sistemle negatif kaldı.

## Strateji

**TrendRider** (hazır strateji): 40 mumluk kırılım + `EMA50 > EMA200` rejim
filtresi + `ADX > 18`. Düşüş rejiminde (`EMA50 < EMA200`) **alım üretmez**,
nakitte bekler. Bu yüzden "her zaman işlem" değil, "fırsat çıkınca işlem"
davranışı gösterir.

## Risk bloğu (önerilen)

| Ayar | Değer | Neden |
|---|---|---|
| Zarar durdur | **3 × ATR** | 2×ATR testere dişinde kesiyor; 5×ATR zararı büyütüyor |
| Stop üst sınırı | **%8** | 4h periyot tavanı |
| Takipli stop | **6 × ATR** | 4–5×ATR trendi ortasında kesiyordu |
| Takipli stop başlangıcı | **%10 kâr** | %8'de bazı coinlerde trend ortasında kesiliyor |
| Breakeven | **%20 kâr** | Erken breakeven trendi sıfıra çekiyor |
| Kâr koruma (Donchian) | **10 mum** | Kârdayken yapı bozulursa çıkar |
| Yeni alım beklemesi | **5 mum** | Aynı sinyale tekrar girip komisyon ödemesin |
| Kâr al (ATR/yüzde) | **kapalı** | Trend takibinde sabit hedef getiriyi yarıya indirir |
| İşlem başına risk | **%2,5 – %4** | Aşağıdaki ölçek tablosuna bakın |
| Günlük zarar limiti | **%3 (canlı)** | Kötü günde art arda stop olmayı durdurur |
| Maksimum pozisyon | **%100** | Tek pozisyon |
| Piyasa rejimi | **BTC > EMA200** | BTC zayıfken altcoin alımı yapmaz |

## Piyasa rejimi filtresi (BTC)

Tek coinin trendi ile piyasanın trendi aynı değildir. Altcoinler BTC'ye yüksek
korelasyonla bağlıdır; BTC 200 periyotluk ortalamasının altındayken alım açmak
strateji doğru olsa bile art arda stop üretir. Filtre yalnızca **yeni girişi**
veto eder; açık pozisyonun stop/çıkış kuralları değişmez.

8 coin / 12.000 mum / risk %4 (taban ayar 8/15, filtre hariç):

| Varyant | Medyan | Ortalama | En kötü coin | Ort. DD | İşlem | PF |
|---|---:|---:|---:|---:|---:|---:|
| Taban (filtresiz, 8/15) | +%85,5 | +%101,7 | +%20,0 | %33,4 | 61 | 2,09 |
| Yalnızca 10/20 | +%80,2 | +%101,0 | +%38,5 | %33,6 | 60 | 2,08 |
| **BTC > EMA200** | +%110,8 | +%119,8 | +%29,8 | **%30,5** | 56 | **2,27** |
| **BTC > EMA200 + 10/20** | **+%108,8** | **+%119,1** | **+%49,8** | **%30,9** | 56 | **2,26** |
| BTC > EMA100 | +%97,3 | +%110,2 | +%33,2 | %30,9 | 57 | 2,12 |
| RSI < 72 | +%83,6 | +%83,1 | −%16,4 | %32,3 | 52 | 2,00 |
| Hacim > 1,2× ortalama | +%79,6 | +%80,7 | −%0,2 | %30,3 | 54 | 1,89 |
| Kısmi kâr 2R'de %33 | +%80,1 | +%76,8 | +%21,8 | **%26,5** | 98 | 3,82 |

Karar: **BTC > EMA200 + 10/20**. Filtre medyanı ~25 puan artırdı, drawdown'ı
düşürdü; 10/20 ise medyanı ~2 puan azaltırken en kötü coini +%29,8'den
+%49,8'e çıkardı (risk-adjusted olarak daha iyi). RSI ve hacim filtreleri
getiriyi düşürdüğü için reddedildi. Kısmi kâr, daha düşük getiri ama %26,5
drawdown isteyen muhafazakâr hesaplar için alternatif olarak kalabilir.

## Ölçülen sonuçlar (risk %4, BTC filtresi + 10/20)

| Coin | Getiri | Maks. DD | İşlem | Kazanma | PF | R:R | En kötü işlem | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTCUSDT | +%82,0 | %26,7 | 77 | %40 | 1,60 | 2,37 | −%6,27 | 0,66 |
| SOLUSDT | +%224,8 | %25,6 | 83 | %40 | 2,15 | 3,25 | −%8,05 | 0,97 |
| XRPUSDT | +%91,1 | %50,5 | 60 | %28 | 1,96 | 4,97 | −%8,05 | 0,60 |
| BNBUSDT | +%126,6 | %35,9 | 74 | %50 | 1,96 | 1,96 | −%8,05 | 0,81 |
| SUIUSDT | +%49,8 | %20,9 | 45 | %47 | 1,77 | 2,02 | −%8,05 | 0,56 |
| ENAUSDT | +%143,2 | %22,6 | 28 | %43 | 3,22 | 4,30 | −%8,05 | 1,33 |
| WLDUSDT | +%65,9 | %28,3 | 35 | %31 | 2,42 | 5,27 | −%8,05 | 0,66 |
| PEPEUSDT | +%169,5 | %36,9 | 42 | %31 | 2,99 | 6,66 | −%8,05 | 0,89 |
| **Ortalama** | **+%119,1** | **%30,9** | **56** | **%39** | — | **3,41** | **−%8,05** | **0,81** |

- **Medyan getiri:** +%108,8 (5,5 yılda)
- **En kötü coin:** +%49,8 (8/8 pozitif)
- **Toplam 444 işlem:** kazanma **%39,4**, ortalama kazanç **+%15,31**,
  ortalama kayıp **−%4,49**
- **Beklenti:** işlem başına **+0,74 R** (`0,394 × 3,41 − 0,606`)

## Risk ölçeği (aynı ayar, farklı pozisyon büyüklüğü)

| İşlem riski | Ortalama getiri | Medyan | En kötü coin | Ort. DD |
|---:|---:|---:|---:|---:|
| %2,5 | +%80,2 | +%83,2 | +%31,7 | %21,7 |
| %4,0 | +%119,1 | +%108,8 | +%49,8 | %30,9 |
| %6,0 | +%165,1 | +%124,5 | +%64,6 | %39,7 |
| %8,0 | +%207,7 | +%137,7 | +%67,6 | %45,5 |

Getiri riskle birlikte artıyor ama **doğrusal değil**: stop mesafesi %8'e
yaklaşınca pozisyon %100 tavanına dayanıyor. %8'in üzerine çıkmak gerçekte
pozisyonu büyütmez, yalnızca gap riskini artırır.

## Ödül/risk oranı

- Ortalama kazanç **+%15,3**, ortalama kayıp **−%4,5** → **R:R ≈ 3,4 : 1**
- Kazanma oranı **%39** → 5 işlemden 2'si kazanıyor, kazanan ~3,4 katı
- **İşlem başına beklenti: +0,74 R**

Bu, "her işlemde %3,4 kazanırsın" demek değildir. Stop mesafesi 1R kabul
edilirse, ortalama kazanan işlem 3,4R; ortalama kaybeden 1R.

## Bir işlemde en fazla zarar

| Kurulum | Fiyat bazında | Sermaye bazında (tek işlem) |
|---|---|---|
| Tek bot, risk %4 | −%8,05 (stop tavanı) | **≤ %4** (planlı) |
| Tek bot, risk %2,5 | −%8,05 | **≤ %2,5** |
| 8 bot (her biri %12,5 sermaye), risk %4 | −%8,05 | **≈ %0,5 toplam** |
| 8 bot, risk %8 | −%8,05 | **≈ %1 toplam** |

- Stop seviyesi aşılarak açılış (gap) olursa kayıp planlanan yüzdeyi aşabilir.
  4h kriptoda nadir, ama haber/ani çöküşte mümkün.
- Aynı anda 8 pozisyon da stop olursa (korelasyonlu çöküş), toplam kayıp
  yaklaşık **8 × tek işlem riski** olur (risk %4'te toplam ~%4).

## Günlük zarar limiti (canlı koruma)

`daily_loss_limit_pct = 3` iken bot, **UTC günü başındaki özkaynağa** göre %3
kayıp görürse gün bitene kadar **yeni pozisyon açmaz**. Açık pozisyonun
stop/takipli stop/çıkış kuralları çalışmaya devam eder; yani koruma stratejiyi
kilitlemez, yalnızca yeni risk alımını durdurur.

Amaç: kötü bir günde art arda stop olup hesabın tamamını riske atmamak.
Backtest bu korumayı **içermez** (günlük equity simülasyonu yok); canlıya özel
bir güvenlik katmanıdır.

## Tek bot mu, 8 bot mu?

Canlı motorda bir botun **nakit havuzu ortaktır**. 8 coini tek botta çalıştırıp
işlem riskini %8 yaparsanız, ilk sinyal nakitin tamamını alır; diğer coinler
pozisyon açamaz. Bu yüzden:

| Kurulum | Davranış | Uygun olduğu durum |
|---|---|---|
| **1 bot / 8 coin / risk %2,5** | Nakit sırayla paylaşılır, 8 fırsata da yer kalır | Basit, dengeli |
| **8 bot / 1 coin / risk %4** | Her coin kendi %12,5'lik diliminde bağımsız çalışır | Backtest'e en yakın |
| **8 bot / 1 coin / risk %8** | Her dilim tam yatırılır; en yüksek getiri | Agresif, %45 DD'ye tolerans |

Backtest sonuçları **her coin bağımsız** varsayımıyla üretildiği için en
tutarlı eşleşme 8 ayrı bottur. Tek botta riski %2,5'in üzerine çıkarmak,
geç gelen sinyalleri küçük pozisyonla bırakır.

> **Kritik:** bir bot aynı anda **tek pozisyon** tutar (`state["position"]`).
> 8 coini tek botta çalıştırmak "8 pozisyon" değildir; ilk sinyal gelen coin
> pozisyonu açar, diğer 7 coin o sırada bekler. Bu yüzden tek botta coin
> çeşitlendirmesi yoktur.

> **Korelasyon uyarısı:** 8 coin de yüksek beta'lı altcoin. BTC filtresi bunu
> azaltır ama yok etmez. Toplam açık riski, "8 bağımsız işlem" gibi değil,
> "tek bir altcoin sepeti" gibi düşünün.

## Tek botta birden fazla strateji?

Motor, botta seçilen stratejilerden **herhangi biri** AL derse pozisyon açar
(VEYA); çıkışta pozisyonu açan stratejinin SAT sinyali + ortak risk kuralları
kullanılır. Yani ikinci strateji yalnızca **daha fazla giriş** üretir, aynı
anda ikinci pozisyon açmaz.

7 kombinasyon 8 coin / 12.000 mum ile ölçüldü (taban 8/15, BTC filtresi yok;
çıkışta tüm stratejilerin SAT'ı VEYA'landı, yani canlıdan daha muhafazakâr):

| Kombinasyon | Medyan | Ortalama | En kötü coin | Ort. DD | İşlem |
|---|---:|---:|---:|---:|---:|
| **TrendRider tek** | **+%85,5** | **+%101,7** | **+%20,0** | %33,4 | 61 |
| TrendRider + SMC | +%70,3 | +%82,2 | +%19,6 | %36,1 | 73 |
| TrendRider + MA_Cross | +%66,4 | +%79,4 | +%20,3 | %33,4 | 93 |
| TrendRider + Tillson | +%64,5 | +%70,1 | −%3,0 | %30,4 | 172 |
| TrendRider + Tillson + SMC | +%35,3 | +%53,7 | −%6,6 | %34,9 | 183 |
| TrendRider + DMO | +%17,0 | +%41,4 | −%20,4 | %34,2 | 191 |
| TrendRider + Dip-Trend | +%11,8 | +%26,6 | −%45,3 | %35,2 | 137 |

Her ek strateji medyanı **düşürdü**: giriş sayısı artıyor, kalite düşüyor ve
komisyon/kayma çoğalıyor. Karar: **tek bot = tek strateji (TrendRider)**.
İkinci bir strateji denenecekse ayrı bot + ayrı sermaye ile denenmeli; böylece
hangi stratejinin kazandırdığı ölçülebilir kalır.

## Nasıl başlatılır?

**Panelden (önerilen):** Botlar → **Önerilen Botlar** düğmesi başlangıç
sermayesini, işlem riskini ve modu sorar; ölçülen ayarlarla **8 botu** tek
tıkla oluşturur. Sermaye 8'e bölünür (ör. 1.000 USDT → bot başına 125 USDT).
Botlar **durdurulmuş** oluşur; kartlardan tek tek başlatılır. Aynı isimde bot
varsa atlanır, yani düğmeye tekrar basmak mükerrer bot üretmez.

Komut satırından kurmak da mümkündür (varsayılan **paper**, dry-run,
BTC rejim filtresi açık):

```bash
python scripts/setup_4h.py                    # önizleme
python scripts/setup_4h.py --apply            # 8 bot × 1 coin, risk %4
python scripts/setup_4h.py --apply --cash 500 # 500 USDT → bot başına 62,5
python scripts/setup_4h.py --apply --single   # tek bot × 8 coin, risk %2,5
python scripts/setup_4h.py --apply --no-btc-regime  # filtreyi kapat
```

Canlıya geçiş sırası:

1. **Paper** 8 botu en az 2–4 hafta çalıştırın; sinyal/çıkışların backtest ile
   aynı davrandığını görün.
2. Panelden canlı işlem anahtarını açın (`LIVE_ENABLED` + üst çubuk anahtarı).
3. Küçük sermaye ile `--mode live --risk 2.5` başlatın; 1–2 ay sonra %4'e
   çıkarın. %8 yalnızca %45 drawdown'a tahammülünüz varsa.
4. Canlıda günlük zarar limiti varsayılan **%3**'tür (`--daily-loss 2` ile
   sıkılaştırılabilir).
5. Borsada **API anahtarına para çekme izni vermeyin**; yalnızca spot işlem.

## 1h neden önerilmiyor?

Aynı yöntemle 18 coin ve 14.000 mum (≈1,6 yıl) test edildi; dört farklı
yaklaşımın tamamı negatif kaldı:

| Yaklaşım | Medyan | En kötü coin |
|---|---:|---:|
| Dip-Trend + kâr koruma(20) | −%3,9 | −%60,5 |
| TrendRider | −%14,4 | −%33,3 |
| Dip-Trend (saf) | −%20,7 | −%66,3 |
| Tillson T3 & QQE | −%30,2 | −%71,8 |

1h'de hareketin büyük kısmı gürültü; komisyon + kayma 90–170 işlemde hesabı
yiyor. Bu yüzden 1h botu kurulacaksa yalnızca **paper** ve küçük sermaye ile
denenmeli.

## Yeniden üretme

```bash
python scripts/bench_4h.py                 # risk %4, BTC filtresi açık
python scripts/bench_4h.py --risk-pct 2.5  # dengeli
python scripts/bench_4h.py --no-btc-regime # filtre etkisini karşılaştır
python scripts/bench_4h.py --bars 20000    # ikinci pencere
```

> Uyarı: 5,5 yıllık tek pencereye bakarak ayar seçmek overfit riski taşır.
> Bu yüzden adaylar 20.000 mumluk ikinci pencerede de kontrol edildi ve
> coin listesi "en kötü coin pozitif" kuralıyla daraltıldı.