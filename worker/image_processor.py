from pathlib import Path

from PIL import Image

DIRECTORIO_OUTPUT_BASE = Path(__file__).parent.parent / "api" / "storage" / "output"

TRANSFORMACIONES_SOPORTADAS = {"resize", "grayscale", "rotate"}


def procesar_imagen(ruta_imagen: str, transformaciones: list, id_lote: str) -> str:
    output_dir = DIRECTORIO_OUTPUT_BASE / id_lote
    output_dir.mkdir(parents=True, exist_ok=True)

    img = Image.open(ruta_imagen)

    # Las transformaciones llegan ordenadas por orden_aplicacion (ORDER BY en worker)
    for t in transformaciones:
        tipo = t.get("tipo")

        if tipo not in TRANSFORMACIONES_SOPORTADAS:
            raise ValueError(f"Transformación no soportada: {tipo}")

        if tipo == "resize":
            width  = t.get("width")  or t.get("ancho")
            height = t.get("height") or t.get("alto")
            img = img.resize((width, height))
        elif tipo == "grayscale":
            img = img.convert("L")
        elif tipo == "rotate":
            angle = t.get("angle") or t.get("angulo")
            img = img.rotate(angle)

    nombre_original = Path(ruta_imagen).stem
    nombre_resultado = f"{nombre_original}_result.jpg"
    ruta_resultado = output_dir / nombre_resultado

    img.convert("RGB").save(ruta_resultado)

    return str(ruta_resultado)
