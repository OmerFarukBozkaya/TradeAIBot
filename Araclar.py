import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import traceback
import time
from datetime import datetime
from Binance import Binance
from Indikator import Indikator
import csv
import pandas as pd
from openpyxl.workbook import Workbook

class Araclar:
    def __init__(self, from_email=None, to_email=None, email_password=None):
        if from_email and to_email and email_password :
            self.from_email = from_email  # Nesnenin from_email değeri
            self.to_email = to_email  # Nesnenin to_email değeri
            self.email_password = email_password  # Nesnenin şifresi
        else:
            self.from_email,self.email_password, self.to_email= self.load_settings()

    def load_settings(self):
        """
        API anahtarlarını 'settings.txt' dosyasından okur.
        Dosyanın her satırı 'key: value' formatında olmalıdır.
        """
        setting = []
        with open("settings.txt", "r") as settings_file:
            for line in settings_file:
                line = line.strip().split(":")
                setting.append(line[1].strip())

        return setting[2], setting[3], setting[4]

    def mail_gonder(self, baslik, mesaj, bekle=300, smtp_server="smtp.gmail.com", smtp_port=587):
        try:
            # E-posta gövdesini oluşturma
            message = MIMEMultipart()
            message['From'] = self.from_email  # Nesneye ait from_email kullanılıyor
            message['To'] = self.to_email  # Nesneye ait to_email kullanılıyor
            message['Subject'] = baslik
            message.attach(MIMEText(mesaj, 'plain'))

            # SMTP sunucusuna bağlanma
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()  # TLS bağlantısı başlatma
            server.login(self.from_email, self.email_password)  # Nesneye ait şifre kullanılıyor

            # E-posta gönderme
            server.sendmail(self.from_email, self.to_email, message.as_string())
            server.quit()
            print("E-posta başarıyla gönderildi.")

        except Exception as e:
            # Hata durumunda e-posta gönderimi tekrar denenir
            hata = traceback.format_exc()
            print("E-posta gönderilirken bir hata oluştu:", hata)
            time.sleep(bekle)
            self.mail_gonder(baslik, mesaj, bekle, smtp_server, smtp_port)  # Recursive olarak tekrar dene

    def saniye_to_hms(self,seconds):
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return hours, minutes, seconds

    def piyasa_acik_mi(self):
        # Şu anki tarihi ve saati al
        simdi = datetime.now()

        # Haftanın gününü kontrol et (0=Pazartesi, 1=Salı, ..., 4=Cuma)
        haftanin_gunu = simdi.weekday()

        # Resmi tatil günleri (burada örnek olarak bazı tatil günlerini ekledik)
        tatil_gunleri = [
            datetime(simdi.year, 1, 1),  # Yılbaşı
            datetime(simdi.year, 5, 1),  # 1 Mayıs İşçi Bayramı
            datetime(simdi.year, 10, 29),  # 29 Ekim Cumhuriyet Bayramı
            datetime(simdi.year, 4, 23),  # Ulusal Egemenlik ve Cocuk Bayramı
            datetime(simdi.year, 7, 15),  # Demokrasi Bayamı
            datetime(simdi.year, 8, 30),  # Zafer Bayramı
        ]

        # Eğer hafta içi ve resmi tatil değilse ve saat 10.00 ile 18.00 arasındaysa True döndür
        if (haftanin_gunu < 5 and
            simdi.time() >= datetime(simdi.year, simdi.month, simdi.day, 10,0).time() and
            simdi.time() <= datetime(simdi.year, simdi.month, simdi.day, 18,15).time() and
            simdi not in tatil_gunleri):
            return True
        else:
            return False

    def veri_seti_olustur(self):
        bn = Binance()
        indikator = Indikator()
        close = bn.data("BTCUSDT", 1000, "4h", 4)
        low = bn.data("BTCUSDT", 1000, "4h", 3)
        high = bn.data("BTCUSDT", 1000, "4h", 2)
        acilis = bn.data("BTCUSDT", 1000, "4h", 1)
        opendate = bn.data("BTCUSDT", 1000, "4h", 0)
        rsi = indikator.RSI(close)
        ema21 = indikator.EMA(close, 21)
        ema7 = indikator.EMA(close, 7)
        atr = indikator.ATR(high, low, close)
        adx = indikator.ADX(high, low, close)
        sma50 = indikator.SMA(close, 50)
        sma200 = indikator.SMA(close, 200)
        # Listeleri bir dataframe'e dönüştürüyoruz ve eksik olan yerleri None (veya NaN) ile dolduruyoruz
        df = pd.DataFrame({
            'opendate': opendate,
            'acilis': acilis,
            'high': high,
            'low': low,
            'close': close,
            'rsi': rsi,
            'ema21': ema21,
            'ema7': ema7,
            'atr': atr,
            'adx': adx,
            'sma50': sma50,
            'sma200': sma200
        })

        # Eksik olan değerleri None (veya NaN) ile doldurma
        df = df.apply(lambda col: col.tolist() + [None] * (df['opendate'].size - col.size) if col.size < df[
            'opendate'].size else col)

        df.to_excel('veriler.xlsx', index=False)