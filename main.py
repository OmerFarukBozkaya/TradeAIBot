from Binance import Binance
from Stratejiler import Al_Sat
from Backtest import Backtest
from IndikatorTest import IndikatorTest
from Tarama import Tarama
from Araclar import Araclar
binance = Binance()
alsat = Al_Sat()
backtest = Backtest()
indikator_test=IndikatorTest()
araclar = Araclar()

print("""
1)Sonuçları kayıt et
2)Indikatör Test
3)Backtest
4)Tarama
""")
com = input("Ne yapılacak :")
if com == "1":
    for i in binance.secili_list():
        for j in ["15m", "1h", "4h", "1d"]:
            backtest.Test(canli_veriler=True, coin=i, selected_strategy_name="DMO",periyot=j, kayit_et=True)
elif com == "2":
    indikator_test.IndikatorResultTest(True)
elif com == "3":
    backtest.Test(canli_veriler=True,coin="FETUSDT", periyot="1d", selected_strategy_name="DMO")
elif com == "4":
    periyot=input("Periyot (15m,1h,4h,1d):")
    while True:
        araclar.mum_olusmasini_bekle(periyot)
        Tarama.Tara(binance.secili_list(),periyot)

#alsat.dynamic_strategy(coinlist=binance.secili_list(),periyot="5m",gercek=False,sonislem="SAT",nakit=100)