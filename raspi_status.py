import os
import psutil
import shutil
import socket

class raspi_status:
    # 1. CPU Sıcaklığı
    @staticmethod
    def get_cpu_temperature():
        temp = os.popen("sudo vcgencmd measure_temp").readline()
        return temp.replace("temp=", "").strip()

    # 2. CPU Frekansı
    @staticmethod
    def get_cpu_frequency():
        freq = os.popen("sudo vcgencmd measure_clock arm").readline()
        return int(freq.split("=")[1].strip()) / 1_000_000  # MHz cinsinden

    # 3. CPU Gerilimi
    @staticmethod
    def get_cpu_voltage():
        voltage = os.popen("sudo vcgencmd measure_volts").readline()
        return voltage.replace("volt=", "").strip()

    # 4. CPU Kullanımı (çekirdek başına)
    @staticmethod
    def get_cpu_usage():
        return psutil.cpu_percent(interval=1)

    # 5. RAM Kullanımı
    @staticmethod
    def get_ram_usage():
        ram_info = psutil.virtual_memory()
        total = ram_info.total / (1024 ** 2)
        used = ram_info.used / (1024 ** 2)
        return total, used

    # 6. Disk Kullanımı
    @staticmethod
    def get_disk_usage():
        total, used, free = shutil.disk_usage("/")
        return total / (1024 ** 3), used / (1024 ** 3), free / (1024 ** 3)

    # 7. Ağ Trafiği ve IP Adresleri
    @staticmethod
    def get_network_info():
        net_io = psutil.net_io_counters()
        interfaces = raspi_status.get_network_interfaces()
        return interfaces, net_io.bytes_sent / (1024 ** 2), net_io.bytes_recv / (1024 ** 2)

    # Ağ Bağlantıları ve IP Adresleri
    @staticmethod
    def get_network_interfaces():
        addrs = psutil.net_if_addrs()
        interfaces = {}
        for interface_name, address_list in addrs.items():
            for addr in address_list:
                if addr.family == socket.AF_INET:  # IPv4 adresleri için socket.AF_INET kullanılır
                    interfaces[interface_name] = addr.address
        return interfaces

    # 8. Uptime
    @staticmethod
    def get_uptime():
        uptime_seconds = os.popen('awk \'{print $1}\' /proc/uptime').readline().strip()
        uptime_hours = float(uptime_seconds) / 3600
        return uptime_hours

    # 9. Yük Ortalaması
    @staticmethod
    def get_load_average():
        return os.getloadavg()

    # 10. GPU Belleği
    @staticmethod
    def get_gpu_memory():
        gpu_mem = os.popen("sudo vcgencmd get_mem gpu").readline()
        return gpu_mem.replace("gpu=", "").strip()

    # 11. Bluetooth Durumu
    @staticmethod
    def get_bluetooth_status():
        status = os.popen("hciconfig").readlines()
        return "UP" if any("UP RUNNING" in line for line in status) else "DOWN"

    # 13. Raspberry Pi Model ve Seri Numarası
    @staticmethod
    def get_raspberry_pi_info():
        model = os.popen("cat /proc/device-tree/model").readline().strip()
        serial = os.popen("cat /proc/cpuinfo | grep Serial").readline().strip().split(": ")[1]
        return model, serial

    # 14. Fan Hızı
    @staticmethod
    def get_fan_speed():
        fan_speed = os.popen("sudo vcgencmd get_fan_speed").readline()
        return fan_speed.strip() if fan_speed else "Fan bilgisi alınamadı"

    # 16. Güncellemeler
    @staticmethod
    def check_for_updates():
        updates = os.popen("apt list --upgradable").readlines()
        package_count = len(updates) - 1  # İlk satır bilgi satırıdır, bu yüzden 1 çıkar
        return package_count

    # Tüm bilgileri yazdırma
    @staticmethod
    def list_system_info():
        cpu_temp = raspi_status.get_cpu_temperature()
        cpu_freq = raspi_status.get_cpu_frequency()
        cpu_voltage = raspi_status.get_cpu_voltage()
        cpu_usage = raspi_status.get_cpu_usage()
        ram_total, ram_used = raspi_status.get_ram_usage()
        disk_total, disk_used, disk_free = raspi_status.get_disk_usage()
        interfaces, net_sent, net_recv = raspi_status.get_network_info()
        uptime_hours = raspi_status.get_uptime()
        load_avg = raspi_status.get_load_average()
        gpu_mem = raspi_status.get_gpu_memory()
        bluetooth_status = raspi_status.get_bluetooth_status()
        model, serial = raspi_status.get_raspberry_pi_info()
        fan_speed = raspi_status.get_fan_speed()

        print("Raspberry Pi Sistem Bilgileri:")
        print(f"1. CPU Sıcaklığı: {cpu_temp}")
        print(f"2. CPU Frekansı: {cpu_freq} MHz")
        print(f"3. CPU Gerilimi: {cpu_voltage}")
        print(f"4. CPU Kullanımı: {cpu_usage}%")
        print(f"5. RAM Toplam: {ram_total:.2f} MB")
        print(f"6. RAM Kullanılan: {ram_used:.2f} MB {(ram_used / ram_total) * 100:.2f}%")
        print(f"7. Disk Toplam: {disk_total:.2f} GB")
        print(f"8. Disk Kullanılan: {disk_used:.2f} GB {(disk_used / disk_total) * 100:.2f}%")
        print(f"9. Disk Boş: {disk_free:.2f} GB {(disk_free / disk_total) * 100:.2f}%")
        print(f"10. Ağ Bağlantıları ve IP'leri: {interfaces}")
        print(f"11. Ağ - Gönderilen: {net_sent:.2f} MB")
        print(f"12. Ağ - Alınan: {net_recv:.2f} MB")
        print(f"13. Uptime: {uptime_hours:.2f} saat")
        print(f"14. Yük Ortalaması (1, 5, 15 dakika): {load_avg}")
        print(f"15. GPU Belleği: {gpu_mem}")
        print(f"16. Bluetooth Durumu: {bluetooth_status}")
        print(f"17. Model: {model}")
        print(f"18. Seri Numarası: {serial}")
        print(f"19. Fan Hızı: {fan_speed}")
        package_count = raspi_status.check_for_updates()
        if package_count > 0:
            print(f"20. Güncelleme Durumu: Güncellenebilir paket sayısı: {package_count}")
            print("Güncelleme için çalıştırılması gereken kod: sudo apt update && sudo apt upgrade")
        else:
            print("20. Güncelleme Durumu: Güncellenebilir paket yok.")
