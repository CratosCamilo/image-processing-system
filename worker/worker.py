import json
import os
import shutil
import socket
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pika
import psycopg2
import psycopg2.extras

from image_processor import procesar_imagen

PROJECT_ROOT = Path(__file__).parent.parent
API_DIR = PROJECT_ROOT / "api"

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
QUEUE_NAME = "cola_imagenes"
WORKER_ID = f"{socket.gethostname()}-{str(uuid.uuid4())[:6]}"

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://admin:admin123@localhost:5432/image_processing",
)

N_WORKERS = int(os.getenv("N_WORKERS", str(os.cpu_count() or 4)))

executor = ThreadPoolExecutor(max_workers=N_WORKERS)

_pika_connection: pika.BlockingConnection | None = None

ESTADO_TAREA_ID     = {"pendiente": 1, "procesando": 2, "completado": 3, "error": 4}
ESTADO_RESULTADO_ID = {"pendiente": 1, "generado": 2, "error": 3}
TRANSFORMACION_TIPO_ID = {
    "resize": 1, "grayscale": 2, "rotate": 3,
    "crop": 4, "flip": 5, "blur": 6, "sharpen": 7,
    "brightness": 8, "contrast": 9, "watermark": 10, "convert": 11,
}


def get_connection() -> psycopg2.extensions.connection:
    return psycopg2.connect(DB_URL)


# --------------------------------------------------------- nodo

ESTADO_NODO_ID = {"activo": 1, "inactivo": 2}


def registrar_nodo(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO nodo_worker (id_nodo, hostname, capacidad, id_estado_nodo)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (id_nodo) DO UPDATE SET id_estado_nodo = EXCLUDED.id_estado_nodo""",
            (WORKER_ID, socket.gethostname(), N_WORKERS, ESTADO_NODO_ID["activo"]),
        )
    conn.commit()


def desregistrar_nodo(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE nodo_worker SET id_estado_nodo = %s WHERE id_nodo = %s",
            (ESTADO_NODO_ID["inactivo"], WORKER_ID),
        )
    conn.commit()


# --------------------------------------------------------- log

def _describir_transformacion(t: dict) -> str:
    tipo = t.get("tipo", "?")
    if tipo == "resize":
        return f"resize({t.get('width')}x{t.get('height')})"
    if tipo == "grayscale":
        return "grayscale"
    if tipo == "rotate":
        return f"rotate({t.get('angle')}deg)"
    if tipo == "crop":
        return f"crop({t.get('x')},{t.get('y')} -> {t.get('width')}x{t.get('height')})"
    if tipo == "flip":
        return f"flip({t.get('direction')})"
    if tipo == "blur":
        return f"blur(r={t.get('radius')})"
    if tipo == "sharpen":
        return f"sharpen(f={t.get('factor')})"
    if tipo == "brightness":
        return f"brightness(f={t.get('factor')})"
    if tipo == "contrast":
        return f"contrast(f={t.get('factor')})"
    if tipo == "watermark":
        texto = str(t.get("text", ""))[:20]
        return f"watermark('{texto}', {t.get('position')})"
    if tipo == "convert":
        return f"convert({t.get('format')})"
    return tipo


def registrar_log(
    conn: psycopg2.extensions.connection,
    id_imagen: str | None,
    id_nodo: str,
    tipo_evento: str,
    descripcion: str,
    id_lote: str | None = None,
    id_tarea: int | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO log_procesamiento
               (id_imagen, id_nodo, tipo_evento, fecha_evento, id_lote, id_tarea, descripcion)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (id_imagen, id_nodo, tipo_evento, datetime.now().isoformat(),
             id_lote, id_tarea, descripcion),
        )
    conn.commit()


# --------------------------------------------------------- imagen

def actualizar_estado_imagen(conn: psycopg2.extensions.connection, id_imagen: str, estado: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE imagen SET id_estado_tarea = %s WHERE id_imagen = %s",
            (ESTADO_TAREA_ID[estado], id_imagen),
        )
    conn.commit()


def obtener_transformaciones(conn: psycopg2.extensions.connection, id_imagen: str) -> list:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT parametros_json FROM imagen_transformacion WHERE id_imagen = %s ORDER BY orden_aplicacion",
            (id_imagen,),
        )
        return [json.loads(row["parametros_json"]) for row in cur.fetchall()]


# --------------------------------------------------------- tarea

def crear_tarea_procesamiento(
    conn: psycopg2.extensions.connection, id_lote: str, id_imagen: str, id_nodo: str
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO tarea_procesamiento
               (id_lote, id_imagen, id_nodo, id_estado_tarea, intento, fecha_asignacion)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id_tarea""",
            (id_lote, id_imagen, id_nodo, ESTADO_TAREA_ID["procesando"], 1,
             datetime.now().isoformat()),
        )
        id_tarea = cur.fetchone()[0]
    conn.commit()
    return id_tarea


def actualizar_estado_tarea(conn: psycopg2.extensions.connection, id_tarea: int, estado: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE tarea_procesamiento SET id_estado_tarea = %s WHERE id_tarea = %s",
            (ESTADO_TAREA_ID[estado], id_tarea),
        )
    conn.commit()


# --------------------------------------------------------- resultado

def insertar_resultado(
    conn: psycopg2.extensions.connection, id_tarea: int, ruta_salida: str | None, estado: str
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO resultado_procesamiento
               (id_tarea, id_estado_resultado, ruta_salida, fecha_generacion)
               VALUES (%s, %s, %s, %s)""",
            (id_tarea, ESTADO_RESULTADO_ID[estado], ruta_salida, datetime.now().isoformat()),
        )
    conn.commit()


# --------------------------------------------------------- lote

def actualizar_estado_lote_si_completo(conn: psycopg2.extensions.connection, id_lote: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM imagen WHERE id_lote = %s AND id_estado_tarea != %s",
            (id_lote, ESTADO_TAREA_ID["completado"]),
        )
        pendientes = cur.fetchone()[0]

    if pendientes == 0:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE lote_procesamiento
                   SET id_estado_lote = %s
                   WHERE id_lote = %s AND id_estado_lote != %s""",
                (ESTADO_TAREA_ID["completado"], id_lote, ESTADO_TAREA_ID["completado"]),
            )
            actualizado = cur.rowcount > 0
        conn.commit()
        if actualizado:
            print(f"  -> Lote {id_lote[:8]}... completado")
            return True
    return False


def limpiar_input_lote(id_lote: str) -> None:
    input_dir = API_DIR / "storage" / "input" / id_lote
    if input_dir.exists():
        shutil.rmtree(input_dir)
        print(f"  -> Input limpiado: {id_lote[:8]}...")


# --------------------------------------------------------- procesamiento (ejecuta en hilo del pool)

def _procesar_tarea(ch, method, body: bytes) -> None:
    conn = get_connection()
    id_imagen = None
    id_tarea = None
    id_lote = None
    try:
        data = json.loads(body)
        id_imagen = data["id_imagen"]
        ruta_absoluta = str(PROJECT_ROOT / "api" / data["ruta"])
        id_lote = data["id_lote"]

        print(f"[Worker:{WORKER_ID}] Tarea recibida: {id_imagen[:8]}...")

        actualizar_estado_imagen(conn, id_imagen, "procesando")
        id_tarea = crear_tarea_procesamiento(conn, id_lote, id_imagen, WORKER_ID)

        transformaciones = obtener_transformaciones(conn, id_imagen)

        for t in transformaciones:
            tipo = t.get("tipo", "")
            if tipo not in TRANSFORMACION_TIPO_ID:
                raise ValueError(f"Transformacion no soportada: '{tipo}'")

        descripcion_pasos = " -> ".join(_describir_transformacion(t) for t in transformaciones)
        registrar_log(
            conn, id_imagen, WORKER_ID, "procesando",
            f"Transformaciones: {descripcion_pasos}",
            id_lote=id_lote, id_tarea=id_tarea,
        )

        ruta_resultado = procesar_imagen(ruta_absoluta, transformaciones, id_lote)

        actualizar_estado_imagen(conn, id_imagen, "completado")
        actualizar_estado_tarea(conn, id_tarea, "completado")
        insertar_resultado(conn, id_tarea, ruta_resultado, "generado")
        registrar_log(
            conn, id_imagen, WORKER_ID, "completado",
            "Procesamiento completado correctamente",
            id_lote=id_lote, id_tarea=id_tarea,
        )
        print(f"[Worker:{WORKER_ID}] Completado: {ruta_resultado}")

        lote_completado = actualizar_estado_lote_si_completo(conn, id_lote)
        if lote_completado:
            limpiar_input_lote(id_lote)

        delivery_tag = method.delivery_tag
        _pika_connection.add_callback_threadsafe(
            lambda: ch.basic_ack(delivery_tag=delivery_tag)
        )

    except Exception as e:
        print(f"[Worker:{WORKER_ID}] Error: {e}")
        traceback.print_exc()
        try:
            conn.rollback()
        except Exception:
            pass
        if id_imagen:
            try:
                actualizar_estado_imagen(conn, id_imagen, "error")
                registrar_log(
                    conn, id_imagen, WORKER_ID, "error",
                    f"Error: {str(e)}",
                    id_lote=id_lote, id_tarea=id_tarea,
                )
            except Exception:
                pass
        if id_tarea:
            try:
                actualizar_estado_tarea(conn, id_tarea, "error")
                insertar_resultado(conn, id_tarea, None, "error")
            except Exception:
                pass

        delivery_tag = method.delivery_tag
        _pika_connection.add_callback_threadsafe(
            lambda: ch.basic_nack(delivery_tag=delivery_tag, requeue=False)
        )
    finally:
        conn.close()


# --------------------------------------------------------- consumer

def on_message(ch, method, _properties, body: bytes) -> None:
    executor.submit(_procesar_tarea, ch, method, body)


if __name__ == "__main__":
    conn = get_connection()
    registrar_nodo(conn)
    conn.close()

    _pika_connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    channel = _pika_connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=N_WORKERS)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)

    print(f"[Worker:{WORKER_ID}] Iniciando con {N_WORKERS} hilos. Ctrl+C para detener.")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print(f"\n[Worker:{WORKER_ID}] Detenido.")
        channel.stop_consuming()
    finally:
        executor.shutdown(wait=True)
        _pika_connection.close()
        conn = get_connection()
        desregistrar_nodo(conn)
        conn.close()
        print(f"[Worker:{WORKER_ID}] Nodo marcado como inactivo en BD.")
