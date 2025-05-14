# TradeAI

Bu proje, kripto paralar ve hisse senetleri üzerinde analiz yaparak otomatik al-sat kararları veren bir bottur. Ek olarak, piyasayı tarar ve bilgilendirme amacıyla e-posta ile raporlar gönderir.

## Nasıl Kurulur

0. ``ssh-keygen`` ile oluşturulan anahtarın public olanını github'a kayıt et.
1. Projeyi yerel dizine çek ``git clone git@github.com:IcedFire34/TradeAIBot.git``
2. venv oluştur ``python -m venv .venv``.
3. Windowsda ``.venv\Scripts\activate`` . Linuxda ``source venv_adi/bin/activate`` ile ortamı aktif et. Sanal ortamdan çıkmak için ``deactivate`` ile çık.
4. Paketleri yüklemek için :
   ```
   sudo apt update
   sudo apt upgrade
   sudo apt install python3-dev python3-pip build-essential cmake gcc g++ -y
   pip install -r requirements.txt
   ```
5. env dosyasını oluştur ve gerekli bilgileri gir.

    ```
    BINANCE_API_KEY="<API_KEY>"
    BINANCE_API_SECRET="<API_SECRET_KEY>"
    GONDERICI_EMAIL="<FROM_MAIL>"
    GONDERICI_EMAIL_SIFRE="<FROM_MAIL_PASS>"
    ALICI_EMAIL="<TO_MAIL>"
    CRYPTOPANIC_TOKEN="<TOKEN>"
    TELEGRAM_API_TOKEN="<TELEGRAM_API_TOKEN>"
    TELEGRAM_CHAT_ID="<TELEGRAM_CHAT_ID>"
    MAIL_GONDER="True"
    TELEGRAM_MESAJ_GONDER="True"
    BUY_MA_CONTROL="False"
    BUY_BB_CONTROL="False"
    STRATEGY_LIMIT_15M="7"
    STRATEGY_LIMIT_1H="15"
    STRATEGY_LIMIT_4H="15"
    STRATEGY_LIMIT_1D="70"
    STRATEGY_LIMIT_CHECK="False"
    DINAMIK_STOP_LOSE="False"
    STATIC_STOP_LOSE="False"
    DESTEK_STOP_LOSE="False"
    TAKE_PROFIT="True"
    CALISACAK_PERIYOTLAR=["15m","1h","1d"]
    UPDATE_STRATEGYS_CHECK="False"
    CALISACAK_PERIYOTLAR_AI=["1m","15m","1h","1d"]
    ```

6. Coinlist oluştur. Bunu ``python main.py`` komutunu çalıştırdıktan sonra ``10``. seçenek ile bunu oluşturabilirsin.
7. Strategylerin güncel analizini yap. Bunu ``python main.py`` komutunu çalıştırdıktan sonra ``1``. seçenek ile bunu yapabilirsin.
8. Analiz sonuçlarınından strategys.json oluştur. Bunu ``python main.py`` komutunu çalıştırdıktan sonra ``14``. seçenek ile bunu oluşturabilirsin.
9. Bu adımların sonunda tüm fonksiyonel özellikleri sorunsuz bir şekilde çalışacaktır.
10. Servisin çalıştıracağı tmux dosyaları için tmux yüklemek gerek.
    ``` 
    sudo apt update
    sudo apt install tmux
    ``` 
    Tmux yüklendikten sonra aşağıdaki kodlari 
    ```
    nano /etc/systemd/system/trade.service
    nano /etc/systemd/system/ip.service
    nano /etc/systemd/system/data_recorder.service
    ``` 
    bu konumdaki dosyayalara yazarak servisi oluştur.

    trade.service
    ````
    [Unit]
    Description=Trade AI Bot Tmux Session Starter
    After=network.target

    [Service]
    Type=forking
    User=<USER>
    WorkingDirectory=/home/<USER>/TradeAIBot
    Environment=TERM=xterm-256color
    Environment=DISPLAY=:0
    ExecStart=/usr/bin/tmux new-session -d -s Trade /bin/bash -c '/home/<USER>/TradeAIBot/Tmux/tmux_trade.sh'
    Restart=no
    StandardOutput=journal
    StandardError=journal

    [Install]
    WantedBy=multi-user.target
    ````
    ip.service
    ````
    [unit]
    Description="ip adresini surekli kontrol eden ve degistiginde bildiren servis"
    After=network.target

    [Service]
    ExecStart=/home/<USER>/TradeAIBot/.venv/bin/python /home/<USER>/TradeAIBot/ip.py
    Restart=on-failure
    User=<USER>
    WorkingDirectory=/home/<USER>/TradeAIBot
    StandardOutput=inherit
    StandardError=inherit
    Environment=PYTHONUNBUFFERED=1

    [Install]
    WantedBy=multi-user.target
    ````
    data_recorder.service
    ````
    [Unit]
    Description=DataRecorder Tmux Session Starter
    After=network.target

    [Service]
    Type=forking
    User=<USER>
    WorkingDirectory=/home/<USER>/TradeAIBot
    Environment=TERM=xterm-256color
    Environment=DISPLAY=:0
    ExecStart=/usr/bin/tmux new-session -d -s DataRec /bin/bash -c '/home/<USER>/TradeAIBot/Tmux/tmux_data_recorder.sh'
    Restart=no
    StandardOutput=journal
    StandardError=journal

    [Install]
    WantedBy=multi-user.target
    ````

11. Tmux'un çalışabilmesi için ``chmod +x Tmux/tmux_trade.sh`` komutunu çalıştır.
12. ``sudo systemctl daemon-reload`` daha sonrasında bu komutu çalıştır.
13. Servisi entkinleştirmek için ``sudo systemctl enable trade.service`` bu komutu çalıştır. 
14. Servisi başlatmak için ``sudo systemctl start trade.service`` bu komutu çalıştır.

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

### 13) Strategys update olusturma
- Belirli periyotlarda strategys.json dosyasını analiz ederek günceller.

### 14) Strategys.json olusturma
- Yapılmış olan analize göre strategys.json dosyası oluşturulur.

### 15) Buy veren coinler
- İstenilen strategy için bulunulan mum için buy sinyali veren coinleri listeler.

### 16) Destek direnc seviyeleri
- İstenilen coin için destek ve direnç seviyelerini listeler.

### 17) Tum pozisyonlari kapat
- TradeAIBot'un açtığı tüm pozisyonları kapatır.

### 18) Full nakite gec
- Tum coinleri anında satar ve full nakite geçer.

### 19) Buy result analizi
- Her alım kontrolünün sonucunun kayıt edildiği dosyayı analiz eder.

## İşlevler

### a) Trade
1. Tüm coinleri tarar.
2. İşlem geçmişini ve periyodik durumlarını loglar.
3. Kapatılıp açıldığında kaldığı yerden devam eder.
4. Test amaçlı gerçek dışı işlemler yapabilir.
5. Alım ve satımları e-posta ve telegramdan bildirir.
6. Hata ile karşılaştığında bildirir ve işlemlere devam eder.
7. Satış beklerken diğer stratejileri de kontrol eder ve sinyalleri gösterir.
8. Dinamik bir stop-loss ile korunur.
9. Manuel satışlara adapte olur.
10. İşlemin açık kalma süresini kaydeder.
11. Kar/Zarar hesaplaması yapar.
12. Başlangıç bakiyesi üzerinden devam eder.
13. Yalnızca botun aldığı coinler üzerinde işlem yapar.

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