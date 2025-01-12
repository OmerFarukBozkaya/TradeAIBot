from Indikator import Indikator
from IndikatorTest import IndikatorTest
import pandas as pd
import numpy as np

class StratejilerTest:
    static_stop_lose_value = 0.025
    atr_factor_strong_trend = 2.0
    atr_factor_weak_trend = 1.2
    destek_stop_lose_tolerans = 0.01
    take_profit_limit = 5

    @staticmethod
    def dinamik_stop_lose(atr,adx,close, highest_price):
        if highest_price is None or close[-1] > highest_price:
            highest_price = close[-1]
        # Piyasa modu belirleme
        adx = adx[-1]
        if adx is not None and adx < 20:
            return None, highest_price, None  # Yatay piyasada stop çalışmaz

        # ATR çarpanı seçimi
        if adx is not None and adx > 30:
            atr_factor = StratejilerTest.atr_factor_strong_trend
        else:
            atr_factor = StratejilerTest.atr_factor_weak_trend

        # Stop seviyesi hesaplama
        stop_seviyesi = highest_price - (atr[-1] * atr_factor)

        if close[-1] < stop_seviyesi:
            return "STOP-LOSE", None, None

        return None, highest_price, stop_seviyesi
    @staticmethod
    def static_stop_lose(close, buy_price, i):
        if buy_price is not None and close[i] < (buy_price * (1 - StratejilerTest.static_stop_lose_value)):
            return "STOP-LOSE"
        return None
    @staticmethod
    def destek_stop_lose(buy_price,destek,direnc,close,low,tolerans=1.02):
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
                    return levels[i],None,None
                if levels[i] < buy_price and levels[i + 1] > buy_price:
                    return levels[i],levels[i + 1],None
        elif direnc is not None and close[-1] > direnc:
            for i in range(len(levels)):
                if i == len(levels) - 1:
                    return levels[i],None,None
                if levels[i] < close[-1] and levels[i + 1] > close[-1]:
                    return levels[i],levels[i + 1],None
        elif close[-1] < destek * (1-StratejilerTest.destek_stop_lose_tolerans):
            return None,None,"STOP-LOSE"
        else:
            return destek,direnc,None
    @staticmethod
    def take_profit(durum_list):
        if len(durum_list[:-1]) != 0:
            ortalama=sum(durum_list[:-1])/len(durum_list[:-1])
        else:
            ortalama=0
        if ortalama > StratejilerTest.take_profit_limit and durum_list[-1]<ortalama:
            return None,"TAKE-PROFIT"
        return ortalama,False

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
        indicators={"main_indicators":None,
                    "sub_indicators": [{"macd_values":macd_values,"macd_signal":macd_signal},
                                       {"RSI":rsi_values},
                                       {"ADX":adx_values}],
                    "sub_horizontal_lines":[[{"name": "", "value": 0, "color": "black"}],
                                            [{"name": "", "value": 50, "color": "black"},{"name": "", "value": 70, "color": "green"},{"name": "", "value": 30, "color": "red"}],
                                            [{"name": "", "value": 25, "color": "black"}]]}
        return signals,indicators

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
        indicators = {"main_indicators": None,
                      "sub_indicators": [{"VMZI": vmzi},
                                         {"ADX": adx},
                                         {"RSI": rsi},
                                         {"ATR": atr}],
                      "sub_horizontal_lines":[[{"name": "", "value": 1.5, "color": "black"}],
                                              [{"name": "", "value": 25, "color": "black"}],
                                            [{"name": "", "value": 50, "color": "black"},{"name": "", "value": 70, "color": "green"},{"name": "", "value": 30, "color": "red"}],
                                              []
                                            ]}
        return signals,indicators

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
        indicators = {"main_indicators": {"SMA50":sma_50,"VAMA": vama},
                      "sub_indicators": None,
                      "sub_horizontal_lines":[]}
        return signals,indicators

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
        indicators = {"main_indicators": None,
                      "sub_indicators": [{"TSO": tso},{"ATR": atr}],
                      "sub_horizontal_lines":[
                          [{"name": "", "value": 0, "color": "black"}],
                          []
                                              ]}
        return signals,indicators

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
        indicators = {"main_indicators": None,
                      "sub_indicators": [
                          {"RSI": rsi, "RSI_BB_DOWN": bb_rsi_down, "BB_RSI_MID":bb_rsi_mid, "BB_RSI_UP":bb_rsi_up},
                          {"ATR": atr}],
                      "sub_horizontal_lines":[
                          [{"name": "", "value": 50, "color": "black"},{"name": "", "value": 70, "color": "green"},{"name": "", "value": 30, "color": "red"}],
                          []
                      ]}
        return signals,indicators

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
        indicators = {"main_indicators": None,
                      "sub_indicators": [
                          {"FDI":fdi},
                          {"macd_values": macd_values, "macd_signal": macd_signal},
                          {"RSI": rsi},
                          {"ADX": adx}],
                      "sub_horizontal_lines":[
                          [{"name": "", "value": 0, "color": "black"}],
                          [{"name": "", "value": 0, "color": "black"}],
                          [{"name": "", "value": 50, "color": "black"},{"name": "", "value": 70, "color": "green"},{"name": "", "value": 30, "color": "red"}],
                          [{"name": "", "value": 25, "color": "black"}]
                                              ]}
        return signals,indicators

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
        indicators = {"main_indicators": {"BB_DOWN":bb_down,"BB_MID":bb_mid,"BB_UP":bb_up},
                      "sub_indicators": [{"ATR": atr}],
                      "sub_horizontal_lines":[
                          [{"name": "", "value": 50, "color": "black"},{"name": "", "value": 70, "color": "green"},{"name": "", "value": 30, "color": "red"}],
                          []
                        ]}
        return signals,indicators

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
        indicators = {"main_indicators": {"SMA9":ma_9,"SMA50":ma_50},
                      "sub_indicators": [{"ATR": atr},{"ADX": adx}],
                      "sub_horizontal_lines":[
                          [],
                          [{"name": "", "value": 25, "color": "black"}]
                                              ]}
        return signals,indicators

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
        indicators = {"main_indicators": {"BB_DOWN":bb_down,"BB_MID":bb_mid,"BB_UP":bb_up},
                      "sub_indicators": [
                          {"DMO":dmo},
                          {"RSI": rsi},
                          {"ADX": adx},
                          {"ATR":atr}],
                      "sub_horizontal_lines":[
                          [{"name": "", "value": 1, "color": "black"}],
                          [{"name": "", "value": 50, "color": "black"},{"name": "", "value": 70, "color": "green"},{"name": "", "value": 30, "color": "red"}],
                          [{"name": "", "value": 25, "color": "black"}],
                          []
                                              ]}
        return signals,indicators

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
        indicators = {"main_indicators": {"BB_DOWN": bb_down, "BB_MID": bb_mid, "BB_UP": bb_up},
                      "sub_indicators": [{"ADX": adx}],
                      "sub_horizontal_lines":[
                          [{"name": "", "value": 30, "color": "black"}]
                                              ]}
        return signals,indicators

    @staticmethod
    def Alpha_Trend(high,low,close,vol):
        signals=[]
        alpha_trend = Indikator.Alpha_Trend(high, low, close,vol,use_volume=True)
        for i in range(len(close)):
            if alpha_trend[i] is None or alpha_trend[i-1] is None or alpha_trend[i-2] is None:
                signals.append(None)
            elif alpha_trend[i]>alpha_trend[i-2]:
                signals.append("BUY")
            elif alpha_trend[i]<alpha_trend[i-2]:
                signals.append("SELL")
            else:
                signals.append(False)
        indicators = {"main_indicators": {"Alpha_Trend": alpha_trend},
                      "sub_indicators": None,
                      "sub_horizontal_lines":None}
        return signals,indicators

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

        indicators = {"main_indicators": {"EMA50": ema_50},
                      "sub_indicators": [{"%K": stoch_k,"%D": stoch_d}],
                      "sub_horizontal_lines": [
                          [{"name": "", "value": 50, "color": "yellow"},{"name": "", "value": 30, "color": "red"},{"name": "", "value": 70, "color": "green"}]
                      ]}

        return signals,indicators

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
        indicators = {"main_indicators": None,
                      "sub_indicators": [{"CCI": cci},{"ATR": atr}],
                      "sub_horizontal_lines": [[]]}

        return signals,indicators

    @staticmethod
    def Local_Min_Max(high,low,close):
        # Sonuçları tutmak için liste
        signals = []

        # Tüm indikatörlerin bir defa hesaplanması
        local_min_max = IndikatorTest.local_min_max(high, low,14)
        bb_down,bb_mid,bb_up = Indikator.BB(close)
        adx=Indikator.ADX(high, low, close)
        ema50=Indikator.EMA(close,50)

        # Her fiyat noktası için sinyal hesaplama
        for i in range(len(high)):
            if local_min_max[i] is None or adx[i] is None or bb_mid[i] is None or ema50[i] is None:
                signals.append(None)
            elif close[i] > local_min_max[i] and adx[i]>30 and close[i]<bb_mid[i] and close[i]>ema50[i]:
                signals.append("BUY")
            elif close[i] < local_min_max[i]:
                signals.append("SELL")
            else:
                signals.append(False)
        indicators = {"main_indicators": {"MIN_MAX":local_min_max},
                      "sub_indicators": [],
                      "sub_horizontal_lines": [[]]}
        return signals, indicators

    @staticmethod
    def SignalMovingAvarage(high,low,close):
        # Sonuçları tutmak için liste
        signals = []

        # Tüm indikatörlerin bir defa hesaplanması
        ma,css = IndikatorTest.SignalMovingAverage(close,50)
        adx=Indikator.ADX(high, low, close)

        # Her fiyat noktası için sinyal hesaplama
        for i in range(len(high)):
            if ma[i] is None or adx[i] is None:
                signals.append(None)
            elif css[i]==1 and adx[i]>25:
                signals.append("BUY")
            elif css[i]==-1:
                signals.append("SELL")
            else:
                signals.append(False)
        indicators = {"main_indicators": {"MA": ma},
                      "sub_indicators": [{"SIGNAL":css}],
                      "sub_horizontal_lines": [[{"name": "", "value": 0, "color": "black"}]]}
        return signals, indicators

    @staticmethod
    def Super_Trend(high,low,close):
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
        indicators = {"main_indicators": {"Super_Trend": supertrend},
                      "sub_indicators": [{"Direction": direction}],
                      "sub_horizontal_lines":[
                          [{"name": "", "value": 0, "color": "black"}]
                                              ]}
        return signals,indicators

    @staticmethod
    def SqueezeMomentum(high, low, close):
        """
        Squeeze Momentum indikatörüne dayalı bir strateji.
        """
        signals = []

        # İndikatör hesaplamaları
        momentum, momentum_state, squeeze_state = IndikatorTest.SqueezeMomentumIndicator(close, high, low)
        adx=Indikator.ADX(high, low, close)
        rsi=IndikatorTest.RSI(close)
        bb_down,bb_mid,bb_up=Indikator.BB(close)
        ema50=Indikator.EMA(close,50)


        # Sinyal üretimi
        for i in range(len(close)):
            if momentum[i] is None or squeeze_state[i] is None or ema50[i] is None:
                signals.append(None)
            elif squeeze_state[i] == 1 and momentum[i]>0 and close[i]>ema50[i]:
                signals.append("BUY")  # Squeeze On ve pozitif momentum artışı
            elif squeeze_state[i] == -1 and momentum[i]<0 and close[i]<ema50[i]:
                signals.append("SELL")  # Squeeze Off ve negatif momentum artışı
            else:
                signals.append(False)

        # Göstergeler ve yatay çizgiler
        indicators = {
            "main_indicators": None,
            "sub_indicators": [{"Momentum State": momentum_state}, {"Squeeze State": squeeze_state}],
            "sub_horizontal_lines": [
                [{"name": "Zero Line", "value": 0, "color": "black"}]
            ],
        }

        return signals, indicators