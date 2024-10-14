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
        results = []

        # İlk 143 mum için None ekleyin
        for i in range(143):
            results.append([None] * len(fibonacci_levels))  # None olan seviyeler

        # 144. mumdan itibaren hesaplama yap
        for i in range(143, len(src)):
            prices = src[i - 143:i + 1]  # Son 144 mumun fiyatlarını al
            start_price = min(prices)
            end_price = max(prices)
            price_range = end_price - start_price

            # Fibonacci değerlerini hesapla
            fibonacci_values = [start_price + level * price_range for level in fibonacci_levels]
            results.append(fibonacci_values)  # Hesaplanan değerleri ekle

        return results

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
                tenkan_sen = (max(high[i - 8:i + 1]) + min(low[i - 8:i + 1])) / 2
            else:
                tenkan_sen = np.nan  # Yeterli veri yoksa NaN
            tenkan_sen_list.append(tenkan_sen)

            if i >= 25:  # Kijun Sen için yeterli veri var mı (26 periyot)
                kijun_sen = (max(high[i - 25:i + 1]) + min(low[i - 25:i + 1])) / 2
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
                senkou_span_b = (max(high[i - 51:i + 1]) + min(low[i - 51:i + 1])) / 2
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
                upper_band = max(high[i - length + 1:i + 1])
                lower_band = min(low[i - length + 1:i + 1])
            else:
                upper_band = np.nan
                lower_band = np.nan
            upper_band_list.append(upper_band)
            lower_band_list.append(lower_band)

        return upper_band_list, lower_band_list