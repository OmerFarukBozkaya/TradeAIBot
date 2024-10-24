from Binance import Binance
from Araclar import Araclar
from Stratejiler import Stratejiler
import time
import traceback
class Tarama:
    @staticmethod
    def Tara(coinlist,periyot):
        binance = Binance()
        araclar = Araclar()
        mum_bekle=True
        strategys = {"15m": [Stratejiler.BB_RSI, Stratejiler.BB_ADX, Stratejiler.BB_Close],
                     "1h": [Stratejiler.BB_RSI, Stratejiler.TSO, Stratejiler.FDI, Stratejiler.BB_ADX,Stratejiler.BB_Close],
                     "4h": [Stratejiler.DMO, Stratejiler.FDI, Stratejiler.VMZI],
                     "1d": [Stratejiler.MACD, Stratejiler.DMO, Stratejiler.VAMA, Stratejiler.VMZI, Stratejiler.MA_Cross,Stratejiler.FDI]}
        print(f"Tarama {periyot} Calisiyor ...", time.ctime())
        while True:
            try:
                result={}
                for strategy in strategys[periyot]:
                    result[strategy.__name__] = {}
                    result[strategy.__name__]["BUY"] = []
                    result[strategy.__name__]["SELL"] = []
                if mum_bekle:
                    araclar.mum_olusmasini_bekle(periyot)
                for coin in coinlist:
                    #   Veri ithali
                    close = binance.data(coin, 1000, periyot, 4)
                    low = binance.data(coin, 1000, periyot, 3)
                    high = binance.data(coin, 1000, periyot, 2)

                    for strategy in strategys[periyot]:
                        calculate = strategy(high,low,close)
                        if  calculate == None or calculate == False:
                            continue
                        elif calculate == "BUY":
                            result[strategy.__name__]["BUY"].append(coin)
                        elif calculate == "SELL":
                            result[strategy.__name__]["SELL"].append(coin)
                mesaj = ""
                gonder = False
                for strategy in result.keys():
                    if len(result[strategy]["BUY"]) > 0 or len(result[strategy]["SELL"]) > 0:
                        gonder = True
                        mesaj = (mesaj +
                                 f"{strategy}\n"
                                 f"BUY:\n"
                                 f"{result[strategy]['BUY']}\n"
                                 f"SELL:\n"
                                 f"{result[strategy]['SELL']}\n\n")
                if gonder:
                    araclar.mail_gonder(f"Tarama | {periyot}",mesaj)
                mum_bekle=True
                time.sleep(10)
            except Exception:
                mum_bekle=False
                hata = traceback.format_exc()
                print(f"Bir hata olustu: {hata}, {time.ctime()}")
                time.sleep(5)  # Küçük bir gecikme sonrası tekrar dene
                araclar.mail_gonder("HATA | Tarama",f"{strategy.__name__} {coin} {periyot} \n{hata}")
                print(f"Tarama {periyot} Calisiyor ...", time.ctime())
                continue  # Döngüye tekrar gir
