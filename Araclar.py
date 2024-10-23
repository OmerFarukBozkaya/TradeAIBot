import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import traceback
import time
from datetime import datetime
from Binance import Binance
from Indikator import Indikator
from Stratejiler import Stratejiler
import pandas as pd

class Araclar:
    def __init__(self, from_email=None, to_email=None, email_password=None):
        if from_email and to_email and email_password :
            self.from_email = from_email  # Nesnenin from_email değeri
            self.to_email = to_email  # Nesnenin to_email değeri
            self.email_password = email_password  # Nesnenin şifresi
        elif(to_email is not None):
            self.to_email = to_email
            self.from_email,self.email_password,self.default_to_email = self.load_settings()
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
        except Exception as e:
            # Hata durumunda e-posta gönderimi tekrar denenir
            hata = traceback.format_exc()
            print("E-posta gönderilirken bir hata oluştu:", hata)
            time.sleep(bekle)
            self.mail_gonder(baslik, mesaj, bekle, smtp_server, smtp_port)  # Recursive olarak tekrar dene

    @staticmethod
    def saniye_to_hms(seconds):
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        # Saat, dakika ve saniyeleri sıfır ile doldurup 2 basamaklı hale getir
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

    @staticmethod
    def piyasa_acik_mi():
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

    @staticmethod
    def veri_seti_olustur(coin,period):
        bn = Binance()
        indikator = Indikator()
        close = bn.data(coin, 1000, period, 4)
        low = bn.data(coin, 1000, period, 3)
        high = bn.data(coin, 1000, period, 2)
        acilis = bn.data(coin, 1000, period, 1)
        opendate = bn.data(coin, 1000, period, 0)
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

    @staticmethod
    def mum_olusmasini_bekle(periyot):
        zaman_dilimleri = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
            "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800, "1M": 2419200
        }
        if time.time() % zaman_dilimleri[periyot] > 10:
            time.sleep(zaman_dilimleri[periyot] - (time.time() % zaman_dilimleri[periyot]))

    @staticmethod
    def strategy_result_analyze(input="strategy_results.xlsx", output_file='strategy_results_analyze.xlsx'):
        # Excel dosyasını oku
        df = pd.read_excel(input)

        # Stratejilerin kümülatif kar zarar ortalamasını ve başarılı olup olmadığını hesaplama
        grouped = df.groupby(['periyot', 'strategy name']).agg(
            karlilik_ortalamasi=pd.NamedAgg(column='kümülatif kar zarar (%)', aggfunc='mean'),
            toplam_karli_islem=pd.NamedAgg(column='karlı işlemler', aggfunc='sum'),
            toplam_zararli_islem=pd.NamedAgg(column='zararlı işlemler', aggfunc='sum'),
            ortalama_islem_sonucu = pd.NamedAgg(column='ortalama işlem sonucu', aggfunc='mean')
        ).reset_index()

        # (Karlı işlemler / Zararlı işlemler) oranını hesapla ve başarılı stratejilere '*' ekle
        grouped['is_successful'] = (grouped['toplam_karli_islem'] / grouped['toplam_zararli_islem']) > 1
        grouped['strategy_summary'] = grouped['strategy name']
        grouped.loc[grouped['is_successful'], 'strategy_summary'] = '*' + grouped['strategy_summary']

        # Her periyot için ayrı pivot tablolar oluştur ve sıralama işlemi yap
        pivot_tables = []
        for period in grouped['periyot'].unique():
            period_group = grouped[grouped['periyot'] == period]
            period_group_sorted = period_group.sort_values('karlilik_ortalamasi', ascending=False)

            # Sadece strategy_summary, karlilik_ortalamasi, toplam karlı ve toplam zararlı işlemleri al
            period_summary = period_group_sorted[['strategy_summary', 'karlilik_ortalamasi',
                                                  'toplam_karli_islem', 'toplam_zararli_islem','ortalama_islem_sonucu']]
            period_summary.index = range(len(period_summary))  # Satırları sıfırdan numaralandır
            period_summary.columns = [f'{period} Strategy', f'{period} Karlilik Ortalaması',
                                      f'{period} Karlı İşlemler',
                                      f'{period} Zararlı İşlemler',
                                      f'{period} Ortalama İşlem Sonucu']  # Sütun adlarını değiştir
            pivot_tables.append(period_summary)

        # Tüm pivot tabloları birleştir (eksik değerleri doldurmayacak şekilde)
        final_table = pd.concat(pivot_tables, axis=1, ignore_index=False)

        # Sonucu bir Excel dosyasına yaz
        final_table.to_excel(output_file, index=False)

        print(f"Sonuçlar {output_file} dosyasına başarıyla kaydedildi.")

    @staticmethod
    def listeden_sahip_olduklarimi_cikar(list):
        # Eğer alım yapacaksam sahip olunan coinleri liste dışı bırak
        binance = Binance()
        for sil in binance.sahip_olduklarim().keys():
            try:
                list.remove(sil[0])
            except:
                continue
        return list

    @staticmethod
    def coin_indikator_degerleri(coin,periyot,adet=10):
        binance = Binance()
        high = binance.data(coin,1000,periyot,2)
        low = binance.data(coin, 1000, periyot, 3)
        close = binance.data(coin, 1000, periyot, 4)

        ema_9 = Indikator.EMA(close,9)[adet*-1:]
        ema_50 = Indikator.EMA(close,50)[adet*-1:]
        ema_200 = Indikator.EMA(close,200)[adet*-1:]
        bb=Indikator.BB(close)
        bb_low=bb[0][adet*-1:]
        bb_mid=bb[1][adet*-1:]
        bb_up=bb[2][adet*-1:]
        rsi=Indikator.RSI(close)[adet*-1:]
        fib=Indikator.FIB(close)[-1]
        macd=Indikator.MACD(close)
        macd_value=macd[0][adet*-1:]
        macd_signal=macd[1][adet*-1:]
        atr=Indikator.ATR(high, low, close)[adet*-1:]
        adx=Indikator.ADX(high, low, close)[adet*-1:]
        cmi=Indikator.CMI(close, high, low)[adet*-1:]
        dmo=Indikator.DMO(close)[adet*-1:]
        vmzi=Indikator.VMZI(close)[adet*-1:]
        fdi=Indikator.FDI(close)[adet*-1:]
        vama=Indikator.VAMA(close)[adet*-1:]
        cci=Indikator.CCI(high, low, close)[adet*-1:]
        tso=Indikator.TSO(high, low, close)[adet*-1:]

        print(f"Close: {close[adet*-1:]}")
        print(f"EMA 9: {ema_9}")
        print(f"EMA 50: {ema_50}")
        print(f"EMA 200: {ema_200}")
        print(f"BB(low): {bb_low}")
        print(f"BB(mid): {bb_mid}")
        print(f"BB(up): {bb_up}")
        print(f"RSI: {rsi}")
        print(f"FIB: {fib}")
        print(f"MACD Values: {macd_value}")
        print(f"MACD Signal: {macd_signal}")
        print(f"ATR: {atr}")
        print(f"ADX: {adx}")
        print(f"CMI: {cmi}")
        print(f"DMO: {dmo}")
        print(f"VMZI: {vmzi}")
        print(f"FDI: {fdi}")
        print(f"VAMA: {vama}")
        print(f"CCI: {cci}")
        print(f"TSO: {tso}")

    @staticmethod
    def coin_strateji_degerleri(coin,periyot):
        binance = Binance()
        high = binance.data(coin, 1000, periyot, 2)
        low = binance.data(coin, 1000, periyot, 3)
        close = binance.data(coin, 1000, periyot, 4)

        strategys=[Stratejiler.MACD,Stratejiler.VMZI,Stratejiler.VAMA,Stratejiler.TSO,
                   Stratejiler.BB_RSI,Stratejiler.FDI,Stratejiler.BB_Close,Stratejiler.MA_Cross,
                   Stratejiler.DMO,Stratejiler.BB_ADX]
        for strategy in strategys:
            print(f"{strategy.__name__} : {strategy(high, low, close)}")
