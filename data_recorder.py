import time
import os
import pandas as pd
import logging
from Binance import Binance
from Araclar import Araclar
import sys

# Logging ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def dosya_var_mi_ve_bos_mu(dosya_yolu: str) -> bool:
    return not os.path.exists(dosya_yolu) or os.stat(dosya_yolu).st_size == 0

def csv_baslat(binance: Binance, coin: str, periyod: str, dosya_yolu: str) -> None:
    logging.info(f"Yeni dosya oluşturuluyor: {dosya_yolu}")
    veri = binance.get_coin_data(coin, periyod, 1000)
    pd.DataFrame(veri).to_csv(dosya_yolu, index=False)

def csv_guncelle(binance: Binance, coin: str, periyod: str, dosya_yolu: str) -> None:
    yeni_veri = pd.DataFrame(binance.get_coin_data(coin, periyod, 1000))
    yeni_veri = yeni_veri.iloc[:-1,:]
    mevcut_veri = pd.read_csv(dosya_yolu) if os.stat(dosya_yolu).st_size > 0 else pd.DataFrame()

    if not mevcut_veri.empty:
        son_zaman = mevcut_veri.iloc[-1]['opendate']
        yeni_satirlar = yeni_veri[yeni_veri['opendate'] > son_zaman]

        if not yeni_satirlar.empty:
            birlesik = pd.concat([mevcut_veri, yeni_satirlar])
            birlesik.to_csv(dosya_yolu, index=False)
            logging.info(f"{len(yeni_satirlar)} yeni satır eklendi. Toplam: {len(birlesik)}")
        else:
            logging.info("Yeni veri yok.")
    else:
        yeni_veri.to_csv(dosya_yolu, index=False)
        logging.info("İlk veri kaydedildi.")

def periyodik_veri_guncelle(binance: Binance, araclar: Araclar, coin: str, periyod: str, csv_yolu: str) -> None:
    while True:
        try:
            csv_guncelle(binance, coin, periyod, csv_yolu)

            # Bekleme süresi (örnek: her 10 saniyede bir kontrol, toplam 2000 saniye)
            bekleme_suresi = 200  # saniye cinsinden toplam süre
            aralik = 10  # her adım arası saniye
            for _ in range(bekleme_suresi // aralik):
                araclar.mum_olusmasini_bekle(periyod)
                time.sleep(aralik)

        except Exception as e:
            logging.error(f"Hata oluştu: {str(e)}")
            time.sleep(60)

def main(coin, periyod):
    binance = Binance()
    araclar = Araclar()

    dosya_yolu = f'Data/{coin}_{periyod}.csv'
    os.makedirs('Data', exist_ok=True)

    if dosya_var_mi_ve_bos_mu(dosya_yolu):
        csv_baslat(binance, coin, periyod, dosya_yolu)
    else:
        logging.info(f"Mevcut dosya kullanılıyor: {dosya_yolu}")

    periyodik_veri_guncelle(binance, araclar, coin, periyod, dosya_yolu)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Kullanım: python main.py COIN PERIYOD")
        exit(1)

    coin = sys.argv[1]
    periyod = sys.argv[2]
    main(coin, periyod)
