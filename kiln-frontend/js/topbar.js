// Topbar — injects nav + user chip + settings dialog.
import { api, toast } from "./api.js";

export function mountTopbar(active) {
  if (!api.isAuthenticated()) {
    location.href = "index.html";
    return;
  }
  const user = api.getUser() || {};
  const topbar = document.createElement("header");
  topbar.className = "topbar";
  topbar.innerHTML = `
    <div class="topbar-inner">
      <a class="brand" href="forge.html">
        <img src="assets/logo.svg" alt="Kiln"/>
        <span>Kiln</span>
      </a>
      <nav class="nav">
        <a href="forge.html" data-key="forge">Forjar</a>
        <a href="lotes.html" data-key="lotes">Lotes</a>
        <a href="info.html" data-key="info">Docs</a>
      </nav>
      <div class="topbar-actions">
        <button class="btn btn-ghost btn-icon" id="btn-settings" title="Configurar API">
          ${iconSettings()}
        </button>
        <div class="user-chip">
          <span class="dot"></span>
          <span class="mono">${user.correo || "—"}</span>
        </div>
        <button class="btn btn-ghost btn-sm" id="btn-logout">Cerrar sesión</button>
      </div>
    </div>
  `;
  document.body.prepend(topbar);

  const navActive = topbar.querySelector(`.nav a[data-key="${active}"]`);
  if (navActive) navActive.classList.add("active");

  topbar.querySelector("#btn-logout").addEventListener("click", () => {
    api.logout();
    location.href = "index.html";
  });
  topbar.querySelector("#btn-settings").addEventListener("click", openSettings);
}

function openSettings() {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay open";
  overlay.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true">
      <h3 class="modal-title">Configuración del API</h3>
      <p class="modal-body">
        Apunta el frontend a una URL específica del backend. El valor se guarda en
        <span class="mono">localStorage</span>.
      </p>
      <label class="label">URL base</label>
      <input id="api-base-input" class="input" placeholder="http://localhost:8000" value="${api.getBase()}"/>
      <p class="text-xs text-muted mt-8">Ejemplos: <span class="mono">http://localhost:8000</span> · <span class="mono">http://192.168.1.50:8000</span></p>
      <div class="modal-actions mt-16">
        <button class="btn" id="api-cancel">Cancelar</button>
        <button class="btn btn-primary" id="api-save">Guardar</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const close = () => overlay.remove();
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  overlay.querySelector("#api-cancel").addEventListener("click", close);
  overlay.querySelector("#api-save").addEventListener("click", () => {
    const val = overlay.querySelector("#api-base-input").value;
    api.setBase(val);
    toast({ title: "API actualizada", body: api.getBase(), variant: "success" });
    close();
  });
  overlay.querySelector("#api-base-input").focus();
}

function iconSettings() {
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`;
}
