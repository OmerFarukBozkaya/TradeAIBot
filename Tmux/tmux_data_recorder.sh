#!/bin/bash

# Coin - Periyot eşleşmeleri
declare -a pairs=(
    "BTCUSDT_1h"
    "XRPUSDT_1h"
    "BNBUSDT_1h"
    "SOLUSDT_1h"
    # Diğer coin-periyotlar buraya eklenebilir
)

# Python script dosyasının adı
SCRIPT="data_recorder.py"

# Tmux oturum adı
SESSION="DataRecorder"

# Dinamik kullanıcı adını al ve sanal ortam aktivasyon scripti yolunu ayarla
VENV_ACTIVATE="/home/$(whoami)/TradeAIBot/.venv/bin/activate"

# Tmux oturumunu oluştur (eğer yoksa)
tmux has-session -t $SESSION 2>/dev/null
if [ $? != 0 ]; then
    tmux new-session -d -s $SESSION
fi

# Her coin-periyot çifti için ayrı pencere aç
for pair in "${pairs[@]}"
do
    IFS='_' read -r coin periyod <<< "$pair"
    WINDOW_NAME="${coin}_${periyod}"

    echo "Başlatılıyor: $WINDOW_NAME"

    # Yeni pencere oluştur
    tmux new-window -t $SESSION -n "$WINDOW_NAME"

    # Sanal ortamı aktive ederek script'i çalıştır
    tmux send-keys -t $SESSION:"$WINDOW_NAME" "source $VENV_ACTIVATE && python3 $SCRIPT $coin $periyod" C-m
done

# İlk (boş) pencereyi kapat
tmux kill-window -t $SESSION:0

echo "✅ Tüm işlemler başlatıldı. İzlemek için: tmux attach -t $SESSION"
