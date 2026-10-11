// three.js-preview: een BENADERING van de HQ-render (camera, belichting, materialen), geen fysisch model.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RGBELoader } from "three/addons/loaders/RGBELoader.js";
import { geometrie, hdriUrl } from "./api.js";
import { waardeNaarHex } from "./kleur.js";

const lin = (rgb) => new THREE.Color().setRGB(rgb[0], rgb[1], rgb[2], THREE.LinearSRGBColorSpace);
const bufGeo = (v) => {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(v.posities, 3));
  g.setAttribute("normal", new THREE.Float32BufferAttribute(v.normalen, 3));
  g.setIndex(v.indices);
  return g;
};

export class Preview {
  constructor(kader, { ral, presets }) {
    this.kader = kader;
    this.ral = ral;
    this.presets = presets;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    this.renderer.toneMapping = THREE.LinearToneMapping; // zoals de PNG: lineair * 2^EV, dan sRGB
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    kader.append(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(40, 16 / 9, 0.01, 200);
    this.camera.position.set(0, 0.55, 0.62);
    this.hfov = 40;
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.addEventListener("change", () => this.vraagRender());
    this.controls.addEventListener("start", () => this.bijVrijeCamera?.());
    this.pmrem = new THREE.PMREMGenerator(this.renderer);
    this.hdriCache = new Map();
    this.blok = new THREE.Group();
    this.scene.add(this.blok);
    this.vloer = null;
    this.spot = null;
    this.geoSleutel = null;
    this.omgevingNaam = undefined;
    new ResizeObserver(() => this.pasMaatAan()).observe(kader);
    this.pasMaatAan();
  }

  vraagRender() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = 0; this.renderer.render(this.scene, this.camera); });
  }

  pasMaatAan() {
    const b = this.kader.clientWidth, h = this.kader.clientHeight;
    if (!b || !h) return;
    this.renderer.setSize(b, h, false);
    this.renderer.domElement.style.cssText = "width:100%;height:100%;display:block";
    this.zetAspect(b / h);
    this.vraagRender();
  }

  /** De config-fov is horizontaal; three.js gebruikt een verticale. */
  zetAspect(aspect) {
    this.camera.aspect = aspect;
    this.camera.fov = (2 * Math.atan(Math.tan((this.hfov * Math.PI) / 360) / aspect) * 180) / Math.PI;
    this.camera.updateProjectionMatrix();
  }

  zetCamera({ positie, doel, fov }) {
    this.hfov = fov;
    this.camera.position.set(...positie);
    this.controls.target.set(...doel);
    this.zetAspect(this.camera.aspect);
    this.controls.update();
    this.vraagRender();
  }

  /** Huidige camera in configvorm (horizontale fov). */
  getCamera() {
    const r = (a) => a.map((x) => Math.round(x * 1e5) / 1e5);
    return { positie: r(this.camera.position.toArray()), doel: r(this.controls.target.toArray()), fov: this.hfov };
  }

  zetEv(ev) {
    this.renderer.toneMappingExposure = 2 ** ev;
    this.vraagRender();
  }

  // --- omgeving ---
  async laadHdri(naam) {
    if (!this.hdriCache.has(naam)) {
      const p = new RGBELoader().loadAsync(hdriUrl(naam)).then((tex) => {
        tex.mapping = THREE.EquirectangularReflectionMapping;
        return { tex, env: this.pmrem.fromEquirectangular(tex).texture };
      });
      this.hdriCache.set(naam, p);
    }
    return this.hdriCache.get(naam);
  }

  async zetOmgeving(cfg) {
    const naam = cfg.scene.omgeving;
    const om = this.presets.omgevingen.find((o) => o.naam === naam);
    this.omgevingNaam = naam;
    if (this.vloer) { this.scene.remove(this.vloer); this.vloer.geometry.dispose(); this.vloer.material.dispose(); }
    if (this.spot) { this.scene.remove(this.spot, this.spot.target); this.spot = null; }
    const hoogte = cfg.hoogte;
    const vloerKleur = om ? lin(om.vloer.albedo) : lin(cfg.scene.vloer_albedo ?? [0.75, 0.75, 0.72]);
    const vloer = new THREE.Mesh(new THREE.PlaneGeometry(40, 40).rotateX(-Math.PI / 2),
      new THREE.MeshStandardMaterial({ color: vloerKleur, roughness: 0.85 }));
    vloer.position.y = cfg.poten ? -cfg.poten.hoogte_m : hoogte - this.presets.tafel_hoogte; // T26: met poten op de poothoogte
    this.vloer = vloer;
    this.scene.add(vloer);
    if (om) {
      const { tex, env } = await this.laadHdri(naam);
      if (this.omgevingNaam !== naam) return; // intussen een andere keuze
      const rot = Math.PI / 2 - (om.rotatie * Math.PI) / 180; // Mitsuba-envmap -> three.js equirect
      this.scene.background = tex;
      this.scene.environment = env;
      this.scene.backgroundIntensity = this.scene.environmentIntensity = om.schaal;
      this.scene.backgroundRotation.set(0, rot, 0);
      this.scene.environmentRotation.set(0, rot, 0);
    } else { // constante omgeving
      const c = lin(cfg.scene.omgeving_radiantie ?? [1, 1, 1]);
      this.scene.background = c;
      this.scene.environment = null;
    }
    const sp = om?.spot ?? (cfg.scene.spot ? { hoogte: 1, intensiteit: 30, kegelhoek: 25 } : null);
    if (sp) {
      const s = new THREE.SpotLight(0xffffff, sp.intensiteit, 0, (sp.kegelhoek * Math.PI) / 180, 0.2, 2);
      s.position.set(0, hoogte + sp.hoogte, 0);
      this.spot = s;
      this.scene.add(s, s.target);
    }
    this.vraagRender();
  }

  // --- tafel ---
  afwerkingMateriaal(f, cfg) {
    const glas = (ruw) => new THREE.MeshPhysicalMaterial({
      color: 0xffffff, transmission: 1, ior: cfg.epoxy.cauchy_a + cfg.epoxy.cauchy_b / 0.347, thickness: cfg.hoogte,
      roughness: ruw, metalness: 0,
    });
    if (f.type === "paintstack") f = f.lagen[f.lagen.length - 1];  // de preview toont de buitenste laag (T24)
    if (f.type === "paint" || f.type === "plate") {
      const c = new THREE.Color(waardeNaarHex(f.color, this.ral));
      const ruw = f.roughness ? Math.sqrt(f.roughness) : null;
      const m = this.verfMateriaal(f, c, ruw);
      m.side = THREE.DoubleSide; // de onderkant moet ook zichtbaar zijn door de transmissie heen
      return m;
    }
    return glas(f.type === "clearcoat" ? Math.sqrt(f.roughness) : 0.0);
  }

  verfMateriaal(f, c, ruw) {
    switch (f.kind) {
      case "glossy": return new THREE.MeshPhysicalMaterial({ color: c, roughness: ruw ?? 0.08, clearcoat: 0.3 });
      case "metallic": return new THREE.MeshStandardMaterial({ color: c, metalness: 1, roughness: ruw ?? 0.3 });
      case "candy": return new THREE.MeshPhysicalMaterial({
        color: c, metalness: f.candy_base === "white" ? 0 : 1, roughness: ruw ?? 0.3, clearcoat: 1, clearcoatRoughness: 0.03 });
      default: return new THREE.MeshStandardMaterial({ color: c, roughness: ruw ?? 0.85 });
    }
  }

  /** Materiaal van een poot (benadering van het Mitsuba-materiaal: Al, Cr, zwarte poedercoating). */
  pootMateriaal(metaal) {
    switch (metaal) {
      case "gepoetst": return new THREE.MeshStandardMaterial({ color: lin([0.55, 0.56, 0.55]), metalness: 1, roughness: Math.sqrt(0.02) });
      case "zwart": return new THREE.MeshStandardMaterial({ color: lin([0.02, 0.02, 0.02]), metalness: 0, roughness: Math.sqrt(0.3) });
      default: return new THREE.MeshStandardMaterial({ color: lin([0.91, 0.92, 0.92]), metalness: 1, roughness: Math.sqrt(0.2) });
    }
  }

  async zetTafel(cfg) {
    const sleutel = JSON.stringify([cfg.diameter, cfg.hoogte, cfg.segmenten, cfg.layers, cfg.poten, cfg.poten && cfg.onderkant.gap_mm]);
    const kleurSleutel = JSON.stringify([cfg.zijkant, cfg.onderkant, cfg.epoxy, cfg.poten?.metaal]);
    if (sleutel !== this.geoSleutel) {
      const g = await geometrie(cfg); // kan een fout geven (bv. inhoud past niet)
      this.geoSleutel = sleutel;
      this.geo = g;
      this.matSleutel = null;
    }
    if (cfg.poten && this.vloer && this.geo.vloer_y != null) this.vloer.position.y = this.geo.vloer_y; // met een plaat hangen de poten lager
    if (kleurSleutel === this.matSleutel) return;
    this.matSleutel = kleurSleutel;
    for (const k of [...this.blok.children]) { this.blok.remove(k); k.geometry?.dispose(); }
    const g = this.geo;
    const glas = this.afwerkingMateriaal({ type: "bare" }, cfg);
    const mantel = this.afwerkingMateriaal(cfg.zijkant, cfg);
    const onder = cfg.onderkant.type === "plate" ? glas : this.afwerkingMateriaal(cfg.onderkant, cfg);
    this.blok.add(new THREE.Mesh(bufGeo(g.vlakken.boven), glas));
    this.blok.add(new THREE.Mesh(bufGeo(g.vlakken.mantel), mantel));
    this.blok.add(new THREE.Mesh(bufGeo(g.vlakken.onder), onder));
    if (cfg.onderkant.type === "plate") {
      const dik = 0.004, gap = cfg.onderkant.gap_mm / 1000;
      const plaat = new THREE.Mesh(new THREE.CylinderGeometry(g.diameter / 2, g.diameter / 2, dik, 96),
        this.afwerkingMateriaal(cfg.onderkant, cfg));
      plaat.position.y = -gap - dik / 2;
      this.blok.add(plaat);
    }
    if (cfg.poten) { // T26: de meshes komen van de backend (zelfde plaatsing als de render)
      const m = this.pootMateriaal(cfg.poten.metaal);
      for (const pg of g.poten ?? []) this.blok.add(new THREE.Mesh(bufGeo(pg), m));
    }
    // inhoud: per soort samengevoegd tot één mesh; de albedo (per exemplaar iets anders) gaat als vertexkleur mee
    for (const soort of ["wood", "flower"]) {
      const pos = [], nor = [], kl = [], idx = [];
      let o = 0;
      for (const d of g.inhoud.filter((x) => x.soort === soort)) {
        pos.push(...d.posities); nor.push(...d.normalen);
        const n = d.posities.length / 3;
        for (let i = 0; i < n; i++) kl.push(...(d.kleur ?? [0.5, 0.5, 0.5]));
        for (const i of d.indices) idx.push(i + o);
        o += n;
      }
      if (!pos.length) continue;
      const geo = bufGeo({ posities: pos, normalen: nor, indices: idx });
      geo.setAttribute("color", new THREE.Float32BufferAttribute(kl, 3));
      // ondoorzichtig: transparante objecten komen niet in de transmissie-pass
      this.blok.add(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9, side: THREE.DoubleSide })));
    }
    this.vraagRender();
  }

  async update(cfg) {
    const omKey = JSON.stringify([cfg.scene.omgeving, cfg.hoogte, cfg.scene.spot, cfg.poten?.hoogte_m ?? null]);
    const omTaak = this._omKey !== omKey ? this.zetOmgeving(cfg) : null;
    this._omKey = omKey;
    await Promise.all([omTaak, this.zetTafel(cfg)]);
    this.vraagRender();
  }
}
