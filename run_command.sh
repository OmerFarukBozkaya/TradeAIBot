#!/bin/bash

alias trade_durdur="tmux kill-session -t Trade"
alias tarama_durdur="tmux kill-session -t Tarama"
alias trade_baslat="bash ~/TradeAIBot/Tmux/tmux_trade.sh"

# Komut kontrolü
if [ "$#" -lt 2 ]; then
    echo "Kullanım: $0 '<komut>' <kullanıcı1> <kullanıcı2> ... <kullanıcıN>"
    exit 1
fi

# İlk parametre çalıştırılacak komut
COMMAND=$1

# Kalan parametreler kullanıcılar
shift
USERS=("$@")

# Her bir kullanıcı için işlemleri yap
for USER in "${USERS[@]}"; do
    HOME_DIR="/home/$USER"
    if [ -d "$HOME_DIR" ]; then
        echo "[$USER] için giriş yapılıyor..."

        # Kullanıcı oturumunda komutu çalıştır
        su - "$USER" -c "cd $HOME_DIR/TradeAIBot && $COMMAND"

        if [ $? -eq 0 ]; then
            echo "[$USER] komut başarıyla çalıştırıldı: $COMMAND"
        else
            echo "[$USER] komut çalıştırılamadı!"
        fi
    else
        echo "[$USER] home dizini bulunamadı: $HOME_DIR"
    fi
done