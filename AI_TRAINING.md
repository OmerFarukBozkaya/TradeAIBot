# AI Eğitimi — Zaman Serisi Protokolü

Bu belge, `Local_Min_Max` stratejisinin "en doğru alım/satım" hedefine yaklaşmak
için eklenen AI hattını açıklar.

## Neden Local_Min_Max hedefi?

`Local_Min_Max`, her mum için geriye ve ileriye bakarak yerel dip/zirve işaretler.
İleriye baktığı için **canlıda doğrudan kullanılamaz**. AI'nin hedefi bu etiketi
kopyalamak değil, yalnızca geçmişten gelen özelliklerle "şu an dibe/zirveye ne
kadar yakınız?" sorusuna olasılık üretmektir.

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
