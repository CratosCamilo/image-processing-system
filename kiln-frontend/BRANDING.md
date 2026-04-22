# Kiln — Branding Guide

> **Kiln** *(noun)* — a furnace or oven used for transformation of raw material.

**Kiln** es una interfaz para el sistema distribuido de procesamiento de imágenes en lote. La metáfora: un horno donde las imágenes se "forjan" en paralelo, transformándose según instrucciones precisas. El nombre evoca calor, proceso, y el resultado final — sin sonar técnico ni agresivo.

- **Tagline corta:** *Forge your images in parallel*
- **Tagline larga:** *Batch image processing, distilled into a single canvas*
- **Voz:** técnica pero humana, breve, directa. Inspirada en Linear, Raycast y Vercel.

---

## Paleta de colores

El sistema usa un **modo oscuro cálido** con un acento ámbar que remite al fuego del horno. Evita el azul corporativo típico — apuesta por tonos terrosos y un naranja quemado como punto focal.

| Token             | Hex       | Uso                                           |
|-------------------|-----------|-----------------------------------------------|
| `--bg`            | `#0b0b0e` | Fondo de página                               |
| `--surface`       | `#131318` | Cards, paneles                                |
| `--surface-2`     | `#1c1c23` | Inputs, hover de cards                        |
| `--surface-3`     | `#26262f` | Chips, controles secundarios                  |
| `--border`        | `#2a2a33` | Bordes sutiles                                |
| `--border-strong` | `#3a3a45` | Bordes de inputs activos                      |
| `--text`          | `#f5f1e8` | Texto principal (blanco cálido, no puro)      |
| `--text-muted`    | `#9b9689` | Texto secundario, labels                      |
| `--text-dim`      | `#5e5b53` | Placeholders, hints                           |
| `--accent`        | `#ff6b2c` | Naranja forja — CTA, foco, links activos      |
| `--accent-hover`  | `#ff884f` | Hover sobre acento                            |
| `--accent-dim`    | `#3a2418` | Fondo tenue del acento (badges, tints)        |
| `--accent-soft`   | `#ff6b2c1a` | Overlay translúcido del acento              |
| `--success`       | `#4ade80` | Estados completados                           |
| `--warning`       | `#fbbf24` | Estados procesando / en curso                 |
| `--error`         | `#ef4444` | Errores, estados fallidos                     |
| `--info`          | `#60a5fa` | Información neutral                           |

**Gradiente de firma:**
```
linear-gradient(135deg, #ff6b2c 0%, #ff3d00 50%, #c2410c 100%)
```
Se usa con moderación — solo en el logo, botón principal y un accent sutil en el fondo del login.

---

## Tipografía

- **UI / cuerpo:** `Inter` (400, 500, 600, 700) — fallback `system-ui, -apple-system, sans-serif`
- **Display / headings:** `Inter` con `letter-spacing: -0.02em` para títulos grandes
- **Monoespaciado:** `JetBrains Mono` — para previews de JSON, IDs de lote, código
- **Escala tipográfica** (base 16px, ratio 1.25):

  | Nombre   | Size   | Uso                        |
  |----------|--------|----------------------------|
  | `xs`     | 12px   | Labels, badges             |
  | `sm`     | 14px   | Texto auxiliar             |
  | `base`   | 16px   | Cuerpo                     |
  | `lg`     | 18px   | Subtítulos                 |
  | `xl`     | 22px   | Títulos de sección         |
  | `2xl`    | 28px   | H1 de página               |
  | `3xl`    | 40px   | Hero en login              |

---

## Radios y elevación

- `--radius-sm`: 6px (chips, badges)
- `--radius-md`: 10px (inputs, botones)
- `--radius-lg`: 14px (cards)
- `--radius-xl`: 20px (paneles grandes)
- `--shadow-sm`: `0 1px 2px rgba(0,0,0,0.4)`
- `--shadow-md`: `0 6px 20px rgba(0,0,0,0.35)`
- `--shadow-glow`: `0 0 24px rgba(255,107,44,0.25)` — halo sobre el CTA principal

---

## Principios visuales

1. **Oscuro cálido, no frío.** El fondo tiene un matiz levemente rojizo, no gris-azul.
2. **El acento es escaso.** El naranja aparece solo donde el usuario debe actuar o mirar — un CTA, un badge de estado, un elemento enfocado.
3. **Densidad controlada.** Se prefiere aire a información comprimida. Padding generoso (16–24px) en cards.
4. **Microinteracciones sutiles.** Transiciones de 120–200ms en `ease-out`. Nada brusco.
5. **Monoespaciado para lo técnico.** IDs, JSON, rutas — siempre en mono para que se distingan del copy narrativo.
6. **Fondo vivo pero calmado.** Un gradiente radial tenue en la esquina del hero + ruido opcional via SVG, al 3% de opacidad.

---

## Iconografía

Se usan íconos SVG inline (sin librería externa) para mantener el bundle liviano. Trazo de 1.5px, estilo "Lucide" — minimal line icons.

---

## Tono de UI copy

- **Preferir verbos directos:** *Forge batch* en lugar de *"Create batch"*. *Upload images* en lugar de *"Choose files"*.
- **Spanglish controlado:** la app es en español (el usuario es hispanohablante y los endpoints usan términos en español: lote, imagen, transformación), pero el branding y algunos CTAs cortos pueden quedar en inglés cuando suenen más naturales (*Forge, Kiln, Ready*).
- **Estados en español** ("pendiente", "procesando", "completado", "error") — coinciden con los que devuelve el backend.

---

## Layout

- **Max width de contenido:** 1280px, centrado
- **Grid del constructor de lote:** split 60/40 (preview imágenes / panel de transformaciones)
- **Topbar:** 56px de alto, sticky, con logo a la izquierda + nav + avatar del usuario a la derecha
- **Responsive:** mobile-first no es prioridad; el uso principal es desktop. Se adapta a ≥1024px de manera fluida y degrada a stack vertical en ≤768px.
