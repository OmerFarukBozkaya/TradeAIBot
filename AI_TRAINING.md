# AI Eğitimi — Zaman Serisi Protokolü

Bu belge kâr odaklı AI hattını açıklar: veri, özellikler, etiket, model
mimarisi, işlem politikası, aşırı öğrenme koruması ve ölçülen sonuçlar.

## Kısa özet

- Model **son 24 mumun gidişatını** görür (LSTM / Transformer).
- Hedef: **trend yukarıyken dibe yakın almak, tepeye yakın satmak**; al-tut'u geçmek.
- Giriş/çıkış **işlem disiplini** ile yapılır (rejim kapısı, takipli stop,
  asgari tutma, bekleme, seçici giriş).
- Başarı, doğrulamanın 3 ayrı penceresinde **işlem kalitesiyle** ölçülür;
  test verisi hiçbir seçime katılmaz.
- Ölçüm (BTCUSDT 1h, son %30): model **+%0,6** (al-tut −%24,6), en iyi
  indikatör −%14,4.

## Mimari: LSTM ve Transformer (sıra modelleri)

Model artık tek bir mumun özelliklerine değil **son 24 mumun gidişatına** bakar:

| Motor | Ne yapar | Ne zaman |
|---|---|---|
| **Transformer** | Dikkat (self-attention) ile pencereyi bütün olarak okur | Varsayılan aday |
| **LSTM** | Kapılı bellek ile zaman içindeki bağımlılıkları taşır | Varsayılan aday |
| MLP | Tek mum; hızlı referans | Yedek |
| GBM | Ağaç tabanlı; sıra belleği yok | Yedek |

Neden sıra modeli? "Dibe yakın al, tepeye yakın sat" kararı fiyatın **son hareketinin
şekline** bağlıdır (düşüşün yavaşlaması, hacmin kuruması, trendin eğimi). Tek mum bunu
taşımaz; pencere taşır.

Aşırı öğrenmeye karşı: dropout, L2, gradyan kırpma, göreli erken durma, **tohum
topluluğu** (2 modelin olasılık ortalaması) ve düşük işlem sayısı.

## Hedef: kâr odaklı (varsayılan)

Eski hedef "Local_Min_Max'a benzemek"ti. Yeni varsayılan **kâr odaklı** hedeftir:

1. **Etiket** (`excess_return`): gelecek `h` mumun getirisi, o anki ATR'ye bölünür
   (`z = fwd / ATR%`). Eşikler **yalnızca eğitim döneminden** hesaplanır.
2. **AL**: `z` yüksek **ve** trend yukarı **ve** fiyat kısa vadeli ortalamanın altında
   → *trend içinde dip alımı*.
3. **SAT**: `z` düşük **ve** fiyat kısa vadeli ortalamanın üstünde → *tepede satış*.
4. **Politika**: girişler yalnızca **trend rejimi açıkken** (EMA200 histerezis bandı)
   yapılır; çıkış **rejim kırılımı + takipli stop** ile olur. Hedef çok uzak tutulur
   (6×ATR) ki trend kaçırılmasın.

### İşlem disiplini (panelde "Uzman ayarları")

| Ayar | Anlamı | Önerilen |
|---|---|---|
| Giriş seçiciliği | Doğrulamada en yüksek olasılıklı mumların %kaçında alım | %2 |
| Asgari tutma | Pozisyon en az kaç mum tutulur | 24 |
| Bekleme | Çıkıştan sonra kaç mum alım yok | 24 |
| Takipli stop | Zirveden geri çekilme | %8 |
| Rejim bandı | EMA200 histerezis bandı | %2 |

Bu ayarlar olmadan model saatte bir alıp satar ve **işlem maliyeti** kazancı siler.
Ölçüm: aynı sinyalle 240 işlem −%37, disiplinli hâli 60 işlem −%8.

### Başarı ölçütü

Skor, doğrulamanın **3 ayrı penceresinde** işlem kalitesinden gelir:

```
pencere_puanı = al-tut farkı + 0.6×getiri + kâr faktörü bonusu
                − düşüş cezası − aşırı işlem cezası
```

- 1000 mumda 6'dan fazla işlem cezalandırılır.
- 3 pencerenin ortalaması + pozitif pencere oranı kullanılır (tek şanslı dönem yetmez).
- **Test verisi hiçbir seçime katılmaz.**

### Ölçülen sonuç (BTCUSDT 1h, 50.000 mum, son %30 test)

| Strateji | Getiri | Al-tut farkı | İşlem | Maks. düşüş |
|---|---|---|---|---|
| Al-tut | −24,56% | — | — | — |
| Super_Trend (en iyi indikatör) | −14,40% | +10,2 | 30 | −38,9% |
| MA_Cross | −32,89% | −8,3 | 53 | −45,5% |
| **LSTM (yeni)** | **+0,64%** | **+22,3** | 21 | **−9,2%** |
| **Transformer (yeni)** | −4,63% | +17,0 | 7 | −4,7% |

Yani model, test döneminde **hem al-tut'u hem en iyi indikatörü** geçti ve düşüşü
çok daha küçük tuttu. Yükseliş dönemlerinde (doğrulama) al-tut'un gerisinde kalır;
bu, sermayeyi korumanın doğal bedelidir.

## Tek düğme: Modeli eğit (önerilen)

**AI Eğitimi → Modeli eğit** kartı tek karar noktasıdır. Tüm ayarlar burada:
coin, periyot, mum sayısı, fiyat verisi, öğrenme tarzı, ufuk, hedef/stop, arama
bütçesi, iyileştirme turu, asgari kazanç, motor, çıktı biçimi, katmanlar,
aktivasyon ve özellik grupları.

Butona bastığında sistem:

1. Profili kaydeder ve fiyat verisini hazırlar (sabit veri varsa ağa çıkmaz).
2. Mevcut şampiyonu yükler.
3. `Aranacak mimari sayısı` kadar adayı **validation** ile dener
   (motor, katmanlar, aktivasyon, özellik grupları otomatik çeşitlenir).
4. En iyi adayı tam eğitimle (walk-forward + tam iyileştirme) yeniden üretir.
5. Testi **yalnızca kazanan için bir kez** çalıştırır.
6. Şampiyondan iyiyse **aynı modeli yerinde günceller** (v2, v3…). Değilse
   **mevcut modeli korur**.

Kararlar:

| Karar | Anlamı |
|---|---|
| `created` | İlk model oluşturuldu ve aktif |
| `updated` | Aynı model yeni sürümle güncellendi |
| `kept` | Yeni adaylar daha iyi değildi; mevcut model korundu |

`kept` bir hata değildir: modelin bozulmadığının garantisidir. Hiçbir aday
eğitilemese bile sistem mevcut modelle devam eder.

Aramada denenen adaylar otomatik silinir; model listesi şişmez. Tüm ayarlar
`ai_profile` kaydında tutulur, sayfayı yenileyince geri gelir.

## Fiyat verisini sabitle (tekrar çekmesin)

AI Eğitimi → **Fiyat verisi** kartı. Fiyat verisi bir kez çekilir, diske yazılır
ve sonraki eğitimler bu **sabit kopyadan** okunur; borsaya istek atılmaz.

- **Yeni veri kopyası al**: seçili coin/periyot/mum sayısı için tek seferlik çekim.
- **Sabitle**: seçilen kopya tüm eğitimlerde (otomatik + elle + nesil) kullanılır.
- **Sabit veriyi yenile**: aynı coin/periyot için güncel fiyatlarla yeni kopya
  oluşturur; eski kopya silinmez.
- **Sabitlemeyi kaldır**: otomatik moda döner. Otomatik modda ilk eğitim veriyi
  bir kez çeker ve sabitler; sonraki eğitimler aynı kopyayı kullanır.
- **Sil**: kopyayı diskten kaldırır.

Ham OHLCV saklanır (`open/high/low/close/volume/opendate`); **indikatörler her
eğitimde bu veriden yeniden hesaplanır**. Yani indikatör tanımını değiştirmek
veriyi yeniden çekmeyi gerektirmez.

Dosyalar: `Data/AI/datasets/<id>/data.npz` + `manifest.json`.
Aynı veride tekrar tekrar eğitim yaptığın için modelleri adil karşılaştırabilirsin.

## Nesiller boyu eğitim (her turda daha iyi)

Tek anahtar: **AI Eğitimi → Nesiller boyu eğit**. Her nesil önceki modelin
ağırlıklarından **sıcak başlangıç** yapar (fine-tune), böylece sıfırdan
başlamaz; öğrendiği temsili koruyarak üzerine ekler.

Akış:

1. 1. nesil mevcut şampiyondan (yoksa sıfırdan) başlar.
2. Her nesil yalnızca eğitim kümesinde eğitilir; eşik validation'da seçilir.
3. Nesil skoru **validation** ile ölçülür — test hiç kullanılmaz.
4. Skor `min_delta` kadar iyileşmezse sabır sonrası erken durulur.
5. En iyi nesil seçilir; önceki nesil şampiyonsa yalnızca **+0.5 puan**
   üstünse terfi eder (gerileme kabul edilmez).
6. Test, yalnızca seçilen nesil için **bir kez** çalıştırılır (denetim).

Neden gerilemez?

- Sıcak başlangıç + erken durdurma: en iyi epoch ağırlıkları saklanır.
- Nesil seçimi validation skoruyla; test seçime katılmaz.
- Şampiyon karşılaştırması ve kalite kapısı aynen uygulanır.
- Özellik şeması değişirse sıcak başlangıç otomatik atlanır (şekil uyuşmaz).

Aynı davranış otomatik öğrenmede de geçerlidir: her zamanlanmış tur mevcut
şampiyondan devam eder.

> GBM motorunda sklearn artımlı eğitimi desteklemediği için sıcak başlangıç
> yoktur; ilerleme veri + deneyim birikiminden gelir. MLP motorunda gerçek
> fine-tune yapılır.

## Otomatik öğrenme (önerilen)

Panelde **AI Eğitimi → Otomatik öğrenme** anahtarını açmak yeterlidir. Seçilen
coin/periyot için model belirli aralıkla kendi kendini yeniden eğitir:

1. Veri çekilir, nedensel özellikler ve gelecek etiketleri üretilir.
2. Train / validation / test + embargo protokolü uygulanır.
3. Walk-forward katları çalıştırılır.
4. **Kalite kapısı** devreye girer (aşırı öğrenme koruması).
5. Model mevcut aktif modelden belirgin biçimde iyiyse otomatik **terfi** eder.
6. Değilse aday olarak kalır veya reddedilir; mevcut model korunur.
7. Hata olursa ayarlar bozulmaz; sonraki tur üstel geri çekilmeyle tekrar dener.

Öğrenme tarzları:

| Tarz | Karakter |
|---|---|
| Temkinli | Uzun ufuk, yüksek eşik, az ama seçici işlem |
| Dengeli | Önerilen başlangıç |
| Agresif | Kısa ufuk, sık işlem, daha fazla gürültü |

Kapanan AI işlemleri (`ai_experiences`) sonraki turlarda ders olarak kullanılır.
Ancak deneyimler eğitim satırlarının **en fazla %20'si** kadar ve sınırlı
ağırlıkla eklenir; az sayıda işlem modeli ele geçiremez.

### Aşırı öğrenme korumaları

Bir modelin aktifleşmesi için:

- Test işlem sayısı yeterli olmalı (tarza göre 8–12).
- Test getirisi ve edge (al-tut farkı) pozitif olmalı.
- Test getirisi eğitim (in-sample) getirisinin çok küçük bir kısmı değilse
  (varsayılan: en az %25'i) model **reddedilir**. Bu, ezberleyen modeli yakalar.
- Walk-forward katlarının en az yarısı (tarza göre %40–60) pozitif olmalı.
- Walk-forward ortalama edge pozitif olmalı.
- Mevcut aktif model varsa yeni model skoru en az **+0.5 puan** daha iyi olmalı;
  yoksa şampiyon korunur.

Skor = `0.6 × test edge + 0.4 × walk-forward ortalama edge`.

## Elle eğitim (gelişmiş)

Panelde "Gelişmiş: elle eğitim" bölümü açılarak tüm parametreler değiştirilebilir.
Aynı protokol uygulanır.

## Eğitim hattı

```
Binance / CSV
   ↓
Nedensel özellikler (app/ai/features.py)
   ↓
Gelecek etiketleri (app/ai/labels.py)
   ↓
%55 saf train → %15 validation → %30 test  (+ horizon kadar embargo)
(Öğrenme toplam %70, test %30)
   ↓
İki ikili model: iyi alım / iyi satım (HistGradientBoosting)
   ↓
Eşik seçimi yalnızca validation
   ↓
Test bir kez değerlendirilir + walk-forward raporu
   ↓
Aday model (Data/Model/ai/<id>/)
   ↓
Panelden backtest → Aktifleştir → bot sihirbazında AI stratejisi
```

### Özellikler

- Geçmiş getiriler (1, 2, 3, 5, 10, 20, 50 mum)
- Fiyatın son N mumun dibine/zirvesine uzaklığı (10..200)
- EMA 7/21/50/200 uzaklığı
- RSI 14/28, MACD histogramı
- Bollinger içi konum ve bant genişliği
- ATR%, ADX
- Hacim z-skoru ve değişimi
- Mum gövde/fitil oranları
- Saat/gün döngüsel özellikleri

Hiçbir özellik `shift(-n)` veya merkezlenmiş pencere kullanmaz.

### Etiketler

Varsayılan "ileri getiri" etiketi:

- **İyi alım:** sonraki `horizon` mumda fiyat `target_move` kadar yükseliyor
  **ve** `stop_move` kadar düşmüyor.
- **İyi satım:** simetrik.

Alternatif olarak panelden "yerel dip/zirve" etiketi seçilebilir; bu yalnızca
deney/karşılaştırma içindir.

### Yinelemeli iyileştirme (tur tur öğrenme)

Tek bir eğitimle kalmıyoruz. Varsayılan olarak **5 tura** kadar şu döngü çalışır:

```
modeli eğit
  → validation'da eşik seç, skoru ölç
  → eğitim kümesinde sanal işlemleri çalıştır
  → her işlemi "erken / geç / zamanında" olarak sınıflandır
  → hatalı zamanlamadaki örneklerin ağırlığını düşür
  → ideal dip/zirve örneklerinin ağırlığını artır
  → ağırlıklarla yeniden eğit ve tekrar ölç
```

Zamanlama analizi:

| Durum | Anlamı | Ağırlık etkisi |
|---|---|---|
| **Erken giriş** | Girdikten sonra fiyat belirgin düştü | Giriş örneği zayıflar |
| **Geç giriş** | Fiyat dipten dönmüşken girdik | Gerçek dip örneği güçlenir |
| **Erken çıkış** | Sattıktan sonra yükseliş sürdü | Satış sinyali örneği zayıflar |
| **Geç çıkış** | Zirveden sonra sattık | Gerçek zirve örneği güçlenir |

Kurallar:

- Ağırlıklar `[0.3, 3.0]` aralığına kırpılır ve ortalaması 1'e normalize edilir;
  tek bir hatalı işlem modeli ele geçiremez.
- Hata analizi yalnızca **eğitim** kümesinde yapılır.
- Tur seçimi yalnızca **validation** skoruyla yapılır; test kümesi hiç kullanılmaz.
- Skor iyileşmezse `sabır` (varsayılan 2) tur sonra durur; en iyi tur saklanır.
- Nihai model, en iyi turun ağırlıklarıyla train + validation üzerinde yeniden
  eğitilir; test yalnızca bir kez değerlendirilir.
- `İyileştirme turu` ve `Sabır` panelden değiştirilebilir (gelişmiş bölüm).

### Sızıntı önlemleri

1. Veri karıştırılmaz; kronolojik bölünür.
2. Train / validation / test arasında `horizon + 2` mum embargo vardır.
3. Eşikler yalnızca validation'da seçilir.
4. Test kümesi eğitimde veya eşik seçiminde kullanılmaz.
5. Eksik değer doldurma ve model parametreleri yalnızca train'den öğrenilir.
6. Walk-forward raporunda her kat kendi geçmişiyle eğitilir, geleceğiyle test edilir.

## Dashboard akışı

1. **Ayarlar → Sistem → Yapay zekâ özellikleri** açılır (`AI_ENABLED=true`).
2. **AI Eğitimi** sekmesinde coin/periyot/mum sayısı/ufuk/hedef/stop seçilir.
3. Eğitim başlatılır; iş kuyruğunda ayrı süreçte çalışır.
4. Biten model **aday** olarak listelenir; test getirisi, edge, işlem sayısı,
   kazanma oranı ve walk-forward özeti görünür.
5. **Backtest** ile farklı coin/periyot ve nakit ayarları denenir.
6. Sonuç uygunsa **Aktifleştir** denir.
7. **Botlar → Yeni bot** ekranında `AI · <model>` seçilir; test modunda çalıştırılır.
8. Canlıya geçiş mevcut dört kilitli akıştan geçer.

## İşlemlerden öğrenme

AI modeliyle açılan her pozisyon kapandığında:

- giriş anındaki özellik vektörü,
- gerçekleşen K/Z,
- coin/periyot/mode ve çıkış nedeni

`ai_experiences` tablosuna yazılır. Sonraki eğitimde `Kapanan AI işlemlerinden
öğren` açıksa bu örnekler **yalnızca train kümesine**, sınırlı ağırlıkla eklenir.
Böylece model kendi hatalarından beslenir; ancak az sayıda işlem modeli ele
geçirmez.

## Model dosyaları

```
Data/Model/ai/<model_id>/
  manifest.json   # parametreler, eşikler, metrikler, durum
  model.pkl       # buy/sell modelleri + özellik şeması
  report.json     # split tarihleri, walk-forward, test işlemleri
```

## Eski AI ile farkı

Eski `AI.py`:

- TensorFlow/Keras ve ağır bağımlılıklar,
- tüm veri üzerinde ölçekleme (sızıntı),
- rastgele `train_test_split` (zaman serisi için yanlış),
- `local_min_max` etiketinin gelecek penceresini hesaba katmayan kullanım.

Yeni hat:

- scikit-learn / HistGradientBoosting (hafif),
- yalnızca train'den öğrenilen dönüşümler,
- kronolojik bölme + embargo,
- testin tek kez kullanılması,
- panelden yönetilen model kataloğu ve bot entegrasyonu.
