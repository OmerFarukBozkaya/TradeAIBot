import requests
import time
import traceback
from Araclar import Araclar
import os

araclar = Araclar()

# İnternet bağlantısını kontrol eden fonksiyon
def internet_var_mi():
    try:
        # Google'a bir istek göndererek internet bağlantısını kontrol ediyoruz
        response = requests.get("https://www.google.com", timeout=5)
        # Eğer durum kodu 200 ise bağlantı başarılı
        if response.status_code == 200:
            return True
    except (requests.ConnectionError, requests.Timeout):
        return False
    return False

# IP adresini alan fonksiyon
def get_ip():
    try:
        if internet_var_mi():
            response = requests.get('https://api64.ipify.org?format=json', timeout=5)
            if response.status_code == 200:
                return response.json().get('ip')
    except requests.RequestException as e:
        print("Error during IP fetching: " + str(e))
    return None

# IP değiştiğinde mail gönder ve dosyaya yaz
def kontrol_ve_mesaj_gonder():
    try:
        # Geçerli IP'yi al
        current_ip = get_ip()

        # Eğer internet bağlantısı varsa ve IP değişmişse
        if current_ip:
            # Dosya mevcut değilse oluştur
            path = "Data/ip.txt"
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if not os.path.exists(path):
                with open(path, "w") as dosya_yaz:
                    dosya_yaz.write(current_ip)
                return  # İlk seferde mail göndermeye gerek yok

            # Dosya varsa IP adresini oku ve karşılaştır

            with open(path, "r") as dosya_oku:
                eski_ip = dosya_oku.readline().strip()

            # Yeni ve eski IP aynı ise mail gönderme
            if eski_ip == current_ip:
                return

            # IP değişmişse mail gönder
            araclar.telegram_mesaj_gonder(f"🌐 IP Değişti Yeni IP: {current_ip}")

            # Dosyayı güncelle
            with open(path, "w") as dosya_yaz:
                dosya_yaz.write(current_ip)
    except Exception as e:
        hata_mesaji = traceback.format_exc()
        araclar.mail_gonder("HATA | IP", hata_mesaji, 300)
        print("Bir hata oluştu: ", hata_mesaji)

def main():
    while True:
        kontrol_ve_mesaj_gonder()
        time.sleep(60)  # 60 saniye bekle

# Uygulamayı çalıştır
if __name__ == "__main__":
    main()
