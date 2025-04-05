#!/bin/bash

# Tmux oturumu adı
SESSION_NAME="Trade"
# Python script'in tam yolu
SCRIPT_PATH="./main.py"
# gercek.json dosyasının yolu
JSON_FILE="gercek.json"
# Trade durumu json dosyalarının bulunduğu dizin
TRADE_DURUMU_DIR="./Trade_Durumu_AI/"  # Kendi dizin yolunuzu yazın
# Sanal ortam aktivasyon scriptinin yolu
VENV_ACTIVATE="/home/omer/TradeAIBot/.venv/bin/activate"

# Tarama ve Trade işlemleri için periyot listeleri
PERIODS=("15m" "1h" "4h" "1d")

# Gercek.json dosyasının var olup olmadığını kontrol et
if [ ! -f $JSON_FILE ]; then
    echo '{"15m":"False","1h":"False","4h":"False","1d":"False","15m_AI":"False","1h_AI":"False","4h_AI":"False","1d_AI":"False"}' > $JSON_FILE
fi

# Yeni bir tmux oturumu başlatın, ilk pencere otomatik olarak atanacak
tmux new-session -d -s $SESSION_NAME

# Sanal ortam aktivasyon komutu
VENV_CMD="source $VENV_ACTIVATE && "

# Trade işlemleri için tmux pencereleri aç
for i in "${!PERIODS[@]}"; do
    period="${PERIODS[$i]}"
    window_name="Trade_$period"

    # Periyoda göre gercek.json dosyasından değer çekme
    REAL_VALUE=$(jq -r --arg period "$period" '.[$period]' $JSON_FILE)

    # Yeni bir pencere aç ve Python script'ini sanal ortamda çalıştır
    tmux new-window -t $SESSION_NAME:$((i+1)) -n "$window_name" \
        "$VENV_CMD python3 $SCRIPT_PATH <<EOF
5
$period
$REAL_VALUE
100
False
EOF
    bash"
done

# Trade durumu json dosyalarını işle
window_counter=${#PERIODS[@]}
window_counter=$((window_counter+1))

# trade_durumu json dosyalarını bul ve işle
for file in "$TRADE_DURUMU_DIR"/trade_durumu_*.json; do
    if [ -f "$file" ]; then
        filename=$(basename "$file" .json)
        IFS='_' read -ra ADDR <<< "$filename"
        periyot="${ADDR[2]}"
        coin="${ADDR[3]}"

        REAL_VALUE=$(jq -r --arg period "${periyot}_AI" '.[$period] // "False"' "$JSON_FILE" 2>/dev/null || echo "False")

        window_name="TradeAI_${periyot}_${coin}"
        tmux new-window -t $SESSION_NAME:$((window_counter)) -n "$window_name" \
            "$VENV_CMD python3 $SCRIPT_PATH <<EOF
25
$coin
$periyot
$REAL_VALUE
100
False
EOF
        bash"

        window_counter=$((window_counter+1))
    fi
done

# Strategys penceresi
tmux new-window -t $SESSION_NAME:$((window_counter)) -n "Strategys" \
    "$VENV_CMD python3 $SCRIPT_PATH <<EOF
13
3d
EOF
    bash"
window_counter=$((window_counter+1))

# Coinlist penceresi
tmux new-window -t $SESSION_NAME:$((window_counter)) -n "Coinlist" \
    "$VENV_CMD python3 $SCRIPT_PATH <<EOF
12
1w
EOF
    bash"

# İlk açılan pencereyi kapat
tmux kill-window -t $SESSION_NAME:0

# Oturumu ekranda aktif hale getir
tmux attach -t $SESSION_NAME