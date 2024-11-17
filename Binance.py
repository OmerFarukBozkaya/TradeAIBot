from binance.client import Client       #   pip install python-binance
import requests
from requests.adapters import HTTPAdapter
import concurrent.futures
import math
import json
class Binance:
    def __init__(self):
        with open("settings.json","r") as file:
            data=json.load(file)
        self.key = data['BINANCE_API_KEY']
        self.secret = data['BINANCE_API_SECRET']
        self.client = Client(self.key, self.secret)
        self.base_url = "https://api.binance.com"
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=300)
        self.session.mount('https://', adapter)

    def sahip_olduklarim(self):
        sahip_olduklarim = {}
        for i in self.client.get_account()["balances"]:
            if ((float(i["free"]) == 0 and float(i["locked"]) == 0) or i["asset"]=="NFT" or i["asset"] == "BUSD" or (
                    i["asset"] == "BNB" and (
                    ((float(i["free"]) + float(i["locked"])) * self.get_coin_data("BNBUSDT","4h",1)['close'][-1]) <= 10))):
                continue
            else:
                sahip_olduklarim[i["asset"] + "USDT"] = float(i["free"])
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
    def create_coin_list(self,coinlist=None):
        if coinlist is None:
            coinlist = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'NEOUSDT', 'LTCUSDT', 'QTUMUSDT', 'ADAUSDT', 'XRPUSDT', 'EOSUSDT', 'IOTAUSDT',
                  'XLMUSDT', 'ONTUSDT', 'TRXUSDT', 'ETCUSDT', 'ICXUSDT', 'NULSUSDT', 'VETUSDT', 'LINKUSDT', 'ONGUSDT', 'HOTUSDT',
                  'ZILUSDT', 'ZRXUSDT', 'FETUSDT', 'BATUSDT', 'IOSTUSDT', 'CELRUSDT', 'DASHUSDT', 'THETAUSDT', 'ENJUSDT',
                  'ATOMUSDT', 'ONEUSDT', 'FTMUSDT', 'ALGOUSDT', 'DOGEUSDT', 'DUSKUSDT', 'ANKRUSDT', 'WINUSDT', 'COSUSDT', 'DENTUSDT',
                  'WANUSDT', 'FUNUSDT', 'CVCUSDT', 'CHZUSDT', 'BANDUSDT', 'XTZUSDT', 'RVNUSDT', 'HBARUSDT',
                  'NKNUSDT', 'STXUSDT', 'KAVAUSDT', 'ARPAUSDT', 'IOTXUSDT', 'RLCUSDT', 'TROYUSDT',
                  'OGNUSDT', 'LSKUSDT', 'BNTUSDT', 'LTOUSDT', 'COTIUSDT', 'STPTUSDT', 'DATAUSDT', 'SOLUSDT',
                  'CTSIUSDT', 'HIVEUSDT', 'CHRUSDT', 'ARDRUSDT', 'MDTUSDT', 'STMXUSDT', 'KNCUSDT', 'LRCUSDT', 'COMPUSDT', 'SCUSDT',
                  'ZENUSDT', 'SNXUSDT', 'VTHOUSDT', 'DGBUSDT', 'SXPUSDT', 'MKRUSDT', 'DCRUSDT', 'STORJUSDT', 'MANAUSDT', 'YFIUSDT',
                  'KMDUSDT', 'JSTUSDT', 'CRVUSDT', 'SANDUSDT', 'NMRUSDT', 'DOTUSDT', 'LUNAUSDT',
                  'RSRUSDT', 'TRBUSDT', 'SUSHIUSDT', 'KSMUSDT', 'EGLDUSDT', 'DIAUSDT', 'RUNEUSDT', 'FIOUSDT', 'UMAUSDT',
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
        file = open("./Data/coin_list.txt", "w")
        for coin in coinlist:
            file.write(f"{coin},")
        file.close()
    def coin_list(self):
        file = open("./Data/coin_list.txt", "r")
        file_coinlist = file.readline().split(",")
        if file_coinlist[-1] == "":
            del file_coinlist[-1]
        file.close()
        return file_coinlist

    @staticmethod
    # minQty'ye uygun miktarı aşağı yuvarlayan fonksiyon
    def miktar_duzelt(quantity, min_qty):
        precision = int(round(-math.log10(min_qty), 0))
        return math.floor(quantity * (10 ** precision)) / (10 ** precision)

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
        result_usdt=[]
        result_btc=[]
        if response.status_code == 200:
            data = response.json()  # JSON yanıtı al
            for i in data['symbols']:
                if i['status']=="TRADING" and "USD" not in i['baseAsset'] and  "SPOT" in i['permissionSets'][0]:
                    if i['quoteAsset'] == "USDT":
                        result_usdt.append(i['symbol'])
                    if i['quoteAsset'] == "BTC":
                        result_btc.append(i['symbol'])
        else:
            print("İstek başarısız oldu:", response.status_code)

        return result_usdt

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
        response = requests.get(self.base_url + data_url, timeout=20)
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
        return result

    def get_coin_minQTY(self,coin):
        url = "https://api.binance.com/api/v3/exchangeInfo"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()  # JSON yanıtı al
            for i in data['symbols']:
                if i['symbol'] == coin and i['status']=="TRADING" and "USD" not in i['baseAsset'] and i['quoteAsset'] == "USDT" and  "SPOT" in i['permissionSets'][0]:
                    return float(i['filters'][1]['minQty'])
        else:
            print("İstek başarısız oldu:", response.status_code)
            return None
    def coins_sorted_by_volume(self, coinlist, periyot):
        binance = Binance()
        data = {}

        # İşlemleri paralel hale getir
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(binance.get_coin_data, coin, periyot, 1): coin for coin in coinlist}
            for future in concurrent.futures.as_completed(futures):
                coin = futures[future]
                try:
                    data[coin] = future.result()['volume_usdt']
                except Exception as e:
                    print(f"{coin} için veri çekilirken hata oluştu: {e}")

        # Hacim verisine göre sıralama
        sirali_coinler = sorted(data.items(), key=lambda x: x[1], reverse=True)

        # Sadece coin isimlerini içeren bir liste oluştur
        sirali_coin_isimleri = [coin for coin, _ in sirali_coinler]

        return sirali_coin_isimleri

    def islem_gecmisi_analiz(self):
        file = open("Log/islem_gecmisi.log","r")
        gunluk_islem_sonucu={}
        strategy_islem_sonucu={}
        periyot_islem_sonucu={}
        for line in file.readlines():
            line = line.split(" ")
            tarih = line[0]
            saat = line[1]
            strategy = line[5]
            periyot = line[6]
            islem = line[7]

            if islem == "SAT":
                sonuc = float(line[-1][:-2])  # Sonucu yüzde olarak alıyoruz
                mum_sayisi = float(line[-7])
                if tarih not in gunluk_islem_sonucu:
                    gunluk_islem_sonucu[tarih]={}
                    gunluk_islem_sonucu[tarih]['sonuc'] = 100  # Başlangıç değeri ekliyoruz
                    gunluk_islem_sonucu[tarih]['adet'] = 0
                    gunluk_islem_sonucu[tarih]['stop_adet'] = 0
                # Kümülatif olarak yüzdelik artış işlemi
                gunluk_islem_sonucu[tarih]['sonuc'] += gunluk_islem_sonucu[tarih]['sonuc'] * sonuc / 100
                gunluk_islem_sonucu[tarih]['adet'] = gunluk_islem_sonucu[tarih]['adet'] + 1

                if line[8] == "[STOP-LOSE]":
                    # Kümülatif olarak yüzdelik artış işlemi
                    gunluk_islem_sonucu[tarih]['stop_adet'] = gunluk_islem_sonucu[tarih]['stop_adet'] + 1

                if periyot not in strategy_islem_sonucu:
                    strategy_islem_sonucu[periyot]={}
                if strategy not in strategy_islem_sonucu[periyot]:
                    strategy_islem_sonucu[periyot][strategy]={}
                    strategy_islem_sonucu[periyot][strategy]['sonuc'] = 100
                    strategy_islem_sonucu[periyot][strategy]['adet'] = 0
                    strategy_islem_sonucu[periyot][strategy]['toplam_mum'] = 0
                    strategy_islem_sonucu[periyot][strategy]['ortalama_mum'] = 0

                # Kümülatif olarak yüzdelik artış işlemi
                strategy_islem_sonucu[periyot][strategy]['sonuc'] += strategy_islem_sonucu[periyot][strategy]['sonuc'] * sonuc / 100
                strategy_islem_sonucu[periyot][strategy]['adet'] = strategy_islem_sonucu[periyot][strategy]['adet'] + 1
                strategy_islem_sonucu[periyot][strategy]['toplam_mum'] = strategy_islem_sonucu[periyot][strategy]['toplam_mum'] + mum_sayisi
                strategy_islem_sonucu[periyot][strategy]['ortalama_mum'] = strategy_islem_sonucu[periyot][strategy]['toplam_mum'] / strategy_islem_sonucu[periyot][strategy]['adet']


                if periyot not in periyot_islem_sonucu:
                    periyot_islem_sonucu[periyot]={}
                    periyot_islem_sonucu[periyot]['sonuc']=100
                    periyot_islem_sonucu[periyot]['adet'] = 0

                periyot_islem_sonucu[periyot]['sonuc'] += periyot_islem_sonucu[periyot]['sonuc'] * sonuc / 100
                periyot_islem_sonucu[periyot]['adet'] = periyot_islem_sonucu[periyot]['adet'] + 1



        print(f"Gunluk islem sonucu:")
        for i in gunluk_islem_sonucu.keys():
            print(f"{i}: {(gunluk_islem_sonucu[i]['sonuc'])-100:.2f}% | {gunluk_islem_sonucu[i]['adet']} adet islem | {gunluk_islem_sonucu[i]['stop_adet']} adet stop.")
        print(f"\nStrategy islem sonucu:")
        for i in strategy_islem_sonucu.keys():
            for j in strategy_islem_sonucu[i].keys():
                print(f"{i} {j}: {(strategy_islem_sonucu[i][j]['sonuc'])-100:.2f}% | {strategy_islem_sonucu[i][j]['adet']} adet islem | {strategy_islem_sonucu[i][j]['ortalama_mum']:.2f} ortalama mum sayisi.")
        print(f"\nPeriyot islem sonucu:")
        for i in periyot_islem_sonucu.keys():
            print(f"{i}: {(periyot_islem_sonucu[i]['sonuc'])-100:.2f}% | {periyot_islem_sonucu[i]['adet']} adet islem.")