from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.auth import router as auth_router
from routes.lote import router as lote_router
from routes.metricas import router as metricas_router
from services.rabbitmq_service import conectar


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.rabbit = await conectar()
    except Exception as e:
        # RabbitMQ no disponible al iniciar: la API arranca igual pero rechazara
        # los POST /lote con 503 hasta que el servicio de cola este levantado.
        print(f"[RabbitMQ] No disponible al iniciar: {e}")
        app.state.rabbit = None
    yield
    if app.state.rabbit is not None:
        await app.state.rabbit.close()


app = FastAPI(
    title="API de Procesamiento de Imágenes",
    description=(
        "Sistema distribuido de procesamiento de imágenes por lotes. "
        "Utiliza RabbitMQ para distribución de tareas y workers con Pillow para las transformaciones. "
        "Consulta `GET /info` para ver transformaciones disponibles y ejemplos de uso."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — solo afecta a clientes que envían el header `Origin` (navegadores).
# Postman, curl, stress_test.py y demás clientes no-browser quedan indiferentes.
#
# allow_credentials=False + allow_origins=["*"] funciona con Bearer tokens
# (el header Authorization se envía manualmente desde el frontend, no depende
# del modo "credentials" de fetch). La seguridad real la aplica JWT, no CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(lote_router)
app.include_router(metricas_router)
