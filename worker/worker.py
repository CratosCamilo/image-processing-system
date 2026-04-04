import json
import shutil
import socket
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import pika

from image_processor import procesar_imagen

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "database.db"
API_DIR = PROJECT_ROOT / "api"

RABBITMQ_HOST = "localhost"
QUEUE_NAME = "cola_imagenes"
WORKER_ID = f"{socket.gethostname()}-{str(uuid.uuid4())[:6]}"

# IDs de estado (deben coincidir con seed de database.py)
ESTADO_TAREA_ID     = {"pendiente": 1, "procesando": 2, "completado": 3, "error": 4}
ESTADO_RESULTADO_ID = {"pendiente": 1, "generado": 2, "error": 3}
TRANSFORMACION_TIPO_ID = {"resize": 1, "grayscale": 2, "rotate": 3}


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------- nodo

def registrar_nodo(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO nodo_worker (id_nodo, hostname, capacidad, id_estado_nodo) VALUES (?, ?, ?, ?)",
        (WORKER_ID, socket.gethostname(), 1, 1),
    )
    conn.commit()


# --------------------------------------------------------- log

def registrar_log(
    conn: sqlite3.Connection,
    id_imagen: str | None,
    id_nodo: str,
    tipo_evento: str,
    descripcion: str,
    id_lote: str | None = None,
    id_tarea: int | None = None,
) -> None:
    conn.execute(
        """INSERT INTO log_procesamiento
           (id_imagen, id_nodo, tipo_evento, fecha_evento, id_lote, id_tarea, descripcion)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (id_imagen, id_nodo, tipo_evento, datetime.now().isoformat(),
         id_lote, id_tarea, descripcion),
    )
    conn.commit()


# --------------------------------------------------------- imagen

def actualizar_estado_imagen(conn: sqlite3.Connection, id_imagen: str, estado: str) -> None:
    conn.execute(
        "UPDATE imagen SET id_estado_tarea = ? WHERE id_imagen = ?",
        (ESTADO_TAREA_ID[estado], id_imagen),
    )
    conn.commit()


def obtener_transformaciones(conn: sqlite3.Connection, id_imagen: str) -> list:
    cursor = conn.execute(
        "SELECT parametros_json FROM imagen_transformacion WHERE id_imagen = ? ORDER BY orden_aplicacion",
        (id_imagen,),
    )
    return [json.loads(row["parametros_json"]) for row in cursor.fetchall()]


# --------------------------------------------------------- tarea

def crear_tarea_procesamiento(
    conn: sqlite3.Connection, id_lote: str, id_imagen: str, id_nodo: str
) -> int:
    cursor = conn.execute(
        """INSERT INTO tarea_procesamiento
           (id_lote, id_imagen, id_nodo, id_estado_tarea, intento, fecha_asignacion)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (id_lote, id_imagen, id_nodo, ESTADO_TAREA_ID["procesando"], 1,
         datetime.now().isoformat()),
    )
    conn.commit()
    return cursor.lastrowid


def actualizar_estado_tarea(conn: sqlite3.Connection, id_tarea: int, estado: str) -> None:
    conn.execute(
        "UPDATE tarea_procesamiento SET id_estado_tarea = ? WHERE id_tarea = ?",
        (ESTADO_TAREA_ID[estado], id_tarea),
    )
    conn.commit()


# --------------------------------------------------------- resultado

def insertar_resultado(
    conn: sqlite3.Connection, id_tarea: int, ruta_salida: str | None, estado: str
) -> None:
    conn.execute(
        """INSERT INTO resultado_procesamiento
           (id_tarea, id_estado_resultado, ruta_salida, fecha_generacion)
           VALUES (?, ?, ?, ?)""",
        (id_tarea, ESTADO_RESULTADO_ID[estado], ruta_salida, datetime.now().isoformat()),
    )
    conn.commit()


# --------------------------------------------------------- lote

def actualizar_estado_lote_si_completo(conn: sqlite3.Connection, id_lote: str) -> bool:
    # imagen tiene todas las filas desde el inicio → fuente de verdad para "pendientes"
    pendientes = conn.execute(
        "SELECT COUNT(*) FROM imagen WHERE id_lote = ? AND id_estado_tarea != ?",
        (id_lote, ESTADO_TAREA_ID["completado"]),
    ).fetchone()[0]
    if pendientes == 0:
        cursor = conn.execute(
            """UPDATE lote_procesamiento
               SET id_estado_lote = ?
               WHERE id_lote = ? AND id_estado_lote != ?""",
            (ESTADO_TAREA_ID["completado"], id_lote, ESTADO_TAREA_ID["completado"]),
        )
        conn.commit()
        if cursor.rowcount > 0:
            print(f"  → Lote {id_lote[:8]}... completado")
            return True
    return False


def limpiar_input_lote(id_lote: str) -> None:
    input_dir = API_DIR / "storage" / "input" / id_lote
    if input_dir.exists():
        shutil.rmtree(input_dir)
        print(f"  → Input limpiado: {id_lote[:8]}...")


# --------------------------------------------------------- consumer

def on_message(ch, method, _properties, body):
    db = get_connection()
    id_imagen = None
    id_tarea = None
    id_lote = None
    try:
        data = json.loads(body)
        id_imagen = data["id_imagen"]
        ruta_absoluta = str(PROJECT_ROOT / "api" / data["ruta"])
        id_lote = data["id_lote"]

        print(f"[Worker:{WORKER_ID}] Tarea recibida: {id_imagen[:8]}...")

        actualizar_estado_imagen(db, id_imagen, "procesando")
        id_tarea = crear_tarea_procesamiento(db, id_lote, id_imagen, WORKER_ID)

        # Obtener transformaciones antes del log para incluirlas en la descripción
        transformaciones = obtener_transformaciones(db, id_imagen)

        tipos = [t.get("tipo", "") for t in transformaciones]
        for tipo in tipos:
            if tipo not in TRANSFORMACION_TIPO_ID:
                raise ValueError(f"Transformación no soportada: {tipo}")

        registrar_log(
            db, id_imagen, WORKER_ID, "procesando",
            f"Transformaciones: {', '.join(tipos)}",
            id_lote=id_lote, id_tarea=id_tarea,
        )

        ruta_resultado = procesar_imagen(ruta_absoluta, transformaciones, id_lote)

        actualizar_estado_imagen(db, id_imagen, "completado")
        actualizar_estado_tarea(db, id_tarea, "completado")
        insertar_resultado(db, id_tarea, ruta_resultado, "generado")
        registrar_log(
            db, id_imagen, WORKER_ID, "completado",
            "Procesamiento completado correctamente",
            id_lote=id_lote, id_tarea=id_tarea,
        )
        print(f"[Worker:{WORKER_ID}] Completado: {ruta_resultado}")

        lote_completado = actualizar_estado_lote_si_completo(db, id_lote)
        if lote_completado:
            limpiar_input_lote(id_lote)

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"[Worker:{WORKER_ID}] Error: {e}")
        if id_imagen:
            actualizar_estado_imagen(db, id_imagen, "error")
            registrar_log(
                db, id_imagen, WORKER_ID, "error",
                f"Error: {str(e)}",
                id_lote=id_lote, id_tarea=id_tarea,
            )
        if id_tarea:
            actualizar_estado_tarea(db, id_tarea, "error")
            insertar_resultado(db, id_tarea, None, "error")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    finally:
        db.close()


if __name__ == "__main__":
    db = get_connection()
    registrar_nodo(db)
    db.close()

    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)

    print(f"[Worker:{WORKER_ID}] Esperando tareas. Ctrl+C para detener.")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print(f"\n[Worker:{WORKER_ID}] Detenido.")
        channel.stop_consuming()
    connection.close()
