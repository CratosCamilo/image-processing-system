from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

DIRECTORIO_OUTPUT_BASE = Path(__file__).parent.parent / "api" / "storage" / "output"

TRANSFORMACIONES_SOPORTADAS = {
    "resize", "grayscale", "rotate",
    "crop", "flip", "blur", "sharpen",
    "brightness", "contrast", "watermark", "convert",
}

_EXT_POR_FORMATO = {"JPEG": ".jpg", "PNG": ".png", "TIFF": ".tiff"}

_POSICION_OFFSET = 10  # margen en píxeles para watermark

# Cacheado a nivel de módulo para no recargar en cada watermark
_FONT_DEFAULT = ImageFont.load_default()


def _calcular_posicion_watermark(position: str, img_size: tuple, text_size: tuple) -> tuple:
    iw, ih = img_size
    tw, th = text_size
    offset = _POSICION_OFFSET
    posiciones = {
        "top-left":     (offset, offset),
        "top-right":    (iw - tw - offset, offset),
        "bottom-left":  (offset, ih - th - offset),
        "bottom-right": (iw - tw - offset, ih - th - offset),
        "center":       ((iw - tw) // 2, (ih - th) // 2),
    }
    return posiciones.get(position, (offset, offset))


def procesar_imagen(ruta_imagen: str, transformaciones: list, id_lote: str) -> str:
    output_dir = DIRECTORIO_OUTPUT_BASE / id_lote
    output_dir.mkdir(parents=True, exist_ok=True)

    img = Image.open(ruta_imagen)

    # Determinar formato de salida (puede ser sobreescrito por "convert")
    output_format = "JPEG"
    output_ext = ".jpg"

    # Las transformaciones llegan ordenadas por orden_aplicacion (ORDER BY en worker)
    for t in transformaciones:
        tipo = t.get("tipo")

        if tipo not in TRANSFORMACIONES_SOPORTADAS:
            raise ValueError(f"Transformación no soportada: '{tipo}'")

        if tipo == "resize":
            img = img.resize((t["width"], t["height"]), Image.LANCZOS)

        elif tipo == "grayscale":
            img = img.convert("L")

        elif tipo == "rotate":
            # expand=True evita que la imagen sea recortada al rotar ángulos no múltiplos de 90°
            img = img.rotate(t["angle"], expand=True)

        elif tipo == "crop":
            x, y, w, h = t["x"], t["y"], t["width"], t["height"]
            img_w, img_h = img.size
            if x < 0 or y < 0 or x + w > img_w or y + h > img_h:
                raise ValueError(
                    f"crop fuera de límites: imagen {img_w}x{img_h}, "
                    f"solicitado ({x},{y}) + {w}x{h}"
                )
            img = img.crop((x, y, x + w, y + h))

        elif tipo == "flip":
            direction = t["direction"]
            if direction == "horizontal":
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            elif direction == "vertical":
                img = img.transpose(Image.FLIP_TOP_BOTTOM)
            else:
                raise ValueError(
                    f"flip: direction inválido '{direction}'. "
                    f"Valores permitidos: 'horizontal', 'vertical'"
                )

        elif tipo == "blur":
            img = img.filter(ImageFilter.GaussianBlur(radius=t["radius"]))

        elif tipo == "sharpen":
            img = ImageEnhance.Sharpness(img).enhance(t["factor"])

        elif tipo == "brightness":
            img = ImageEnhance.Brightness(img).enhance(t["factor"])

        elif tipo == "contrast":
            img = ImageEnhance.Contrast(img).enhance(t["factor"])

        elif tipo == "watermark":
            text = t["text"][:50]  # protección contra textos excesivamente largos
            position = t["position"]
            opacity = t["opacity"]
            alpha = int(opacity * 255)

            # Crear capa de texto y medir con el mismo Draw (sin imagen 1×1 auxiliar)
            modo_original = img.mode
            base = img.convert("RGBA")
            txt_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_layer)

            bbox = draw.textbbox((0, 0), text, font=_FONT_DEFAULT)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            xy = _calcular_posicion_watermark(position, img.size, (text_w, text_h))
            draw.text(xy, text, fill=(255, 255, 255, alpha), font=_FONT_DEFAULT)

            base = Image.alpha_composite(base, txt_layer)
            img = base if modo_original == "RGBA" else base.convert(modo_original)

        elif tipo == "convert":
            fmt = t["format"].upper()  # "jpeg"→"JPEG", "png"→"PNG", "tiff"→"TIFF"
            if fmt not in _EXT_POR_FORMATO:
                raise ValueError(
                    f"Formato de conversión no soportado: '{fmt}'. "
                    f"Soportados: {list(_EXT_POR_FORMATO)}"
                )
            output_format = fmt
            output_ext = _EXT_POR_FORMATO[fmt]
            # No modifica píxeles — solo registra el formato de salida

    nombre_original = Path(ruta_imagen).stem
    nombre_resultado = f"{nombre_original}_result{output_ext}"
    ruta_resultado = output_dir / nombre_resultado

    # Garantizar compatibilidad de modo con formato de salida
    if output_format == "JPEG" and img.mode != "RGB":
        img = img.convert("RGB")
    elif output_format == "PNG" and img.mode not in ("RGB", "RGBA", "L", "P"):
        img = img.convert("RGB")
    elif output_format == "TIFF" and img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")

    img.save(ruta_resultado, format=output_format)

    return str(ruta_resultado)
