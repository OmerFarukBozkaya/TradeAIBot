from Binance import Binance
from Backtest import Backtest
from IndikatorTest import IndikatorTest
from Tarama import Tarama
from Araclar import Araclar
from Trade import Trade
import time
binance = Binance()
backtest = Backtest()
trade=Trade()
indikator_test=IndikatorTest()
araclar = Araclar()

print("""
0)Veri seti olustur
1)Backtest sonuçlarını kayıt et
2)IndikatörTest sınıfını Test et
3)Backtest testi yap
4)Tarama
5)Trade
""")
com = input("Ne yapılacak :")
if com=="0":
    araclar.veri_seti_olustur("BTCUSDT","15m")
if com == "1":
    a = time.time()
    for i in binance.secili_list():
        for j in ["15m", "1h", "4h", "1d"]:
            backtest.Test(canli_veriler=True, coin=i,periyot=j, kayit_et=True)
    # Analiz yapılıyor
    Araclar.strategy_result_analyze()
    b=time.time()
    print(araclar.saniye_to_hms(b-a))
elif com == "2":
    indikator_test.IndikatorResultTest(True)
elif com == "3":
    backtest.Test(canli_veriler=True,periyot="1h",coin="SHIBUSDT", selected_strategy_name="BB(RSI)")
elif com == "4":
    periyot=input("Periyot (15m,1h,4h,1d):")
    Tarama.Tara(binance.secili_list(), periyot)
elif com == "5":
    coinlist=[]
    periyot = input("Periyot (15m,1h,4h,1d):")
    gercek = input("Gercek:") == "True"
    nakit= float(input("Nakit:").replace(",","."))
    sonislem=input("Son islem:")
    if sonislem=="AL":
        coin=input("Coin:")
        coinlist.append(coin)
    else:
        coinlist=binance.secili_list()
    trade.TradeEt(coinlist,periyot,sonislem,gercek,nakit)