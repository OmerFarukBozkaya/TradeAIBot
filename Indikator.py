import numpy as np
import pandas as pd
class Indikator:
    @staticmethod
    def EMA(src, length):
        if len(src) < length:
            return [None] * len(src)
        alpha = 2 / (length + 1)
        ema_list = [src[0]]  # İlk değeri doğrudan başlangıç olarak kullanıyoruz
        for val in src[1:]:
            ema_list.append(alpha * val + (1 - alpha) * ema_list[-1])
        return ema_list

    @staticmethod
    def SMA(src, length):
        if len(src) < length:
            return [None] * len(src)

        sma_list = [None] * (length - 1)  # İlk length-1 değeri None
        for i in range(length - 1, len(src)):
            sma_list.append(np.mean(src[i + 1 - length:i + 1]))
        return sma_list

    @staticmethod
    def BB(src, length=20):
        # Eğer yeterli veri yoksa None döndür
        if len(src) < length:
            return [None] * len(src), [None] * len(src), [None] * len(src)

        # Hareketli ortalama (Rolling Mean) hesapla
        rolling_mean = np.convolve(src, np.ones(length) / length, mode='valid')

        # Hareketli standart sapma (Rolling Std) hesapla
        rolling_std = np.array([np.std(src[i:i + length]) for i in range(len(src) - length + 1)])

        # Üst ve alt bandı hesapla
        upper_band = rolling_mean + 2 * rolling_std
        lower_band = rolling_mean - 2 * rolling_std

        # Sonuçların başlangıcına None ekleyerek uzunluğu eşitle
        lower_band = np.concatenate([np.full(length - 1, None), lower_band])
        rolling_mean = np.concatenate([np.full(length - 1, None), rolling_mean])
        upper_band = np.concatenate([np.full(length - 1, None), upper_band])

        # Eğer çıktı uzunluğunda eksik veri varsa None ile doldur
        if len(lower_band) < len(src):
            lower_band = np.concatenate([lower_band, np.full(len(src) - len(lower_band), None)])
            rolling_mean = np.concatenate([rolling_mean, np.full(len(src) - len(rolling_mean), None)])
            upper_band = np.concatenate([upper_band, np.full(len(src) - len(upper_band), None)])

        return lower_band.tolist(), rolling_mean.tolist(), upper_band.tolist()

    @staticmethod
    def RSI(src, length=14):
        if len(src) < length:
            return [None] * len(src)

        deltas = np.diff(src)  # Fiyat değişimlerini hesapla
        seed = deltas[:length]  # İlk length kadar veriyi kullanarak başlangıç değerleri al
        up = np.where(seed >= 0, seed, 0).sum() / length  # Pozitif değişimlerin ortalaması
        down = -np.where(seed < 0, seed, 0).sum() / length  # Negatif değişimlerin ortalaması

        rs = up / down if down != 0 else float('inf')  # İlk RS (relative strength) değeri
        rsi = np.zeros_like(src)  # RSI sonuç dizisi
        rsi[:length] = 100.0 - (100.0 / (1.0 + rs))  # İlk RSI değerini hesapla

        for i in range(length, len(src)):
            delta = deltas[i - 1]
            upval = max(delta, 0)  # Eğer değişim pozitifse
            downval = -min(delta, 0)  # Eğer değişim negatifse

            # Hareketli ortalamaları güncelle
            up = (up * (length - 1) + upval) / length
            down = (down * (length - 1) + downval) / length

            # RS değeri sıfıra bölünmekten kaçınarak güncellenir
            if down == 0:
                rs = float('inf')  # Fiyat yalnızca artmışsa, RS sonsuz olur
                rsi[i] = 100.0  # RSI değeri 100 olarak atanır
            elif up == 0:
                rs = 0  # Fiyat yalnızca düşmüşse, RS sıfır olur
                rsi[i] = 0.0  # RSI değeri 0 olarak atanır
            else:
                rs = up / down
                rsi[i] = 100.0 - (100.0 / (1.0 + rs))

        return rsi.tolist()
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
        if len(src) < 144:
            return [[None] * 6] * len(src)  # İlk 144 veri yoksa None ile doldur

        fibonacci_levels = [0, 0.236, 0.382, 0.5, 0.618, 1.0]
        results = [[None] * len(fibonacci_levels)] * 143  # İlk 143 mum için None ekleyin

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
        if len(src) < slow_length:
            return [None] * len(src), [None] * len(src)

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
        if len(src) < length:
            return [None] * len(src)

        momentum = np.zeros(len(src))
        for i in range(length, len(src)):
            momentum[i] = src[i] - src[i - length]
        return momentum.tolist()

    @staticmethod
    def ATR(high, low, close, length=14):
        # Yeterli veri yoksa None döndür
        if len(close) < length:
            return [None] * len(close)

        high = np.array(high, dtype=float)
        low = np.array(low, dtype=float)
        close = np.array(close, dtype=float)

        # Önceki kapanış değerlerini kaydırarak elde et
        previous_close = np.roll(close, 1)
        previous_close[0] = np.nan

        # True Range hesapla, ilk length kadar değer None olacak
        tr = np.maximum(high - low, np.maximum(np.abs(high - previous_close), np.abs(low - previous_close)))

        # ATR dizisini None ile başlat ve hesaplamalar sonrası doldur
        atr = [None] * (length - 1)  # İlk length - 1 kadarını None olarak bırak
        initial_tr_mean = np.nanmean(tr[:length])  # İlk ATR değerini hesapla
        atr.append(initial_tr_mean)

        # ATR değerlerini hesapla
        for i in range(length, len(close)):
            atr_value = (atr[i - 1] * (length - 1) + tr[i]) / length if atr[i - 1] is not None else None
            atr.append(atr_value)

        return atr
    @staticmethod
    def ADX(high, low, close, adxlen=14, dilen=14):
        # Yeterli veri kontrolü
        if len(close) < dilen:
            return [None] * len(close)

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
        tr_smooth = np.full(len(close), np.nan)  # 'None' yerine 'np.nan' kullanılması daha uygun
        tr_smooth[dilen - 1] = np.nanmean(tr[:dilen])

        for i in range(dilen, len(tr)):
            tr_smooth[i] = (tr_smooth[i - 1] * (dilen - 1) + tr[i]) / dilen

        # Plus ve Minus hesaplama
        plus = np.zeros(len(close))  # None yerine sıfır kullanıyoruz
        minus = np.zeros(len(close))  # None yerine sıfır kullanıyoruz

        for i in range(dilen - 1, len(plus)):
            plus[i] = 100 * np.nanmean(plus_dm[i - dilen + 1:i + 1]) / (tr_smooth[i] if tr_smooth[i] != 0 else 1)
            minus[i] = 100 * np.nanmean(minus_dm[i - dilen + 1:i + 1]) / (tr_smooth[i] if tr_smooth[i] != 0 else 1)

        # ADX hesaplama
        dx = 100 * np.abs(plus - minus) / np.maximum(1e-10, (plus + minus))
        adx = [None] * (adxlen - 1)  # Başlangıçta None eklenebilir
        adx.append(np.nanmean(dx[:adxlen]))  # İlk ADX değeri hesaplama

        for i in range(adxlen, len(dx)):
            adx.append((adx[i - 1] * (adxlen - 1) + dx[i]) / adxlen)

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
            # Tenkan Sen (9 periyot)
            if i >= 8:  # Yeterli veri var mı (9 periyot)
                tenkan_sen = (max(high[i - 8:i + 1]) + min(low[i - 8:i + 1])) / 2
            else:
                tenkan_sen = None  # Yeterli veri yoksa None
            tenkan_sen_list.append(tenkan_sen)

            # Kijun Sen (26 periyot)
            if i >= 25:  # Yeterli veri var mı (26 periyot)
                kijun_sen = (max(high[i - 25:i + 1]) + min(low[i - 25:i + 1])) / 2
            else:
                kijun_sen = None  # Yeterli veri yoksa None
            kijun_sen_list.append(kijun_sen)

            # Senkou Span A (Tenkan Sen ve Kijun Sen'in ortalaması, 26. periyot sonrası)
            if i >= 25:
                if tenkan_sen is not None and kijun_sen is not None:
                    senkou_span_a = (tenkan_sen + kijun_sen) / 2
                else:
                    senkou_span_a = None  # Eğer Tenkan Sen veya Kijun Sen None ise Senkou Span A da None olmalı
            else:
                senkou_span_a = None  # Yeterli veri yoksa None
            senkou_span_a_list.append(senkou_span_a)

            # Senkou Span B (52 periyot)
            if i >= 51:  # Yeterli veri var mı (52 periyot)
                senkou_span_b = (max(high[i - 51:i + 1]) + min(low[i - 51:i + 1])) / 2
            else:
                senkou_span_b = None  # Yeterli veri yoksa None
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
                upper_band = None  # Yeterli veri yoksa None
                lower_band = None  # Yeterli veri yoksa None

            upper_band_list.append(upper_band)
            lower_band_list.append(lower_band)

        return upper_band_list, lower_band_list
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
        momentum = Indikator.calculate_momentum(src, length)

        # Momentum değişim hızı hesapla (Acceleration)
        acceleration = []
        for i in range(length + 1, len(momentum)):
            acc = momentum[i] - momentum[i - 1]  # Zaman 1 olarak kabul edilir
            # Negatif ivmeleri sıfıra ayarla
            acceleration.append(max(0, acc))  # Negatif ivmeleri sıfıra ayarla

        # İlk `length + 1` değerini None ile doldur
        acceleration = [None] * (length + 1) + acceleration

        # PMAI hesapla (Acceleration değerlerini normalize ederek)
        pmai = []
        max_acceleration = max(acceleration[length + 1:], default=0)

        for i in range(len(acceleration)):
            if acceleration[i] is None:
                pmai.append(None)  # None değerlerini None olarak bırak
            else:
                # Normalizasyon
                if max_acceleration > 0:  # Sıfırdan büyükse normalize et
                    normalized_pmai = 100 * (acceleration[i] / max_acceleration)
                else:
                    normalized_pmai = 0  # Tüm ivmeler sıfırsa PMAI'yı sıfır yap
                pmai.append(normalized_pmai)

        return pmai
    @staticmethod
    def Max_Last(src, length=20):
        # Sonuçları saklamak için bir liste oluştur
        max_values = []
        # İlk 19 değer için sonuç eklemeyeceğiz (çünkü 20 mum eksik)
        for i in range(len(src)):
            if i < length - 1:
                max_values.append(None)  # İlk 19 adım için sonuç eklenmez
            else:
                # Son 20 mumun maksimumunu al
                max_in_window = max(src[i - (length - 1):i + 1])
                max_values.append(max_in_window)
        return max_values

    @staticmethod
    def CMI(close, high, low):
        # Trend göstergesi - EMA ile ölç
        trend = np.array(Indikator.EMA(close, length=14), dtype=float)
        # Momentum göstergesi - RSI kullan
        momentum = np.array(Indikator.RSI(close, length=14), dtype=float)
        # Volatilite göstergesi - Bollinger Band ve ATR kullan
        lower_band, mid_band, upper_band = Indikator.BB(close)
        atr = np.array(Indikator.ATR(high, low, close, length=14), dtype=float)

        # NaN'leri None'a dönüştür
        trend = [None if np.isnan(x) else x for x in trend]
        momentum = [None if np.isnan(x) else x for x in momentum]
        atr = [None if np.isnan(x) else x for x in atr]

        # Geçerli sayısal değerlerden None olmayanları al
        def filter_valid_values(data):
            # None değerlerini filtrele
            return [x for x in data if x is not None]

        trend_valid = filter_valid_values(trend)
        momentum_valid = filter_valid_values(momentum)
        atr_valid = filter_valid_values(atr)

        # Normalize et ve ortalama hesapla
        def normalize(valid_values, original_values):
            if len(valid_values) > 0:
                min_val = min(valid_values)
                max_val = max(valid_values)
                if max_val != min_val:
                    normalized = [(x - min_val) / (max_val - min_val) for x in valid_values]

                    # Geçerli değerlerin olduğu yerlere normalize edilmiş değerleri yerleştir
                    normalized_idx = 0
                    for i in range(len(original_values)):
                        if original_values[i] is not None:
                            original_values[i] = normalized[normalized_idx]
                            normalized_idx += 1
            return original_values

        trend_normalized = normalize(trend_valid, trend)
        momentum_normalized = normalize(momentum_valid, momentum)
        atr_normalized = normalize(atr_valid, atr)

        # Tüm değerleri birleştirip CMI oluştur
        cmi = [(trend_normalized[i] + momentum_normalized[i] + atr_normalized[i]) / 3 if trend_normalized[
                                                                                             i] is not None and
                                                                                         momentum_normalized[
                                                                                             i] is not None and
                                                                                         atr_normalized[
                                                                                             i] is not None else None
               for i in range(len(trend_normalized))]

        return cmi

    @staticmethod
    def DMO(src, length=14):
        dmo_values = []
        for i in range(len(src)):
            if i >= length:
                # Momentum hesaplaması (Close_t - Close_{t-period})
                mom = src[i] - src[i - length]
                # Volatilite hesaplaması
                volatility = np.mean([abs(src[j] - src[j - 1]) for j in range(i - length + 1, i + 1)])
                # DMO hesaplama
                dmo = mom / volatility if volatility != 0 else 0
            else:
                dmo = None  # İlk period öncesi yeterli veri olmadığı için None
            dmo_values.append(dmo)
        return dmo_values
    @staticmethod
    def VMZI(src, length=14):
        vmzi_values = [None] * length  # İlk 'period' kadar None olacak çünkü hesaplama yapılamaz
        for i in range(length, len(src)):
            # Momentum hesapla
            momentum = src[i] - src[i - length]
            # Volatilite (standart sapma) hesapla
            volatility = np.std(src[i - length:i])
            if volatility != 0:  # Volatilite sıfırsa bölme hatası olmasın diye kontrol ediyoruz
                vmzi = momentum / volatility
            else:
                vmzi = 0
            vmzi_values.append(vmzi)
        return vmzi_values

    @staticmethod
    def FDI(src, length=14):
        fdi_values = [None] * (length * 2)  # İlk 2 period boyunca None olacak, çünkü hesaplama yapılamaz

        for i in range(length * 2, len(src)):
            # Önce değişim oranını hesapla
            price_change_ratio_now = (src[i] - src[i - length]) / src[i - length]
            price_change_ratio_past = (src[i - length] - src[i - length * 2]) / src[
                i - length * 2]

            # Fiyat-Değişim İvmesi (FDI) hesapla
            fdi = price_change_ratio_now - price_change_ratio_past

            fdi_values.append(fdi)

        return fdi_values

    @staticmethod
    def VAMA(src, length=14):
        prices = np.array(src)
        vama = np.full(len(prices), None)  # Başlangıçta tüm değerleri None olarak ayarla

        for i in range(length, len(prices)):
            # Hareketli ortalama hesapla
            ma = np.mean(prices[i - length:i])

            # Volatiliteyi hesapla (standart sapma)
            volatility = np.std(prices[i - length:i])

            # VAMA hesapla (Hareketli Ortalama + Volatilite)
            vama[i] = ma + volatility

        return vama.tolist()

    @staticmethod
    def CCI(high, low, close, period=20, length=5):
        high = np.array(high)
        low = np.array(low)
        close = np.array(close)

        # Typical Price (TP) hesapla
        tp = (high + low + close) / 3

        # SMA hesapla (Basit Hareketli Ortalama)
        sma_tp = pd.Series(tp).rolling(window=period).mean().to_numpy()

        # Mean Deviation (Ortalama Sapma) hesapla
        mean_deviation = pd.Series(tp).rolling(window=period).apply(
            lambda x: np.mean(np.abs(x - np.mean(x)))).to_numpy()

        # CCI hesapla
        cci = (tp - sma_tp) / (0.015 * mean_deviation)
        # CCI ortalamasını hesaplayıp geri döndürme
        cci = pd.Series(cci)
        return cci.rolling(window=length).mean().to_numpy().tolist()

    @staticmethod
    def TSO(high, low, close, period_ema_short=12, period_ema_long=26):
        if len(close) < max(period_ema_short, period_ema_long):
            return [None] * len(close)
        ema_short = Indikator.EMA(close, period_ema_short)
        ema_long = Indikator.EMA(close, period_ema_long)
        cci_values = Indikator.CCI(high, low, close)
        tso = []
        for i in range(len(close)):
            if ema_short[i] > ema_long[i] and cci_values[i] > 0:
                tso.append(1)
            elif ema_short[i] < ema_long[i] and cci_values[i] < 0:
                tso.append(-1)
            else:
                tso.append(0)
        return tso

    @staticmethod
    def Alpha_Trend(high, low, close, volume=None, coeff=1.0, period=14, use_volume=False):
        """
        AlphaTrend göstergesini hesaplar.
        """
        # ATR Hesaplama
        atr = Indikator.ATR(high, low, close, length=period)

        # UpT ve DownT Hesaplama
        upT = [low[i] - (atr[i] * coeff) if atr[i] is not None else None for i in range(len(low))]
        downT = [high[i] + (atr[i] * coeff) if atr[i] is not None else None for i in range(len(high))]

        # Trend Yönü (RSI veya MFI Kullanımı)
        if use_volume and volume is not None:
            mfi = Indikator.MFI(high, low, close, volume, length=period)
            trend_indicator = [mfi[i] >= 50 if mfi[i] is not None else None for i in range(len(mfi))]
        else:
            rsi = Indikator.RSI(close, length=period)
            trend_indicator = [rsi[i] >= 50 if rsi[i] is not None else None for i in range(len(rsi))]

            # AlphaTrend Hesaplama
        alpha_trend = [None] * len(close)

        # İlk periyotlar için hesaplama yapılmayacak, sonrasında ise hesaplama yapılacak
        for i in range(len(close)):
            # İlk geçerli veriyi bulmak için (period-1) kadar bekliyoruz
            if i >= period - 1:
                if trend_indicator[i] is not None:
                    # İlk geçerli hesaplama
                    if i == period - 1:
                        alpha_trend[i] = upT[i] if trend_indicator[i] else downT[i]
                    # Sonraki hesaplamalar
                    elif i > period - 1:
                        # Önceki alpha_trend değeri None değilse, işlemi gerçekleştirebiliriz
                        if alpha_trend[i - 1] is not None:
                            if trend_indicator[i]:
                                alpha_trend[i] = max(alpha_trend[i - 1], upT[i]) if upT[i] is not None else alpha_trend[
                                    i - 1]
                            else:
                                alpha_trend[i] = min(alpha_trend[i - 1], downT[i]) if downT[i] is not None else \
                                alpha_trend[i - 1]

        return alpha_trend

    @staticmethod
    def MFI(high, low, close, volume, length=14):
        """
        Money Flow Index (MFI) hesaplar.
        İlk periyot boyunca eksik olan veriler 'None' olarak döner.
        """
        if len(close) < length:
            return [None] * len(close)

        # Typical Price (Ortalama Fiyat)
        typical_price = (np.array(high) + np.array(low) + np.array(close)) / 3

        # Money Flow (Para Akışı)
        money_flow = typical_price * np.array(volume)

        # Pozitif ve Negatif Para Akışı
        positive_flow = np.zeros_like(money_flow)
        negative_flow = np.zeros_like(money_flow)
        for i in range(1, len(typical_price)):
            if typical_price[i] > typical_price[i - 1]:
                positive_flow[i] = money_flow[i]
            elif typical_price[i] < typical_price[i - 1]:
                negative_flow[i] = money_flow[i]

        # Rolling Sum (Hareketli Toplam)
        positive_mf = pd.Series(positive_flow).rolling(window=length).sum()
        negative_mf = pd.Series(negative_flow).rolling(window=length).sum()

        # Money Flow Ratio (Para Akış Oranı)
        mfr = positive_mf / negative_mf.replace(0, np.nan)
        mfi = 100 - (100 / (1 + mfr))

        # İlk length - 1 değerini None yap
        mfi = mfi.to_list()
        mfi = [None if i < length - 1 else mfi[i] for i in range(len(mfi))]

        return mfi

    @staticmethod
    def destek_direnc_hesapla(buy_price, low, window=14, tolerance=0.01):
        # Listeyi DataFrame'e dönüştür
        data = pd.DataFrame({'Low': low})
        data['Support'] = np.nan
        for i in range(window, len(data) - window):
            local_min = data['Low'][i]
            is_support = all(local_min <= data['Low'][i - window:i + window])
            if is_support:
                data.loc[i, 'Support'] = local_min
        # Destek seviyelerini gruplayarak benzeyenleri tek bir seviyeye indir
        support_levels = data['Support'].dropna().unique()
        grouped_levels = []
        for level in sorted(support_levels):
            if not grouped_levels or abs(level - grouped_levels[-1]) > tolerance * level:
                grouped_levels.append(float(level))

        for i in range(len(grouped_levels)):
            if i == len(grouped_levels) - 1:
                return grouped_levels[i], None, grouped_levels
            if grouped_levels[i] < buy_price and grouped_levels[i + 1] > buy_price:
                return grouped_levels[i], grouped_levels[i + 1], grouped_levels

    @staticmethod
    def Super_Trend(high, low, close, atr_length=10, factor=3.0):
        """
        Supertrend hesaplama fonksiyonu (doğru ve optimize edilmiş)

        Parameters:
            high (list): Yüksek fiyat verileri
            low (list): Düşük fiyat verileri
            close (list): Kapanış fiyatları
            atr_length (int): ATR periyodu
            factor (float): Faktör (çarpan)

        Returns:
            tuple: (Supertrend değerleri, trend yönleri)
        """
        # Verileri DataFrame'e dönüştür
        data = pd.DataFrame({'high': high, 'low': low, 'close': close})

        # Ortalama True Range (ATR) hesaplama
        data['tr1'] = data['high'] - data['low']
        data['tr2'] = abs(data['high'] - data['close'].shift(1))
        data['tr3'] = abs(data['low'] - data['close'].shift(1))
        data['true_range'] = data[['tr1', 'tr2', 'tr3']].max(axis=1)
        data['atr'] = data['true_range'].rolling(atr_length).mean()

        # Supertrend üst ve alt bantlarının hesaplanması
        hl2 = (data['high'] + data['low']) / 2
        data['upper_band'] = hl2 + factor * data['atr']
        data['lower_band'] = hl2 - factor * data['atr']

        # Supertrend ve yön hesaplama
        supertrend = [None] * len(data)
        direction = [None] * len(data)

        for i in range(len(data)):
            if i < atr_length:
                # ATR periyodu tamamlanmadan Supertrend hesaplanmaz
                continue
            elif i == atr_length:
                # İlk trend başlangıcı için alt bant kullanılır
                supertrend[i] = data['lower_band'].iloc[i]
                direction[i] = 1  # Başlangıçta Uptrend
            else:
                # Önceki trend ve yön
                prev_supertrend = supertrend[i - 1]
                prev_direction = direction[i - 1]

                # Şartlara göre Supertrend hesaplama
                if data['close'].iloc[i] > prev_supertrend:
                    supertrend[i] = data['lower_band'].iloc[i]
                    direction[i] = 1  # Uptrend
                elif data['close'].iloc[i] < prev_supertrend:
                    supertrend[i] = data['upper_band'].iloc[i]
                    direction[i] = -1  # Downtrend
                else:
                    # Trend değişmezse önceki değerleri koru
                    supertrend[i] = prev_supertrend
                    direction[i] = prev_direction

                # Üst ve alt bant güncellemesi
                if direction[i] == 1:  # Uptrend ise üst bandı aşmamalı
                    supertrend[i] = min(supertrend[i], data['upper_band'].iloc[i])
                elif direction[i] == -1:  # Downtrend ise alt bandı geçmemeli
                    supertrend[i] = max(supertrend[i], data['lower_band'].iloc[i])
        supertrend = [float(x) if x is not None else float('nan') for x in supertrend]
        return supertrend, direction

    @staticmethod
    def ParabolicSAR(high, low, start=0.02, increment=0.02, maximum=0.2):
        """
        Parabolic SAR hesaplama fonksiyonu.

        :param high: Yüksek fiyatların listesi
        :param low: Düşük fiyatların listesi
        :param start: Başlangıç hız faktörü
        :param increment: Hız faktöründeki artış
        :param maximum: Maksimum hız faktörü
        :return: Parabolic SAR değerlerinin listesi
        """
        # Yeterli veri kontrolü
        if len(high) < 2 or len(low) < 2:
            return [None] * len(high)

        sar = [None]  # İlk SAR değeri None
        af = start  # Başlangıç hız faktörü
        ep = high[0]  # İlk yüksek değer (Extreme Point)
        uptrend = True  # İlk trend yukarı

        for i in range(1, len(high)):
            if uptrend:
                # SAR hesaplama
                new_sar = sar[-1] + af * (ep - sar[-1]) if sar[-1] is not None else low[i - 1]

                # Trend devam ediyor mu kontrolü
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + increment, maximum)

                # Trend değişimi kontrolü
                if low[i] < new_sar:
                    uptrend = False
                    new_sar = ep
                    ep = low[i]
                    af = start
            else:
                # SAR hesaplama
                new_sar = sar[-1] + af * (ep - sar[-1]) if sar[-1] is not None else high[i - 1]

                # Trend devam ediyor mu kontrolü
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + increment, maximum)

                # Trend değişimi kontrolü
                if high[i] > new_sar:
                    uptrend = True
                    new_sar = ep
                    ep = high[i]
                    af = start

            # SAR'ın mevcut mumun en yüksek veya en düşük değerini aşmamasını sağla
            new_sar = min(new_sar, high[i - 1]) if uptrend else max(new_sar, low[i - 1])
            sar.append(new_sar)

        return sar

    @staticmethod
    def StochasticRSI(close, lengthRSI=14, lengthStoch=14, smoothK=3, smoothD=3):
        """
        Stochastic RSI hesaplama fonksiyonu.

        :param close: Kapanış fiyatlarının listesi
        :param lengthRSI: RSI hesaplaması için periyot (varsayılan: 14)
        :param lengthStoch: Stochastic hesaplaması için periyot (varsayılan: 14)
        :param smoothK: K hattı için hareketli ortalama periyodu (varsayılan: 3)
        :param smoothD: D hattı için hareketli ortalama periyodu (varsayılan: 3)
        :return: Stochastic RSI'nın K ve D değerlerinin listesi
        """
        if len(close) < max(lengthRSI, lengthStoch, smoothK, smoothD):
            return [None] * len(close), [None] * len(close)

        # RSI hesaplama
        rsi = Indikator.RSI(close, length=lengthRSI)

        # Stochastic K hesaplama
        stoch_k = []
        for i in range(len(rsi)):
            if i < lengthStoch - 1 or rsi[i] is None:
                stoch_k.append(None)
            else:
                window = rsi[i - lengthStoch + 1:i + 1]
                valid_values = [x for x in window if x is not None]
                if len(valid_values) == lengthStoch:
                    min_rsi = min(valid_values)
                    max_rsi = max(valid_values)
                    stoch_k.append(
                        100 * (rsi[i] - min_rsi) / (max_rsi - min_rsi) if max_rsi != min_rsi else 0
                    )
                else:
                    stoch_k.append(None)

        # Smooth K (smoothK ile hareketli ortalama hesaplama)
        k_values = [None] * (smoothK - 1)  # İlk smoothK - 1 değeri None
        for i in range(smoothK - 1, len(stoch_k)):
            window = stoch_k[i - smoothK + 1:i + 1]
            valid_values = [x for x in window if x is not None]
            if len(valid_values) == smoothK:
                k_values.append(sum(valid_values) / smoothK)
            else:
                k_values.append(None)

        # Smooth D (smoothD ile hareketli ortalama hesaplama)
        d_values = [None] * (smoothD - 1)  # İlk smoothD - 1 değeri None
        for i in range(smoothD - 1, len(k_values)):
            window = k_values[i - smoothD + 1:i + 1]
            valid_values = [x for x in window if x is not None]
            if len(valid_values) == smoothD:
                d_values.append(sum(valid_values) / smoothD)
            else:
                d_values.append(None)

        return k_values, d_values
