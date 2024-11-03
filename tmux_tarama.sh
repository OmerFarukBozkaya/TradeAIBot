#!/bin/bash

# Tmux oturumu adı
SESSION_NAME="Tarama"
# Python script'in tam yolu
SCRIPT_PATH="./main.py"  # Kendi script dosyanızın yolunu yazın

# Tarama ve Trade işlemleri için periyot listeleri
PERIODS=("15m" "1h" "1d")

# Yeni bir tmux oturumu başlatın
tmux new-session -d -s $SESSION_NAME

# Tarama işlemleri için tmux pencereleri aç
for period in "${PERIODS[@]}"; do
    tmux new-window -t $SESSION_NAME -n "Tarama_$period" "python3 $SCRIPT_PATH << EOF
4
$period
EOF
    bash"
done

# Oturumu ekranda aktif hale getir
tmux attach -t $SESSION_NAME