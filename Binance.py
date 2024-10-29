from binance.client import Client       #   pip install python-binance
from Indikator import Indikator
class Binance:
    def __init__(self, api_key=None, api_secret=None):
        """
        Binance sınıfının yapıcısı. API anahtarı ve gizli anahtarı ile Binance istemcisi başlatır.
        Eğer anahtarlar None ise settings.txt dosyasından yükler.
        """
        if api_key and api_secret:
            self.key = api_key
            self.secret = api_secret
        else:
            self.key, self.secret = self.load_settings()

        self.client = Client(self.key, self.secret)
    def load_settings(self):
        """
        API anahtarlarını 'settings.txt' dosyasından okur.
        Dosyanın her satırı 'key: value' formatında olmalıdır.
        """
        setting = []
        with open("settings.txt", "r") as settings_file:
            for line in settings_file:
                line = line.strip().split(":")
                setting.append(line[1].strip())

        return setting[0], setting[1]
    def sahip_olduklarim(self):
        sahip_olduklarim = {}
        for i in self.client.get_account()["balances"]:
            if ((float(i["free"]) == 0 and float(i["locked"]) == 0) or i["asset"]=="NFT" or i["asset"] == "BUSD" or (
                    i["asset"] == "BNB" and (
                    ((float(i["free"]) + float(i["locked"])) * self.data("BNBUSDT", 1, "4h", 4)[-1]) <= 10))):
                continue
            else:
                sahip_olduklarim[i["asset"] + "USDT"] = i["free"]
        return sahip_olduklarim
    def al(self, coin, adet):
        order = self.client.order_market_buy(symbol=coin, quantity=adet)
    def sat(self, coin, adet):
        order = self.client.order_market_sell(symbol=coin, quantity=adet)
    def mevcut_adedim(self, coin):
        for i in self.client.get_account()["balances"]:
            if (i["asset"] + "USDT" == coin or i["asset"] + "BUSD" == coin):
                return float(i["free"])
    def toplam_cuzdan_degeri(self):
        cuzdan = self.sahip_olduklarim()
        toplam_deger = 0
        for i in cuzdan.keys():
            if(i == "USDTUSDT"):
                toplam_deger=toplam_deger+float(cuzdan[i])
            else:
                toplam_deger = toplam_deger + (self.data(i,1,"1m",4)[-1] * float(cuzdan[i]))
        return toplam_deger
    def coin_list(self):
        result = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'NEOUSDT', 'LTCUSDT', 'QTUMUSDT', 'ADAUSDT', 'XRPUSDT',
                  'EOSUSDT', 'IOTAUSDT', 'XLMUSDT', 'ONTUSDT', 'TRXUSDT', 'ETCUSDT', 'ICXUSDT', 'NULSUSDT',
                  'VETUSDT', 'LINKUSDT', 'WAVESUSDT', 'BTTUSDT', 'ONGUSDT', 'HOTUSDT', 'ZILUSDT', 'ZRXUSDT',
                  'FETUSDT', 'BATUSDT', 'ZECUSDT', 'IOSTUSDT', 'CELRUSDT', 'DASHUSDT', 'NANOUSDT',
                  'OMGUSDT', 'THETAUSDT', 'ENJUSDT', 'MITHUSDT', 'MATICUSDT', 'ATOMUSDT', 'ONEUSDT', 'FTMUSDT',
                  'ALGOUSDT', 'GTOUSDT', 'DOGEUSDT', 'DUSKUSDT', 'ANKRUSDT', 'WINUSDT', 'COSUSDT', 'TOMOUSDT',
                  'PERLUSDT', 'DENTUSDT', 'MFTUSDT', 'KEYUSDT', 'DOCKUSDT', 'WANUSDT', 'FUNUSDT', 'CVCUSDT',
                  'CHZUSDT', 'BANDUSDT', 'BEAMUSDT', 'XTZUSDT', 'RENUSDT', 'RVNUSDT', 'HBARUSDT', 'NKNUSDT',
                  'STXUSDT', 'KAVAUSDT', 'ARPAUSDT', 'IOTXUSDT', 'RLCUSDT', 'CTXCUSDT', 'TROYUSDT', 'VITEUSDT',
                  'FTTUSDT', 'OGNUSDT', 'DREPUSDT', 'TCTUSDT', 'WRXUSDT', 'BTSUSDT', 'LSKUSDT', 'BNTUSDT', 'LTOUSDT',
                  'AIONUSDT', 'MBLUSDT', 'COTIUSDT', 'STPTUSDT', 'DATAUSDT', 'SOLUSDT', 'CTSIUSDT', 'HIVEUSDT',
                  'CHRUSDT', 'ARDRUSDT', 'MDTUSDT', 'STMXUSDT', 'KNCUSDT', 'LRCUSDT', 'PNTUSDT', 'COMPUSDT', 'SCUSDT',
                  'ZENUSDT', 'SNXUSDT', 'VTHOUSDT', 'DGBUSDT', 'GBPUSDT', 'SXPUSDT', 'MKRUSDT', 'DCRUSDT', 'STORJUSDT',
                  'MANAUSDT', 'AUDUSDT', 'YFIUSDT', 'BALUSDT', 'BLZUSDT', 'IRISUSDT', 'KMDUSDT', 'JSTUSDT', 'ANTUSDT',
                  'CRVUSDT', 'SANDUSDT', 'OCEANUSDT', 'NMRUSDT', 'DOTUSDT', 'LUNAUSDT', 'RSRUSDT', 'PAXGUSDT', 'WNXMUSDT',
                  'TRBUSDT', 'SUSHIUSDT', 'YFIIUSDT', 'KSMUSDT', 'EGLDUSDT', 'DIAUSDT', 'RUNEUSDT', 'FIOUSDT', 'UMAUSDT',
                  'BELUSDT', 'WINGUSDT', 'UNIUSDT', 'OXTUSDT', 'SUNUSDT', 'AVAXUSDT', 'FLMUSDT', 'ORNUSDT', 'UTKUSDT',
                  'XVSUSDT', 'ALPHAUSDT', 'AAVEUSDT', 'NEARUSDT', 'FILUSDT', 'INJUSDT', 'AUDIOUSDT', 'CTKUSDT', 'AKROUSDT',
                  'AXSUSDT', 'HARDUSDT', 'STRAXUSDT', 'ROSEUSDT', 'AVAUSDT', 'XEMUSDT', 'SKLUSDT', 'GRTUSDT', 'JUVUSDT',
                  'PSGUSDT', '1INCHUSDT', 'REEFUSDT', 'OGUSDT', 'ATMUSDT', 'ASRUSDT', 'CELOUSDT', 'RIFUSDT', 'TRUUSDT',
                  'CKBUSDT', 'FIROUSDT', 'LITUSDT', 'SFPUSDT', 'DODOUSDT', 'CAKEUSDT', 'ACMUSDT', 'BADGERUSDT', 'FISUSDT',
                  'OMUSDT', 'PONDUSDT', 'DEGOUSDT', 'ALICEUSDT', 'LINAUSDT', 'PERPUSDT', 'SUPERUSDT', 'CFXUSDT', 'TKOUSDT',
                  'PUNDIXUSDT', 'TLMUSDT', 'BARUSDT', 'FORTHUSDT', 'BAKEUSDT', 'BURGERUSDT', 'SLPUSDT', 'SHIBUSDT', 'ICPUSDT',
                  'ARUSDT', 'POLSUSDT', 'MDXUSDT', 'MASKUSDT', 'LPTUSDT', 'XVGUSDT', 'ATAUSDT', 'GTCUSDT', 'ERNUSDT', 'KLAYUSDT',
                  'PHAUSDT', 'BONDUSDT', 'MLNUSDT', 'DEXEUSDT', 'C98USDT', 'CLVUSDT', 'QNTUSDT', 'FLOWUSDT', 'MINAUSDT', 'RAYUSDT',
                  'FARMUSDT', 'ALPACAUSDT', 'QUICKUSDT', 'MBOXUSDT', 'FORUSDT', 'REQUSDT', 'GHSTUSDT', 'WAXPUSDT', 'GNOUSDT',
                  'XECUSDT', 'ELFUSDT', 'DYDXUSDT', 'IDEXUSDT', 'VIDTUSDT', 'GALAUSDT', 'ILVUSDT', 'YGGUSDT', 'SYSUSDT', 'DFUSDT',
                  'FIDAUSDT', 'FRONTUSDT', 'CVPUSDT', 'AGLDUSDT', 'RADUSDT', 'BETAUSDT', 'RAREUSDT', 'LAZIOUSDT', 'CHESSUSDT',
                  'ADXUSDT', 'AUCTIONUSDT', 'DARUSDT', 'MOVRUSDT', 'CITYUSDT', 'ENSUSDT', 'KP3RUSDT', 'QIUSDT', 'PORTOUSDT',
                  'POWRUSDT', 'VGXUSDT', 'JASMYUSDT', 'AMPUSDT', 'PYRUSDT', 'ALCXUSDT', 'SANTOSUSDT', 'BICOUSDT', 'FLUXUSDT',
                  'FXSUSDT', 'VOXELUSDT', 'HIGHUSDT', 'CVXUSDT', 'PEOPLEUSDT', 'OOKIUSDT', 'SPELLUSDT', 'JOEUSDT', 'ACHUSDT',
                  'IMXUSDT', 'GLMRUSDT', 'LOKAUSDT', 'SCRTUSDT', 'API3USDT', 'BTTCUSDT', 'ACAUSDT', 'XNOUSDT']
        return result
    def minimum_hareket(self,basamak):
        if (basamak == 1):
            return 0
        if (basamak == 0.1):
            return 1
        if (basamak == 0.01):
            return 2
        if (basamak == 0.001):
            return 3
        if (basamak == 0.0001):
            return 4
        if (basamak == 0.00001):
            return 5
        if (basamak == 0.000001):
            return 6
    def secili_list(self):
        return ['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','TRXUSDT','ADAUSDT',
                'AVAXUSDT','SHIBUSDT','LINKUSDT','BCHUSDT','DOTUSDT','NEARUSDT','LTCUSDT','UNIUSDT',
                'ICPUSDT','FETUSDT','ETCUSDT','XLMUSDT','STXUSDT','IMXUSDT','AAVEUSDT','FILUSDT',
                'HBARUSDT','INJUSDT','VETUSDT','ATOMUSDT','FTMUSDT','RUNEUSDT','GRTUSDT','MINAUSDT',
                'MANAUSDT','IOTAUSDT','QTUMUSDT','CVCUSDT']
    def data(self,ad, adet, zaman, mod):
        """
        :param ad: Coin Adi (str)
        :param adet: Cekilecek veri adedi (int)
        :param zaman: Mum periyodu (str)
        :param mod: 0=Anlik fiyat 1=Mum kapanisi (int)
        :return: 0=Acılıs Zamani
                 1=Acilis
                 2=En yuksek
                 3=En dusuk
                 4=Kapanis
                 5=Burut Hacim
                 6=Kapanis Zamani
                 7=Varlik Hacmi Teklifi
                 8=Trader Sayisi
                 9=Alis Hacmi
                 10=Satis Hacmi
                 11=Göz Ardi Edilebilir
        """
        klines = self.client.get_klines(symbol=ad, limit=adet, interval=zaman)

        opentime = [float(entry[0]) for entry in klines]
        open = [float(entry[1]) for entry in klines]
        high = [float(entry[2]) for entry in klines]
        low = [float(entry[3]) for entry in klines]
        close = [float(entry[4]) for entry in klines]
        burutvolume = [float(entry[5]) for entry in klines]
        closetime = [float(entry[6]) for entry in klines]
        varlikhacmiteklifi = [float(entry[7]) for entry in klines]
        tuccarsayisi = [float(entry[8]) for entry in klines]
        alishacmi = [float(entry[9]) for entry in klines]
        satishacmi = [float(entry[10]) for entry in klines]
        gozardiedilebilir = [float(entry[11]) for entry in klines]

        if (mod == 0):
            return opentime
        elif (mod == 1):
            return open
        elif (mod == 2):
            return high
        elif (mod == 3):
            return low
        elif (mod == 4):
            return close
        elif (mod == 5):
            return burutvolume
        elif (mod == 6):
            return closetime
        elif (mod == 7):
            return varlikhacmiteklifi
        elif (mod == 8):
            return tuccarsayisi
        elif (mod == 9):
            return alishacmi
        elif (mod == 10):
            return satishacmi
        elif (mod == 11):
            return gozardiedilebilir
