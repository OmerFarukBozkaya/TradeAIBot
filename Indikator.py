import numpy as np
import pandas as pd
class Indikator:
    @staticmethod
    def EMA(src, length):
        alpha = 2 / (length + 1)
        ema_list = [src[0]]  # İlk değeri doğrudan başlangıç olarak kullanıyoruz
        for val in src[1:]:
            ema_list.append(alpha * val + (1 - alpha) * ema_list[-1])
        return ema_list

    @staticmethod
    def SMA(src, length):
        if len(src) < length:
            return None
        return np.mean(src[-length:])  # Daha hızlı ve basit

    @staticmethod
    def BB(src, length=20):  # OK
        # Hareketli ortalama hesaplaması
        rolling_mean = np.convolve(src, np.ones(length) / length, mode='valid')

        # Hareketli ortalama etrafındaki standart sapmayı hesapla
        rolling_std = np.std([src[i:i + length] for i in range(len(src) - length + 1)], axis=1)

        # Üst ve alt bantları hesapla
        upper_band = rolling_mean + 2 * rolling_std
        lower_band = rolling_mean - 2 * rolling_std

        return lower_band, rolling_mean, upper_band

    @staticmethod
    def RSI(src, length=14):
        deltas = np.diff(src)
        seed = deltas[:length]
        up = np.where(seed >= 0, seed, 0).sum() / length
        down = -np.where(seed < 0, seed, 0).sum() / length
        rs = up / down
        rsi = np.zeros_like(src)
        rsi[:src] = 100.0 - (100.0 / (1.0 + rs))

        for i in range(length, len(src)):
            delta = deltas[i - 1]
            upval = max(delta, 0)
            downval = -min(delta, 0)

            up = (up * (length - 1) + upval) / length
            down = (down * (length - 1) + downval) / length
            rs = up / down
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))

        return rsi

    @staticmethod
    def PIVOT(high, low, close):
        pivot_point = (high + low + close) / 3
        support_1 = (2 * pivot_point) - high
        support_2 = pivot_point - (high - low)
        resistance_1 = (2 * pivot_point) - low
        resistance_2 = pivot_point + (high - low)

        return pivot_point, support_1, support_2, resistance_1, resistance_2

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
