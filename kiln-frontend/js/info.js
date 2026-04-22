import { api, toast, escapeHtml } from "./api.js";
import { mountTopbar } from "./topbar.js";

mountTopbar("info");

const wrap = document.getElementById("info-content");

try {
  const data = await api.info();
  render(data);
} catch (err) {
  wrap.innerHTML = `<div class="card text-error">No se pudo cargar /info — ${escapeHtml(err.message)}</div>`;
  toast({ title: "Error al cargar docs", body: err.message, variant: "error" });
}

function render(data) {
  const transforms = data.transformaciones || [];
  const formatos = data.formatos_entrada_permitidos || [];
  const orden = data.orden_recomendado || [];
  const flujo = data.flujo || [];
  const ejemplo = data.ejemplo_json_completo || {};

  wrap.innerHTML = `
    <div class="grid-gap" style="grid-template-columns: 1.4fr 1fr; display: grid; gap: 24px;">
      <div class="card">
        <h3 class="card-title mt-0">Las 11 transformaciones</h3>
        <p class="card-subtitle" style="margin-bottom: 16px;">
          Formatos de entrada aceptados: ${formatos.map((f) => `<span class="chip mono">${escapeHtml(f)}</span>`).join(" ")}
          · Salida por defecto: <span class="chip mono">${escapeHtml(data.formato_salida_defecto || "")}</span>
        </p>
        <div class="info-grid">
          ${transforms.map(renderTransform).join("")}
        </div>
      </div>

      <div>
        <div class="card">
          <h3 class="card-title mt-0">Orden recomendado</h3>
          <p class="card-subtitle" style="margin-bottom: 12px;">
            Kiln ordena automáticamente las transformaciones en este orden al enviar el lote.
          </p>
          <ol class="mono" style="padding-left: 20px; color: var(--text-muted); line-height: 1.8;">
            ${orden.map((o) => `<li>${escapeHtml(o)}</li>`).join("")}
          </ol>
        </div>

        <div class="card mt-16">
          <h3 class="card-title mt-0">Flujo del sistema</h3>
          <ol style="padding-left: 20px; color: var(--text-muted); line-height: 1.7;">
            ${flujo.map((f) => `<li>${renderFlujoItem(f)}</li>`).join("")}
          </ol>
        </div>

        <div class="card mt-16">
          <h3 class="card-title mt-0">Ejemplo de JSON</h3>
          <div class="json-preview mono">${colorize(JSON.stringify(ejemplo, null, 2))}</div>
        </div>
      </div>
    </div>
  `;
}

function renderTransform(t) {
  const params = t.parametros && Object.keys(t.parametros).length
    ? Object.entries(t.parametros).map(([k, v]) => `<div><b>${escapeHtml(k)}</b> — ${escapeHtml(v)}</div>`).join("")
    : `<div class="text-dim">sin parámetros</div>`;
  return `
    <div class="info-item">
      <h3>${escapeHtml(t.tipo)}</h3>
      <p>${escapeHtml(t.descripcion || "")}</p>
      <div class="info-params">${params}</div>
    </div>
  `;
}

function renderFlujoItem(s) {
  return escapeHtml(s).replace(/(GET|POST)\s(\/[^\s—]+)/g, '<span class="mono text-xs" style="color: var(--accent);">$1 $2</span>');
}

function colorize(str) {
  return escapeHtml(str)
    .replace(/&quot;([^&]+?)&quot;(\s*:)/g, '<span class="k">&quot;$1&quot;</span>$2')
    .replace(/:\s*&quot;([^&]*?)&quot;/g, ': <span class="s">&quot;$1&quot;</span>')
    .replace(/:\s*(-?\d+\.?\d*)/g, ': <span class="n">$1</span>');
}
