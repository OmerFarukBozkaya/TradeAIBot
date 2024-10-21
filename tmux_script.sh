#!/bin/bash

# tmux oturumu adı
SESSION_NAME="trading_session"

# Python script'in tam yolu
SCRIPT_PATH="./main.py"  # Kendi script dosyanızın yolunu yazın

# Periyot listeleri
TARAMA_PERIODS=("15m" "1h" "4h" "1d")
TRADE_PERIODS=("15m" "1h" "4h" "1d")

# Yeni bir tmux oturumu başlatın
tmux new-session -d -s $SESSION_NAME

# Tarama işlemleri için tmux pencereleri aç
for i in "${!TARAMA_PERIODS[@]}"; do
    period=${TARAMA_PERIODS[$i]}
    tmux new-window -t $SESSION_NAME -n "Tarama_$period" "python3 $SCRIPT_PATH << EOF
4
$period
EOF
    bash"
done

# Trade işlemleri için tmux pencereleri aç
for i in "${!TRADE_PERIODS[@]}"; do
    period=${TRADE_PERIODS[$i]}
    tmux new-window -t $SESSION_NAME -n "Trade_$period" "python3 $SCRIPT_PATH << EOF
5
$period
False
1000
SAT
EOF
    bash"
done

# Oturumu ekranda aktif hale getir
tmux attach -t $SESSION_NAME
