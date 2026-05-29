// ============================================================
// Kiln — API client
// Small fetch wrapper with JWT handling + error normalization.
// ============================================================

const LS_TOKEN = "kiln:token";
const LS_USER = "kiln:user";
const LS_BASE = "kiln:api_base";
const LS_LOTES = "kiln:lotes";

const DEFAULT_BASE = "https://stagnant-copious-oblivion.ngrok-free.dev";

export const api = {
  getBase() {
    return localStorage.getItem(LS_BASE) || DEFAULT_BASE;
  },
  setBase(url) {
    const clean = (url || "").trim().replace(/\/+$/, "");
    if (!clean) {
      localStorage.removeItem(LS_BASE);
    } else {
      localStorage.setItem(LS_BASE, clean);
    }
  },
  getToken() {
    return localStorage.getItem(LS_TOKEN);
  },
  setToken(token) {
    if (token) localStorage.setItem(LS_TOKEN, token);
    else localStorage.removeItem(LS_TOKEN);
  },
  getUser() {
    const raw = localStorage.getItem(LS_USER);
    return raw ? JSON.parse(raw) : null;
  },
  setUser(user) {
    if (user) localStorage.setItem(LS_USER, JSON.stringify(user));
    else localStorage.removeItem(LS_USER);
  },
  isAuthenticated() {
    return !!this.getToken();
  },
  logout() {
    this.setToken(null);
    this.setUser(null);
  },

  // Local history of batches created from this browser
  getLotes() {
    try {
      return JSON.parse(localStorage.getItem(LS_LOTES) || "[]");
    } catch {
      return [];
    }
  },
  addLote(entry) {
    const all = this.getLotes();
    all.unshift(entry);
    localStorage.setItem(LS_LOTES, JSON.stringify(all.slice(0, 100)));
  },
  removeLote(id_lote) {
    const all = this.getLotes().filter((l) => l.id_lote !== id_lote);
    localStorage.setItem(LS_LOTES, JSON.stringify(all));
  },

  // ---------- HTTP core ----------
  async _request(path, { method = "GET", body, headers = {}, raw = false } = {}) {
    const url = this.getBase() + path;
    const token = this.getToken();
    const finalHeaders = { ...headers };
    if (token) finalHeaders["Authorization"] = `Bearer ${token}`;
    finalHeaders["ngrok-skip-browser-warning"] = "true";

    let res;
    try {
      res = await fetch(url, { method, headers: finalHeaders, body });
    } catch (err) {
      throw new ApiError(
        0,
        `No se pudo contactar el API en ${this.getBase()} — revisa la configuración y que el servidor esté activo.`,
        err
      );
    }

    if (res.status === 401) {
      // Token inválido/expirado o ausente → forzar re-login
      this.logout();
      const detail = await extractError(res);
      if (!location.pathname.endsWith("/") && !location.pathname.endsWith("/index.html")) {
        location.href = "index.html";
      }
      throw new ApiError(401, detail || "Sesión expirada — inicia sesión nuevamente");
    }

    if (!res.ok) {
      const detail = await extractError(res);
      throw new ApiError(res.status, detail || `Error HTTP ${res.status}`);
    }

    if (raw) return res;
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res.text();
  },

  // ---------- Endpoints ----------
  async login(correo, password) {
    const res = await fetch(this.getBase() + "/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "true" },
      body: JSON.stringify({ correo, password }),
    }).catch((err) => {
      throw new ApiError(0, `No se pudo contactar el API en ${this.getBase()}`, err);
    });
    if (!res.ok) {
      const detail = await extractError(res);
      throw new ApiError(res.status, detail || "Error al iniciar sesión");
    }
    const data = await res.json();
    this.setToken(data.access_token);
    this.setUser({ correo });
    return data;
  },

  info() {
    return this._request("/info");
  },

  async crearLote(formData) {
    return this._request("/lote", { method: "POST", body: formData });
  },

  estadoLote(id) {
    return this._request(`/lote/${encodeURIComponent(id)}`);
  },

  async descargarResultado(id) {
    const res = await this._request(`/lote/${encodeURIComponent(id)}/resultado`, { raw: true });
    const blob = await res.blob();
    const filename = `lote_${id.slice(0, 8)}_resultado.zip`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    return blob;
  },
};

export class ApiError extends Error {
  constructor(status, message, cause) {
    super(message);
    this.status = status;
    this.cause = cause;
  }
}

async function extractError(res) {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => d.msg || JSON.stringify(d)).join(" · ");
    }
    if (data.message) return data.message;
    return JSON.stringify(data);
  } catch {
    try { return await res.text(); } catch { return null; }
  }
}

// ============================================================
// Toasts
// ============================================================
export function toast({ title, body, variant = "info", ttl = 4000 } = {}) {
  let region = document.querySelector(".toast-region");
  if (!region) {
    region = document.createElement("div");
    region.className = "toast-region";
    document.body.appendChild(region);
  }
  const el = document.createElement("div");
  el.className = `toast ${variant}`;
  el.innerHTML = `
    ${title ? `<div class="toast-title">${escapeHtml(title)}</div>` : ""}
    ${body ? `<div class="toast-body">${escapeHtml(body)}</div>` : ""}
  `;
  region.appendChild(el);
  setTimeout(() => {
    el.style.transition = "opacity 200ms, transform 200ms";
    el.style.opacity = "0";
    el.style.transform = "translateX(20px)";
    setTimeout(() => el.remove(), 220);
  }, ttl);
}

export function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
