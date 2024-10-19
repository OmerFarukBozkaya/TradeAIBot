from Indikator import Indikator
from Binance import Binance
from Araclar import Araclar
class Tarama:
    @staticmethod
    def MACD(close):
        macd=Indikator.MACD(close)
        macd_values = macd[0]
        macd_signal = macd[1]
        rsi=Indikator.RSI(close)
        if macd_signal[-1] is not None and macd_values[-1] is not None and rsi[-1] is not None:
            if macd_values[-1] > macd_signal[-1] and rsi[-1]>50:
                return "BUY"
            elif macd_values[-1] < macd_signal[-1]:
                return "SELL"
            else:
                return False
        else:
            return None
    @staticmethod
    def VMZI(high,low,close):
        vmzi=Indikator.VMZI(close)
        adx=Indikator.ADX(high,low,close)
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
    def TSO(high,low,close):
        tso = Indikator.TSO(high,low,close)
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
        bb_rsi=Indikator.BB(rsi)
        bb_rsi_down=bb_rsi[0]
        bb_rsi_up=bb_rsi[2]
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
        macd= Indikator.MACD(close)
        macd_values = macd[0]
        macd_signal = macd[1]
        if fdi[-2] is not None and rsi[-1] is not None and macd_values[-1] is not None and macd_signal[-1] is not None:
            if fdi[-2] > 0 and fdi[-2] < fdi[-1] and rsi[-1] > 40 and macd_values>macd_signal:
                return "BUY"
            elif fdi[-2] < 0 and fdi[-2] > fdi[-1] and rsi[-1] < 60 and macd_values<macd_signal:
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
    def MA_Cross(high,low,close):
        ma_9 = Indikator.SMA(close,9)
        ma_50 = Indikator.SMA(close,50)
        adx = Indikator.ADX(high,low,close)
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
        dmo=Indikator.DMO(close)
        adx=Indikator.ADX(high,low,close)
        rsi=Indikator.RSI(close)
        atr=Indikator.ATR(high,low, close)
        atr_14=Indikator.SMA(atr,14)
        bb = Indikator.BB(close)
        bb_down = bb[0]
        bb_mid = bb[1]
        bb_up = bb[2]
        if dmo[-1] is not None and adx[-1] is not None and rsi[-1] is not None and bb_down[-1] is not None:
            if dmo[-1] > 1.0 and adx[-1] > 20 and rsi[-1] > 50 and close[-1] >= bb_up[-1]:
                return "BUY"
            elif dmo[-1] < 0.8 or adx[-1] < 20 or (rsi[-1]<50 and close[-1] <= bb_down[-1]):
                return "SELL"
            else:
                return False
        else:
            return None

    @staticmethod
    def Tara(coinlist,periyot):
        binance = Binance()
        araclar = Araclar()
        resault_15m={"BB(close)":{'BUY':[],'SELL':[]},
                 "TSO":{'BUY':[],'SELL':[]},
                 "BB(RSI)":{'BUY':[],'SELL':[]},
                 "FDI":{'BUY':[],'SELL':[]},
                 "VMZI":{'BUY':[],'SELL':[]},
                 "MACD":{'BUY':[],'SELL':[]},
                 "VAMA":{'BUY':[],'SELL':[]},
                 "MA_Cross": {'BUY': [], 'SELL': []},
                 "DMO": {'BUY': [], 'SELL': []},
        }
        resault_1h = {"BB(close)":{'BUY':[],'SELL':[]},
                 "TSO":{'BUY':[],'SELL':[]},
                 "BB(RSI)":{'BUY':[],'SELL':[]},
                 "FDI":{'BUY':[],'SELL':[]},
                 "VMZI":{'BUY':[],'SELL':[]},
                 "MACD":{'BUY':[],'SELL':[]},
                 "VAMA":{'BUY':[],'SELL':[]},
                 "MA_Cross": {'BUY': [], 'SELL': []},
                 "DMO": {'BUY': [], 'SELL': []},
        }
        resault_4h = {"BB(close)":{'BUY':[],'SELL':[]},
                 "TSO":{'BUY':[],'SELL':[]},
                 "BB(RSI)":{'BUY':[],'SELL':[]},
                 "FDI":{'BUY':[],'SELL':[]},
                 "VMZI":{'BUY':[],'SELL':[]},
                 "MACD":{'BUY':[],'SELL':[]},
                 "VAMA":{'BUY':[],'SELL':[]},
                 "MA_Cross": {'BUY': [], 'SELL': []},
                 "DMO": {'BUY': [], 'SELL': []},
        }
        resault_1d = {"BB(close)":{'BUY':[],'SELL':[]},
                 "TSO":{'BUY':[],'SELL':[]},
                 "BB(RSI)":{'BUY':[],'SELL':[]},
                 "FDI":{'BUY':[],'SELL':[]},
                 "VMZI":{'BUY':[],'SELL':[]},
                 "MACD":{'BUY':[],'SELL':[]},
                 "VAMA":{'BUY':[],'SELL':[]},
                 "MA_Cross": {'BUY': [], 'SELL': []},
                 "DMO": {'BUY': [], 'SELL': []},
        }

        for coin in coinlist:
            if periyot == "15m":
                #   BB(close),BB(RSI)
                close = binance.data(coin, 1000, periyot, 4)
                low = binance.data(coin, 1000, periyot, 3)
                high = binance.data(coin, 1000, periyot, 2)

                #   BB(close) Stratejisi
                bb_close = Tarama.BB_Close(close)
                if bb_close == None or bb_close == False:
                    continue
                elif bb_close == "BUY":
                    resault_15m["BB(close)"]["BUY"].append(coin)
                elif bb_close == "SELL":
                    resault_15m["BB(close)"]["SELL"].append(coin)

                #   BB(RSI) Stratejisi
                bb_rsi = Tarama.BB_RSI(close)
                if bb_rsi == None or bb_rsi == False:
                    continue
                elif bb_rsi == "BUY":
                    resault_15m["BB(RSI)"]["BUY"].append(coin)
                elif bb_rsi == "SELL":
                    resault_15m["BB(RSI)"]["SELL"].append(coin)

            elif periyot == "1h":
                #   TSO,BB(RSI),FDI,MACD,MA Cross
                close = binance.data(coin, 1000, periyot, 4)
                low = binance.data(coin, 1000, periyot, 3)
                high = binance.data(coin, 1000, periyot, 2)

                #   TSO Stratejisi
                tso = Tarama.TSO(high,low, close)
                if tso == None or tso == False:
                    continue
                elif tso == "BUY":
                    resault_1h["TSO"]["BUY"].append(coin)
                elif tso == "SELL":
                    resault_1h["TSO"]["SELL"].append(coin)

                #   BB(RSI) Stratejisi
                bb_rsi = Tarama.BB_RSI(close)
                if bb_rsi == None or bb_rsi == False:
                    continue
                elif bb_rsi == "BUY":
                    resault_1h["BB(RSI)"]["BUY"].append(coin)
                elif bb_rsi == "SELL":
                    resault_1h["BB(RSI)"]["SELL"].append(coin)

                #   FDI Stratejisi
                fdi = Tarama.FDI(close)
                if fdi == None or fdi == False:
                    continue
                elif fdi == "BUY":
                    resault_1h["FDI"]["BUY"].append(coin)
                elif fdi == "SELL":
                    resault_1h["FDI"]["SELL"].append(coin)

                #   MACD Stratejisi
                macd = Tarama.MACD(close)
                if macd == None or macd == False:
                    continue
                elif macd == "BUY":
                    resault_1h["MACD"]["BUY"].append(coin)
                elif macd == "SELL":
                    resault_1h["MACD"]["SELL"].append(coin)

                #   MA Cross Stratejisi
                ma_cross = Tarama.MA_Cross(high,low,close)
                if ma_cross == None or ma_cross == False:
                    continue
                elif ma_cross == "BUY":
                    resault_1h["MA_Cross"]["BUY"].append(coin)
                elif ma_cross == "SELL":
                    resault_1h["MA_Cross"]["SELL"].append(coin)

            elif periyot == "4h":
                #   DMO,VMZI,VAMA,Ma Cross
                close = binance.data(coin, 1000, periyot, 4)
                low = binance.data(coin, 1000, periyot, 3)
                high = binance.data(coin, 1000, periyot, 2)

                #   DMO Stratejisi
                dmo = Tarama.DMO(high,low,close)
                if dmo == None or dmo == False:
                    continue
                elif dmo == "BUY":
                    resault_4h["DMO"]["BUY"].append(coin)
                elif dmo == "SELL":
                    resault_4h["DMO"]["SELL"].append(coin)

                #   VMZI Stratejisi
                vmzi = Tarama.VMZI(high, low, close)
                if vmzi == None or vmzi == False:
                    continue
                elif vmzi == "BUY":
                    resault_4h["VMZI"]["BUY"].append(coin)
                elif vmzi == "SELL":
                    resault_4h["VMZI"]["SELL"].append(coin)

                #   VAMA Stratejisi
                vama = Tarama.VAMA(close)
                if vama == None or vama == False:
                    continue
                elif vama == "BUY":
                    resault_4h["VAMA"]["BUY"].append(coin)
                elif vama == "SELL":
                    resault_4h["VAMA"]["SELL"].append(coin)

                #   MA Cross Stratejisi
                ma_cross = Tarama.MA_Cross(high,low,close)
                if ma_cross == None or ma_cross == False:
                    continue
                elif ma_cross == "BUY":
                    resault_4h["MA_Cross"]["BUY"].append(coin)
                elif ma_cross == "SELL":
                    resault_4h["MA_Cross"]["SELL"].append(coin)

            elif periyot == "1d":
                #   MACD,DMO,VMZI,VAMA,Ma Cross,FDI
                close = binance.data(coin, 1000, periyot, 4)
                low = binance.data(coin, 1000, periyot, 3)
                high = binance.data(coin, 1000, periyot, 2)

                #   MACD Stratejisi
                macd=Tarama.MACD(close)
                if macd == None or macd == False:
                    continue
                elif macd == "BUY":
                    resault_1d["MACD"]["BUY"].append(coin)
                elif macd == "SELL":
                    resault_1d["MACD"]["SELL"].append(coin)

                #   DMO Stratejisi
                dmo = Tarama.DMO(high,low,close)
                if dmo == None or dmo == False:
                    continue
                elif dmo == "BUY":
                    resault_1d["DMO"]["BUY"].append(coin)
                elif dmo == "SELL":
                    resault_1d["DMO"]["SELL"].append(coin)

                #   VMZI Stratejisi
                vmzi = Tarama.VMZI(high, low, close)
                if vmzi == None or vmzi == False:
                    continue
                elif vmzi == "BUY":
                    resault_1d["VMZI"]["BUY"].append(coin)
                elif vmzi == "SELL":
                    resault_1d["VMZI"]["SELL"].append(coin)

                #   VAMA Stratejisi
                vama = Tarama.VAMA(close)
                if vama == None or vama == False:
                    continue
                elif vama == "BUY":
                    resault_1d["VAMA"]["BUY"].append(coin)
                elif vama == "SELL":
                    resault_1d["VAMA"]["SELL"].append(coin)

                #   MA Cross Stratejisi
                ma_cross = Tarama.MA_Cross(high,low,close)
                if ma_cross == None or ma_cross == False:
                    continue
                elif ma_cross == "BUY":
                    resault_1d["MA_Cross"]["BUY"].append(coin)
                elif ma_cross == "SELL":
                    resault_1d["MA_Cross"]["SELL"].append(coin)

                #   FDI Stratejisi
                fdi = Tarama.FDI(close)
                if fdi == None or fdi == False:
                    continue
                elif fdi == "BUY":
                    resault_1d["FDI"]["BUY"].append(coin)
                elif fdi == "SELL":
                    resault_1d["FDI"]["SELL"].append(coin)

        if periyot == "15m":
            #   BB(close),BB(RSI)
            mesaj=""
            gonder = False
            if len(resault_15m['BB(close)']['BUY'])>0 or len(resault_15m['BB(close)']['SELL']) >0:
                gonder=True
                mesaj = (mesaj +
                         (f"BB(Close)\n"
                         f"BUY:\n"
                         f"{resault_15m['BB(close)']['BUY']}\n"
                         f"SELL:\n"
                         f"{resault_15m['BB(close)']['SELL']}\n"
                         ))
            if len(resault_15m['BB(RSI)']['BUY'])>0 or len(resault_15m['BB(RSI)']['SELL']) >0:
                gonder=True
                mesaj = (mesaj +
                         (f"BB(RSI)\n"
                         f"BUY:\n"
                         f"{resault_15m['BB(RSI)']['BUY']}\n"
                         f"SELL:\n"
                         f"{resault_15m['BB(RSI)']['SELL']}\n"
                         ))
            if gonder:
                araclar.mail_gonder(f"Tarama |{periyot}",mesaj)
        elif periyot == "1h":
            #   TSO,BB(RSI),FDI,MACD,MA Cross
            mesaj = ""
            gonder = False
            if len(resault_1h['TSO']['BUY']) > 0 or len(resault_1h['TSO']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"TSO\n"
                          f"BUY:\n"
                          f"{resault_1h['TSO']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_1h['TSO']['SELL']}\n"
                          ))
            if len(resault_1h['BB(RSI)']['BUY']) > 0 or len(resault_1h['BB(RSI)']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"BB(RSI)\n"
                          f"BUY:\n"
                          f"{resault_1h['BB(RSI)']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_1h['BB(RSI)']['SELL']}\n"
                          ))
            if len(resault_1h['FDI']['BUY']) > 0 or len(resault_1h['FDI']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"FDI\n"
                          f"BUY:\n"
                          f"{resault_1h['FDI']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_1h['FDI']['SELL']}\n"
                          ))
            if len(resault_1h['MACD']['BUY']) > 0 or len(resault_1h['MACD']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"MACD\n"
                          f"BUY:\n"
                          f"{resault_1h['MACD']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_1h['MACD']['SELL']}\n"
                          ))
            if len(resault_1h['MA Cross']['BUY']) > 0 or len(resault_1h['MA Cross']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"TSO\n"
                          f"BUY:\n"
                          f"{resault_1h['MA Cross']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_1h['MA Cross']['SELL']}\n"
                          ))
            if gonder:
                araclar.mail_gonder(f"Tarama |{periyot}", mesaj)

        elif periyot == "4h":
            #   DMO,VMZI,VAMA,Ma Cross
            mesaj = ""
            gonder = False
            if len(resault_4h['DMO']['BUY']) > 0 or len(resault_4h['DMO']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"DMO\n"
                          f"BUY:\n"
                          f"{resault_4h['DMO']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_4h['DMO']['SELL']}\n"
                          ))
            if len(resault_4h['VMZI']['BUY']) > 0 or len(resault_4h['VMZI']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"VMZI\n"
                          f"BUY:\n"
                          f"{resault_4h['VMZI']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_4h['VMZI']['SELL']}\n"
                          ))
            if len(resault_4h['VAMA']['BUY']) > 0 or len(resault_4h['VAMA']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"VAMA\n"
                          f"BUY:\n"
                          f"{resault_4h['VAMA']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_4h['VAMA']['SELL']}\n"
                          ))
            if len(resault_4h['MA Cross']['BUY']) > 0 or len(resault_4h['MA Cross']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"MA Cross\n"
                          f"BUY:\n"
                          f"{resault_4h['MA Cross']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_4h['MA Cross']['SELL']}\n"
                          ))
            if gonder:
                araclar.mail_gonder(f"Tarama |{periyot}", mesaj)
        elif periyot == "1d":
            #   MACD,DMO,VMZI,VAMA,Ma Cross,FDI
            mesaj = ""
            gonder = False
            if len(resault_1d['MACD']['BUY']) > 0 or len(resault_1d['MACD']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"MACD\n"
                          f"BUY:\n"
                          f"{resault_1d['MACD']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_1d['MACD']['SELL']}\n"
                          ))
            if len(resault_1d['DMO']['BUY']) > 0 or len(resault_1d['DMO']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"DMO\n"
                          f"BUY:\n"
                          f"{resault_1d['DMO']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_1d['DMO']['SELL']}\n"
                          ))
            if len(resault_1d['VMZI']['BUY']) > 0 or len(resault_1d['VMZI']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"VMZI\n"
                          f"BUY:\n"
                          f"{resault_1d['VMZI']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_1d['VMZI']['SELL']}\n"
                          ))
            if len(resault_1d['VAMA']['BUY']) > 0 or len(resault_1d['VAMA']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"VAMA\n"
                          f"BUY:\n"
                          f"{resault_1d['VAMA']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_1d['VAMA']['SELL']}\n"
                          ))
            if len(resault_1d['MA Cross']['BUY']) > 0 or len(resault_1d['MA Cross']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"MA Cross\n"
                          f"BUY:\n"
                          f"{resault_1d['MA Cross']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_1d['MA Cross']['SELL']}\n"
                          ))
            if len(resault_1d['FDI']['BUY']) > 0 or len(resault_1d['FDI']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"FDI\n"
                          f"BUY:\n"
                          f"{resault_1d['FDI']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_1d['FDI']['SELL']}\n"
                          ))
            if gonder:
                araclar.mail_gonder(f"Tarama |{periyot}", mesaj)