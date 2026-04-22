// ============================================================
// Kiln — Transformations catalog
// Contrato: cada transformación genera un objeto { tipo, ...params }
// que el backend (POST /lote) acepta dentro de { transformaciones: [...] }.
// ============================================================

export const WATERMARK_POSITIONS = [
  "top-left",
  "top-right",
  "bottom-left",
  "bottom-right",
  "center",
];

export const CONVERT_FORMATS = ["jpeg", "png", "tiff"];

export const FLIP_DIRECTIONS = ["horizontal", "vertical"];

// Orden recomendado según CLAUDE.md / ARQUITECTURA.txt
export const RECOMMENDED_ORDER = [
  "crop",
  "resize",
  "flip",
  "rotate",
  "brightness",
  "contrast",
  "blur",
  "sharpen",
  "grayscale",
  "watermark",
  "convert",
];

export const TRANSFORMS = {
  resize: {
    label: "Resize",
    description: "Redimensiona al ancho y alto indicados (px).",
    defaults: { width: 800, height: 600 },
    fields: [
      { key: "width", label: "Ancho (px)", type: "int", min: 1 },
      { key: "height", label: "Alto (px)", type: "int", min: 1 },
    ],
  },
  grayscale: {
    label: "Grayscale",
    description: "Convierte la imagen a escala de grises.",
    defaults: {},
    fields: [],
  },
  rotate: {
    label: "Rotate",
    description: "Rota N grados (antihorario). Se expande para no recortar.",
    defaults: { angle: 90 },
    fields: [
      { key: "angle", label: "Ángulo (°)", type: "float" },
    ],
  },
  crop: {
    label: "Crop",
    description: "Recorta una región rectangular.",
    defaults: { x: 0, y: 0, width: 400, height: 400 },
    fields: [
      { key: "x", label: "X", type: "int", min: 0 },
      { key: "y", label: "Y", type: "int", min: 0 },
      { key: "width", label: "Ancho", type: "int", min: 1 },
      { key: "height", label: "Alto", type: "int", min: 1 },
    ],
  },
  flip: {
    label: "Flip",
    description: "Refleja horizontal o verticalmente.",
    defaults: { direction: "horizontal" },
    fields: [
      { key: "direction", label: "Dirección", type: "select", options: FLIP_DIRECTIONS },
    ],
  },
  blur: {
    label: "Blur",
    description: "Desenfoque gaussiano. Radio ≥ 0.1.",
    defaults: { radius: 2.0 },
    fields: [
      { key: "radius", label: "Radio", type: "float", min: 0.1, step: 0.1 },
    ],
  },
  sharpen: {
    label: "Sharpen",
    description: "Aumenta la nitidez. Factor ≥ 1.0 (1.0 = sin cambio).",
    defaults: { factor: 2.0 },
    fields: [
      { key: "factor", label: "Factor", type: "float", min: 1.0, step: 0.1 },
    ],
  },
  brightness: {
    label: "Brightness",
    description: "Ajusta el brillo. > 0.0 (1.0 = sin cambio).",
    defaults: { factor: 1.2 },
    fields: [
      { key: "factor", label: "Factor", type: "float", min: 0.01, step: 0.1 },
    ],
  },
  contrast: {
    label: "Contrast",
    description: "Ajusta el contraste. > 0.0 (1.0 = sin cambio).",
    defaults: { factor: 1.5 },
    fields: [
      { key: "factor", label: "Factor", type: "float", min: 0.01, step: 0.1 },
    ],
  },
  watermark: {
    label: "Watermark",
    description: "Superpone texto con opacidad. Máx 50 caracteres.",
    defaults: { text: "Kiln", position: "bottom-right", opacity: 0.6 },
    fields: [
      { key: "text", label: "Texto", type: "text", maxLength: 50 },
      { key: "position", label: "Posición", type: "select", options: WATERMARK_POSITIONS },
      { key: "opacity", label: "Opacidad", type: "float", min: 0.0, max: 1.0, step: 0.05 },
    ],
  },
  convert: {
    label: "Convert",
    description: "Cambia el formato del archivo de salida. Siempre al final.",
    defaults: { format: "png" },
    fields: [
      { key: "format", label: "Formato", type: "select", options: CONVERT_FORMATS },
    ],
  },
};

export const TRANSFORM_TYPES = Object.keys(TRANSFORMS);

/**
 * Ordena una lista de transformaciones según el orden recomendado.
 * Garantiza que 'convert' siempre quede al final si está presente.
 */
export function sortTransformations(list) {
  const copy = [...list];
  copy.sort((a, b) => {
    const ia = RECOMMENDED_ORDER.indexOf(a.tipo);
    const ib = RECOMMENDED_ORDER.indexOf(b.tipo);
    return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
  });
  // Mover cualquier 'convert' al final
  const convertIdx = copy.findIndex((t) => t.tipo === "convert");
  if (convertIdx !== -1 && convertIdx !== copy.length - 1) {
    const [c] = copy.splice(convertIdx, 1);
    copy.push(c);
  }
  return copy;
}

/**
 * Valida una transformación. Retorna null si ok, o un string de error.
 */
export function validateTransformation(t) {
  const spec = TRANSFORMS[t.tipo];
  if (!spec) return `Tipo desconocido: ${t.tipo}`;
  for (const f of spec.fields) {
    const v = t[f.key];
    if (v === undefined || v === null || v === "") {
      return `${spec.label}: falta ${f.label}`;
    }
    if (f.type === "int" || f.type === "float") {
      const n = Number(v);
      if (Number.isNaN(n)) return `${spec.label}.${f.key} debe ser numérico`;
      if (f.min !== undefined && n < f.min) return `${spec.label}.${f.key} debe ser ≥ ${f.min}`;
      if (f.max !== undefined && n > f.max) return `${spec.label}.${f.key} debe ser ≤ ${f.max}`;
    }
    if (f.type === "text" && f.maxLength && String(v).length > f.maxLength) {
      return `${spec.label}.${f.key} máximo ${f.maxLength} caracteres`;
    }
    if (f.type === "select" && !f.options.includes(v)) {
      return `${spec.label}.${f.key} debe ser uno de: ${f.options.join(", ")}`;
    }
  }
  return null;
}

/**
 * Normaliza los valores de una transformación a los tipos esperados por el backend.
 */
export function normalizeTransformation(t) {
  const spec = TRANSFORMS[t.tipo];
  const out = { tipo: t.tipo };
  for (const f of spec.fields) {
    let v = t[f.key];
    if (f.type === "int") v = parseInt(v, 10);
    else if (f.type === "float") v = parseFloat(v);
    out[f.key] = v;
  }
  return out;
}
