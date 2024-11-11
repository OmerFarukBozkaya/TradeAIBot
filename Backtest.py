from IndikatorTest import IndikatorTest
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.gridspec as gridspec
import os
import pandas as pd
import csv
from Binance import Binance
from Stratejiler import Stratejiler

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
            data = binance.get_coin_data(coin, periyot, 1000)
            high = data['high']
            low = data['low']
            close = data['close']

        print("Yeni")
        # Strateji listesi (Strateji adı, alım koşulu, satım koşulu)
        strategies = [
            {
                "name": "MACD",
                "buy_condition": lambda i: Stratejiler.MACD(high[:i], low[:i], close[:i]) == "BUY",
                "sell_condition": lambda i: Stratejiler.MACD(high[:i], low[:i], close[:i]) == "SELL"
            },
            {
                "name": "Ma Cross",
                "buy_condition": lambda i: Stratejiler.MA_Cross(high[:i], low[:i], close[:i]) == "BUY",
                "sell_condition": lambda i: Stratejiler.MA_Cross(high[:i], low[:i], close[:i]) == "SELL"
            },
            {
                "name": "BB(RSI)",
                "buy_condition": lambda i: Stratejiler.BB_RSI(high[:i], low[:i], close[:i]) == "BUY",
                "sell_condition": lambda i: Stratejiler.BB_RSI(high[:i], low[:i], close[:i]) == "SELL"
            },
            {
                "name": "BB(close)",
                "buy_condition": lambda i: Stratejiler.BB_Close(high[:i], low[:i], close[:i]) == "BUY",
                "sell_condition": lambda i: Stratejiler.BB_Close(high[:i], low[:i], close[:i]) == "SELL"
            },
            {
                "name": "DMO",
                "buy_condition": lambda i: Stratejiler.DMO(high[:i], low[:i], close[:i]) == "BUY",
                "sell_condition": lambda i: Stratejiler.DMO(high[:i], low[:i], close[:i]) == "SELL"
            },
            {
                "name": "VMZI",
                "buy_condition": lambda i: Stratejiler.VMZI(high[:i], low[:i], close[:i]) == "BUY",
                "sell_condition": lambda i: Stratejiler.VMZI(high[:i], low[:i], close[:i]) == "SELL"
            },
            {
                "name": "FDI",
                "buy_condition": lambda i: Stratejiler.FDI(high[:i], low[:i], close[:i]) == "BUY",
                "sell_condition": lambda i: Stratejiler.FDI(high[:i], low[:i], close[:i]) == "SELL"
            },
            {
                "name": "VAMA",
                "buy_condition": lambda i: Stratejiler.VAMA(high[:i], low[:i], close[:i]) == "BUY",
                "sell_condition": lambda i: Stratejiler.VAMA(high[:i], low[:i], close[:i]) == "SELL"
            },
            {
                "name": "TSO",
                "buy_condition": lambda i: Stratejiler.TSO(high[:i], low[:i], close[:i]) == "BUY",
                "sell_condition": lambda i: Stratejiler.TSO(high[:i], low[:i], close[:i]) == "SELL"
            },
            {
                "name": "BB ADX",
                "buy_condition": lambda i: Stratejiler.BB_ADX(high[:i], low[:i], close[:i]) == "BUY",
                "sell_condition": lambda i: Stratejiler.BB_ADX(high[:i], low[:i], close[:i]) == "SELL"
            },

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

            for i in range(4,len(close)):
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