#!/bin/bash
set -e

PROYECTO="$HOME/image-processing-system"
API_STORAGE="$PROYECTO/api/storage"

echo "============================================================"
echo "  SETUP VM-WORKER — Worker + NFS client"
echo "============================================================"

# ---- Verificar que el .env.worker existe y tiene las IPs reales ----
if [ ! -f "$HOME/.env.worker" ]; then
    echo ""
    echo "ERROR: No existe $HOME/.env.worker"
    echo "Cópialo desde el proyecto:"
    echo "  cp $PROYECTO/scripts/deploy/.env.worker.example $HOME/.env.worker"
    echo "Luego edítalo con las IPs reales y vuelve a ejecutar este script."
    exit 1
fi

if grep -q "<IP-VM-DB>" "$HOME/.env.worker" || grep -q "<IP-VM-API>" "$HOME/.env.worker"; then
    echo ""
    echo "ERROR: Debes reemplazar <IP-VM-DB> y <IP-VM-API> con las IPs reales en $HOME/.env.worker"
    echo "Usa: nano $HOME/.env.worker"
    exit 1
fi

# Extraer IP de VM-API desde el .env.worker
API_IP=$(grep "^RABBITMQ_HOST=" "$HOME/.env.worker" | cut -d= -f2 | tr -d ' ')
if [ -z "$API_IP" ]; then
    echo "ERROR: No se encontró RABBITMQ_HOST en $HOME/.env.worker"
    exit 1
fi

echo ""
echo ">>> Actualizando paquetes..."
sudo apt update -y

echo ""
echo ">>> Instalando Python y cliente NFS..."
sudo apt install -y python3 python3-pip python3-venv nfs-common

echo ""
echo ">>> Creando entorno virtual Python para el worker..."
cd "$PROYECTO/worker"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
deactivate
echo "    Dependencias instaladas."

echo ""
echo ">>> Configurando NFS mount (storage de VM-API: $API_IP)..."
mkdir -p "$API_STORAGE"

FSTAB_LINE="$API_IP:$API_STORAGE $API_STORAGE nfs defaults,_netdev 0 0"

if ! grep -qF "$API_IP:$API_STORAGE" /etc/fstab; then
    echo "$FSTAB_LINE" | sudo tee -a /etc/fstab
    echo "    Entrada agregada a /etc/fstab"
else
    echo "    Entrada NFS ya existe en /etc/fstab"
fi

echo "    Montando..."
sudo mount -a

if mountpoint -q "$API_STORAGE"; then
    echo "    NFS montado correctamente en $API_STORAGE"
else
    echo "    ADVERTENCIA: El mount NFS no se realizó."
    echo "    Verifica que VM-API esté encendida y accesible en $API_IP"
    echo "    Intenta manualmente: sudo mount $API_IP:$API_STORAGE $API_STORAGE"
fi

echo ""
echo ">>> Instalando servicio systemd para el worker (worker.service)..."
sudo cp "$PROYECTO/scripts/deploy/worker.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable worker
sudo systemctl start worker

echo ""
echo ">>> Verificando estado del servicio..."
sleep 3
if sudo systemctl is-active --quiet worker; then
    echo "    worker.service está CORRIENDO."
else
    echo "    ADVERTENCIA: worker.service no inició correctamente."
    echo "    Revisa los logs con: journalctl -u worker -n 30"
fi

echo ""
echo "============================================================"
echo "  VM-Worker lista."
echo ""
echo "  IP de esta VM: $(hostname -I | awk '{print $1}')"
echo "  Conectado a VM-API ($API_IP) via NFS y RabbitMQ"
echo ""
echo "  Ver logs del worker: journalctl -u worker -f"
echo "============================================================"
