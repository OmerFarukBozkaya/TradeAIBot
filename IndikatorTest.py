import numpy as np
import pandas as pd
from Indikator import Indikator
class IndikatorTest:
    @staticmethod
    def IndikatorResultTest(canli_veriler):
        test_indikator = IndikatorTest()
        indikator = Indikator()
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

        print(f"EMA: {indikator.EMA(close, 17)[-1] == test_indikator.EMA(close, 17)[-1]}")
        print(f"SMA: {indikator.SMA(close, 17)[-1] == test_indikator.SMA(close, 17)[-1]}")
        print(f"BB (low): {indikator.BB(close)[0][-1] == test_indikator.BB(close)[0][-1]}")
        print(f"BB (mid): {indikator.BB(close)[1][-1] == test_indikator.BB(close)[1][-1]}")
        print(f"BB (up): {indikator.BB(close)[2][-1] == test_indikator.BB(close)[2][-1]}")
        print(f"RSI: {indikator.RSI(close)[-1] == test_indikator.RSI(close)[-1]}")
        print(f"FIB: {indikator.FIB(close)[-1] == test_indikator.FIB(close)[-1]}")
        print(f"MACD: {indikator.MACD(close)[-1] == test_indikator.MACD(close)[-1]}")
        print(f"Momentum: {indikator.Momentum(close)[-1] == test_indikator.Momentum(close)[-1]}")
        print(f"ATR: {indikator.ATR(high, low, close)[-1] == test_indikator.ATR(high, low, close)[-1]}")
        print(f"ADX: {indikator.ADX(high, low, close)[-1] == test_indikator.ADX(high, low, close)[-1]}")
        print(
            f"Ichimoku: {indikator.Ichimoku_Bulutu(high, low)[0][-1] == test_indikator.Ichimoku_Bulutu(high, low)[0][-1]}")
        print(
            f"Donchain: {indikator.Donchian_Kanali(high, low)[0][-1] == test_indikator.Donchian_Kanali(high, low)[0][-1]}")
    @staticmethod
    def EMA(src, length):
        alpha = 2 / (length + 1)
        ema = [src[0]]  # İlk değeri doğrudan kullanıyoruz
        for i in range(1, len(src)):
            ema.append(alpha * src[i] + (1 - alpha) * ema[-1])
        return ema
    @staticmethod
    def SMA(src, length):
        sma_list = []
        for i in range(len(src)):
            if i + 1 < length:
                sma_list.append(None)  # Yeterli pencere yoksa None ekleniyor
            else:
                sma_list.append(np.mean(src[i + 1 - length:i + 1]))
        return sma_list
    @staticmethod
    def BB(src, length=20):
        rolling_mean = np.convolve(src, np.ones(length) / length, mode='valid')
        rolling_std = np.array([np.std(src[i:i + length]) for i in range(len(src) - length + 1)])
        upper_band = rolling_mean + 2 * rolling_std
        lower_band = rolling_mean - 2 * rolling_std

        # None ile başlangıcı doldurma
        lower_band = np.concatenate([np.full(length - 1, None), lower_band])
        rolling_mean = np.concatenate([np.full(length - 1, None), rolling_mean])
        upper_band = np.concatenate([np.full(length - 1, None), upper_band])

        return lower_band, rolling_mean, upper_band
    @staticmethod
    def RSI(src, length=14):
        deltas = np.diff(src)
        seed = deltas[:length]
        up = np.where(seed >= 0, seed, 0).sum() / length
        down = -np.where(seed < 0, seed, 0).sum() / length
        rs = up / down if down != 0 else 0
        rsi = np.zeros_like(src)
        rsi[:length] = 100.0 - (100.0 / (1.0 + rs))

        for i in range(length, len(src)):
            delta = deltas[i - 1]
            upval = max(delta, 0)
            downval = -min(delta, 0)

            up = (up * (length - 1) + upval) / length
            down = (down * (length - 1) + downval) / length
            rs = up / down if down != 0 else 0
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))

        return rsi
    @staticmethod
    def FIB(src):
        fibonacci_levels = [0, 0.236, 0.382, 0.5, 0.618, 1.0]
        prices = src[-144:]
        start_price = min(prices)
        end_price = max(prices)
        price_range = end_price - start_price
        fibonacci_values = [start_price + level * price_range for level in fibonacci_levels]

        return fibonacci_values
    @staticmethod
    def MACD(src, fast_length=12, slow_length=26, signal_length=9, sma_source="EMA", sma_signal="EMA"):
        close_series = pd.Series(src)
        if sma_source == "SMA":
            fast_ma = close_series.rolling(fast_length).mean()
            slow_ma = close_series.rolling(slow_length).mean()
        else:
            fast_ma = close_series.ewm(span=fast_length).mean()
            slow_ma = close_series.ewm(span=slow_length).mean()
        macd = fast_ma - slow_ma
        if sma_signal == "SMA":
            signal = macd.rolling(signal_length).mean()
        else:
            signal = macd.ewm(span=signal_length).mean()
        return macd.tolist(), signal.tolist()
    @staticmethod
    def Momentum(src, length=10):
        momentum = np.zeros(len(src))
        for i in range(length, len(src)):
            momentum[i] = src[i] - src[i - length]
        return momentum
    @staticmethod
    def ATR(high, low, close, length=14):
        high = np.array(high)
        low = np.array(low)
        close = np.array(close)

        previous_close = np.roll(close, 1)
        previous_close[0] = np.nan

        tr = np.maximum(high - low, np.maximum(abs(high - previous_close), abs(low - previous_close)))

        atr = np.zeros_like(close)
        atr[length - 1] = np.nanmean(tr[:length])

        for i in range(length, len(close)):
            atr[i] = (atr[i - 1] * (length - 1) + tr[i]) / length

        return atr
    @staticmethod
    def ADX(high, low, close, adxlen=14, dilen=14):
        high = np.array(high)
        low = np.array(low)
        close = np.array(close)

        tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))

        up = np.maximum(high[1:] - high[:-1], 0)
        down = np.maximum(low[:-1] - low[1:], 0)

        plus_dm = np.zeros(len(high))
        minus_dm = np.zeros(len(low))

        for i in range(1, len(high)):
            plus_dm[i] = up[i - 1] if (up[i - 1] > down[i - 1] and up[i - 1] > 0) else 0
            minus_dm[i] = down[i - 1] if (down[i - 1] > up[i - 1] and down[i - 1] > 0) else 0

        tr_smooth = np.zeros_like(close)
        tr_smooth[dilen - 1] = np.nanmean(tr[:dilen])

        for i in range(dilen, len(tr)):
            tr_smooth[i] = (tr_smooth[i - 1] * (dilen - 1) + tr[i]) / dilen

        plus = np.zeros_like(close)
        minus = np.zeros_like(close)

        for i in range(dilen - 1, len(plus)):
            if i >= dilen - 1:
                plus[i] = 100 * np.nanmean(plus_dm[i - dilen + 1:i + 1]) / (tr_smooth[i] if tr_smooth[i] != 0 else 1)
                minus[i] = 100 * np.nanmean(minus_dm[i - dilen + 1:i + 1]) / (tr_smooth[i] if tr_smooth[i] != 0 else 1)

        dx = 100 * np.abs(plus - minus) / np.maximum(1e-10, (plus + minus))
        adx = np.zeros(len(dx))
        adx[adxlen - 1] = np.nanmean(dx[:adxlen])

        for i in range(adxlen, len(dx)):
            adx[i] = (adx[i - 1] * (adxlen - 1) + dx[i]) / adxlen

        return adx
    @staticmethod
    def Ichimoku_Bulutu(high, low):
        """
        Ichimoku Bulutu indikatörünün bileşenlerini liste olarak hesaplar.

        :param high: En yüksek fiyatların listesi
        :param low: En düşük fiyatların listesi
        :return: Tenkan Sen, Kijun Sen, Senkou Span A, Senkou Span B listeleri
        """
        tenkan_sen_list = []
        kijun_sen_list = []
        senkou_span_a_list = []
        senkou_span_b_list = []

        for i in range(len(high)):
            if i >= 8:  # Tenkan Sen için yeterli veri var mı (9 periyot)
                tenkan_sen = (max(high[i-8:i+1]) + min(low[i-8:i+1])) / 2
            else:
                tenkan_sen = np.nan  # Yeterli veri yoksa NaN
            tenkan_sen_list.append(tenkan_sen)

            if i >= 25:  # Kijun Sen için yeterli veri var mı (26 periyot)
                kijun_sen = (max(high[i-25:i+1]) + min(low[i-25:i+1])) / 2
            else:
                kijun_sen = np.nan
            kijun_sen_list.append(kijun_sen)

            # Senkou Span A, sadece Tenkan ve Kijun hesaplandıktan sonra anlamlıdır
            if i >= 25:
                senkou_span_a = (tenkan_sen_list[i] + kijun_sen_list[i]) / 2
            else:
                senkou_span_a = np.nan
            senkou_span_a_list.append(senkou_span_a)

            # Senkou Span B, 52 periyot için yeterli veri olmalı
            if i >= 51:
                senkou_span_b = (max(high[i-51:i+1]) + min(low[i-51:i+1])) / 2
            else:
                senkou_span_b = np.nan
            senkou_span_b_list.append(senkou_span_b)

        return tenkan_sen_list, kijun_sen_list, senkou_span_a_list, senkou_span_b_list
    @staticmethod
    def Donchian_Kanali(high, low, length=20):
        """
        Donchian Kanalı indikatörünü liste olarak hesaplar.

        :param high: En yüksek fiyatların listesi
        :param low: En düşük fiyatların listesi
        :param length: Donchian kanalının hesaplanacağı periyot (varsayılan: 20)
        :return: Üst bant ve Alt bant listeleri
        """
        upper_band_list = []
        lower_band_list = []

        for i in range(len(high)):
            if i >= length - 1:  # Yeterli veri var mı (length periyot)
                upper_band = max(high[i-length+1:i+1])
                lower_band = min(low[i-length+1:i+1])
            else:
                upper_band = np.nan
                lower_band = np.nan
            upper_band_list.append(upper_band)
            lower_band_list.append(lower_band)

        return upper_band_list, lower_band_list

    @staticmethod
    def calculate_pmai(price_list, period=14):
        """
        PMAI (Price Momentum Acceleration Index) hesaplar.

        Args:
            price_list (list): Fiyat verilerinin listesi.
            period (int): Momentum ve ivme hesaplamaları için kullanılan dönem sayısı.

        Returns:
            list: PMAI değerlerinin listesi.
        """
        # Momentum hesapla
        momentum = IndikatorTest.Momentum(price_list, period)

        # Momentum değişim hızı hesapla (Acceleration)
        acceleration = []
        for i in range(period + 1, len(momentum)):
            acc = (momentum[i] - momentum[i - 1]) / 1  # Zaman 1 olarak kabul edilir
            acceleration.append(acc)

        # İlk `period+1` değerini NaN ile doldur
        acceleration = [np.nan] * (period + 1) + acceleration

        # PMAI hesapla (Acceleration değerlerini normalize ederek)
        pmai = []
        for i in range(len(acceleration)):
            if np.isnan(acceleration[i]):
                pmai.append(np.nan)
            else:
                # PMAI değerini normalize et ve %0-%100 aralığına getir
                normalized_pmai = 100 * (acceleration[i] / max(acceleration[period + 1:], default=1))
                pmai.append(normalized_pmai)

        return pmai

    @staticmethod
    def calculate_momentum(price_list, period=14):
        momentum = []
        for i in range(period, len(price_list)):
            mom = price_list[i] - price_list[i - period]
            momentum.append(mom)
        return [np.nan] * period + momentum

    @staticmethod
    def PMAI(src, length=14):
        """
        PMAI (Price Momentum Acceleration Index) hesaplar.
        """
        # Momentum hesapla
        momentum = IndikatorTest.calculate_momentum(src, length)

        # Momentum değişim hızı hesapla (Acceleration)
        acceleration = []
        for i in range(length + 1, len(momentum)):
            acc = momentum[i] - momentum[i - 1]  # Zaman 1 olarak kabul edilir
            # Negatif ivmeleri sıfıra ayarla
            acceleration.append(max(0, acc))  # Negatif ivmeleri sıfıra ayarla

        # İlk `length + 1` değerini NaN ile doldur
        acceleration = [np.nan] * (length + 1) + acceleration

        # PMAI hesapla (Acceleration değerlerini normalize ederek)
        pmai = []
        max_acceleration = max(acceleration[length + 1:], default=0)

        for i in range(len(acceleration)):
            if np.isnan(acceleration[i]):
                pmai.append(np.nan)
            else:
                # Normalizasyon
                if max_acceleration > 0:  # Sıfırdan büyükse normalize et
                    normalized_pmai = 100 * (acceleration[i] / max_acceleration)
                else:
                    normalized_pmai = 0  # Tüm ivmeler sıfırsa PMAI'yı sıfır yap

                pmai.append(normalized_pmai)

        return pmai