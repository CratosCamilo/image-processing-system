import asyncio

import psutil
from fastapi import APIRouter, Depends, HTTPException, status

from services.auth_service import get_current_user
from services.persistence_service import PersistenceService

router = APIRouter()
persistence = PersistenceService()


@router.get("/metricas", summary="Métricas del sistema")
async def metricas_sistema():
    cpu = await asyncio.get_event_loop().run_in_executor(
        None, lambda: psutil.cpu_percent(interval=0.5)
    )
    mem = psutil.virtual_memory()
    datos = persistence.obtener_metricas_sistema()

    return {
        "sistema": {
            "cpu_porcentaje": cpu,
            "memoria_total_mb": round(mem.total / 1024 / 1024, 1),
            "memoria_usada_mb": round(mem.used / 1024 / 1024, 1),
            "memoria_porcentaje": mem.percent,
        },
        "procesamiento": {
            "total_lotes": datos["total_lotes"],
            "lotes_por_estado": datos["lotes_por_estado"],
            "total_imagenes": datos["total_imagenes"],
            "imagenes_por_estado": datos["imagenes_por_estado"],
        },
        "workers_activos": datos["workers_activos"],
    }


@router.get("/lote/{id_lote}/metricas", summary="Métricas de un lote")
async def metricas_lote(id_lote: str, current_user: dict = Depends(get_current_user)):
    lote = persistence.obtener_lote(id_lote)
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado")
    if not persistence.verificar_propietario_lote(id_lote, current_user["id_usuario"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene acceso a este lote",
        )

    datos = persistence.obtener_metricas_lote(id_lote)
    imagenes = datos["imagenes"]
    trans_counts = datos["trans_counts"]
    tiempos = datos["tiempos"]

    total = len(imagenes)
    completadas = sum(1 for i in imagenes if i["estado"] == "completado")
    errores = sum(1 for i in imagenes if i["estado"] == "error")
    tasa_exito = round(completadas / total * 100, 1) if total > 0 else 0.0

    tiempos_validos = [
        float(i["tiempo_segundos"])
        for i in imagenes
        if i["tiempo_segundos"] is not None
    ]

    tiempo_total = None
    if tiempos.get("inicio") and tiempos.get("fin"):
        tiempo_total = round(
            (tiempos["fin"] - tiempos["inicio"]).total_seconds(), 2
        )

    return {
        "id_lote": id_lote,
        "estado": lote["estado"],
        "fecha_creacion": lote["fecha_creacion"],
        "resumen": {
            "total_imagenes": total,
            "completadas": completadas,
            "errores": errores,
            "tasa_exito_porcentaje": tasa_exito,
        },
        "tiempos": {
            "tiempo_total_lote_segundos": tiempo_total,
            "tiempo_promedio_por_imagen_segundos": (
                round(sum(tiempos_validos) / len(tiempos_validos), 2)
                if tiempos_validos else None
            ),
            "imagen_mas_rapida_segundos": (
                round(min(tiempos_validos), 2) if tiempos_validos else None
            ),
            "imagen_mas_lenta_segundos": (
                round(max(tiempos_validos), 2) if tiempos_validos else None
            ),
        },
        "workers_utilizados": list({i["id_nodo"] for i in imagenes if i["id_nodo"]}),
        "imagenes": [
            {
                "nombre": i["nombre_archivo"],
                "formato": i["formato"],
                "resolucion": i["resolucion"],
                "estado": i["estado"],
                "worker": i["id_nodo"],
                "tiempo_segundos": (
                    round(float(i["tiempo_segundos"]), 2)
                    if i["tiempo_segundos"] is not None else None
                ),
                "num_transformaciones": trans_counts.get(i["nombre_archivo"], 0),
            }
            for i in imagenes
        ],
    }
