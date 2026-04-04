import requests
import random
import json
import zipfile
import sys
from pathlib import Path

# -------- CONFIG --------
OUTPUT_DIR = Path("batch_temp")
ZIP_NAME = "lote.zip"

SIZES = [
    (200, 300),
    (400, 400),
    (800, 600),
    (1024, 768),
    (1920, 1080),
]

TRANSFORMACIONES = [
    lambda: {"tipo": "grayscale"},
    lambda: {"tipo": "rotate", "angle": random.choice([90, 180, 270])},
    lambda: {"tipo": "resize", "width": random.choice([200, 300, 500]), "height": random.choice([200, 300, 500])},
]


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

    # 🔹 Descargar imagen
    w, h = random.choice(SIZES)
    url = f"https://picsum.photos/{w}/{h}"

    response = requests.get(url)
    img_path = OUTPUT_DIR / f"{nombre}.jpg"

    with open(img_path, "wb") as f:
        f.write(response.content)

    # 🔹 Generar JSON
    transformaciones = [t() for t in random.sample(TRANSFORMACIONES, k=2)]

    json_data = {
        "transformaciones": transformaciones
    }

    json_path = OUTPUT_DIR / f"{nombre}.json"

    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2)

    print(f"✔ Generado {nombre}")


# -------- CREAR ZIP --------
with zipfile.ZipFile(ZIP_NAME, "w") as z:
    for file in OUTPUT_DIR.iterdir():
        z.write(file, file.name)

print(f"\n🔥 ZIP generado: {ZIP_NAME}")