from Binance import Binance
from Araclar import Araclar
from Stratejiler import Stratejiler
import time
import traceback
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
import logging
import os
from logging.handlers import RotatingFileHandler

if not os.path.exists('Log'):
    os.makedirs('Log')

# İşlem geçmişi için ayrı bir logger oluştur
tarama = logging.getLogger('tarama')
handler = RotatingFileHandler(
    'Log/tarama.log',
    maxBytes=25 * 1024 * 1024,  # 25 MB
    backupCount=1              # 1 yedek dosya tut
)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
tarama.addHandler(handler)
tarama.propagate = False

class Tarama:
    @staticmethod
    def Tara(coinlist, periyot, mum_bekle=True):
        binance = Binance()
        araclar = Araclar()

        print(f"Tarama {periyot} Calisiyor ...", time.ctime())
        tarama.info(f"Tarama {periyot} Calisiyor ...")

        while True:
            try:
                strategys = araclar.get_strategys()
                result = {strategy.__name__: {"BUY": [], "SELL": []} for strategy in strategys[periyot]}

                if mum_bekle:
                    araclar.mum_olusmasini_bekle(periyot)

                if len(strategys[periyot])>0:
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
                                tarama.error(f"{coin} {strategy_name} için işlem hatası: {e}")
                                print(f"{coin} {strategy_name} için işlem hatası: {e}")
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
                        tarama.info(f"{periyot} tarama mail gonderildi")
                mum_bekle = True
                time.sleep(10)
            except Exception:
                mum_bekle = False
                hata = traceback.format_exc()
                print(f"Bir hata olustu: {hata}, {time.ctime()}")
                tarama.error(f"Bir hata olustu: {hata}")
                time.sleep(5)
                araclar.mail_gonder("HATA | Tarama", f"{periyot} \n{hata}")
                continue

    @staticmethod
    def process_coin_data(binance, coin, periyot, strategies):
        """ Tekil bir coin için veriyi çekip stratejileri çalıştırır """
        try:
            data = binance.get_coin_data(coin, periyot, 1000)
            high = np.array(data['high'])
            low = np.array(data['low'])
            close = np.array(data['close'])
            vol=np.array(data['volume_usdt'])

            coin_results = {}
            for strategy in strategies:
                if strategy.__name__ == "Alpha_Trend":
                    strategy_result = strategy(high, low, close, vol)
                else:
                    strategy_result = strategy(high, low, close)

                if strategy_result[-1] == "BUY":
                    coin_results[strategy.__name__] = "BUY"
                elif strategy_result[-1] == "SELL":
                    coin_results[strategy.__name__] = "SELL"
            return coin_results
        except Exception as e:
            print(f"Veri işleme hatası ({coin}): {e}")
            tarama.error(f"Veri işleme hatası ({coin}): {e}")
            return {}

    @staticmethod
    def Piyasa_Durumu(coinlist):
        binance = Binance()
        strategys = Araclar.get_strategys()

        strategies_columns = {period: [strat.__name__ for strat in period_strategies] for period, period_strategies in
                              strategys.items()}
        result_table = pd.DataFrame(index=coinlist, columns=strategies_columns.keys())

        def calculate_strategy(coin, period, strategy, high, low, close,vol):
            if strategy.__name__ != "Alpha_Trend":
                strategy_results = strategy(high, low, close)
            else:
                strategy_results = strategy(high, low, close,vol)

            son_sell_index = 0
            for i in range(len(strategy_results) - 1, -1, -1):
                if strategy_results[i] == 'SELL':
                    son_sell_index = i
                    break
            son_buy_index = 0
            for i in range(len(strategy_results) - 1, -1, -1):
                if strategy_results[i] == 'BUY':
                    son_buy_index = i
                    break
            if (strategy_results[-2] == "BUY") and ("BUY" not in strategy_results[son_sell_index:-2]):
                result = "BUY"
            elif strategy_results[-2] == "SELL" and ("SELL" not in strategy_results[son_buy_index:-2]):
                result = "SELL"
            else:
                result = False
            return 1 if result == "BUY" else -1 if result == "SELL" else 0

        # Her period ve coin için stratejileri hesapla ve ortalama sonuçları döndür
        def process_coin_for_period(coin, period):
            data = binance.get_coin_data(coin, period, 1000)
            high = np.array(data['high'])
            low = np.array(data['low'])
            close = np.array(data['close'])
            vol = np.array(data['volume_coin'])
            if high is None or low is None or close is None:
                print(f"Veri çekiminde hata: Coin: {coin}, Periyot: {period}")
                return period, np.nan  # Hata durumunda NaN dön

            results = []
            for strategy in strategys[period]:
                result = calculate_strategy(coin, period, strategy, high, low, close,vol)
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