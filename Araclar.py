import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import traceback
import time
import datetime
from Binance import Binance
from Indikator import Indikator
from IndikatorTest import IndikatorTest
from Stratejiler import Stratejiler
from StratejilerTest import StratejilerTest
import pandas as pd
import os
import requests
import json
from Backtest import Backtest
from dotenv import load_dotenv
from glob import glob
import numpy as np
from matplotlib.gridspec import GridSpec
import matplotlib.pyplot as plt
from datetime import datetime
from matplotlib.widgets import Cursor
import logging
from logging.handlers import RotatingFileHandler

# Klasör kontrolü
os.makedirs('Data/Strategy', exist_ok=True)

# Ortak format
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Trade Logger
trade = logging.getLogger('araclar')
trade.setLevel(logging.INFO)  # Logger seviyesi
trade_handler = RotatingFileHandler(
    'Log/trade.log',
    maxBytes=25 * 1024 * 1024,  # 25 MB
    backupCount=1              # 1 yedek dosya tut
)
trade_handler.setFormatter(formatter)
trade.addHandler(trade_handler)
trade.propagate = False

class Araclar:
    def __init__(self , to_email=None):
        env_files = glob(".env*")
        if env_files:
            # İlk bulunan dosyayı seç
            selected_env_file = env_files[0]
            # Seçilen dosyayı yükle
            load_dotenv(selected_env_file)
        else:
            print(".env ile başlayan bir dosya bulunamadı.")
        self.from_email=os.getenv('GONDERICI_EMAIL')
        self.to_email=os.getenv('ALICI_EMAIL')
        self.email_password=os.getenv('GONDERICI_EMAIL_SIFRE')
        self.telegram_api_token=os.getenv('TELEGRAM_API_TOKEN')
        self.telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID')
        self.strategy_limit_15m=os.getenv('STRATEGY_LIMIT_15M')
        self.strategy_limit_1h=os.getenv('STRATEGY_LIMIT_1H')
        self.strategy_limit_4h=os.getenv('STRATEGY_LIMIT_4H')
        self.strategy_limit_1d=os.getenv('STRATEGY_LIMIT_1D')
        self.strategy_limit_check=os.getenv('STRATEGY_LIMIT_CHECK')
        self.update_strategy_check=os.getenv('UPDATE_STRATEGYS_CHECK')
        if(to_email is not None):
            self.to_email = to_email

    @staticmethod
    def internet_var_mi():
        try:
            # Google'a bir istek göndererek internet bağlantısını kontrol ediyoruz
            response = requests.get("https://www.google.com", timeout=5)
            # Eğer durum kodu 200 ise bağlantı başarılı
            if response.status_code == 200:
                return True
        except (requests.ConnectionError, requests.Timeout):
            return False
        return False
    @staticmethod
    def data_test_olustur(coin,periyot):
        binance = Binance()
        data = binance.get_coin_data(coin, periyot, 1000)
        high = data['high']
        low = data['low']
        close = data['close']
        path_close = "Data/close-test.txt"
        path_low = "Data/low-test.txt"
        path_high = "Data/high-test.txt"
        os.makedirs(os.path.dirname(path_close), exist_ok=True)
        os.makedirs(os.path.dirname(path_low), exist_ok=True)
        os.makedirs(os.path.dirname(path_high), exist_ok=True)
        # Dosyayı yaz
        with open(path_close, "w") as file:
            for i in close:
                file.write(f"{i},")
        # Dosyayı yaz
        with open(path_high, "w") as file:
            for i in high:
                file.write(f"{i},")
        # Dosyayı yaz
        with open(path_low, "w") as file:
            for i in low:
                file.write(f"{i},")

    def mail_gonder(self, baslik, mesaj, smtp_server="smtp.gmail.com", smtp_port=587):
        deneme_hakki=5
        while True:
            if not self.internet_var_mi():
                time.sleep(5)
                continue

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
                break
            except:
                hata = traceback.format_exc()
                trade.error(f"E-posta gönderilirken bir hata oluştu: {baslik} \n {hata}")
                deneme_hakki=deneme_hakki-1
                if deneme_hakki==0:
                    trade.error(f"!!! E-posta gonder deneme limiti bitti !!! kapatiliyor ...")
                    break
                continue

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
        binance = Binance()
        indikator = Indikator()
        data = binance.get_coin_data(coin, period, 1000)
        high = data['high']
        low = data['low']
        close = data['close']
        acilis = data['open']
        fark = list(pd.DataFrame(close).iloc[:,0]-pd.DataFrame(acilis).iloc[:,0])
        opendate = data['opendate']
        rsi = indikator.RSI(close)
        ema21 = indikator.EMA(close, 21)
        ema7 = indikator.EMA(close, 7)
        atr = indikator.ATR(high, low, close)
        adx = indikator.ADX(high, low, close)
        sma50 = indikator.SMA(close, 50)
        sma200 = indikator.SMA(close, 200)
        macd = indikator.MACD(close)
        bb=indikator.BB(close)
        tso = indikator.TSO(high, low, close)
        # Listeleri bir dataframe'e dönüştürüyoruz ve eksik olan yerleri None (veya NaN) ile dolduruyoruz
        df = pd.DataFrame({
            'opendate': opendate,
            'acilis': acilis,
            'high': high,
            'low': low,
            'close': close,
            'fark': fark,
            'rsi': rsi,
            'ema21': ema21,
            'ema7': ema7,
            'atr': atr,
            'adx': adx,
            'sma50': sma50,
            'sma200': sma200,
            'macd_val': macd[0],
            'macd_signal': macd[1],
            'bb_down' : bb[0],
            'bb_mid' : bb[1],
            'bb_up' : bb[2],
            'tso' : tso,
        })

        # Eksik olan değerleri None (veya NaN) ile doldurma
        df = df.apply(lambda col: col.tolist() + [None] * (df['opendate'].size - col.size) if col.size < df[
            'opendate'].size else col)
        path='Data/veriler.xlsx'
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df.to_excel(path, index=False)

    @staticmethod
    def veri_seti_olustur_strategys(coin,period):
        binance = Binance()
        indikator = Indikator()
        data = binance.get_coin_data(coin, period, 1000)
        high = data['high']
        low = data['low']
        close = data['close']
        acilis = data['open']
        opendate = data['opendate']

        # Strategyler
        macd,indicators = StratejilerTest.MACD(high, low, close)
        vmzi,indicators = StratejilerTest.VMZI(high, low, close)
        vama,indicators = StratejilerTest.VAMA(high, low, close)
        tso,indicators = StratejilerTest.TSO(high, low, close)
        bb_rsi,indicators = StratejilerTest.BB_RSI(high, low, close)
        fdi,indicators = StratejilerTest.FDI(high, low, close)
        bb_close,indicators = StratejilerTest.BB_Close(high, low, close)
        ma_cross,indicators = StratejilerTest.MA_Cross(high, low, close)
        dmo,indicators = StratejilerTest.DMO(high, low, close)
        bb_adx,indicators = StratejilerTest.BB_ADX(high, low, close)
        ema_stochastic,indicators = StratejilerTest.EMA_StochasticRSI(high, low, close)
        cci_atr,indicators = StratejilerTest.CCI_ATR(high, low, close)
        signal_moving_avarage,indicators = StratejilerTest.SignalMovingAvarage(high, low, close)
        super_trend,indicators = StratejilerTest.Super_Trend(high, low, close)
        squeeze_momentum,indicators = StratejilerTest.SqueezeMomentum(high, low, close)

        # Listeleri bir dataframe'e dönüştürüyoruz ve eksik olan yerleri None (veya NaN) ile dolduruyoruz
        df = pd.DataFrame({
            'opendate': opendate,
            'acilis': acilis,
            'high': high,
            'low': low,
            'close': close,
            'macd' : macd,
            'vmzi' : vmzi,
            'vama' : vama,
            'tso' : tso,
            'bb_rsi' : bb_rsi,
            'fdi' : fdi,
            'bb_close' : bb_close,
            'ma_cross' : ma_cross,
            'dmo' : dmo,
            'bb_adx' : bb_adx,
            'ema_stochastic' : ema_stochastic,
            'cci_atr' : cci_atr,
            'signal_moving_avarage' : signal_moving_avarage,
            'super_trend' : super_trend,
            'squeeze_momentum' : squeeze_momentum
        })

        # Değerleri değiştir
        df.replace({'BUY': 1, 'SELL': -1, 'False': 0}, inplace=True)

        # Gerekli sütunlarda veri türü dönüşümü
        df = df.astype({'macd': 'float64', 'vmzi': 'float64', 'vama': 'float64', 'tso': 'float64',
                        'bb_rsi': 'float64', 'fdi': 'float64', 'bb_close': 'float64', 'ma_cross': 'float64',
                        'dmo': 'float64', 'bb_adx': 'float64', 'ema_stochastic': 'float64',
                        'cci_atr': 'float64', 'signal_moving_avarage': 'float64', 'super_trend': 'float64',
                        'squeeze_momentum': 'float64'})

        # Eksik olan değerleri None (veya NaN) ile doldurma
        df = df.apply(lambda col: col.tolist() + [None] * (df['opendate'].size - col.size) if col.size < df[
            'opendate'].size else col)
        path = 'Data/veriler_strategys.xlsx'
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df.to_excel(path, index=False)

    @staticmethod
    def create_dataset():
        # 1. Veri yükleme optimizasyonu
        bas_veri_yukle = time.perf_counter()
        data = pd.read_csv(
            'Data/btcusd_1-min_data.csv',
            usecols=['Timestamp', 'Open', 'Close', 'High', 'Low']
        )
        son_veri_yukle = time.perf_counter()
        print(f"Veri yukleme süresi: {Araclar.saniye_to_hms(son_veri_yukle - bas_veri_yukle)}")

        # Tarih dönüşümü ve gereksiz sütunları düşürme
        bas_hesapla = time.perf_counter()
        data['timestamp'] = pd.to_datetime(data['Timestamp'], unit='s')
        data.drop(columns=['Timestamp'], inplace=True)  # Timestamp artık gereksiz

        # Bellek dostu veri tipi dönüşümleri
        data['Open'] = data['Open'].astype('float32')
        data['Close'] = data['Close'].astype('float32')
        data['High'] = data['High'].astype('float32')
        data['Low'] = data['Low'].astype('float32')

        # Tarih bazlı sütunlar
        data['yil'] = data['timestamp'].dt.year.astype('int16')
        data['ay'] = data['timestamp'].dt.month.astype('int8')
        data['gun'] = data['timestamp'].dt.day.astype('int8')
        data['saat'] = data['timestamp'].dt.hour.astype('int8')
        data['dakika'] = data['timestamp'].dt.minute.astype('int8')

        # Fiyat farkı hesaplama
        data['fark'] = (data['Close'] - data['Open']).astype('float32')

        # NumPy dizileri ile işlem
        close_np = data['Close'].values.astype('float32')
        high_np = data['High'].values.astype('float32')
        low_np = data['Low'].values.astype('float32')

        # 4. Indikatör hesaplamaları optimizasyonu
        print("Hesaplaniyor...")

        bb = np.array(Indikator.BB(close_np),dtype='float32')
        macd = np.array(Indikator.MACD(close_np),dtype='float32')
        log_return = np.log(data['Close'] / data['Close'].shift(1))
        stochastic_rsi = np.array(Indikator.StochasticRSI(close_np),dtype='float32')
        macd_dema = np.array(Indikator.MACD_DEMA(close_np),dtype='float32')

        hesaplamalar = {
            # INDIKATOR
            'rsi': np.array(Indikator.RSI(close_np),dtype='float32'),
            'ema21': np.array(Indikator.EMA(close_np, 21),dtype='float32'),
            'ema7': np.array(Indikator.EMA(close_np, 7),dtype='float32'),
            'atr': np.array(Indikator.ATR(high_np, low_np, close_np),dtype='float32'),
            'adx': np.array(Indikator.ADX(high_np, low_np, close_np),dtype='float32'),
            'sma50': np.array(Indikator.SMA(close_np, 50),dtype='float32'),
            'sma200': np.array(Indikator.SMA(close_np, 200),dtype='float32'),
            'macd_val': macd[0],
            'macd_signal': macd[1],
            'bb_bot': bb[0],
            'bb_mid': bb[1],
            'bb_top': bb[2],
            'log_return': log_return,
            'volatility': log_return.rolling(window=20).std(),

            'momentum' : np.array(Indikator.Momentum(close_np),dtype='float32'),
            'alpha_trend' : np.array(Indikator.Alpha_Trend(high_np, low_np, close_np),dtype='float32'),
            'super_trend_val' : np.array(Indikator.Super_Trend(high_np, low_np, close_np)[0],dtype='float32'),
            'parabolic_sar' : np.array(Indikator.ParabolicSAR(high_np, low_np),dtype='float32'),
            'stochastic_rsi_k' : stochastic_rsi[0],
            'stochastic_rsi_d' : stochastic_rsi[0],
            'signal_moving_avarage_50' : np.array(Indikator.SignalMovingAverage(close_np,50)[0],dtype='float32'),
            'macd_dema_macd' : macd_dema[0],
            'macd_dema_signal' : macd_dema[1],
            'bb_trend' : np.array(Indikator.BBTrend(close_np),dtype='float32'),

            # STRATEGY

            #'macd': np.array(Stratejiler.MACD(high_np, low_np, close_np),dtype='object'),
            #'vmzi': np.array(Stratejiler.VMZI(high_np, low_np, close_np),dtype='object'),
            #'bb_rsi': np.array(Stratejiler.BB_RSI(high_np, low_np, close_np),dtype='object'),
            #'fdi': np.array(Stratejiler.FDI(high_np, low_np, close_np),dtype='object'),
            #'bb_close': np.array(Stratejiler.BB_Close(high_np, low_np, close_np),dtype='object'),
            #'ma_cross': np.array(Stratejiler.MA_Cross(high_np, low_np, close_np),dtype='object'),
            #'dmo': np.array(Stratejiler.DMO(high_np, low_np, close_np),dtype='object'),
            #'bb_adx': np.array(Stratejiler.BB_ADX(high_np, low_np, close_np),dtype='object'),
            #'ema_stochastic': np.array(Stratejiler.EMA_StochasticRSI(high_np, low_np, close_np),dtype='object'),
            #'cci_atr': np.array(Stratejiler.CCI_ATR(high_np, low_np, close_np),dtype='object'),
            #'signal_moving_avarage': np.array(Stratejiler.SignalMovingAvarage(high_np, low_np, close_np),dtype='object'),
            #'super_trend': np.array(Stratejiler.Super_Trend(high_np, low_np, close_np),dtype='object'),
            #'squeeze_momentum': np.array(Stratejiler.SqueezeMomentum(high_np, low_np, close_np),dtype='object'),
            #'bbtrend_macddema': np.array(Stratejiler.BBTrend_MACDDEMA(high_np, low_np, close_np),dtype='object'),
            'local_min_max': np.array(Stratejiler.Local_Min_Max(high_np, low_np, close_np),dtype='object')

        }
        son_hesapla = time.perf_counter()
        print(f"Hesaplama süresi: {Araclar.saniye_to_hms(son_hesapla - bas_hesapla)} ")
        # 5. Strateji hesaplamaları optimizasyonu
        print("Dataframe oluşturuluyor ...")

        # 6. DataFrame oluşturma optimizasyonu
        last_data = pd.DataFrame({
            'timestamp': data['timestamp'],
            'yil': data['yil'] ,
            'ay':data['ay'] ,
            'gun':data['gun'] ,
            'saat':data['saat'] ,
            'dakika':data['dakika'],
            'open': data['Open'],
            'close': data['Close'],
            'high': data['High'],
            'low': data['Low'],
            'fark': data['fark'],
            **hesaplamalar,
        })

        # Ön işleme
        print("On isleme")

        last_data['sma_diff'] = last_data['sma50'] - last_data['sma200']
        last_data['local_min_max'] = last_data['local_min_max'].replace({'BUY':1,'SELL':-1,False: 0})
        last_data['local_min_max'].astype('float32')

        # Save
        print("Kaydet")
        path = 'Data/btcusd_1-min_data_indicators_strategys.csv'
        os.makedirs(os.path.dirname(path), exist_ok=True)
        last_data.to_csv(path, index=False,float_format='%.5f')

        print("İşlem tamamlandı!")
        print(last_data)
        print(f"Toplam satır sayısı: {len(last_data)}")
        print(f"Toplam sütun sayısı: {len(last_data.columns)}")
        print(f"Bellek kullanımı: {last_data.memory_usage(deep=True).sum() / 1024 ** 2:.2f} MB")

    @staticmethod
    def modify_dataset():
        data = pd.read_csv('Data/btcusd_1-min_data_indicators_strategys.csv')
        data = data.drop(['local_min_max'],axis=1)

        high_np = data['high'].values
        low_np = data['low'].values
        close_np = data['close'].values

        print('Hesaplaniyor ...')
        stochastic_rsi = Indikator.StochasticRSI(close_np)
        macd_dema = Indikator.MACD_DEMA(close_np)
        ek_ozellikler = {
            'momentum': Indikator.Momentum(close_np),
            'cci': Indikator.CCI(high_np, low_np, close_np),
            'alpha_trend': Indikator.Alpha_Trend(high_np, low_np, close_np),
            'super_trend_val': Indikator.Super_Trend(high_np, low_np, close_np)[0],
            'parabolic_sar': Indikator.ParabolicSAR(high_np, low_np),
            'stochastic_rsi_k': stochastic_rsi[0],
            'stochastic_rsi_d': stochastic_rsi[0],
            'signal_moving_avarage_50': Indikator.SignalMovingAverage(close_np, 50)[0],
            'macd_dema_macd': macd_dema[0],
            'macd_dema_signal': macd_dema[1],
            'bb_trend': Indikator.BBTrend(close_np),
            'local_min_max': Stratejiler.Local_Min_Max(high_np, low_np, close_np)
        }
        print('Hesaplamalar tamamlandi')

        for ozellik in ek_ozellikler.keys():
            data[ozellik] = ek_ozellikler[ozellik]
        data = data.dropna()
        data.replace({'BUY': 1, 'SELL': -1, False: 0}, inplace=True)
        data = data.astype(np.float32)

        print("Kaydet")
        path = 'Data/btcusd_1-min_data_indicators_strategys_modify.csv'
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data.to_csv(path, index=False)

    @staticmethod
    def mum_olusmasini_bekle(periyot):
        zaman_dilimleri = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
            "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800, "1M": 2419200
        }
        if time.time() % zaman_dilimleri[periyot] > 10:
            time.sleep(zaman_dilimleri[periyot] - (time.time() % zaman_dilimleri[periyot]))

    def strategy_result_analyze(self,input="Data/strategy_results.xlsx", output_file='Data/strategy_results_analyze.xlsx'):
        # Excel dosyasını oku
        df = pd.read_excel(input)

        # Stratejilerin kümülatif kar zarar ortalamasını ve başarılı olup olmadığını hesaplama
        grouped = df.groupby(['periyot', 'strategy name']).agg(
            karlilik_ortalamasi=pd.NamedAgg(column='kümülatif kar zarar (%)', aggfunc='mean'),
            toplam_karli_islem=pd.NamedAgg(column='karlı işlemler', aggfunc='sum'),
            toplam_zararli_islem=pd.NamedAgg(column='zararlı işlemler', aggfunc='sum'),
            ortalama_islem_sonucu=pd.NamedAgg(column='ortalama işlem sonucu', aggfunc='mean')
        ).reset_index()

        # (Karlı işlemler / Zararlı işlemler) oranını hesapla ve başarılı stratejilere '*' ekle
        grouped['is_successful'] = (grouped['toplam_karli_islem'] / grouped['toplam_zararli_islem']) > 1
        grouped['strategy_summary'] = grouped['strategy name']
        grouped.loc[grouped['is_successful'], 'strategy_summary'] = '*' + grouped['strategy_summary']

        # Her periyot için ayrı pivot tablolar oluştur ve sıralama işlemi yap
        pivot_tables = []
        result_dict = {}

        for period in grouped['periyot'].unique():
            period_group = grouped[grouped['periyot'] == period]
            period_group_sorted = period_group.sort_values('karlilik_ortalamasi', ascending=False)

            # Sadece strategy_summary, karlilik_ortalamasi, toplam karlı ve toplam zararlı işlemleri al
            period_summary = period_group_sorted[['strategy_summary', 'karlilik_ortalamasi',
                                                  'toplam_karli_islem', 'toplam_zararli_islem',
                                                  'ortalama_islem_sonucu']]
            period_summary.index = range(len(period_summary))  # Satırları sıfırdan numaralandır
            period_summary.columns = [f'{period} Strategy', f'{period} Karlilik Ortalaması',
                                      f'{period} Karlı İşlemler',
                                      f'{period} Zararlı İşlemler',
                                      f'{period} Ortalama İşlem Sonucu']  # Sütun adlarını değiştir
            pivot_tables.append(period_summary)

            # JSON için veriyi hazırlama
            result_dict[period] = period_summary.to_dict(orient='records')

        # Tüm pivot tabloları birleştir (eksik değerleri doldurmayacak şekilde)
        final_table = pd.concat(pivot_tables, axis=1, ignore_index=False)

        # Excel dosyasına kaydet
        final_table.to_excel(output_file, index=False)

        # JSON dosyasına kaydet
        json_output_file = output_file.replace(".xlsx", ".json")
        with open(json_output_file, 'w', encoding='utf-8') as f:
            json.dump(result_dict, f, indent=4, ensure_ascii=False)

        trade.info(f"Sonuçlar {output_file} ve {json_output_file} dosyalarına başarıyla kaydedildi.")

    def strategy_analyze_save(self):
        # Dosya var mı kontrolü
        if os.path.exists('Data/strategy_results_analyze.json'):
            with open('Data/strategy_results_analyze.json', 'r',encoding="utf-8") as f:
                result = json.load(f)  # JSON dosyasını yükle
                strategys = {}

                # JSON içindeki periyotlara göre işlem
                for period, data in result.items():
                    strategies_list = []
                    # Periyoda göre strateji sayısını belirle
                    if period == '15m':
                        num_strategies = 3
                        limit=float(self.strategy_limit_15m)
                    elif period == '1h':
                        num_strategies = 3
                        limit=float(self.strategy_limit_1h)
                    elif period == '4h':
                        num_strategies = 3
                        limit=float(self.strategy_limit_4h)
                    elif period == '1d':
                        num_strategies = 3
                        limit=float(self.strategy_limit_1d)
                    else:
                        num_strategies = 0  # Eğer belirli bir periyot yoksa 0 strateji al

                    # Stratejileri listeye ekle, yalnızca belirli sayıda strateji al
                    for strategy in data[:num_strategies]:
                        if self.strategy_limit_check == "True" and strategy[f"{period} Karlilik Ortalaması"] > limit:
                            strategies_list.append(strategy[f"{period} Strategy"].replace("*", ""))
                        elif self.strategy_limit_check != "True":
                            strategies_list.append(strategy[f"{period} Strategy"].replace("*", ""))

                    # Stratejileri kaydet
                    strategys[period] = strategies_list

                # Sonuçları yeni JSON dosyasına yaz
                with open('Data/strategys.json', 'w') as f:
                    json.dump(strategys, f, indent=4)

            print("Strateji analizi başarıyla tamamlandı ve stratejiler kaydedildi.")
        else:
            print("Hata: 'strategy_results_analyze.json' dosyası bulunamadı.")

    @staticmethod
    def get_strategys():
        # Data klasörünün mevcut olup olmadığını kontrol et ve oluştur
        os.makedirs("Data", exist_ok=True)
        default_strategys = {"15m": ["BB_RSI","BB_ADX","FDI"],"1d": ["MA_Cross","MACD","DMO"],"1h": ["TSO","BB_ADX","BB_RSI"],"4h": ["VMZI","DMO","FDI"]}

        # Dosya kontrolü
        if not os.path.exists('Data/strategys.json'):
            # Varsayılan dosyayı oluştur
            with open('Data/strategys.json', 'w') as f:
                json.dump(default_strategys, f, indent=4)
            print("Varsayılan strategys.json oluşturuldu.")
            
        with open(f'Data/strategys.json', 'r') as f:
            result = json.load(f)
            strategys = {}
            for period in result.keys():
                function_list = []
                # Fonksiyon isimlerini globals() ile eşleştir ve diziye ekle
                for name in result[period]:
                    if hasattr(Stratejiler, name):  # functions modülünde bu isimde bir fonksiyon var mı?
                        function_list.append(getattr(Stratejiler, name))
                    else:
                        print(f"Fonksiyon tanımlı değil: {name}")
                strategys[period] = function_list
        return strategys

    @staticmethod
    def listeden_sahip_olduklarimi_cikar(coinlist,sahip_olduklarim):
        # Eğer alım yapacaksam sahip olunan coinleri liste dışı bırak
        for sil in sahip_olduklarim.keys():
            try:
                coinlist.remove(sil)
            except:
                continue
        return coinlist

    @staticmethod
    def coin_indikator_degerleri(coin,periyot,adet=10):
        binance = Binance()
        data=binance.get_coin_data(coin,periyot,1000)
        high = data['high']
        low = data['low']
        close = data['close']

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
    def coin_strateji_degerleri(coin,periyot,adet):
        binance = Binance()
        data = binance.get_coin_data(coin, periyot, 1000)
        high = data['high']
        low = data['low']
        close = data['close']

        strategies = [getattr(Stratejiler, func) for func in dir(Stratejiler)
                      if callable(getattr(Stratejiler, func))
                      and not func.startswith("__")
                      and not getattr(Stratejiler, func).__name__ in ["dinamik_stop_lose", "static_stop_lose",
                                                                          "destek_stop_lose", "Alpha_Trend","take_profit"]]
        for strategy in strategies:
            print(f"{strategy.__name__} : {strategy(high, low, close)[-adet:]}")

    @staticmethod
    def mum_sagligi(open,close):
        uzunluk=len(open)
        resault=0
        for i in range(uzunluk):
            if open[i] == close[i]:
                resault = resault + 1
        return resault

    @staticmethod
    def coinlist_sira_duzenle(periyot):
        binance = Binance()
        while True:
            Araclar.mum_olusmasini_bekle(periyot)
            coinlist=binance.coin_list()
            sirali_liste = binance.coins_sorted_by_volume(coinlist,periyot)
            binance.create_coin_list(sirali_liste)
            time.sleep(10)

    def telegram_mesaj_gonder(self, mesaj):
        max_length = 4096  # Telegram'ın maksimum mesaj uzunluğu sınırı
        deneme_hakki=5
        while True:
            if not self.internet_var_mi():
                print("Internet yok. Mesaj gönderilemedi!")
                time.sleep(5)
                continue

            if self.telegram_chat_id == "" or self.telegram_api_token == "":
                print("Gerekli bilgiler eksik")
                break

            try:
                # Mesajı parçalar halinde gönderme
                for i in range(0, len(mesaj), max_length):
                    chunk = mesaj[i:i + max_length]
                    url = f"https://api.telegram.org/bot{self.telegram_api_token}/sendMessage"
                    payload = {
                        "chat_id": self.telegram_chat_id,
                        "text": chunk
                    }

                    response = requests.post(url, data=payload)

                    if response.status_code == 200:
                        pass
                    else:
                        print("Mesaj gönderilemedi:", response.text)
                        time.sleep(5)
                        continue
            except:
                trade.error("!!! Telegram mesaji gonderiminde hata !!!")
                deneme_hakki=deneme_hakki-1
                if deneme_hakki==0:
                    trade.error("!!! Telegram mesaj deneme hakki bitti !!! kapatiliyor ...")
                    break
                continue

            # Tüm parçalar gönderildikten sonra döngüden çık
            break

    def update_strategys(self,periyod):
        backtest=Backtest()
        while True:
            Araclar.mum_olusmasini_bekle(periyod)
            if self.strategy_limit_check != "True":
                time.sleep(10)
                continue
            araclar=Araclar()
            # Hesaplamalar Yapılıyor
            backtest.paralel_hesaplama()
            # Analiz yapılıyor
            araclar.strategy_result_analyze()
            # strategy.json hazırlanıyor
            araclar.strategy_analyze_save()

    @staticmethod
    def stratejinin_buy_verdikleri(strategy_name,periyot):
        binance = Binance()
        coinlist = binance.coin_list()
        strategy = getattr(Stratejiler,strategy_name)
        sonuc=[]
        for coin in coinlist:
            data=binance.get_coin_data(coin,periyot,1000)
            high=data['high']
            low=data['low']
            close=data['close']
            signal = strategy(high[:-1],low[:-1],close[:-1])
            if signal[-1]=="BUY" and "BUY" not in signal[-6:-1]:
                sonuc.append(coin)
        print(sonuc)
        return sonuc

    @staticmethod
    def tekli_analiz(coin, periyot,stop=True,canli_veri=True):
        result = Backtest.Hesapla(coin, periyot, stop=stop,canli_veri=canli_veri)
        Backtest.Kayit_Et([result['EXCEL DATA']])
        Backtest.backtest_islem_gecmisi_analiz(result['ISLEM GECMISI'])
        Araclar.strategy_result_analyze()

    @staticmethod
    def ondalik_basamak_sayisi(sayi):
        # String'e çevir ve noktadan sonrasını al
        str_sayi = str(sayi)
        if '.' in str_sayi:
            return len(str_sayi.split('.')[1])  # Noktadan sonrasının uzunluğu
        else:
            return 0  # Eğer nokta yoksa, ondalık basamak yoktur

    @staticmethod
    def strategys_update_check(periyod,limit):
        if os.path.exists('Data/strategy_results_analyze.json'):
            with open('Data/strategy_results_analyze.json', 'r',encoding="utf-8") as f:
                result = json.load(f)  # JSON dosyasını yükle
                # JSON içindeki periyotlara göre işlem
                for period, data in result.items():
                    # Periyoda göre strateji sayısını belirle
                    if period == periyod:
                        for strategy in data[:3]:
                            if strategy[f"{period} Karlilik Ortalaması"] < limit:
                                return False
                        return True
        return None

    @staticmethod
    def acik_pozisyonlarin_grafigi(periyot):
        binance = Binance()

        # Dosya kontrolü
        file_path = f'Trade_Durumu/trade_durumu_{periyot}.json'
        if not os.path.exists(file_path):
            print(f"{periyot} için açık işlem dosyası bulunamadı.")
            return

        # JSON verisini yükle
        with open(file_path, 'r') as f:
            durum = json.load(f)

        islem_acik = durum['islem_acik']
        alinan_coin = durum['alinan_coin']
        alim_fiyati = durum['alim_fiyati']
        strategy_func = getattr(StratejilerTest, durum['sell_strategy']) if durum['sell_strategy'] else None
        periyot = durum['periyot']

        if not islem_acik:
            print(f"{periyot} için açık işlem yok!")
            return

        # Binance verisi çek
        data = binance.get_coin_data(alinan_coin, periyot, 1000)
        open_date = [datetime.fromtimestamp(ts / 1000.0) for ts in data['opendate']]
        open_price = data['open']
        high = data['high']
        low = data['low']
        close = data['close']
        volume = data['volume_coin']

        n = len(open_price)

        # Strateji sonucu ve indikatör değerlerini hesapla
        strategy_results, indicators = strategy_func(high, low, close)

        # Ana grafik
        num_sub_graphs = len(indicators['sub_indicators'])
        total_rows = 2 + num_sub_graphs
        fig = plt.figure(figsize=(16, 6 + 3 * num_sub_graphs))
        gs = GridSpec(total_rows, 2, height_ratios=[2] + [1] * num_sub_graphs + [1])

        ax_main = fig.add_subplot(gs[0, :])
        ax_main.set_title(f"{alinan_coin} {periyot} Grafiği")
        ax_main.set_ylabel("Fiyat")

        # Mum grafiği
        for i in range(len(close)):
            color = 'green' if close[i] >= open_price[i] else 'red'
            ax_main.plot([i, i], [low[i], high[i]], color=color, linewidth=1)
            ax_main.add_patch(
                plt.Rectangle((i - 0.4, min(open_price[i], close[i])), 0.8, abs(close[i] - open_price[i]), color=color))

        # Alış fiyatı
        ax_main.axhline(alim_fiyati, color='blue', linestyle='--', label=f"Alış Fiyatı: {alim_fiyati}")

        # Ana indikatörler
        if indicators['main_indicators']:
            for name, values in indicators['main_indicators'].items():
                ax_main.plot(values, label=name)

        ax_main.legend()

        # Alt grafikler
        ax_sub_list = []
        for idx, sub_indicator in enumerate(indicators['sub_indicators']):
            ax_sub = fig.add_subplot(gs[1 + idx, :])
            ax_sub_list.append(ax_sub)
            for name, values in sub_indicator.items():
                ax_sub.plot(values, label=name)

            # Sabit yatay çizgileri çizme
            if 'sub_horizontal_lines' in indicators:
                for line in indicators['sub_horizontal_lines'][idx]:  # Alt grafik için yatay çizgiler
                    ax_sub.axhline(line['value'], color=line['color'], linestyle='--')

            ax_sub.legend()

        # Kümülatif sonuç grafikleri
        ax_cumulative = fig.add_subplot(gs[-1, 0])


        ax_cumulative_percentage = fig.add_subplot(gs[-1, 1])


        initial_capital = 100
        capital_history = [initial_capital]
        profit_loss_percentages = []

        last_signal = None
        buy_price = None

        for i, signal in enumerate(strategy_results):
            if last_signal is None or last_signal == 'red':
                if signal == "BUY":
                    last_signal = 'green'
                    buy_price = close[i]
            elif last_signal == 'green':
                if signal == "SELL":
                    last_signal = 'red'
                    sell_price = close[i]
                    profit_percentage = ((sell_price - buy_price) / buy_price) * 100
                    current_capital = capital_history[-1] * (1 + profit_percentage / 100)
                    capital_history.append(current_capital)
                    profit_loss_percentages.append(profit_percentage)

        # Kümülatif Kâr/Zarar Grafiği
        final_capital = capital_history[-1] if capital_history else initial_capital
        ax_cumulative.axhline(initial_capital, color='black', linestyle='--')
        ax_cumulative.plot(capital_history, 'o-', label=f"Kapital (Son: {final_capital:.2f})")
        ax_cumulative.legend()

        # İşlem Sonuçları (%) Grafiği
        ax_cumulative_percentage.axhline(0, color='black', linestyle='--')
        ax_cumulative_percentage.plot(profit_loss_percentages, 'o-', label="İşlem Sonuçları (%)")
        ax_cumulative_percentage.legend()

        # X-ticks'leri kaldır
        for ax in [ax_main] + ax_sub_list:
            ax.set_xticks([])

        # Son eksen için yalnızca X-ticks gösterilir
        ax_cumulative_percentage.set_xlabel("Zaman")

        # Zoom ve pan hareketlerinin eş zamanlı olması için paylaşımı ayarla
        for ax in [ax_main] + ax_sub_list:
            ax.sharex(ax_main)

        a = 0
        # Mouse ile veri inceleme
        cursor_main = Cursor(ax_main, useblit=True, color='blue', linewidth=1)

        def format_coord(x, y):
            index = int(round(x))
            if 0 <= index < n:
                o = open_price[index]
                h = high[index]
                l = low[index]
                c = close[index]
                v = volume[index]
                time = open_date[index]

                # Yüzdelik değişim hesaplama
                if o != 0:
                    price_change_percent = ((c - o) / o) * 100
                else:
                    price_change_percent = 0

                indicator_values = {}
                if indicators['main_indicators']:
                    indicator_values.update(
                        {name: values[index] for name, values in indicators['main_indicators'].items() if
                         values[index] is not None})
                if indicators['sub_indicators']:
                    for sub in indicators['sub_indicators']:
                        indicator_values.update(
                            {name: values[index] for name, values in sub.items() if values[index] is not None})

                # Fiyat değişimini ve diğer indikatörleri ekle
                indicator_text = ", ".join(f"{name}: {value:.2f}" for name, value in indicator_values.items())
                return f"Time: {time}, Open: {o}, High: {h}, Low: {l}, Close: {c}, Volume: {v} ,Change: {price_change_percent:.2f}%, {indicator_text}"
            return f"X: {x:.2f}, Y: {y:.2f}"

        ax_main.format_coord = format_coord

        # Mouse ile veri inceleme
        cursor_main = Cursor(ax_cumulative_percentage, useblit=True, color='blue', linewidth=1)

        def format_coord(x, y):
            index = int(round(x))
            if 0 <= index < n:
                result = profit_loss_percentages[index]

                return f"{index}. İşlem Sonucu: {result:.2f}% "
            return f"X: {x:.2f}, Y: {y:.2f}"

        ax_cumulative_percentage.format_coord = format_coord

        plt.tight_layout()
        plt.show()

    @staticmethod
    def ms_to_d_m_y(saniye):
        """
            Unix Timestamp'i gün, ay ve yıl olarak döndüren bir fonksiyon.

            Args:
                timestamp (float): Unix Timestamp değeri (milisaniye olarak)

            Returns:
                tuple: (gün, ay, yıl) şeklinde bir tuple döndürür.
        """
        # Tarihi dönüştür
        date = datetime.utcfromtimestamp(saniye)

        # Gün, ay ve yılı ayıkla
        day = date.day
        month = date.month
        year = date.year

        return day, month, year
    @staticmethod
    def coin_aylik_sonuc(coin,periyot):
        binance = Binance()
        data = binance.get_coin_data(coin,periyot,1000)
        opendate = data['opendate']
        open_price = data['open']
        close = data['close']
        high = data['high']
        low = data['low']
        vol = data['volume_coin']
        result={1:[],2:[],3:[],4:[],5:[],6:[],7:[],8:[],9:[],10:[],11:[],12:[]}
        for i in range(len(opendate)):
            gun,ay,yil=Araclar.ms_to_d_m_y(opendate[i]/1000)
            change = ((close[i]/open_price[i])-1)*100
            if change > 0:
                change=1
            else:
                change = -1
            result[ay].append(change)
        print(f"Ocak: {result[1]}| {sum(result[1])}\nSubat: {result[2]}| {sum(result[2])}\nMart: {result[3]}| {sum(result[3])}\nNisan: {result[4]}| {sum(result[4])}\nMayis: {result[5]}| {sum(result[5])}\nHaziran: {result[6]}| {sum(result[6])}\n"
              f"Temmuz: {result[7]}| {sum(result[7])}\nAgustos: {result[8]}| {sum(result[8])}\nEylul: {result[9]}| {sum(result[9])}\nEkim: {result[10]}| {sum(result[10])}\nKasim: {result[11]}| {sum(result[11])}\nAralik: {result[12]}| {sum(result[12])}\n")

    @staticmethod
    def change_env_variable(file_path, key, new_value):
        with open(file_path, "r") as file:
            lines = file.readlines()

        with open(file_path, "w") as file:
            for line in lines:
                if line.startswith(f"{key}="):
                    file.write(f"{key}={new_value}\n")
                else:
                    file.write(line)