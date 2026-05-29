import json
from datetime import datetime

from db.database import get_cursor

# IDs de estado — deben coincidir con el seed de database.py
ESTADO_LOTE_ID      = {"pendiente": 1, "procesando": 2, "completado": 3, "error": 4}
ESTADO_TAREA_ID     = {"pendiente": 1, "procesando": 2, "completado": 3, "error": 4}
ESTADO_RESULTADO_ID = {"pendiente": 1, "generado": 2, "error": 3}
TRANSFORMACION_TIPO_ID = {
    "resize": 1, "grayscale": 2, "rotate": 3,
    "crop": 4, "flip": 5, "blur": 6, "sharpen": 7,
    "brightness": 8, "contrast": 9, "watermark": 10, "convert": 11,
}

# ------------------------------------------------- validadores de parámetros

_POSICIONES_WATERMARK = {"top-left", "top-right", "bottom-left", "bottom-right", "center"}


def _req_int(p: dict, key: str) -> None:
    if key not in p:
        raise ValueError(f"Falta parámetro requerido: '{key}'")
    if not isinstance(p[key], int):
        raise ValueError(f"El parámetro '{key}' debe ser un entero, recibido: {type(p[key]).__name__}")


def _req_float(p: dict, key: str) -> None:
    if key not in p:
        raise ValueError(f"Falta parámetro requerido: '{key}'")
    if not isinstance(p[key], (int, float)):
        raise ValueError(f"El parámetro '{key}' debe ser numérico, recibido: {type(p[key]).__name__}")


def _req_float_min(p: dict, key: str, min_val: float) -> None:
    _req_float(p, key)
    if p[key] < min_val:
        raise ValueError(f"El parámetro '{key}' debe ser ≥ {min_val}, recibido: {p[key]}")


def _req_float_range(p: dict, key: str, lo: float, hi: float) -> None:
    _req_float(p, key)
    if not (lo <= p[key] <= hi):
        raise ValueError(f"El parámetro '{key}' debe estar en [{lo}, {hi}], recibido: {p[key]}")


def _req_str(p: dict, key: str) -> None:
    if key not in p:
        raise ValueError(f"Falta parámetro requerido: '{key}'")
    if not isinstance(p[key], str) or not p[key].strip():
        raise ValueError(f"El parámetro '{key}' debe ser un string no vacío")


def _req_enum(p: dict, key: str, allowed: set) -> None:
    if key not in p:
        raise ValueError(f"Falta parámetro requerido: '{key}'")
    if p[key] not in allowed:
        raise ValueError(f"El parámetro '{key}' debe ser uno de {sorted(allowed)}, recibido: '{p[key]}'")


_VALIDADORES = {
    "resize":     lambda p: (_req_int(p, "width"),   _req_int(p, "height")),
    "grayscale":  lambda p: None,
    "rotate":     lambda p: _req_float(p, "angle"),
    "crop":       lambda p: (_req_int(p, "x"),       _req_int(p, "y"),
                             _req_int(p, "width"),   _req_int(p, "height")),
    "flip":       lambda p: _req_enum(p, "direction", {"horizontal", "vertical"}),
    "blur":       lambda p: _req_float_min(p, "radius", 0.1),
    "sharpen":    lambda p: _req_float_min(p, "factor", 1.0),
    "brightness": lambda p: _req_float_min(p, "factor", 0.1),
    "contrast":   lambda p: _req_float_min(p, "factor", 0.1),
    "watermark":  lambda p: (_req_str(p, "text"),
                             _req_enum(p, "position", _POSICIONES_WATERMARK),
                             _req_float_range(p, "opacity", 0.0, 1.0)),
    "convert":    lambda p: _req_enum(p, "format", {"jpeg", "png", "tiff"}),
}


class PersistenceService:

    # ------------------------------------------------------------------ lote

    def crear_lote(self, id_lote: str, id_usuario: int) -> None:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO lote_procesamiento
                   (id_lote, fecha_creacion, id_estado_lote, id_usuario)
                   VALUES (%s, %s, %s, %s)""",
                (id_lote, datetime.now().isoformat(), ESTADO_LOTE_ID["procesando"], id_usuario),
            )

    def verificar_propietario_lote(self, id_lote: str, id_usuario: int) -> bool:
        with get_cursor() as cur:
            cur.execute(
                "SELECT 1 FROM lote_procesamiento WHERE id_lote = %s AND id_usuario = %s",
                (id_lote, id_usuario),
            )
            return cur.fetchone() is not None

    def obtener_lote(self, id_lote: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute(
                """SELECT lp.id_lote, lp.fecha_creacion, lp.id_estado_lote,
                          el.nombre AS estado
                   FROM lote_procesamiento lp
                   LEFT JOIN estado_lote el ON lp.id_estado_lote = el.id_estado_lote
                   WHERE lp.id_lote = %s""",
                (id_lote,),
            )
            row = cur.fetchone()
            # RealDictCursor ya devuelve un dict; se castea para garantizar tipo plain dict
            return dict(row) if row else None

    def obtener_estadisticas_lote(self, id_lote: str) -> dict:
        with get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM imagen WHERE id_lote = %s", (id_lote,)
            )
            # COUNT(*) con RealDictCursor devuelve {"count": N}
            total = cur.fetchone()["count"]

            cur.execute(
                "SELECT COUNT(*) FROM tarea_procesamiento WHERE id_lote = %s", (id_lote,)
            )
            tareas_existentes = cur.fetchone()["count"]

            if tareas_existentes > 0:
                cur.execute(
                    "SELECT COUNT(*) FROM tarea_procesamiento WHERE id_lote = %s AND id_estado_tarea = %s",
                    (id_lote, ESTADO_TAREA_ID["completado"]),
                )
            else:
                cur.execute(
                    "SELECT COUNT(*) FROM imagen WHERE id_lote = %s AND id_estado_tarea = %s",
                    (id_lote, ESTADO_TAREA_ID["completado"]),
                )
            completadas = cur.fetchone()["count"]
            return {"total": total, "completadas": completadas}

    # --------------------------------------------------------------- imagen

    def guardar_imagen(
        self, id_lote: str, id_imagen: str, nombre: str, ruta: str,
        formato: str, resolucion: str
    ) -> None:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO imagen
                   (id_imagen, id_lote, nombre_archivo, ruta_origen, id_estado_tarea, formato, resolucion)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (id_imagen, id_lote, nombre, ruta, ESTADO_TAREA_ID["pendiente"],
                 formato, resolucion),
            )

    def actualizar_estado_imagen(self, id_imagen: str, estado: str) -> None:
        with get_cursor() as cur:
            cur.execute(
                "UPDATE imagen SET id_estado_tarea = %s WHERE id_imagen = %s",
                (ESTADO_TAREA_ID[estado], id_imagen),
            )

    # --------------------------------------------------- transformaciones

    def guardar_transformaciones(self, id_imagen: str, json_data: dict) -> None:
        transformaciones = (
            json_data if isinstance(json_data, list)
            else json_data.get("transformaciones", [json_data])
        )
        with get_cursor() as cur:
            for orden, transformacion in enumerate(transformaciones):
                tipo = transformacion.get("tipo", "")
                id_transformacion = TRANSFORMACION_TIPO_ID.get(tipo)
                if id_transformacion is None:
                    raise ValueError(
                        f"Transformación no soportada: '{tipo}'. "
                        f"Válidas: {list(TRANSFORMACION_TIPO_ID)}"
                    )
                try:
                    _VALIDADORES[tipo](transformacion)
                except ValueError as e:
                    raise ValueError(f"Error en transformación '{tipo}' (posición {orden}): {e}")

                cur.execute(
                    """INSERT INTO imagen_transformacion
                       (id_imagen, orden_aplicacion, parametros_json, id_transformacion)
                       VALUES (%s, %s, %s, %s)""",
                    (id_imagen, orden, json.dumps(transformacion), id_transformacion),
                )

    # ------------------------------------------------- tarea_procesamiento

    def crear_tarea(self, id_lote: str, id_imagen: str, id_nodo: str) -> int:
        with get_cursor() as cur:
            # RETURNING devuelve el ID generado por SERIAL directamente
            cur.execute(
                """INSERT INTO tarea_procesamiento
                   (id_lote, id_imagen, id_nodo, id_estado_tarea, intento, fecha_asignacion)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING id_tarea""",
                (id_lote, id_imagen, id_nodo,
                 ESTADO_TAREA_ID["procesando"], 1, datetime.now().isoformat()),
            )
            return cur.fetchone()["id_tarea"]

    def actualizar_estado_tarea(self, id_tarea: int, estado: str) -> None:
        with get_cursor() as cur:
            cur.execute(
                "UPDATE tarea_procesamiento SET id_estado_tarea = %s WHERE id_tarea = %s",
                (ESTADO_TAREA_ID[estado], id_tarea),
            )

    # ---------------------------------------------- resultado_procesamiento

    # ----------------------------------------------------------- métricas

    def obtener_metricas_sistema(self) -> dict:
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM lote_procesamiento")
            total_lotes = cur.fetchone()["count"]

            cur.execute("""
                SELECT el.nombre, COUNT(*) AS cantidad
                FROM lote_procesamiento lp
                JOIN estado_lote el ON lp.id_estado_lote = el.id_estado_lote
                GROUP BY el.nombre
            """)
            lotes_por_estado = {r["nombre"]: r["cantidad"] for r in cur.fetchall()}

            cur.execute("SELECT COUNT(*) FROM imagen")
            total_imagenes = cur.fetchone()["count"]

            cur.execute("""
                SELECT et.nombre, COUNT(*) AS cantidad
                FROM imagen i
                JOIN estado_tarea et ON i.id_estado_tarea = et.id_estado_tarea
                GROUP BY et.nombre
            """)
            imagenes_por_estado = {r["nombre"]: r["cantidad"] for r in cur.fetchall()}

            cur.execute("""
                SELECT id_nodo, hostname, capacidad
                FROM nodo_worker WHERE id_estado_nodo = 1
            """)
            workers = [dict(r) for r in cur.fetchall()]

        return {
            "total_lotes": total_lotes,
            "lotes_por_estado": lotes_por_estado,
            "total_imagenes": total_imagenes,
            "imagenes_por_estado": imagenes_por_estado,
            "workers_activos": workers,
        }

    def obtener_metricas_lote(self, id_lote: str) -> dict:
        with get_cursor() as cur:
            cur.execute("""
                SELECT
                    i.nombre_archivo, i.formato, i.resolucion,
                    et.nombre AS estado, t.id_nodo,
                    EXTRACT(EPOCH FROM (r.fecha_generacion - t.fecha_asignacion))
                        AS tiempo_segundos
                FROM imagen i
                JOIN estado_tarea et ON i.id_estado_tarea = et.id_estado_tarea
                LEFT JOIN tarea_procesamiento t ON t.id_imagen = i.id_imagen
                LEFT JOIN resultado_procesamiento r ON r.id_tarea = t.id_tarea
                WHERE i.id_lote = %s
                ORDER BY i.nombre_archivo
            """, (id_lote,))
            imagenes = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT i.nombre_archivo, COUNT(it.id_imagen_transformacion) AS num
                FROM imagen i
                LEFT JOIN imagen_transformacion it ON it.id_imagen = i.id_imagen
                WHERE i.id_lote = %s
                GROUP BY i.id_imagen, i.nombre_archivo
            """, (id_lote,))
            trans_counts = {r["nombre_archivo"]: r["num"] for r in cur.fetchall()}

            cur.execute("""
                SELECT MIN(t.fecha_asignacion) AS inicio, MAX(r.fecha_generacion) AS fin
                FROM tarea_procesamiento t
                JOIN resultado_procesamiento r ON r.id_tarea = t.id_tarea
                WHERE t.id_lote = %s
            """, (id_lote,))
            tiempos = dict(cur.fetchone())

        return {"imagenes": imagenes, "trans_counts": trans_counts, "tiempos": tiempos}

    def insertar_resultado(self, id_tarea: int, ruta_salida: str | None, estado: str) -> None:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO resultado_procesamiento
                   (id_tarea, id_estado_resultado, ruta_salida, fecha_generacion)
                   VALUES (%s, %s, %s, %s)""",
                (id_tarea, ESTADO_RESULTADO_ID[estado],
                 ruta_salida, datetime.now().isoformat()),
            )
