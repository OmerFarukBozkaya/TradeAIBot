import time
import traceback
from Binance import Binance
from Indikator import Indikator
from Araclar import Araclar
import logging

zaman_dilimleri = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
    "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800, "1M": 2419200
}
# Log ayarları
logging.basicConfig(filename='trading_log.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# İşlem geçmişi için ayrı bir logger oluştur
islemgecmisi = logging.getLogger('islemgecmisi')
handler = logging.FileHandler('islem_gecmisi.log')
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
islemgecmisi.addHandler(handler)

class Al_Sat:
    def iskelet(self, coinlist, periyot, gercek, sonislem, nakit,stop_lose_var=True,stop_takip=False, mumbekle=True, alis_fiyati=0):
        """
        Değiştirilmesi gereken değerler

        0)Stratejinin adı
        1)Alıncak fiyat verileri
        2)Indikatörler ve indikatörün sağlıklı sonuç verebilmesi için merekli olan minimum veri miktarı
        3)Alım şartı
        4)Stop lose takip etmesi için gerekli şart
        5)Stop lose değeri hesaplama
        6)Stop lose varsayılan değeri hesaplama
        7)Hedeflenen satış şartı
        8)Hata oluştuğunda tekrardan çağırılacak fonksiyon

        """
        """        
        :param coinlist: list  
        :param periyot: string
        :param gercek: bool
        :param sonislem: string
        :param nakit: float
        :param stop_lose_var: bool
        :param stop_takip: bool
        :param mumbekle: bool
        :param alis_fiyati: float
        """
        binance = Binance()
        araclar = Araclar()
        alis=alis_fiyati
        strateji_adi = "iskelet"    # [0]
        logging.info(f"{periyot} {strateji_adi} Calisiyor ... {gercek}")
        print(f"{periyot} {strateji_adi} Calisiyor ... {gercek}", time.ctime())
        while sonislem == "AL":
            try:
                if mumbekle:
                    # Mumun oluşmasını bekle
                    if time.time() % zaman_dilimleri[periyot] > 300 or True:
                        time.sleep(zaman_dilimleri[periyot] - (time.time() % zaman_dilimleri[periyot]))

                sahip_olduklarim = binance.sahip_olduklarim()

                if sonislem == "SAT":
                    # Eğer alım yapacaksam sahip olunan coinleri liste dışı bırak
                    for sil in sahip_olduklarim.keys():
                        try:
                            coinlist.remove(sil[0])
                        except:
                            continue

                for coin in coinlist:
                    # Veri çek
                    # [1]
                    close = binance.data(coin, 1000, periyot, 4)

                    # [2]
                    if len(close)<50:
                        continue
                    # İndikatörleri hesapla
                    """
                    Gerekli indikatörler burda hesaplanacak
                    """

                    # AL işlemi
                    if sonislem == "SAT":
                        if close : # Alım şartı [3]
                            sonislem = "AL"
                            adet = round((nakit / close[-1]), binance.minimum_hareket(
                                float(binance.client.get_symbol_info(coin)["filters"][1]["minQty"])))

                            logging.info(f"AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
                            islemgecmisi.info(f"{strateji_adi} AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
                            alis=close[-1]
                            if gercek:  # Gerçek işlem mi kontrol et
                                print("Gercekten alindi")
                                binance.al(coin, adet)

                            araclar.mail_gonder(f"AL | {strateji_adi} {periyot}", f"{coin} alindi, Maliyet: {close[-1]} USDT")
                            coinlist = [coin]
                            break

                    # Satış işlemleri
                    else:
                        if stop_lose_var:
                            # Stop-Lose hesapla
                            if (close or stop_takip): # Takip etmesi için gereken şart  # [4]
                                stop_lose = close  # Yeni stop lose     # [5]
                                stop_takip = True
                            else:
                                stop_lose = close # Varsayılan stop lose    # [6]

                            # Stop-Lose
                            if close[-1] < stop_lose: # Stop lose kontrolü
                                sonislem = "SAT"
                                adet = 0
                                adim = binance.minimum_hareket(
                                    float(binance.client.get_symbol_info(coin)["filters"][1]["minQty"]))
                                logging.info(f"SAT [Stop Lose]| {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
                                islemgecmisi.info(
                                    f"{strateji_adi} SAT [Stop Lose] | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}, Kar/Zarar: {round((((close[-1]/alis)-1) * 100),2)} %")
                                if gercek:
                                    print("Gercekten satildi")
                                    mevcut_adedim = sahip_olduklarim[coin]
                                    adet = round(mevcut_adedim - (mevcut_adedim % float(adim)), adim)
                                    binance.sat(coin, adet)

                                araclar.mail_gonder(f"SAT [Stop Lose] | {strateji_adi} {periyot}", f"{coin} satildi")
                                return
                        # SAT işlemi
                        if close:   # Hedeflenen satış şartı    # [7]
                            sonislem = "SAT"
                            adet = 0
                            adim = binance.minimum_hareket(
                                float(binance.client.get_symbol_info(coin)["filters"][1]["minQty"]))
                            logging.info(f"SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
                            islemgecmisi.info(f"{strateji_adi} SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
                            if gercek:
                                print("Gercekten satildi")
                                mevcut_adedim = sahip_olduklarim[coin]
                                adet = round(mevcut_adedim - (mevcut_adedim % float(adim)), adim)
                                binance.sat(coin, adet)

                            araclar.mail_gonder(f"SAT | {strateji_adi} {periyot}", f"{coin} satildi")
                            return

            except Exception:
                # Hata durumunda tekrar çalıştırma
                hata = traceback.format_exc()
                logging.error(f"Hata oluştu: {hata}")
                araclar.mail_gonder(f"HATA | {strateji_adi} {periyot}", hata)
                self.iskelet(coinlist, periyot, gercek, sonislem, nakit,stop_lose_var,stop_takip,mumbekle,alis)     # [8]
    def BB_RSI(self, coinlist, periyot, gercek, sonislem, nakit, mumbekle=True):
        binance = Binance()
        araclar = Araclar()
        logging.info(f"{periyot} BB_RSI Calisiyor ... {gercek}")
        print(f"{periyot} BB_RSI Calisiyor ... {gercek}", time.ctime())
        while sonislem == "AL":
            try:
                if mumbekle:
                    # Mumun oluşmasını bekle
                    if time.time() % zaman_dilimleri[periyot] > 300 or True:
                        time.sleep(zaman_dilimleri[periyot] - (time.time() % zaman_dilimleri[periyot]))

                sahip_olduklarim = binance.sahip_olduklarim()

                if sonislem == "SAT":
                    # Sahip olunan coinleri liste dışı bırak
                    for sil in sahip_olduklarim.keys():
                        try:
                            coinlist.remove(sil[0])
                        except:
                            continue

                for coin in coinlist:
                    # Veri çek
                    close = binance.data(coin, 1000, periyot, 4)

                    # RSI ve BB indikatörlerini hesapla
                    rsi = Indikator.RSI(close)
                    bb = Indikator.BB(rsi)

                    # AL işlemi
                    if sonislem == "SAT":
                        if bb[0][-1] > rsi[-1]:
                            sonislem = "AL"
                            adet = round((nakit / close[-1]), binance.minimum_hareket(
                                float(binance.client.get_symbol_info(coin)["filters"][1]["minQty"])))

                            logging.info(f"AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
                            islemgecmisi.info(f"BB_RSI AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
                            if gercek:  # Gerçek işlem mi kontrol et
                                print("Gercekten alindi")
                                binance.al(coin, adet)

                            araclar.mail_gonder(f"AL | BB_RSI {periyot}", f"{coin} alindi, Maliyet: {close[-1]} USDT")
                            coinlist = [coin]
                            break

                    # SAT işlemi
                    else:
                        if bb[2][-2] < rsi[-2] and bb[2][-1] > rsi[-1]:
                            sonislem = "SAT"
                            adet = 0
                            adim = binance.minimum_hareket(
                                float(binance.client.get_symbol_info(coin)["filters"][1]["minQty"]))
                            logging.info(f"SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
                            islemgecmisi.info(f"BB_RSI SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
                            if gercek:
                                print("Gercekten satildi")
                                mevcut_adedim = sahip_olduklarim[coin]
                                adet = round(mevcut_adedim - (mevcut_adedim % float(adim)), adim)
                                binance.sat(coin, adet)

                            araclar.mail_gonder(f"SAT | BB_RSI {periyot}", f"{coin} satildi")
                            return
            except Exception:
                # Hata durumunda tekrar çalıştırma
                hata = traceback.format_exc()
                logging.error(f"Hata oluştu: {hata}")
                araclar.mail_gonder(f"HATA | BB_RSI {periyot}", hata)
                self.BB_RSI(coinlist, periyot, gercek, sonislem, nakit)
    def MACD_EMA(self, coinlist, periyot, gercek, sonislem, nakit, mumbekle=True):
        binance = Binance()
        araclar = Araclar()
        templist = coinlist
        logging.info(f"{periyot} MACD_EMA Calisiyor ... {gercek}")
        print(f"{periyot} MACD_EMA Calisiyor ... {gercek}", time.ctime())
        while True:
            try:
                if mumbekle:
                    if time.time() % zaman_dilimleri[periyot] > 300:
                        time.sleep(zaman_dilimleri[periyot] - (time.time() % zaman_dilimleri[periyot]))

                sahip_olduklarim = binance.sahip_olduklarim()

                if sonislem == "SAT":
                    for sil in sahip_olduklarim.keys():
                        try:
                            coinlist.remove(sil[0])
                        except:
                            continue

                for coin in coinlist:
                    close = binance.data(coin, 1000, periyot, 4)
                    macd, sinyal = Indikator.MACD(close)
                    ema200 = Indikator.EMA(close, 200)

                    if sonislem == "SAT":
                        if macd[-1] > sinyal[-1] and macd[-2] < sinyal[-2] and close[-1] > ema200[-1]:
                            sonislem = "AL"
                            adet = round((nakit / close[-1]), binance.minimum_hareket(
                                float(binance.client.get_symbol_info(coin)["filters"][1]["minQty"])))

                            logging.info(f"AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
                            islemgecmisi.info(f"MACD_EMA AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
                            if gercek:
                                binance.al(coin, adet)

                            araclar.mail_gonder(f"AL | MACD_EMA {periyot}", f"{coin} alindi, Maliyet: {close[-1]} USDT")
                            coinlist = [coin]
                            break
                    else:
                        if macd[-1] < sinyal[-1] and macd[-2] > sinyal[-2]:
                            sonislem = "SAT"
                            adim = binance.minimum_hareket(float(binance.client.get_symbol_info(coin)["filters"][1]["minQty"]))
                            mevcut_adedim = sahip_olduklarim[coin]
                            adet = round(mevcut_adedim - (mevcut_adedim % float(adim)), adim)

                            logging.info(f"SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
                            islemgecmisi.info(f"MACD_EMA SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
                            if gercek:
                                binance.sat(coin, adet)

                            profit_loss = (adet * close[-1]) - nakit
                            self.update_performance("MACD_EMA", profit_loss)
                            araclar.mail_gonder(f"SAT | MACD_EMA {periyot}", f"{coin} satildi")
                            coinlist = templist
                            break
            except Exception:
                hata = traceback.format_exc()
                logging.error(f"Hata oluştu: {hata}")
                araclar.mail_gonder(f"HATA | MACD_EMA {periyot}", hata)
                self.MACD_EMA(coinlist, periyot, gercek, sonislem, nakit)
    def Momentum_StochRSI(self, coinlist, periyot, gercek, sonislem, nakit, mumbekle=True):
        binance = Binance()
        araclar = Araclar()
        templist = coinlist
        logging.info(f"{periyot} Momentum_StochRSI Calisiyor ... {gercek}")
        print(f"{periyot} Momentum_StochRSI Calisiyor ... {gercek}", time.ctime())
        while True:
            try:
                if mumbekle:
                    if time.time() % zaman_dilimleri[periyot] > 300:
                        time.sleep(zaman_dilimleri[periyot] - (time.time() % zaman_dilimleri[periyot]))

                sahip_olduklarim = binance.sahip_olduklarim()

                if sonislem == "SAT":
                    for sil in sahip_olduklarim.keys():
                        try:
                            coinlist.remove(sil[0])
                        except:
                            continue

                for coin in coinlist:
                    close = binance.data(coin, 1000, periyot, 4)
                    momentum = Indikator.Momentum(close)
                    stoch_rsi = Indikator.Stochastic_RSI(close)

                    if sonislem == "SAT":
                        if momentum[-1] > 0 and stoch_rsi[-1] < 0.2:
                            sonislem = "AL"
                            adet = round((nakit / close[-1]), binance.minimum_hareket(
                                float(binance.client.get_symbol_info(coin)["filters"][2]["minQty"])))

                            logging.info(f"AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
                            islemgecmisi.info(f"Momentum_StochRSI AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
                            if gercek:
                                binance.al(coin, adet)

                            araclar.mail_gonder(f"AL | Momentum_StochRSI {periyot}", f"{coin} alindi, Maliyet: {close[-1]} USDT")
                            coinlist = [coin]
                            break
                    else:
                        if momentum[-1] < 0 and stoch_rsi[-1] > 0.8:
                            sonislem = "SAT"
                            adim = binance.minimum_hareket(float(binance.client.get_symbol_info(coin)["filters"][2]["minQty"]))
                            mevcut_adedim = sahip_olduklarim[coin]
                            adet = round(mevcut_adedim - (mevcut_adedim % float(adim)), adim)

                            logging.info(f"SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
                            islemgecmisi.info(f"Momentum_StochRSI SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
                            if gercek:
                                binance.sat(coin, adet)

                            profit_loss = (adet * close[-1]) - nakit
                            self.update_performance("Momentum_StochRSI", profit_loss)
                            araclar.mail_gonder(f"SAT | Momentum_StochRSI {periyot}", f"{coin} satildi")
                            coinlist = templist
                            break
            except Exception:
                hata = traceback.format_exc()
                logging.error(f"Hata oluştu: {hata}")
                araclar.mail_gonder(f"HATA | Momentum_StochRSI {periyot}", hata)
                self.Momentum_StochRSI(coinlist, periyot, gercek, sonislem, nakit)
    def BB_ADX(self, coinlist, periyot, gercek, sonislem, nakit, mumbekle=True):
        binance = Binance()
        araclar = Araclar()
        logging.info(f"{periyot} Bollinger_ADX_Strategy Calisiyor ... {gercek}")
        print(f"{periyot} Bollinger_ADX_Strategy Calisiyor ... {gercek}", time.ctime())

        while sonislem == "AL":
            try:
                if mumbekle:
                    # Mumun oluşmasını bekle
                    if time.time() % zaman_dilimleri[periyot] > 300 or True:
                        time.sleep(zaman_dilimleri[periyot] - (time.time() % zaman_dilimleri[periyot]))

                sahip_olduklarim = binance.sahip_olduklarim()

                if sonislem == "SAT":
                    # Sahip olunan coinleri liste dışı bırak
                    for sil in sahip_olduklarim.keys():
                        try:
                            coinlist.remove(sil[0])
                        except:
                            continue

                for coin in coinlist:
                    # Veri çek
                    high = binance.data(coin, 1000, periyot, 2)
                    low = binance.data(coin, 1000, periyot, 3)
                    close = binance.data(coin, 1000, periyot, 4)

                    # Bollinger Band ve ADX hesapla
                    bb_lower, bb_middle, bb_upper = Indikator.BB(close)
                    adx = Indikator.ADX(high, low, close)

                    # AL işlemi
                    if sonislem == "SAT":
                        # Fiyat alt Bollinger bandının altında ve ADX trendi güçlü ise alım yap
                        if close[-1] < bb_lower[-1] and adx[-1] > 25:
                            sonislem = "AL"
                            adet = round((nakit / close[-1]), binance.minimum_hareket(
                                float(binance.client.get_symbol_info(coin)["filters"][1]["minQty"])))

                            logging.info(f"AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
                            islemgecmisi.info(
                                f"Bollinger_ADX_Strategy AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
                            if gercek:
                                print("Gercekten alindi")
                                binance.al(coin, adet)

                            araclar.mail_gonder(f"AL | Bollinger_ADX_Strategy {periyot}",
                                                f"{coin} alındı, Maliyet: {close[-1]} USDT")
                            coinlist = [coin]
                            break

                    # SAT işlemi
                    else:
                        # Fiyat üst Bollinger bandının üzerinde ve ADX trend gücü düşük ise satış yap
                        if close[-1] > bb_upper[-1] and adx[-1] < 20:
                            sonislem = "SAT"
                            adim = binance.minimum_hareket(
                                float(binance.client.get_symbol_info(coin)["filters"][1]["minQty"]))
                            mevcut_adedim = sahip_olduklarim[coin]
                            adet = round(mevcut_adedim - (mevcut_adedim % float(adim)), adim)

                            logging.info(f"SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
                            islemgecmisi.info(
                                f"Bollinger_ADX_Strategy SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
                            if gercek:
                                print("Gercekten satildi")
                                binance.sat(coin, adet)

                            araclar.mail_gonder(f"SAT | Bollinger_ADX_Strategy {periyot}", f"{coin} satıldı")
                            return
            except Exception:
                # Hata durumunda tekrar çalıştırma
                hata = traceback.format_exc()
                logging.error(f"Hata oluştu: {hata}")
                araclar.mail_gonder(f"HATA | Bollinger_ADX_Strategy {periyot}", hata)
                self.Bollinger_ADX_Strategy(coinlist, periyot, gercek, sonislem, nakit)
    def MA_Cross(self, coinlist, periyot, gercek, sonislem, nakit,stop_lose_var=True,stop_takip=False, mumbekle=True, alis_fiyati=0):
        binance = Binance()
        araclar = Araclar()
        alis=alis_fiyati
        logging.info(f"{periyot} MA_Cross Calisiyor ... {gercek}")
        print(f"{periyot} MA_Cross Calisiyor ... {gercek}", time.ctime())
        while sonislem == "AL":
            try:
                if mumbekle:
                    # Mumun oluşmasını bekle
                    if time.time() % zaman_dilimleri[periyot] > 300 or True:
                        time.sleep(zaman_dilimleri[periyot] - (time.time() % zaman_dilimleri[periyot]))

                sahip_olduklarim = binance.sahip_olduklarim()

                if sonislem == "SAT":
                    # Sahip olunan coinleri liste dışı bırak
                    for sil in sahip_olduklarim.keys():
                        try:
                            coinlist.remove(sil[0])
                        except:
                            continue

                for coin in coinlist:
                    # Veri çek
                    close = binance.data(coin, 1000, periyot, 4)

                    if len(close)<50:
                        continue
                    # MA indikatörlerini hesapla
                    ma9 = Indikator.SMA(close,9)
                    ma50 = Indikator.SMA(close,50)

                    # AL işlemi
                    if sonislem == "SAT":
                        if ma9[-1] > ma50[-1] and ma9[-2] < ma50[-2]:
                            sonislem = "AL"
                            adet = round((nakit / close[-1]), binance.minimum_hareket(
                                float(binance.client.get_symbol_info(coin)["filters"][1]["minQty"])))

                            logging.info(f"AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
                            islemgecmisi.info(f"MA_Cross AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
                            alis=close[-1]
                            if gercek:  # Gerçek işlem mi kontrol et
                                print("Gercekten alindi")
                                binance.al(coin, adet)

                            araclar.mail_gonder(f"AL | MA_Cross {periyot}", f"{coin} alindi, Maliyet: {close[-1]} USDT")
                            coinlist = [coin]
                            break

                    # Satış işlemleri
                    else:
                        if stop_lose_var:
                            # Stop-Lose hesapla
                            if (close[-1] > ma9 * 1.03 or stop_takip):
                                stop_lose = ma9[-1] * 0.99
                                stop_takip = True
                            else:
                                stop_lose = ma50[-1] * 0.99

                            # Stop-Lose
                            if close[-1] < stop_lose:
                                sonislem = "SAT"
                                adet = 0
                                adim = binance.minimum_hareket(
                                    float(binance.client.get_symbol_info(coin)["filters"][1]["minQty"]))
                                logging.info(f"SAT [Stop Lose]| {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
                                islemgecmisi.info(
                                    f"MA_Cross SAT [Stop Lose] | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}, Kar/Zarar: {round((((close[-1]/alis)-1) * 100),2)} %")
                                if gercek:
                                    print("Gercekten satildi")
                                    mevcut_adedim = sahip_olduklarim[coin]
                                    adet = round(mevcut_adedim - (mevcut_adedim % float(adim)), adim)
                                    binance.sat(coin, adet)

                                araclar.mail_gonder(f"SAT [Stop Lose] | MA_Cross {periyot}", f"{coin} satildi")
                                return
                        # SAT işlemi
                        if ma9[-1] < ma50[-1] and ma9[-2] > ma50[-2]:
                            sonislem = "SAT"
                            adet = 0
                            adim = binance.minimum_hareket(
                                float(binance.client.get_symbol_info(coin)["filters"][1]["minQty"]))
                            logging.info(f"SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
                            islemgecmisi.info(f"MA_Cross SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
                            if gercek:
                                print("Gercekten satildi")
                                mevcut_adedim = sahip_olduklarim[coin]
                                adet = round(mevcut_adedim - (mevcut_adedim % float(adim)), adim)
                                binance.sat(coin, adet)

                            araclar.mail_gonder(f"SAT | MA_Cross {periyot}", f"{coin} satildi")
                            return

            except Exception:
                # Hata durumunda tekrar çalıştırma
                hata = traceback.format_exc()
                logging.error(f"Hata oluştu: {hata}")
                araclar.mail_gonder(f"HATA | MA_Cross {periyot}", hata)
                self.MA_Cross(coinlist, periyot, gercek, sonislem, nakit,stop_lose_var,stop_takip,mumbekle,alis)

    def dynamic_strategy(self, coinlist, periyot, gercek, sonislem, nakit,mumbekle=True):
        # Dinamik olarak en iyi stratejiyi seçer
        for coin in coinlist:
            if mumbekle:
                # Mumun oluşmasını bekle
                if time.time() % zaman_dilimleri[periyot] > 300 or True:
                    time.sleep(zaman_dilimleri[periyot] - (time.time() % zaman_dilimleri[periyot]))

            binance = Binance()
            high=binance.data(coin,1000,periyot,2)
            low = binance.data(coin, 1000, periyot, 3)
            close = binance.data(coin, 1000, periyot, 4)

            atr = Indikator.ATR(high,low,close)
            adx = Indikator.ADX(high,low,close)
            rsi = Indikator.RSI(close)

            # Aşırı volatilite ve güçlü trend
            if atr[-1] > atr[-2] * 1.2 and adx[-1] > 30:
                self.BB_ADX([coin],periyot,gercek,sonislem,nakit,False)

            # Düşük volatilite ve yatay piyasa
            elif atr[-1] < atr[-2] and adx[-1] < 20:
                return "Pivot_Point"

            # Trend zayıflaması veya piyasada belirsizlik
            elif adx[-1] < 15 or rsi[-1] > 70 or rsi[-1] < 30:
                return "SMA_Cross"

            # Belirsiz trend
            else:
                self.BB_RSI([coin],periyot,gercek,sonislem,nakit,False)

        """
        logging.info(f'Dinamik strateji çalışıyor: {strategy}')
        if strategy == "BB_RSI":
            self.BB_RSI(coinlist, periyot, gercek, sonislem, nakit)
        elif strategy == "MACD_EMA":
            self.MACD_EMA(coinlist, periyot, gercek, sonislem, nakit)
        elif strategy == "Momentum_StochRSI":
            self.Momentum_StochRSI(coinlist, periyot, gercek, sonislem, nakit)
        """

