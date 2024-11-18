from Indikator import Indikator

class Stratejiler:
    static_stop_lose_value = 0.025
    atr_factor_strong_trend = 2.0
    atr_factor_weak_trend = 1.2

    @staticmethod
    def dinamik_stop_lose(high, low, close, highest_price):
        if highest_price is None or close[-1] > highest_price:
            highest_price = close[-1]

        atr_values = Indikator.ATR(high, low, close)
        adx_values = Indikator.ADX(high, low, close)

        # Piyasa modu belirleme
        adx = adx_values[-1]
        if adx < 20:
            return None, highest_price, None  # Yatay piyasada stop çalışmaz

        # ATR çarpanı seçimi
        if adx > 30:
            atr_factor = Stratejiler.atr_factor_strong_trend
        else:
            atr_factor = Stratejiler.atr_factor_weak_trend

        # Stop seviyesi hesaplama
        stop_seviyesi = highest_price - (atr_values[-1] * atr_factor)

        if close[-1] < stop_seviyesi:
            return "STOP-LOSE", None, None

        return None, highest_price, stop_seviyesi

    @staticmethod
    def static_stop_lose(close, buy_price):
        if buy_price is not None and close[-1] < (buy_price * (1 - Stratejiler.static_stop_lose_value)):
            return "STOP-LOSE"
        return None
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
