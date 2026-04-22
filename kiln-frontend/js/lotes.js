import { api, toast, escapeHtml } from "./api.js";
import { mountTopbar } from "./topbar.js";

mountTopbar("lotes");

const wrap = document.getElementById("lotes-table-wrap");
const btnRefresh = document.getElementById("btn-refresh");
const idInput = document.getElementById("id-input");
const btnOpen = document.getElementById("btn-open");

btnRefresh.addEventListener("click", () => render(true));
btnOpen.addEventListener("click", () => {
  const id = idInput.value.trim();
  if (!id) return;
  location.href = `lote.html?id=${encodeURIComponent(id)}`;
});
idInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") btnOpen.click();
});

render();

async function render(refetch = false) {
  const lotes = api.getLotes();
  if (lotes.length === 0) {
    wrap.innerHTML = `
      <div class="empty-state" style="margin: 24px;">
        No has creado lotes todavía.<br/>
        <a href="forge.html">Forja el primero →</a>
      </div>`;
    return;
  }

  wrap.innerHTML = `
    <table class="lotes-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Imágenes</th>
          <th>Creado</th>
          <th>Estado</th>
          <th>Progreso</th>
          <th style="text-align:right;">Acciones</th>
        </tr>
      </thead>
      <tbody>
        ${lotes.map(renderRow).join("")}
      </tbody>
    </table>
  `;

  // Bind row actions
  wrap.querySelectorAll("[data-action='remove']").forEach((b) => {
    b.addEventListener("click", () => {
      if (!confirm("¿Quitar este lote del historial local? (no lo borra del servidor)")) return;
      api.removeLote(b.dataset.id);
      render();
    });
  });
  wrap.querySelectorAll("[data-action='open']").forEach((b) => {
    b.addEventListener("click", () => {
      location.href = `lote.html?id=${encodeURIComponent(b.dataset.id)}`;
    });
  });

  // Live status fetch
  for (const l of lotes) {
    fetchStatusForRow(l.id_lote, refetch).catch(() => {});
  }
}

function renderRow(l) {
  const created = l.created_at ? new Date(l.created_at) : null;
  return `
    <tr data-id="${l.id_lote}">
      <td><span class="lote-id">${escapeHtml(l.id_lote.slice(0, 8))}…</span></td>
      <td>${l.total ?? "—"}</td>
      <td>${created ? created.toLocaleString() : "—"}</td>
      <td id="estado-${l.id_lote}"><span class="badge">—</span></td>
      <td id="progreso-${l.id_lote}" style="min-width:180px;">
        <div class="progress-bar"><div class="progress-fill" style="width: 0%"></div></div>
      </td>
      <td style="text-align:right; white-space: nowrap;">
        <button class="btn btn-sm" data-action="open" data-id="${l.id_lote}">Abrir</button>
        <button class="btn btn-sm btn-ghost" data-action="remove" data-id="${l.id_lote}">Quitar</button>
      </td>
    </tr>
  `;
}

async function fetchStatusForRow(id, force) {
  const estadoCell = document.getElementById(`estado-${id}`);
  const progresoCell = document.getElementById(`progreso-${id}`);
  try {
    const data = await api.estadoLote(id);
    if (estadoCell) estadoCell.innerHTML = estadoBadge(data.estado);
    if (progresoCell) {
      const pct = Number(data.progreso) || 0;
      progresoCell.innerHTML = `
        <div class="flex-gap">
          <div class="progress-bar" style="flex:1;"><div class="progress-fill" style="width: ${pct}%"></div></div>
          <span class="text-xs text-muted mono" style="min-width:56px; text-align:right;">${data.completadas}/${data.total}</span>
        </div>`;
    }
  } catch (err) {
    if (estadoCell) {
      estadoCell.innerHTML = `<span class="badge badge-error" title="${escapeHtml(err.message)}">no disponible</span>`;
    }
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
