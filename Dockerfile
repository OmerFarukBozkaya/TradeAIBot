# 1. Resmi Python görüntüsünü kullan
FROM python:3.10

# 3. Bağımlılıkları kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Proje dosyalarını kopyala
COPY . .

# 5. Container çalıştırıldığında çalıştırılacak komutu belirle
CMD ["python", "main.py"]
