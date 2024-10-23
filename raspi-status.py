import os
import psutil
import shutil

# 1. CPU Sıcaklığını alma
def get_cpu_temperature():
    temp = os.popen("vcgencmd measure_temp").readline()
    return temp.replace("temp=", "").strip()

# 2. CPU kullanımını alma (çekirdek başına)
def get_cpu_usage():
    return psutil.cpu_percent(interval=1)

def get_cpu_per_core_usage():
    return psutil.cpu_percent(interval=1, percpu=True)

# 3. RAM kullanımını alma
def get_ram_usage():
    ram_info = psutil.virtual_memory()
    total = ram_info.total / (1024 ** 2)
    used = ram_info.used / (1024 ** 2)
    return total, used

# 4. Disk kullanımını alma
def get_disk_usage():
    total, used, free = shutil.disk_usage("/")
    return total / (1024 ** 3), used / (1024 ** 3), free / (1024 ** 3)

# 5. Swap Belleği kullanımını alma
def get_swap_usage():
    swap = psutil.swap_memory()
    return swap.total / (1024 ** 2), swap.used / (1024 ** 2)

# 6. Ağ durumu ve trafiği
def get_network_info():
    net_io = psutil.net_io_counters()
    return net_io.bytes_sent / (1024 ** 2), net_io.bytes_recv / (1024 ** 2)

# 7. Uptime (cihazın çalışma süresi)
def get_uptime():
    uptime_seconds = os.popen('awk \'{print $1}\' /proc/uptime').readline().strip()
    uptime_hours = float(uptime_seconds) / 3600
    return uptime_hours

# 8. Yük ortalaması
def get_load_average():
    return os.getloadavg()

# 9. GPU Belleği
def get_gpu_memory():
    gpu_mem = os.popen("vcgencmd get_mem gpu").readline()
    return gpu_mem.replace("gpu=", "").strip()

# 10. USB cihazları listele
def list_usb_devices():
    devices = os.popen("lsusb").readlines()
    return [device.strip() for device in devices]

# Tüm bilgileri yazdırma
def list_system_info():
    cpu_temp = get_cpu_temperature()
    cpu_usage = get_cpu_usage()
    cpu_per_core = get_cpu_per_core_usage()
    ram_total, ram_used = get_ram_usage()
    disk_total, disk_used, disk_free = get_disk_usage()
    swap_total, swap_used = get_swap_usage()
    net_sent, net_recv = get_network_info()
    uptime_hours = get_uptime()
    load_avg = get_load_average()
    gpu_mem = get_gpu_memory()
    usb_devices = list_usb_devices()

    print("Raspberry Pi Sistem Bilgileri:")
    print(f"1. CPU Sıcaklığı: {cpu_temp}")
    print(f"2. CPU Kullanımı: {cpu_usage}%")
    print(f"3. CPU Çekirdek Kullanımları: {cpu_per_core}")
    print(f"4. RAM Toplam: {ram_total:.2f} MB")
    print(f"5. RAM Kullanılan: {ram_used:.2f} MB {(ram_used/ram_total)*100:.2f}%")
    print(f"6. Disk Toplam: {disk_total:.2f} GB")
    print(f"7. Disk Kullanılan: {disk_used:.2f} GB {(disk_used/disk_total)*100:.2f}%")
    print(f"8. Disk Boş: {disk_free:.2f} GB {(disk_free/disk_total)*100:.2f}%")
    print(f"9. Swap Toplam: {swap_total:.2f} MB")
    print(f"10. Swap Kullanılan: {swap_used:.2f} MB {(swap_used/swap_total)*100}%")
    print(f"11. Ağ - Gönderilen: {net_sent:.2f} MB")
    print(f"12. Ağ - Alınan: {net_recv:.2f} MB")
    print(f"13. Uptime: {uptime_hours:.2f} saat")
    print(f"14. Yük Ortalaması (1, 5, 15 dakika): {load_avg}")
    print(f"15. GPU Belleği: {gpu_mem}")
    print("16. USB Cihazları:")
    for device in usb_devices:
        print(f"   {device}")

# Betiği çalıştırma
if __name__ == "__main__":
    list_system_info()
