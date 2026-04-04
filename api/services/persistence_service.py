import json
from datetime import datetime

from db.database import get_connection

# IDs de estado — deben coincidir con el seed de database.py
ESTADO_LOTE_ID      = {"pendiente": 1, "procesando": 2, "completado": 3, "error": 4}
ESTADO_TAREA_ID     = {"pendiente": 1, "procesando": 2, "completado": 3, "error": 4}
ESTADO_RESULTADO_ID = {"pendiente": 1, "generado": 2, "error": 3}
TRANSFORMACION_TIPO_ID = {"resize": 1, "grayscale": 2, "rotate": 3}


class PersistenceService:

    # ------------------------------------------------------------------ lote

    def crear_lote(self, id_lote: str) -> None:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO lote_procesamiento
                   (id_lote, fecha_creacion, id_estado_lote)
                   VALUES (?, ?, ?)""",
                (id_lote, datetime.now().isoformat(), ESTADO_LOTE_ID["procesando"]),
            )

    def obtener_lote(self, id_lote: str) -> dict | None:
        """Retorna el lote con 'estado' como nombre legible (JOIN con estado_lote)."""
        with get_connection() as conn:
            row = conn.execute(
                """SELECT lp.id_lote, lp.fecha_creacion, lp.id_estado_lote,
                          el.nombre AS estado
                   FROM lote_procesamiento lp
                   LEFT JOIN estado_lote el ON lp.id_estado_lote = el.id_estado_lote
                   WHERE lp.id_lote = ?""",
                (id_lote,),
            ).fetchone()
            return dict(row) if row else None

    def obtener_estadisticas_lote(self, id_lote: str) -> dict:
        with get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM imagen WHERE id_lote = ?", (id_lote,)
            ).fetchone()[0]
            # imagen siempre tiene todas las filas desde el inicio → fuente de verdad para total
            # tarea_procesamiento solo existe cuando el worker la crea → usar para completadas
            tareas_existentes = conn.execute(
                "SELECT COUNT(*) FROM tarea_procesamiento WHERE id_lote = ?", (id_lote,)
            ).fetchone()[0]
            if tareas_existentes > 0:
                completadas = conn.execute(
                    "SELECT COUNT(*) FROM tarea_procesamiento WHERE id_lote = ? AND id_estado_tarea = ?",
                    (id_lote, ESTADO_TAREA_ID["completado"]),
                ).fetchone()[0]
            else:
                completadas = conn.execute(
                    "SELECT COUNT(*) FROM imagen WHERE id_lote = ? AND id_estado_tarea = ?",
                    (id_lote, ESTADO_TAREA_ID["completado"]),
                ).fetchone()[0]
            return {"total": total, "completadas": completadas}

    # --------------------------------------------------------------- imagen

    def guardar_imagen(
        self, id_lote: str, id_imagen: str, nombre: str, ruta: str,
        formato: str, resolucion: str
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO imagen
                   (id_imagen, id_lote, nombre_archivo, ruta_origen, id_estado_tarea, formato, resolucion)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (id_imagen, id_lote, nombre, ruta, ESTADO_TAREA_ID["pendiente"],
                 formato, resolucion),
            )

    def actualizar_estado_imagen(self, id_imagen: str, estado: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE imagen SET id_estado_tarea = ? WHERE id_imagen = ?",
                (ESTADO_TAREA_ID[estado], id_imagen),
            )

    # --------------------------------------------------- transformaciones

    def guardar_transformaciones(self, id_imagen: str, json_data: dict) -> None:
        transformaciones = (
            json_data if isinstance(json_data, list)
            else json_data.get("transformaciones", [json_data])
        )
        with get_connection() as conn:
            for orden, transformacion in enumerate(transformaciones):
                tipo = transformacion.get("tipo", "")
                id_transformacion = TRANSFORMACION_TIPO_ID.get(tipo)
                if id_transformacion is None:
                    raise ValueError(
                        f"Transformación no soportada: '{tipo}'. "
                        f"Válidas: {list(TRANSFORMACION_TIPO_ID)}"
                    )
                conn.execute(
                    """INSERT INTO imagen_transformacion
                       (id_imagen, orden_aplicacion, parametros_json, id_transformacion)
                       VALUES (?, ?, ?, ?)""",
                    (id_imagen, orden, json.dumps(transformacion), id_transformacion),
                )

    # ------------------------------------------------- tarea_procesamiento
    # Nota: las tareas se crean directamente en estado "procesando" porque
    # RabbitMQ ya actúa como cola — el worker solo recibe la tarea cuando
    # está listo para procesarla. No existe un estado "pendiente" en tarea.

    def crear_tarea(self, id_lote: str, id_imagen: str, id_nodo: str) -> int:
        with get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO tarea_procesamiento
                   (id_lote, id_imagen, id_nodo, id_estado_tarea, intento, fecha_asignacion)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (id_lote, id_imagen, id_nodo,
                 ESTADO_TAREA_ID["procesando"], 1, datetime.now().isoformat()),
            )
            return cursor.lastrowid

    def actualizar_estado_tarea(self, id_tarea: int, estado: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE tarea_procesamiento SET id_estado_tarea = ? WHERE id_tarea = ?",
                (ESTADO_TAREA_ID[estado], id_tarea),
            )

    # ---------------------------------------------- resultado_procesamiento

    def insertar_resultado(self, id_tarea: int, ruta_salida: str | None, estado: str) -> None:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO resultado_procesamiento
                   (id_tarea, id_estado_resultado, ruta_salida, fecha_generacion)
                   VALUES (?, ?, ?, ?)""",
                (id_tarea, ESTADO_RESULTADO_ID[estado],
                 ruta_salida, datetime.now().isoformat()),
            )
