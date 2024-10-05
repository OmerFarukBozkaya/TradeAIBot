import time
import traceback
from Binance import Binance
from Indikator import Indikator
from Araclar import Araclar
zaman_dilimleri={"1m":60,"3m":180,"5m":300,"15m":900,"30m":1800,"1h":3600,"2h":7200,"4h":14400,"6h":21600,"8h":28800,"12h":43200,"1d":86400,"3d":259200,"1w":604800,"1M":2419200}

class Al_Sat:
    def BB_RSI(self,coinlist,periyot,gercek,sonislem,nakit):
        binance = Binance()
        araclar= Araclar()
        while True:
            print(gercek,periyot,"Calisiyor ...",time.ctime(time.time()))
            try:
                #Mumun olusmasini bekleme alani
                if(time.time()%zaman_dilimleri[periyot]>300):
                    time.sleep(zaman_dilimleri[periyot]-(time.time()%zaman_dilimleri[periyot]))

                #Sahip olduğum coinler
                sahip_olduklarim = binance.sahip_olduklarim()


                #Taranacaklardan sahip olduklarimi cikar
                for sil in sahip_olduklarim.keys():
                    try:
                        coinlist.remove(sil[0])
                    except:
                        continue

                #Tarama
                for coin in coinlist:
                    #Data
                    close=binance.data(coin,1000,periyot,4)

                    #Indikator
                    rsi=Indikator.RSI(close)
                    bb=Indikator.BB(rsi)

                    if(sonislem=="SAT"):
                        if (bb[0][-1] > rsi[-1]):   #ALIM SARTI
                            sonislem="AL"
                            #Adet hesaplama
                            adet = round((nakit / close[-1]), binance.minimum_hareket(float(binance.client.get_symbol_info(coin)["filters"][2]["minQty"])))

                            if (gercek):  # Eger islem gercek ise borsaya emir gönderecek
                                binance.al(coin,adet)
                            araclar.mail_gonder("AL | BB_RSI Al-sat "+periyot, coin + " " + str(adet) + " alindi \n" + "Maliyet : " + str(close[-1]) + " USDT")
                            break
                    else:
                        if (bb[2][-2] < rsi[-2] and bb[2][-1] > rsi[-1]):  # SATIM SARTI
                            sonislem = "SAT"

                            #Adet hesaplama
                            mevcut_adedim=sahip_olduklarim[coin]
                            basamak = float(binance.client.get_symbol_info(coin)["filters"][2]["minQty"])
                            adim = binance.minimum_hareket(basamak)
                            adet = round(mevcut_adedim - (mevcut_adedim % basamak), adim)

                            if (gercek):  # Eger islem gercek ise borsaya emir gönderecek
                                binance.sat(coin,adet)
                            araclar.mail_gonder("SAT | BB_RSI Al-sat "+periyot,coin + " " + str(adet) + " satildi")
                            break
            except :
                # Hata bildirimi
                hata = traceback.format_exc()
                araclar.mail_gonder("HATA | BB_RSI Al-sat "+periyot, hata)
                #Tekrar calistir
                self.BB_RSI(coinlist, periyot,gercek,sonislem,nakit)

class Tarama:

    def tarama_bildir_coin(self,coinlist, periyot, mumbekle):
        bb_rsi = []
        macd_ema = []
        binance = Binance()
        araclar = Araclar()
        print(periyot, "Tarama Calisiyor [Coin]...", time.ctime(time.time()))
        while True:
            try:
                # Mumun olusmasini bekleme alani
                if mumbekle:
                    if (time.time() % zaman_dilimleri[periyot] > 120):
                        time.sleep(zaman_dilimleri[periyot] - (time.time() % zaman_dilimleri[periyot]))
                for coin in coinlist:
                    #   Veriler
                    en_kucuk = 99999999
                    en_buyuk = 0
                    high = binance.data(coin, 1000, periyot, 2)
                    low = binance.data(coin, 1000, periyot, 3)
                    close = binance.data(coin, 1000, periyot, 4)
                    close_day = binance.data(coin, 1000, "1d", 4)
                    if (len(close) < 35):
                        continue

                    for fiyat in close[-144:]:
                        if (fiyat < en_kucuk):
                            en_kucuk = fiyat
                        elif (fiyat > en_buyuk):
                            en_buyuk = fiyat

                    fiyatlar_seviyeler = {}
                    seviyeler = [0.236, 0.382, 0.5, 0.618, 0.786]
                    for j in seviyeler:
                        fib_fiyat = en_kucuk - (en_kucuk - en_buyuk) * j
                        fiyatlar_seviyeler[j] = fib_fiyat

                    #   BB-RSI
                    rsi = Indikator.RSI(close)
                    bb = Indikator.BB(rsi)
                    if (bb[0][-1] > rsi[-1] and ((close[-1] <= fiyatlar_seviyeler[0.236]) or (
                            close[-1] <= fiyatlar_seviyeler[0.382] * 1.01 and close[-1] >= fiyatlar_seviyeler[
                        0.382] * 0.99) or (close[-1] <= fiyatlar_seviyeler[0.5] * 1.01 and close[-1] >=
                                           fiyatlar_seviyeler[0.5] * 0.99) or (
                                                         close[-1] <= fiyatlar_seviyeler[0.618] * 1.01 and close[-1] >=
                                                         fiyatlar_seviyeler[0.618] * 0.99))):
                        if (len(bb_rsi) == 0):
                            bb_rsi.append(coin + " " + str(close[-1]))
                        elif (rsi[-1] < 30):
                            bb_rsi.append(coin + " " + str(close[-1]))
                    #   MACD-EMA
                    Macd = Indikator.MACD(close)
                    macd = Macd[0]
                    sinyal = Macd[1]
                    ema200 = Indikator.EMA(close, 200)
                    if (close[-1] > ema200[-1] and macd[-1] > sinyal[-1] and macd[-2] < sinyal[-2] and macd[-1] > 0):
                        macd_ema.append(coin + " " + str(close[-1]))

                mesaj = "BB-RSI : " + str(bb_rsi) + "\n" + "MACD-EMA[200] : " + str(macd_ema)

                araclar.mail_gonder("Robot | Tarama [Coin] " + periyot, mesaj)

                #   Temizleme
                bb_rsi = []
                macd_ema = []
            except:
                hata = traceback.format_exc()
                araclar.mail_gonder("HATA | Tarama [Coin] " + periyot, hata)
                self.tarama_bildir_coin(coinlist, periyot, mumbekle)
