from Indikator import Indikator
class Stratejiler:
    @staticmethod
    def MACD(close):
        macd = Indikator.MACD(close)
        macd_values = macd[0]
        macd_signal = macd[1]
        rsi = Indikator.RSI(close)
        if macd_signal[-1] is not None and macd_values[-1] is not None and rsi[-1] is not None:
            if macd_values[-1] > macd_signal[-1] and rsi[-1] > 50:
                return "BUY"
            elif macd_values[-1] < macd_signal[-1]:
                return "SELL"
            else:
                return False
        else:
            return None

    @staticmethod
    def VMZI(high, low, close):
        vmzi = Indikator.VMZI(close)
        adx = Indikator.ADX(high, low, close)
        rsi = Indikator.RSI(close)
        if vmzi[-1] is not None and adx[-1] is not None and rsi[-1] is not None:
            if vmzi[-1] > 1.5 and adx[-1] > 25 and rsi[-1] > 50:
                return "BUY"
            elif vmzi[-1] < 0 and rsi[-1] < 50:
                return "SELL"
            else:
                return False
        else:
            return None

    @staticmethod
    def VAMA(close):
        vama = Indikator.VAMA(close)
        if vama[-1] is not None:
            if vama[-1] * 1.02 < close[-1]:
                return "BUY"
            elif vama[-1] * 0.98 > close[-1]:
                return "SELL"
            else:
                return False
        else:
            return None

    @staticmethod
    def TSO(high, low, close):
        tso = Indikator.TSO(high, low, close)
        if tso[-1] is not None:
            if tso[-1] == 1:
                return "BUY"
            elif tso[-1] == -1:
                return "SELL"
            else:
                return False
        else:
            return None

    @staticmethod
    def BB_RSI(close):
        rsi = Indikator.RSI(close)
        bb_rsi = Indikator.BB(rsi)
        bb_rsi_down = bb_rsi[0]
        bb_rsi_up = bb_rsi[2]
        if rsi[-2] is not None and bb_rsi_down[-2] is not None and bb_rsi_up[-2] is not None:
            if bb_rsi_down[-2] > rsi[-2] and bb_rsi_down[-1] < rsi[-1]:
                return "BUY"
            elif bb_rsi_up[-2] < rsi[-2] and bb_rsi_up[-1] > rsi[-1]:
                return "SELL"
            else:
                return False
        else:
            return None

    @staticmethod
    def FDI(close):
        fdi = Indikator.FDI(close)
        rsi = Indikator.RSI(close)
        macd = Indikator.MACD(close)
        macd_values = macd[0]
        macd_signal = macd[1]
        if fdi[-2] is not None and rsi[-1] is not None and macd_values[-1] is not None and macd_signal[-1] is not None:
            if fdi[-2] > 0 and fdi[-2] < fdi[-1] and rsi[-1] > 40 and macd_values[-1] > macd_signal[-1]:
                return "BUY"
            elif fdi[-2] < 0 and fdi[-2] > fdi[-1] and rsi[-1] < 60 and macd_values[-1] < macd_signal[-1]:
                return "SELL"
            else:
                return False
        else:
            return None

    @staticmethod
    def BB_Close(close):
        bb = Indikator.BB(close)
        bb_down = bb[0]
        bb_mid = bb[1]
        bb_up = bb[2]
        if bb_down[-2] is not None and bb_mid[-2] is not None and bb_up[-2] is not None:
            if bb_down[-2] > close[-2] and bb_down[-1] < close[-1]:
                return "BUY"
            elif ((bb_up[-2] < close[-2] and bb_up[-1] > close[-1]) or (bb_down[-1] * 0.99 > close[-1]) or
                  (bb_mid[-2] < close[-2] and bb_mid[-1] > close[-1])):
                return "SELL"
            else:
                return False
        else:
            return None

    @staticmethod
    def MA_Cross(high, low, close):
        ma_9 = Indikator.SMA(close, 9)
        ma_50 = Indikator.SMA(close, 50)
        adx = Indikator.ADX(high, low, close)
        if ma_9[-2] is not None and ma_50[-2] is not None and adx[-1] is not None:
            if ma_9[-2] < ma_50[-2] and ma_9[-1] > ma_50[-1] and adx[-1] > 30:
                return "BUY"
            elif (ma_9[-2] > ma_50[-2] and ma_9[-1] < ma_50[-1]) or (ma_50[-1] * 0.99 > close[-1]):
                return "SELL"
            else:
                return False
        else:
            return None

    @staticmethod
    def DMO(high, low, close):
        dmo = Indikator.DMO(close)
        adx = Indikator.ADX(high, low, close)
        rsi = Indikator.RSI(close)
        atr = Indikator.ATR(high, low, close)
        bb = Indikator.BB(close)
        bb_down = bb[0]
        bb_up = bb[2]
        if dmo[-1] is not None and adx[-1] is not None and rsi[-1] is not None and bb_down[-1] is not None:
            if dmo[-1] > 1.0 and adx[-1] > 20 and rsi[-1] > 50 and close[-1] >= bb_up[-1]:
                return "BUY"
            elif dmo[-1] < 0.8 or adx[-1] < 20 or (rsi[-1] < 50 and close[-1] <= bb_down[-1]):
                return "SELL"
            else:
                return False
        else:
            return None

    @staticmethod
    def BB_ADX(high,low,close):
        bb = Indikator.BB(close)
        adx = Indikator.ADX(high, low, close)
        bb_down = bb[0]
        bb_up = bb[2]
        if bb_down[-1] is not None and bb_up[-1] is not None and adx[-1] is not None:
            if bb_down[-1] > close[-1] and adx[-1] > 25:
                return "BUY"
            elif (close[-1] > bb_up[-1] and adx[-1] < 20):
                return "SELL"
            else:
                return False
        else:
            return None
