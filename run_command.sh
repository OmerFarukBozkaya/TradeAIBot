#!/bin/bash

# .bashrc dosyasını kaynak göstererek alias'ları yükleyin
if [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi

# Çalıştırılacak komut kontrolü
if [ "$#" -lt 2 ]; then
    echo "Kullanım: $0 '<komut>' <kullanıcı1> <kullanıcı2> ... <kullanıcıN>"
    exit 1
fi

COMMAND=$1
shift
USERS=("$@")

for USER in "${USERS[@]}"; do
    HOME_DIR="/home/$USER"
    if [ -d "$HOME_DIR" ]; then
        echo "[$USER] için giriş yapılıyor..."

        # Kullanıcının alias'larını ve ortamını kullanarak komutu çalıştır
        su - "$USER" -c "cd $HOME_DIR && source ~/.bashrc && cd TradeAIBot && $COMMAND"

        if [ $? -eq 0 ]; then
            echo "[$USER] komut başarıyla çalıştırıldı: $COMMAND"
        else
            echo "[$USER] komut çalıştırılamadı!"
        fi
    else
        echo "[$USER] home dizini bulunamadı: $HOME_DIR"
    fi
done