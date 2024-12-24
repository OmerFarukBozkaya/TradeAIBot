#!/bin/bash

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
        echo "[$USER] dizinine geçiliyor: $HOME_DIR"
        cd "$HOME_DIR/TradeAIBot" || { echo "[$USER] Dizine gidilemiyor!"; continue; }

        echo "[$USER] komut çalıştırılıyor: $COMMAND"
        eval "$COMMAND"
    else
        echo "[$USER] home dizini bulunamadı: $HOME_DIR"
    fi
done