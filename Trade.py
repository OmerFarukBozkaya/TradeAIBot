import time
import traceback
from Binance import Binance
from Araclar import Araclar
from Stratejiler import Stratejiler
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

class Trade:
    def __init__(self):
        self.binance = Binance()
        self.araclar = Araclar()
    def iskelet(self, coinlist, periyot, gercek, nakit,sonislem="SAT", stop_lose_var=True,stop_takip=False, mumbekle=True, alis_fiyati=0,strategy_name=None):
        """
        Değiştirilmesi gereken değerler:
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
        binance = Binance()
        araclar = Araclar()
        alis=alis_fiyati
        strateji_adi = "iskelet"    # [0]
        logging.info(f"{periyot} {strateji_adi} Calisiyor ... {gercek}")
        print(f"{periyot} {strateji_adi} Calisiyor ... {gercek}", time.ctime())
        while sonislem == "AL":
            try:
                if mumbekle:
                    araclar.mum_olusmasini_bekle(periyot)

                sahip_olduklarim = binance.sahip_olduklarim()

                if sonislem == "SAT":
                    coinlist=araclar.listeden_sahip_olduklarimi_cikar(coinlist)

                for coin in coinlist:
                    # Veri çek
                    # [1]
                    close = binance.data(coin, 1000, periyot, 4)

                    # AL işlemi
                    if sonislem == "SAT":
                        if close is not None: # Alım şartı [3]
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

    def TradeEt(self,coinlist,periyot,sonislem,gercek,nakit):
        strategy=None
        adet=None
        temp=coinlist
        while True:
            Araclar.mum_olusmasini_bekle(periyot)
            for coin in coinlist:
                close = self.binance.data(coin, 1000, periyot, 4)
                low = self.binance.data(coin, 1000, periyot, 3)
                high = self.binance.data(coin, 1000, periyot, 2)
                if sonislem == "SAT":
                    print("Almak için bakıcam")
                    if periyot == "15m":
                        if Stratejiler.BB_Close(close) == "BUY":
                            strategy = Stratejiler.BB_Close(close)
                            sonislem,adet = self.buy(coin, periyot, strategy.__name__, gercek, nakit, close)
                            coinlist = [coin]
                            break
                        if Stratejiler.BB_RSI(close) == "BUY":
                            strategy = Stratejiler.BB_RSI(close)
                            sonislem,adet = self.buy(coin, periyot, strategy.__name__, gercek, nakit, close)
                            coinlist = [coin]
                            break
                        if Stratejiler.BB_ADX(high,low,close) == "BUY":
                            strategy = Stratejiler.BB_ADX(high,low,close)
                            sonislem, adet = self.buy(coin, periyot, strategy.__name__, gercek, nakit, close)
                            coinlist = [coin]
                            break
                        if Stratejiler.MA_Cross(high,low,close) == "BUY":
                            strategy = Stratejiler.MA_Cross(high,low,close)
                            sonislem, adet = self.buy(coin, periyot, strategy.__name__, gercek, nakit, close)
                            coinlist = [coin]
                            break
                        if Stratejiler.TSO(high,low,close) == "BUY":
                            strategy = Stratejiler.TSO(high,low,close)
                            sonislem, adet = self.buy(coin, periyot, strategy.__name__, gercek, nakit, close)
                            coinlist = [coin]
                            break
                        if Stratejiler.VMZI(high,low,close) == "BUY":
                            strategy = Stratejiler.VMZI(high,low,close)
                            sonislem, adet = self.buy(coin, periyot, strategy.__name__, gercek, nakit, close)
                            coinlist = [coin]
                            break
                        if Stratejiler.FDI(close) == "BUY":
                            strategy = Stratejiler.FDI(close)
                            sonislem, adet = self.buy(coin, periyot, strategy.__name__, gercek, nakit, close)
                            coinlist = [coin]
                            break
                        if Stratejiler.DMO(high,low,close) == "BUY":
                            strategy = Stratejiler.DMO(high,low,close)
                            sonislem, adet = self.buy(coin, periyot, strategy.__name__, gercek, nakit, close)
                            coinlist = [coin]
                            break
                        if Stratejiler.VAMA(close) == "BUY":
                            strategy = Stratejiler.VAMA(close)
                            sonislem, adet = self.buy(coin, periyot, strategy.__name__, gercek, nakit, close)
                            coinlist = [coin]
                            break
                        if Stratejiler.MACD(close) == "BUY":
                            strategy = Stratejiler.MACD(close)
                            sonislem, adet = self.buy(coin, periyot, strategy.__name__, gercek, nakit, close)
                            coinlist = [coin]
                            break
                    elif periyot == "1h":
                        if Stratejiler.TSO(high,low,close) == "BUY":
                            sonislem,adet = self.buy(coin, periyot, "TSO", gercek, nakit, close)
                            strategy = Stratejiler.TSO(high,low,close)
                            coinlist=[coin]
                            break
                    elif periyot == "4h":
                        print(periyot)
                    elif periyot == "1d":
                        print(periyot)

                elif sonislem == "AL":
                    print("satmaya çalışıyorum")
                    print(coin)
                    if strategy == "SELL":
                        sonislem = self.sell(coin,adet,periyot,close,strategy.__name__,gercek)
                        coinlist=temp


    def buy(self,coin,periyot,strateji_adi,gercek,nakit,close):
        adet = round((nakit / close[-1]), self.binance.minimum_hareket(
            float(self.binance.client.get_symbol_info(coin)["filters"][1]["minQty"])))
        logging.info(f"AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")
        islemgecmisi.info(f"{strateji_adi} AL | {coin} alındı, Adet: {adet}, Fiyat: {close[-1]}")

        if gercek:  # Gerçek işlem mi kontrol et
            print("Gercekten alindi")
            self.binance.al(coin, adet)

        self.araclar.mail_gonder(f"AL | {strateji_adi} {periyot}",
                            f"{coin} alindi, Adet: {adet}, Maliyet: {close[-1]} USDT")
        return "AL",adet

    def sell(self,coin,adet,periyot,close,strateji_adi,gercek):
        adim = self.binance.minimum_hareket(float(self.binance.client.get_symbol_info(coin)["filters"][1]["minQty"]))
        logging.info(f"SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
        islemgecmisi.info(f"{strateji_adi} SAT | {coin} satıldı, Adet: {adet}, Fiyat: {close[-1]}")
        if gercek:
            print("Gercekten satildi")
            mevcut_adedim = self.binance.sahip_olduklarim()[coin]
            adet = round(mevcut_adedim - (mevcut_adedim % float(adim)), adim)
            self.binance.sat(coin, adet)
        self.araclar.mail_gonder(f"SAT | {strateji_adi} {periyot}", f"{coin} satildi")
        return "SAT"
