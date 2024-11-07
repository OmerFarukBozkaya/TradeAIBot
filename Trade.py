import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from Binance import Binance
from Araclar import Araclar
from Stratejiler import Stratejiler
import logging
import threading
import json
import os

# Log ayarları
logging.basicConfig(filename='trading_log.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# İşlem geçmişi için ayrı bir logger oluştur
islemgecmisi = logging.getLogger('islemgecmisi')
handler = logging.FileHandler('islem_gecmisi.log')
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
islemgecmisi.addHandler(handler)
islemgecmisi.propagate = False


class Trade:
    def __init__(self):
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

    def kaydet(self):
        durum = {
            'islem_acik': self.islem_acik,
            'alinan_coin': self.alinan_coin,
            'alim_fiyati': self.alim_fiyati,
            'adet': self.adet,
            'nakit': self.nakit,
            'sell_strategy': self.sell_strategy.__name__ if self.sell_strategy else None,
            'periyot': self.periyot,
            'mum_sayisi':self.mum_sayisi
        }
        with open(f'trade_durumu_{self.periyot}.json', 'w') as f:
            json.dump(durum, f)

    # Durumu yükleyen fonksiyon
    def yukle(self):
        if os.path.exists(f'trade_durumu_{self.periyot}.json'):
            with open(f'trade_durumu_{self.periyot}.json', 'r') as f:
                durum = json.load(f)
                self.islem_acik = durum['islem_acik']
                self.alinan_coin = durum['alinan_coin']
                self.alim_fiyati = durum['alim_fiyati']
                self.adet = durum['adet']
                self.nakit = durum['nakit']
                self.sell_strategy = getattr(Stratejiler, durum['sell_strategy']) if durum['sell_strategy'] else None
                self.periyot = durum['periyot']
                self.mum_sayisi = durum['mum_sayisi']
    def TradeEt(self, coinlist, periyot, gercek,nakit):
        self.gercek = gercek  # Gerçek işlem bilgisi kaydedildi
        self.nakit=nakit
        self.periyot=periyot
        self.yukle()
        strategys = {
            "15m": [Stratejiler.BB_RSI, Stratejiler.BB_ADX, Stratejiler.BB_Close],
            "1h": [Stratejiler.BB_RSI, Stratejiler.TSO, Stratejiler.FDI, Stratejiler.BB_ADX, Stratejiler.BB_Close],
            "4h": [Stratejiler.DMO, Stratejiler.FDI, Stratejiler.VMZI],
            "1d": [Stratejiler.MACD, Stratejiler.DMO, Stratejiler.VAMA, Stratejiler.VMZI, Stratejiler.MA_Cross,
                   Stratejiler.FDI]
        }
        logging.info(f"Trade {periyot} Calisiyor ... {gercek}")
        print(f"Trade {periyot} Calisiyor ... {gercek}", time.ctime())

        with ThreadPoolExecutor(max_workers=len(coinlist)) as executor:
            while True:
                # Mum oluşmasını bekler
                self.kaydet()
                self.araclar.mum_olusmasini_bekle(periyot)
                # Eğer bir işlem zaten açılmışsa, satış sinyali bekle
                if self.islem_acik:
                    self.satis_sinyali_bekle(periyot)
                else:
                    # Sahip olunan coinleri hariç tutarak işlem yapılacak coin listesini güncelle
                    coinlist = self.araclar.listeden_sahip_olduklarimi_cikar(coinlist)
                    future_to_coin = {executor.submit(self.alim_sinyali_kontrol, coin, periyot, strategys,self.nakit): coin
                                      for coin in coinlist}
                    for future in as_completed(future_to_coin):
                        try:
                            result = future.result()
                            if result:  # Eğer bir işlem açılmışsa, döngüden çık
                                break
                        except Exception:
                            hata = traceback.format_exc()
                            logging.error(f"Bir hata olustu: {hata}")
                            self.araclar.mail_gonder(f"HATA | Trade {periyot}", f"{hata}")
                            time.sleep(5)

    def alim_sinyali_kontrol(self, coin, periyot, strategys,nakit):
        try:
            data = self.binance.get_coin_data(coin, periyot, 1000)
            high = data['high']
            low = data['low']
            close = data['close']
            open = data['open']
            
            if self.araclar.mum_sagligi(open=open[-50:],close=close[-50:]) > 5:
                return False

            for strategy in strategys[periyot]:
                with self.global_lock:  # Global kilit kullanarak sadece bir strateji kontrol et
                    if not self.islem_acik and strategy(high, low, close) == "BUY":
                        sonislem, self.adet = self.buy(coin, periyot, str(strategy.__name__), close,nakit)
                        self.alinan_coin = coin  # Alınan coin'i kaydet
                        self.alim_fiyati = close[-1]  # Alım fiyatını kaydet
                        self.islem_acik = True  # İşlem açıldı
                        self.sell_strategy = strategy  # Kullanılan strateji
                        return True  # İşlem açıldı, döngüden çık
            return False  # İşlem açılmadı
        except Exception as e:
            logging.error(f"Alim sinyali kontrolünde hata oluştu: {e}")
            return False

    def satis_sinyali_bekle(self, periyot):
        try:
            while self.islem_acik:
                self.araclar.mum_olusmasini_bekle(periyot)
                self.mum_sayisi = self.mum_sayisi + 1
                self.kaydet()
                data = self.binance.get_coin_data(self.alinan_coin, periyot, 1000)
                high = data['high']
                low = data['low']
                close = data['close']
                logging.info(
                    f"DURUM : {periyot} {self.sell_strategy.__name__} {self.alinan_coin} Islem Suresi: {self.mum_sayisi} mum. Kar/Zarar: {((close[-1] / self.alim_fiyati) - 1) * 100:.2f}%")

                sell_strategy_sonuc = self.sell_strategy(high, low, close,self.alim_fiyati)
                if  sell_strategy_sonuc == "SELL" or (self.gercek and self.binance.mevcut_adedim(self.alinan_coin) == 0):
                    self.sell(self.alinan_coin, periyot, close, str(self.sell_strategy.__name__), self.alim_fiyati)
                    self.islem_acik = False
                    self.alinan_coin = None
                    self.alim_fiyati = None
                    self.mum_sayisi=0
                    self.kaydet()
                    break  # Satış yapıldı, döngüden çık
                elif sell_strategy_sonuc == "STOP-LOSE":
                    self.stop_lose(self.alinan_coin, periyot, close, str(self.sell_strategy.__name__), self.alim_fiyati)
                    self.islem_acik = False
                    self.alinan_coin = None
                    self.alim_fiyati = None
                    self.mum_sayisi = 0
                    self.kaydet()
                    break  # Satış yapıldı, döngüden çık
                time.sleep(10)
        except Exception as e:
            hata = traceback.format_exc()
            logging.error(f"Satış sinyali bekleme sırasında hata: {hata}")
            self.araclar.mail_gonder(f"HATA | Trade {periyot}", f"{hata}")

    def buy(self, coin, periyot, strateji_adi, close,nakit):
        # Adet hesapla
        adet = round((nakit / close[-1]), self.binance.minimum_hareket(
            float(self.binance.client.get_symbol_info(coin)["filters"][1]["minQty"])))
        if self.gercek:
            if nakit > 10:
                print("Gerçekten alındı")
                self.binance.al(coin, adet)
                self.nakit = 0
            else:
                print("Yeterli miktarda nakit yok !")

        logging.info(f"AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
        islemgecmisi.info(f"{strateji_adi} {periyot} AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
        print(f"{strateji_adi} {periyot} AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")

        self.araclar.mail_gonder(f"AL | {strateji_adi} {periyot}",
                                 f"{coin} alındı, Adet: {adet}, Maliyet: {close[-1]} USDT")
        return "AL", adet

    def sell(self, coin, periyot, close, strateji_adi, buy_price):
        kar_zarar = ((close[-1] / buy_price) - 1) * 100
        logging.info(f"SAT {strateji_adi} {periyot}| {coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]}")
        islemgecmisi.info(
            f"{strateji_adi} {periyot} SAT | {coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]:.2f} Kar/Zarar: {kar_zarar:.2f}%"
        )
        print(
            f"{strateji_adi} {periyot} SAT | {coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]:.2f} Kar/Zarar: {kar_zarar:.2f}%"
        )

        if self.gercek:
            print("Gerçekten satıldı")
            mevcut_adedim = self.binance.sahip_olduklarim()[coin]
            adet = round(mevcut_adedim - (mevcut_adedim % float(self.binance.minimum_hareket(float(self.binance.client.get_symbol_info(coin)["filters"][1]["minQty"])))))
            self.nakit = (close[-1] * adet)*0.999
            self.binance.sat(coin, adet)
        self.araclar.mail_gonder(f"SAT | {strateji_adi} {periyot}",
                                     f"{coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar:{((close[-1] / buy_price) - 1) * 100:.2f}%")
        return "SAT"

    def stop_lose(self, coin, periyot, close, strateji_adi, buy_price):
        kar_zarar = ((close[-1] / buy_price) - 1) * 100
        logging.info(f"SAT [STOP-LOSE] {strateji_adi} {periyot}| {coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]}")
        islemgecmisi.info(
            f"{strateji_adi} {periyot} SAT [STOP-LOSE] | {coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]:.2f} Kar/Zarar: {kar_zarar:.2f}%"
        )
        print(
            f"{strateji_adi} {periyot} SAT [STOP-LOSE] | {coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]:.2f} Kar/Zarar: {kar_zarar:.2f}%"
        )

        if self.gercek:
            print("Gerçekten satıldı")
            mevcut_adedim = self.binance.sahip_olduklarim()[coin]
            adet = round(mevcut_adedim - (mevcut_adedim % float(self.binance.minimum_hareket(
                float(self.binance.client.get_symbol_info(coin)["filters"][1]["minQty"])))))
            self.nakit = (close[-1] * adet) * 0.999
            self.binance.sat(coin, adet)
        self.araclar.mail_gonder(f"SAT [STOP-LOSE] | {strateji_adi} {periyot}",
                                 f"{coin} satıldı, Adet: {self.adet}, Fiyat: {close[-1]} Kar/Zarar:{((close[-1] / buy_price) - 1) * 100:.2f}%")
        return "SAT"
