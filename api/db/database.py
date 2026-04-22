import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

# En desarrollo local apunta a Docker; en deploy se sobreescribe con la IP de la VM de BD.
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://admin:admin123@localhost:5432/image_processing",
)

# Tablas de catalogo primero (referenciadas por FK en tablas principales).
# SERIAL = entero autoincremental. TIMESTAMP reemplaza DATETIME de SQLite.
_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS usuario (
        id_usuario     SERIAL PRIMARY KEY,
        correo         TEXT NOT NULL UNIQUE,
        password_hash  TEXT NOT NULL,
        fecha_creacion TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS estado_lote (
        id_estado_lote INTEGER PRIMARY KEY,
        nombre         TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS estado_tarea (
        id_estado_tarea INTEGER PRIMARY KEY,
        nombre          TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS estado_resultado (
        id_estado_resultado INTEGER PRIMARY KEY,
        nombre              TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS estado_nodo (
        id_estado_nodo INTEGER PRIMARY KEY,
        nombre         TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transformacion (
        id_transformacion SERIAL PRIMARY KEY,
        tipo              TEXT NOT NULL UNIQUE,
        descripcion       TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lote_procesamiento (
        id_lote        TEXT PRIMARY KEY,
        fecha_creacion TIMESTAMP,
        id_estado_lote INTEGER REFERENCES estado_lote(id_estado_lote),
        id_usuario     INTEGER REFERENCES usuario(id_usuario)
    )
    """,
    # Migración para BDs existentes que no tienen la columna id_usuario
    "ALTER TABLE lote_procesamiento ADD COLUMN IF NOT EXISTS id_usuario INTEGER REFERENCES usuario(id_usuario)",
    """
    CREATE TABLE IF NOT EXISTS imagen (
        id_imagen       TEXT PRIMARY KEY,
        id_lote         TEXT,
        nombre_archivo  TEXT,
        ruta_origen     TEXT,
        id_estado_tarea INTEGER REFERENCES estado_tarea(id_estado_tarea),
        formato         TEXT,
        resolucion      TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS imagen_transformacion (
        id_imagen_transformacion SERIAL PRIMARY KEY,
        id_imagen                TEXT,
        orden_aplicacion         INTEGER,
        parametros_json          TEXT,
        id_transformacion        INTEGER REFERENCES transformacion(id_transformacion)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nodo_worker (
        id_nodo        TEXT PRIMARY KEY,
        hostname       TEXT,
        capacidad      INTEGER,
        id_estado_nodo INTEGER DEFAULT 1 REFERENCES estado_nodo(id_estado_nodo)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS log_procesamiento (
        id_log       SERIAL PRIMARY KEY,
        id_imagen    TEXT,
        id_nodo      TEXT,
        tipo_evento  TEXT,
        fecha_evento TIMESTAMP,
        id_lote      TEXT,
        id_tarea     INTEGER,
        descripcion  TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tarea_procesamiento (
        id_tarea         SERIAL PRIMARY KEY,
        id_lote          TEXT REFERENCES lote_procesamiento(id_lote),
        id_imagen        TEXT REFERENCES imagen(id_imagen),
        id_nodo          TEXT REFERENCES nodo_worker(id_nodo),
        id_estado_tarea  INTEGER REFERENCES estado_tarea(id_estado_tarea),
        intento          INTEGER DEFAULT 1,
        fecha_asignacion TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resultado_procesamiento (
        id_resultado        SERIAL PRIMARY KEY,
        id_tarea            INTEGER REFERENCES tarea_procesamiento(id_tarea),
        id_estado_resultado INTEGER REFERENCES estado_resultado(id_estado_resultado),
        ruta_salida         TEXT,
        fecha_generacion    TIMESTAMP
    )
    """,
]

# ON CONFLICT DO NOTHING reemplaza INSERT OR IGNORE de SQLite.
_SEED_STATEMENTS = [
    "INSERT INTO estado_lote VALUES (1, 'pendiente')   ON CONFLICT DO NOTHING",
    "INSERT INTO estado_lote VALUES (2, 'procesando')  ON CONFLICT DO NOTHING",
    "INSERT INTO estado_lote VALUES (3, 'completado')  ON CONFLICT DO NOTHING",
    "INSERT INTO estado_lote VALUES (4, 'error')       ON CONFLICT DO NOTHING",

    "INSERT INTO estado_tarea VALUES (1, 'pendiente')  ON CONFLICT DO NOTHING",
    "INSERT INTO estado_tarea VALUES (2, 'procesando') ON CONFLICT DO NOTHING",
    "INSERT INTO estado_tarea VALUES (3, 'completado') ON CONFLICT DO NOTHING",
    "INSERT INTO estado_tarea VALUES (4, 'error')      ON CONFLICT DO NOTHING",

    "INSERT INTO estado_resultado VALUES (1, 'pendiente') ON CONFLICT DO NOTHING",
    "INSERT INTO estado_resultado VALUES (2, 'generado')  ON CONFLICT DO NOTHING",
    "INSERT INTO estado_resultado VALUES (3, 'error')     ON CONFLICT DO NOTHING",

    "INSERT INTO estado_nodo VALUES (1, 'activo')   ON CONFLICT DO NOTHING",
    "INSERT INTO estado_nodo VALUES (2, 'inactivo') ON CONFLICT DO NOTHING",

    "INSERT INTO transformacion (id_transformacion, tipo, descripcion) VALUES (1,  'resize',     'Redimensionar imagen al ancho y alto indicados')  ON CONFLICT DO NOTHING",
    "INSERT INTO transformacion (id_transformacion, tipo, descripcion) VALUES (2,  'grayscale',  'Convertir imagen a escala de grises')              ON CONFLICT DO NOTHING",
    "INSERT INTO transformacion (id_transformacion, tipo, descripcion) VALUES (3,  'rotate',     'Rotar imagen N grados')                            ON CONFLICT DO NOTHING",
    "INSERT INTO transformacion (id_transformacion, tipo, descripcion) VALUES (4,  'crop',       'Recortar region rectangular de la imagen')         ON CONFLICT DO NOTHING",
    "INSERT INTO transformacion (id_transformacion, tipo, descripcion) VALUES (5,  'flip',       'Reflejar imagen horizontal o verticalmente')       ON CONFLICT DO NOTHING",
    "INSERT INTO transformacion (id_transformacion, tipo, descripcion) VALUES (6,  'blur',       'Aplicar desenfoque gaussiano')                     ON CONFLICT DO NOTHING",
    "INSERT INTO transformacion (id_transformacion, tipo, descripcion) VALUES (7,  'sharpen',    'Aumentar nitidez de la imagen')                    ON CONFLICT DO NOTHING",
    "INSERT INTO transformacion (id_transformacion, tipo, descripcion) VALUES (8,  'brightness', 'Ajustar brillo de la imagen')                      ON CONFLICT DO NOTHING",
    "INSERT INTO transformacion (id_transformacion, tipo, descripcion) VALUES (9,  'contrast',   'Ajustar contraste de la imagen')                   ON CONFLICT DO NOTHING",
    "INSERT INTO transformacion (id_transformacion, tipo, descripcion) VALUES (10, 'watermark',  'Anadir texto como marca de agua')                  ON CONFLICT DO NOTHING",
    "INSERT INTO transformacion (id_transformacion, tipo, descripcion) VALUES (11, 'convert',    'Convertir formato de salida (jpeg, png, tiff)')    ON CONFLICT DO NOTHING",
]


def get_connection() -> psycopg2.extensions.connection:
    """
    Retorna una conexion psycopg2 sin cerrar. El llamador es responsable de
    hacer commit/rollback y cerrar. Usado por el worker, que gestiona el ciclo
    de vida de la conexion manualmente dentro de cada hilo.
    """
    return psycopg2.connect(DB_URL)


@contextmanager
def get_cursor():
    """
    Context manager para la API. Abre conexion, entrega un RealDictCursor
    (las filas se acceden como dicts: row["campo"]), hace commit al salir o
    rollback si hay excepcion, y cierra la conexion en cualquier caso.
    """
    conn = psycopg2.connect(DB_URL)
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
    finally:
        conn.close()


def _seed_usuario(conn) -> None:
    """Inserta el usuario de prueba si no existe. Se llama dentro de init_db()."""
    from passlib.context import CryptContext  # import local para no romper si passlib no está instalado aún
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd.hash("1234")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO usuario (correo, password_hash) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            ("admin@test.com", hashed),
        )


def init_db() -> None:
    conn = psycopg2.connect(DB_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                for stmt in _SCHEMA_STATEMENTS:
                    cur.execute(stmt)
                for stmt in _SEED_STATEMENTS:
                    cur.execute(stmt)
            _seed_usuario(conn)
    finally:
        conn.close()


init_db()
