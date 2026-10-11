// Plek kiezen op een beeld: klik = punt, slepen = rechthoek. Een plek is {x0, y0, x1, y1} in fracties van het beeld.

/** Koppelt klik/sleep aan `el`. `rectVan(e)` geeft de rechthoek (viewport) van het beeld onder de muis, of null. */
export function koppelSelectie(el, bij, rectVan = () => el.getBoundingClientRect()) {
  let start = null;
  const frac = (e, r) => [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
  el.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const r = rectVan(e);
    if (!r || !r.width) return;
    e.preventDefault();
    start = { r, px: e.clientX, py: e.clientY };
    el.setPointerCapture?.(e.pointerId);
  });
  el.addEventListener("pointerup", (e) => {
    if (!start) return;
    const { r, px, py } = start;
    start = null;
    const [x0, y0] = frac({ clientX: px, clientY: py }, r);
    const [x1, y1] = frac(e, r);
    const sleep = Math.hypot(e.clientX - px, e.clientY - py) > 5;
    bij(sleep ? { x0: Math.min(x0, x1), y0: Math.min(y0, y1), x1: Math.max(x0, x1), y1: Math.max(y0, y1) } : { x0, y0, x1: x0, y1: y0 });
  });
  el.addEventListener("pointercancel", () => { start = null; });
  el.style.cursor = "crosshair";
}

export const isPunt = (p) => p.x0 === p.x1 && p.y0 === p.y1;

/** Plek van fracties naar pixels van een beeld `b` x `h`: {x, y, r} of {x0, y0, x1, y1}. */
export function plekNaarPixels(p, b, h, minStraal = 2) {
  if (isPunt(p)) return { x: +(p.x0 * b).toFixed(1), y: +(p.y0 * h).toFixed(1), r: Math.max(minStraal, +(b / 160).toFixed(1)) };
  const x0 = Math.min(Math.floor(p.x0 * b), b - 2), y0 = Math.min(Math.floor(p.y0 * h), h - 2);
  return { x0, y0, x1: Math.min(b, Math.max(x0 + 1, Math.ceil(p.x1 * b))), y1: Math.min(h, Math.max(y0 + 1, Math.ceil(p.y1 * h))) };
}

/** Markering (kruisje of kader) in een positioneerbaar element. */
export function zetMarkering(el, p) {
  let m = el.querySelector(":scope > .markering");
  if (!p) { m?.remove(); return; }
  if (!m) { m = document.createElement("div"); el.append(m); }
  m.className = "markering " + (isPunt(p) ? "punt" : "gebied");
  m.style.left = `${p.x0 * 100}%`;
  m.style.top = `${p.y0 * 100}%`;
  m.style.width = isPunt(p) ? "" : `${(p.x1 - p.x0) * 100}%`;
  m.style.height = isPunt(p) ? "" : `${(p.y1 - p.y0) * 100}%`;
}
