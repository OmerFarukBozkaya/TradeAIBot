from Indikator import Indikator
from Binance import Binance
import pandas as pd
import numpy as np

class Stratejiler:
    static_stop_lose_value = 0.025
    atr_factor_strong_trend = 2.0
    atr_factor_weak_trend = 1.2
    destek_stop_lose_tolerans = 0.01
    dinamik_stop_lose_tolerans = 0.01
    take_profit_limit = 5

    @staticmethod
    def dinamik_stop_lose(high, low, close, highest_price):
        if highest_price is None or close[-1] > highest_price:
            highest_price = close[-1]

        atr_values = Indikator.ATR(high, low, close)
        adx_values = Indikator.ADX(high, low, close)

        # Piyasa modu belirleme
        adx = adx_values[-1]
        if adx < 20:
            return None, highest_price, -1  # Yatay piyasada stop çalışmaz

        # ATR çarpanı seçimi
        if adx > 30:
            atr_factor = Stratejiler.atr_factor_strong_trend
        else:
            atr_factor = Stratejiler.atr_factor_weak_trend

        # Stop seviyesi hesaplama
        stop_seviyesi = highest_price - (atr_values[-1] * atr_factor)

        if close[-1] < stop_seviyesi * (1-Stratejiler.dinamik_stop_lose_tolerans):
            return "STOP-LOSE", None, -1

        return None, highest_price, stop_seviyesi

    @staticmethod
    def static_stop_lose(close, buy_price):
        if buy_price is not None and close[-1] < (buy_price * (1 - Stratejiler.static_stop_lose_value)):
            return "STOP-LOSE"
        return None

    @staticmethod
    def destek_stop_lose(buy_price, destek, direnc, close, low, tolerans=1.02):
        yerel_minimum = []
        for i in range(1, len(low) - 1):
            if low[i - 1] > low[i] and low[i] < low[i + 1]:
                yerel_minimum.append(low[i])
        yerel_minimum.sort()

        # Destek seviyelerini bulma
        levels = []
        temp = []
        for i in range(len(yerel_minimum) - 1):
            if len(temp) == 0:
                temp.append(yerel_minimum[i])
            if yerel_minimum[i] * tolerans > yerel_minimum[i + 1] and temp[0] * tolerans > yerel_minimum[i]:
                temp.append(yerel_minimum[i])
            else:
                if temp:  # `temp` boş değilse
                    toplam = sum(temp)
                    levels.append(toplam / len(temp))  # Ortalamayı ekle
                else:
                    levels.append(yerel_minimum[i])
                temp = []

        # Son kalan temp verilerini ekle
        if temp:
            toplam = sum(temp)
            levels.append(toplam / len(temp))

        if destek is None:
            for i in range(len(levels)):
                if i == len(levels) - 1:
                    return levels[i], None, None
                if levels[i] < buy_price and levels[i + 1] > buy_price:
                    return levels[i], levels[i + 1], None
        elif direnc is not None and close[-1] > direnc:
            for i in range(len(levels)):
                if i == len(levels) - 1:
                    return levels[i], None, None
                if levels[i] < close[-1] and levels[i + 1] > close[-1]:
                    return levels[i], levels[i + 1], None
        elif close[-1] < destek * (1 - Stratejiler.destek_stop_lose_tolerans):
            return None, None, "STOP-LOSE"
        else:
            return destek, direnc, None

    @staticmethod
    def take_profit(durum_list):
        if len(durum_list[:-1]) != 0:
            ortalama = sum(durum_list[:-1]) / len(durum_list[:-1])
        else:
            ortalama = 0
        if ortalama > Stratejiler.take_profit_limit and durum_list[-1] < ortalama:
            return None, "TAKE-PROFIT"
        return ortalama, False

    @staticmethod
    def MACD(high, low, close):
        # Sonuçları tutmak için liste
        signals = []

        # Tüm indikatörlerin bir defa hesaplanması
        macd_values, macd_signal = Indikator.MACD(close)
        rsi_values = Indikator.RSI(close)
        adx_values = Indikator.ADX(high, low, close)

        # Her fiyat noktası için sinyal hesaplama
        for i in range(len(close)):
            if macd_values[i] is None or macd_signal[i] is None or rsi_values[i] is None or adx_values[i] is None:
                signals.append(None)
            elif macd_values[i] > macd_signal[i] and rsi_values[i] > 50 and adx_values[i] > 25:
                signals.append("BUY")
            elif macd_values[i] < macd_signal[i] and adx_values[i] > 25:
                signals.append("SELL")
            else:
                signals.append(False)
        return signals

    @staticmethod   #   OK
    def VMZI(high, low, close):
        signals=[]

        vmzi = Indikator.VMZI(close)
        adx = Indikator.ADX(high, low, close)
        rsi = Indikator.RSI(close)
        atr = Indikator.ATR(high, low, close)  # ATR eklendi

        # Her fiyat noktası için sinyal hesaplama
        for i in range(len(close)):
            if vmzi[i] is None or adx[i] is None or rsi[i] is None or atr[i] is None or atr[i-1] is None:
                signals.append(None)
            elif vmzi[i] > 1.5 and adx[i] > 25 and atr[i] > atr[i-1]:
                signals.append("BUY")
            elif vmzi[i] < 0 and rsi[i] < 50 and atr[i] > atr[i-1]:
                signals.append("SELL")
            else:
                signals.append(False)
        return signals

    @staticmethod   #   OK
    def VAMA(high, low, close):
        signals=[]
        vama = Indikator.VAMA(close)
        sma_50 = Indikator.SMA(close, 50)  # SMA karşılaştırması eklendi

        # Her fiyat noktası için sinyal hesaplama
        for i in range(len(close)):
            if vama[i] is None or sma_50[i] is None:
                signals.append(None)
            elif vama[i] * 1.02 < close[i] and close[i] > sma_50[i]:
                signals.append("BUY")
            elif vama[i] * 0.98 > close[i]:
                signals.append("SELL")
            else:
                signals.append(False)
        return signals

    @staticmethod   #   OK
    def TSO(high, low, close):
        signals=[]

        tso = Indikator.TSO(high, low, close)
        atr = Indikator.ATR(high, low, close)  # ATR eklendi

        # Her fiyat noktası için sinyal hesaplama
        for i in range(len(close)):
            if tso[i] is None or atr[i] is None or atr[i - 1] is None:
                signals.append(None)
            elif tso[i] == 1 and atr[i] > atr[i - 1]:
                signals.append("BUY")
            elif tso[i] == -1 and atr[i] > atr[i - 1]:
                signals.append("SELL")
            else:
                signals.append(False)
        return signals

    @staticmethod   #   OK
    def BB_RSI(high, low, close):
        signals=[]

        rsi = Indikator.RSI(close)
        bb_rsi_down, bb_rsi_mid , bb_rsi_up = Indikator.BB(rsi)
        atr = Indikator.ATR(high, low, close)  # ATR eklendi

        # Her fiyat noktası için sinyal hesaplama
        for i in range(len(close)):
            if rsi[i] is None or rsi[i-1] is None or bb_rsi_down[i] is None or bb_rsi_down[i-1] is None or bb_rsi_up[i] is None or bb_rsi_up[i-1] is None or atr[i] is None or atr[i - 1] is None:
                signals.append(None)
            elif bb_rsi_down[i-1] > rsi[i-1] and bb_rsi_down[i]<rsi[i] and atr[i] > atr[i - 1]:
                signals.append("BUY")
            elif bb_rsi_up[i-1] < rsi[i-1] and bb_rsi_up[i] > rsi[i] and atr[i] > atr[i - 1]:
                signals.append("SELL")
            else:
                signals.append(False)
        return signals

    @staticmethod   #   OK
    def FDI(high, low, close):
        signals=[]

        fdi = Indikator.FDI(close)
        rsi = Indikator.RSI(close)
        macd_values, macd_signal = Indikator.MACD(close)
        adx = Indikator.ADX(high, low, close)  # ADX eklendi

        # Her fiyat noktası için sinyal hesaplama
        for i in range(len(close)):
            if (fdi[i] is None or fdi[i - 1] is None or rsi[i] is None or macd_values[i] is None or
                    macd_signal[i] is None or adx[i] is None ):
                signals.append(None)
            elif fdi[i - 1] > 0 and fdi[i-1] < fdi[i] and rsi[i] > 40 and macd_values[i] > macd_signal[i] and adx[i] > 20:
                signals.append("BUY")
            elif fdi[i - 1] < 0 and fdi[i-1] > fdi[i] and rsi[i] < 60 and macd_values[i] < macd_signal[i] and adx[i] > 20:
                signals.append("SELL")
            else:
                signals.append(False)
        return signals

    @staticmethod   #   OK
    def BB_Close(high, low, close):
        signals=[]

        bb_down, bb_mid, bb_up = Indikator.BB(close)
        atr = Indikator.ATR(high, low, close)  # ATR eklendi

        # Her fiyat noktası için sinyal hesaplama
        for i in range(len(close)):
            if i == 0 or bb_down[i] is None or bb_down[i-1] is None or bb_mid[i] is None or bb_mid[i-1] is None or bb_up[i] is None or bb_up[i-1] is None or atr[i] is None or atr[i-1] is None:
                signals.append(None)
            elif bb_down[i-1] > close[i-1] and bb_down[i] < close[i] and atr[i] > atr[i-1]:
                signals.append("BUY")
            elif ((bb_up[i-1] < close[i-1] and bb_up[i] > close[i]) or (bb_down[i] * 0.99 > close[i] or (bb_mid[i-1] < close[i-1] and bb_mid[i] > close[i]))) and atr[i] > atr[i-1]:
                signals.append("SELL")
            else:
                signals.append(False)
        return signals

    @staticmethod   #   OK
    def MA_Cross(high, low, close):
        signals=[]

        ma_9 = Indikator.SMA(close, 9)
        ma_50 = Indikator.SMA(close, 50)
        adx = Indikator.ADX(high, low, close)
        atr = Indikator.ATR(high, low, close)  # ATR eklendi

        # Her fiyat noktası için sinyal hesaplama
        for i in range(len(close)):
            if ma_9[i] is None or ma_9[i-1] is None or ma_50[i] is None or ma_50[i-1] is None or adx[i] is None or atr[i] is None or atr[i-1] is None:
                signals.append(None)
            elif ma_9[i-1] < ma_50[i-1] and ma_9[i] > ma_50[i] and adx[i] > 25 and atr[i] > atr[i-1]:
                signals.append("BUY")
            elif ((ma_9[i-1] > ma_50[i-1] and ma_9[i] < ma_50[i]) or (ma_50[i] * 0.99 > close[i])) and adx[i]>25 and atr[i] > atr[i-1]:
                signals.append("SELL")
            else:
                signals.append(False)
        return signals

    @staticmethod   #   OK
    def DMO(high, low, close):
        signals=[]

        dmo = Indikator.DMO(close)
        adx = Indikator.ADX(high, low, close)
        rsi = Indikator.RSI(close)
        bb_down, bb_mid ,bb_up = Indikator.BB(close)
        atr = Indikator.ATR(high, low, close)  # ATR eklendi

        # Her fiyat noktası için sinyal hesaplama
        for i in range(len(close)):
            if dmo[i] is None or adx[i] is None or rsi[i] is None or bb_up[i] is None or bb_down is None or atr[i] is None or atr[i-1] is None:
                signals.append(None)
            elif dmo[i] > 1.0 and adx[i] > 20 and rsi[i] > 50 and close[i] >= bb_up[i] and atr[i] > atr[i-1]:
                signals.append("BUY")
            elif (dmo[i] < 0.8 or adx[i] < 20 or (rsi[i] < 50 and close[i] <= bb_down[i])) and atr[i] > atr[i-1]:
                signals.append("SELL")
            else:
                signals.append(False)
        return signals

    @staticmethod   #   OK
    def BB_ADX(high, low, close):
        signals=[]

        bb_down, bb_mid ,bb_up = Indikator.BB(close)
        adx = Indikator.ADX(high, low, close)

        # Her fiyat noktası için sinyal hesaplama
        for i in range(len(close)):
            if i == 0 or adx[i] is None or bb_down[i] is None or bb_up[i] is None or bb_up[i-1] is None:
                signals.append(None)
            elif bb_down[i] < close[i] and adx[i] > 30:
                signals.append("BUY")
            elif bb_up[i-1] < close[i-1] and bb_up[i]>close[i]:
                signals.append("SELL")
            else:
                signals.append(False)
        return signals

    @staticmethod
    def Alpha_Trend(high, low, close, vol):
        signals = []
        alpha_trend = Indikator.Alpha_Trend(high, low, close, vol, use_volume=True)
        for i in range(len(close)):
            if alpha_trend[i] is None or alpha_trend[i - 1] is None or alpha_trend[i - 2] is None:
                signals.append(None)
            elif alpha_trend[i] > alpha_trend[i - 2]:
                signals.append("BUY")
            elif alpha_trend[i] < alpha_trend[i - 2]:
                signals.append("SELL")
            else:
                signals.append(False)
        return signals

    @staticmethod
    def Super_Trend(high, low, close):
        signals = []
        supertrend, direction = Indikator.Super_Trend(high, low, close)
        for i in range(len(close)):
            if direction[i] is None:
                signals.append(None)
            elif direction[i] == 1:
                signals.append("BUY")
            elif direction[i] == -1:
                signals.append("SELL")
            else:
                signals.append(False)
        return signals

    @staticmethod
    def EMA_StochasticRSI(high, low, close):
        signals = []

        ema_50 = Indikator.EMA(close, 50)
        stoch_k, stoch_d = Indikator.StochasticRSI(close)

        for i in range(len(close)):
            if ema_50[i] is None or stoch_k[i] is None or stoch_d[i] is None:
                signals.append(None)
            elif close[i] > ema_50[i] and stoch_k[i] > stoch_d[i]:
                signals.append("BUY")
            elif close[i] < ema_50[i] and stoch_k[i] < stoch_d[i]:
                signals.append("SELL")
            else:
                signals.append(False)

        return signals

    @staticmethod
    def CCI_ATR(high, low, close):
        signals = []

        cci = Indikator.CCI(high, low, close)
        atr = Indikator.ATR(high, low, close)

        for i in range(len(close)):
            if cci[i] is None or atr[i] is None or atr[i - 1] is None:
                signals.append(None)
            elif cci[i] > 100 and atr[i] > atr[i - 1]:
                signals.append("BUY")
            elif cci[i] < 0 and atr[i] < atr[i - 1]:
                signals.append("SELL")
            else:
                signals.append(False)

        return signals

    @staticmethod
    def Local_Min_Max(high, low, close):
        # Sonuçları tutmak için liste
        signals = []

        # Tüm indikatörlerin bir defa hesaplanması
        result = Indikator.local_min_max(close, close, 13)
        adx = Indikator.ADX(high, low, close)

        # Her fiyat noktası için sinyal hesaplama
        for i in range(len(high)):
            if result[i] is None or adx[i] is None:  # local_min[i] is None or local_max[i] is None or adx[i] is None or bb_mid[i] is None or ema50[i] is None
                signals.append(None)
            elif close[i] > result[i] and adx[i]>25:  # and adx[i]>30 and close[i]<bb_mid[i] and close[i]>ema50[i]
                signals.append("BUY")
            elif close[i] < result[i]:
                signals.append("SELL")
            else:
                signals.append(False)

        return signals

    @staticmethod
    def SignalMovingAvarage(high, low, close):
        # Sonuçları tutmak için liste
        signals = []

        # Tüm indikatörlerin bir defa hesaplanması
        ma, css = Indikator.SignalMovingAverage(close, 50)
        adx = Indikator.ADX(high, low, close)

        # Her fiyat noktası için sinyal hesaplama
        for i in range(len(high)):
            if ma[i] is None or adx[i] is None:
                signals.append(None)
            elif css[i] == 1 and adx[i] > 25:
                signals.append("BUY")
            elif css[i] == -1:
                signals.append("SELL")
            else:
                signals.append(False)

        return signals

    @staticmethod
    def SqueezeMomentum(high, low, close):
        """
        Squeeze Momentum indikatörüne dayalı bir strateji.
        """
        signals = []

        # İndikatör hesaplamaları
        momentum, momentum_state, squeeze_state = Indikator.SqueezeMomentumIndicator(close, high, low)
        adx = Indikator.ADX(high, low, close)
        rsi = Indikator.RSI(close)
        bb_down, bb_mid, bb_up = Indikator.BB(close)
        ema50 = Indikator.EMA(close, 50)

        # Sinyal üretimi
        for i in range(len(close)):
            if momentum[i] is None or squeeze_state[i] is None or ema50[i] is None:
                signals.append(None)
            elif squeeze_state[i] == 1 and momentum[i] > 0 and close[i] > ema50[i]:
                signals.append("BUY")  # Squeeze On ve pozitif momentum artışı
            elif squeeze_state[i] == -1 and momentum[i] < 0 and close[i] < ema50[i]:
                signals.append("SELL")  # Squeeze Off ve negatif momentum artışı
            else:
                signals.append(False)

        return signals

    @staticmethod
    def SMC_Strategy(high, low, close):
        """
        Gelişmiş SMC stratejisi: Momentum ve Trend gücü dahil
        """
        smc = Indikator.SMC(high, low, close)
        highs, lows = smc["highs"], smc["lows"]
        msb_up, msb_down = smc["msb_up"], smc["msb_down"]
        fvg_up, fvg_down = smc["fvg_up"], smc["fvg_down"]

        # Momentum ve trend gücü indikatörleri
        adx = Indikator.ADX(high, low, close)
        ema_kisa = Indikator.EMA(Binance.hlc3(high, low, close), 50)
        ema_uzun = Indikator.EMA(Binance.hlc3(high, low, close), 200)

        signals = []
        for i in range(len(close)):
            if msb_up[i] and adx[i] > 25 and ema_uzun[i] is not None and ema_kisa[i] is not None and ema_kisa[i] < \
                    close[i] and ema_uzun[i] < ema_kisa[i]:
                signals.append("BUY")
            elif msb_down[i] and adx[i] > 25:
                signals.append("SELL")
            else:
                signals.append(None)

        return signals

    @staticmethod
    def BBTrend_MACDDEMA(high, low, close):
        signals = [None]

        bb_trend = Indikator.BBTrend(close, 30)
        macd, signal, _ = Indikator.MACD_DEMA(close)

        # Her fiyat noktası için sinyal hesaplama
        for i in range(1, len(close)):
            if macd[i - 1] is None or signal[i - 1] is None or bb_trend[i] is None:
                signals.append(None)
            elif macd[i] < 0 and signal[i] < 0 and macd[i - 1] < signal[i - 1] and macd[i] > signal[i] and bb_trend[i] > 0:
                signals.append("BUY")
            elif macd[i] > 0 and signal[i] > 0 and macd[i] < signal[i] and bb_trend[i] < 0:
                signals.append("SELL")
            else:
                signals.append(False)

        return signals

    @staticmethod
    def AI(high,low,close):
        from AI import predict_single_row
        bb = np.array(Indikator.BB(close), dtype='float32')
        hesaplamalar = {
            # INDIKATOR
            'adx': np.array(Indikator.ADX(high, low, close), dtype='float32'),
            'sma50': np.array(Indikator.SMA(close, 50), dtype='float32'),
            'sma200': np.array(Indikator.SMA(close, 200), dtype='float32'),
            'ema21': np.array(Indikator.EMA(close, 21), dtype='float32'),
            'ema7': np.array(Indikator.EMA(close, 7), dtype='float32'),
            'parabolic_sar': np.array(Indikator.ParabolicSAR(high, low), dtype='float32'),
            'super_trend_val': np.array(Indikator.Super_Trend(high, low, close)[0], dtype='float32'),
            'alpha_trend': np.array(Indikator.Alpha_Trend(high, low, close), dtype='float32'),
            'bb_trend': np.array(Indikator.BBTrend(close), dtype='float32'),
            'sma_diff': np.array(np.nan, dtype='float32'),
            'signal_moving_avarage_50': np.array(Indikator.SignalMovingAverage(close, 50)[0], dtype='float32'),
            'bb_bot': bb[0],
            'bb_mid': bb[1],
            'bb_top': bb[2],
        }
        # 6. DataFrame oluşturma optimizasyonu
        last_data = pd.DataFrame({
            'close': np.array(close, dtype='float32'),
            **hesaplamalar,
        })
        last_data['sma_diff'] = last_data['sma50'] - last_data['sma200']
        last_data.dropna()

        return predict_single_row(last_data.iloc[-20:, :])