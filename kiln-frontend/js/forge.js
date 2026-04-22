// ============================================================
// Kiln — Forge page logic
// Manages: image uploads, global/individual transformations,
// JSON preview, and batch submission to POST /lote.
// ============================================================
import { api, toast, escapeHtml } from "./api.js";
import { mountTopbar } from "./topbar.js";
import {
  TRANSFORMS,
  TRANSFORM_TYPES,
  sortTransformations,
  validateTransformation,
  normalizeTransformation,
} from "./transformations.js";

mountTopbar("forge");

// ---------- State ----------
/** @type {{id:string, file:File, url:string, transformations: any[]}[]} */
let images = [];
/** @type {any[]} */
let globalTransformations = [];
let activeScope = "global"; // 'global' | 'individual'
let activeImageId = null; // id of selected image (for individual scope)

// ---------- DOM refs ----------
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const imgGrid = document.getElementById("img-grid");
const imgCounter = document.getElementById("img-counter");
const transformSelect = document.getElementById("transform-select");
const btnAddTransform = document.getElementById("btn-add-transform");
const transformList = document.getElementById("transform-list");
const jsonPreview = document.getElementById("json-preview");
const activeImgName = document.getElementById("active-img-name");
const scopeTabs = document.querySelectorAll(".scope-tab");
const scopeHelp = document.getElementById("scope-help");
const countGlobal = document.getElementById("count-global");
const countIndividual = document.getElementById("count-individual");
const tabIndividual = document.getElementById("tab-individual");
const btnForge = document.getElementById("btn-forge");
const btnReset = document.getElementById("btn-reset");

// ---------- Populate transform dropdown ----------
for (const tipo of TRANSFORM_TYPES) {
  const opt = document.createElement("option");
  opt.value = tipo;
  opt.textContent = `${TRANSFORMS[tipo].label}  —  ${TRANSFORMS[tipo].description}`;
  transformSelect.appendChild(opt);
}

// ---------- Dropzone ----------
fileInput.addEventListener("change", (e) => addFiles(e.target.files));
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("drag-over");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag-over"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("drag-over");
  addFiles(e.dataTransfer.files);
});

function addFiles(fileList) {
  const ALLOWED_EXT = [".jpg", ".jpeg", ".png", ".tif", ".tiff"];
  const ALLOWED_MIME = ["image/jpeg", "image/png", "image/tiff"];
  let rejected = 0;
  let duplicates = 0;

  const existingNames = new Set(images.map((i) => i.file.name));

  for (const f of Array.from(fileList)) {
    const ext = "." + f.name.split(".").pop().toLowerCase();
    const mimeOk = ALLOWED_MIME.includes(f.type);
    const extOk = ALLOWED_EXT.includes(ext);
    if (!mimeOk && !extOk) {
      rejected++;
      continue;
    }
    if (existingNames.has(f.name)) {
      duplicates++;
      continue;
    }
    const id = crypto.randomUUID();
    images.push({
      id,
      file: f,
      url: URL.createObjectURL(f),
      transformations: [],
    });
    existingNames.add(f.name);
  }

  if (rejected) toast({ title: `${rejected} archivo(s) rechazados`, body: "Solo JPEG, PNG o TIFF", variant: "warning" });
  if (duplicates) toast({ title: `${duplicates} duplicado(s) omitido(s)`, variant: "warning" });

  renderImages();
  updatePreview();
  fileInput.value = "";
}

function removeImage(id) {
  const img = images.find((i) => i.id === id);
  if (img) URL.revokeObjectURL(img.url);
  images = images.filter((i) => i.id !== id);
  if (activeImageId === id) {
    activeImageId = images[0]?.id || null;
    if (!activeImageId) switchScope("global");
  }
  renderImages();
  renderTransformList();
  updatePreview();
}

function renderImages() {
  imgCounter.textContent = images.length;
  tabIndividual.disabled = images.length === 0;
  if (images.length === 0) {
    imgGrid.innerHTML = "";
    return;
  }
  imgGrid.innerHTML = images
    .map(
      (img) => `
      <div class="img-tile ${img.id === activeImageId ? "selected" : ""}" data-id="${img.id}">
        <img src="${img.url}" alt="${escapeHtml(img.file.name)}" loading="lazy"/>
        <button class="img-tile-remove" data-remove="${img.id}" title="Quitar del lote">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
        <div class="img-tile-meta">
          <span title="${escapeHtml(img.file.name)}">${truncate(img.file.name, 14)}</span>
          ${img.transformations.length ? `<span class="img-tile-count">+${img.transformations.length}</span>` : ""}
        </div>
      </div>`
    )
    .join("");

  imgGrid.querySelectorAll(".img-tile").forEach((el) => {
    el.addEventListener("click", (e) => {
      if (e.target.closest("[data-remove]")) return;
      const id = el.dataset.id;
      activeImageId = id;
      switchScope("individual");
      renderImages();
      renderTransformList();
      updatePreview();
    });
  });
  imgGrid.querySelectorAll("[data-remove]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      removeImage(btn.dataset.remove);
    });
  });
}

function truncate(s, n) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

// ---------- Scope tabs ----------
scopeTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    if (tab.disabled) return;
    switchScope(tab.dataset.scope);
  });
});

function switchScope(scope) {
  if (scope === "individual" && !activeImageId) {
    activeImageId = images[0]?.id || null;
    if (!activeImageId) return;
  }
  activeScope = scope;
  scopeTabs.forEach((t) => t.classList.toggle("active", t.dataset.scope === scope));
  scopeHelp.textContent =
    scope === "global"
      ? "Estas transformaciones se aplican a todas las imágenes del lote."
      : "Estas transformaciones se añaden SOLO a la imagen seleccionada, después de las globales.";
  renderImages();
  renderTransformList();
  updatePreview();
}

// ---------- Transformation list ----------
btnAddTransform.addEventListener("click", () => {
  const tipo = transformSelect.value;
  const spec = TRANSFORMS[tipo];
  const current = getActiveList();
  if (tipo === "convert" && current.some((t) => t.tipo === "convert")) {
    toast({ title: "Solo se permite un 'convert' por conjunto", variant: "warning" });
    return;
  }
  current.push({ tipo, ...structuredClone(spec.defaults) });
  persistActiveList(sortTransformations(current));
  renderTransformList();
  renderImages();
  updatePreview();
});

function getActiveList() {
  if (activeScope === "global") return [...globalTransformations];
  const img = images.find((i) => i.id === activeImageId);
  return img ? [...img.transformations] : [];
}

function persistActiveList(list) {
  if (activeScope === "global") {
    globalTransformations = list;
  } else {
    const img = images.find((i) => i.id === activeImageId);
    if (img) img.transformations = list;
  }
  countGlobal.textContent = globalTransformations.length;
  const active = images.find((i) => i.id === activeImageId);
  countIndividual.textContent = active ? active.transformations.length : 0;
}

function renderTransformList() {
  const list = getActiveList();
  countGlobal.textContent = globalTransformations.length;
  const active = images.find((i) => i.id === activeImageId);
  countIndividual.textContent = active ? active.transformations.length : 0;

  if (list.length === 0) {
    transformList.innerHTML = `<div class="empty-state">
      Aún no hay transformaciones ${activeScope === "global" ? "globales" : "para esta imagen"}.
      <br/>Añade una desde el selector de arriba.
    </div>`;
    return;
  }

  transformList.innerHTML = list
    .map((t, idx) => renderTransformItem(t, idx, list.length))
    .join("");

  // Bind field changes
  transformList.querySelectorAll("[data-field]").forEach((inp) => {
    inp.addEventListener("input", onFieldChange);
    inp.addEventListener("change", onFieldChange);
  });
  // Bind remove / move
  transformList.querySelectorAll("[data-remove-idx]").forEach((b) => {
    b.addEventListener("click", () => {
      const idx = parseInt(b.dataset.removeIdx, 10);
      const cur = getActiveList();
      cur.splice(idx, 1);
      persistActiveList(cur);
      renderTransformList();
      renderImages();
      updatePreview();
    });
  });
  transformList.querySelectorAll("[data-move]").forEach((b) => {
    b.addEventListener("click", () => {
      const idx = parseInt(b.dataset.idx, 10);
      const dir = b.dataset.move === "up" ? -1 : 1;
      const cur = getActiveList();
      const target = idx + dir;
      if (target < 0 || target >= cur.length) return;
      [cur[idx], cur[target]] = [cur[target], cur[idx]];
      persistActiveList(cur);
      renderTransformList();
      updatePreview();
    });
  });
}

function onFieldChange(e) {
  const inp = e.target;
  const idx = parseInt(inp.dataset.idx, 10);
  const key = inp.dataset.field;
  const cur = getActiveList();
  if (!cur[idx]) return;
  let v = inp.value;
  const spec = TRANSFORMS[cur[idx].tipo].fields.find((f) => f.key === key);
  if (spec && (spec.type === "int" || spec.type === "float")) {
    v = v === "" ? "" : Number(v);
  }
  cur[idx][key] = v;
  persistActiveList(cur);
  updatePreview();
}

function renderTransformItem(t, idx, total) {
  const spec = TRANSFORMS[t.tipo];
  const fieldsHtml = spec.fields.length
    ? `<div class="field-inline">${spec.fields.map((f) => renderField(f, t, idx)).join("")}</div>`
    : `<div class="text-xs text-dim">Sin parámetros.</div>`;

  return `
    <div class="transform-item">
      <div class="transform-item-head">
        <div class="transform-item-head-left">
          <span class="transform-tag">${escapeHtml(t.tipo)}</span>
          <span class="transform-order">paso ${idx + 1} / ${total}</span>
        </div>
        <div class="transform-actions">
          <button class="icon-btn" data-move="up" data-idx="${idx}" ${idx === 0 ? "disabled" : ""} title="Subir">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg>
          </button>
          <button class="icon-btn" data-move="down" data-idx="${idx}" ${idx === total - 1 ? "disabled" : ""} title="Bajar">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <button class="icon-btn danger" data-remove-idx="${idx}" title="Quitar">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6"/></svg>
          </button>
        </div>
      </div>
      ${fieldsHtml}
    </div>
  `;
}

function renderField(f, t, idx) {
  const v = t[f.key] ?? "";
  if (f.type === "select") {
    return `
      <div>
        <label class="label">${escapeHtml(f.label)}</label>
        <select class="select" data-field="${f.key}" data-idx="${idx}">
          ${f.options.map((o) => `<option value="${o}" ${o === v ? "selected" : ""}>${o}</option>`).join("")}
        </select>
      </div>`;
  }
  if (f.type === "text") {
    return `
      <div>
        <label class="label">${escapeHtml(f.label)}</label>
        <input class="input" type="text" data-field="${f.key}" data-idx="${idx}" value="${escapeHtml(String(v))}" ${f.maxLength ? `maxlength="${f.maxLength}"` : ""}/>
      </div>`;
  }
  // int / float
  return `
    <div>
      <label class="label">${escapeHtml(f.label)}</label>
      <input class="input" type="number" data-field="${f.key}" data-idx="${idx}" value="${escapeHtml(String(v))}"
        ${f.min !== undefined ? `min="${f.min}"` : ""}
        ${f.max !== undefined ? `max="${f.max}"` : ""}
        ${f.step !== undefined ? `step="${f.step}"` : f.type === "float" ? `step="0.1"` : ""}
      />
    </div>`;
}

// ---------- JSON preview ----------
function buildImageJson(img) {
  const merged = [...globalTransformations, ...img.transformations];
  return { transformaciones: sortTransformations(merged) };
}

function updatePreview() {
  const active = images.find((i) => i.id === activeImageId) || images[0];
  if (!active) {
    activeImgName.textContent = "—";
    jsonPreview.innerHTML = '<span class="text-dim">// Sube al menos una imagen para ver el JSON generado</span>';
    return;
  }
  activeImgName.textContent = active.file.name;
  const json = buildImageJson(active);
  jsonPreview.innerHTML = colorizeJson(JSON.stringify(json, null, 2));
}

function colorizeJson(str) {
  return escapeHtml(str)
    .replace(/&quot;([^&]+?)&quot;(\s*:)/g, '<span class="k">&quot;$1&quot;</span>$2')
    .replace(/:\s*&quot;([^&]*?)&quot;/g, ': <span class="s">&quot;$1&quot;</span>')
    .replace(/:\s*(-?\d+\.?\d*)/g, ': <span class="n">$1</span>');
}

// ---------- Reset ----------
btnReset.addEventListener("click", () => {
  if (images.length === 0 && globalTransformations.length === 0) return;
  if (!confirm("¿Limpiar el lote en construcción? Se perderán imágenes y transformaciones.")) return;
  images.forEach((i) => URL.revokeObjectURL(i.url));
  images = [];
  globalTransformations = [];
  activeImageId = null;
  switchScope("global");
  renderImages();
  renderTransformList();
  updatePreview();
  toast({ title: "Canvas limpiada", variant: "success", ttl: 1500 });
});

// ---------- Forge (submit) ----------
btnForge.addEventListener("click", onForge);

async function onForge() {
  if (images.length === 0) {
    toast({ title: "Sin imágenes", body: "Sube al menos una imagen al lote", variant: "warning" });
    return;
  }

  // Build final JSONs per image and validate
  const finalJsons = [];
  for (const img of images) {
    const json = buildImageJson(img);
    // Validar cada transformación
    for (const t of json.transformaciones) {
      const err = validateTransformation(t);
      if (err) {
        toast({ title: `Error en ${img.file.name}`, body: err, variant: "error", ttl: 6000 });
        return;
      }
    }
    // Normalizar tipos numéricos
    json.transformaciones = json.transformaciones.map(normalizeTransformation);
    finalJsons.push({ img, json });
  }

  if (globalTransformations.length === 0 && images.every((i) => i.transformations.length === 0)) {
    if (!confirm("No definiste transformaciones. El lote se enviará sin pasos — ¿continuar?")) return;
  }

  openForgeModal(images.length);

  // Build multipart FormData: for each image, append image file + JSON with same base name.
  const fd = new FormData();
  for (const { img, json } of finalJsons) {
    const baseName = img.file.name.replace(/\.[^/.]+$/, "");
    // Sanitizar: quitar caracteres problemáticos del base name (pero mantener nombres razonables)
    const safeBase = baseName.replace(/[^\w\-.]/g, "_");
    const ext = img.file.name.split(".").pop();
    const imgRenamed = new File([img.file], `${safeBase}.${ext}`, { type: img.file.type });
    const jsonBlob = new Blob([JSON.stringify(json)], { type: "application/json" });
    fd.append("archivos", imgRenamed, `${safeBase}.${ext}`);
    fd.append("archivos", jsonBlob, `${safeBase}.json`);
  }

  setForgeStatus("Enviando archivos al API…");

  try {
    const res = await api.crearLote(fd);
    const id_lote = res.id_lote;
    api.addLote({
      id_lote,
      estado: res.estado,
      total: images.length,
      created_at: new Date().toISOString(),
      nombres: images.map((i) => i.file.name),
    });
    finishForgeModal(id_lote, images.length);
    toast({
      title: "Lote enviado",
      body: `id_lote ${id_lote.slice(0, 8)}…  ·  ${images.length} imágenes`,
      variant: "success",
    });
  } catch (err) {
    console.error(err);
    toast({
      title: "Falló el envío",
      body: err.message || "Error desconocido",
      variant: "error",
      ttl: 7000,
    });
    closeForgeModal();
  }
}

function openForgeModal(count) {
  const modal = document.getElementById("forge-modal");
  modal.classList.add("open");
  document.getElementById("forge-count").textContent = count;
  document.getElementById("forge-modal-actions").classList.add("hidden");
  document.getElementById("forge-progress").classList.add("indeterminate");
  document.getElementById("forge-modal-title").textContent = "Forjando lote…";
  btnForge.disabled = true;
}
function setForgeStatus(text) {
  document.getElementById("forge-modal-status").textContent = text;
}
function finishForgeModal(id_lote, count) {
  document.getElementById("forge-modal-title").textContent = "Lote enviado ";
  document.getElementById("forge-modal-body").innerHTML = `
    <span class="mono">${count}</span> imagen(es) publicadas en RabbitMQ. Los workers las
    procesarán en paralelo.
    <br/><br/>
    <span class="text-muted text-xs">id_lote:</span>
    <code class="mono">${id_lote}</code>
  `;
  document.getElementById("forge-progress").classList.remove("indeterminate");
  document.getElementById("forge-progress").style.width = "100%";
  document.getElementById("forge-modal-status").textContent = "Listo. Puedes abrir el lote para ver su progreso.";
  document.getElementById("forge-goto-detail").href = `lote.html?id=${encodeURIComponent(id_lote)}`;
  document.getElementById("forge-modal-actions").classList.remove("hidden");
  btnForge.disabled = false;
}
function closeForgeModal() {
  document.getElementById("forge-modal").classList.remove("open");
  btnForge.disabled = false;
}

// Initial render
renderImages();
renderTransformList();
updatePreview();
