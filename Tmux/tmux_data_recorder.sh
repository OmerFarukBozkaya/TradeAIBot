#!/bin/bash

# Coin - Periyot eşleşmeleri (tek tek tanımlı)
declare -a pairs=(
    "BTCUSDT_1h"
)

# Python script dosyasının adı
SCRIPT="./data_recorder.py"

# Tmux oturum adı
SESSION="DataRecorder"

# Sanal ortam aktivasyon scriptinin yolu
VENV_ACTIVATE="/home/$(whoami)/TradeAIBot/.venv/bin/activate"

# Tmux oturumunu oluştur (eğer yoksa)
tmux has-session -t $SESSION 2>/dev/null
if [ $? != 0 ]; then
    tmux new-session -d -s $SESSION
fi

# Sanal ortam aktivasyon komutu
VENV_CMD="source $VENV_ACTIVATE && "

# Her coin-periyot çifti için ayrı pencere aç
for pair in "${pairs[@]}"
do
    IFS='_' read -r coin periyod <<< "$pair"
    WINDOW_NAME="${coin}_${periyod}"

    echo "Başlatılıyor: $WINDOW_NAME"

    tmux new-window -t $SESSION -n "$WINDOW_NAME"
    tmux send-keys -t $SESSION:"$WINDOW_NAME" "python3 $SCRIPT $coin $periyod" C-m
done

echo "Tüm işlemler başlatıldı. İzlemek için: tmux attach -t $SESSION"

# İlk açılan pencereyi kapat
tmux kill-window -t $SESSION_NAME:0