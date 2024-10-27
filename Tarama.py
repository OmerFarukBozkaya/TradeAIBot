from Binance import Binance
from Araclar import Araclar
from Stratejiler import Stratejiler
import time
import traceback
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import numpy as np
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

    @staticmethod
    def Piyasa_Durumu():
        binance = Binance()
        coins = binance.secili_list()

        # Periyoda göre stratejiler
        strategys = {
            "15m": [Stratejiler.BB_RSI, Stratejiler.BB_ADX, Stratejiler.BB_Close],
            "1h": [Stratejiler.BB_RSI, Stratejiler.TSO, Stratejiler.FDI, Stratejiler.BB_ADX, Stratejiler.BB_Close],
            "4h": [Stratejiler.DMO, Stratejiler.FDI, Stratejiler.VMZI],
            "1d": [Stratejiler.MACD, Stratejiler.DMO, Stratejiler.VAMA, Stratejiler.VMZI, Stratejiler.MA_Cross,
                   Stratejiler.FDI]
        }

        # Sütun isimlerini oluştur
        strategies_columns = {period: [strat.__name__ for strat in period_strategies] for period, period_strategies in
                              strategys.items()}

        # Sonuç tablosunu oluştur
        result_table = pd.DataFrame(index=coins, columns=strategies_columns.keys())

        # Tüm sütunları görmek için ayarları yapılandırın
        pd.set_option('display.max_columns', None)
        pd.set_option('display.expand_frame_repr', False)

        def calculate_strategy(coin, period, strategy, high, low, close):
            result = strategy(high, low, close)
            return 1 if result == "BUY" else -1 if result == "SELL" else 0

        # Sonuçları toplamak için bir sözlük
        results_count = {coin: {period: [] for period in strategys.keys()} for coin in coins}

        for period, period_strategies in strategys.items():
            with ThreadPoolExecutor() as executor:
                futures = []
                for coin in coins:
                    high = binance.data(coin, 1000, period, 2)
                    low = binance.data(coin, 1000, period, 3)
                    close = binance.data(coin, 1000, period, 4)

                    # Verileri kontrol et
                    if high is None or low is None or close is None:
                        print(f"Veri çekiminde hata: Coin: {coin}, Periyot: {period}")
                        continue  # Veri yoksa sonraki coin'e geç

                    for strategy in period_strategies:
                        future = executor.submit(calculate_strategy, coin, period, strategy, high, low, close)
                        futures.append((coin, period, future))

                for coin, period, future in futures:
                    try:
                        result = future.result()
                        results_count[coin][period].append(result)  # Sonucu listeye ekle
                    except Exception as e:
                        print(f"Hata oluştu: {e}")
                        results_count[coin][period].append(np.nan)  # Hata durumunda NaN olarak ekle

        # Ortalamaları hesapla ve tabloya yaz
        for coin in coins:
            for period in results_count[coin]:
                results = results_count[coin][period]
                if results:  # Eğer sonuçlar varsa
                    average = np.nanmean(results)  # NaN'leri atlayarak ortalama al
                    result_table.loc[coin, period] = round(average, 2)  # Ortalamayı iki ondalık basamakla yaz

        # Toplam ortalamayı hesaplamak için bir sütun ekleyin
        result_table['Toplam Ortalama'] = result_table.fillna(0).mean(axis=1).round(
            2)  # NaN'leri sıfırla doldur ve iki ondalık basamakla yuvarla

        return result_table