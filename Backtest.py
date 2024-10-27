from IndikatorTest import IndikatorTest
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.gridspec as gridspec
import os
import pandas as pd
import csv
from Binance import Binance

class Backtest:
    @staticmethod
    def Test(canli_veriler,coin="BTCUSDT",file_name='THYAO Geçmiş Verileri.csv',periyot="4h",adet=1000, selected_strategy_name=None,kayit_et=False,hisse=False):
        close = []
        low = []
        high = []
        #Veri ithali
        if canli_veriler == False and hisse == False:   # Kayıtlı coin verileri
            close = open("Data/close-test.txt", "r").read().split(",")
            low = open("Data/low-test.txt", "r").read().split(",")
            high = open("Data/high-test.txt", "r").read().split(",")
            for i in range(len(close)):
                close[i] = float(close[i])
                low[i] = float(low[i])
                high[i] = float(high[i])
        elif canli_veriler == False and hisse == True:  # csv den hisse verilerini oku
            with open(file_name, mode='r', newline='', encoding='utf-8') as file:
                csv_reader = csv.reader(file)
                next(csv_reader)
                for row in csv_reader:
                    close.append(float(row[1].replace(",",".")))
                    low.append(float(row[4].replace(",", ".")))
                    high.append(float(row[3].replace(",", ".")))
                close.reverse()
                high.reverse()
                low.reverse()

        elif canli_veriler == True and hisse == False:  # Canlı coin verileri
            binance = Binance()
            close = binance.data(coin, adet, periyot, 4)
            low = binance.data(coin, adet, periyot, 3)
            high = binance.data(coin, adet, periyot, 2)

        # İndikatör hesaplamaları
        pmai_values = IndikatorTest.PMAI(close)
        pmai_sma = IndikatorTest.SMA(pmai_values, 14)
        rsi_values = IndikatorTest.RSI(close)
        adx = IndikatorTest.ADX(high, low, close)
        ema_200 = IndikatorTest.EMA(close,200)
        macd = IndikatorTest.MACD(close)
        macd_values = macd[0]
        macd_signal = macd[1]
        bb_rsi = IndikatorTest.BB(rsi_values)
        bb_rsi_down = bb_rsi[0]
        bb_rsi_up = bb_rsi[2]
        bb=IndikatorTest.BB(close)
        bb_down = bb[0]
        bb_mid = bb[1]
        bb_up = bb[2]
        max_high_20 = IndikatorTest.Max_Last(high, 20)
        max_low_20 = IndikatorTest.Max_Last(low, 20)
        ma_9 = IndikatorTest.SMA(close, 9)
        ma_50 = IndikatorTest.SMA(close, 50)
        fib = IndikatorTest.FIB(close)
        dmo=IndikatorTest.DMO(close)
        vmzi=IndikatorTest.VMZI(close)
        fdi = IndikatorTest.FDI(close)
        vama=IndikatorTest.VAMA(close,14)
        ichimoku_bulutu=IndikatorTest.Ichimoku_Bulutu(high, low)
        tso = IndikatorTest.TSO(high,low,close)

        # Strateji listesi (Strateji adı, alım koşulu, satım koşulu)
        strategies = [
            {
                "name": "PMAI & RSI",
                "buy_condition": lambda i: pmai_values[i] is not None and pmai_sma[i] is not None and
                                           rsi_values[i] is not None and adx[i] is not None and

                                           pmai_values[i] > pmai_sma[i] * 1.2 and rsi_values[i] > 50 and adx[i] > 25,
                "sell_condition": lambda i: pmai_values[i] is not None and pmai_values[i] < 30
            },
            {
                "name": "MACD",
                "buy_condition": lambda i: macd_values[i] is not None and macd_signal[i] is not None and \
                                           rsi_values[i] is not None and

                                           macd_values[i] > macd_signal[i] and rsi_values[i] > 50,
                "sell_condition": lambda i: macd_values[i] is not None and macd_signal[i] is not None and \
                                            macd_values[i] < macd_signal[i]
            },
            {
                "name": "Breakout",
                "buy_condition": lambda i: max_high_20[i - 1] is not None and adx[i] is not None and

                                           max_high_20[i - 1] < close[i] and adx[i] > 30,
                "sell_condition": lambda i: max_low_20[i - 1] is not None and adx[i] is not None and
                                            low[i - 1] is not None and ((max_low_20[i - 1] > close[i]) or
                                        (close[i] > buy_price * 1.05 and close[i] < buy_price * 0.98) or (low[i - 1] * 0.98 > close[i]))
            },
            {
                "name": "Ma Cross",
                "buy_condition": lambda i: ma_9[i-1] is not None and ma_50[i-1] is not None and \
                                           adx[i] is not None and ma_9[i] is not None and ma_50[i] is not None and

                                           ma_9[i-1] < ma_50[i-1] and ma_9[i] > ma_50[i] and adx[i] > 30,
                "sell_condition": lambda i: ma_9[i-1] is not None and ma_50[i-1] is not None and \
                                           ma_9[i] is not None and ma_50[i] is not None and ((ma_9[i] < ma_50[i] and
                                           ma_9[i-1] > ma_50[i-1]) or (close[i]>ma_9[i]*1.03 and close[i]<ma_9[i]*0.99) or (ma_50[i]*0.99>close[i]))
            },
            {
                "name": "BB(RSI)",
                "buy_condition": lambda i: bb_rsi_down[i - 1] is not None and bb_rsi_down[i] is not None and rsi_values[i - 1]
                                           is not None and rsi_values[i] is not None and

                                           bb_rsi_down[i - 1] > rsi_values[i - 1] and bb_rsi_down[i] < rsi_values[i],
                "sell_condition": lambda i: bb_rsi_up[i - 1] is not None and bb_rsi_up[i] is not None and rsi_values[i - 1]
                                           is not None and rsi_values[i] is not None and bb_rsi_up[i - 1] < rsi_values[i - 1]
                                            and bb_rsi_up[i] > rsi_values[i]
            },
            {
                "name": "BB(close)",
                "buy_condition": lambda i: bb_down[i - 1] is not None and bb_down[i] is not None and

                                           bb_down[i - 1] > close[i - 1] and bb_down[i] < close[i],
                "sell_condition": lambda i: bb_up[i - 1] is not None and bb_up[i] is not None and
                                            (bb_up[i - 1] < close[i - 1] and bb_up[i] > close[i]) or (bb_down[i]*0.99>close[i]) or
                                            (bb_mid[i-1]<close[i-1] and bb_mid[i]>close[i]) or (close[i]<buy_price * 0.97)
            },
            {
                "name": "RSI Aşırı Alım/Satım",
                "buy_condition": lambda i: rsi_values[i] is not None and

                                           rsi_values[i]<30,
                "sell_condition": lambda i: rsi_values[i-1] is not None and rsi_values[i]>70 or
                                            (rsi_values[i-1]>50 and rsi_values[i]<50) or (rsi_values[i]<25)
            },
            {
                "name": "Fibonacci Retracement",
                "buy_condition": lambda i: fib[i-1][0] is not None and fib[i][0] is not None and

                                           (close[i-1] > fib[i-1][1] and close[i] < fib[i][1]),
                "sell_condition": lambda i: fib[i][0] is not None and (fib[i][4]<close[i]) or (buy_price * 0.97 > close[i]) or
                                            (close[i] > buy_price * 1.05 and fib[i][2]*0.99 > close[i] and fib[i-1][2] < close[i-1] )
            },
            {
                "name": "DMO",
                "buy_condition": lambda i: dmo[i] is not None and adx[i] is not None and rsi_values[i] is not None and bb_up[i] is not None and

                #(dmo[i]>1.5 and adx[i] > 25 and rsi_values[i] > 50 and atr[i]<atr_14[i])
                                           (dmo[i]>1.0 and adx[i] > 20 and rsi_values[i] > 50 and close[i]>=bb_up[i]),
                "sell_condition": lambda i: dmo[i] is not None and adx[i] is not None and
                                            (dmo[i]<0.8 or adx[i] < 20 or (rsi_values[i]<50 and close[i] <= bb_down[i]))
            },
            {
                "name": "VMZI",
                "buy_condition": lambda i: vmzi[i] is not None and adx[i] is not None and rsi_values[i] is not None and

                                           (vmzi[i]>1.5 and adx[i] > 25 and rsi_values[i] > 50),
                "sell_condition": lambda i: vmzi[i] is not None and rsi_values[i] is not None and
                                            (vmzi[i]<0 and rsi_values[i] < 50)
            },
            {
                "name": "FDI",
                "buy_condition": lambda i: fdi[i-1] is not None and fdi[i] is not None and rsi_values[i] is not None and
                                            macd_values[i] is not None and macd_signal[i] is not None and

                                           (fdi[i-1]>0 and  fdi[i-1] < fdi[i] and rsi_values[i] > 40 and macd_values[i] > macd_signal[i]),
                "sell_condition": lambda i: fdi[i-1] is not None and fdi[i] is not None and rsi_values[i] is not None and
                                            (fdi[i-1]<0 and fdi[i-1] > fdi[i] and rsi_values[i] < 60 and macd_values[i] < macd_signal[i])
            },
            {
                "name": "VAMA",
                "buy_condition": lambda i: vama[i] is not None and

                                           (vama[i]*1.02<close[i]),
                "sell_condition": lambda i: vama[i] is not None and
                                           (vama[i]*0.98>close[i])
            },
            {
                "name": "Ichimoku Bulutu",
                "buy_condition": lambda i: ichimoku_bulutu[0][i] is not None and ichimoku_bulutu[1][i] is not None and
                                           ichimoku_bulutu[2][i] is not None and ichimoku_bulutu[3][i] is not None and
                                           ichimoku_bulutu[0][i - 1] is not None and ichimoku_bulutu[1][i-1] is not None and
                                            #ichimoku_bulutu[0][i]>close[i] and ichimoku_bulutu[1][i]>close[i] and
                                            #ichimoku_bulutu[2][i]>close[i] and ichimoku_bulutu[3][i]>close[i] and
                                           (
                                            ichimoku_bulutu[0][i-1] < ichimoku_bulutu[1][i-1] and ichimoku_bulutu[0][i] > ichimoku_bulutu[1][i]),
                "sell_condition": lambda i: ichimoku_bulutu[0][i] is not None and ichimoku_bulutu[1][i] is not None and
                                           ichimoku_bulutu[2][i] is not None and ichimoku_bulutu[3][i] is not None and
                                           ichimoku_bulutu[0][i - 1] is not None and ichimoku_bulutu[1][i-1] is not None and

                                            ((ichimoku_bulutu[0][i]<close[i] and ichimoku_bulutu[1][i]<close[i] and
                                            ichimoku_bulutu[2][i]<close[i] and ichimoku_bulutu[3][i]<close[i]) or (
                                            ichimoku_bulutu[0][i-1] > ichimoku_bulutu[1][i-1] and ichimoku_bulutu[0][i] < ichimoku_bulutu[1][i]))
            },
            {
                "name": "TSO",
                "buy_condition": lambda i: tso[i] is not None and

                                           (tso[i] == 1),
                "sell_condition": lambda i: tso[i] is not None and
                                           (tso[i] == -1)
            },
            {
                "name": "Ma Range Breakout",
                "buy_condition": lambda i: ma_50[i-1] is not None and ma_50[i] is not None and

                                           (ma_50[i-1] > close[i-1] and ma_50[i] < close[i]),
                "sell_condition": lambda i: ma_50[i-1] is not None and ma_50[i] is not None and

                                           (ma_50[i-1] < close[i-1] and ma_50[i] > close[i]),
            },
            {
                "name": "BB ADX",
                "buy_condition": lambda i: bb_down[i] is not None and adx[i] is not None and

                                           (close[i] < bb_down[i] and adx[i] > 25),
                "sell_condition": lambda i: bb_up[i] is not None and adx[i] is not None and

                                            (close[i] > bb_up[i] and adx[i] < 20),
            },
            {
                "name": "MACD EMA",
                "buy_condition": lambda i: macd_values[i-1] is not None and macd_values[i] is not None and
                                            macd_signal[i-1] is not None and macd_signal[i] is not None and ema_200[i] is not None and

                                           (macd_values[i] > macd_signal[i] and macd_values[i-1] < macd_signal[i-1] and close[i] > ema_200[i]),
                "sell_condition": lambda i: macd_values[i-1] is not None and macd_values[i] is not None and
                                            macd_signal[i-1] is not None and macd_signal[i] is not None and

                                            (macd_values[i] < macd_signal[i] and macd_values[i-1] > macd_signal[i-1]),
            }

        ]
        if kayit_et != True:
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
        colors = ['orange','green','purple','red','brown','pink','gray','olive','cyan','blue','gold','lightblue','lightgreen',
            'magenta','salmon','teal','violet','darkorange','darkgreen','darkviolet','deepskyblue','dodgerblue','crimson',
            'khaki','chartreuse','lavender','lightcoral','mediumseagreen','orangered','indigo','slategray','cornflowerblue',
            'mediumslateblue','lightsteelblue','palevioletred','springgreen','seashell','peru','steelblue','tan','wheat']

        # Seçilen stratejiye göre alım ve satım noktaları (yeşil ve kırmızı yuvarlaklar)
        buy_points = []
        sell_points = []
        # Excel'e yazılacak veriler için bir liste oluştur
        excel_data = []

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

            for i in range(len(close)):
                if last_signal is None or last_signal == 'red':
                    if strategy["buy_condition"](i):
                        last_signal = 'green'
                        buy_price = close[i]
                        amount_purchased = current_capital / buy_price
                        current_capital = 0
                        if selected_strategy_name == strategy["name"]:
                            buy_points.append(i)  # Alım noktasını kaydet
                elif last_signal == 'green':
                    if strategy["sell_condition"](i):
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

                        if selected_strategy_name == strategy["name"]:
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

            if  kayit_et != True:
                # Her strateji için kapital ve kümülatif kâr/zarar grafiği
                ax2 = fig.add_subplot(gs[idx + 1, 0])
                ax2.plot(capital_history, marker='o', markersize=5, linewidth=2,
                         color=colors[idx % len(colors)],
                         label=f"{strategy['name']} Kapital\nSon Kapital: {final_capital:.2f}\nKümülatif Kâr/Zarar: {cumulative_total_profit_loss:.2f}%")
                ax2.set_title(f"{strategy['name']} Kapital Durumu")
                ax2.set_xlabel('İşlem Sayısı')
                ax2.set_ylabel('Kapital (TL)')
                ax2.axhline(initial_capital, color='black', linestyle='--')
                ax2.legend()

                # Kârlı ve zararlı işlemler
                ax3 = fig.add_subplot(gs[idx + 1, 1])
                ax3.plot(cumulative_profit_loss, marker='o', markersize=5, linewidth=2,
                         color=colors[idx % len(colors)],
                         label=f"{strategy['name']} Kâr/Zarar\nKârlı İşlemler: {profitable_trades}\nZararlı İşlemler: {losing_trades}")
                ax3.set_title(f"{strategy['name']} Kümülatif Kâr/Zarar (%)")
                ax3.set_xlabel('İşlem Sayısı')
                ax3.set_ylabel('Kâr/Zarar (%)')
                ax3.axhline(0, color='black', linestyle='--')
                ax3.legend()

            #Excel çıktısı oluştur.
            if kayit_et:
                if selected_strategy_name==None:
                    strategy_name = strategy['name']
                    cumulative_total_profit_loss = ((capital_histories[idx][
                                                         -1] - 100) / 100) * 100  # Son kapital ile kümülatif kâr/zarar
                    profitable_trades = profitable_trade_counts[idx]
                    losing_trades = losing_trade_counts[idx]
                    if len(cumulative_profit_loss) > 0:
                        ortalama_islem = IndikatorTest.SMA(cumulative_profit_loss, len(cumulative_profit_loss))[-1]
                    else:
                        ortalama_islem = 0
                    # Veriyi ekle
                    excel_data.append({
                        'coin': coin,
                        'periyot': periyot,
                        'strategy name': strategy_name,
                        'kümülatif kar zarar (%)': cumulative_total_profit_loss,
                        'karlı işlemler': profitable_trades,
                        'zararlı işlemler': losing_trades,
                        'ortalama işlem sonucu': ortalama_islem
                    })
                elif selected_strategy_name == strategy['name'] :
                    strategy_name = strategy['name']
                    cumulative_total_profit_loss = ((capital_histories[idx][
                                                         -1] - 100) / 100) * 100  # Son kapital ile kümülatif kâr/zarar
                    profitable_trades = profitable_trade_counts[idx]
                    losing_trades = losing_trade_counts[idx]
                    if len(cumulative_profit_loss) > 0:
                        ortalama_islem = IndikatorTest.SMA(cumulative_profit_loss, len(cumulative_profit_loss))[-1]
                    else:
                        ortalama_islem = 0

                    # Veriyi ekle
                    excel_data.append({
                        'coin': coin,
                        'periyot': periyot,
                        'strategy name': strategy_name,
                        'kümülatif kar zarar (%)': cumulative_total_profit_loss,
                        'karlı işlemler': profitable_trades,
                        'zararlı işlemler': losing_trades,
                        'ortalama işlem sonucu':ortalama_islem
                    })



        if kayit_et:
            # Excel dosyasına yazma işlemi
            output_file = "Data/strategy_results.xlsx"
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            # Eğer dosya varsa, mevcut verileri oku
            if os.path.exists(output_file):
                existing_df = pd.read_excel(output_file, engine='openpyxl')
            else:
                existing_df = pd.DataFrame()  # Eğer dosya yoksa boş bir DataFrame oluştur

            # Yeni veriyi mevcut verilerle birleştir
            df = pd.DataFrame(excel_data)
            combined_df = pd.concat([existing_df, df], ignore_index=True)

            # Genişletilmiş veri çerçevesini aynı dosyaya tekrar kaydet
            combined_df.to_excel(output_file, index=False, engine='openpyxl')

        if kayit_et != True:
            # 1. grafikte alım ve satım noktalarını göster
            if selected_strategy_name is not None:
                for buy_point in buy_points:
                    ax1.plot(buy_point, close[buy_point], 'go', label="Alım Noktası")  # Yeşil yuvarlak
                for sell_point in sell_points:
                    ax1.plot(sell_point, close[sell_point], 'ro', label="Satım Noktası")  # Kırmızı yuvarlak

            plt.tight_layout()
            plt.show()
