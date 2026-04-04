from pathlib import Path

from fastapi import UploadFile

DIRECTORIO_INPUT = Path(__file__).parent.parent / "storage" / "input"


class StorageService:
    def __init__(self):
        DIRECTORIO_INPUT.mkdir(parents=True, exist_ok=True)

    def guardar_imagen(self, archivo: UploadFile, nombre: str, id_lote: str) -> str:
        ruta = DIRECTORIO_INPUT / id_lote / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        archivo.file.seek(0)
        ruta.write_bytes(archivo.file.read())
        return str(Path("storage") / "input" / id_lote / nombre)

    def guardar_json(self, archivo: UploadFile, nombre: str, id_lote: str) -> str:
        ruta = DIRECTORIO_INPUT / id_lote / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        archivo.file.seek(0)
        ruta.write_bytes(archivo.file.read())
        return str(Path("storage") / "input" / id_lote / nombre)
