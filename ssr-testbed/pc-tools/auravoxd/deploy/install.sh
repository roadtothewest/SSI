#!/bin/sh
# Se corre EN LA RASPBERRY, en la carpeta donde se copiaron auravoxd y auravoxd.service:
#   sudo sh install.sh
set -e

install -m 755 auravoxd /usr/local/bin/auravoxd
install -m 644 auravoxd.service /etc/systemd/system/auravoxd.service
mkdir -p /home/aura/auravox && chown aura:aura /home/aura/auravox

# SPI0 habilitado (crea /dev/spidev0.0); hace falta reiniciar si se agrega.
CFG=/boot/firmware/config.txt
[ -f "$CFG" ] || CFG=/boot/config.txt
if ! grep -q '^dtparam=spi=on' "$CFG"; then
    echo 'dtparam=spi=on' >> "$CFG"
    echo "SPI habilitado en $CFG: reinicia la Pi (sudo reboot) para que aparezca /dev/spidev0.0"
fi

systemctl daemon-reload
systemctl enable --now auravoxd
systemctl --no-pager status auravoxd | head -5
echo "HMI: http://$(hostname -I | awk '{print $1}'):8080"
