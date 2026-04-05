import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "database.db"

# Tablas de catálogo primero (referenciadas por FK en tablas principales)
SCHEMA = """
CREATE TABLE IF NOT EXISTS estado_lote (
    id_estado_lote INTEGER PRIMARY KEY,
    nombre         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS estado_tarea (
    id_estado_tarea INTEGER PRIMARY KEY,
    nombre          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS estado_resultado (
    id_estado_resultado INTEGER PRIMARY KEY,
    nombre              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS estado_nodo (
    id_estado_nodo INTEGER PRIMARY KEY,
    nombre         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transformacion (
    id_transformacion INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo              TEXT NOT NULL UNIQUE,
    descripcion       TEXT
);

CREATE TABLE IF NOT EXISTS lote_procesamiento (
    id_lote        TEXT PRIMARY KEY,
    fecha_creacion DATETIME,
    id_estado_lote INTEGER REFERENCES estado_lote(id_estado_lote)
);

CREATE TABLE IF NOT EXISTS imagen (
    id_imagen       TEXT PRIMARY KEY,
    id_lote         TEXT,
    nombre_archivo  TEXT,
    ruta_origen     TEXT,
    id_estado_tarea INTEGER REFERENCES estado_tarea(id_estado_tarea),
    formato         TEXT,
    resolucion      TEXT
);

CREATE TABLE IF NOT EXISTS imagen_transformacion (
    id_imagen_transformacion INTEGER PRIMARY KEY AUTOINCREMENT,
    id_imagen                TEXT,
    orden_aplicacion         INTEGER,
    parametros_json          TEXT,
    id_transformacion        INTEGER REFERENCES transformacion(id_transformacion)
);

CREATE TABLE IF NOT EXISTS nodo_worker (
    id_nodo        TEXT PRIMARY KEY,
    hostname       TEXT,
    capacidad      INTEGER,
    id_estado_nodo INTEGER DEFAULT 1 REFERENCES estado_nodo(id_estado_nodo)
);

CREATE TABLE IF NOT EXISTS log_procesamiento (
    id_log       INTEGER PRIMARY KEY AUTOINCREMENT,
    id_imagen    TEXT,
    id_nodo      TEXT,
    tipo_evento  TEXT,
    fecha_evento DATETIME,
    id_lote      TEXT,
    id_tarea     INTEGER,
    descripcion  TEXT
);

CREATE TABLE IF NOT EXISTS tarea_procesamiento (
    id_tarea         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_lote          TEXT REFERENCES lote_procesamiento(id_lote),
    id_imagen        TEXT REFERENCES imagen(id_imagen),
    id_nodo          TEXT REFERENCES nodo_worker(id_nodo),
    id_estado_tarea  INTEGER REFERENCES estado_tarea(id_estado_tarea),
    intento          INTEGER DEFAULT 1,
    fecha_asignacion DATETIME
);

CREATE TABLE IF NOT EXISTS resultado_procesamiento (
    id_resultado        INTEGER PRIMARY KEY AUTOINCREMENT,
    id_tarea            INTEGER REFERENCES tarea_procesamiento(id_tarea),
    id_estado_resultado INTEGER REFERENCES estado_resultado(id_estado_resultado),
    ruta_salida         TEXT,
    fecha_generacion    DATETIME
);
"""

SEED = """
INSERT OR IGNORE INTO estado_lote VALUES (1, 'pendiente');
INSERT OR IGNORE INTO estado_lote VALUES (2, 'procesando');
INSERT OR IGNORE INTO estado_lote VALUES (3, 'completado');
INSERT OR IGNORE INTO estado_lote VALUES (4, 'error');

INSERT OR IGNORE INTO estado_tarea VALUES (1, 'pendiente');
INSERT OR IGNORE INTO estado_tarea VALUES (2, 'procesando');
INSERT OR IGNORE INTO estado_tarea VALUES (3, 'completado');
INSERT OR IGNORE INTO estado_tarea VALUES (4, 'error');

INSERT OR IGNORE INTO estado_resultado VALUES (1, 'pendiente');
INSERT OR IGNORE INTO estado_resultado VALUES (2, 'generado');
INSERT OR IGNORE INTO estado_resultado VALUES (3, 'error');

INSERT OR IGNORE INTO estado_nodo VALUES (1, 'activo');
INSERT OR IGNORE INTO estado_nodo VALUES (2, 'inactivo');

INSERT OR IGNORE INTO transformacion (id_transformacion, tipo, descripcion)
    VALUES (1, 'resize', 'Redimensionar imagen al ancho y alto indicados');
INSERT OR IGNORE INTO transformacion (id_transformacion, tipo, descripcion)
    VALUES (2, 'grayscale', 'Convertir imagen a escala de grises');
INSERT OR IGNORE INTO transformacion (id_transformacion, tipo, descripcion)
    VALUES (3, 'rotate', 'Rotar imagen N grados');
INSERT OR IGNORE INTO transformacion (id_transformacion, tipo, descripcion)
    VALUES (4, 'crop', 'Recortar región rectangular de la imagen');
INSERT OR IGNORE INTO transformacion (id_transformacion, tipo, descripcion)
    VALUES (5, 'flip', 'Reflejar imagen horizontal o verticalmente');
INSERT OR IGNORE INTO transformacion (id_transformacion, tipo, descripcion)
    VALUES (6, 'blur', 'Aplicar desenfoque gaussiano');
INSERT OR IGNORE INTO transformacion (id_transformacion, tipo, descripcion)
    VALUES (7, 'sharpen', 'Aumentar nitidez de la imagen');
INSERT OR IGNORE INTO transformacion (id_transformacion, tipo, descripcion)
    VALUES (8, 'brightness', 'Ajustar brillo de la imagen');
INSERT OR IGNORE INTO transformacion (id_transformacion, tipo, descripcion)
    VALUES (9, 'contrast', 'Ajustar contraste de la imagen');
INSERT OR IGNORE INTO transformacion (id_transformacion, tipo, descripcion)
    VALUES (10, 'watermark', 'Añadir texto como marca de agua');
INSERT OR IGNORE INTO transformacion (id_transformacion, tipo, descripcion)
    VALUES (11, 'convert', 'Convertir formato de salida (jpeg, png, tiff)');
"""

# Migraciones para instalaciones existentes (sin las nuevas columnas FK)
MIGRATIONS = [
    "ALTER TABLE lote_procesamiento ADD COLUMN id_estado_lote INTEGER REFERENCES estado_lote(id_estado_lote)",
    "ALTER TABLE imagen ADD COLUMN id_estado_tarea INTEGER REFERENCES estado_tarea(id_estado_tarea)",
    "ALTER TABLE imagen ADD COLUMN formato TEXT",
    "ALTER TABLE imagen ADD COLUMN resolucion TEXT",
    "ALTER TABLE imagen_transformacion ADD COLUMN id_transformacion INTEGER REFERENCES transformacion(id_transformacion)",
    "ALTER TABLE nodo_worker ADD COLUMN id_estado_nodo INTEGER DEFAULT 1",
    "ALTER TABLE log_procesamiento ADD COLUMN id_lote TEXT",
    "ALTER TABLE log_procesamiento ADD COLUMN id_tarea INTEGER",
    "ALTER TABLE log_procesamiento ADD COLUMN descripcion TEXT",
]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        for migration in MIGRATIONS:
            try:
                conn.execute(migration)
            except Exception:
                pass  # Columna ya existe
        conn.executescript(SEED)


init_db()
