from IndikatorTest import IndikatorTest
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.gridspec as gridspec

class Backtest:
    @staticmethod
    def Test(canli_veriler):
        close = open("close-test.txt", "r").read().split(",")
        low = open("low-test.txt", "r").read().split(",")
        high = open("high-test.txt", "r").read().split(",")

        for i in range(len(close)):
            close[i] = float(close[i])
            low[i] = float(low[i])
            high[i] = float(high[i])

        if canli_veriler:
            from Binance import Binance
            binance = Binance()
            coin = "BTCUSDT"
            adet = 1000
            periyot = "4h"
            close = binance.data(coin, adet, periyot, 4)
            low = binance.data(coin, adet, periyot, 3)
            high = binance.data(coin, adet, periyot, 2)

        # İndikatör hesaplamaları
        pmai_values = IndikatorTest.PMAI(close)
        pmai_sma = IndikatorTest.SMA(pmai_values, 14)
        rsi_values = IndikatorTest.RSI(close)
        adx = IndikatorTest.ADX(high, low, close)
        macd = IndikatorTest.MACD(close)
        macd_values = macd[0]
        macd_signal = macd[1]
        bb_rsi=IndikatorTest.BB(rsi_values)
        bb_rsi_down=bb_rsi[0]
        bb_rsi_mid = bb_rsi[1]
        bb_rsi_up = bb_rsi[2]
        max_high_20=IndikatorTest.Max_Last(high,20)
        max_low_20=IndikatorTest.Max_Last(low,20)
        ma_9=IndikatorTest.SMA(close,9)
        ma_50=IndikatorTest.SMA(close,50)

        # Strateji listesi (Strateji adı, alım koşulu, satım koşulu)
        strategies = [
            {
                "name": "PMAI & RSI",
                "buy_condition": lambda i: pmai_values[i] is not None and pmai_sma[i] is not None and \
                                           rsi_values[i] is not None and adx[i] is not None and \
                                           pmai_values[i] > pmai_sma[i] * 1.2 and rsi_values[i] > 50 and adx[i] > 25,
                "sell_condition": lambda i: pmai_values[i] is not None and pmai_values[i] < 30
            },
            {
                "name": "MACD",
                "buy_condition": lambda i: macd_values[i] is not None and macd_signal[i] is not None and \
                                           rsi_values[i] is not None and \
                                           macd_values[i] > macd_signal[i] and rsi_values[i] > 50,
                "sell_condition": lambda i: macd_values[i] is not None and macd_signal[i] is not None and \
                                            macd_values[i] < macd_signal[i]
            },
            {
                "name": "Breakout",
                "buy_condition": lambda i: max_high_20[i-1] is not None and adx[i] is not None and \
                                           max_high_20[i-1] < close[i] and adx[i]>30,
                "sell_condition": lambda i: max_low_20[i-1] is not None and adx[i] is not None and \
                                            max_low_20[i-1] > close[i]
            },
            {
                "name": "Ma Cross",
                "buy_condition": lambda i: ma_9[i-1] is not None and ma_50[i-1] is not None and \
                                           adx[i] is not None and ma_9[i] is not None and ma_50 is not None and ma_9[i-1]<ma_50[i-1] and ma_9[i]>ma_50[i] and adx[i] > 30,
                "sell_condition": lambda i: ma_9[i-1] is not None and ma_50[i-1] is not None and \
                                           ma_9[i] is not None and ma_50[i] is not None and ma_9[i]<ma_50[i] and ma_9[i-1]>ma_50[i-1]
            }
        ]

        # Grafik düzeni ayarlama
        fig = plt.figure(figsize=(16, 16))
        gs = gridspec.GridSpec(2, 2, height_ratios=[2, 1])

        # 1. Grafik: Fiyat, sadece kapanış fiyatı
        ax1 = fig.add_subplot(gs[0, :])
        ax1.set_xlabel('Zaman (Periyotlar)')
        ax1.set_ylabel('Fiyat', color='blue')
        ax1.plot(close, color='blue', label='Fiyat', linewidth=1.5)
        ax1.tick_params(axis='y', labelcolor='blue')
        ax1.set_xticks(np.arange(0, len(close), step=50))
        ax1.set_ylim(min(close) * 0.95, max(close) * 1.05)
        ax1.yaxis.set_major_locator(plt.MaxNLocator(10))

        # Kapital ve kâr/zarar verilerini tutmak için
        capital_histories = []
        cumulative_profit_losses = []
        total_profit_losses = []
        profitable_trade_counts = []
        losing_trade_counts = []

        colors = ['orange', 'green','purple','red','brown','pink','gray','olive','cyan']  # Stratejiler için renkler

        # Her stratejiyi test et
        for strategy in strategies:
            last_signal = None
            buy_price = None
            cumulative_profit_loss = []  # Kümülatif kâr/zarar yüzdesi
            total_profit_loss = 0  # Toplam kâr/zarar
            profitable_trades = 0  # Kârlı işlem sayısı
            losing_trades = 0  # Zararlı işlem sayısı
            initial_capital = 100
            current_capital = initial_capital
            capital_history = [initial_capital]
            for i in range(len(close)):
                if last_signal is None or last_signal == 'red':
                    if strategy["buy_condition"](i):
                        last_signal = 'green'
                        buy_price = close[i]
                        amount_purchased = current_capital / buy_price
                        current_capital = 0  # Nakit sıfırlanır

                elif last_signal == 'green':
                    if strategy["sell_condition"](i):
                        last_signal = 'red'
                        sell_price = close[i]
                        profit_percentage = ((sell_price - buy_price) / buy_price) * 100
                        cumulative_profit_loss.append(profit_percentage)

                        # Toplam kâr/zararı güncelle
                        total_profit_loss += (profit_percentage * (amount_purchased * buy_price) / initial_capital)

                        # Kârlı mı zararlı mı kontrol et
                        if profit_percentage > 0:
                            profitable_trades += 1
                        else:
                            losing_trades += 1

                        # Satış sonrası elde kalan para
                        current_capital = amount_purchased * sell_price
                        capital_history.append(current_capital)

                        buy_price = None

            capital_histories.append(capital_history)
            cumulative_profit_losses.append(cumulative_profit_loss)
            total_profit_losses.append(total_profit_loss)
            profitable_trade_counts.append(profitable_trades)
            losing_trade_counts.append(losing_trades)

            # 2. ve 3. grafikler için verileri 1. grafiğin legend'ına ekle
            ax1.plot([], [], marker='o', markersize=5, linewidth=2,
                     label=f"{strategy['name']} Kapital: {capital_history[-1]:.2f}, "
                           f"Kârlı İşlem: {profitable_trade_counts[-1]}, Zararlı İşlem: {losing_trade_counts[-1]}",
                     color=colors[strategies.index(strategy)])

            ax1.plot([], [], marker='o', markersize=5, linewidth=2,
                     label=f"{strategy['name']} Kümülatif Kâr/Zarar: {total_profit_loss:.2f} %",
                     color=colors[strategies.index(strategy)])

        # Başlangıç kapitali
        ax1.axhline(initial_capital, color='black', linestyle='--', label='Başlangıç Kapitali')

        # 2. Grafik: Kapital durumu
        ax2 = fig.add_subplot(gs[1, 0])
        ax2.set_xlabel('İşlem Sayısı')
        ax2.set_ylabel('Kapital Durumu (TL)')
        for idx, capital_history in enumerate(capital_histories):
            ax2.plot(capital_history, marker='o', markersize=5, linewidth=2,
                     color=colors[idx % len(colors)])
        ax2.axhline(initial_capital, color='black', linestyle='--')

        # 3. Grafik: Kümülatif Kâr/Zarar
        ax3 = fig.add_subplot(gs[1, 1])
        ax3.set_xlabel('İşlem Sayısı')
        ax3.set_ylabel('Kümülatif Kâr/Zarar (%)')
        for idx, cumulative_profit_loss in enumerate(cumulative_profit_losses):
            ax3.plot(cumulative_profit_loss, marker='o', markersize=5, linewidth=2,
                     color=colors[idx % len(colors)])
        ax3.axhline(0, color='black', linestyle='--')

        # Legend sadece 1. grafikte gösterilecek
        ax1.legend(loc='upper left')

        plt.tight_layout()
        plt.show()


Backtest.Test(True)