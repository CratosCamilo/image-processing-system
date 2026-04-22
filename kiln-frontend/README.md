# Kiln — Frontend

Interfaz web para el sistema distribuido de procesamiento de imágenes. Consume el API FastAPI descrito en el proyecto padre sin tocarlo.

> **Kiln** forja lotes de imágenes en paralelo: subes N imágenes, defines transformaciones globales e individuales, y el sistema las procesa de forma distribuida.

## Stack

- HTML + CSS + JavaScript vanilla (sin build step, sin frameworks)
- Sin dependencias de npm — todo corre en el navegador
- Google Fonts (Inter + JetBrains Mono) como única dependencia externa

## Cómo correr en local

No hay build — basta con servir la carpeta con cualquier static server:

```bash
# opción 1 — python
cd kiln-frontend
python -m http.server 5500

# opción 2 — node (si tienes npx)
npx serve kiln-frontend -p 5500
```

Luego abre `http://localhost:5500`. La API debe estar corriendo en `http://localhost:8000` (configurable desde el ícono de ajustes del topbar).

**Credenciales de prueba:** `admin@test.com` / `1234` (seed del backend).

## Configuración del API

La URL del backend se guarda en `localStorage` bajo la clave `kiln:api_base`. Default: `http://localhost:8000`.

Puedes cambiarla en tiempo real desde el botón de engranaje del topbar — útil para apuntar a una VM de deploy o a otro entorno.

## CORS (importante para deploy en Vercel)

El backend **no tiene CORS habilitado por defecto**. Cuando despliegues Kiln en Vercel y apuntes a una API remota, necesitarás una de estas dos opciones:

1. **Habilitar CORS en el backend** (preferido) — agregar `CORSMiddleware` al `api/main.py` con `allow_origins=["https://tu-dominio.vercel.app"]`.
2. **Proxy via `vercel.json`** — usar rewrites para que Kiln haga requests al mismo origen y Vercel los reenvíe a la API (ver `vercel.json`).

## Deploy en Vercel

```bash
# desde la carpeta kiln-frontend/
vercel deploy
```

Vercel detecta el proyecto como static site automáticamente. El `vercel.json` incluye un ejemplo de rewrite por si prefieres la opción de proxy.

## Estructura

```
kiln-frontend/
├── index.html          # Login
├── forge.html          # Constructor de lote (upload + config)
├── lotes.html          # Historial y estado de lotes
├── lote.html           # Detalle de un lote (polling)
├── info.html           # Docs de transformaciones
├── css/
│   └── styles.css
├── js/
│   ├── api.js          # Cliente HTTP con JWT
│   ├── auth.js         # Login + guard de sesión
│   ├── forge.js        # Lógica del constructor de lote
│   ├── lotes.js        # Listado local de lotes + status
│   ├── lote.js         # Polling del estado de un lote
│   ├── info.js         # Consumo de GET /info
│   ├── topbar.js       # Topbar común (ajustes, logout)
│   └── transformations.js  # Definición de los 11 tipos y sus formularios
├── assets/
│   └── logo.svg
├── BRANDING.md         # Guía visual (paleta, tipografía, tono)
├── README.md
└── vercel.json
```

## Endpoints que consume

| Endpoint                         | Dónde                      |
|----------------------------------|----------------------------|
| `POST /auth/login`               | `index.html`               |
| `GET  /info`                     | `info.html`                |
| `POST /lote`                     | `forge.html`               |
| `GET  /lote/{id}`                | `lotes.html`, `lote.html`  |
| `GET  /lote/{id}/resultado`      | `lote.html` (descarga ZIP) |

Los IDs de los lotes enviados desde este navegador se guardan en `localStorage` bajo `kiln:lotes` para poder listarlos después sin un endpoint de listado.
