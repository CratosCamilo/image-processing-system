import { api, toast } from "./api.js";

if (api.isAuthenticated()) {
  location.href = "forge.html";
}

const form = document.getElementById("login-form");
const submitBtn = document.getElementById("submit-btn");
const submitLabel = document.getElementById("submit-label");
const apiHint = document.getElementById("api-hint");

apiHint.textContent = `API → ${api.getBase()}`;

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const correo = /** @type {HTMLInputElement} */ (document.getElementById("correo")).value.trim();
  const password = /** @type {HTMLInputElement} */ (document.getElementById("password")).value;

  if (!correo || !password) {
    toast({ title: "Faltan campos", variant: "warning" });
    return;
  }

  submitBtn.disabled = true;
  submitLabel.innerHTML = '<span class="spinner"></span> Autenticando…';

  try {
    await api.login(correo, password);
    toast({ title: "Bienvenido a Kiln", body: correo, variant: "success", ttl: 1500 });
    setTimeout(() => (location.href = "forge.html"), 400);
  } catch (err) {
    toast({
      title: "Error al iniciar sesión",
      body: err.message || "Credenciales inválidas",
      variant: "error",
      ttl: 5000,
    });
    submitBtn.disabled = false;
    submitLabel.textContent = "Entrar al horno";
  }
});

document.getElementById("btn-settings-login").addEventListener("click", () => {
  const nuevo = prompt("URL base del API:", api.getBase());
  if (nuevo !== null) {
    api.setBase(nuevo);
    apiHint.textContent = `API → ${api.getBase()}`;
    toast({ title: "API actualizada", body: api.getBase(), variant: "success" });
  }
});
