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

        sma_list = []
        for i in range(len(src)):
            if i + 1 < length:
                # Eğer pencere boyutuna ulaşmadıysa None ekleyelim
                sma_list.append(None)
            else:
                # Pencereye uygun olan kısım için ortalama alalım
                sma_list.append(np.mean(src[i + 1 - length:i + 1]))

        return sma_list

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
        rsi[:length] = 100.0 - (100.0 / (1.0 + rs))

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

    @staticmethod
    def Momentum(src, length=10):
        momentum = np.zeros(len(src))
        for i in range(length, len(src)):
            momentum[i] = src[i] - src[i - length]
        return momentum

    @staticmethod
    def Stochastic_RSI(src, length=14):
        rsi = Indikator.RSI(src, length)
        stoch_rsi = np.zeros(len(rsi))
        for i in range(length, len(rsi)):
            rsi_window = rsi[i - length:i]
            stoch_rsi[i] = (rsi[i] - np.min(rsi_window)) / (np.max(rsi_window) - np.min(rsi_window))
        return stoch_rsi

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

        # True Range (TR) hesaplama
        tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))

        # Plus DM ve Minus DM hesaplama
        up = np.maximum(high[1:] - high[:-1], 0)
        down = np.maximum(low[:-1] - low[1:], 0)

        plus_dm = np.zeros(len(high))
        minus_dm = np.zeros(len(low))

        for i in range(1, len(high)):
            plus_dm[i] = up[i - 1] if (up[i - 1] > down[i - 1] and up[i - 1] > 0) else 0
            minus_dm[i] = down[i - 1] if (down[i - 1] > up[i - 1] and down[i - 1] > 0) else 0

        # ATR hesaplama
        tr_smooth = np.zeros_like(close)
        tr_smooth[dilen - 1] = np.nanmean(tr[:dilen])

        for i in range(dilen, len(tr)):
            tr_smooth[i] = (tr_smooth[i - 1] * (dilen - 1) + tr[i]) / dilen

        # Plus ve Minus hesaplama
        plus = np.zeros_like(close)
        minus = np.zeros_like(close)

        for i in range(dilen - 1, len(plus)):
            if i >= dilen - 1:
                plus[i] = 100 * np.nanmean(plus_dm[i - dilen + 1:i + 1]) / (tr_smooth[i] if tr_smooth[i] != 0 else 1)
                minus[i] = 100 * np.nanmean(minus_dm[i - dilen + 1:i + 1]) / (tr_smooth[i] if tr_smooth[i] != 0 else 1)

        # ADX Hesaplama
        dx = 100 * np.abs(plus - minus) / np.maximum(1e-10, (plus + minus))  # Sıfıra bölmeyi önlemek için
        adx = np.zeros(len(dx))
        adx[adxlen - 1] = np.nanmean(dx[:adxlen])

        for i in range(adxlen, len(dx)):
            adx[i] = (adx[i - 1] * (adxlen - 1) + dx[i]) / adxlen

        return adx
