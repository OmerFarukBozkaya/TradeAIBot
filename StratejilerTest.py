from Indikator import Indikator

class StratejilerTest:
    stop_lose = 0.025

    @staticmethod
    def check_stop_lose(close, buy_price):
        # Eğer alım fiyatı mevcutsa ve kapanış fiyatı stop-lose sınırının altındaysa "STOP-LOSE" döndür.
        if buy_price is not None and close[-1] < (buy_price * (1 - StratejilerTest.stop_lose)):
            return "STOP-LOSE"
        return None

    @staticmethod
    def MACD(high, low, close):
        signals = []
        macd_values, macd_signal = Indikator.MACD(close)
        rsi = Indikator.RSI(close)
        adx = Indikator.ADX(high, low, close)

        # Dinamik ADX filtresi ve volatilite kontrolü
        for i in range(len(close)):  # Bu döngüde tüm verilere bakıyoruz
            if i == 0 or i == 1:  # İlk iki veri için sinyal verilmiyor, çünkü MACD ve diğer göstergeler ilk iki indekste hesaplanamaz
                signals.append("None")  # Bu noktada sinyal verilmiyor
            else:
                # Tüm göstergeler mevcutsa, sinyal kararını yapıyoruz
                if all(val is not None for val in [macd_values[i - 1], macd_signal[i - 1], rsi[i - 1], adx[i - 1]]):
                    # Al sinyali
                    if macd_values[i - 1] < macd_signal[i - 1] and rsi[i - 1] > 50 and adx[i - 1] > 25:
                        if macd_values[i] > macd_signal[i] and rsi[i] > 50 and adx[i] > 25:
                            signals.append("BUY")
                        else:
                            signals.append("False")
                    # Sat sinyali
                    elif macd_values[i] < macd_signal[i] and adx[i] > 25:
                        signals.append("SELL")
                    else:
                        signals.append("False")
                else:
                    signals.append("None")

        return signals

    @staticmethod   #   OK
    def VMZI(high, low, close, buy_price=None):
        stop_lose_check = StratejilerTest.check_stop_lose(close, buy_price)
        if stop_lose_check:
            return stop_lose_check

        vmzi = Indikator.VMZI(close)
        adx = Indikator.ADX(high, low, close)
        rsi = Indikator.RSI(close)
        atr = Indikator.ATR(high, low, close)  # ATR eklendi

        # ATR ve ADX ile volatilite ve trend filtreleme
        if all(val is not None for val in [vmzi[-1],vmzi[-1], adx[-1], rsi[-1], atr[-2],vmzi[-2], adx[-2], rsi[-2], atr[-3],vmzi[-3], adx[-3], rsi[-3], atr[-4]]):
            if not (vmzi[-3] > 1.5 and adx[-3] > 25 and rsi[-3] > 50 and atr[-3] > atr[-4]):
                if vmzi[-2] > 1.5 and adx[-2] > 25 and rsi[-2] > 50 and atr[-2] > atr[-3]:
                    return "BUY"
            elif vmzi[-2] < 0 and rsi[-2] < 50 and atr[-2] > atr[-3]:
                return "SELL"
            else :
                return False
        return None

    @staticmethod   #   OK
    def VAMA(high, low, close, buy_price=None):
        stop_lose_check = StratejilerTest.check_stop_lose(close, buy_price)
        if stop_lose_check:
            return stop_lose_check

        vama = Indikator.VAMA(close)
        sma_50 = Indikator.SMA(close, 50)  # SMA karşılaştırması eklendi

        # SMA ve VAMA uyumu ile al/sat sinyali
        if all(val is not None for val in [vama[-1],sma_50[-1],vama[-2],sma_50[-2],vama[-3],sma_50[-3]]):
            if not (vama[-3] * 1.02 < close[-3] and close[-3] > sma_50[-3]):
                if vama[-2] * 1.02 < close[-2] and close[-2] > sma_50[-2]:
                    return "BUY"
            elif vama[-2] * 0.98 > close[-2]:
                return "SELL"
            else :
                return False
        return None

    @staticmethod   #   OK
    def TSO(high, low, close, buy_price=None):
        stop_lose_check = StratejilerTest.check_stop_lose(close, buy_price)
        if stop_lose_check:
            return stop_lose_check

        tso = Indikator.TSO(high, low, close)
        atr = Indikator.ATR(high, low, close)  # ATR eklendi

        # ATR ile trend gücünün doğrulanması
        if all(val is not None for val in [atr[-1],tso[-1],atr[-2],tso[-2],atr[-3],tso[-3],atr[-4]]):
            if not (tso[-3] == 1 and atr[-3] > atr[-4]):
                if tso[-2] == 1 and atr[-2] > atr[-3]:
                    return "BUY"
            elif tso[-2] == -1 and atr[-2] > atr[-3]:
                return "SELL"
            else:
                return False
        return None

    @staticmethod   #   OK
    def BB_RSI(high, low, close, buy_price=None):
        stop_lose_check = StratejilerTest.check_stop_lose(close, buy_price)
        if stop_lose_check:
            return stop_lose_check

        rsi = Indikator.RSI(close)
        bb_rsi = Indikator.BB(rsi)
        bb_rsi_down, _, bb_rsi_up = bb_rsi
        atr = Indikator.ATR(high, low, close)  # ATR eklendi

        # ATR ile volatilite filtresi
        if all(val is not None for val in [rsi[-1], bb_rsi_down[-1], atr[-1],rsi[-2], bb_rsi_down[-2], bb_rsi_up[-1], atr[-2],rsi[-3], bb_rsi_down[-3], bb_rsi_up[-2], atr[-3],rsi[-4], bb_rsi_down[-4], bb_rsi_up[-3], atr[-4]]):
            if not (bb_rsi_down[-4] > rsi[-4] and bb_rsi_down[-3] < rsi[-3] and atr[-3] > atr[-4]):
                if (bb_rsi_down[-3] > rsi[-3] and bb_rsi_down[-2] < rsi[-2] and atr[-2] > atr[-3]):
                    return "BUY"
            elif bb_rsi_up[-3] < rsi[-3] and bb_rsi_up[-2] > rsi[-2] and atr[-1] > atr[-2]:
                return "SELL"
            else :
                return False
        return None

    @staticmethod   #   OK
    def FDI(high, low, close, buy_price=None):
        stop_lose_check = StratejilerTest.check_stop_lose(close, buy_price)
        if stop_lose_check:
            return stop_lose_check

        fdi = Indikator.FDI(close)
        rsi = Indikator.RSI(close)
        macd = Indikator.MACD(close)
        macd_values, macd_signal = macd
        adx = Indikator.ADX(high, low, close)  # ADX eklendi

        # ADX ile trend doğrulama ve RSI için daha düşük bir eşik
        if all(val is not None for val in [fdi[-1],fdi[-2], rsi[-1], macd_values[-1], macd_signal[-1],adx[-1],fdi[-3], rsi[-2], macd_values[-2], macd_signal[-2],adx[-2],fdi[-4], rsi[-3], macd_values[-3], macd_signal[-3],adx[-3]]):
            if not (fdi[-4] > 0 and fdi[-4] < fdi[-3] and rsi[-3] > 40 and macd_values[-3] > macd_signal[-3] and adx[-3] > 20):
                if fdi[-3] > 0 and fdi[-3] < fdi[-2] and rsi[-2] > 40 and macd_values[-2] > macd_signal[-2] and adx[-2] > 20:
                    return "BUY"
            elif fdi[-3] < 0 and fdi[-3] > fdi[-2] and rsi[-2] < 60 and macd_values[-2] < macd_signal[-2] and adx[-2] > 20:
                return "SELL"
            else :
                return False
        return None

    @staticmethod   #   OK
    def BB_Close(high, low, close, buy_price=None):
        stop_lose_check = StratejilerTest.check_stop_lose(close, buy_price)
        if stop_lose_check:
            return stop_lose_check

        bb = Indikator.BB(close)
        bb_down, bb_mid, bb_up = bb
        atr = Indikator.ATR(high, low, close)  # ATR eklendi

        # ATR ile volatilite doğrulaması
        if all(val is not None for val in [bb_down[-1], bb_mid[-1], bb_up[-1], atr[-1],bb_down[-2], bb_mid[-2], bb_up[-2], atr[-2],bb_down[-3], bb_mid[-3], bb_up[-3], atr[-3]]):
            if bb_down[-3] > close[-3] and bb_down[-2] < close[-2] and atr[-2] > atr[-3]:
                return "BUY"
            elif ((bb_up[-3] < close[-3] and bb_up[-2] > close[-2]) or (bb_down[-2] * 0.99 > close[-2]) or
                  (bb_mid[-3] < close[-3] and bb_mid[-2] > close[-2])) and atr[-2] > atr[-3]:
                return "SELL"
            else :
                return False
        return None

    @staticmethod   #   OK
    def MA_Cross(high, low, close, buy_price=None):
        stop_lose_check = StratejilerTest.check_stop_lose(close, buy_price)
        if stop_lose_check:
            return stop_lose_check

        ma_9 = Indikator.SMA(close, 9)
        ma_50 = Indikator.SMA(close, 50)
        adx = Indikator.ADX(high, low, close)
        atr = Indikator.ATR(high, low, close)  # ATR eklendi

        # ADX ve ATR ile trend gücü ve volatilite doğrulaması
        if all(val is not None for val in [ma_9[-1], ma_50[-1],atr[-1],ma_9[-2], ma_50[-2],atr[-2],adx[-1],ma_9[-3], ma_50[-3],atr[-3],adx[-2]]):
            if ma_9[-3] < ma_50[-3] and ma_9[-2] > ma_50[-2] and adx[-2] > 25 and atr[-2] > atr[-3] :
                return "BUY"
            elif ((ma_9[-3] > ma_50[-3] and ma_9[-2] < ma_50[-2]) or (ma_50[-2] * 0.99 > close[-2])) and adx[-2] > 25 and atr[-2] > atr[-3] :
                return "SELL"
            else :
                return False
        return None

    @staticmethod   #   OK
    def DMO(high, low, close, buy_price=None):
        stop_lose_check = StratejilerTest.check_stop_lose(close, buy_price)
        if stop_lose_check:
            return stop_lose_check

        dmo = Indikator.DMO(close)
        adx = Indikator.ADX(high, low, close)
        rsi = Indikator.RSI(close)
        bb = Indikator.BB(close)
        bb_down, bb_up = bb[0], bb[2]
        atr = Indikator.ATR(high, low, close)  # ATR eklendi

        # ATR ile volatilite doğrulaması ve ADX ile trend gücü analizi
        if all(val is not None for val in [atr[-1],dmo[-1], adx[-1], rsi[-1], bb_up[-1], atr[-2],
            dmo[-2], adx[-2], rsi[-2], bb_down[-1], bb_up[-2], atr[-3],
            dmo[-3], adx[-3], rsi[-3], bb_down[-2], bb_up[-3], atr[-4]]):
            if not (dmo[-3] > 1.0 and adx[-3] > 20 and rsi[-3] > 50 and close[-3] >= bb_up[-3] and atr[-3] > atr[-4]):
                if dmo[-2] > 1.0 and adx[-2] > 20 and rsi[-2] > 50 and close[-2] >= bb_up[-2] and atr[-2] > atr[-3]:
                    return "BUY"
            elif (dmo[-2] < 0.8 or adx[-2] < 20 or (rsi[-2] < 50 and close[-2] <= bb_down[-2])) and atr[-2] > atr[-3]:
                return "SELL"
            else :
                return False
        return None

    @staticmethod   #   OK
    def BB_ADX(high, low, close, buy_price=None):
        stop_lose_check = StratejilerTest.check_stop_lose(close, buy_price)
        if stop_lose_check:
            return stop_lose_check

        bb = Indikator.BB(close)
        bb_down, bb_up = bb[0], bb[2]
        adx = Indikator.ADX(high, low, close)

        # ADX ve RSI ile trend ve aşırı alım/satım durumu kontrolü
        if all(val is not None for val in [bb_down[-1], bb_up[-1], adx[-1],bb_down[-2], bb_up[-2], adx[-2],bb_down[-3], bb_up[-3], adx[-3]]):
            if not (bb_down[-3] < close[-3] and adx[-3] > 30):
                if bb_down[-2] < close[-2] and adx[-2] > 30:
                    return "BUY"
            elif bb_up[-3] < close[-3] and bb_up[-2] > close[-2]:
                return "SELL"
            else :
                return False
        return None
