# TradeAI

Bu proje, kripto paralar ve hisse senetleri üzerinde analiz yaparak otomatik al-sat kararları veren bir bottur. Ek olarak, piyasayı tarar ve bilgilendirme amacıyla e-posta ile raporlar gönderir.

## Menüler

### 0) Veri Seti Oluştur
- Fiyat ve indikatör verilerinden oluşan veri setini oluşturur ve analizlerde tekrar kullanır.

### 1) Backtest Sonuçlarını Kaydet
- Stratejilerin geçmiş fiyat verilerindeki performansını analiz eder ve rapor oluşturur.

### 2) İndikatör Test Et
- İndikatör sınıfında yapılan değişiklikleri test ederek analiz eder.

### 3) Backtest Yap
- Stratejilerin tek bir varlık üzerindeki performansını grafikle gösterir.
- Seçilen stratejiyi alım ve satım noktaları ile işaretleyerek sonuçları sunar.

### 4) Tarama
- Piyasayı analiz eder ve sinyalleri e-posta ile bildirir.

### 5) Trade
- Otomatik olarak alım-satım işlemlerini gerçekleştirir.

### 6) Coin İndikatör Değerleri
- Seçilen coin için indikatör değerlerini gösterir.

### 7) Coin Strateji Değerleri
- Seçilen coin için strateji değerlerini gösterir.

### 8) Cihaz Bilgilerini Görüntüle
- Çalışan cihazın donanım bilgilerini gösterir.

### 9) Piyasa Durumu
- Piyasa raporu oluşturmak için belirli periyotlarda uygun stratejilerle analiz yapar.

### 10) Coinlist Oluştur
- Dosya olarak coin listesi oluşturur.

### 11) İşlem Geçmişini Analiz Et
- İşlem geçmişini analiz eder ve sonuçları gösterir.

### 12) Hacime Göre Coinlist Sıralama
- Belirli periyotlarda hacme göre coinleri sıralar ve yeni bir coin listesi oluşturur.

### 13)Strategys update olusturma
- Belirli periyotlarda stratejilerin performanslarını analiz eder ve her periyot için 3'er tane seçerek strategys.json oluşturur.

### 14)Strategys.json olustur
- Elde edilmiş analiz sonuçlarına göre Strategys.json oluşturur.

### 15)Buy veren coinler
- Seçili periyotta ve strateji de bulunulan mum için buy sinyali veren coinleri listeler.

## İşlevler

### a) Trade
1. Tüm coinleri tarar.
2. İşlem geçmişini ve periyodik durumlarını loglar.
3. Kapatılıp açıldığında kaldığı yerden devam eder.
4. Test amaçlı gerçek dışı işlemler yapabilir.
5. Alım ve satımları e-posta ve telegram ile bildirir.
6. Hata ile karşılaştığında bildirir ve işlemlere devam eder.
7. Satış beklerken diğer stratejileri de kontrol eder ve sinyalleri gösterir.
8. Statik, dinamik ve destek stop-loss ile korunur.
9. Manuel satışlara adapte olur.
10. İşlemin açık kalma süresini kaydeder.
11. Kar/Zarar hesaplaması yapar.
12. Başlangıç bakiyesi üzerinden devam eder.
13. Yalnızca botun aldığı coinler üzerinde işlem yapar.
14. Satış sonrası kendini kapatabilir.

### b) Tarama
1. Tüm coinleri tarar.
2. Kapatılıp açıldığında kaldığı yerden devam eder.
3. Hata ile karşılaştığında bildirir ve devam eder.
4. Periyotlara uygun stratejilerle alım veya satım sinyali veren coinleri listeler.

### c) Piyasa Durumu
1. Tüm coinleri tarar.
2. Her periyot için uygun stratejilerle analiz yapar ve rapor oluşturur.
3. Her coinin her periyottaki strateji ortalamalarını alır.
4. Tüm periyotlar için her coinin ortalamasını alır.

---

Bu bot, piyasa analizlerini ve stratejik alım-satım işlemlerini entegre bir şekilde yaparak kullanıcıyı bilgilendirir ve işlemlerini otomatikleştirir.
