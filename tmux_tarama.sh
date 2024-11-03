#!/bin/bash

# Tmux oturumu adı
SESSION_NAME="Tarama"
# Python script'in tam yolu
SCRIPT_PATH="./main.py"  # Kendi script dosyanızın yolunu yazın

# Tarama ve Trade işlemleri için periyot listeleri
PERIODS=("15m" "1h" "1d")

# Yeni bir tmux oturumu başlatın, ilk pencere otomatik olarak atanacak
tmux new-session -d -s $SESSION_NAME

# Tarama işlemleri için tmux pencereleri aç
for i in "${!PERIODS[@]}"; do
    period="${PERIODS[$i]}"
    window_name="Tarama_$period"

    # Geçici dosya oluştur
    input_file=$(mktemp)
    echo "4" > "$input_file"           # İlk girdi: 4
    echo "$period" >> "$input_file"     # İkinci girdi: period değeri

    # Yeni bir pencere aç ve Python script'ini çalıştır, girdileri dosyadan oku
    tmux new-window -t $SESSION_NAME:$((i+1)) -n "$window_name" "python3 $SCRIPT_PATH < $input_file; rm $input_file; bash"
done

# İlk açılan pencereyi kapat (otomatik açılan boş pencere)
tmux kill-window -t $SESSION_NAME:0

# Oturumu ekranda aktif hale getir
tmux attach -t $SESSION_NAME
