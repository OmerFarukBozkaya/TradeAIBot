#!/bin/bash

# Alias'ları tanımlayın veya kullanıcıdan yükleyin
if [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi

# Parametre kontrolü
if [ "$#" -lt 2 ]; then
    echo "Kullanım: $0 '<komut>' <kullanıcı1> <kullanıcı2> ... <kullanıcıN>"
    exit 1
fi

COMMAND=$1  # Çalıştırılacak komut (alias dahil olabilir)
TARGET_DIR="TradeAIBot"  # Hedef klasör
shift
USERS=("$@")  # Kullanıcı listesi

for USER in "${USERS[@]}"; do
    HOME_DIR="/home/$USER"
    if [ -d "$HOME_DIR" ]; then
        echo "[$USER] için $TARGET_DIR klasörüne giriş yapılıyor..."

        # Kullanıcının ortamında komutları belirli bir klasörde çalıştır
        su - "$USER" -c "cd $TARGET_DIR && bash -i -c \"$COMMAND\""

        if [ $? -eq 0 ]; then
            echo "[$USER] komut başarıyla çalıştırıldı: $COMMAND"
        else
            echo "[$USER] komut çalıştırılamadı!"
        fi
    else
        echo "[$USER] home dizini bulunamadı: $HOME_DIR"
    fi
done