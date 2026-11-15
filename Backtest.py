import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from IndikatorTest import IndikatorTest
from StratejilerTest import StratejilerTest
from Binance import Binance
from datetime import datetime

class Backtest:
    @staticmethod
    def Hesapla(coin, periyot,stop=False,canli_veri=True,ema_check=False,bb_check=False,sar_check=False,adx_atr_check=False):
        dinamik_stop=False
        static_stop=False
        binance = Binance()
        # Veri ithali
        data = binance.get_coin_data(coin, periyot, 1000)
        if canli_veri :
            high = data['high']
            low = data['low']
            close = data['close']
            vol = data['volume_coin']
        else:
            close = open("Data/close-test.txt", "r").read().split(",")
            low = open("Data/low-test.txt", "r").read().split(",")
            high = open("Data/high-test.txt", "r").read().split(",")
            for i in range(len(close)):
                close[i] = float(close[i])
                low[i] = float(low[i])
                high[i] = float(high[i])
        # Strateji listesi

        strategies = [getattr(StratejilerTest, func) for func in dir(StratejilerTest)
                      if callable(getattr(StratejilerTest, func))
                      and not func.startswith("__")
                      and not getattr(StratejilerTest, func).__name__ in ["dinamik_stop_lose", "static_stop_lose",
                                                                          "destek_stop_lose","take_profit","Local_Min_Max","SMC_Strategy"]]

        # Excel'e yazılacak veriler için bir liste oluştur
        excel_data = []
        islem_gecmisi = []

        # Her strateji için hesaplamalar
        for strategy in strategies:
            last_signal = None
            buy_price = None
            cumulative_profit_loss = []
            total_profit_loss = 0
            profitable_trades = 0
            losing_trades = 0
            initial_capital = 100
            capital_history = [initial_capital]

            # Strateji sonucu hesaplama
            if strategy.__name__ not in ["Smart_MACD_Reversal",
                                         "Alpha_Trend", "E_A_S_Y"]:
                strategy_result, indicators = strategy(high, low, close)
            if strategy.__name__ in ["Smart_MACD_Reversal", "Alpha_Trend"]:
                strategy_result, indicators = strategy(high, low, close, vol)
            if strategy.__name__ in ["E_A_S_Y"]:
                ha_data = binance.heiken_ashi(data)
                ha_high = ha_data['high']
                ha_low = ha_data['low']
                ha_close = ha_data['close']
                strategy_result, indicators = strategy(ha_high, ha_low, ha_close)
            high_price = 0
            atr = IndikatorTest.ATR(high,low,close)
            adx = IndikatorTest.ADX(high,low,close)
            if ema_check:
                hlc3=Binance.hlc3(high, low, close)
                ema200 = IndikatorTest.EMA(hlc3, 200)
            if bb_check:
                bb_down,bb_mid,bb_top=IndikatorTest.BB(close)
            if sar_check:
                sar = IndikatorTest.ParabolicSAR(high, low)

            for i in range(len(close)):
                if last_signal is None or last_signal == 'red':  # Yeni pozisyon açma
                    if ema_check or bb_check:
                        if ema_check:
                            if ema200[i] is not None and close[i]>ema200[i]:
                                pass
                            else:
                                continue
                        if bb_check:
                            if bb_mid[i] is not None and close[i]<bb_mid[i]:
                                pass
                            else:
                                continue
                        if sar_check:
                            if sar[i] is not None and close[i]>sar[i]:
                                pass
                            else:
                                continue
                        if adx_atr_check:
                            if adx[i] is not None and atr[i] is not None and atr[i-1] is not None and 25>adx[i] and atr[i]>atr[i-1]:
                                pass
                            else:
                                continue
                        son_sell_index = 0
                        for j in range(len(strategy_result[:i+1]) - 1, -1, -1):
                            if strategy_result[:i+1][j] == 'SELL':
                                son_sell_index = j
                                break
                        buy_control = (strategy_result[i] == "BUY") and ("BUY" not in strategy_result[son_sell_index:i])
                        if buy_control:
                            islem_gecmisi.append(
                                f"{i}.mum {strategy.__name__} {periyot} {coin} fiyat : {close[i]} alindi.")
                            last_signal = 'green'
                            buy_price = close[i]
                    else:
                        son_sell_index = 0
                        for j in range(len(strategy_result[:i + 1]) - 1, -1, -1):
                            if strategy_result[:i + 1][j] == 'SELL':
                                son_sell_index = j
                                break
                        buy_control = (strategy_result[i] == "BUY") and ("BUY" not in strategy_result[son_sell_index:i])
                        if buy_control:
                            islem_gecmisi.append(
                                f"{i}.mum {strategy.__name__} {periyot} {coin} fiyat : {close[i]} alindi.")
                            last_signal = 'green'
                            buy_price = close[i]
                elif last_signal == 'green':  # Mevcut pozisyonu kapama
                    if stop:
                        if dinamik_stop:
                            dinamik_stop_signal,high_price,stop_level=StratejilerTest.dinamik_stop_lose(atr,adx,close,high_price)
                        if static_stop:
                            static_stop_signal = StratejilerTest.static_stop_lose(close,buy_price,i)
                    if strategy_result[i] == "SELL" or (stop and ((dinamik_stop and dinamik_stop_signal == "STOP-LOSE") or (static_stop and static_stop_signal == "STOP-LOSE"))):
                        kar_zarar = ((close[i] / buy_price) - 1) * 100
                        if strategy_result[i] == "SELL":
                            islem_gecmisi.append(f"{i}.mum {strategy.__name__} {periyot} {coin} fiyat : {close[i]} satildi [HEDEF]. Kar/Zarar: {kar_zarar} %")
                        elif static_stop_signal == "STOP-LOSE":
                            islem_gecmisi.append(f"{i}.mum {strategy.__name__} {periyot} {coin} fiyat : {close[i]} satildi [STOP-LOSE][STATIC]. Kar/Zarar: {kar_zarar} %")
                        else:
                            islem_gecmisi.append(f"{i}.mum {strategy.__name__} {periyot} {coin} fiyat : {close[i]} satildi [STOP-LOSE][DINAMIK]. Kar/Zarar: {kar_zarar} %")
                        last_signal = 'red'
                        sell_price = close[i]
                        profit_percentage = ((sell_price - buy_price) / buy_price) * 100
                        current_capital = capital_history[-1] * (1 + profit_percentage / 100)
                        capital_history.append(current_capital)

                        cumulative_profit_loss.append(profit_percentage)
                        total_profit_loss += profit_percentage

                        if profit_percentage > 0:
                            profitable_trades += 1
                        else:
                            losing_trades += 1
                        buy_price = None  # Pozisyon kapandı

            # Kümülatif sonuçları hesapla
            cumulative_total_profit_loss = ((capital_history[-1] - initial_capital) / initial_capital) * 100
            if len(cumulative_profit_loss) > 0:
                ortalama_islem = IndikatorTest.SMA(cumulative_profit_loss, len(cumulative_profit_loss))[-1]
            else:
                ortalama_islem = 0

            # Excel çıktısı oluştur
            strategy_name = strategy.__name__
            excel_data.append({
                'coin': coin,
                'periyot': periyot,
                'strategy name': strategy_name,
                'kümülatif kar zarar (%)': cumulative_total_profit_loss,
                'karlı işlemler': profitable_trades,
                'zararlı işlemler': losing_trades,
                'ortalama işlem sonucu': ortalama_islem
            })
        return {'EXCEL DATA':excel_data,"ISLEM GECMISI":islem_gecmisi}
    @staticmethod
    def Kayit_Et(excel_data_list):
        # Kayıt yapılacak dosyanın yolu
        output_file = "Data/strategy_results.xlsx"

        # Dosyanın bulunduğu klasörün varlığını kontrol et ve yoksa oluştur
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        # İç içe listelerdeki verileri düz bir listeye ayıkla
        flattened_data = []
        for data in excel_data_list:
            for item in data:  # İçteki sözlükleri ayıkla
                flattened_data.append(item)

        # Yeni veriler için DataFrame oluştur
        new_data_df = pd.DataFrame(flattened_data)

        # Veriyi sıfırdan dosyaya yaz (önceki veriler silinir)
        new_data_df.to_excel(output_file, index=False, engine='openpyxl')
    @staticmethod
    def Grafik_Ciz(coin, periyot,selected_strategy_name=None,stop=False,ema_check=False,bb_check=False,heiken_ashi=False):
        import matplotlib.pyplot as plt
        from matplotlib.widgets import Cursor
        
        # Veri ithali
        binance = Binance()
        data = binance.get_coin_data(coin, periyot, 1000)
        opendate=data['opendate']
        vol = data['volume_coin']
        if heiken_ashi:
            data=binance.heiken_ashi(data)
        open = data['open']
        high = data['high']
        low = data['low']
        close = data['close']

        # Strateji listesi
        if selected_strategy_name is None:
            strategies = [getattr(StratejilerTest, func) for func in dir(StratejilerTest)
                          if callable(getattr(StratejilerTest, func))
                          and not func.startswith("__")
                          and not getattr(StratejilerTest, func).__name__ in ["dinamik_stop_lose", "static_stop_lose",
                                                                              "destek_stop_lose", "take_profit"]]
        else:
            strategies=[getattr(StratejilerTest,selected_strategy_name)]

        # Girişlerin uzunluğunu kontrol et
        n = len(open)
        if not all(len(lst) == n for lst in [high, low, close, opendate]):
            raise ValueError("Tüm listelerin uzunluğu eşit olmalıdır.")

        # Timestamp'leri doğrula ve datetime formatına çevir
        try:
            dates = [
                datetime.fromtimestamp(ts / 1000.0).strftime('%Y-%m-%d %H:%M:%S') if ts > 0 else "Invalid Timestamp" for
                ts in opendate]
        except Exception as e:
            raise ValueError(f"Timestamps işleminde hata oluştu: {e}")

        if "Invalid Timestamp" in dates:
            raise ValueError(
                "Geçersiz zaman damgaları tespit edildi. Lütfen tüm timestamp değerlerinin pozitif ve geçerli olduğundan emin olun.")

        for strategy in strategies:
            last_signal = None
            buy_points = []
            sell_points = []
            stop_points = []
            if strategy.__name__ not in ["SMC_Strategy","SMC_Strategy_new","Smart_MACD_Reversal","Alpha_Trend","E_A_S_Y"]:
                strategy_resault,indicators = strategy(high, low, close)
            if strategy.__name__ in ["Smart_MACD_Reversal","Alpha_Trend"]:
                strategy_resault,indicators = strategy(high,low,close,vol)
            if strategy.__name__ in ["E_A_S_Y"]:
                ha_data=binance.heiken_ashi(data)
                ha_high=ha_data['high']
                ha_low=ha_data['low']
                ha_close=ha_data['close']
                strategy_resault, indicators = strategy(ha_high, ha_low, ha_close)
            destek=None
            direnc=None
            dinamik_stop_lose_check=False
            higest_price=0
            dinamik_stop_signal=None
            atr=IndikatorTest.ATR(high, low, close)
            adx=IndikatorTest.ADX(high, low, close)
            if ema_check:
                ema50=IndikatorTest.EMA(close,50)
            if bb_check:
                bb_down, bb_mid, bb_top = IndikatorTest.BB(close)

            # 2. Grafik: Kapital ve kâr/zarar hesaplama
            initial_capital = 100
            current_capital = initial_capital
            capital_history = [initial_capital]
            cumulative_profit_loss = []
            buy_price = None

            for i in range(len(close)):
                if strategy.__name__ in ["SMC_Strategy","SMC_Strategy_new"]:
                    strategy_resault,indicators=strategy(high[:i+1],low[:i+1],close[:i+1])
                if last_signal is None or last_signal == 'red':
                    if ema_check or bb_check:
                        if ema_check:
                            if ema50[i] is not None and close[i] > ema50[i]:
                                pass
                            else:
                                continue
                        if bb_check:
                            if bb_mid[i] is not None and close[i] <= bb_mid[i]:
                                pass
                            else:
                                continue
                        if strategy_resault[i] == "BUY":
                            last_signal = 'green'
                            buy_points.append(i)
                            buy_price = close[i]
                    else:
                        if strategy_resault[i] == "BUY":  # and (ema50[i] is not None and close[i]>ema50[i])
                            last_signal = 'green'
                            buy_points.append(i)
                            buy_price = close[i]

                elif last_signal == 'green':
                    # Stop-lose hesaplama
                    if stop:
                        destek, direnc, destek_stop_signal = StratejilerTest.destek_stop_lose(buy_points[-1], destek,direnc, close[:i + 1],low[:i + 1])
                        if direnc is None:
                            dinamik_stop_lose_check = True
                        if dinamik_stop_lose_check:
                            dinamik_stop_signal, higest_price, stop_level = StratejilerTest.dinamik_stop_lose(atr[:i + 1], adx[:i + 1], close[:i + 1], higest_price)
                    if strategy_resault[i] == "SELL":
                        last_signal = 'red'
                        sell_points.append(i)
                        sell_price = close[i]
                        profit_percentage = ((sell_price - buy_price) / buy_price) * 100
                        current_capital *= (1 + profit_percentage / 100)
                        capital_history.append(current_capital)
                        cumulative_profit_loss.append(profit_percentage)

                    elif stop and (destek_stop_signal=="STOP-LOSE" or (dinamik_stop_lose_check and dinamik_stop_signal=="STOP-LOSE")):     #
                        last_signal = 'red'
                        dinamik_stop_lose_check=False
                        higest_price=0
                        stop_points.append(i)
                        sell_price = close[i]
                        profit_percentage = ((sell_price - buy_price) / buy_price) * 100
                        current_capital *= (1 + profit_percentage / 100)
                        capital_history.append(current_capital)
                        cumulative_profit_loss.append(profit_percentage)

            # Yeni pencere oluştur
            fig = plt.figure(figsize=(16, 10))

            # 1. Grafik: Fiyat ve alım-satım noktaları
            ax1 = plt.subplot2grid((2, 2), (0, 0), colspan=2)
            ax1.set_xlabel('Zaman (Periyotlar)')
            ax1.set_ylabel('Fiyat', color='black')
            ax1.set_title(f"{coin} {periyot} - {strategy.__name__}")
            ax1.tick_params(axis='y', labelcolor='black')
            ax1.set_xticks(np.arange(0, len(close), step=25))
            ax1.set_ylim(min(close) * 0.95, max(close) * 1.05)


            # Mum grafiği çizimi
            for i in range(len(close)):
                color = 'green' if close[i] >= open[i] else 'red'  # Yeşil yükseliş, kırmızı düşüş
                ax1.plot([i, i], [low[i], high[i]], color=color, linewidth=1.5)  # Fitil çizimi
                ax1.add_patch(plt.Rectangle((i - 0.4, min(open[i], close[i])), 0.8, abs(close[i] - open[i]),
                                            color=color, alpha=0.7))  # Mum gövdesi

            # Alım ve Satım Noktalarını ekle
            for buy_point in buy_points:
                ax1.plot(buy_point, low[buy_point]*0.99, 'c^', label="Alım Noktası")
            for sell_point in sell_points:
                ax1.plot(sell_point, high[sell_point]*1.01, 'kv', label="Satım Noktası")
            for stop_point in stop_points:
                ax1.plot(stop_point, high[stop_point]*1.01, 'mv', label="Stop Noktası")

            # Mouse ile veri inceleme
            cursor_main = Cursor(ax1, useblit=True, color='blue', linewidth=1)

            def format_coord(x, y):
                index = int(round(x))
                if 0 <= index < n:
                    o = open[index]
                    h = high[index]
                    l = low[index]
                    c = close[index]
                    time = dates[index]
                    buy_sell_points=None
                    if index in buy_points:
                        buy_sell_points="BUY"
                    elif index in sell_points:
                        buy_sell_points="SELL"

                    # Yüzdelik değişim hesaplama
                    if o != 0:
                        price_change_percent = ((c - o) / o) * 100
                    else:
                        price_change_percent = 0

                    # Fiyat değişimini ve diğer indikatörleri ekle

                    return f"Time: {time}, Open: {o}, High: {h}, Low: {l}, Close: {c}, Change: {price_change_percent:.2f}%, Buy/Sell Points: {buy_sell_points} "
                return f"X: {x:.2f}, Y: {y:.2f}"

            ax1.format_coord = format_coord

            ax2 = plt.subplot2grid((2, 2), (1, 0))
            ax2.plot(capital_history, marker='o', markersize=5, linewidth=2,
                     label=f"Kapital\nSon Kapital: {capital_history[-1]:.2f}")
            ax2.set_title(f"{strategy.__name__} Kapital Durumu")
            ax2.set_xlabel('İşlem Sayısı')
            ax2.set_ylabel('Kapital (TL)')
            ax2.axhline(initial_capital, color='black', linestyle='--')
            ax2.legend()

            # Mouse ile veri inceleme
            cursor_capital = Cursor(ax2, useblit=True, color='blue', linewidth=1)

            def format_coord(x, y):
                index = int(round(x))
                if 0 <= index < len(capital_history):
                    kumulatif = capital_history[index]

                    return f"{index+1}. Kumulatif deger: {kumulatif:.2f} "
                return f"X: {x:.2f}, Y: {y:.2f}"

            ax2.format_coord = format_coord

            # Toplam karlı ve zararlı işlem sayıları
            total_profit_trades = sum(1 for x in cumulative_profit_loss if x > 0)
            total_loss_trades = sum(1 for x in cumulative_profit_loss if x < 0)

            # 3. Grafik: Kümülatif kâr/zarar yüzdesi
            ax3 = plt.subplot2grid((2, 2), (1, 1))
            ax3.plot(cumulative_profit_loss, marker='o', markersize=5, linewidth=2, label=f"{strategy.__name__} Kâr/Zarar\nKârlı İşlemler: {total_profit_trades}\nZararlı İşlemler: {total_loss_trades}")
            ax3.set_title(f"{strategy.__name__} Kümülatif Kâr/Zarar (%)")
            ax3.set_xlabel('İşlem Sayısı')
            ax3.set_ylabel('Kâr/Zarar (%)')
            ax3.axhline(0, color='black', linestyle='--')
            ax3.legend()

            # Mouse ile veri inceleme
            cursor_result = Cursor(ax3, useblit=True, color='blue', linewidth=1)

            def format_coord(x, y):
                index = int(round(x))
                if 0 <= index < len(cumulative_profit_loss):
                    result = cumulative_profit_loss[index]

                    return f"{index+1}. İşlem Sonucu: {result:.2f}% "
                return f"X: {x:.2f}, Y: {y:.2f}"

            ax3.format_coord = format_coord

            plt.tight_layout()
            IndikatorTest.Grafik_Indikator(open,high,low,close,vol,opendate,indicators['main_indicators'],indicators['sub_indicators'],indicators['sub_horizontal_lines'])
            plt.show()
    @staticmethod
    def Grafik_Ciz_Save(coin, periyot, selected_strategy_name=None):
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        
        # Veri ithali
        binance = Binance()
        data = binance.get_coin_data(coin, periyot, 1000)
        high = data['high']
        low = data['low']
        close = data['close']

        # Strateji listesi
        strategies = [getattr(StratejilerTest, func) for func in dir(StratejilerTest)
                      if callable(getattr(StratejilerTest, func))
                      and not func.startswith("__")
                      and not getattr(StratejilerTest, func).__name__ in ["dinamik_stop_lose", "static_stop_lose",
                                                                          "destek_stop_lose", "Alpha_Trend","take_profit"]]

        fig = plt.figure(figsize=(16, 30))
        gs = gridspec.GridSpec(len(strategies) + 1, 2, height_ratios=[2] + [1] * len(strategies))

        # 1. Grafik: Fiyat
        ax1 = fig.add_subplot(gs[0, :])
        ax1.set_xlabel('Zaman (Periyotlar)')
        ax1.set_ylabel('Fiyat', color='black')
        ax1.plot(close, color='black', label='Fiyat', linewidth=1.5)
        ax1.tick_params(axis='y', labelcolor='black')
        ax1.set_xticks(np.arange(0, len(close), step=25))
        ax1.set_ylim(min(close) * 0.95, max(close) * 1.05)
        ax1.yaxis.set_major_locator(plt.MaxNLocator(10))
        ax1.legend()
        ax1.set_title(f"{coin} {periyot} {selected_strategy_name}")

        capital_histories = []
        cumulative_profit_losses = []
        total_profit_losses = []
        profitable_trade_counts = []
        losing_trade_counts = []
        colors = ['orange', 'green', 'purple', 'red', 'brown', 'pink', 'gray', 'olive', 'cyan', 'blue', 'gold',
                  'lightblue', 'lightgreen',
                  'magenta', 'salmon', 'teal', 'violet', 'darkorange', 'darkgreen', 'darkviolet', 'deepskyblue',
                  'dodgerblue', 'crimson',
                  'khaki', 'chartreuse', 'lavender', 'lightcoral', 'mediumseagreen', 'orangered', 'indigo', 'slategray',
                  'cornflowerblue',
                  'mediumslateblue', 'lightsteelblue', 'palevioletred', 'springgreen', 'seashell', 'peru', 'steelblue',
                  'tan', 'wheat']

        # Seçilen stratejiye göre alım ve satım noktaları (yeşil ve kırmızı yuvarlaklar)
        buy_points = []
        sell_points = []

        # Her strateji için ayrı bir subplot
        for idx, strategy in enumerate(strategies):
            last_signal = None
            buy_price = None
            cumulative_profit_loss = []
            total_profit_loss = 0
            profitable_trades = 0
            losing_trades = 0
            initial_capital = 100
            current_capital = initial_capital
            capital_history = [initial_capital]

            strategy_resault,indicators = strategy(high, low, close)
            if strategy.__name__ == "Super_Trend":
                print(strategy_resault)
            for i in range(len(close)):
                if last_signal is None or last_signal == 'red':
                    if strategy_resault[i] == "BUY":
                        last_signal = 'green'
                        buy_price = close[i]
                        amount_purchased = current_capital / buy_price
                        current_capital = 0
                        if selected_strategy_name == strategy.__name__:
                            buy_points.append(i)  # Alım noktasını kaydet
                elif last_signal == 'green':
                    if strategy_resault[i] == "SELL":
                        last_signal = 'red'
                        sell_price = close[i]
                        profit_percentage = ((sell_price - buy_price) / buy_price) * 100
                        current_capital = capital_history[-1] * (1 + profit_percentage / 100)
                        capital_history.append(current_capital)

                        cumulative_profit_loss.append(profit_percentage)
                        total_profit_loss += profit_percentage

                        if profit_percentage > 0:
                            profitable_trades += 1
                        else:
                            losing_trades += 1

                        if selected_strategy_name == strategy.__name__:
                            sell_points.append(i)  # Satım noktasını kaydet

                        buy_price = None

            capital_histories.append(capital_history)
            cumulative_profit_losses.append(cumulative_profit_loss)
            total_profit_losses.append(total_profit_loss)
            profitable_trade_counts.append(profitable_trades)
            losing_trade_counts.append(losing_trades)

            # Son kapital ve kümülatif kâr/zarar hesaplamaları
            final_capital = capital_history[-1]
            cumulative_total_profit_loss = ((final_capital - initial_capital) / initial_capital) * 100

            # Her strateji için kapital ve kümülatif kâr/zarar grafiği
            ax2 = fig.add_subplot(gs[idx + 1, 0])
            ax2.plot(capital_history, marker='o', markersize=5, linewidth=2,
                     color=colors[idx % len(colors)],
                     label=f"{strategy.__name__} Kapital\nSon Kapital: {final_capital:.2f}\nKümülatif Kâr/Zarar: {cumulative_total_profit_loss:.2f}%")
            ax2.set_title(f"{strategy.__name__} Kapital Durumu")
            ax2.set_xlabel('İşlem Sayısı')
            ax2.set_ylabel('Kapital (TL)')
            ax2.axhline(initial_capital, color='black', linestyle='--')
            ax2.legend()

            # Kârlı ve zararlı işlemler
            ax3 = fig.add_subplot(gs[idx + 1, 1])
            ax3.plot(cumulative_profit_loss, marker='o', markersize=5, linewidth=2,
                     color=colors[idx % len(colors)],
                     label=f"{strategy.__name__} Kâr/Zarar\nKârlı İşlemler: {profitable_trades}\nZararlı İşlemler: {losing_trades}")
            ax3.set_title(f"{strategy.__name__} Kümülatif Kâr/Zarar (%)")
            ax3.set_xlabel('İşlem Sayısı')
            ax3.set_ylabel('Kâr/Zarar (%)')
            ax3.axhline(0, color='black', linestyle='--')
            ax3.legend()

        # 1. grafikte alım ve satım noktalarını göster
        if selected_strategy_name is not None:
            for buy_point in buy_points:
                ax1.plot(buy_point, close[buy_point], 'go', label="Alım Noktası")  # Yeşil yuvarlak
            for sell_point in sell_points:
                ax1.plot(sell_point, close[sell_point], 'ro', label="Satım Noktası")  # Kırmızı yuvarlak

                # Grafiği PNG olarak kaydet
        plt.tight_layout()
        plt.savefig(
            f"./Data/{coin}_{periyot}_{selected_strategy_name if selected_strategy_name else 'TümStratejiler'}.png",
            dpi=300, bbox_inches='tight')
    @staticmethod
    def hesapla_wrapper(args):
        coin, periyot = args
        return Backtest.Hesapla(coin, periyot)['EXCEL DATA']
    @staticmethod
    def paralel_hesaplama():
        binance = Binance()
        coins = binance.secili_list()  # Coin listesini al
        periyots = ["15m", "1h", "4h", "1d"]  # Periyotlar
        sonuclar = []

        # Coin ve periyot kombinasyonlarını oluştur
        tasks = [(coin, periyot) for coin in coins for periyot in periyots]

        # Paralel işlem yapmak için ProcessPoolExecutor kullanıyoruz
        with ProcessPoolExecutor() as executor:
            # Görevleri paralel çalıştır
            results = executor.map(Backtest.hesapla_wrapper, tasks)

        # Sonuçları birleştir
        sonuclar.extend(results)

        # Sonuçları kaydet
        Backtest.Kayit_Et(sonuclar)
    @staticmethod
    def backtest_islem_gecmisi_analiz(islem_gecmisi):
        strategys=[]
        dinamik_stop_sonucu=[]
        static_stop_sonucu=[]
        hedef_satis_sonucu=[]
        sonuc={}
        for islem in islem_gecmisi:
            islem=islem.split(" ")
            if islem[1] not in strategys:
                if len(strategys) >0:
                    dinamik_sayisi=len(dinamik_stop_sonucu)
                    static_sayisi=len(static_stop_sonucu)
                    hedef_sayisi=len(hedef_satis_sonucu)
                    oran=((static_sayisi+dinamik_sayisi)/(static_sayisi+dinamik_sayisi+hedef_sayisi))*100
                    oran=f"{oran:.2f}%"
                    sonuc[strategys[-1]]={"dinamik_stop_sayisi":dinamik_sayisi,"static_stop_sayisi":static_sayisi,"hedef_satis_sayisi":hedef_sayisi,"stop_orani":oran}
                    dinamik_stop_sonucu = []
                    static_stop_sonucu = []
                    hedef_satis_sonucu = []
                strategys.append(islem[1])
            if "%" in islem:
                if "[STOP-LOSE][DINAMIK]." in islem:
                    dinamik_stop_sonucu.append(islem[10])
                elif "[STOP-LOSE][STATIC]." in islem:
                    static_stop_sonucu.append(islem[10])
                elif "[HEDEF]." in islem:
                    hedef_satis_sonucu.append(islem[10])
        dinamik_sayisi = len(dinamik_stop_sonucu)
        static_sayisi = len(static_stop_sonucu)
        hedef_sayisi = len(hedef_satis_sonucu)
        oran = ((static_sayisi + dinamik_sayisi) / (static_sayisi + dinamik_sayisi + hedef_sayisi)) * 100
        oran = f"{oran:.2f}%"
        sonuc[strategys[-1]] = {"dinamik_stop_sayisi": dinamik_sayisi, "static_stop_sayisi": static_sayisi,
                                "hedef_satis_sayisi": hedef_sayisi, "stop_orani": oran}

        for strategy in strategys:
            print(f"{strategy}:Dinamik stop:{sonuc[strategy]['dinamik_stop_sayisi']} Static stop: {sonuc[strategy]['static_stop_sayisi']} Hedef: {sonuc[strategy]['hedef_satis_sayisi']} Stop Orani: {sonuc[strategy]['stop_orani']}")
        return sonuc
