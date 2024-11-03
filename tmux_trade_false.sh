#!/bin/bash

# Tmux oturumu adı
SESSION_NAME="Trade"
# Python script'in tam yolu
SCRIPT_PATH="./main.py"  # Kendi script dosyanızın yolunu yazın

# Tarama ve Trade işlemleri için periyot listeleri
PERIODS=("15m" "1h" "1d")

# Yeni bir tmux oturumu başlatın
tmux new-session -d -s $SESSION_NAME

# Trade işlemleri için tmux pencereleri aç
for period in "${PERIODS[@]}"; do
    tmux new-window -t $SESSION_NAME -n "Trade_$period" "python3 $SCRIPT_PATH << EOF
5
False
$period
False
100
EOF
    bash"
done

# Oturumu ekranda aktif hale getir
tmux attach -t $SESSION_NAME