# Arquitectura del Sistema — Deploy en VMs

## Diagrama de componentes

```
┌──────────────────────────────────────────────────────────────────────┐
│  PC HOST (Windows 11)                                                │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │  VirtualBox — Bridged Adapter (todas las VMs)                 │   │
│  │                                                               │   │
│  │  ┌──────────────┐  streaming  ┌─────────────────┐            │   │
│  │  │    vm-db     │────────────►│  vm-db-replica  │            │   │
│  │  │192.168.40.13 │             │  192.168.40.17  │            │   │
│  │  │  VDI 10 GB   │             │  (clon vm-db)   │            │   │
│  │  │ PostgreSQL   │             │  PostgreSQL      │            │   │
│  │  │  primario    │             │  standby (R/O)  │            │   │
│  │  └──────┬───────┘             └─────────────────┘            │   │
│  │         │                                                     │   │
│  │         │           ┌──────────────────────────────┐         │   │
│  │         └───────────│         vm-api               │         │   │
│  │                     │      192.168.40.14            │         │   │
│  │                     │       VDI 20 GB               │         │   │
│  │                     │ FastAPI :8000                 │         │   │
│  │                     │ RabbitMQ :5672               │         │   │
│  │                     │ NFS server (api/storage/)    │         │   │
│  │                     └──────────┬───────────────────┘         │   │
│  │                                │ NFS mount                   │   │
│  │         ┌──────────────────────┼──────────────────────┐      │   │
│  │         │                      │                      │      │   │
│  │  ┌──────┴──────┐        ┌──────┴──────┐               │      │   │
│  │  │ vm-worker-1 │        │ vm-worker-2 │               │      │   │
│  │  │192.168.40.15│        │192.168.40.16│               │      │   │
│  │  │  VDI 10 GB  │        │ (clon del  │               │      │   │
│  │  │ worker.py   │        │  anterior) │               │      │   │
│  │  │ N_WORKERS=2 │        │ N_WORKERS=2│               │      │   │
│  │  └─────────────┘        └─────────────┘              │      │   │
│  └───────────────────────────────────────────────────────┘      │   │
│                                                                  │   │
│  ngrok → tunnel HTTPS → vm-api:8000  (para frontend Vercel)     │   │
└──────────────────────────────────────────────────────────────────────┘

Frontend: klin-frontend.vercel.app (HTTPS, externo)
```

---

## VMs y sus VHDs

| VM | VHD | IP fija | Hostname | Servicios |
|----|-----|---------|----------|-----------|
| vm-db | `discos-virtuales/vhd-db.vdi` | 192.168.40.13 | vm-db | PostgreSQL 14 (primario) |
| vm-db-replica | `vms_settings/vm-db-replica/` (clon) | 192.168.40.17 | vm-db-replica | PostgreSQL 14 (standby R/O) |
| vm-api | `discos-virtuales/vhd-api.vdi` | 192.168.40.14 | vm-api | FastAPI + RabbitMQ + NFS server |
| vm-worker-1 | `discos-virtuales/vhd-worker.vdi` | 192.168.40.15 | vm-worker-1 | worker.py + NFS client |
| vm-worker-2 | `vms_settings/vm-worker-2/` (clon) | 192.168.40.16 | vm-worker-2 | worker.py + NFS client |

**IPs estáticas** configuradas via netplan en las 5 VMs — no cambian entre sesiones.

**NOTA**: vm-worker-2 y vm-db-replica se crearon como clones completos (Full clone + Reinitialize MAC).
Sus VHDs quedaron en la carpeta interna de VirtualBox — llevar esas carpetas junto con los otros .vdi.

---

## IPs (estáticas — configuradas via netplan)

```
IP-VM-DB         = 192.168.40.13
IP-VM-DB-REPLICA = 192.168.40.17
IP-VM-API        = 192.168.40.14
IP-VM-WORKER-1   = 192.168.40.15
IP-VM-WORKER-2   = 192.168.40.16
Gateway          = 192.168.40.1
```

---

## Variables de entorno por componente

### VM-API (`~/.env.api`)
```
DATABASE_URL=postgresql://admin:admin123@<IP-VM-DB>:5432/image_processing
SECRET_KEY=mi-clave-secreta-jwt-cambiar-en-produccion
```

### VM-Worker-1 y VM-Worker-2 (`~/.env.worker`)
```
DATABASE_URL=postgresql://admin:admin123@<IP-VM-DB>:5432/image_processing
RABBITMQ_HOST=<IP-VM-API>
N_WORKERS=2
```

---

## Servicios systemd

| VM | Unit | Comando | Auto-restart |
|----|------|---------|--------------|
| vm-api | `api.service` | `uvicorn main:app --host 0.0.0.0 --port 8000` | Restart=always |
| vm-worker-1/2 | `worker.service` | `python worker.py` | Restart=always |

Gestión: `sudo systemctl {start|stop|restart|status} {api|worker}`
Logs: `journalctl -u {api|worker} -f`

---

## Compartición de storage (NFS)

**Problema**: `storage_service.py` escribe en `api/storage/input/` y `image_processor.py`
escribe en `api/storage/output/`. Ambas rutas son relativas al proyecto. Si workers están
en VMs distintas, no tienen acceso a esos archivos.

**Solución**: NFS mount transparente.

```
VM-API exporta:
  /home/ubuntu/image-processing-system/api/storage   →   accesible por red

VM-Worker-1 y VM-Worker-2 montan en la MISMA ruta:
  <IP-VM-API>:/home/ubuntu/.../api/storage  →  /home/ubuntu/.../api/storage
```

El código no cambia — los paths se resuelven igual en todas las VMs.

Entrada en `/etc/fstab` de los workers:
```
<IP-VM-API>:/home/ubuntu/image-processing-system/api/storage \
  /home/ubuntu/image-processing-system/api/storage \
  nfs defaults,_netdev 0 0
```

---

## RabbitMQ — acceso remoto

Por defecto, RabbitMQ solo acepta al usuario `guest` desde `localhost`.
Los workers en otras VMs necesitan conectarse remotamente.

**Configuración en VM-API** (`/etc/rabbitmq/rabbitmq.conf`):
```
loopback_users = none
```

Esto permite que `guest:guest` se conecte desde cualquier IP de la red local.
Sin cambios de código — el worker solo usa `RABBITMQ_HOST` como variable de entorno.

---

## Orden de arranque

```
1. vm-db            → PostgreSQL primario debe estar listo antes que todo
2. vm-db-replica    → puede arrancar en cualquier momento después de vm-db
3. vm-api           → RabbitMQ + API (init_db() crea schema al arrancar)
4. vm-worker-1 y vm-worker-2 → simultáneamente, después de vm-api
```

Orden de apagado (inverso):
```
1. vm-worker-1 y vm-worker-2
2. vm-api
3. vm-db-replica
4. vm-db
```

Si los workers arrancan antes que RabbitMQ esté disponible → se desconectan.
Solución: `sudo systemctl restart worker` en cada worker.

---

## Scripts de deploy

Todos en `scripts/deploy/`:

| Archivo | Propósito |
|---------|-----------|
| `setup_db.sh` | Instala y configura PostgreSQL en vm-db |
| `setup_api.sh` | Instala RabbitMQ, Python, NFS server, api.service en vm-api |
| `setup_worker.sh` | Instala Python, NFS client, worker.service en vm-worker |
| `api.service` | Unidad systemd para uvicorn |
| `worker.service` | Unidad systemd para worker.py |
| `.env.api.example` | Plantilla de variables para vm-api |
| `.env.worker.example` | Plantilla de variables para vm-worker |
| `GUIA_VMS.txt` | Guía completa de creación de VMs e instalación de Ubuntu paso a paso |
| `ARRANQUE.txt` | Guía de arranque ordenado para cada sesión de uso |

---

## Exposición al exterior (ngrok)

El frontend (`klin-frontend.vercel.app`) es HTTPS. No puede llamar a una API HTTP por
política de mixed content del navegador.

**Solución**: ngrok en el PC host crea un túnel HTTPS que apunta a vm-api.

```powershell
# Desde PC host (ngrok ya instalado)
ngrok http <IP-VM-API>:8000
# Copia la URL HTTPS generada → pégala en el frontend → "Configurar API"
```

La URL cambia cada vez que se reinicia ngrok (plan gratuito).

---

## Pruebas

```powershell
# Stress test contra las VMs (genera reporte HTML con Gantt por nodo)
python scripts/stress_test_vms.py `
  --url http://<IP-VM-API>:8000 `
  --db-url postgresql://admin:admin123@<IP-VM-DB>:5432/image_processing

# Generar lote de prueba manual
python scripts/generarbatch.py 5

# Subir lote (PowerShell)
$r = Invoke-RestMethod -Uri "http://<IP-VM-API>:8000/auth/login" `
  -Method POST -ContentType "application/json" `
  -Body '{"correo":"admin@test.com","password":"1234"}'
$TOKEN = $r.access_token
curl -X POST http://<IP-VM-API>:8000/lote `
  -H "Authorization: Bearer $TOKEN" `
  -F "archivos=@lote.zip"
```

---

## Credenciales

| Sistema | Usuario | Contraseña |
|---------|---------|------------|
| VMs (SSH) | ubuntu | ubuntu123 |
| PostgreSQL | admin | admin123 |
| RabbitMQ | guest | guest |
| API (test) | admin@test.com | 1234 |
