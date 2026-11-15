from Binance import Binance
from Backtest import Backtest
from IndikatorTest import IndikatorTest
from Tarama import Tarama
from Araclar import Araclar
from Trade import Trade
import time
from raspi_status import raspi_status
from Indikator import Indikator
from Stratejiler import Stratejiler
from StratejilerTest import StratejilerTest

def main ():
    binance = Binance()
    backtest = Backtest()
    trade = Trade()
    indikator_test = IndikatorTest()
    araclar = Araclar()

    print("""
    0)Veri seti olustur
    1)Backtest sonuçlarını kayıt et
    2)Indikatör Test et
    3)Backtest yap
    4)Tarama
    5)Trade
    6)Coin Indikator degerleri
    7)Coin Strateji degerleri
    8)Cihaz bilgilerini görüntüle
    9)Piyasa durumu
    10)Coinlist olustur
    11)Islem gecmisi analiz
    12)Hacime gore coinlist siralama
    13)Strategys update olusturma
    14)Strategys.json olustur
    15)Buy veren coinler
    16)Destek direnc seviyeleri
    17)Tum pozisyonlari kapat
    18)Full nakite gec
    19)Buy result analizi
    20)Acik pozisyon grafigi
    21)Coin aylik sonuc
    22)Trade aylik hedef kontrolu
    23)Tek pozisyon kapat
    24)AI
    25)Trade AI
    """)
    com = input("Ne yapılacak :")
    if com == "0":
        a = time.time()
        araclar.veri_seti_olustur("BTCUSDT", "15m")
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "1":
        a = time.time()
        # Hesaplamalar Yapılıyor
        backtest.paralel_hesaplama()
        # Analiz yapılıyor
        araclar.strategy_result_analyze()
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "2":
        a = time.time()
        indikator_test.IndikatorResultTest(True)
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "3":
        periyot = input("Periyot (15m,1h,4h,1d):")
        coin = input("Coin:")
        functions = [func for func in dir(StratejilerTest) if
                     callable(getattr(StratejilerTest, func)) and not func.startswith("__")]
        functions.remove("dinamik_stop_lose")
        functions.remove("static_stop_lose")
        functions.remove("destek_stop_lose")
        print(functions)
        select_strategy = input("Gösterilecek strategy:")
        a = time.time()
        if select_strategy == "":
            select_strategy = None
        backtest.Grafik_Ciz(coin=coin, periyot=periyot,selected_strategy_name=select_strategy)
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "4":
        coinlist = binance.coin_list()
        periyot = input("Periyot (15m,1h,4h,1d):")
        a = time.time()
        Tarama.Tara(coinlist, periyot)
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "5":
        periyot = input("Periyot (15m,1h,4h,1d):")
        gercek = input("Gercek:") == "True"
        nakit = float(input("Nakit:").replace(",", "."))
        temp_trade = input("Temp Trade:") == "True"
        a = time.time()
        trade.TradeEt(periyot, gercek, nakit,temp_trade)
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "6":
        a = time.time()
        coin = input("Coin:")
        adet = int(input("Adet : "))
        periyot = input("Periyot (15m,1h,4h,1d):")
        if periyot not in ["15m", "1h", "4h", "1d"]:
            for i in ["15m", "1h", "4h", "1d"]:
                print(i)
                araclar.coin_indikator_degerleri(coin, i, adet)
        else:
            araclar.coin_indikator_degerleri(coin, periyot, adet)
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "7":
        coin = input("Coin:")
        periyot = input("Periyot (15m,1h,4h,1d):")
        adet = int(input("Adet:"))
        a = time.time()
        if periyot not in ["15m", "1h", "4h", "1d"]:
            for i in ["15m", "1h", "4h", "1d"]:
                print(i)
                araclar.coin_strateji_degerleri(coin, i, adet)
        else:
            araclar.coin_strateji_degerleri(coin, periyot, adet)
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "8":
        a = time.time()
        raspi_status.list_system_info()
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "9":
        a = time.time()
        print(Tarama.Piyasa_Durumu(binance.coin_list()))
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "10":
        a = time.time()
        binance.create_coin_list()
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "11":
        a = time.time()
        binance.islem_gecmisi_analiz()
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "12":
        a = time.time()
        periyot = input("Periyot:")
        araclar.coinlist_sira_duzenle(periyot)
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "13":
        a = time.time()
        periyot = input("Periyot:")
        araclar.update_strategys(periyot)
        b = time.time()
        print(araclar.saniye_to_hms(b-a))
    elif com == "14":
        a=time.time()
        araclar=Araclar()
        araclar.strategy_analyze_save()
        b=time.time()
        print(araclar.saniye_to_hms(b-a))
    elif com == "15":
        a=time.time()
        functions = [func for func in dir(Stratejiler) if callable(getattr(Stratejiler, func)) and not func.startswith("__")]
        functions.remove("dinamik_stop_lose")
        functions.remove("static_stop_lose")
        functions.remove("destek_stop_lose")
        print(functions)
        strategy=input("Strateji adi: ")
        periyot = input("Periyot: ")
        araclar.stratejinin_buy_verdikleri(strategy,periyot)
        b=time.time()
        print(araclar.saniye_to_hms(b-a))
    elif com == "16":
        a=time.time()
        coin=input("Coin:")
        periyot=input("Periyot:")
        buy_price=float(input("Buy price:"))
        data=binance.get_coin_data(coin,periyot,1000)
        if buy_price=="":
            buy_price=data['close'][-1]
        low=data['low']
        destek,direnc,liste=Indikator.destek_direnc_hesapla(buy_price,low)
        print(f"Destek:{destek}\nDirenc:{direnc}\n{liste}")
        b=time.time()
        print(araclar.saniye_to_hms(b-a))
    elif com == "17":
        a=time.time()
        emin_misin=input("Emin misin : ")=="Evet"
        if emin_misin:
            binance.tum_pozisyonlari_kapat()
        else:
            print("Islem gerceklesmedi !")
        b=time.time()
        print(araclar.saniye_to_hms(b-a))
    elif com == "18":
        a=time.time()
        emin_misin = input("Emin misin : ") == "Evet"
        if emin_misin:
            binance.full_nakite_gec()
        else:
            print("Islem gerceklesmedi !")
        b=time.time()
        print(araclar.saniye_to_hms(b-a))
    elif com == "19":
        a=time.time()
        binance.buy_result_analyze()
        b=time.time()
        print(araclar.saniye_to_hms(b-a))
    elif com == "20":
        a = time.time()
        periyot=input("Periyot: ")
        Araclar.acik_pozisyonlarin_grafigi(periyot)
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "21":
        a = time.time()
        coin=input("Coin: ")
        periyot = input("Periyot: ")
        Araclar.coin_aylik_sonuc(coin,periyot)
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "22":
        a = time.time()
        hedef=int(input("Hedef: "))
        binance.trade_aylik_hedef(hedef)
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "23":
        a = time.time()
        periyot=input("Periyot: ")
        binance.tek_pozisyon_kapat(periyot)
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "24":
        a = time.time()
        import AI
        AI.main()
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
    elif com == "25":
        coin = input("Coin:")
        periyot = input("Periyot (15m,1h,4h,1d):")
        gercek = input("Gercek:") == "True"
        nakit = float(input("Nakit:").replace(",", "."))
        temp_trade = input("Temp Trade:") == "True"
        a = time.time()
        trade.TradeEtAI(coin, periyot, gercek, nakit, temp_trade)
        b = time.time()
        print(araclar.saniye_to_hms(b - a))
if __name__ == "__main__":
    main()

