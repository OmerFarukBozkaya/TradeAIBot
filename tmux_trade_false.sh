#!/bin/bash

# Tmux oturumu adı
SESSION_NAME="Trade"
# Python script'in tam yolu
SCRIPT_PATH="./main.py"  # Kendi script dosyanızın yolunu yazın

# Tarama ve Trade işlemleri için periyot listeleri
PERIODS=("15m" "1h" "1d")

# Yeni bir tmux oturumu başlatın, ilk pencere otomatik olarak atanacak
tmux new-session -d -s $SESSION_NAME

# Trade işlemleri için tmux pencereleri aç
for i in "${!PERIODS[@]}"; do
    period="${PERIODS[$i]}"
    window_name="Trade_$period"

    # Geçici dosya oluştur
    input_file=$(mktemp)
    echo "5" > "$input_file"           # İlk girdi: 5
    echo "$period" >> "$input_file"     # İkinci girdi: period
    echo "False" >> "$input_file"        # Üçüncü girdi: False
    echo "100" >> "$input_file"         # Dördüncü girdi: 100

    # Yeni bir pencere aç ve Python script'ini çalıştır, girdileri dosyadan oku
    tmux new-window -t $SESSION_NAME:$((i+1)) -n "$window_name" "python3 $SCRIPT_PATH < $input_file; rm $input_file; bash"
done

# İlk açılan pencereyi kapat (otomatik açılan boş pencere)
tmux kill-window -t $SESSION_NAME:0

# Oturumu ekranda aktif hale getir
tmux attach -t $SESSION_NAME
