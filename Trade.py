import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from Binance import Binance
from Araclar import Araclar
from Stratejiler import Stratejiler
import logging
from logging.handlers import RotatingFileHandler
import threading
import json
import os
from dotenv import load_dotenv
from Indikator import Indikator
from glob import glob

if not os.path.exists('Log'):
    os.makedirs('Log')
if not os.path.exists('Trade_Durumu'):
    os.makedirs('Trade_Durumu')

# Ortak format
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Trade Logger
trade = logging.getLogger('trade')
trade.setLevel(logging.INFO)  # Logger seviyesi
trade_handler = RotatingFileHandler(
    'Log/trade.log',
    maxBytes=25 * 1024 * 1024,  # 25 MB
    backupCount=1              # 1 yedek dosya tut
)
trade_handler.setFormatter(formatter)
trade.addHandler(trade_handler)
trade.propagate = False

# İşlem Geçmişi Logger
islemgecmisi = logging.getLogger('islemgecmisi')
islemgecmisi.setLevel(logging.INFO)  # Logger seviyesi
islemgecmisi_handler = RotatingFileHandler(
    'Log/islem_gecmisi.log',
    maxBytes=25 * 1024 * 1024,  # 25 MB
    backupCount=1              # 1 yedek dosya tut
)
islemgecmisi_handler.setFormatter(formatter)
islemgecmisi.addHandler(islemgecmisi_handler)
islemgecmisi.propagate = False

# Hesaplama Sonuçları Logger
buy_result = logging.getLogger('buy_result')
buy_result.setLevel(logging.INFO)  # Logger seviyesi
buy_result_handler = RotatingFileHandler(
    'Log/buy_result.log',
    maxBytes=25 * 1024 * 1024,  # 25 MB
    backupCount=1              # 1 yedek dosya tut
)
buy_result_handler.setFormatter(formatter)
buy_result.addHandler(buy_result_handler)
buy_result.propagate = False

class Trade:
    def __init__(self):
        env_files = glob(".env*")
        if env_files:
            # İlk bulunan dosyayı seç
            selected_env_file = env_files[0]
            # Seçilen dosyayı yükle
            load_dotenv(selected_env_file)
        else:
            print(".env ile başlayan bir dosya bulunamadı.")
        self.binance = Binance()
        self.araclar = Araclar()
        self.islem_acik = False  # İşlem durumu
        self.alinan_coin = None  # Alınan coin
        self.alim_fiyati = None  # Alım fiyatı
        self.adet = None  # Adet bilgisi
        self.gercek = False  # Gerçek işlem mi?
        self.global_lock = threading.Lock()  # Paralel işlemleri kontrol için global kilit
        self.nakit = None
        self.sell_strategy=None
        self.mum_sayisi=0
        self.strategys = Araclar.get_strategys()
        self.highest_price = None
        self.destek=None
        self.direnc=None
        self.mail_gonder=os.getenv('MAIL_GONDER')
        self.telegram_mesaj_gonder=os.getenv('TELEGRAM_MESAJ_GONDER')
        self.buy_ma_control = os.getenv('BUY_MA_CONTROL')
        self.buy_bb_control = os.getenv('BUY_BB_CONTROL')
        self.durum_list=[]
    def kaydet(self):
        durum = {
            'islem_acik': self.islem_acik,
            'alinan_coin': self.alinan_coin,
            'alim_fiyati': self.alim_fiyati,
            'adet': self.adet,
            'nakit': self.nakit,
            'sell_strategy': self.sell_strategy.__name__ if self.sell_strategy else None,
            'periyot': self.periyot,
            'mum_sayisi':self.mum_sayisi,
            'highest_price':self.highest_price,
            'destek':self.destek,
            'direnc':self.direnc,
            'durum_list':self.durum_list
        }
        with open(f'Trade_Durumu/trade_durumu_{self.periyot}.json', 'w') as f:
            json.dump(durum, f)
    def yukle(self):
        if os.path.exists(f'Trade_Durumu/trade_durumu_{self.periyot}.json'):
            with open(f'Trade_Durumu/trade_durumu_{self.periyot}.json', 'r') as f:
                durum = json.load(f)
                self.islem_acik = durum['islem_acik']
                self.alinan_coin = durum['alinan_coin']
                self.alim_fiyati = durum['alim_fiyati']
                self.adet = durum['adet']
                self.nakit = durum['nakit']
                self.sell_strategy = getattr(Stratejiler, durum['sell_strategy']) if durum['sell_strategy'] else None
                self.periyot = durum['periyot']
                self.mum_sayisi = durum['mum_sayisi']
                self.highest_price = durum['highest_price']
                self.destek = durum['destek']
                self.direnc = durum['direnc']
                self.durum_list = durum['durum_list']
    def TradeEt(self, periyot, gercek,nakit,temp_trade=False):
        self.gercek = gercek  # Gerçek işlem bilgisi kaydedildi
        self.nakit=nakit
        self.periyot=periyot
        if not temp_trade:
            self.yukle()
        trade.info(f"Trade {periyot} Calisiyor ... {gercek}")
        print(f"Trade {periyot} Calisiyor ... {gercek}", time.ctime())
        coinlist=self.binance.coin_list()
        self.araclar.mum_olusmasini_bekle(periyot)

        with ThreadPoolExecutor(max_workers=len(coinlist)) as executor:
            while True:
                # Eğer bir işlem zaten açılmışsa, satış sinyali bekle
                if self.islem_acik:
                    self.satis_sinyali_bekle(periyot,temp_trade)
                    if os.path.exists(f"Trade_Durumu/bitir_{periyot}"):
                        if self.mail_gonder=="True":
                            self.araclar.mail_gonder(f"Trade {periyot} durduruldu","Son işlem kapatıldı ve trade durduruldu")
                        if self.telegram_mesaj_gonder=="True":
                            self.araclar.telegram_mesaj_gonder(f"❌ Trade {periyot} son işlem kapatıldı ve trade durduruldu")
                        exit(0)
                else:
                    coinlist = self.binance.coin_list()
                    self.strategys = self.araclar.get_strategys()
                    if len(self.strategys[periyot])>0:
                        # Sahip olunan coinleri hariç tutarak işlem yapılacak coin listesini güncelle
                        coinlist = self.araclar.listeden_sahip_olduklarimi_cikar(coinlist)
                        future_to_coin = {
                            executor.submit(self.alim_sinyali_kontrol, coin, periyot, self.strategys, self.nakit,
                                            temp_trade): coin
                            for coin in coinlist}
                        for future in as_completed(future_to_coin):
                            try:
                                result = future.result()
                                if result:  # Eğer bir işlem açılmışsa, döngüden çık
                                    break
                            except Exception as e:
                                hata = traceback.format_exc()
                                trade.error(f"Bir hata olustu: {hata}")
                                if self.mail_gonder == "True":
                                    self.araclar.mail_gonder(f"HATA | Trade {periyot}", f"{hata}")
                                if self.telegram_mesaj_gonder == "True":
                                    self.araclar.telegram_mesaj_gonder(f"❗ HATA | Trade {periyot} \n {e}")
                                time.sleep(5)
                    
                # Mum oluşmasını bekler
                if not self.islem_acik:
                    time.sleep(10)
                    self.araclar.mum_olusmasini_bekle(periyot)
    def alim_sinyali_kontrol(self, coin, periyot, strategys,nakit,temp_trade=False):
        limit=5
        while True:
            try:
                data = self.binance.get_coin_data(coin, periyot, 1000)
                high = data['high']
                low = data['low']
                close = data['close']
                open = data['open']
                vol = data['volume_usdt']
            except Exception as e:
                trade.error(f"Veri ithalinde hata oluştu: {e} \n [{periyot}] [{coin}]")
                continue

            if self.araclar.mum_sagligi(open=open[-50:], close=close[-50:]) > 5:
                return False

            for strategy in strategys[periyot]:
                with self.global_lock:  # Global kilit kullanarak sadece bir strateji kontrol et
                    if strategy.__name__ == "Alpha_Trend":
                        strategy_result = strategy(high, low, close, vol)
                    else:
                        strategy_result = strategy(high, low, close)
                    succes = False
                    while not succes:
                        try:
                            ema_50 = Indikator.EMA(close,50)
                            bb_down,bb_mid,bb_up = Indikator.BB(close)
                            son_sell_index = 0
                            for i in range(len(strategy_result) - 1, -1, -1):
                                if strategy_result[i] == 'SELL':
                                    son_sell_index = i
                                    break
                            destek,direnc,signal=Stratejiler.destek_stop_lose(close[-1],None,None,close,low)
                            buy_control = (strategy_result[-2] == "BUY") and ("BUY" not in strategy_result[son_sell_index:-2])
                            direnc_control = (direnc is not None)
                            ema_control = (ema_50[-1] is not None and close[-1] > ema_50[-1]) or self.buy_ma_control=="False"
                            bb_control = (bb_mid[-1] is not None and close[-1]<bb_mid[-1]) or self.buy_bb_control=="False"
                            buy_result.info(f"{periyot} {strategy.__name__} {coin} {buy_control} {direnc_control} {ema_control} {bb_control}")
                            if (not self.islem_acik) and buy_control and direnc_control and ema_control and bb_control:
                                strateji_adi = str(strategy.__name__)
                                self.adet = self.buy(coin, periyot, strateji_adi, close, nakit)
                                self.alinan_coin = coin  # Alınan coin'i kaydet
                                self.alim_fiyati = close[-1]  # Alım fiyatını kaydet
                                self.islem_acik = True  # İşlem açıldı
                                self.sell_strategy = strategy  # Kullanılan strateji
                                if not temp_trade:
                                    self.kaydet()
                                trade.info(f"AL | {coin} alındı, Adet: {self.adet}, Fiyat: {close[-1]}")
                                islemgecmisi.info(
                                    f"{strateji_adi} {periyot} AL | {coin} alındı, Adet: {self.adet}, Fiyat: {close[-1]}")
                                print(f"{strateji_adi} {periyot} AL | {coin} alındı, Adet: {self.adet}, Fiyat: {close[-1]}")
                                if self.mail_gonder=="True":
                                    self.araclar.mail_gonder(f"AL | {strateji_adi} {periyot}",f"{coin} alındı, Adet: {self.adet}, Maliyet: {close[-1]} USDT")
                                if self.telegram_mesaj_gonder=="True":
                                    self.araclar.telegram_mesaj_gonder(f"🟢 AL | {strateji_adi} {periyot}\n{coin} alındı, Adet: {self.adet}, Maliyet: {close[-1]} USDT")
                                return True  # İşlem açıldı, döngüden çık
                            succes = True
                        except Exception as e:
                            trade.error(f"Alim sinyali kontrolünde hata oluştu: {e} \n [{strategy.__name__}] [{periyot}] [{coin}]")
                            time.sleep(2)
                            if limit==0:
                                trade.error(
                                    f"Alim sinyali kontrolünde hata oluştu: Deneme limiti asildi cikis yapiliyot {e} \n [{strategy.__name__}] [{periyot}] [{coin}]")
                                return False
                            else:
                                limit=limit-1

            return False  # İşlem açılmadı
    def satis_sinyali_bekle(self, periyot,temp_trade=False):
        env_files = glob(".env*")
        if env_files:
            # İlk bulunan dosyayı seç
            selected_env_file = env_files[0]
            # Seçilen dosyayı yükle
            load_dotenv(selected_env_file)
        else:
            print(".env ile başlayan bir dosya bulunamadı.")
        dinamik_stop_lose=os.getenv('DINAMIK_STOP_LOSE')=="True"
        static_stop_lose=os.getenv('STATIC_STOP_LOSE')=="True"
        destek_stop_lose=os.getenv('DESTEK_STOP_LOSE')=="True"
        take_profit=os.getenv('TAKE_PROFIT')=="True"
        stop_seviyesi=-1
        ortalama=0
        basamak_sayisi=self.araclar.ondalik_basamak_sayisi(self.alim_fiyati)
        self.araclar.mum_olusmasini_bekle(periyot)
        while self.islem_acik:
            # Veri ithali
            try:
                data = self.binance.get_coin_data(self.alinan_coin, periyot, 1000)
                high = data['high']
                low = data['low']
                close = data['close']
                vol = data['volume_usdt']
            except Exception as e:
                trade.error(
                    f"Veri ithali sırasında hata: {e} \n [{periyot}] [{self.alinan_coin}] [{self.sell_strategy.__name__}]")
                time.sleep(5)
                hata = traceback.format_exc()
                if self.mail_gonder=="True":
                    self.araclar.mail_gonder(f"HATA | Trade {periyot}", f"{hata}")
                if self.telegram_mesaj_gonder=="True":
                    self.araclar.telegram_mesaj_gonder(f"❗ HATA | Trade {periyot} \n {e}")
                continue

            # Hesaplamalar
            try:
                # Strategy
                if self.sell_strategy.__name__ == "Alpha_Trend":
                    sell_strategy_result = self.sell_strategy(high, low, close,vol)[-2]
                else:
                    sell_strategy_result = self.sell_strategy(high, low, close)[-2]

                # Stop-Lose
                if destek_stop_lose:
                    self.destek, self.direnc, destek_stop_lose_check = Stratejiler.destek_stop_lose(self.alim_fiyati, self.destek, self.direnc, close, low)
                    if self.direnc is None:
                        dinamik_stop_lose = True
                if dinamik_stop_lose:
                    dinamik_stop_lose_check, self.highest_price, stop_seviyesi = Stratejiler.dinamik_stop_lose(high, low, close, self.highest_price)
                if static_stop_lose:
                    static_stop_lose_check = Stratejiler.static_stop_lose(close, self.alim_fiyati)

                # Take-profit
                kar_zarar = ((close[-1] / self.alim_fiyati) - 1) * 100
                if take_profit:
                    if kar_zarar > 5:
                        self.durum_list.append(kar_zarar)
                    ortalama, take_profit_signal = Stratejiler.take_profit(self.durum_list)

                # Data
                mevcut_adedim = self.binance.mevcut_adedim(self.alinan_coin)
                minqty = self.binance.get_coin_minQTY(self.alinan_coin)
            except Exception as e:
                trade.error(
                    f"Satış hesaplama sırasında hata: {e} \n [{periyot}] [{self.alinan_coin}] [{self.sell_strategy.__name__}]")
                time.sleep(5)
                hata = traceback.format_exc()
                if self.mail_gonder=="True":
                    self.araclar.mail_gonder(f"HATA | Trade {periyot}", f"{hata}")
                if self.telegram_mesaj_gonder=="True":
                    self.araclar.telegram_mesaj_gonder(f"❗ HATA | Trade {periyot} \n {e}")
                continue

            # İşlemler
            if self.gercek and mevcut_adedim <= minqty:
                self.manul_sell(self.alinan_coin, periyot, close, str(self.sell_strategy.__name__), self.alim_fiyati)
                self.islem_acik = False
                self.alinan_coin = None
                self.alim_fiyati = None
                self.direnc = None
                self.destek = None
                self.highest_price = None
                self.mum_sayisi = 0
                self.durum_list = []
                if not temp_trade:
                    self.kaydet()
                break  # Satış yapıldı, döngüden çık
            elif sell_strategy_result == "SELL":
                try:
                    self.sell(self.alinan_coin, periyot, close, str(self.sell_strategy.__name__), self.alim_fiyati)
                    self.islem_acik = False
                    self.alinan_coin = None
                    self.alim_fiyati = None
                    self.direnc=None
                    self.destek=None
                    self.highest_price=None
                    self.mum_sayisi = 0
                    self.durum_list = []
                    if not temp_trade:
                        self.kaydet()
                    break  # Satış yapıldı, döngüden çık
                except Exception as e:
                    trade.error(
                        f"Hedef Satış işleminde hata: {e} \n [{periyot}] [{self.alinan_coin}] [{self.sell_strategy.__name__}]")
                    time.sleep(5)
                    hata = traceback.format_exc()
                    if self.mail_gonder=="True":
                        self.araclar.mail_gonder(f"HATA | Trade {periyot}", f"{hata}")
                    if self.telegram_mesaj_gonder=="True":
                        self.araclar.telegram_mesaj_gonder(f"❗ HATA | Trade {periyot} \n {e}")
                    continue
            elif (static_stop_lose and  static_stop_lose_check == "STOP-LOSE") or (dinamik_stop_lose and dinamik_stop_lose_check == "STOP-LOSE") or (destek_stop_lose and destek_stop_lose_check == "STOP-LOSE"):
                try:
                    self.stop_lose(self.alinan_coin, periyot, close, str(self.sell_strategy.__name__), self.alim_fiyati)
                    self.islem_acik = False
                    self.alinan_coin = None
                    self.alim_fiyati = None
                    self.destek = None
                    self.direnc = None
                    self.highest_price = None
                    self.mum_sayisi = 0
                    self.durum_list = []
                    if not temp_trade:
                        self.kaydet()
                    break  # Satış yapıldı, döngüden çık
                except Exception as e:
                    trade.error(f"STOP-LOSE işleminde hata: {e} \n [{periyot}] [{self.alinan_coin}]")
                    time.sleep(5)
                    hata = traceback.format_exc()
                    if self.mail_gonder=="True":
                        self.araclar.mail_gonder(f"HATA | Trade {periyot}", f"{hata}")
                    if self.telegram_mesaj_gonder=="True":
                        self.araclar.telegram_mesaj_gonder(f"❗ HATA | Trade {periyot} \n {e}")
                    continue
            elif take_profit and take_profit_signal == "TAKE-PROFIT":
                try:
                    self.take_profit_sell(self.alinan_coin, periyot, close, str(self.sell_strategy.__name__), self.alim_fiyati)
                    self.islem_acik = False
                    self.alinan_coin = None
                    self.alim_fiyati = None
                    self.destek = None
                    self.direnc = None
                    self.highest_price = None
                    self.mum_sayisi = 0
                    self.durum_list=[]
                    if not temp_trade:
                        self.kaydet()
                    break  # Satış yapıldı, döngüden çık
                except Exception as e:
                    trade.error(f"TAKE-PROFIT işleminde hata: {e} \n [{periyot}] [{self.alinan_coin}]")
                    time.sleep(5)
                    hata = traceback.format_exc()
                    if self.mail_gonder=="True":
                        self.araclar.mail_gonder(f"HATA | Trade {periyot}", f"{hata}")
                    if self.telegram_mesaj_gonder=="True":
                        self.araclar.telegram_mesaj_gonder(f"❗ HATA | Trade {periyot} \n {e}")
                    continue

            self.mum_sayisi = self.mum_sayisi + 1
            if not temp_trade:
                self.kaydet()
            other_strategy = self.strategys[periyot].copy()
            other_strategy.remove(self.sell_strategy)
            other_strategy_result = []
            try:
                for strategy in other_strategy:
                    if strategy.__name__ == "Alpha_Trend":
                        result = strategy(high[:-1], low[:-1], close[:-1], vol[:-1])[-1]
                    else:
                        result = strategy(high[:-1], low[:-1], close[:-1])[-1]
                    if result == "BUY":
                        other_strategy_result.append(1)
                    elif result == "SELL":
                        other_strategy_result.append(-1)
                    else:
                        other_strategy_result.append(0)
            except Exception as e:
                trade.error(f"Diger stratejilerin sonuclarini hesaplamada hata : {e} ")
                time.sleep(5)
                hata = traceback.format_exc()
                if self.mail_gonder=="True":
                    self.araclar.mail_gonder(f"HATA | Trade {periyot}", f"{hata}")
                if self.telegram_mesaj_gonder=="True":
                    self.araclar.telegram_mesaj_gonder(f"❗ HATA | Trade {periyot} \n {e}")
                continue

            stop_seviyesi=round(stop_seviyesi,basamak_sayisi)
            yuvarlanmis_destek=round(self.destek,basamak_sayisi)
            trade.info(
                f"DURUM : {periyot} {self.sell_strategy.__name__} {self.alinan_coin} Islem Suresi: {self.mum_sayisi} mum. Diger strategyler {other_strategy_result} Stop-Lose: {stop_seviyesi}|{yuvarlanmis_destek}. Durum Ortalamasi: {ortalama:.2f} Kar/Zarar: {kar_zarar:.2f}%")
            if self.telegram_mesaj_gonder=="True":
                self.araclar.telegram_mesaj_gonder(f"🔵 DURUM : {periyot} {self.sell_strategy.__name__} {self.alinan_coin} Islem Suresi: {self.mum_sayisi} mum. Diger strategyler {other_strategy_result} Stop-Lose: {stop_seviyesi}|{yuvarlanmis_destek}. Durum Ortalamasi: {ortalama:.2f} Kar/Zarar: {kar_zarar:.2f}%")
            time.sleep(10)
            self.araclar.mum_olusmasini_bekle(periyot)
    def buy(self, coin, periyot, strateji_adi, close,nakit):
        # Adet hesapla
        minQty = self.binance.get_coin_minQTY(coin)
        adet = nakit / close[-1]
        adet = self.binance.miktar_duzelt(adet,minQty)
        if self.gercek:
            if nakit > 10:
                self.binance.al(coin, adet)
                self.nakit = round(self.nakit-(adet * close[-1]),2)
            else:
                print("Yeterli miktarda nakit yok !")
                if self.mail_gonder=="True":
                    self.araclar.mail_gonder(f"AL(!) | {strateji_adi} {periyot} ",f"Yeterli miktarda nakit yok. Mevcut nakit : {nakit}")
                if self.telegram_mesaj_gonder=="True":
                    self.araclar.telegram_mesaj_gonder(f"❗ AL(!) | Trade {strateji_adi} {periyot} Yeterli miktarda nakit yok. Mevcut nakit :  {nakit}")

        return adet
    def sell(self, coin, periyot, close, strateji_adi, buy_price):
        kar_zarar = ((close[-1] / buy_price) - 1) * 100
        self.mum_sayisi = self.mum_sayisi + 1
        trade.info(f"SAT {strateji_adi} {periyot}| {coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]}")
        islemgecmisi.info(
            f"{strateji_adi} {periyot} SAT | {coin} satıldı, Mum sayisi : {self.mum_sayisi} Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar: {kar_zarar:.2f}%"
        )
        print(
            f"{strateji_adi} {periyot} SAT | {coin} satıldı, Mum sayisi : {self.mum_sayisi} Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar: {kar_zarar:.2f}%"
        )

        if self.gercek:
            mevcut_adedim = self.binance.sahip_olduklarim()[coin]
            minQty = self.binance.get_coin_minQTY(coin)
            adet = self.binance.miktar_duzelt(mevcut_adedim,minQty)
            self.nakit = round(self.nakit + ((close[-1] * adet)*0.999),2)
            self.binance.sat(coin, adet)
        if self.mail_gonder=="True":
            self.araclar.mail_gonder(f"SAT | {strateji_adi} {periyot}",f"{coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar:{((close[-1] / buy_price) - 1) * 100:.2f}%")
        if self.telegram_mesaj_gonder=="True":
            self.araclar.telegram_mesaj_gonder(f"🔴 SAT | {strateji_adi} {periyot} \n{coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar:{((close[-1] / buy_price) - 1) * 100:.2f}%")
        return "SAT"
    def stop_lose(self, coin, periyot, close, strateji_adi, buy_price):
        kar_zarar = ((close[-1] / buy_price) - 1) * 100
        self.mum_sayisi = self.mum_sayisi + 1
        trade.info(f"SAT [STOP-LOSE] {strateji_adi} {periyot}| {coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]}")
        islemgecmisi.info(
            f"{strateji_adi} {periyot} SAT [STOP-LOSE] | {coin} satıldı, Mum sayisi : {self.mum_sayisi} Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar: {kar_zarar:.2f}%"
        )
        print(
            f"{strateji_adi} {periyot} SAT [STOP-LOSE] | {coin} satıldı, Mum sayisi : {self.mum_sayisi} Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar: {kar_zarar:.2f}%"
        )

        if self.gercek:
            mevcut_adedim = self.binance.sahip_olduklarim()[coin]
            minQty = self.binance.get_coin_minQTY(coin)
            adet = self.binance.miktar_duzelt(mevcut_adedim,minQty)
            self.nakit = round(self.nakit + ((close[-1] * adet) * 0.999),2)
            self.binance.sat(coin, adet)
        if self.mail_gonder=="True":
            self.araclar.mail_gonder(f"SAT [STOP-LOSE] | {strateji_adi} {periyot}",f"{coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar:{((close[-1] / buy_price) - 1) * 100:.2f}%")
        if self.telegram_mesaj_gonder=="True":
            self.araclar.telegram_mesaj_gonder(f"🛑 SAT [STOP-LOSE] | {strateji_adi} {periyot} \n{coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar:{((close[-1] / buy_price) - 1) * 100:.2f}%")
        return "SAT"
    def manul_sell(self, coin, periyot, close, strateji_adi, buy_price):
        kar_zarar = ((close[-1] / buy_price) - 1) * 100
        self.mum_sayisi = self.mum_sayisi + 1
        trade.info(f"SAT [MANUEL] {strateji_adi} {periyot}| {coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]}")
        islemgecmisi.info(
            f"{strateji_adi} {periyot} SAT [MANUEL] | {coin} satıldı, Mum sayisi : {self.mum_sayisi} Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar: {kar_zarar:.2f}%"
        )
        print(
            f"{strateji_adi} {periyot} SAT [MANUEL] | {coin} satıldı, Mum sayisi : {self.mum_sayisi} Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar: {kar_zarar:.2f}%"
        )

        if self.mail_gonder == "True":
            self.araclar.mail_gonder(f"SAT [MANUEL] | {strateji_adi} {periyot}",
                                     f"{coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar:{((close[-1] / buy_price) - 1) * 100:.2f}%")
        if self.telegram_mesaj_gonder == "True":
            self.araclar.telegram_mesaj_gonder(
                f"🛑 SAT [MANUEL] | {strateji_adi} {periyot} \n{coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar:{((close[-1] / buy_price) - 1) * 100:.2f}%")

        return "SAT"
    def take_profit_sell(self,coin, periyot, close, strateji_adi, buy_price):
        kar_zarar = ((close[-1] / buy_price) - 1) * 100
        self.mum_sayisi = self.mum_sayisi + 1
        trade.info(f"SAT [TAKE-PROFIT] {strateji_adi} {periyot}| {coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]}")
        islemgecmisi.info(
            f"{strateji_adi} {periyot} SAT [TAKE-PROFIT] | {coin} satıldı, Mum sayisi : {self.mum_sayisi} Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar: {kar_zarar:.2f}%"
        )
        print(
            f"{strateji_adi} {periyot} SAT [TAKE-PROFIT] | {coin} satıldı, Mum sayisi : {self.mum_sayisi} Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar: {kar_zarar:.2f}%"
        )

        if self.gercek:
            mevcut_adedim = self.binance.sahip_olduklarim()[coin]
            minQty = self.binance.get_coin_minQTY(coin)
            adet = self.binance.miktar_duzelt(mevcut_adedim, minQty)
            self.nakit = round(self.nakit + ((close[-1] * adet) * 0.999), 2)
            self.binance.sat(coin, adet)
        if self.mail_gonder == "True":
            self.araclar.mail_gonder(f"SAT [TAKE-PROFIT] | {strateji_adi} {periyot}",f"{coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar:{((close[-1] / buy_price) - 1) * 100:.2f}%")
        if self.telegram_mesaj_gonder == "True":
            self.araclar.telegram_mesaj_gonder(f"✅ SAT [TAKE-PROFIT] | {strateji_adi} {periyot} \n{coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar:{((close[-1] / buy_price) - 1) * 100:.2f}%")
        return "SAT"
