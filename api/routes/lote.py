import json
import shutil
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from typing import List

from schemas.lote_schema import LoteEstadoResponse, LoteResponse
from services.persistence_service import PersistenceService
from services.rabbitmq_service import publicar_tarea
from services.storage_service import StorageService

router = APIRouter()

storage = StorageService()
persistence = PersistenceService()

EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp", ".gif"}
FORMATOS_PERMITIDOS = {"JPEG", "PNG", "TIFF"}
STORAGE_OUTPUT = Path(__file__).parent.parent / "storage" / "output"


class _ArchivoMemoria:
    """Simula la interfaz mínima de UploadFile para archivos extraídos de un ZIP."""

    def __init__(self, nombre: str, contenido: bytes):
        self.filename = nombre
        self.file = BytesIO(contenido)

    async def read(self) -> bytes:
        self.file.seek(0)
        return self.file.read()


def _extraer_archivos_zip(archivo_zip: UploadFile) -> tuple[dict, dict]:
    """Extrae imágenes y JSONs de un ZIP y los devuelve clasificados por nombre base."""
    archivo_zip.file.seek(0)
    contenido_zip = archivo_zip.file.read()

    try:
        zf = zipfile.ZipFile(BytesIO(contenido_zip))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="El archivo ZIP está corrupto")

    entradas = [e for e in zf.infolist() if not e.is_dir()]
    if not entradas:
        raise HTTPException(status_code=400, detail="El archivo ZIP está vacío")

    imagenes: dict[str, _ArchivoMemoria] = {}
    jsons: dict[str, _ArchivoMemoria] = {}

    for entrada in entradas:
        nombre = Path(entrada.filename).name  # ignorar subdirectorios del zip
        ext = Path(nombre).suffix.lower()
        stem = Path(nombre).stem
        contenido = zf.read(entrada.filename)
        archivo = _ArchivoMemoria(nombre, contenido)

        if ext in EXTENSIONES_IMAGEN:
            imagenes[stem] = archivo
        elif ext == ".json":
            jsons[stem] = archivo

    return imagenes, jsons


def _leer_metadata_imagen(contenido: bytes, nombre_archivo: str) -> tuple[str, str]:
    """
    Abre los bytes de imagen con PIL y retorna (formato, resolucion).
    Valida que el formato sea uno de los permitidos: JPEG, PNG, TIFF.
    """
    try:
        with Image.open(BytesIO(contenido)) as pil_img:
            formato = pil_img.format
            width, height = pil_img.size
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo leer la imagen: {nombre_archivo}",
        )

    if formato not in FORMATOS_PERMITIDOS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Formato no permitido en '{nombre_archivo}': {formato}. "
                f"Formatos aceptados: {', '.join(sorted(FORMATOS_PERMITIDOS))}"
            ),
        )

    resolucion = f"{width}x{height}"
    return formato, resolucion


_DESCRIPCION_POST_LOTE = """
Crea un nuevo lote de procesamiento de imágenes.

---

**Formato de envío**

Enviar archivos individualmente o dentro de un único ZIP.
Para cada imagen debe existir un archivo JSON con el **mismo nombre base**:

```
img1.jpg  →  img1.json
foto2.png →  foto2.json
```

---

**Formato del JSON de transformaciones**

```json
{
  "transformaciones": [
    { "tipo": "resize", "width": 800, "height": 600 },
    { "tipo": "grayscale" },
    { "tipo": "rotate", "angle": 90 }
  ]
}
```

---

**Transformaciones soportadas**

| Tipo        | Parámetros requeridos         |
|-------------|-------------------------------|
| `resize`    | `width` (int), `height` (int) |
| `grayscale` | _(sin parámetros)_            |
| `rotate`    | `angle` (float, grados)       |

---

**Formatos de imagen permitidos:** JPEG, PNG, TIFF

---

**Flujo de uso**

1. `POST /lote` — subir batch → retorna `id_lote`
2. `GET /lote/{id_lote}` — consultar estado y progreso
3. `GET /lote/{id_lote}/resultado` — descargar ZIP con imágenes procesadas
"""


@router.post(
    "/lote",
    response_model=LoteResponse,
    summary="Crear lote de procesamiento",
    description=_DESCRIPCION_POST_LOTE,
)
async def crear_lote(background_tasks: BackgroundTasks, archivos: List[UploadFile] = File(...)):
    for f in archivos:
        if not f.filename:
            raise HTTPException(status_code=400, detail="Archivo sin nombre detectado")

    archivo_zip = next(
        (f for f in archivos if Path(f.filename).suffix.lower() == ".zip"), None
    )

    if archivo_zip:
        imagenes, jsons = _extraer_archivos_zip(archivo_zip)
        if not imagenes:
            raise HTTPException(
                status_code=400,
                detail="El archivo ZIP no contiene imágenes válidas",
            )
        if not jsons:
            raise HTTPException(
                status_code=400,
                detail="El archivo ZIP no contiene archivos JSON",
            )
        faltantes_zip = [nombre for nombre in imagenes if nombre not in jsons]
        if faltantes_zip:
            raise HTTPException(
                status_code=400,
                detail=f"Faltan archivos JSON para las imágenes: {', '.join(faltantes_zip)}",
            )
    else:
        imagenes = {
            Path(f.filename).stem: f
            for f in archivos
            if Path(f.filename).suffix.lower() in EXTENSIONES_IMAGEN
        }
        jsons = {
            Path(f.filename).stem: f
            for f in archivos
            if Path(f.filename).suffix.lower() == ".json"
        }

    if not imagenes:
        raise HTTPException(status_code=400, detail="No se enviaron imágenes válidas")

    faltantes = [nombre for nombre in imagenes if nombre not in jsons]
    if faltantes:
        raise HTTPException(
            status_code=400,
            detail=f"Faltan archivos JSON para las imágenes: {', '.join(faltantes)}",
        )

    id_lote = str(uuid.uuid4())
    persistence.crear_lote(id_lote)

    for nombre_base, archivo_img in imagenes.items():
        archivo_json = jsons[nombre_base]

        contenido_json = await archivo_json.read()
        try:
            json_data = json.loads(contenido_json)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail=f"JSON inválido en el archivo: {archivo_json.filename}",
            )

        archivo_json.file.seek(0)

        # Leer bytes de la imagen para obtener metadata real con PIL
        contenido_img = await archivo_img.read()
        formato, resolucion = _leer_metadata_imagen(contenido_img, archivo_img.filename)
        archivo_img.file.seek(0)

        id_imagen = str(uuid.uuid4())

        ruta_img = storage.guardar_imagen(archivo_img, archivo_img.filename, id_lote)
        storage.guardar_json(archivo_json, archivo_json.filename, id_lote)

        persistence.guardar_imagen(id_lote, id_imagen, nombre_base, ruta_img, formato, resolucion)
        persistence.guardar_transformaciones(id_imagen, json_data)

        background_tasks.add_task(
            publicar_tarea,
            {"id_imagen": id_imagen, "ruta": ruta_img, "id_lote": id_lote},
        )

    return LoteResponse(id_lote=id_lote, estado="procesando")


@router.get(
    "/lote/{id_lote}",
    response_model=LoteEstadoResponse,
    summary="Estado del lote",
    description="Retorna el estado actual del lote y el progreso de procesamiento.",
)
async def estado_lote(id_lote: str):
    lote = persistence.obtener_lote(id_lote)
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado")

    stats = persistence.obtener_estadisticas_lote(id_lote)
    total = stats["total"]
    completadas = stats["completadas"]
    progreso = round(completadas / total * 100, 1) if total > 0 else 0.0

    return LoteEstadoResponse(
        id_lote=id_lote,
        estado=lote["estado"],
        total=total,
        completadas=completadas,
        progreso=progreso,
    )


@router.get(
    "/lote/{id_lote}/resultado",
    summary="Descargar resultados",
    description="Descarga un ZIP con todas las imágenes procesadas del lote. Limpia el directorio de salida tras la descarga.",
)
async def descargar_resultado(id_lote: str, background_tasks: BackgroundTasks):
    lote = persistence.obtener_lote(id_lote)
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado")
    if lote["estado"] != "completado":
        raise HTTPException(status_code=400, detail="El lote aún no está completado")

    output_dir = STORAGE_OUTPUT / id_lote
    if not output_dir.exists() or not any(output_dir.iterdir()):
        raise HTTPException(status_code=404, detail="No se encontraron resultados para este lote")

    zip_path = STORAGE_OUTPUT / f"{id_lote}_resultado.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for archivo in output_dir.iterdir():
            if archivo.is_file():
                zf.write(archivo, archivo.name)

    background_tasks.add_task(_limpiar_resultado, output_dir, zip_path)

    return FileResponse(
        path=str(zip_path),
        filename=f"lote_{id_lote[:8]}_resultado.zip",
        media_type="application/zip",
    )


@router.get(
    "/info",
    summary="Información del sistema",
    description="Retorna las transformaciones disponibles, un ejemplo de JSON y el flujo de uso.",
)
async def info():
    return {
        "transformaciones": [
            {
                "tipo": "resize",
                "descripcion": "Redimensionar imagen al ancho y alto indicados",
                "parametros": {"width": "int — ancho en píxeles", "height": "int — alto en píxeles"},
            },
            {
                "tipo": "grayscale",
                "descripcion": "Convertir imagen a escala de grises",
                "parametros": {},
            },
            {
                "tipo": "rotate",
                "descripcion": "Rotar imagen N grados en sentido antihorario",
                "parametros": {"angle": "float — grados de rotación"},
            },
        ],
        "formatos_permitidos": sorted(FORMATOS_PERMITIDOS),
        "ejemplo_json": {
            "transformaciones": [
                {"tipo": "resize", "width": 800, "height": 600},
                {"tipo": "grayscale"},
                {"tipo": "rotate", "angle": 90},
            ]
        },
        "flujo": [
            "POST /lote — subir imágenes y JSONs (individuales o en ZIP) → retorna id_lote",
            "GET /lote/{id_lote} — consultar estado y progreso del procesamiento",
            "GET /lote/{id_lote}/resultado — descargar ZIP con imágenes procesadas",
        ],
    }


def _limpiar_resultado(output_dir: Path, zip_path: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    if zip_path.exists():
        zip_path.unlink()
