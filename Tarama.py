from Binance import Binance
from Araclar import Araclar
from Stratejiler import Stratejiler
class Tarama:
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
                bb_close = Stratejiler.BB_Close(close)
                if bb_close == None or bb_close == False:
                    continue
                elif bb_close == "BUY":
                    resault_15m["BB(close)"]["BUY"].append(coin)
                elif bb_close == "SELL":
                    resault_15m["BB(close)"]["SELL"].append(coin)

                #   BB(RSI) Stratejisi
                bb_rsi = Stratejiler.BB_RSI(close)
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
                tso = Stratejiler.TSO(high,low, close)
                if tso == None or tso == False:
                    continue
                elif tso == "BUY":
                    resault_1h["TSO"]["BUY"].append(coin)
                elif tso == "SELL":
                    resault_1h["TSO"]["SELL"].append(coin)

                #   BB(RSI) Stratejisi
                bb_rsi = Stratejiler.BB_RSI(close)
                if bb_rsi == None or bb_rsi == False:
                    continue
                elif bb_rsi == "BUY":
                    resault_1h["BB(RSI)"]["BUY"].append(coin)
                elif bb_rsi == "SELL":
                    resault_1h["BB(RSI)"]["SELL"].append(coin)

                #   FDI Stratejisi
                fdi = Stratejiler.FDI(close)
                if fdi == None or fdi == False:
                    continue
                elif fdi == "BUY":
                    resault_1h["FDI"]["BUY"].append(coin)
                elif fdi == "SELL":
                    resault_1h["FDI"]["SELL"].append(coin)

                #   MACD Stratejisi
                macd = Stratejiler.MACD(close)
                if macd == None or macd == False:
                    continue
                elif macd == "BUY":
                    resault_1h["MACD"]["BUY"].append(coin)
                elif macd == "SELL":
                    resault_1h["MACD"]["SELL"].append(coin)

                #   MA_Cross Stratejisi
                ma_cross = Stratejiler.MA_Cross(high,low,close)
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
                dmo = Stratejiler.DMO(high,low,close)
                if dmo == None or dmo == False:
                    continue
                elif dmo == "BUY":
                    resault_4h["DMO"]["BUY"].append(coin)
                elif dmo == "SELL":
                    resault_4h["DMO"]["SELL"].append(coin)

                #   VMZI Stratejisi
                vmzi = Stratejiler.VMZI(high, low, close)
                if vmzi == None or vmzi == False:
                    continue
                elif vmzi == "BUY":
                    resault_4h["VMZI"]["BUY"].append(coin)
                elif vmzi == "SELL":
                    resault_4h["VMZI"]["SELL"].append(coin)

                #   VAMA Stratejisi
                vama = Stratejiler.VAMA(close)
                if vama == None or vama == False:
                    continue
                elif vama == "BUY":
                    resault_4h["VAMA"]["BUY"].append(coin)
                elif vama == "SELL":
                    resault_4h["VAMA"]["SELL"].append(coin)

                #   MA Cross Stratejisi
                ma_cross = Stratejiler.MA_Cross(high,low,close)
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
                macd=Stratejiler.MACD(close)
                if macd == None or macd == False:
                    continue
                elif macd == "BUY":
                    resault_1d["MACD"]["BUY"].append(coin)
                elif macd == "SELL":
                    resault_1d["MACD"]["SELL"].append(coin)

                #   DMO Stratejisi
                dmo = Stratejiler.DMO(high,low,close)
                if dmo == None or dmo == False:
                    continue
                elif dmo == "BUY":
                    resault_1d["DMO"]["BUY"].append(coin)
                elif dmo == "SELL":
                    resault_1d["DMO"]["SELL"].append(coin)

                #   VMZI Stratejisi
                vmzi = Stratejiler.VMZI(high, low, close)
                if vmzi == None or vmzi == False:
                    continue
                elif vmzi == "BUY":
                    resault_1d["VMZI"]["BUY"].append(coin)
                elif vmzi == "SELL":
                    resault_1d["VMZI"]["SELL"].append(coin)

                #   VAMA Stratejisi
                vama = Stratejiler.VAMA(close)
                if vama == None or vama == False:
                    continue
                elif vama == "BUY":
                    resault_1d["VAMA"]["BUY"].append(coin)
                elif vama == "SELL":
                    resault_1d["VAMA"]["SELL"].append(coin)

                #   MA Cross Stratejisi
                ma_cross = Stratejiler.MA_Cross(high,low,close)
                if ma_cross == None or ma_cross == False:
                    continue
                elif ma_cross == "BUY":
                    resault_1d["MA_Cross"]["BUY"].append(coin)
                elif ma_cross == "SELL":
                    resault_1d["MA_Cross"]["SELL"].append(coin)

                #   FDI Stratejisi
                fdi = Stratejiler.FDI(close)
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
            if len(resault_1h['MA_Cross']['BUY']) > 0 or len(resault_1h['MA_Cross']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"TSO\n"
                          f"BUY:\n"
                          f"{resault_1h['MA_Cross']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_1h['MA_Cross']['SELL']}\n"
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
            if len(resault_4h['MA_Cross']['BUY']) > 0 or len(resault_4h['MA_Cross']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"MA Cross\n"
                          f"BUY:\n"
                          f"{resault_4h['MA_Cross']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_4h['MA_Cross']['SELL']}\n"
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
            if len(resault_1d['MA_Cross']['BUY']) > 0 or len(resault_1d['MA_Cross']['SELL']) > 0:
                gonder = True
                mesaj = (mesaj +
                         (f"MA Cross\n"
                          f"BUY:\n"
                          f"{resault_1d['MA_Cross']['BUY']}\n"
                          f"SELL:\n"
                          f"{resault_1d['MA_Cross']['SELL']}\n"
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