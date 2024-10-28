from Binance import Binance
from Araclar import Araclar
from Stratejiler import Stratejiler
import time
import traceback
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
class Tarama:
    @staticmethod
    def Tara(coinlist, periyot, mum_bekle=True):
        binance = Binance()
        araclar = Araclar()
        strategys = {
            "15m": [Stratejiler.BB_RSI, Stratejiler.BB_ADX, Stratejiler.BB_Close],
            "1h": [Stratejiler.BB_RSI, Stratejiler.TSO, Stratejiler.FDI, Stratejiler.BB_ADX, Stratejiler.BB_Close],
            "4h": [Stratejiler.DMO, Stratejiler.FDI, Stratejiler.VMZI],
            "1d": [Stratejiler.MACD, Stratejiler.DMO, Stratejiler.VAMA, Stratejiler.VMZI, Stratejiler.MA_Cross,
                   Stratejiler.FDI]
        }

        print(f"Tarama {periyot} Calisiyor ...", time.ctime())

        while True:
            try:
                result = {strategy.__name__: {"BUY": [], "SELL": []} for strategy in strategys[periyot]}

                if mum_bekle:
                    araclar.mum_olusmasini_bekle(periyot)

                # Coin verilerini paralel olarak çekme ve işleme
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future_to_coin = {
                        executor.submit(Tarama.process_coin_data, binance, coin, periyot, strategys[periyot]): coin
                        for coin in coinlist
                    }

                    # Sonuçları toplama
                    for future in concurrent.futures.as_completed(future_to_coin):
                        coin = future_to_coin[future]
                        try:
                            coin_results = future.result()
                            for strategy_name, signal in coin_results.items():
                                if signal == "BUY":
                                    result[strategy_name]["BUY"].append(coin)
                                elif signal == "SELL":
                                    result[strategy_name]["SELL"].append(coin)
                        except Exception as e:
                            print(f"{coin} için işlem hatası: {e}")
                            continue

                # E-posta gönderme
                mesaj, gonder = "", False
                for strategy in result.keys():
                    if result[strategy]["BUY"] or result[strategy]["SELL"]:
                        gonder = True
                        mesaj += (f"{strategy}\n"
                                  f"BUY:\n{result[strategy]['BUY']}\n"
                                  f"SELL:\n{result[strategy]['SELL']}\n\n")

                if gonder:
                    araclar.mail_gonder(f"Tarama | {periyot}", mesaj)

                mum_bekle = True
                time.sleep(10)
            except Exception:
                mum_bekle = False
                hata = traceback.format_exc()
                print(f"Bir hata olustu: {hata}, {time.ctime()}")
                time.sleep(5)
                araclar.mail_gonder("HATA | Tarama", f"{periyot} \n{hata}")
                continue

    @staticmethod
    def process_coin_data(binance, coin, periyot, strategies):
        """ Tekil bir coin için veriyi çekip stratejileri çalıştırır """
        try:
            close = np.array(binance.data(coin, 1000, periyot, 4))
            low = np.array(binance.data(coin, 1000, periyot, 3))
            high = np.array(binance.data(coin, 1000, periyot, 2))

            coin_results = {}
            for strategy in strategies:
                calculate = strategy(high, low, close)
                if calculate == "BUY" or calculate == "SELL":
                    coin_results[strategy.__name__] = calculate
            return coin_results
        except Exception as e:
            print(f"Veri işleme hatası ({coin}): {e}")
            return {}

    @staticmethod
    def Piyasa_Durumu(coinlist):
        binance = Binance()
        strategys = {
            "15m": [Stratejiler.BB_RSI, Stratejiler.BB_ADX, Stratejiler.BB_Close],
            "1h": [Stratejiler.BB_RSI, Stratejiler.TSO, Stratejiler.FDI, Stratejiler.BB_ADX, Stratejiler.BB_Close],
            "4h": [Stratejiler.DMO, Stratejiler.FDI, Stratejiler.VMZI],
            "1d": [Stratejiler.MACD, Stratejiler.DMO, Stratejiler.VAMA, Stratejiler.VMZI, Stratejiler.MA_Cross,
                   Stratejiler.FDI]
        }

        strategies_columns = {period: [strat.__name__ for strat in period_strategies] for period, period_strategies in
                              strategys.items()}
        result_table = pd.DataFrame(index=coinlist, columns=strategies_columns.keys())

        def calculate_strategy(coin, period, strategy, high, low, close):
            result = strategy(high, low, close)
            return 1 if result == "BUY" else -1 if result == "SELL" else 0

        # Her period ve coin için stratejileri hesapla ve ortalama sonuçları döndür
        def process_coin_for_period(coin, period):
            close = np.array(binance.data(coin, 1000, period, 4))
            low = np.array(binance.data(coin, 1000, period, 3))
            high = np.array(binance.data(coin, 1000, period, 2))
            if high is None or low is None or close is None:
                print(f"Veri çekiminde hata: Coin: {coin}, Periyot: {period}")
                return period, np.nan  # Hata durumunda NaN dön

            results = []
            for strategy in strategys[period]:
                result = calculate_strategy(coin, period, strategy, high, low, close)
                results.append(result)

            # Ortalama sonucu hesapla ve döndür
            return period, round(np.nanmean(results), 2)

        # Sonuçları toplamak için bir sözlük
        with ThreadPoolExecutor() as executor:
            for coin in coinlist:
                futures = {executor.submit(process_coin_for_period, coin, period): period for period in
                           strategys.keys()}
                coin_results = {}

                for future in futures:
                    period, result = future.result()
                    coin_results[period] = result

                # Sonuçları DataFrame'e kaydet
                for period, avg_result in coin_results.items():
                    result_table.loc[coin, period] = avg_result

        # Toplam ortalamayı hesapla ve tabloya ekle
        result_table['Toplam Ortalama'] = result_table.fillna(0).mean(axis=1).round(2)
        result_table.to_excel("Data/piyasa_durumu.xlsx")
        return result_table