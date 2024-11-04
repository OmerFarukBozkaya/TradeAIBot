from Indikator import Indikator
class Stratejiler:
    stop_lose = 0.025
    @staticmethod
    def MACD(high, low, close,buy_price=None):
        macd = Indikator.MACD(close)
        macd_values = macd[0]
        macd_signal = macd[1]
        rsi = Indikator.RSI(close)
        if macd_signal[-3] is not None and macd_values[-3] is not None and rsi[-3] is not None:
            if  (macd_values[-3] < macd_signal[-3] or rsi[-3] < 50) and macd_values[-2] > macd_signal[-2] and rsi[-2] > 50:
                return "BUY"
            elif macd_values[-2] < macd_signal[-2]:
                return "SELL"
            elif buy_price is not None and close[-1] < (buy_price * (1 - Stratejiler.stop_lose)):
                return "STOP-LOSE"
            else:
                return False
        else:
            return None

    @staticmethod
    def VMZI(high, low, close,buy_price=None):
        vmzi = Indikator.VMZI(close)
        adx = Indikator.ADX(high, low, close)
        rsi = Indikator.RSI(close)
        if vmzi[-3] is not None and adx[-3] is not None and rsi[-3] is not None:
            if (vmzi[-3] < 1.5 or adx[-3] < 25 or rsi[-3] < 50) and vmzi[-2] > 1.5 and adx[-2] > 25 and rsi[-2] > 50:
                return "BUY"
            elif vmzi[-2] < 0 and rsi[-2] < 50:
                return "SELL"
            elif buy_price is not None and close[-1] < (buy_price * (1 - Stratejiler.stop_lose)):
                return "STOP-LOSE"
            else:
                return False
        else:
            return None

    @staticmethod
    def VAMA(high, low, close,buy_price=None):
        vama = Indikator.VAMA(close)
        if vama[-3] is not None:
            if (vama[-3] * 1.02 > close[-3]) and vama[-2] * 1.02 < close[-2]:
                return "BUY"
            elif vama[-2] * 0.98 > close[-2]:
                return "SELL"
            elif buy_price is not None and close[-1] < (buy_price * (1 - Stratejiler.stop_lose)):
                return "STOP-LOSE"
            else:
                return False
        else:
            return None

    @staticmethod
    def TSO(high, low, close,buy_price=None):
        tso = Indikator.TSO(high, low, close)
        if tso[-3] is not None:
            if tso[-3] != 1 and tso[-2] == 1:
                return "BUY"
            elif tso[-2] == -1:
                return "SELL"
            elif buy_price is not None and close[-1] < (buy_price * (1 - Stratejiler.stop_lose)):
                return "STOP-LOSE"
            else:
                return False
        else:
            return None

    @staticmethod
    def BB_RSI(high, low, close,buy_price=None):
        rsi = Indikator.RSI(close)
        bb_rsi = Indikator.BB(rsi)
        bb_rsi_down = bb_rsi[0]
        bb_rsi_up = bb_rsi[2]
        if rsi[-3] is not None and bb_rsi_down[-3] is not None and bb_rsi_up[-3] is not None:
            if bb_rsi_down[-3] > rsi[-3] and bb_rsi_down[-2] < rsi[-2]:
                return "BUY"
            elif bb_rsi_up[-3] < rsi[-3] and bb_rsi_up[-2] > rsi[-2]:
                return "SELL"
            elif buy_price is not None and close[-1] < (buy_price * (1 - Stratejiler.stop_lose)):
                return "STOP-LOSE"
            else:
                return False
        else:
            return None

    @staticmethod
    def FDI(high, low, close,buy_price=None):
        fdi = Indikator.FDI(close)
        rsi = Indikator.RSI(close)
        macd = Indikator.MACD(close)
        macd_values = macd[0]
        macd_signal = macd[1]
        if fdi[-4] is not None and rsi[-3] is not None and macd_values[-3] is not None and macd_signal[-3] is not None:
            if (fdi[-4] < 0 or fdi[-4] > fdi[-3] or rsi[-3] < 40 or macd_values[-3] < macd_signal[-3]) and fdi[-3] > 0 and fdi[-3] < fdi[-2] and rsi[-2] > 40 and macd_values[-2] > macd_signal[-2]:
                return "BUY"
            elif fdi[-3] < 0 and fdi[-3] > fdi[-2] and rsi[-2] < 60 and macd_values[-2] < macd_signal[-2]:
                return "SELL"
            elif buy_price is not None and close[-1] < (buy_price * (1 - Stratejiler.stop_lose)):
                return "STOP-LOSE"
            else:
                return False
        else:
            return None

    @staticmethod
    def BB_Close(high, low, close,buy_price=None):
        bb = Indikator.BB(close)
        bb_down = bb[0]
        bb_mid = bb[1]
        bb_up = bb[2]
        if bb_down[-3] is not None and bb_mid[-3] is not None and bb_up[-3] is not None:
            if bb_down[-3] > close[-3] and bb_down[-2] < close[-2]:
                return "BUY"
            elif ((bb_up[-3] < close[-3] and bb_up[-2] > close[-2]) or (bb_down[-2] * 0.99 > close[-2]) or
                  (bb_mid[-3] < close[-3] and bb_mid[-2] > close[-2])):
                return "SELL"
            elif buy_price is not None and close[-1] < (buy_price * (1 - Stratejiler.stop_lose)):
                return "STOP-LOSE"
            else:
                return False
        else:
            return None

    @staticmethod
    def MA_Cross(high, low, close,buy_price=None):
        ma_9 = Indikator.SMA(close, 9)
        ma_50 = Indikator.SMA(close, 50)
        adx = Indikator.ADX(high, low, close)
        if ma_9[-2] is not None and ma_50[-2] is not None and adx[-1] is not None:
            if ma_9[-3] < ma_50[-3] and ma_9[-2] > ma_50[-2] and adx[-2] > 30:
                return "BUY"
            elif (ma_9[-3] > ma_50[-3] and ma_9[-2] < ma_50[-2]) or (ma_50[-2] * 0.99 > close[-2]):
                return "SELL"
            elif buy_price is not None and close[-1] < (buy_price * (1 - Stratejiler.stop_lose)):
                return "STOP-LOSE"
            else:
                return False
        else:
            return None

    @staticmethod
    def DMO(high, low, close,buy_price=None):
        dmo = Indikator.DMO(close)
        adx = Indikator.ADX(high, low, close)
        rsi = Indikator.RSI(close)
        bb = Indikator.BB(close)
        bb_down = bb[0]
        bb_up = bb[2]
        if dmo[-3] is not None and adx[-3] is not None and rsi[-3] is not None and bb_down[-2] is not None and bb_up[-3] is not None:
            if (dmo[-3] < 1.0 or adx[-3] < 20 or rsi[-3] < 50 or close[-3] < bb_up[-3]) and dmo[-2] > 1.0 and adx[-2] > 20 and rsi[-2] > 50 and close[-2] >= bb_up[-2]:
                return "BUY"
            elif dmo[-2] < 0.8 or adx[-2] < 20 or (rsi[-2] < 50 and close[-2] <= bb_down[-2]):
                return "SELL"
            elif buy_price is not None and close[-1] < (buy_price * (1 - Stratejiler.stop_lose)):
                return "STOP-LOSE"
            else:
                return False
        else:
            return None

    @staticmethod
    def BB_ADX(high, low, close,buy_price=None):
        bb = Indikator.BB(close)
        adx = Indikator.ADX(high, low, close)
        bb_down = bb[0]
        bb_up = bb[2]
        if bb_down[-2] is not None and bb_up[-2] is not None and adx[-2] is not None:
            if bb_down[-2] > close[-2] and adx[-2] > 25:
                return "BUY"
            elif (close[-2] > bb_up[-2] and adx[-2] < 20):
                return "SELL"
            elif buy_price is not None and close[-1] < (buy_price * (1 - Stratejiler.stop_lose)):
                return "STOP-LOSE"
            else:
                return False
        else:
            return None
