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
import os
import requests
import json
import threading
from Backtest import Backtest

if not os.path.exists('Data'):
    os.makedirs('Data')

class Araclar:
    def __init__(self , to_email=None):
        with open("settings.json","r") as file:
            data=json.load(file)
        self.from_email=data['GONDERICI_EMAIL']
        self.to_email=data['ALICI_EMAIL']
        self.email_password=data['GONDERICI_EMAIL_SIFRE']
        self.telegram_api_token=data['TELEGRAM_API_TOKEN']
        self.telegram_chat_id=data['TELEGRAM_CHAT_ID']
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
        while True:
            if not Araclar.internet_var_mi():
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
                print("E-posta gönderilirken bir hata oluştu:", hata)
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
    def mum_olusmasini_bekle(periyot):
        zaman_dilimleri = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
            "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800, "1M": 2419200
        }
        if time.time() % zaman_dilimleri[periyot] > 10:
            time.sleep(zaman_dilimleri[periyot] - (time.time() % zaman_dilimleri[periyot]))

    def strategy_result_analyze(input="Data/strategy_results.xlsx", output_file='Data/strategy_results_analyze.xlsx'):
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

        print(f"Sonuçlar {output_file} ve {json_output_file} dosyalarına başarıyla kaydedildi.")

    @staticmethod
    def strategy_analyze_save():
        # Dosya var mı kontrolü
        if os.path.exists('Data/strategy_results_analyze.json'):
            with open('Data/strategy_results_analyze.json', 'r') as f:
                result = json.load(f)  # JSON dosyasını yükle
                strategys = {}

                # JSON içindeki periyotlara göre işlem
                for period, data in result.items():
                    strategies_list = []
                    # Periyoda göre strateji sayısını belirle
                    if period == '15m':
                        num_strategies = 3
                    elif period == '1h':
                        num_strategies = 3
                    elif period == '4h':
                        num_strategies = 3
                    elif period == '1d':
                        num_strategies = 3
                    else:
                        num_strategies = 0  # Eğer belirli bir periyot yoksa 0 strateji al

                    # Stratejileri listeye ekle, yalnızca belirli sayıda strateji al
                    strategies_list = [
                        strategy[f"{period} Strategy"].replace("*", "")
                        for strategy in data[:num_strategies]
                    ]

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
    def listeden_sahip_olduklarimi_cikar(coinlist):
        # Eğer alım yapacaksam sahip olunan coinleri liste dışı bırak
        binance = Binance()
        for sil in binance.sahip_olduklarim().keys():
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

        strategys=[Stratejiler.MACD,Stratejiler.VMZI,Stratejiler.VAMA,Stratejiler.TSO,
                   Stratejiler.BB_RSI,Stratejiler.FDI,Stratejiler.BB_Close,Stratejiler.MA_Cross,
                   Stratejiler.DMO,Stratejiler.BB_ADX]
        for strategy in strategys:
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

    def telegram_mesaj_gonder(self,mesaj):
        while True:
            # Mesaj gönderme URL'si
            if self.telegram_chat_id is None or self.telegram_api_token is None:
                break
            url = f"https://api.telegram.org/bot{self.telegram_api_token}/sendMessage"

            # Mesaj gönderme isteği
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": mesaj
            }
            response = requests.post(url, data=payload)

            if response.status_code == 200:
                break
            else:
                print("Mesaj gönderilemedi:", response.text)
                time.sleep(5)
                continue

    @staticmethod
    def update_strategys(periyod):
        backtest=Backtest()
        while True:
            Araclar.mum_olusmasini_bekle(periyod)
            # Hesaplamalar Yapılıyor
            backtest.paralel_hesaplama()
            # Analiz yapılıyor
            Araclar.strategy_result_analyze()
            # strategy.json hazırlanıyor
            Araclar.strategy_analyze_save()

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



