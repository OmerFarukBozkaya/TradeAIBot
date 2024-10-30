from binance.client import Client       #   pip install python-binance
import requests
from requests.adapters import HTTPAdapter
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
        self.base_url = "https://api.binance.com"
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=300)
        self.session.mount('https://', adapter)
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
                    ((float(i["free"]) + float(i["locked"])) * self.get_coin_data("BNBUSDT","4h",1)['close'][-1]) <= 10))):
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
                toplam_deger = toplam_deger + (self.get_coin_data(i,"1m",1)['close'][-1] * float(cuzdan[i]))
        return toplam_deger
    def coin_list(self):
        result = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'NEOUSDT', 'LTCUSDT', 'QTUMUSDT', 'ADAUSDT', 'XRPUSDT', 'EOSUSDT', 'IOTAUSDT',
                  'XLMUSDT', 'ONTUSDT', 'TRXUSDT', 'ETCUSDT', 'ICXUSDT', 'NULSUSDT', 'VETUSDT', 'LINKUSDT', 'ONGUSDT', 'HOTUSDT',
                  'ZILUSDT', 'ZRXUSDT', 'FETUSDT', 'BATUSDT', 'IOSTUSDT', 'CELRUSDT', 'DASHUSDT', 'THETAUSDT', 'ENJUSDT',
                  'ATOMUSDT', 'ONEUSDT', 'FTMUSDT', 'ALGOUSDT', 'DOGEUSDT', 'DUSKUSDT', 'ANKRUSDT', 'WINUSDT', 'COSUSDT', 'DENTUSDT',
                  'WANUSDT', 'FUNUSDT', 'CVCUSDT', 'CHZUSDT', 'BANDUSDT', 'XTZUSDT', 'RVNUSDT', 'HBARUSDT',
                  'NKNUSDT', 'STXUSDT', 'KAVAUSDT', 'ARPAUSDT', 'IOTXUSDT', 'RLCUSDT', 'TROYUSDT',
                  'OGNUSDT', 'LSKUSDT', 'BNTUSDT', 'LTOUSDT', 'COTIUSDT', 'STPTUSDT', 'DATAUSDT', 'SOLUSDT',
                  'CTSIUSDT', 'HIVEUSDT', 'CHRUSDT', 'ARDRUSDT', 'MDTUSDT', 'STMXUSDT', 'KNCUSDT', 'LRCUSDT', 'COMPUSDT', 'SCUSDT',
                  'ZENUSDT', 'SNXUSDT', 'VTHOUSDT', 'DGBUSDT', 'SXPUSDT', 'MKRUSDT', 'DCRUSDT', 'STORJUSDT', 'MANAUSDT', 'YFIUSDT',
                  'KMDUSDT', 'JSTUSDT', 'CRVUSDT', 'SANDUSDT', 'NMRUSDT', 'DOTUSDT', 'LUNAUSDT',
                  'RSRUSDT', 'PAXGUSDT', 'TRBUSDT', 'SUSHIUSDT', 'KSMUSDT', 'EGLDUSDT', 'DIAUSDT', 'RUNEUSDT', 'FIOUSDT', 'UMAUSDT',
                  'BELUSDT', 'WINGUSDT', 'UNIUSDT', 'OXTUSDT', 'AVAXUSDT', 'FLMUSDT', 'UTKUSDT', 'XVSUSDT', 'ALPHAUSDT',
                  'AAVEUSDT', 'NEARUSDT', 'FILUSDT', 'INJUSDT', 'AUDIOUSDT', 'CTKUSDT', 'AXSUSDT', 'STRAXUSDT',
                  'ROSEUSDT', 'AVAUSDT', 'SKLUSDT', 'GRTUSDT', '1INCHUSDT', 'CELOUSDT', 'RIFUSDT', 'TRUUSDT', 'CKBUSDT',
                  'LITUSDT', 'SFPUSDT', 'DODOUSDT', 'CAKEUSDT', 'BADGERUSDT', 'FISUSDT', 'OMUSDT', 'PONDUSDT', 'DEGOUSDT', 'ALICEUSDT',
                  'PERPUSDT', 'SUPERUSDT', 'CFXUSDT', 'TKOUSDT', 'PUNDIXUSDT', 'TLMUSDT', 'FORTHUSDT', 'BAKEUSDT',
                  'BURGERUSDT', 'SLPUSDT', 'SHIBUSDT', 'ICPUSDT', 'ARUSDT', 'MASKUSDT', 'LPTUSDT', 'XVGUSDT', 'ATAUSDT', 'GTCUSDT',
                  'ERNUSDT', 'PHAUSDT', 'MLNUSDT', 'DEXEUSDT', 'C98USDT', 'QNTUSDT', 'FLOWUSDT', 'MINAUSDT', 'RAYUSDT',
                  'FARMUSDT', 'ALPACAUSDT', 'QUICKUSDT', 'MBOXUSDT', 'REQUSDT', 'GHSTUSDT', 'WAXPUSDT', 'GNOUSDT', 'XECUSDT',
                  'DYDXUSDT', 'IDEXUSDT', 'VIDTUSDT', 'GALAUSDT', 'ILVUSDT', 'YGGUSDT', 'SYSUSDT', 'DFUSDT', 'FIDAUSDT', 'AGLDUSDT',
                  'RADUSDT', 'RAREUSDT', 'CHESSUSDT', 'ADXUSDT', 'AUCTIONUSDT', 'DARUSDT', 'MOVRUSDT', 'ENSUSDT',
                  'QIUSDT', 'PORTOUSDT', 'POWRUSDT', 'AMPUSDT', 'PYRUSDT', 'ALCXUSDT', 'BICOUSDT', 'FLUXUSDT',
                  'FXSUSDT', 'VOXELUSDT', 'HIGHUSDT', 'PEOPLEUSDT', 'SPELLUSDT', 'JOEUSDT', 'ACHUSDT',
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

    def trade_edilebilir_coinler(self):
        url = "https://api.binance.com/api/v3/exchangeInfo"
        response = requests.get(url)
        # Dönen yanıtı kontrol et ve kullan
        result=[]
        if response.status_code == 200:
            data = response.json()  # JSON yanıtı al
            for i in data['symbols']:
                if i['status']=="TRADING" and "USD" not in i['baseAsset'] and i['quoteAsset'] == "USDT" and  "SPOT" in i['permissionSets'][0]:
                    result.append(i['symbol'])
        else:
            print("İstek başarısız oldu:", response.status_code)

        olmayanlar=[]
        olanlar=[]
        coinlist=self.coin_list()
        for i in coinlist:
            if i not in result:
                olmayanlar.append(i)
            else:
                olanlar.append(i)
        print(f"Doğru olanların sayısı : {len(olanlar)} Kaldırılanların sayısı : {len(olmayanlar)} Trade edilebilir : {len(result)}")
        return result

    def get_coin_data(self,coin,periyot,adet):
        data_url = f"/api/v3/klines?symbol={coin}&interval={periyot}&limit={adet}"
        result={
            'opendate':[],
            'open':[],
            'high':[],
            'low':[],
            'close':[],
            'volume_coin':[],
            'closedate':[],
            'volume_usdt':[],
            'trade_number':[],
            'buy_coin_volume':[],
            'buy_usdt_volume':[],
            'ignore':[]
        }
        try:
            response = requests.get(self.base_url + data_url,timeout=20)
            response.raise_for_status()
            data = response.json()  # JSON yanıtı al
            for i in data:
                result['opendate'].append(float(i[0]))
                result['open'].append(float(i[1]))
                result['high'].append(float(i[2]))
                result['low'].append(float(i[3]))
                result['close'].append(float(i[4]))
                result['volume_coin'].append(float(i[5]))
                result['closedate'].append(float(i[6]))
                result['volume_usdt'].append(float(i[7]))
                result['trade_number'].append(float(i[8]))
                result['buy_coin_volume'].append(float(i[9]))
                result['buy_usdt_volume'].append(float(i[10]))
                result['ignore'].append(float(i[11]))
        except requests.exceptions.RequestException as e:
            print(f"İstek başarısız oldu: {e}")

        return result