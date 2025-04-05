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
        # NumPy array'lerine çevir
        high = np.array(high)
        low = np.array(low)
        close = np.array(close)

        # Typical Price (TP) hesapla
        tp = (high + low + close) / 3
        tp_series = pd.Series(tp)

        # SMA hesapla (rolling hesaplamada min_periods parametresi ile yeterli veri olmadığında NaN döndür)
        sma_tp = tp_series.rolling(window=period, min_periods=period).mean()

        # Ortalama Sapma hesapla
        mean_deviation = tp_series.rolling(window=period, min_periods=period).apply(
            lambda x: np.mean(np.abs(x - np.mean(x))), raw=True
        )

        # CCI hesapla, yeterli veri olmadığı durumlarda NaN üretir
        cci = (tp_series - sma_tp) / (0.015 * mean_deviation)

        # Ek bir smoothing: rolling ortalama ile 'length' periyotlu ortalama hesaplama
        cci_smoothed = cci.rolling(window=length, min_periods=length).mean()

        # NaN değerleri None olarak değiştirip listeye çevir
        result = [None if pd.isna(x) else x for x in cci_smoothed.tolist()]

        # Çıktı, giriş verisi ile aynı uzunlukta olacaktır (ilk kısımlar None)
        return result

    @staticmethod
    def TSO(high, low, close, period_ema_short=12, period_ema_long=26):
        if len(close) < max(period_ema_short, period_ema_long):
            return [None] * len(close)
        ema_short = Indikator.EMA(close, period_ema_short)
        ema_long = Indikator.EMA(close, period_ema_long)
        cci_values = Indikator.CCI(high, low, close)
        tso = []
        for i in range(len(close)):
            if ema_short[i] is None or ema_long[i] is None or cci_values[i] is None:
                tso.append(None)
            elif ema_short[i] > ema_long[i] and cci_values[i] > 0:
                tso.append(1)
            elif ema_short[i] < ema_long[i] and cci_values[i] < 0:
                tso.append(-1)
            else:
                tso.append(0)
        return tso

    @staticmethod
    def Alpha_Trend(high, low, close, volume=None, coeff=1.0, period=14, use_volume=False):
        """
        AlphaTrend göstergesini hesaplar. Giriş verisiyle aynı uzunlukta çıktı üretir;
        ilk periyotlarda yeterli veri olmadığı için None değerleri döndürür.
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

        # AlphaTrend hesaplaması için sonuç listesi (giriş uzunluğu kadar None ile başlatılır)
        alpha_trend = [None] * len(close)

        for i in range(len(close)):
            # Yeterli veri yoksa hesaplama yapılmaz, None kalır
            if i < period - 1:
                alpha_trend[i] = None
            else:
                # İlk hesaplama: i == period-1
                if i == period - 1:
                    # Eğer trend göstergesi None değilse, upT veya downT seçimi
                    if trend_indicator[i] is not None:
                        alpha_trend[i] = upT[i] if trend_indicator[i] else downT[i]
                    else:
                        alpha_trend[i] = None
                else:
                    # Önceki alpha_trend değeri mevcutsa, devamlılık sağlanır
                    if alpha_trend[i - 1] is not None:
                        if trend_indicator[i] is not None:
                            if trend_indicator[i]:
                                # Mevcut upT değeri varsa, önceki ile karşılaştır
                                alpha_trend[i] = max(alpha_trend[i - 1], upT[i]) if upT[i] is not None else alpha_trend[
                                    i - 1]
                            else:
                                alpha_trend[i] = min(alpha_trend[i - 1], downT[i]) if downT[i] is not None else \
                                    alpha_trend[i - 1]
                        else:
                            # Trend göstergesi hesaplanamadıysa, önceki değeri koru
                            alpha_trend[i] = alpha_trend[i - 1]
                    else:
                        # Önceki hesaplanmış değer yoksa None kalır
                        alpha_trend[i] = None

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

        # Çıkış listelerini giriş verisi ile aynı uzunlukta oluştur (ilk kısımlar None)
        supertrend = [None] * len(data)
        direction = [None] * len(data)

        for i in range(len(data)):
            if i < atr_length:
                # ATR periyodu tamamlanmadan hesaplama yapma, None bırak
                continue
            elif i == atr_length:
                # İlk hesaplama için başlangıç değeri: alt bant kullanılıyor
                supertrend[i] = data['lower_band'].iloc[i]
                direction[i] = 1  # Başlangıçta Uptrend
            else:
                # Önceki değerlerden faydalanarak hesaplama yap
                prev_supertrend = supertrend[i - 1]
                prev_direction = direction[i - 1]

                if data['close'].iloc[i] > prev_supertrend:
                    supertrend[i] = data['lower_band'].iloc[i]
                    direction[i] = 1  # Uptrend
                elif data['close'].iloc[i] < prev_supertrend:
                    supertrend[i] = data['upper_band'].iloc[i]
                    direction[i] = -1  # Downtrend
                else:
                    supertrend[i] = prev_supertrend
                    direction[i] = prev_direction

                # Üst ve alt bant güncellemesi
                if direction[i] == 1:
                    supertrend[i] = min(supertrend[i], data['upper_band'].iloc[i])
                elif direction[i] == -1:
                    supertrend[i] = max(supertrend[i], data['lower_band'].iloc[i])

        return supertrend, direction

    @staticmethod
    def ParabolicSAR(high, low, start=0.02, increment=0.02, maximum=0.2):
        """
        Parabolic SAR hesaplama fonksiyonu.
        İlk iki değer None döndürülür, çünkü ilk periyotlar için yeterli veri yoktur.

        :param high: Yüksek fiyatların listesi
        :param low: Düşük fiyatların listesi
        :param start: Başlangıç hız faktörü
        :param increment: Hız faktöründeki artış
        :param maximum: Maksimum hız faktörü
        :return: Parabolic SAR değerlerinin listesi (giriş verisi ile aynı uzunlukta)
        """
        # Yeterli veri kontrolü
        if len(high) < 2 or len(low) < 2:
            return [None] * len(high)

        # İlk iki değer None (ilk periyotlar için hesaplama yapılamıyor)
        sar = [None, None]

        # Varsayılan olarak uptrend kabul edelim
        uptrend = True
        # İlk hesaplama için, uptrend olduğundan,
        # başlangıç SAR değeri ilk iki mumun en düşük değerlerinin minimumu olsun.
        sar[1] = min(low[0], low[1])
        # EP (Extreme Point): Uptrend için en yüksek, downtrend için en düşük değeri temsil eder.
        ep = max(high[0], high[1])
        af = start  # Başlangıç hız faktörü

        # Hesaplamalara 2. indeksten başlanır.
        for i in range(2, len(high)):
            if uptrend:
                new_sar = sar[i - 1] + af * (ep - sar[i - 1])
                # Uptrend durumunda, yeni SAR değeri önceki iki mumun düşük değeriyle sınırlandırılır.
                new_sar = min(new_sar, low[i - 1], low[i - 2])
                # Eğer güncel düşük, hesaplanan SAR değerinin altına düşerse trend tersine döner.
                if low[i] < new_sar:
                    uptrend = False
                    new_sar = ep  # Trend değişiminde SAR, önceki EP olarak alınır.
                    ep = low[i]  # Yeni EP downtrend için güncellenir.
                    af = start
            else:
                new_sar = sar[i - 1] + af * (ep - sar[i - 1])
                # Downtrend durumunda, yeni SAR değeri önceki iki mumun yüksek değeriyle sınırlandırılır.
                new_sar = max(new_sar, high[i - 1], high[i - 2])
                # Eğer güncel yüksek, hesaplanan SAR değerinin üzerine çıkarsa trend tersine döner.
                if high[i] > new_sar:
                    uptrend = True
                    new_sar = ep  # Trend değişiminde SAR, önceki EP olarak alınır.
                    ep = high[i]  # Yeni EP uptrend için güncellenir.
                    af = start

            # Mevcut trend devam ediyorsa, EP ve af güncellenir.
            if uptrend:
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + increment, maximum)
            else:
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + increment, maximum)

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
        :return: Giriş verisi uzunluğu kadar, ilk kısımlar None; ardından hesaplanmış Stochastic RSI K ve D değerleri.
        """
        if len(close) < max(lengthRSI, lengthStoch, smoothK, smoothD):
            return [None] * len(close), [None] * len(close)

        # RSI hesaplama (burada RSI fonksiyonunun çıktısının giriş uzunluğu kadar olduğunu varsayıyoruz)
        rsi = Indikator.RSI(close, length=lengthRSI)

        # Stochastic K için çıktı dizisini giriş uzunluğu kadar None ile başlatıyoruz
        stoch_k = [None] * len(rsi)
        for i in range(len(rsi)):
            if i < lengthStoch - 1 or rsi[i] is None:
                stoch_k[i] = None
            else:
                window = rsi[i - lengthStoch + 1: i + 1]
                valid_values = [x for x in window if x is not None]
                if len(valid_values) == lengthStoch:
                    min_rsi = min(valid_values)
                    max_rsi = max(valid_values)
                    stoch_k[i] = 100 * (rsi[i] - min_rsi) / (max_rsi - min_rsi) if max_rsi != min_rsi else 0
                else:
                    stoch_k[i] = None

        # Smooth K hesaplaması: Giriş uzunluğu kadar None ile dolu bir dizi oluşturuyoruz
        k_values = [None] * len(stoch_k)
        for i in range(len(stoch_k)):
            if i < smoothK - 1:
                k_values[i] = None
            else:
                window = stoch_k[i - smoothK + 1: i + 1]
                valid_values = [x for x in window if x is not None]
                k_values[i] = sum(valid_values) / smoothK if len(valid_values) == smoothK else None

        # Smooth D hesaplaması: Yine giriş uzunluğu kadar None ile dolu bir dizi oluşturuyoruz
        d_values = [None] * len(k_values)
        for i in range(len(k_values)):
            if i < smoothD - 1:
                d_values[i] = None
            else:
                window = k_values[i - smoothD + 1: i + 1]
                valid_values = [x for x in window if x is not None]
                d_values[i] = sum(valid_values) / smoothD if len(valid_values) == smoothD else None

        return k_values, d_values

    @staticmethod
    def local_min_max(high, low, length=3):
        result = []
        for i in range(length):
            result.append(None)
        for j in range(length, len(high) - length):
            mevcut_fiyat_high = high[j]
            mevcut_fiyat_low = low[j]
            onceki_length_high = high[j - length:j]
            sonraki_length_high = high[j + 1:j + length + 1]
            onceki_length_low = low[j - length:j]
            sonraki_length_low = low[j + 1:j + length + 1]
            local_max = True
            local_min = True
            for l in range(length):
                if mevcut_fiyat_low < onceki_length_low[l] and mevcut_fiyat_low < sonraki_length_low[l]:
                    pass
                else:
                    local_min = False
                if onceki_length_high[l] < mevcut_fiyat_high and sonraki_length_high[l] < mevcut_fiyat_high:
                    pass
                else:
                    local_max = False
            if local_max:
                result.append(high[j])
            elif local_min:
                result.append(low[j])
            else:
                result.append(result[-1])

            # print(f"{mevcut_fiyat}\n{onceki_length}\n{sonraki_length}")
        for k in range(length):
            result.append(result[-1])
        return result

    @staticmethod
    def SignalMovingAverage(src, length):
        """
        Signal Moving Average (LuxAlgo) indikatörü.

        :param src: Fiyat verileri (list)
        :param length: SMA uzunluğu (int)
        :return: Signal Moving Average ve Renk sinyalleri (list, list)
        """
        if len(src) < length:
            return [None] * len(src), [None] * len(src)

        # SMA hesaplama
        sma_values = np.convolve(src, np.ones(length) / length, mode='valid')
        sma = [None] * (length - 1) + sma_values.tolist()  # Çıktının uzunluğu girdiyle aynı

        # Mutlak fark hesaplama
        abs_diff = [None if i == 0 or sma[i] is None or sma[i - 1] is None else abs(sma[i] - sma[i - 1]) for i in
                    range(len(src))]

        # R² hesaplama (Korelasyonun karesi)
        bar_index = np.arange(len(src))
        r2 = []
        for i in range(len(src)):
            if i < length:
                r2.append(None)
            else:
                valid_src = src[i - length + 1:i + 1]
                valid_bar_index = bar_index[i - length + 1:i + 1]
                correlation = np.corrcoef(valid_src, valid_bar_index)[0, 1]
                r2.append(correlation ** 2)

        # Signal Moving Average hesaplama
        ma = [None] * len(src)
        os = [None] * len(src)  # Yön sinyali

        # İlk 'length-1' indeks None olarak kalıyor; ilk hesaplama index = length-1'te başlar.
        for i in range(length - 1, len(src)):
            if i == (length - 1):
                # İlk hesaplama için başlangıç değeri, SMA değerini kullanıyoruz.
                ma[i] = sma[i]
                # İlk yön için, kendisinden önce veri olmadığı için 0 (veya nötr) atanabilir.
                os[i] = 0
            else:
                if r2[i] is not None and r2[i] > 0.5:
                    # Eğer SMA değeri geçerliyse, önceki değeri kullanarak yönü hesapla.
                    os[i] = np.sign(src[i - 1] - sma[i - 1]) if sma[i - 1] is not None else os[i - 1]
                    ma[i] = r2[i] * sma[i] + (1 - r2[i]) * ma[i - 1]
                else:
                    os[i] = os[i - 1]
                    if ma[i - 1] is not None and abs_diff[i] is not None and os[i] is not None:
                        ma[i] = ma[i - 1] - abs_diff[i] * os[i]
                    else:
                        ma[i] = ma[i - 1]

        # Renk sinyalleri (Yeşil: Pozitif trend, Kırmızı: Negatif trend)
        css = [None if o is None else (1 if o == 1 else -1) for o in os]

        return ma, css

    @staticmethod
    def SqueezeMomentumIndicator(high, low, close, length=20, multBB=2.0, lengthKC=20, multKC=1.5, useTrueRange=True):
        """
        Squeeze Momentum Indicator [LazyBear].

        :param close: Kapanış fiyatları (list veya np.array)
        :param high: En yüksek fiyatlar (list veya np.array)
        :param low: En düşük fiyatlar (list veya np.array)
        :param length: Bollinger Bantları için dönem uzunluğu
        :param multBB: Bollinger Bantları çarpanı
        :param lengthKC: Keltner Kanalı için dönem uzunluğu
        :param multKC: Keltner Kanalı çarpanı
        :param useTrueRange: TrueRange kullanım seçeneği
        :return: Momentum değerleri (list), momentum durumları (list), squeeze durumları (list)
        """
        close = np.array(close, dtype=float)
        high = np.array(high, dtype=float)
        low = np.array(low, dtype=float)

        # Bollinger Bantları (BB) hesaplama
        bb_basis = pd.Series(close).rolling(window=length).mean().to_numpy()
        bb_dev = pd.Series(close).rolling(window=length).std().to_numpy() * multBB
        upperBB = bb_basis + bb_dev
        lowerBB = bb_basis - bb_dev

        # Keltner Kanalları (KC) hesaplama
        kc_ma = pd.Series(close).rolling(window=lengthKC).mean().to_numpy()
        if useTrueRange:
            tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
        else:
            tr = high - low
        tr[0] = 0  # İlk değer için TR sıfır yapılır
        kc_range_ma = pd.Series(tr).rolling(window=lengthKC).mean().to_numpy()
        upperKC = kc_ma + kc_range_ma * multKC
        lowerKC = kc_ma - kc_range_ma * multKC

        # Squeeze Durumlarını Belirleme
        sqz_on = (lowerBB > lowerKC) & (upperBB < upperKC)
        sqz_off = (lowerBB < lowerKC) & (upperBB > upperKC)
        no_sqz = ~(sqz_on | sqz_off)

        squeeze_state = np.where(sqz_on, 1, np.where(sqz_off, -1, 0))

        # Momentum Hesaplama
        avg_high_low = (pd.Series(high).rolling(window=lengthKC).max() + pd.Series(low).rolling(
            window=lengthKC).min()) / 2
        linreg_source = close - (avg_high_low + kc_ma) / 2
        momentum = pd.Series(linreg_source).rolling(window=lengthKC).apply(
            lambda x: np.polyfit(np.arange(len(x)), x, 1)[0], raw=True
        ).to_numpy()

        # Momentum Durumları
        momentum_state = []
        for i in range(len(momentum)):
            if i == 0 or np.isnan(momentum[i]) or np.isnan(momentum[i - 1]):
                momentum_state.append(None)
            elif momentum[i] > 0:
                momentum_state.append(1 if momentum[i] > momentum[i - 1] else 0)
            else:
                momentum_state.append(-2 if momentum[i] < momentum[i - 1] else -1)

        return momentum.tolist(), momentum_state, squeeze_state.tolist()

    @staticmethod
    def SMC(high, low, close, length=20):
        """
        Gelişmiş SMC indikatörü:
        - Likidite Havuzları
        - Order Blocks
        - Market Structure Break (MSB)
        - Fair Value Gap (FVG)
        """
        # Likidite Havuzları
        highs = [max(high[i - length:i]) if i >= length else None for i in range(len(high))]
        lows = [min(low[i - length:i]) if i >= length else None for i in range(len(low))]

        # MSB Tespiti
        msb_up = [close[i] > highs[i - 1] if i > 0 and highs[i - 1] is not None else None for i in range(len(close))]
        msb_down = [close[i] < lows[i - 1] if i > 0 and lows[i - 1] is not None else None for i in range(len(close))]

        # Fair Value Gap (FVG) Tespiti
        fvg_up = [high[i - 2] < low[i] if i >= 2 else None for i in range(len(close))]
        fvg_down = [low[i - 2] > high[i] if i >= 2 else None for i in range(len(close))]

        return {
            "highs": highs,
            "lows": lows,
            "msb_up": msb_up,
            "msb_down": msb_down,
            "fvg_up": fvg_up,
            "fvg_down": fvg_down
        }

    @staticmethod
    def MACD_DEMA(src, short_length=12, long_length=26, signal_length=9):
        """
        MACD DEMA hesaplama fonksiyonu
        """
        if len(src) < long_length:
            return [None] * len(src), [None] * len(src)

        def DEMA(values, length):
            ema_a = pd.Series(values).ewm(span=length).mean()
            ema_b = ema_a.ewm(span=length).mean()
            return 2 * ema_a - ema_b

        demaslow = DEMA(src, long_length)
        demafast = DEMA(src, short_length)

        macd_line = demafast - demaslow
        signal_line = DEMA(macd_line, signal_length)
        histogram = macd_line - signal_line

        return macd_line.tolist(), signal_line.tolist(), histogram.tolist()

    @staticmethod
    def BBTrend(src, short_length=20, long_length=50, std_dev=2.0):
        """
        BBTrend hesaplama fonksiyonu.
        Giriş verisinin uzunluğu ile aynı uzunlukta sonuç üretir.
        İlk veriler için yeterli veri yoksa değerler None döndürür.
        """
        if len(src) < max(short_length, long_length):
            return [None] * len(src)

        def BB(values, length, std_dev):
            series = pd.Series(values)
            # Sadece yeterli veri olduğunda hesaplama yapılır (min_periods parametresi ile)
            middle = series.rolling(window=length, min_periods=length).mean()
            std = series.rolling(window=length, min_periods=length).std()
            upper = middle + std_dev * std
            lower = middle - std_dev * std
            return middle, upper, lower

        short_middle, short_upper, short_lower = BB(src, short_length, std_dev)
        long_middle, long_upper, long_lower = BB(src, long_length, std_dev)

        # Hesaplama, sadece short_middle değeri mevcutsa uygulanır
        bb_trend = (abs(short_lower - long_lower) - abs(short_upper - long_upper)) / short_middle * 100

        # pandas serisinin NaN değerlerini None'a çevirerek giriş verisi uzunluğunda bir liste oluşturuyoruz
        bb_trend_list = [None if pd.isna(x) else x for x in bb_trend.tolist()]

        return bb_trend_list
