// Plek kiezen op een beeld: klik = punt, slepen = rechthoek. Een plek is {x0, y0, x1, y1} in fracties van het beeld.

/** Koppelt klik/sleep aan `el`. `rectVan(e)` geeft de rechthoek (viewport) van het beeld onder de muis, of null. */
/** Een plek: rechthoek in fracties van het beeld (een punt heeft x0 = x1 en y0 = y1). */
export interface Plek { x0: number; y0: number; x1: number; y1: number }

export function koppelSelectie(el: HTMLElement, bij: (p: Plek) => void,
  rectVan: (e: PointerEvent) => DOMRect | null = () => el.getBoundingClientRect()): void {
  let start: { r: DOMRect; px: number; py: number } | null = null;
  const frac = (e: { clientX: number; clientY: number }, r: DOMRect): [number, number] => [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
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

export const isPunt = (p: Plek): boolean => p.x0 === p.x1 && p.y0 === p.y1;

/** Plek van fracties naar pixels van een beeld `b` x `h`: {x, y, r} of {x0, y0, x1, y1}. */
export function plekNaarPixels(p: Plek, b: number, h: number, minStraal = 2):
  { x: number; y: number; r: number } | { x0: number; y0: number; x1: number; y1: number } {
  if (isPunt(p)) return { x: +(p.x0 * b).toFixed(1), y: +(p.y0 * h).toFixed(1), r: Math.max(minStraal, +(b / 160).toFixed(1)) };
  const x0 = Math.min(Math.floor(p.x0 * b), b - 2), y0 = Math.min(Math.floor(p.y0 * h), h - 2);
  return { x0, y0, x1: Math.min(b, Math.max(x0 + 1, Math.ceil(p.x1 * b))), y1: Math.min(h, Math.max(y0 + 1, Math.ceil(p.y1 * h))) };
}

/** Markering (kruisje of kader) in een positioneerbaar element. */
export function zetMarkering(el: HTMLElement, p: Plek | null | undefined): void {
  let m = el.querySelector<HTMLElement>(":scope > .markering");
  if (!p) { m?.remove(); return; }
  if (!m) { m = document.createElement("div"); el.append(m); }
  m.className = "markering " + (isPunt(p) ? "punt" : "gebied");
  m.style.left = `${p.x0 * 100}%`;
  m.style.top = `${p.y0 * 100}%`;
  m.style.width = isPunt(p) ? "" : `${(p.x1 - p.x0) * 100}%`;
  m.style.height = isPunt(p) ? "" : `${(p.y1 - p.y0) * 100}%`;
}
