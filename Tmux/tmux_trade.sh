#!/bin/bash

# Tmux oturumu adı
SESSION_NAME="Trade"
# Python script'in tam yolu
SCRIPT_PATH="./main.py"  # Kendi script dosyanızın yolunu yazın

# Tarama ve Trade işlemleri için periyot listeleri
PERIODS=("15m" "1h" "1d")

# Gerçek dosyasının var olup olmadığını kontrol et
if [ ! -f gercek.txt ]; then
    # Dosya yoksa, oluştur ve içine 'False' yaz
    echo "False" > gercek.txt
fi

# gercek.txt dosyasını okuyarak True/False değerini değişkene atama
REAL_VALUE=$(cat gercek.txt)

# Yeni bir tmux oturumu başlatın, ilk pencere otomatik olarak atanacak
tmux new-session -d -s $SESSION_NAME

# Trade işlemleri için tmux pencereleri aç
for i in "${!PERIODS[@]}"; do
    period="${PERIODS[$i]}"
    window_name="Trade_$period"

    # Yeni bir pencere aç ve Python script'ini çalıştır, girdileri doğrudan <<EOF ile ver
    tmux new-window -t $SESSION_NAME:$((i+1)) -n "$window_name" "python3 $SCRIPT_PATH <<EOF
5
$period
$REAL_VALUE
100
EOF
    bash"
done

# İlk açılan pencereyi kapat (otomatik açılan boş pencere)
tmux kill-window -t $SESSION_NAME:0

# Oturumu ekranda aktif hale getir
tmux attach -t $SESSION_NAME
