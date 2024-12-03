#!/bin/bash

# Tmux oturumu adı
SESSION_NAME="Trade"
# Python script'in tam yolu
SCRIPT_PATH="./main.py"  # Kendi script dosyanızın yolunu yazın
# gercek.json dosyasının yolu
JSON_FILE="gercek.json"

# Tarama ve Trade işlemleri için periyot listeleri
PERIODS=("15m" "1h" "1d")

# Gercek.json dosyasının var olup olmadığını kontrol et
if [ ! -f $JSON_FILE ]; then
    echo '{"15m":"False","1h":"False","1d":"False"}' > $JSON_FILE
fi

# Yeni bir tmux oturumu başlatın, ilk pencere otomatik olarak atanacak
tmux new-session -d -s $SESSION_NAME

# Trade işlemleri için tmux pencereleri aç
for i in "${!PERIODS[@]}"; do
    period="${PERIODS[$i]}"
    window_name="Trade_$period"

    # Periyoda göre gercek.json dosyasından değer çekme
    REAL_VALUE=$(jq -r --arg period "$period" '.[$period]' $JSON_FILE)

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
