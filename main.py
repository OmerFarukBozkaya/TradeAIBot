from Binance import Binance
from Backtest import Backtest
from IndikatorTest import IndikatorTest
from Tarama import Tarama
from Araclar import Araclar
from Trade import Trade
import time
from raspi_status import raspi_status
binance = Binance()
backtest = Backtest()
trade = Trade()
indikator_test = IndikatorTest()
araclar = Araclar()

print("""
0)Veri seti olustur
1)Backtest sonuçlarını kayıt et
2)IndikatörTest sınıfını Test et
3)Backtest testi yap
4)Tarama
5)Trade
6)Coin Indikator degerleri
7)Coin Strateji degerleri
8)Cihaz bilgilerini görüntüle
9)Piyasa durumu
10)Coinlist olustur
11)Islem gecmisi analiz
12)Hacime gore coinlist siralama
""")
com = input("Ne yapılacak :")
if com == "0":
    a=time.time()
    araclar.veri_seti_olustur("BTCUSDT","15m")
    b=time.time()
    print(araclar.saniye_to_hms(b - a))
elif com == "1":
    a = time.time()
    for i in binance.secili_list():
        for j in ["15m", "1h", "4h", "1d"]:
            backtest.Test(canli_veriler=True, coin=i,periyot=j, kayit_et=True)
    # Analiz yapılıyor
    Araclar.strategy_result_analyze()
    b=time.time()
    print(araclar.saniye_to_hms(b-a))
elif com == "2":
    a=time.time()
    indikator_test.IndikatorResultTest(True)
    b=time.time()
    print(araclar.saniye_to_hms(b - a))
elif com == "3":
    periyot = input("Periyot (15m,1h,4h,1d):")
    coin = input("Coin:")
    select_strategy=input("Gösterilecek strategy:")
    a=time.time()
    if select_strategy=="":
        select_strategy=None
    backtest.Test(canli_veriler=True,periyot=periyot,coin=coin, selected_strategy_name=select_strategy)
    b=time.time()
    print(araclar.saniye_to_hms(b-a))
elif com == "4":
    coinlist = binance.coin_list()
    periyot=input("Periyot (15m,1h,4h,1d):")
    a=time.time()
    Tarama.Tara(coinlist, periyot)
    b=time.time()
    print(araclar.saniye_to_hms(b-a))
elif com == "5":
    periyot = input("Periyot (15m,1h,4h,1d):")
    gercek = input("Gercek:") == "True"
    nakit= float(input("Nakit:").replace(",","."))
    a=time.time()
    trade.TradeEt(periyot,gercek,nakit)
    b=time.time()
    print(araclar.saniye_to_hms(b-a))
elif com == "6":
    a=time.time()
    coin=input("Coin:")
    adet = int(input("Adet : "))
    periyot = input("Periyot (15m,1h,4h,1d):")
    if periyot not in ["15m","1h","4h","1d"]:
        for i in ["15m","1h","4h","1d"]:
            print(i)
            araclar.coin_indikator_degerleri(coin,i,adet)
    else:
        araclar.coin_indikator_degerleri(coin,periyot,adet)
    b=time.time()
    print(araclar.saniye_to_hms(b - a))
elif com == "7":
    coin = input("Coin:")
    periyot = input("Periyot (15m,1h,4h,1d):")
    a=time.time()
    if periyot not in ["15m","1h","4h","1d"]:
        for i in ["15m","1h","4h","1d"]:
            print(i)
            araclar.coin_strateji_degerleri(coin,i)
    else:
        araclar.coin_strateji_degerleri(coin, periyot)
    b=time.time()
    print(araclar.saniye_to_hms(b-a))
elif com == "8":
    a=time.time()
    raspi_status.list_system_info()
    b=time.time()
    print(araclar.saniye_to_hms(b - a))
elif com == "9":
    a=time.time()
    print(Tarama.Piyasa_Durumu(binance.coin_list()))
    b=time.time()
    print(araclar.saniye_to_hms(b-a))
elif com == "10":
    a=time.time()
    binance.create_coin_list()
    b=time.time()
    print(araclar.saniye_to_hms(b-a))
elif com == "11":
    a = time.time()
    binance.islem_gecmisi_analiz()
    b = time.time()
    print(araclar.saniye_to_hms(b - a))
elif com == "12":
    a=time.time()
    periyot = input("Periyot:")
    araclar.coinlist_sira_duzenle(periyot)
    b=time.time()
    print(araclar.saniye_to_hms(b-a))