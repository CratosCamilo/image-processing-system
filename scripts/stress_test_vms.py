#!/usr/bin/env python3
"""
stress_test_vms.py — Prueba de carga para el deploy en VMs sin Docker.

Simula flujo real durante ~2 minutos: genera lotes, los envía, monitorea progreso
y descarga los resultados al completarse. Genera un reporte HTML interactivo con
Gantt de procesamiento, detalle por lote y resumen por nodo.

Uso:
    python scripts/stress_test_vms.py --url http://<IP-VM-API>:8000 --db-url postgresql://admin:admin123@<IP-VM-DB>:5432/image_processing

Ejemplo casa:
    python scripts/stress_test_vms.py --url http://192.168.40.15:8000 --db-url postgresql://admin:admin123@192.168.40.12:5432/image_processing
"""

import argparse
import io
import json
import os
import random
import threading
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

try:
    import psycopg2
    import psycopg2.extras
    _DB_OK = True
except ImportError:
    _DB_OK = False

DB_URL = os.getenv("DATABASE_URL", "postgresql://admin:admin123@localhost:5432/image_processing")

# ─────────────────────────── CONFIG ─────────────────────────────────────────

API_BASE         = "http://192.168.40.15:8000"
DURACION_SEG     = 120
MAX_CONCURRENTE  = 3
POLL_INTERVAL    = 5
MIN_IMAGENES     = 3
MAX_IMAGENES     = 35

TEST_CORREO      = "admin@test.com"
TEST_PASSWORD    = "1234"

SCHEDULE = [
    (10,  2),
    (40,  3),
    (80,  2),
]

PICSUM_SIZES = [(400, 300), (640, 480), (800, 600), (1024, 768), (1280, 720)]
TEXTOS_WM    = ["Test", "Demo", "Sample", "Confidencial"]
POSICIONES   = ["top-left", "top-right", "bottom-left", "bottom-right", "center"]


# ──────────────────── GENERADORES DE TRANSFORMACIONES ────────────────────────

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

def api_login(base: str) -> str:
    resp = requests.post(
        f"{base}/auth/login",
        json={"correo": TEST_CORREO, "password": TEST_PASSWORD},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def api_enviar_lote(base: str, zip_bytes: bytes, headers: dict) -> Optional[str]:
    try:
        resp = requests.post(
            f"{base}/lote",
            files={"archivos": ("lote.zip", zip_bytes, "application/zip")},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("id_lote")
    except Exception as e:
        _log(f"[!] Error enviando lote: {e}")
        return None


def api_estado(base: str, id_lote: str, headers: dict) -> Optional[dict]:
    try:
        resp = requests.get(f"{base}/lote/{id_lote}", headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        _log(f"[!] Error consultando {id_lote[:8]}: {e}")
        return None


def api_descargar(base: str, id_lote: str, headers: dict) -> tuple[bool, int]:
    try:
        resp = requests.get(f"{base}/lote/{id_lote}/resultado", headers=headers, timeout=60, stream=True)
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

    _log(f"  Autenticando como {TEST_CORREO}...")
    try:
        token = api_login(base_url)
        auth_headers = {"Authorization": f"Bearer {token}"}
        _log("  ✔ Token obtenido — sesión activa\n")
    except Exception as e:
        _log(f"  ✗ No se pudo autenticar: {e}")
        _log("  Asegúrate de que la API esté corriendo y el usuario exista.")
        return

    t_inicio      = time.time()
    lotes: dict[str, EstadoLote] = {}
    schedule_idx  = 0
    lote_numero   = 0

    def elapsed() -> float:
        return time.time() - t_inicio

    lotes_lock = threading.Lock()

    def lotes_activos() -> list[EstadoLote]:
        return [l for l in lotes.values() if l.t_completado is None and not l.error]

    def _worker_generar(numero: int, n: int, resultados: list, idx: int):
        """Fase 1: descarga imágenes y construye el ZIP en memoria. Solo genera, no envía."""
        _log(f"  → [#{numero}] Generando lote ({n} imágenes, descargando de picsum)...")
        try:
            zip_bytes, real_n = _generar_zip_en_memoria(n)
            resultados[idx] = (numero, zip_bytes, real_n)
            _log(f"  · [#{numero}] Lote listo en memoria ({real_n} imgs)")
        except Exception as e:
            _log(f"  [!] [#{numero}] Error generando: {e}")
            resultados[idx] = None

    def _worker_enviar(numero: int, zip_bytes: bytes, real_n: int):
        """Fase 2: envía un ZIP ya generado a la API. Solo envía, no genera."""
        id_lote = api_enviar_lote(base_url, zip_bytes, auth_headers)
        if id_lote:
            est = EstadoLote(id_lote=id_lote, numero=numero,
                             n_imagenes=real_n, t_envio=elapsed())
            with lotes_lock:
                lotes[id_lote] = est
            _log(f"  ✔ [#{numero}] Enviado → {id_lote[:8]}... ({real_n} imgs)")
        else:
            _log(f"  ✗ [#{numero}] La API rechazó el envío")

    def enviar_lotes_en_paralelo(cantidad: int):
        """
        Fase 1 — genera todos los ZIPs en paralelo y espera a que terminen todos.
        Fase 2 — envía todos los ZIPs listos en paralelo al mismo tiempo.
        La barrera entre fases garantiza que los envíos lleguen a la API
        simultáneamente sin importar el tamaño de cada lote.
        """
        nonlocal lote_numero
        lotes_info = []
        for _ in range(cantidad):
            lote_numero += 1
            lotes_info.append((lote_numero, random.randint(MIN_IMAGENES, MAX_IMAGENES)))

        # ── Fase 1: generar en paralelo ──────────────────────────────────────
        resultados = [None] * len(lotes_info)
        threads_gen = [
            threading.Thread(
                target=_worker_generar,
                args=(numero, n, resultados, idx),
                daemon=True,
            )
            for idx, (numero, n) in enumerate(lotes_info)
        ]
        for t in threads_gen:
            t.start()
        for t in threads_gen:
            t.join()

        # ── Barrera: todos los ZIPs están listos ─────────────────────────────
        listos = [r for r in resultados if r is not None]
        _log(f"  [=] {len(listos)}/{len(lotes_info)} lotes generados — enviando todos a la vez...")

        # ── Fase 2: enviar en paralelo ───────────────────────────────────────
        threads_env = [
            threading.Thread(
                target=_worker_enviar,
                args=(numero, zip_bytes, real_n),
                daemon=True,
            )
            for numero, zip_bytes, real_n in listos
        ]
        for t in threads_env:
            t.start()
        for t in threads_env:
            t.join()

    def poll_y_descargar():
        pendientes = [l for l in lotes.values() if l.t_descargado is None]
        if not pendientes:
            return
        for est in pendientes:
            info = api_estado(base_url, est.id_lote, auth_headers)
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
                ok, kb = api_descargar(base_url, est.id_lote, auth_headers)
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

        if lotes:
            _log(f"\n[t={t:.0f}s] ─── Consultando {len(lotes)} lote(s) ───")
            poll_y_descargar()

        time.sleep(POLL_INTERVAL)

    _log(f"\n[t={elapsed():.0f}s] ─── Tiempo agotado — consulta final ───")
    poll_y_descargar()

    generar_reporte_html(lotes, t_inicio, base_url)


# ─────────────────────── CONSULTA A LA BASE DE DATOS ─────────────────────────

def _consultar_datos_lotes(ids_lote: list) -> dict:
    if not _DB_OK or not ids_lote:
        return {}
    try:
        conn = psycopg2.connect(DB_URL)
        ph = ",".join(["%s"] * len(ids_lote))
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

            cur.execute(f"""
                SELECT i.id_imagen, i.id_lote, i.nombre_archivo, i.formato, i.resolucion,
                       et.nombre AS estado
                FROM imagen i
                JOIN estado_tarea et ON i.id_estado_tarea = et.id_estado_tarea
                WHERE i.id_lote IN ({ph})
                ORDER BY i.id_lote, i.nombre_archivo
            """, ids_lote)
            imagenes = [dict(r) for r in cur.fetchall()]

            cur.execute(f"""
                SELECT tp.id_tarea, tp.id_lote, tp.id_imagen, tp.id_nodo,
                       tp.fecha_asignacion, tp.intento, et.nombre AS estado
                FROM tarea_procesamiento tp
                JOIN estado_tarea et ON tp.id_estado_tarea = et.id_estado_tarea
                WHERE tp.id_lote IN ({ph})
            """, ids_lote)
            tareas = [dict(r) for r in cur.fetchall()]

            cur.execute(f"""
                SELECT rp.id_tarea, rp.fecha_generacion, rp.ruta_salida,
                       er.nombre AS estado_resultado
                FROM resultado_procesamiento rp
                JOIN estado_resultado er ON rp.id_estado_resultado = er.id_estado_resultado
                JOIN tarea_procesamiento tp ON rp.id_tarea = tp.id_tarea
                WHERE tp.id_lote IN ({ph})
            """, ids_lote)
            resultados = [dict(r) for r in cur.fetchall()]

            cur.execute(f"""
                SELECT id_log, id_imagen, id_nodo, tipo_evento,
                       fecha_evento, id_lote, id_tarea, descripcion
                FROM log_procesamiento
                WHERE id_lote IN ({ph})
                ORDER BY fecha_evento
            """, ids_lote)
            logs = [dict(r) for r in cur.fetchall()]

        conn.close()
        return {"imagenes": imagenes, "tareas": tareas, "resultados": resultados, "logs": logs}
    except Exception as e:
        _log(f"[!] No se pudo consultar la BD para el reporte: {e}")
        return {}


# ─────────────────────────── REPORTE HTML ────────────────────────────────────

_NODE_PALETTE = [
    "#6366f1", "#ec4899", "#14b8a6", "#f59e0b",
    "#ef4444", "#8b5cf6", "#06b6d4", "#84cc16",
    "#f97316", "#10b981",
]
_LOTE_PALETTE = [
    "#3b82f6", "#10b981", "#f97316", "#a855f7",
    "#14b8a6", "#f43f5e", "#eab308", "#64748b",
]


def _ts_to_epoch_ms(ts) -> Optional[int]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return int(ts.timestamp() * 1000)
    try:
        return int(datetime.fromisoformat(str(ts)).timestamp() * 1000)
    except Exception:
        return None


def _fmt_ts(ts) -> str:
    if ts is None:
        return "—"
    if isinstance(ts, datetime):
        return ts.strftime("%H:%M:%S.%f")[:12]
    try:
        return datetime.fromisoformat(str(ts)).strftime("%H:%M:%S.%f")[:12]
    except Exception:
        return str(ts)


def generar_reporte_html(lotes: dict, t_inicio: float, base_url: str):
    ids_lote = list(lotes.keys())
    db = _consultar_datos_lotes(ids_lote)

    # ── índices rápidos ────────────────────────────────────────────────────
    tareas_por_imagen   = {t["id_imagen"]: t for t in db.get("tareas", [])}
    resultados_por_tarea = {r["id_tarea"]: r for r in db.get("resultados", [])}
    logs_por_lote       = {}
    for lg in db.get("logs", []):
        logs_por_lote.setdefault(lg["id_lote"], []).append(lg)
    imagenes_por_lote   = {}
    for img in db.get("imagenes", []):
        imagenes_por_lote.setdefault(img["id_lote"], []).append(img)

    # ── nodos únicos con color ─────────────────────────────────────────────
    nodos_set = sorted({t["id_nodo"] for t in db.get("tareas", []) if t.get("id_nodo")})
    nodo_color = {n: _NODE_PALETTE[i % len(_NODE_PALETTE)] for i, n in enumerate(nodos_set)}

    # ── lote color ────────────────────────────────────────────────────────
    lotes_ordenados = sorted(lotes.values(), key=lambda x: x.t_envio)
    lote_color = {l.id_lote: _LOTE_PALETTE[i % len(_LOTE_PALETTE)]
                  for i, l in enumerate(lotes_ordenados)}

    # ── stats globales ────────────────────────────────────────────────────
    completados = [l for l in lotes.values() if l.t_completado is not None]
    con_error   = [l for l in lotes.values() if l.error]
    total_imgs  = sum(l.n_imagenes for l in lotes.values())
    imgs_proc   = sum(l.completadas for l in lotes.values())
    duraciones  = [l.t_completado - l.t_envio for l in completados if l.t_completado]
    prom_dur    = sum(duraciones) / len(duraciones) if duraciones else 0
    t_total     = time.time() - t_inicio
    inicio_str  = datetime.fromtimestamp(t_inicio).strftime("%Y-%m-%d %H:%M:%S")
    fin_str     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    t_inicio_ms = int(t_inicio * 1000)

    # ── datos Gantt ───────────────────────────────────────────────────────
    gantt_labels, gantt_data, gantt_colors, gantt_lote_colors, gantt_tooltips = [], [], [], [], []

    for est in lotes_ordenados:
        imgs = imagenes_por_lote.get(est.id_lote, [])
        for img in sorted(imgs, key=lambda x: x.get("nombre_archivo", "")):
            tarea = tareas_por_imagen.get(img["id_imagen"])
            if not tarea:
                continue
            resultado = resultados_por_tarea.get(tarea["id_tarea"])
            inicio_ms = _ts_to_epoch_ms(tarea.get("fecha_asignacion"))
            fin_ms    = _ts_to_epoch_ms(resultado.get("fecha_generacion")) if resultado else None
            if inicio_ms is None or fin_ms is None:
                continue

            inicio_s = (inicio_ms - t_inicio_ms) / 1000
            fin_s    = (fin_ms    - t_inicio_ms) / 1000
            dur_s    = fin_s - inicio_s
            nodo     = tarea.get("id_nodo", "?")
            color    = nodo_color.get(nodo, "#94a3b8")
            nombre   = img.get("nombre_archivo", img["id_imagen"][:8])
            estado_r = resultado.get("estado_resultado", "?") if resultado else tarea.get("estado", "?")

            # descripcion del log "procesando" para ver las transformaciones
            trans_desc = ""
            for lg in logs_por_lote.get(est.id_lote, []):
                if lg.get("id_imagen") == img["id_imagen"] and lg.get("tipo_evento") == "procesando":
                    trans_desc = lg.get("descripcion", "").replace("Transformaciones: ", "")
                    break

            gantt_labels.append(f"Lote #{est.numero} / {nombre}")
            gantt_data.append([round(inicio_s, 2), round(fin_s, 2)])
            gantt_colors.append(color)
            gantt_lote_colors.append(lote_color.get(est.id_lote, "#64748b"))
            gantt_tooltips.append({
                "lote": f"#{est.numero} ({est.id_lote[:8]}...)",
                "imagen": nombre,
                "nodo": nodo,
                "inicio": _fmt_ts(tarea.get("fecha_asignacion")),
                "fin": _fmt_ts(resultado.get("fecha_generacion")) if resultado else "—",
                "duracion": f"{dur_s:.2f}s",
                "estado": estado_r,
                "transformaciones": trans_desc or "—",
            })

    # ── actividad por nodo ────────────────────────────────────────────────
    nodo_stats = {}
    for t in db.get("tareas", []):
        nodo = t.get("id_nodo", "?")
        nodo_stats.setdefault(nodo, {"total": 0, "completadas": 0, "duraciones": []})
        nodo_stats[nodo]["total"] += 1
        r = resultados_por_tarea.get(t["id_tarea"])
        if r and r.get("estado_resultado") == "generado":
            nodo_stats[nodo]["completadas"] += 1
            ini = _ts_to_epoch_ms(t.get("fecha_asignacion"))
            fin = _ts_to_epoch_ms(r.get("fecha_generacion"))
            if ini and fin:
                nodo_stats[nodo]["duraciones"].append((fin - ini) / 1000)

    # ── HTML ──────────────────────────────────────────────────────────────
    gantt_labels_js  = json.dumps(gantt_labels,     ensure_ascii=False)
    gantt_data_js    = json.dumps(gantt_data)
    gantt_colors_js  = json.dumps(gantt_colors)
    gantt_tooltips_js = json.dumps(gantt_tooltips,  ensure_ascii=False)

    # secciones por lote
    lote_sections_html = ""
    for est in lotes_ordenados:
        col   = lote_color.get(est.id_lote, "#64748b")
        imgs  = imagenes_por_lote.get(est.id_lote, [])
        logs  = logs_por_lote.get(est.id_lote, [])

        if est.t_completado:
            dur_lote = est.t_completado - est.t_envio
            badge = f'<span class="badge badge-ok">completado en {dur_lote:.1f}s</span>'
        elif est.error:
            badge = '<span class="badge badge-err">error</span>'
        else:
            badge = f'<span class="badge badge-pend">incompleto {est.progreso:.0f}%</span>'

        # tabla de imágenes
        rows = ""
        for img in sorted(imgs, key=lambda x: x.get("nombre_archivo", "")):
            tarea   = tareas_por_imagen.get(img["id_imagen"])
            result  = resultados_por_tarea.get(tarea["id_tarea"]) if tarea else None
            nodo    = tarea.get("id_nodo", "—") if tarea else "—"
            nc      = nodo_color.get(nodo, "#94a3b8")
            ini_str = _fmt_ts(tarea.get("fecha_asignacion")) if tarea else "—"
            fin_str = _fmt_ts(result.get("fecha_generacion")) if result else "—"
            ini_ms  = _ts_to_epoch_ms(tarea.get("fecha_asignacion")) if tarea else None
            fin_ms2 = _ts_to_epoch_ms(result.get("fecha_generacion")) if result else None
            dur_img = f"{(fin_ms2 - ini_ms)/1000:.2f}s" if ini_ms and fin_ms2 else "—"
            estado_img = result.get("estado_resultado", tarea.get("estado", "?") if tarea else "?") if result else (tarea.get("estado", "?") if tarea else "?")
            estado_cls = "ok" if estado_img == "generado" else ("err" if "error" in estado_img else "pend")

            trans_desc = ""
            for lg in logs:
                if lg.get("id_imagen") == img["id_imagen"] and lg.get("tipo_evento") == "procesando":
                    trans_desc = lg.get("descripcion", "").replace("Transformaciones: ", "")
                    break

            rows += f"""
            <tr>
              <td><code>{img.get('nombre_archivo','—')}</code></td>
              <td><span class="node-pill" style="background:{nc}22;color:{nc};border:1px solid {nc}44">{nodo.split('-')[0] if nodo != '—' else '—'}<br><small style="opacity:.6;font-size:10px">{nodo[-6:] if nodo != '—' else ''}</small></span></td>
              <td class="mono">{ini_str}</td>
              <td class="mono">{fin_str}</td>
              <td class="mono">{dur_img}</td>
              <td><span class="badge badge-{estado_cls}">{estado_img}</span></td>
              <td class="trans-cell"><small>{trans_desc}</small></td>
            </tr>"""

        # timeline de logs del lote
        timeline_html = ""
        for lg in logs:
            ev   = lg.get("tipo_evento", "")
            ev_cls = {"procesando": "ev-proc", "completado": "ev-ok", "error": "ev-err"}.get(ev, "ev-info")
            icon = {"procesando": "⚙", "completado": "✓", "error": "✗"}.get(ev, "·")
            nodo_lg = lg.get("id_nodo", "")
            nc_lg   = nodo_color.get(nodo_lg, "#94a3b8")
            desc    = lg.get("descripcion") or ""
            img_name = ""
            for img in imgs:
                if img["id_imagen"] == lg.get("id_imagen"):
                    img_name = img.get("nombre_archivo", "")
                    break
            timeline_html += f"""
            <div class="tl-item {ev_cls}">
              <div class="tl-dot">{icon}</div>
              <div class="tl-body">
                <span class="tl-time">{_fmt_ts(lg.get('fecha_evento'))}</span>
                <span class="tl-img">{img_name}</span>
                <span class="node-pill sm" style="background:{nc_lg}22;color:{nc_lg};border:1px solid {nc_lg}44">{nodo_lg[-12:] if nodo_lg else '—'}</span>
                <div class="tl-desc">{desc}</div>
              </div>
            </div>"""

        lote_sections_html += f"""
        <div class="card lote-card" style="border-left:4px solid {col}">
          <div class="lote-header" onclick="toggle('lote-{est.numero}')">
            <span class="lote-num" style="color:{col}">Lote #{est.numero}</span>
            <code class="lote-id">{est.id_lote[:8]}...</code>
            {badge}
            <span class="lote-meta">{est.completadas}/{est.n_imagenes} imágenes &nbsp;·&nbsp; enviado {datetime.fromtimestamp(t_inicio + est.t_envio).strftime('%H:%M:%S')}</span>
            <span class="toggle-icon">▾</span>
          </div>
          <div id="lote-{est.numero}" class="lote-body">
            <div class="tabs">
              <button class="tab active" onclick="showTab(this,'tab-tbl-{est.numero}','tab-tl-{est.numero}')">Imágenes</button>
              <button class="tab" onclick="showTab(this,'tab-tl-{est.numero}','tab-tbl-{est.numero}')">Log timeline</button>
            </div>
            <div id="tab-tbl-{est.numero}">
              <div class="table-wrap">
                <table>
                  <thead><tr><th>Imagen</th><th>Nodo</th><th>Inicio</th><th>Fin</th><th>Duración</th><th>Estado</th><th>Transformaciones</th></tr></thead>
                  <tbody>{rows}</tbody>
                </table>
              </div>
            </div>
            <div id="tab-tl-{est.numero}" style="display:none">
              <div class="timeline">{timeline_html}</div>
            </div>
          </div>
        </div>"""

    # sección de nodos
    nodos_rows = ""
    for nodo, stats in sorted(nodo_stats.items()):
        nc    = nodo_color.get(nodo, "#94a3b8")
        durs  = stats["duraciones"]
        prom  = sum(durs)/len(durs) if durs else 0
        mn    = min(durs) if durs else 0
        mx    = max(durs) if durs else 0
        nodos_rows += f"""
        <tr>
          <td><span class="node-pill" style="background:{nc}22;color:{nc};border:1px solid {nc}44">{nodo}</span></td>
          <td style="text-align:center">{stats['total']}</td>
          <td style="text-align:center">{stats['completadas']}</td>
          <td style="text-align:center">{prom:.2f}s</td>
          <td style="text-align:center">{mn:.2f}s</td>
          <td style="text-align:center">{mx:.2f}s</td>
        </tr>"""

    nodos_leyenda = "".join(
        f'<span class="node-pill" style="background:{nc}22;color:{nc};border:1px solid {nc}44;margin:4px">{n}</span>'
        for n, nc in nodo_color.items()
    )

    # nodos barchart data
    nodos_bar_labels = json.dumps([n for n in nodo_stats], ensure_ascii=False)
    nodos_bar_data   = json.dumps([nodo_stats[n]["completadas"] for n in nodo_stats])
    nodos_bar_colors = json.dumps([nodo_color.get(n, "#94a3b8") for n in nodo_stats])

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stress Test — {inicio_str}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0f172a;color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;font-size:14px;line-height:1.6}}
h1{{font-size:1.5rem;font-weight:700;color:#f1f5f9}}
h2{{font-size:1.1rem;font-weight:600;color:#cbd5e1;margin-bottom:12px}}
a{{color:#6366f1}}
.page{{max-width:1400px;margin:0 auto;padding:24px 16px}}
.header{{background:linear-gradient(135deg,#1e1b4b,#1e293b);border-radius:16px;padding:24px 28px;margin-bottom:24px;border:1px solid #312e81}}
.header h1{{margin-bottom:4px}}
.header .sub{{color:#94a3b8;font-size:13px}}
.stats-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:24px}}
.stat-card{{background:#1e293b;border-radius:12px;padding:16px 20px;border:1px solid #334155}}
.stat-val{{font-size:2rem;font-weight:700;line-height:1}}
.stat-lbl{{color:#64748b;font-size:12px;margin-top:4px}}
.card{{background:#1e293b;border-radius:12px;padding:20px;margin-bottom:16px;border:1px solid #334155}}
.chart-wrap{{position:relative;width:100%;overflow-x:auto}}
table{{width:100%;border-collapse:collapse}}
thead tr{{background:#0f172a}}
th{{padding:8px 12px;text-align:left;color:#64748b;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #334155}}
td{{padding:8px 12px;border-bottom:1px solid #1e293b;vertical-align:top}}
tr:hover td{{background:#243044}}
.table-wrap{{overflow-x:auto;border-radius:8px;border:1px solid #334155}}
.badge{{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}}
.badge-ok{{background:#14532d44;color:#4ade80;border:1px solid #14532d}}
.badge-err{{background:#7f1d1d44;color:#f87171;border:1px solid #7f1d1d}}
.badge-pend{{background:#78350f44;color:#fbbf24;border:1px solid #78350f}}
.node-pill{{display:inline-block;padding:3px 8px;border-radius:6px;font-size:11px;font-weight:600;line-height:1.4}}
.node-pill.sm{{font-size:10px;padding:2px 6px}}
.mono{{font-family:'Cascadia Code','Fira Code',monospace;font-size:12px}}
.lote-card{{cursor:default}}
.lote-header{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;cursor:pointer;user-select:none;padding-bottom:4px}}
.lote-num{{font-size:1.1rem;font-weight:700}}
.lote-id{{color:#64748b;font-size:12px;background:#0f172a;padding:2px 6px;border-radius:4px}}
.lote-meta{{color:#64748b;font-size:12px;margin-left:auto}}
.toggle-icon{{color:#475569;font-size:16px;transition:.2s}}
.lote-body{{margin-top:16px}}
.tabs{{display:flex;gap:8px;margin-bottom:12px;border-bottom:1px solid #334155;padding-bottom:8px}}
.tab{{background:none;border:none;color:#64748b;padding:4px 12px;border-radius:6px;cursor:pointer;font-size:13px}}
.tab.active,.tab:hover{{background:#334155;color:#e2e8f0}}
.trans-cell{{max-width:280px;word-break:break-word;color:#94a3b8}}
.timeline{{display:flex;flex-direction:column;gap:0}}
.tl-item{{display:flex;gap:12px;padding:8px 0;border-left:2px solid #334155;padding-left:16px;position:relative}}
.tl-dot{{position:absolute;left:-9px;width:16px;height:16px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700}}
.ev-ok .tl-dot{{background:#14532d;color:#4ade80;border:2px solid #4ade80}}
.ev-err .tl-dot{{background:#7f1d1d;color:#f87171;border:2px solid #f87171}}
.ev-proc .tl-dot{{background:#1e1b4b;color:#818cf8;border:2px solid #818cf8}}
.ev-info .tl-dot{{background:#1e293b;color:#94a3b8;border:2px solid #475569}}
.tl-body{{flex:1;min-width:0}}
.tl-time{{font-family:monospace;font-size:11px;color:#64748b;margin-right:8px}}
.tl-img{{font-weight:600;font-size:12px;margin-right:8px}}
.tl-desc{{color:#94a3b8;font-size:11px;margin-top:2px;word-break:break-word}}
.section-title{{font-size:1rem;font-weight:700;color:#cbd5e1;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid #334155}}
.leyenda{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px}}
@media(max-width:600px){{.stats-grid{{grid-template-columns:1fr 1fr}}.lote-meta{{display:none}}}}
</style>
</head>
<body>
<div class="page">

  <div class="header">
    <h1>Reporte de Prueba de Carga</h1>
    <div class="sub">API: {base_url} &nbsp;·&nbsp; {inicio_str} → {fin_str} &nbsp;·&nbsp; Duración: {t_total:.1f}s</div>
  </div>

  <div class="stats-grid">
    <div class="stat-card"><div class="stat-val" style="color:#6366f1">{len(lotes)}</div><div class="stat-lbl">Lotes enviados</div></div>
    <div class="stat-card"><div class="stat-val" style="color:#4ade80">{len(completados)}</div><div class="stat-lbl">Completados</div></div>
    <div class="stat-card"><div class="stat-val" style="color:#f87171">{len(con_error)}</div><div class="stat-lbl">Con error</div></div>
    <div class="stat-card"><div class="stat-val" style="color:#38bdf8">{total_imgs}</div><div class="stat-lbl">Imágenes totales</div></div>
    <div class="stat-card"><div class="stat-val" style="color:#4ade80">{imgs_proc}</div><div class="stat-lbl">Imágenes procesadas</div></div>
    <div class="stat-card"><div class="stat-val" style="color:#fbbf24">{prom_dur:.1f}s</div><div class="stat-lbl">Tiempo prom. por lote</div></div>
    <div class="stat-card"><div class="stat-val" style="color:#a78bfa">{len(nodos_set)}</div><div class="stat-lbl">Nodos activos</div></div>
    <div class="stat-card"><div class="stat-val" style="color:#34d399">{min(duraciones):.1f}s / {max(duraciones):.1f}s</div><div class="stat-lbl">Min / Max lote</div></div>
  </div>

  <!-- GANTT -->
  <div class="card">
    <h2>Timeline de procesamiento por imagen</h2>
    <div class="leyenda" id="leyenda-nodos">{nodos_leyenda}</div>
    <div class="chart-wrap" style="height:{max(300, len(gantt_labels) * 22 + 60)}px">
      <canvas id="ganttChart"></canvas>
    </div>
  </div>

  <!-- ACTIVIDAD POR NODO -->
  <div class="card">
    <div class="section-title">Actividad por nodo</div>
    <div style="display:grid;grid-template-columns:1fr 320px;gap:20px;align-items:start">
      <div class="table-wrap">
        <table>
          <thead><tr><th>Nodo</th><th>Tareas asignadas</th><th>Completadas</th><th>Prom. duración</th><th>Mínimo</th><th>Máximo</th></tr></thead>
          <tbody>{nodos_rows}</tbody>
        </table>
      </div>
      <div style="height:260px"><canvas id="nodosChart"></canvas></div>
    </div>
  </div>

  <!-- POR LOTE -->
  <div class="section-title" style="margin-top:8px">Detalle por lote</div>
  {lote_sections_html}

</div>

<script>
const T0_MS = {t_inicio_ms};

// ── Gantt ──────────────────────────────────────────────────────────────────
const ganttLabels   = {gantt_labels_js};
const ganttData     = {gantt_data_js};
const ganttColors   = {gantt_colors_js};
const ganttTooltips = {gantt_tooltips_js};

function fmtSecs(s) {{
  const d = new Date(T0_MS + s * 1000);
  return d.toLocaleTimeString('es-CO', {{hour12:false}}) + '.' + String(d.getMilliseconds()).padStart(3,'0');
}}

new Chart(document.getElementById('ganttChart'), {{
  type: 'bar',
  data: {{
    labels: ganttLabels,
    datasets: [{{
      label: 'Procesamiento',
      data: ganttData,
      backgroundColor: ganttColors,
      borderColor: ganttColors.map(c => c + 'cc'),
      borderWidth: 1,
      borderRadius: 3,
      borderSkipped: false,
    }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          title: ctx => ganttTooltips[ctx[0].dataIndex]?.imagen || '',
          label: ctx => {{
            const t = ganttTooltips[ctx.dataIndex];
            if (!t) return '';
            return [
              ` Lote: ${{t.lote}}`,
              ` Nodo: ${{t.nodo}}`,
              ` Inicio: ${{t.inicio}}`,
              ` Fin:    ${{t.fin}}`,
              ` Duración: ${{t.duracion}}`,
              ` Estado: ${{t.estado}}`,
              ` Transforms: ${{t.transformaciones}}`,
            ];
          }},
        }},
        backgroundColor: '#1e293b',
        borderColor: '#475569',
        borderWidth: 1,
        titleColor: '#f1f5f9',
        bodyColor: '#94a3b8',
        padding: 12,
      }},
    }},
    scales: {{
      x: {{
        grid: {{ color: '#1e293b' }},
        ticks: {{
          color: '#64748b',
          callback: v => fmtSecs(v),
          maxRotation: 0,
        }},
        title: {{ display: true, text: 'Tiempo de ejecución', color: '#475569' }},
      }},
      y: {{
        grid: {{ color: '#1e293b' }},
        ticks: {{ color: '#94a3b8', font: {{ size: 11 }} }},
      }},
    }},
  }},
}});

// ── Nodos bar ──────────────────────────────────────────────────────────────
new Chart(document.getElementById('nodosChart'), {{
  type: 'doughnut',
  data: {{
    labels: {nodos_bar_labels},
    datasets: [{{
      data: {nodos_bar_data},
      backgroundColor: {nodos_bar_colors},
      borderColor: '#0f172a',
      borderWidth: 3,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{
        position: 'bottom',
        labels: {{ color: '#94a3b8', font: {{ size: 11 }} }},
      }},
      tooltip: {{
        backgroundColor: '#1e293b',
        borderColor: '#475569',
        borderWidth: 1,
        titleColor: '#f1f5f9',
        bodyColor: '#94a3b8',
      }},
    }},
  }},
}});

// ── UI helpers ─────────────────────────────────────────────────────────────
function toggle(id) {{
  const el = document.getElementById(id);
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}}
function showTab(btn, showId, hideId) {{
  document.getElementById(showId).style.display = 'block';
  document.getElementById(hideId).style.display = 'none';
  btn.closest('.tabs').querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}}
</script>
</body>
</html>"""

    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta   = Path(__file__).parent / f"reporte_{ts}.html"
    ruta.write_text(html, encoding="utf-8")
    _log(f"\n  Reporte HTML generado: {ruta.name}")
    _log(f"  Abre el archivo en tu navegador para verlo.")


# ─────────────────────────── ENTRY POINT ─────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prueba de carga del sistema de procesamiento de imágenes"
    )
    parser.add_argument(
        "--url", default=API_BASE,
        help=f"URL base de la API (default: {API_BASE})"
    )
    parser.add_argument(
        "--db-url", default=None,
        help="Cadena de conexión PostgreSQL (ej: postgresql://admin:admin123@192.168.40.12:5432/image_processing)"
    )
    args = parser.parse_args()
    if args.db_url:
        globals()["DB_URL"] = args.db_url
    else:
        print(f"[!] AVISO: no se pasó --db-url. Usando DB_URL={DB_URL}")
        print(f"    Si la BD está en otra VM, pasa: --db-url postgresql://admin:admin123@<IP-VM-DB>:5432/image_processing\n")
    main(args.url)
