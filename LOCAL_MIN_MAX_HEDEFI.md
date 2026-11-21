> **Güncel yön (2026-11):** Varsayılan hedef artık **kâr odaklı** (trend içinde dip alımı /
> tepe satışı). Local_Min_Max taklidi panelde bir seçenek olarak korunur. Ayrıntı ve ölçümler
> için AI_TRAINING.md dosyasına bakın.

# Local_Min_Max hedefi

Bu projede AI'nın amacı **Local_Min_Max'ın alım/satım yaptığı yerlere yaklaşmaktır**.
Local_Min_Max geleceğe baktığı için birebir kopyalanamaz (canlıda uygulanamaz);
bu yüzden hedef "aynısı olmak" değil, **olabildiğince yaklaşmak** ve bunu
**al-tut getirisini geçerek** yapmaktır.

## Neden eski yaklaşım yanlıştı?

Eski hedef "sonraki N mumda %X yükselirse iyi alım" idi. Bu:

- Local_Min_Max ile ilgisizdi (dip/zirve kavramı yoktu),
- sabit %10 hedef 1h grafikte neredeyse imkânsızdı (model hiç pozitif örnek bulamıyordu),
- sabit yüzdeler coin oynaklığını yok sayıyordu.

## Yeni hedef

### 1. Etiket: dip/zirve bölgesi

Her mum için:

- **AL hedefi (1):** fiyatın `low` değeri, `±pivot penceresi` içindeki en düşük
  fiyatın **`band` kadar** üstünde veya altında.
- **SAT hedefi (1):** `high`, pencerenin en yüksek fiyatının `band` kadar altında.

`band` küçükse yalnızca tam dip pozitif olur (az ama isabetli), büyükse geniş
bölge pozitif olur (çok ama gürültülü). Varsayılan **%0,1**.

### 2. Eşik: doğrudan uyuma göre

Model olasılıkları, `Local_Min_Max` pivotlarına **karşı** taranır:

- ±2 mum kayma toleransı,
- `asgari isabet` (varsayılan 0,35) sağlanacak şekilde eşik seçilir.

Böylece model "her muma sinyal ver" diyemez; sadece pivotlara benzeyen yerlerde
ateşler.

### 3. Başarı ölçütü

```
skor = 100 × uyum(F1) + 0,2 × al-tut farkı + 0,1 × getiri
```

- **Uyum (F1):** modelin AL/SAT sinyalleri ile gerçek pivotlar arasındaki
  precision/recall dengesi. **Baskın ölçüt**: 1 puan F1 ≈ 1 puan skor.
- **Al-tut farkı (edge):** strateji getirisi − al-tut getirisi. Yalnızca
  eşitliği bozar ve aşırı kötüyse cezalandırılır (tek validation dilimindeki
  gürültü skoru ele geçirmesin).
- İşlem sayısı çok azsa ceza.

Model kartında ve eğitim sonucunda şunlar görünür:

- **Local_Min_Max uyumu:** test F1 (%)
- **AL isabet / yakalama**, **SAT isabet / yakalama**
- **Al-tut farkı** ve getiri
- İşlem sayısı, kazanma oranı

### 4. Hedef/stop yüzdeleri

Sabit yüzde yerine **ATR tabanlı**:

```
hedef  = 2,0 × ATR%   (sınır: %0,2 – %25)
stop   = 1,2 × ATR%   (sınır: %0,2 – %20)
```

Böylece sakin coinlerde küçük, oynak coinlerde büyük hedefler kullanılır.
Elle değer girilirse o kullanılır.

### 5. Aşırı öğrenme koruması

- Etiket `pivot penceresi` mum sonra kesinleşir; eğitim/validasyon/test arasında
  bu kadar **embargo** bırakılır.
- Tur seçimi yalnızca **validation** uyumuyla yapılır; test bir kez görülür.
- Model, mevcut modelden daha iyi değilse **korunur** (gerileme yok).
- `band` çok küçük tutulursa model yalnızca birkaç örneği ezberleyebilir; bu
  yüzden test F1'i ve al-tut farkı birlikte raporlanır.

### 6. Tekrar eğitimde hatalardan öğrenme

Veri **sabit** kalır; aynı mumlar tekrar kullanılır. Buna karşılık her tur:

- önceki neslin **eğitim kümesinde yanıldığı örnekleri** daha yüksek ağırlıkla
  görür (hata odaklı ağırlıklandırma; turdan tura artar),
- farklı tohum, öğrenme hızı ve dropout dener,
- AL/SAT eşiklerini validation uyumuna göre yeniden seçer.

Böylece tekrar eğitim "aynı modeli kopyalamak" yerine gerçekten hatalarına
odaklanır. Aynı veride iyileşmenin de bir sınırı vardır; skor artmıyorsa sürüm
korunur ve tur kabul edilmez.

### 7. Sızıntı (leakage) korumaları

- **Embargo etiketin ileri bakışına göre**: Local_Min_Max etiketi `pivot
  penceresi` kadar ileri bakar. Embargo artık `max(pencere, ufuk) + 2` mumdur;
  yanlışlıkla yalnızca ufka bağlanmaz.
- **Bölmeler kronolojik ve ayrık**: %55 eğitim / %15 validation / %30 test.
  Test yalnızca bir kez, en sonda değerlendirilir.
- **Walk-forward yalnızca eğitim+validation bölgesinde** çalışır; test dönemi
  çapraz doğrulamaya hiç girmez.
- **Ölçekleme ve eksik değer doldurma** yalnızca eğitim kümesinden öğrenilir;
  validation/test bunları devralır.
- **Terfi kararı** 3 validation penceresinin ortalamasıyla verilir; test
  karara hiç katılmaz.

## Ölçülen örnek (BTCUSDT 1h, 6.000 mum)
| Ölçüt | Sonuç |
|---|---|
| Local_Min_Max uyumu (test F1) | ~%29 |
| AL isabet / yakalama | 0,39 / 0,24 |
| SAT isabet / yakalama | 0,38 / 0,23 |
| Strateji getirisi | −%4,1 |
| Al-tut getirisi | −%19,4 |
| **Al-tut farkı** | **+%15,3** |

Yani model Local_Min_Max'ı birebir kopyalamıyor (kopyalasa test F1'i ~1,0 ve
canlıda kullanılamaz olurdu) ama dip/zirvelere anlamlı biçimde yaklaşıyor ve
düşen piyasada al-tut'tan belirgin şekilde daha iyi koruyor.

## Ayarlar

Panelde yalnızca şunlar gerekli:

- Coin, periyot, geçmiş mum, fiyat verisi
- **Uğraşma düzeyi:** Hızlı / Dengeli / Titiz

Uzman ayarları (katlanmış):

| Ayar | Anlamı | Önerilen |
|---|---|---|
| Pivot penceresi | Local_Min_Max'ın iki yana baktığı mum | 0 = otomatik |
| Dip/zirve bandı | "Dibe yakın" sayılma yüzdesi | %0,10 |
| Kayma toleransı | Sinyal kaç mum kayarsa tuttu sayılsın | 2 |
| Asgari isabet | Sinyallerin en az kaçta kaçı pivot olmalı | 0,35 |
