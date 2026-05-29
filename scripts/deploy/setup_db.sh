#!/bin/bash
set -e

echo "============================================================"
echo "  SETUP VM-DB — PostgreSQL"
echo "============================================================"

echo ""
echo ">>> Actualizando paquetes..."
sudo apt update -y

echo ""
echo ">>> Instalando PostgreSQL..."
sudo apt install -y postgresql

# Detectar version instalada
PG_VERSION=$(pg_lsclusters -h | awk '{print $1}' | head -1)
echo "    Versión detectada: PostgreSQL $PG_VERSION"

echo ""
echo ">>> Creando usuario 'admin' y base de datos 'image_processing'..."
sudo -u postgres psql -c "CREATE USER admin WITH PASSWORD 'admin123';" 2>/dev/null || echo "    (usuario ya existía, ok)"
sudo -u postgres psql -c "CREATE DATABASE image_processing OWNER admin;" 2>/dev/null || echo "    (base de datos ya existía, ok)"

echo ""
echo ">>> Configurando acceso remoto desde cualquier IP..."

PG_CONF=$(sudo find /etc/postgresql -name "postgresql.conf" 2>/dev/null | head -1)
PG_HBA=$(sudo find /etc/postgresql -name "pg_hba.conf" 2>/dev/null | head -1)

# listen_addresses = '*'
sudo sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" "$PG_CONF"
sudo sed -i "s/listen_addresses = 'localhost'/listen_addresses = '*'/" "$PG_CONF"

# Agregar regla md5 para cualquier IP (solo si no está ya)
if ! sudo grep -q "0.0.0.0/0" "$PG_HBA"; then
    echo "host    all             all             0.0.0.0/0               md5" | sudo tee -a "$PG_HBA"
fi

echo ""
echo ">>> Reiniciando y habilitando PostgreSQL..."
sudo systemctl restart postgresql
sudo systemctl enable postgresql

echo ""
echo "============================================================"
echo "  VM-DB lista."
echo ""
echo "  IP de esta VM (anótala):"
hostname -I | awk '{print "    " $1}'
echo ""
echo "  Usa esta IP como <IP-VM-DB> en los .env de la API y workers:"
echo "  DATABASE_URL=postgresql://admin:admin123@<IP-VM-DB>:5432/image_processing"
echo "============================================================"
