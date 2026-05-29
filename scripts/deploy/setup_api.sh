#!/bin/bash
set -e

PROYECTO="$HOME/image-processing-system"

echo "============================================================"
echo "  SETUP VM-API — FastAPI + RabbitMQ + NFS server"
echo "============================================================"

# ---- Verificar que el .env.api existe y tiene la IP de VM-DB ----
if [ ! -f "$HOME/.env.api" ]; then
    echo ""
    echo "ERROR: No existe $HOME/.env.api"
    echo "Cópialo desde el proyecto:"
    echo "  cp $PROYECTO/scripts/deploy/.env.api.example $HOME/.env.api"
    echo "Luego edítalo con la IP real de VM-DB y vuelve a ejecutar este script."
    exit 1
fi

if grep -q "<IP-VM-DB>" "$HOME/.env.api"; then
    echo ""
    echo "ERROR: Debes reemplazar <IP-VM-DB> con la IP real en $HOME/.env.api"
    echo "Usa: nano $HOME/.env.api"
    exit 1
fi

echo ""
echo ">>> Actualizando paquetes..."
sudo apt update -y

echo ""
echo ">>> Instalando Python, RabbitMQ y servidor NFS..."
sudo apt install -y python3 python3-pip python3-venv rabbitmq-server nfs-kernel-server

echo ""
echo ">>> Configurando RabbitMQ (permitir usuario 'guest' desde red local)..."
sudo mkdir -p /etc/rabbitmq
echo "loopback_users = none" | sudo tee /etc/rabbitmq/rabbitmq.conf
sudo systemctl enable rabbitmq-server
sudo systemctl restart rabbitmq-server
echo "    RabbitMQ corriendo en puerto 5672"

echo ""
echo ">>> Creando entorno virtual Python para la API..."
cd "$PROYECTO/api"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
deactivate
echo "    Dependencias instaladas."

echo ""
echo ">>> Creando directorios de storage..."
mkdir -p "$PROYECTO/api/storage/input"
mkdir -p "$PROYECTO/api/storage/output"

echo ""
echo ">>> Configurando NFS — exportando storage a los workers..."
STORAGE_PATH="$PROYECTO/api/storage"

if ! sudo grep -qF "$STORAGE_PATH" /etc/exports 2>/dev/null; then
    echo "$STORAGE_PATH *(rw,sync,no_subtree_check,no_root_squash)" | sudo tee -a /etc/exports
fi

sudo systemctl enable nfs-kernel-server
sudo systemctl start nfs-kernel-server
sudo exportfs -ra
echo "    Export NFS activo: $STORAGE_PATH"

echo ""
echo ">>> Instalando servicio systemd para la API (api.service)..."
sudo cp "$PROYECTO/scripts/deploy/api.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable api
sudo systemctl start api

echo ""
echo ">>> Verificando estado del servicio..."
sleep 3
if sudo systemctl is-active --quiet api; then
    echo "    api.service está CORRIENDO."
else
    echo "    ADVERTENCIA: api.service no inició correctamente."
    echo "    Revisa los logs con: journalctl -u api -n 30"
fi

echo ""
echo "============================================================"
echo "  VM-API lista."
echo ""
echo "  IP de esta VM (anótala):"
hostname -I | awk '{print "    " $1}'
echo ""
echo "  Los workers usarán esta IP para:"
echo "    RABBITMQ_HOST=<esta IP>"
echo "    y para el mount NFS de storage"
echo ""
echo "  Verificar API: curl http://$(hostname -I | awk '{print $1}'):8000/info"
echo "============================================================"
