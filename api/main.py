from fastapi import FastAPI
from routes.lote import router as lote_router

app = FastAPI(
    title="API de Procesamiento de Imágenes",
    description=(
        "Sistema distribuido de procesamiento de imágenes por lotes. "
        "Utiliza RabbitMQ para distribución de tareas y workers con Pillow para las transformaciones. "
        "Consulta `GET /info` para ver transformaciones disponibles y ejemplos de uso."
    ),
    version="1.0.0",
)

app.include_router(lote_router)
