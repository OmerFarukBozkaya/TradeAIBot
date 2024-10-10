from IndikatorTest import IndikatorTest
import matplotlib.pyplot as plt
import numpy as np
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

        pmai_values = IndikatorTest.PMAI(close)
        pmai_sma = IndikatorTest.SMA(pmai_values, 14)
        rsi_values = IndikatorTest.RSI(close)
        adx = IndikatorTest.ADX(high, low, close)

        # Grafik çizimi
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(20, 15))

        # 1. Grafik: Fiyat, Alım-Satım sinyalleri
        ax1.set_xlabel('Zaman (Periyotlar)')
        ax1.set_ylabel('Fiyat', color='blue')
        ax1.plot(close, color='blue', label='Fiyat', linewidth=1.5)
        ax1.tick_params(axis='y', labelcolor='blue')
        ax1.set_xticks(np.arange(0, len(close), step=50))

        last_signal = None  # Son sinyalin durumu
        buy_price = None  # Alım yapılan fiyat
        cumulative_profit_loss = []  # Kümülatif kâr/zarar yüzdesi
        total_profit_loss = 0  # Toplam kâr/zarar
        profitable_trades = 0  # Kârlı işlem sayısı
        losing_trades = 0  # Zararlı işlem sayısı

        for i in range(len(pmai_values)):
            if pmai_values[i] is not None and pmai_sma[i] is not None and rsi_values[i] is not None:
                if last_signal is None or last_signal == 'red':
                    if pmai_values[i] > pmai_sma[i] * 1.1 and rsi_values[i] > 50 and (adx[i] > 25):
                        ax1.scatter(i, close[i], color='green', s=50, label='Alım Sinyali', alpha=0.5)
                        last_signal = 'green'
                        buy_price = close[i]

                elif last_signal == 'green':
                    if pmai_values[i] < 30:
                        ax1.scatter(i, close[i], color='red', s=50, label='Satım Sinyali', alpha=0.5)
                        last_signal = 'red'

                        if buy_price is not None:
                            profit = ((close[i] - buy_price) / buy_price) * 100
                            cumulative_profit_loss.append(profit)
                            total_profit_loss += profit

                            # Kârlı mı zararlı mı kontrol et
                            if profit > 0:
                                profitable_trades += 1
                            else:
                                losing_trades += 1

                            buy_price = None

        # 2. Grafik: Kâr/Zarar yüzdesi grafiği
        ax2.set_xlabel('İşlem Sayısı')
        ax2.set_ylabel('Kümülatif Kâr/Zarar (%)')

        # Kâr/Zarar noktaları
        profit_loss_points = [0]  # İlk başlangıçta 0
        for profit in cumulative_profit_loss:
            profit_loss_points.append(profit_loss_points[-1] + profit)

        # Noktaları çiz
        ax2.plot(range(len(cumulative_profit_loss)), cumulative_profit_loss, marker='o', color='orange', markersize=5,
                 linewidth=2, label='Kümülatif Kâr/Zarar')
        ax2.axhline(0, color='black', linestyle='--')

        # Legend ekle
        ax2.legend([f"Toplam Kârlı İşlem: {profitable_trades}\n"
                    f"Toplam Zararlı İşlem: {losing_trades}\n"
                    f"Genel Durum: {total_profit_loss:.2f}%"], loc='upper left')

        plt.tight_layout()
        plt.show()

Backtest.Test(True)