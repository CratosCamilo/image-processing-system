#!/usr/bin/env python3
"""
stress_test.py — Prueba de carga continua del sistema de procesamiento de imágenes.

Simula flujo real durante ~2 minutos: genera lotes, los envía, monitorea progreso
y descarga los resultados al completarse (sin guardar el contenido) para liberar
espacio en el servidor.

Uso:
    python scripts/stress_test.py
    python scripts/stress_test.py --url http://localhost:8000
"""

import argparse
import io
import json
import random
import threading
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

# ─────────────────────────── CONFIG ─────────────────────────────────────────

API_BASE         = "http://localhost:8000"
DURACION_SEG     = 120          # duración total de la prueba
MAX_CONCURRENTE  = 3            # máximo de lotes activos al mismo tiempo
POLL_INTERVAL    = 5            # segundos entre rondas de polling
MIN_IMAGENES     = 3
MAX_IMAGENES     = 35

# Momentos de envío: (segundos desde inicio, cantidad de lotes a intentar enviar)
SCHEDULE = [
    (10,  2),
    (40,  3),
    (80,  2),
]

PICSUM_SIZES = [(400, 300), (640, 480), (800, 600), (1024, 768), (1280, 720)]
TEXTOS_WM    = ["Test", "Demo", "Sample", "Confidencial"]
POSICIONES   = ["top-left", "top-right", "bottom-left", "bottom-right", "center"]


# ──────────────────── GENERADORES DE TRANSFORMACIONES ────────────────────────
# (misma lógica que scripts/generarbatch.py)

def gen_resize(*_):
    return {"tipo": "resize", "width": random.randint(200, 800), "height": random.randint(200, 800)}

def gen_grayscale(*_):
    return {"tipo": "grayscale"}

def gen_rotate(*_):
    return {"tipo": "rotate", "angle": random.choice([90, 180, 270])}

def gen_crop(w, h):
    max_w = int(w * 0.8); max_h = int(h * 0.8)
    cw = random.randint(max_w // 2, max_w); ch = random.randint(max_h // 2, max_h)
    x  = random.randint(0, w - cw);          y  = random.randint(0, h - ch)
    return {"tipo": "crop", "x": x, "y": y, "width": cw, "height": ch}

def gen_flip(*_):
    return {"tipo": "flip", "direction": random.choice(["horizontal", "vertical"])}

def gen_blur(*_):
    return {"tipo": "blur", "radius": round(random.uniform(0.5, 3.0), 1)}

def gen_sharpen(*_):
    return {"tipo": "sharpen", "factor": round(random.uniform(1.0, 2.0), 1)}

def gen_brightness(*_):
    return {"tipo": "brightness", "factor": round(random.uniform(0.5, 2.0), 1)}

def gen_contrast(*_):
    return {"tipo": "contrast", "factor": round(random.uniform(0.5, 2.0), 1)}

def gen_watermark(*_):
    return {"tipo": "watermark", "text": random.choice(TEXTOS_WM),
            "position": random.choice(POSICIONES), "opacity": round(random.uniform(0.3, 0.8), 1)}

def gen_convert(*_):
    return {"tipo": "convert", "format": random.choice(["jpeg", "png", "tiff"])}

_GRUPOS = [
    [gen_crop],
    [gen_resize, gen_rotate, gen_flip],
    [gen_brightness, gen_contrast, gen_grayscale],
    [gen_blur, gen_sharpen],
    [gen_watermark],
]

def _generar_transformaciones(img_w: int, img_h: int) -> list:
    k = random.randint(1, 5)
    resultado, tipos = [], set()
    for grupo in _GRUPOS:
        if len(resultado) >= k:
            break
        if random.random() < 0.5:
            gen = random.choice(grupo)
            t = gen(img_w, img_h)
            if t["tipo"] not in tipos:
                resultado.append(t); tipos.add(t["tipo"])
    extras = [gen_resize, gen_rotate, gen_flip, gen_brightness,
              gen_contrast, gen_grayscale, gen_blur, gen_sharpen, gen_watermark]
    random.shuffle(extras)
    for gen in extras:
        if len(resultado) >= k:
            break
        t = gen(img_w, img_h)
        if t["tipo"] not in tipos:
            resultado.append(t); tipos.add(t["tipo"])
    resultado = resultado[:k]
    if random.random() < 0.3 and len(resultado) < k:
        resultado.append(gen_convert(img_w, img_h))
    return resultado or [gen_grayscale(img_w, img_h)]


# ──────────────────────── GENERACIÓN DE ZIP EN MEMORIA ───────────────────────

def _generar_zip_en_memoria(n_imagenes: int) -> tuple[bytes, int]:
    """
    Descarga n_imagenes de picsum.photos y las empaqueta junto a sus JSONs
    en un ZIP en memoria. Retorna (zip_bytes, cantidad_real).
    """
    buf = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(1, n_imagenes + 1):
            img_w, img_h = random.choice(PICSUM_SIZES)
            resp = requests.get(f"https://picsum.photos/{img_w}/{img_h}", timeout=20)
            resp.raise_for_status()
            nombre = f"img{i:03d}"
            zf.writestr(f"{nombre}.jpg", resp.content)
            transforms = _generar_transformaciones(img_w, img_h)
            zf.writestr(f"{nombre}.json", json.dumps({"transformaciones": transforms}))
            total += 1
    return buf.getvalue(), total


# ─────────────────────────── LLAMADAS A LA API ───────────────────────────────

def api_enviar_lote(base: str, zip_bytes: bytes) -> Optional[str]:
    try:
        resp = requests.post(
            f"{base}/lote",
            files={"archivos": ("lote.zip", zip_bytes, "application/zip")},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("id_lote")
    except Exception as e:
        _log(f"[!] Error enviando lote: {e}")
        return None


def api_estado(base: str, id_lote: str) -> Optional[dict]:
    try:
        resp = requests.get(f"{base}/lote/{id_lote}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        _log(f"[!] Error consultando {id_lote[:8]}: {e}")
        return None


def api_descargar(base: str, id_lote: str) -> tuple[bool, int]:
    """
    Descarga el ZIP de resultados y lo descarta (solo libera espacio en el servidor).
    Retorna (éxito, bytes_recibidos).
    """
    try:
        resp = requests.get(f"{base}/lote/{id_lote}/resultado", timeout=60, stream=True)
        resp.raise_for_status()
        kb = sum(len(chunk) for chunk in resp.iter_content(chunk_size=8192)) // 1024
        return True, kb
    except Exception as e:
        _log(f"[!] Error descargando {id_lote[:8]}: {e}")
        return False, 0


# ─────────────────────────── ESTADO DE LOTE ──────────────────────────────────

@dataclass
class EstadoLote:
    id_lote: str
    numero: int
    n_imagenes: int
    t_envio: float
    t_completado: Optional[float] = None
    t_descargado: Optional[float] = None
    progreso: float = 0.0
    completadas: int = 0
    estado_api: str = "pendiente"
    error: bool = False
    kb_descargados: int = 0


# ─────────────────────────── UTILIDADES ──────────────────────────────────────

def _log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


# ─────────────────────────── BUCLE PRINCIPAL ─────────────────────────────────

def main(base_url: str):
    _log(f"=== PRUEBA DE CARGA | API: {base_url} | Duración: {DURACION_SEG}s ===")
    _log(f"    Schedule: {SCHEDULE}")
    _log(f"    Máx. concurrente: {MAX_CONCURRENTE} | Poll: {POLL_INTERVAL}s\n")

    t_inicio      = time.time()
    lotes: dict[str, EstadoLote] = {}
    schedule_idx  = 0
    lote_numero   = 0

    def elapsed() -> float:
        return time.time() - t_inicio

    lotes_lock = threading.Lock()

    def lotes_activos() -> list[EstadoLote]:
        return [l for l in lotes.values() if l.t_completado is None and not l.error]

    def _worker_envio(numero: int, n: int):
        """Genera el ZIP y lo envía. Corre en su propio thread."""
        _log(f"  → [#{numero}] Generando lote ({n} imágenes, descargando de picsum)...")
        try:
            zip_bytes, real_n = _generar_zip_en_memoria(n)
        except Exception as e:
            _log(f"  [!] [#{numero}] Error generando: {e}")
            return
        id_lote = api_enviar_lote(base_url, zip_bytes)
        if id_lote:
            est = EstadoLote(id_lote=id_lote, numero=numero,
                             n_imagenes=real_n, t_envio=elapsed())
            with lotes_lock:
                lotes[id_lote] = est
            _log(f"  ✔ [#{numero}] Enviado → {id_lote[:8]}... ({real_n} imgs)")
        else:
            _log(f"  ✗ [#{numero}] La API rechazó el envío")

    def enviar_lotes_en_paralelo(cantidad: int):
        """Lanza `cantidad` threads de envío simultáneamente y espera a que terminen."""
        nonlocal lote_numero
        threads = []
        for _ in range(cantidad):
            lote_numero += 1
            n = random.randint(MIN_IMAGENES, MAX_IMAGENES)
            t = threading.Thread(target=_worker_envio, args=(lote_numero, n), daemon=True)
            threads.append(t)
        # Arrancar todos juntos para que lleguen casi al mismo tiempo a la API
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def poll_y_descargar():
        pendientes = [l for l in lotes.values() if l.t_descargado is None]
        if not pendientes:
            return
        for est in pendientes:
            info = api_estado(base_url, est.id_lote)
            if not info:
                continue
            est.progreso    = info.get("progreso", 0.0)
            est.completadas = info.get("completadas", 0)
            est.estado_api  = info.get("estado", "?")

            icono = "✔" if est.progreso >= 100 else ("✗" if est.estado_api == "error" else "·")
            _log(f"  {icono} #{est.numero} {est.id_lote[:8]}... "
                 f"[{est.estado_api}] {est.completadas}/{est.n_imagenes} "
                 f"({est.progreso:.0f}%)")

            if est.progreso >= 100.0 and est.t_completado is None:
                est.t_completado = elapsed()
                ok, kb = api_descargar(base_url, est.id_lote)
                if ok:
                    est.t_descargado = elapsed()
                    est.kb_descargados = kb
                    dur = est.t_completado - est.t_envio
                    _log(f"    ↓ #{est.numero} descargado ({kb} KB descartado) "
                         f"— procesado en {dur:.0f}s")
                else:
                    est.estado_api = "error_descarga"

            elif est.estado_api == "error":
                est.error = True

    # ── Bucle principal ───────────────────────────────────────────────────
    while elapsed() < DURACION_SEG:
        t = elapsed()

        # Verificar schedule
        if schedule_idx < len(SCHEDULE):
            t_sched, cant = SCHEDULE[schedule_idx]
            if t >= t_sched:
                schedule_idx += 1
                disponibles = MAX_CONCURRENTE - len(lotes_activos())
                a_enviar = min(cant, disponibles)
                _log(f"\n[t={t:.0f}s] ─── Schedule: {cant} lote(s) programado(s), "
                     f"{disponibles} slot(s) disponible(s) → enviando {a_enviar} en paralelo ───")
                if a_enviar > 0:
                    enviar_lotes_en_paralelo(a_enviar)
                if a_enviar < cant:
                    _log(f"  (!) {cant - a_enviar} lote(s) omitido(s): cupo lleno")

        # Polling
        if lotes:
            _log(f"\n[t={t:.0f}s] ─── Consultando {len(lotes)} lote(s) ───")
            poll_y_descargar()

        time.sleep(POLL_INTERVAL)

    # Consulta final antes del reporte
    _log(f"\n[t={elapsed():.0f}s] ─── Tiempo agotado — consulta final ───")
    poll_y_descargar()

    generar_reporte(lotes, t_inicio)


# ─────────────────────────── REPORTE FINAL ───────────────────────────────────

def generar_reporte(lotes: dict[str, EstadoLote], t_inicio: float):
    t_total = time.time() - t_inicio
    inicio  = datetime.fromtimestamp(t_inicio).strftime("%Y-%m-%d %H:%M:%S")
    fin     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    completados = [l for l in lotes.values() if l.t_completado is not None]
    descargados = [l for l in lotes.values() if l.t_descargado is not None]
    en_proceso  = [l for l in lotes.values() if l.t_completado is None and not l.error]
    con_error   = [l for l in lotes.values() if l.error]

    total_imgs  = sum(l.n_imagenes for l in lotes.values())
    imgs_proc   = sum(l.completadas for l in lotes.values())
    total_kb    = sum(l.kb_descargados for l in descargados)

    duraciones  = [l.t_completado - l.t_envio for l in completados if l.t_completado]
    prom_dur    = sum(duraciones) / len(duraciones) if duraciones else 0

    SEP  = "=" * 72
    SEP2 = "-" * 72

    lines = [
        "",
        SEP,
        "  REPORTE DE PRUEBA DE CARGA — SISTEMA DE PROCESAMIENTO DE IMÁGENES",
        SEP,
        f"  Inicio:              {inicio}",
        f"  Fin:                 {fin}",
        f"  Duración real:       {t_total:.1f}s",
        SEP2,
        f"  LOTES ENVIADOS:      {len(lotes)}",
        f"  LOTES COMPLETADOS:   {len(completados)}",
        f"  LOTES DESCARGADOS:   {len(descargados)}",
        f"  LOTES EN PROCESO:    {len(en_proceso)}",
        f"  LOTES CON ERROR:     {len(con_error)}",
        SEP2,
        f"  IMÁGENES TOTALES:    {total_imgs}",
        f"  IMÁGENES PROCESADAS: {imgs_proc}",
        f"  IMÁGENES PENDIENTES: {total_imgs - imgs_proc}",
        f"  DATOS DESCARGADOS:   {total_kb} KB (descartados)",
        SEP2,
        "  DETALLE POR LOTE:",
    ]

    for est in sorted(lotes.values(), key=lambda x: x.t_envio):
        t_env = f"t+{est.t_envio:.0f}s"
        if est.t_completado:
            dur = est.t_completado - est.t_envio
            resultado = f"completado en {dur:.0f}s"
        elif est.error:
            resultado = "ERROR"
        else:
            resultado = f"incompleto ({est.progreso:.0f}%)"
        dsc = f" | {est.kb_descargados} KB descargado" if est.t_descargado else ""
        lines.append(
            f"    #{est.numero:02d}  {est.id_lote[:8]}...  [{t_env}]  "
            f"{est.completadas}/{est.n_imagenes} imgs  {resultado}{dsc}"
        )

    if duraciones:
        lines += [
            SEP2,
            f"  TIEMPOS DE PROCESAMIENTO (lotes completados):",
            f"    Promedio: {prom_dur:.1f}s",
            f"    Mínimo:   {min(duraciones):.1f}s",
            f"    Máximo:   {max(duraciones):.1f}s",
        ]

    lines.append(SEP)

    reporte = "\n".join(lines)
    print(reporte)

    ruta = Path(__file__).parent / f"reporte_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    ruta.write_text(reporte + "\n", encoding="utf-8")
    print(f"\n  Reporte guardado en: {ruta.name}")


# ─────────────────────────── ENTRY POINT ─────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prueba de carga del sistema de procesamiento de imágenes"
    )
    parser.add_argument(
        "--url", default=API_BASE,
        help=f"URL base de la API (default: {API_BASE})"
    )
    args = parser.parse_args()
    main(args.url)
