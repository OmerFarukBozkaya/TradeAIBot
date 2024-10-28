import time
import traceback
from Binance import Binance
from Araclar import Araclar
from Stratejiler import Stratejiler
import logging

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
    def TradeEt(self,coinlist,periyot,sonislem,gercek,nakit,sell_strategy=None):
        temp=coinlist
        cik=False
        buy_price=None
        adet=None
        mum_bekle=True
        strategys={"15m":[Stratejiler.BB_RSI,Stratejiler.BB_ADX,Stratejiler.BB_Close],
                   "1h":[Stratejiler.BB_RSI,Stratejiler.TSO,Stratejiler.FDI,Stratejiler.BB_ADX,Stratejiler.BB_Close],
                   "4h":[Stratejiler.DMO,Stratejiler.FDI,Stratejiler.VMZI],
                   "1d":[Stratejiler.MACD,Stratejiler.DMO,Stratejiler.VAMA,Stratejiler.VMZI,Stratejiler.MA_Cross,Stratejiler.FDI]
                   }
        logging.info(f"Trade {periyot} Calisiyor ... {gercek}")
        print(f"Trade {periyot} Calisiyor ... {gercek}", time.ctime())
        while True:
            try:
                if mum_bekle:
                    Araclar.mum_olusmasini_bekle(periyot)
                if sonislem == "SAT":
                    coinlist=self.araclar.listeden_sahip_olduklarimi_cikar(coinlist)
                for coin in coinlist:
                    close = self.binance.data(coin, 1000, periyot, 4)
                    low = self.binance.data(coin, 1000, periyot, 3)
                    high = self.binance.data(coin, 1000, periyot, 2)
                    if sonislem == "SAT":
                        for strategy in strategys[periyot]:
                            if strategy(high, low, close) == "BUY":
                                sell_strategy = strategy
                                sonislem, adet = self.buy(coin, periyot, str(strategy.__name__), gercek, nakit, close)
                                coinlist = [coin]
                                buy_price=close[-1]
                                cik = True
                                break
                    if cik:
                        cik = False
                        break
                    elif sonislem == "AL":
                        logging.info(f"DURUM : {periyot} {sell_strategy.__name__} Kar/Zarar: {((close[-1]/buy_price)-1)*100:.2f}%")
                        if sell_strategy(high, low, close) == "SELL":
                            sonislem = self.sell(coin, adet, periyot, close, str(sell_strategy.__name__), gercek,buy_price)
                            coinlist = temp
                mum_bekle=True
                time.sleep(10)
            except Exception:
                mum_bekle=False
                hata = traceback.format_exc()
                logging.error(f"Bir hata olustu: {hata}")
                self.araclar.mail_gonder(f"HATA | Trade {periyot}",f"{strategy.__name__} {coin} {periyot} \n {hata}")
                time.sleep(5)  # Küçük bir gecikme sonrası tekrar dene
                logging.info(f"Trade {periyot} Calisiyor ... {gercek}")
                print(f"Trade {periyot} Calisiyor ... {gercek}", time.ctime())
                continue  # Döngüye tekrar gir

    def buy(self,coin,periyot,strateji_adi,gercek,nakit,close):
        adet = round((nakit / close[-1]), self.binance.minimum_hareket(
            float(self.binance.client.get_symbol_info(coin)["filters"][1]["minQty"])))
        logging.info(f"AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
        islemgecmisi.info(f"{strateji_adi} {periyot} AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
        print(f"{strateji_adi} {periyot} AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")

        if gercek:  # Gerçek işlem mi kontrol et
            print("Gercekten alindi")
            self.binance.al(coin, adet)

        self.araclar.mail_gonder(f"AL | {strateji_adi} {periyot}",
                            f"{coin} alindi, Adet: {adet}, Maliyet: {close[-1]} USDT")
        return "AL",adet
    def sell(self,coin,adet,periyot,close,strateji_adi,gercek,buy_price):
        adim = self.binance.minimum_hareket(float(self.binance.client.get_symbol_info(coin)["filters"][1]["minQty"]))
        logging.info(f"SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
        islemgecmisi.info(f"{strateji_adi} {periyot} SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]} Kar/Zarar:{((close[-1]/buy_price)-1)*100}%")
        print(f"{strateji_adi} {periyot} SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]} Kar/Zarar:{((close[-1]/buy_price)-1)*100}%")
        if gercek:
            print("Gercekten satildi")
            mevcut_adedim = self.binance.sahip_olduklarim()[coin]
            adet = round(mevcut_adedim - (mevcut_adedim % float(adim)), adim)
            self.binance.sat(coin, adet)
        self.araclar.mail_gonder(f"SAT | {strateji_adi} {periyot}", f"{coin} satildi, Adet: {adet}, Fiyat: {close[-1]} Kar/Zarar:{((close[-1]/buy_price)-1)*100}%")
        return "SAT"
