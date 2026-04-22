import { api, toast, escapeHtml } from "./api.js";
import { mountTopbar } from "./topbar.js";

mountTopbar("lotes");

const params = new URLSearchParams(location.search);
const id = params.get("id");

const loteId = document.getElementById("lote-id");
const loteEstado = document.getElementById("lote-estado");
const statTotal = document.getElementById("stat-total");
const statDone = document.getElementById("stat-done");
const statPct = document.getElementById("stat-pct");
const progressFill = document.getElementById("progress-fill");
const lastUpdate = document.getElementById("lote-last-update");
const btnRefresh = document.getElementById("btn-refresh");
const btnDownload = document.getElementById("btn-download");
const nombresCard = document.getElementById("lote-nombres-card");
const nombresEl = document.getElementById("lote-nombres");

if (!id) {
  loteId.textContent = "sin id";
  loteEstado.innerHTML = `<span class="badge badge-error">No se proveyó un id_lote</span>`;
  btnRefresh.disabled = true;
} else {
  loteId.textContent = id;
  const localEntry = api.getLotes().find((l) => l.id_lote === id);
  if (localEntry?.nombres?.length) {
    nombresCard.style.display = "";
    nombresEl.innerHTML = localEntry.nombres
      .map((n) => `<div>${escapeHtml(n)}</div>`)
      .join("");
  }
  start();
}

let pollTimer = null;
let pollInterval = 2000;

btnRefresh.addEventListener("click", () => fetchStatus(true));
btnDownload.addEventListener("click", onDownload);

async function start() {
  await fetchStatus();
}

async function fetchStatus(isManual = false) {
  if (isManual) {
    btnRefresh.innerHTML = '<span class="spinner"></span> Refrescando…';
    btnRefresh.disabled = true;
  }
  try {
    const data = await api.estadoLote(id);
    applyStatus(data);
  } catch (err) {
    loteEstado.innerHTML = `<span class="badge badge-error">${escapeHtml(err.message)}</span>`;
  } finally {
    if (isManual) {
      btnRefresh.innerHTML = "Refrescar ahora";
      btnRefresh.disabled = false;
    }
    lastUpdate.textContent = `Última actualización: ${new Date().toLocaleTimeString()}`;
  }
}

function applyStatus(data) {
  statTotal.textContent = data.total ?? "—";
  statDone.textContent = data.completadas ?? "—";
  const pct = Number(data.progreso) || 0;
  statPct.innerHTML = `${pct.toFixed(1)}<span class="sub">%</span>`;
  progressFill.style.width = `${pct}%`;
  loteEstado.innerHTML = estadoBadge(data.estado);

  const completo = data.estado === "completado";
  btnDownload.disabled = !completo;

  // Programar siguiente poll si aún no terminó
  if (pollTimer) clearTimeout(pollTimer);
  if (data.estado === "procesando" || data.estado === "pendiente") {
    pollTimer = setTimeout(() => fetchStatus(), pollInterval);
  }
}

async function onDownload() {
  btnDownload.disabled = true;
  const label = btnDownload.innerHTML;
  btnDownload.innerHTML = '<span class="spinner"></span> Descargando…';
  try {
    await api.descargarResultado(id);
    toast({ title: "Descarga iniciada", body: "ZIP con las imágenes procesadas", variant: "success" });
  } catch (err) {
    toast({ title: "No se pudo descargar", body: err.message, variant: "error", ttl: 6000 });
  } finally {
    btnDownload.disabled = false;
    btnDownload.innerHTML = label;
  }
}

function estadoBadge(estado) {
  const variant =
    estado === "completado" ? "success" :
    estado === "procesando" ? "warning" :
    estado === "error" ? "error" :
    estado === "pendiente" ? "info" :
    "";
  return `<span class="badge badge-${variant}">${escapeHtml(estado || "—")}</span>`;
}
