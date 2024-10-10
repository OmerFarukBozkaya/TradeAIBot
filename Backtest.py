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
            periyot = "1h"
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

        # Grafik düzeni ayarlama
        fig = plt.figure(figsize=(16, 16))  # Daha küçük genel figür boyutu
        gs = gridspec.GridSpec(2, 2, height_ratios=[2, 1])  # Yükseklik oranı değiştirildi (ilk grafik daha küçük)

        # 1. Grafik: Fiyat, Alım-Satım sinyalleri (En üstte)
        ax1 = fig.add_subplot(gs[0, :])
        ax1.set_xlabel('Zaman (Periyotlar)')
        ax1.set_ylabel('Fiyat', color='blue')
        ax1.plot(close, color='blue', label='Fiyat', linewidth=1.5)
        ax1.tick_params(axis='y', labelcolor='blue')
        ax1.set_xticks(np.arange(0, len(close), step=50))

        # Detay için Y ekseni ayarı
        ax1.set_ylim(min(close) * 0.95, max(close) * 1.05)
        ax1.yaxis.set_major_locator(plt.MaxNLocator(10))

        last_signal = None  # Son sinyalin durumu
        buy_price = None  # Alım yapılan fiyat
        cumulative_profit_loss = []  # Kümülatif kâr/zarar yüzdesi
        total_profit_loss = 0  # Toplam kâr/zarar
        profitable_trades = 0  # Kârlı işlem sayısı
        losing_trades = 0  # Zararlı işlem sayısı

        # Başlangıçta sahip olunan para
        initial_capital = 100  # 100 TL ile başla
        current_capital = initial_capital  # Şu anki para miktarı
        capital_history = [initial_capital]  # Para geçmişini tut

        for i in range(len(pmai_values)):
            if pmai_values[i] is not None and pmai_sma[i] is not None and rsi_values[i] is not None and adx[i] is not None and macd_values[i] is not None:
                if last_signal is None or last_signal == 'red':
                    if pmai_values[i] > pmai_sma[i]*1.2 and rsi_values[i] > 50 and (adx[i] > 25):
                        ax1.scatter(i, close[i], color='green', s=50, label='Alım Sinyali', alpha=0.5)
                        last_signal = 'green'
                        buy_price = close[i]
                        # Alım işlemi
                        amount_purchased = current_capital / buy_price  # Alım yapılan miktar
                        current_capital = 0  # Alım sonrasında nakit sıfırlanır

                elif last_signal == 'green':
                    if pmai_values[i] < 30 and macd_values[i]<macd_signal[i]:
                        ax1.scatter(i, close[i], color='red', s=50, label='Satım Sinyali', alpha=0.5)
                        last_signal = 'red'

                        if buy_price is not None:
                            # Satış işlemi sonrası kâr/zarar yüzdesini hesapla
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
                            current_capital = amount_purchased * sell_price  # Satıştan sonra nakit
                            capital_history.append(current_capital)  # Para geçmişine ekle

                            buy_price = None

        # 2. Grafik: Kapital durumu (Sol alt)
        ax2 = fig.add_subplot(gs[1, 0])
        ax2.set_xlabel('İşlem Sayısı')
        ax2.set_ylabel('Kapital Durumu (TL)')

        # Para geçmişini çiz
        ax2.plot(capital_history, marker='o', color='orange', markersize=5, linewidth=2, label='Kapital Durumu')
        ax2.axhline(initial_capital, color='black', linestyle='--', label='Başlangıç Kapitali')

        # Detaylı Y ekseni için ayar
        ax2.set_ylim(min(capital_history) * 0.95, max(capital_history) * 1.05)
        ax2.yaxis.set_major_locator(plt.MaxNLocator(8))

        # 3. Grafik: Kümülatif Kâr/Zarar (Sağ alt)
        ax3 = fig.add_subplot(gs[1, 1])
        ax3.set_xlabel('İşlem Sayısı')
        ax3.set_ylabel('Kümülatif Kâr/Zarar (%)')

        ax3.plot(cumulative_profit_loss, marker='o', color='green', markersize=5, linewidth=2,
                 label='Kümülatif Kâr/Zarar')
        ax3.axhline(0, color='black', linestyle='--', label='Kar/Zarar')

        # Y eksenindeki aralığı detaylandır
        ax3.set_ylim(min(cumulative_profit_loss) * 1.1, max(cumulative_profit_loss) * 1.1)
        ax3.yaxis.set_major_locator(plt.MaxNLocator(8))

        # Legend ekle
        ax2.legend([f"Toplam Kârlı İşlem: {profitable_trades}\n"
                    f"Toplam Zararlı İşlem: {losing_trades}\n"
                    f"Genel Durum: {total_profit_loss:.2f}%\n"
                    f"Son Kapital: {current_capital:.2f} TL"], loc='upper left')

        ax3.legend([f"Kümülatif Kâr/Zarar: {total_profit_loss:.2f}%"], loc='upper left')

        plt.tight_layout()
        plt.show()

Backtest.Test(True)