// Vanilla binding for the thinking-orbs engine (npm: thinking-orbs) - the package ships a React component, but its
// canvas engine is framework-free, so the app uses it directly: no React, no bundler.
import { resolvePreset, MODE_FRAMES, paintFrame } from "/vendor/thinking-orbs/engine.es.js";

const reduced = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const hexTint = h => { const m = /^#?([0-9a-f]{6})$/i.exec(h || ""); if (!m) return undefined;
  const n = parseInt(m[1], 16); return {r: n >> 16 & 255, g: n >> 8 & 255, b: n & 255}; };

/** canvas: a <canvas>; state: working|searching|solving|listening|connecting|weaving|composing|breathing|shaping;
 *  size: 20 (inline) or 64 (large); color: optional #rrggbb tint (the app's dark theme is always on) */
export function orb(canvas, {state = "working", size = 20, color, label} = {}) {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.round(size * dpr); canvas.height = Math.round(size * dpr);
  canvas.style.width = canvas.style.height = size + "px";
  canvas.setAttribute("role", "img"); if (label) canvas.setAttribute("aria-label", label);
  const ctx = canvas.getContext("2d");
  let cur = null, raf = 0, alive = true;
  const set = s => {
    const {mode, speed, opts} = resolvePreset(s, size);
    cur = {fn: MODE_FRAMES[mode], speed, opts, tint: hexTint(color)};
    if (reduced()) draw(0.6);
  };
  const draw = t => { ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, size, size);
    paintFrame(ctx, cur.fn(size, t, cur.opts), true, cur.tint); };
  const loop = () => { if (!alive) return; if (!document.hidden) draw(performance.now() / 1e3 * cur.speed); raf = requestAnimationFrame(loop); };
  set(state);
  if (!reduced()) raf = requestAnimationFrame(loop);
  return { setState: set, stop() { alive = false; cancelAnimationFrame(raf); } };
}
