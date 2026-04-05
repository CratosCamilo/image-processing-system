import json
import random
import sys
import zipfile
from pathlib import Path

import requests

# -------- CONFIG --------
OUTPUT_DIR = Path("batch_temp")
ZIP_NAME = "lote.zip"

SIZES = [
    (400, 300),
    (640, 480),
    (800, 600),
    (1024, 768),
    (1280, 720),
]

TEXTOS_WATERMARK = ["Test", "Demo", "Sample", "Confidencial"]
POSICIONES_WATERMARK = ["top-left", "top-right", "bottom-left", "bottom-right", "center"]


# -------- GENERADORES POR TIPO --------

def gen_resize(*_):
    return {"tipo": "resize",
            "width": random.randint(200, 800),
            "height": random.randint(200, 800)}


def gen_grayscale(*_):
    return {"tipo": "grayscale"}


def gen_rotate(*_):
    return {"tipo": "rotate",
            "angle": random.choice([90, 180, 270])}


def gen_crop(img_w, img_h):
    max_w = int(img_w * 0.8)
    max_h = int(img_h * 0.8)
    crop_w = random.randint(max_w // 2, max_w)
    crop_h = random.randint(max_h // 2, max_h)
    x = random.randint(0, img_w - crop_w)
    y = random.randint(0, img_h - crop_h)
    return {"tipo": "crop", "x": x, "y": y, "width": crop_w, "height": crop_h}


def gen_flip(*_):
    return {"tipo": "flip",
            "direction": random.choice(["horizontal", "vertical"])}


def gen_blur(*_):
    return {"tipo": "blur",
            "radius": round(random.uniform(0.5, 3.0), 1)}


def gen_sharpen(*_):
    return {"tipo": "sharpen",
            "factor": round(random.uniform(1.0, 2.0), 1)}


def gen_brightness(*_):
    return {"tipo": "brightness",
            "factor": round(random.uniform(0.5, 2.0), 1)}


def gen_contrast(*_):
    return {"tipo": "contrast",
            "factor": round(random.uniform(0.5, 2.0), 1)}


def gen_watermark(*_):
    return {"tipo": "watermark",
            "text": random.choice(TEXTOS_WATERMARK),
            "position": random.choice(POSICIONES_WATERMARK),
            "opacity": round(random.uniform(0.3, 0.8), 1)}


def gen_convert(*_):
    return {"tipo": "convert",
            "format": random.choice(["jpeg", "png", "tiff"])}


# Grupos ordenados según pipeline lógico:
# crop → geometría → color → filtro → watermark → convert
_GRUPOS_ORDENADOS = [
    [gen_crop],
    [gen_resize, gen_rotate, gen_flip],
    [gen_brightness, gen_contrast, gen_grayscale],
    [gen_blur, gen_sharpen],
    [gen_watermark],
]


def generar_transformaciones(img_w, img_h) -> list:
    k = random.randint(1, 5)
    resultado = []
    tipos_ya: set = set()

    for grupo in _GRUPOS_ORDENADOS:
        if len(resultado) >= k:
            break
        if random.random() < 0.5:
            gen = random.choice(grupo)
            t = gen(img_w, img_h)
            if t["tipo"] not in tipos_ya:
                resultado.append(t)
                tipos_ya.add(t["tipo"])

    # Completar si faltan transformaciones
    extras = [gen_resize, gen_rotate, gen_flip, gen_brightness,
              gen_contrast, gen_grayscale, gen_blur, gen_sharpen, gen_watermark]
    random.shuffle(extras)
    for gen in extras:
        if len(resultado) >= k:
            break
        t = gen(img_w, img_h)
        if t["tipo"] not in tipos_ya:
            resultado.append(t)
            tipos_ya.add(t["tipo"])

    # Garantizar límite global de k transformaciones (antes de convert)
    resultado = resultado[:k]

    # convert siempre al final, máximo 1 vez (30% de probabilidad), solo si hay espacio
    if random.random() < 0.3 and len(resultado) < k:
        resultado.append(gen_convert(img_w, img_h))

    return resultado if resultado else [gen_grayscale(img_w, img_h)]


# -------- VALIDAR INPUT --------
if len(sys.argv) != 2:
    print("Uso: python generarbatch.py <cantidad>")
    sys.exit(1)

cantidad = int(sys.argv[1])


# -------- LIMPIAR DIRECTORIO --------
if OUTPUT_DIR.exists():
    for f in OUTPUT_DIR.iterdir():
        f.unlink()
else:
    OUTPUT_DIR.mkdir()


# -------- GENERAR DATA --------
for i in range(1, cantidad + 1):
    nombre = f"img{i}"

    img_w, img_h = random.choice(SIZES)
    url = f"https://picsum.photos/{img_w}/{img_h}"
    response = requests.get(url, timeout=15)

    img_path = OUTPUT_DIR / f"{nombre}.jpg"
    with open(img_path, "wb") as f:
        f.write(response.content)

    transformaciones = generar_transformaciones(img_w, img_h)
    json_data = {"transformaciones": transformaciones}

    json_path = OUTPUT_DIR / f"{nombre}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    tipos = [t["tipo"] for t in transformaciones]
    print(f"✔ {nombre} ({img_w}x{img_h}): {' → '.join(tipos)}")


# -------- CREAR ZIP --------
with zipfile.ZipFile(ZIP_NAME, "w") as z:
    for file in OUTPUT_DIR.iterdir():
        z.write(file, file.name)

print(f"\nZIP generado: {ZIP_NAME} ({cantidad} imágenes)")
