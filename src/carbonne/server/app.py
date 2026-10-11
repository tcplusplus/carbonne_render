"""FastAPI-app: schema, presets, geometrie, HDRI's, renderjobs (WebSocket) en opgeslagen configs."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from carbonne.analyse.parameters import PARAMETERS
from carbonne.analyse.reeks import zet_pad
from carbonne.core import environments as env
from carbonne.core import verfbibliotheek as bib
from carbonne.core.config import TableConfig
from carbonne.core.kleur import lineair_naar_srgb, ral_tabel
from carbonne.core.verf import VerfEigenschappen, VerfFout, Vertaling, vertaal_verf
from carbonne.core.verf_tekst import TekstFout, uit_tekst, vraag
from carbonne.render.pipeline import RenderOpties
from carbonne.server.hdri import hdri_1k
from carbonne.server.jobs import EINDSTATEN, JobManager, Renderer

ROOT = Path(__file__).resolve().parents[3]
NAAM_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class RenderAanvraag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: TableConfig
    opties: RenderOpties = Field(default_factory=RenderOpties, description="cache_map wordt door de server bepaald")
    herkomst: bool = Field(False, description="render met de herkomst-integrator (T13); ~2x trager")


class ReeksAanvraag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: TableConfig
    parameter: str = Field(description="pad uit GET /api/reeks/parameters")
    waarden: list = Field(min_length=1, max_length=24)
    gebied: list[float] = Field(description="[x, y] (met straal) of [x0, y0, x1, y1], pixels van het reeksbeeld")
    straal: float = Field(2.0, gt=0, le=200)
    breedte: int = Field(256, ge=32, le=1024, description="breedte van het reeksbeeld; de hoogte volgt de config")
    spp: int = Field(512, ge=2, le=16384, description="totaal per waarde (twee helften)")
    seed: int = 0
    ev: float = 0.0


class TekstAanvraag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tekst: str = Field(min_length=1, description="het geplakte ChatGPT-antwoord")


class ConfigOpslaan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    naam: str
    config: TableConfig


def plaats_of_422(config: TableConfig, loc: tuple[str, ...]) -> list[list]:
    """Plaats de inhoud; past een laag niet (te hoog of laag in het blok, te groot, te vol), dan 422 in het
    Pydantic-formaat (`loc` wijst de laag aan) in plaats van een 500 of een render die achteraf faalt."""
    from carbonne.core.inhoud import plaats_laag

    totaal: list = []
    uit = []
    for li, laag in enumerate(config.layers):
        try:
            its = plaats_laag(config, laag, totaal)
        except ValueError as e:
            raise HTTPException(422, [{"type": "inhoud_past_niet", "loc": [*loc, "layers", li], "msg": str(e)}]) from e
        totaal += its
        uit.append(its)
    return uit


def maak_app(
    renderer: Renderer | None = None,
    cache_map: Path | None = None,
    configs_map: Path | None = None,
    web_map: Path | None = None,
    verven_map: Path | None = None,
) -> FastAPI:
    """App-fabriek; tests geven een nep-`renderer` en tijdelijke mappen mee."""
    cache_map = cache_map or Path(os.environ.get("CARBONNE_CACHE", ROOT / "cache"))
    configs_map = configs_map or Path(os.environ.get("CARBONNE_CONFIGS", ROOT / "configs"))
    web_map = web_map or ROOT / "web"
    verven_map = bib.verf_map(verven_map)
    kw = {"renderer": renderer} if renderer is not None else {}
    jobs = JobManager(cache_map=cache_map, uit_map=cache_map / "server", **kw)
    app = FastAPI(title="carbonne", version="0.1.0")
    app.state.jobs = jobs

    @app.get("/api/schema")
    def schema() -> dict:
        return TableConfig.model_json_schema()

    @app.get("/api/presets")
    def presets() -> dict:
        return {
            "omgevingen": [
                {"naam": o.naam, "omschrijving": o.omschrijving, "hdri": o.hdri.naam, "rotatie": o.rotatie,
                 "schaal": o.schaal, "vloer": o.vloer.model_dump(), "spot": o.spot.model_dump() if o.spot else None}
                for o in env.OMGEVINGEN.values()
            ],
            "camera_presets": list(env.CAMERA_PRESETS),
            "tafel_hoogte": env.TAFEL_HOOGTE,
            "ral": [{"code": c, "hex": h, "naam": n} for c, (h, n) in ral_tabel().items()],
        }

    @app.get("/api/camera/{naam}")
    def camera(naam: str, diameter: float = 0.35, hoogte: float = 0.04, poot_hoogte: float | None = None) -> dict:
        """`poot_hoogte` (m, T26): met poten staat het oog t.o.v. de vloer onder de poten."""
        try:
            tafel = env.TAFEL_HOOGTE if poot_hoogte is None else hoogte + poot_hoogte
            return env.camera_preset(naam, diameter, hoogte, tafel).model_dump()
        except KeyError as e:
            raise HTTPException(404, str(e)) from e

    @app.post("/api/geometrie")
    def geometrie(config: TableConfig) -> dict:
        """Mesh van het blok en de inhoud voor de three.js-preview (meter, onderkant op y = 0)."""
        from carbonne.core.scene import cilinder_geometrie

        def plat(v, n, f) -> dict:
            return {"posities": v.astype("float32").ravel().round(6).tolist(),
                    "normalen": n.astype("float32").ravel().round(5).tolist(),
                    "indices": f.astype("int64").ravel().tolist()}

        vlakken = {k: plat(g["v"], g["n"], g["f"]) for k, g in
                   cilinder_geometrie(config.diameter, config.hoogte, config.segmenten).items()}
        def kleur(b) -> list[float] | None:  # eerste rgb-waarde in de bsdf: de albedo van het item
            if isinstance(b, dict):
                if b.get("type") == "rgb":
                    return list(b["value"])
                return next((k for v in b.values() if (k := kleur(v))), None)
            return None

        inhoud = [{"laag": li, "soort": it.soort, "kleur": kleur(it.bsdf), **plat(it.posities(), it.n, it.f)}
                  for li, its in enumerate(plaats_of_422(config, ("body",))) for it in its]
        from carbonne.core.poten import poot_geometrieen, vloer_y

        poten = [plat(g["v"], g["n"], g["f"]) for g in poot_geometrieen(config)]
        return {"diameter": config.diameter, "hoogte": config.hoogte, "vlakken": vlakken, "inhoud": inhoud,
                "poten": poten, "vloer_y": vloer_y(config)}

    @app.get("/api/hdri/{naam}")
    def hdri(naam: str) -> FileResponse:
        if naam not in env.OMGEVINGEN:
            raise HTTPException(404, f"onbekende omgeving {naam!r}")
        return FileResponse(hdri_1k(naam, cache_map), media_type="application/octet-stream",
                            filename=f"{naam}_1k.hdr")

    # --- renders ---
    def job_of_404(job_id: str):
        job = jobs.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "onbekende render")
        return job

    @app.post("/api/render", status_code=202)
    def render_start(aanvraag: RenderAanvraag) -> dict:
        plaats_of_422(aanvraag.config, ("body", "config"))
        job = jobs.indienen(aanvraag.config, aanvraag.opties, aanvraag.herkomst)
        return {"id": job.id, "status": job.status}

    @app.get("/api/render/{job_id}")
    def render_status(job_id: str) -> dict:
        return job_of_404(job_id).momentopname(met_beeld=False)

    @app.delete("/api/render/{job_id}")
    def render_annuleer(job_id: str) -> dict:
        job = jobs.annuleer(job_id)
        if job is None:
            raise HTTPException(404, "onbekende render")
        return {"id": job.id, "status": job.status}

    @app.websocket("/api/render/{job_id}")
    async def render_ws(ws: WebSocket, job_id: str) -> None:
        job = jobs.jobs.get(job_id)
        if job is None:
            await ws.close(code=4404)
            return
        await ws.accept()
        gezien = -1
        try:
            while True:
                if job.versie != gezien:
                    gezien = job.versie
                    await ws.send_json(job.momentopname())
                    if job.status in EINDSTATEN:
                        break
                await asyncio.sleep(0.1)
            await ws.close()
        except WebSocketDisconnect:
            pass  # de render loopt door; annuleren gaat via DELETE

    @app.get("/api/render/{job_id}/result.png")
    def result_png(job_id: str) -> Response:
        job = job_of_404(job_id)
        if job.resultaat is None:
            raise HTTPException(409, f"render is {job.status}")
        return Response(job.resultaat.png, media_type="image/png")

    @app.get("/api/render/{job_id}/result.exr")
    def result_exr(job_id: str) -> FileResponse:
        job = job_of_404(job_id)
        if job.resultaat is None:
            raise HTTPException(409, f"render is {job.status}")
        return FileResponse(jobs.exr_pad(job), media_type="image/x-exr", filename=f"{job.id}.exr")

    @app.get("/api/render/{job_id}/herkomst")
    def render_herkomst(job_id: str, x: float | None = None, y: float | None = None, r: float = Query(2.0, gt=0),
                        x0: float | None = None, y0: float | None = None, x1: float | None = None,
                        y1: float | None = None) -> dict:
        """Herkomst van de kleur in een punt (`x`, `y`, `r`) of rechthoek (`x0`, `y0`, `x1`, `y1`), in pixels van
        het resultaatbeeld. Rekent op het bewaarde resultaat; er wordt niets opnieuw gerenderd."""
        from carbonne.core.herkomst import herkomst_van
        from carbonne.core.herkomst_cli import staal_rgb8

        job = job_of_404(job_id)
        if job.resultaat is None:
            raise HTTPException(409, f"render is {job.status}")
        if not job.herkomst:
            raise HTTPException(409, "render is niet gestart met herkomst: true")
        if None not in (x0, y0, x1, y1) and x is None and y is None:
            gebied: tuple = (x0, y0, x1, y1)
        elif x is not None and y is not None and x0 is y0 is x1 is y1 is None:
            gebied = (x, y)
        else:
            raise HTTPException(422, "geef x en y (met r), of x0, y0, x1 en y1")
        try:
            h = herkomst_van(job.resultaat.beeld, gebied, r)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        hx = lambda rgb: "#{:02x}{:02x}{:02x}".format(*staal_rgb8(rgb))
        d = asdict(h)
        d["straal"] = r if len(gebied) == 2 else None
        d["hex"] = hx(h.rgb)
        for c, cat in zip(d["categorieen"], h.categorieen, strict=True):
            c["hex"], c["hex_per_pad"] = hx(cat.rgb), hx(cat.rgb_per_pad)
        return d

    @app.get("/api/render/{job_id}/herkomst.npz")
    def herkomst_npz(job_id: str) -> FileResponse:
        """Het ruwe resultaat met alle kanalen (bronkanalen en padstatistieken): `beeld` (h, w, c) en `kanaalnamen`."""
        job = job_of_404(job_id)
        if job.resultaat is None:
            raise HTTPException(409, f"render is {job.status}")
        if not job.herkomst:
            raise HTTPException(409, "render is niet gestart met herkomst: true")
        return FileResponse(jobs.npz_pad(job), media_type="application/octet-stream", filename=f"{job.id}.npz")

    # --- wat-als-reeksen ---
    def reeks_of_404(reeks_id: str):
        job = jobs.reeksen.get(reeks_id)
        if job is None:
            raise HTTPException(404, "onbekende reeks")
        return job

    @app.get("/api/reeks/parameters")
    def reeks_parameters() -> list[dict]:
        return PARAMETERS

    @app.post("/api/reeks", status_code=202)
    def reeks_start(a: ReeksAanvraag) -> dict:
        if len(a.gebied) not in (2, 4):
            raise HTTPException(422, "gebied is [x, y] of [x0, y0, x1, y1]")
        plaats_of_422(a.config, ("body", "config"))
        try:  # valideer pad en alle waarden vooraf: geen job voor een reeks die toch faalt
            for w in a.waarden:
                zet_pad(a.config, a.parameter, w)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        job = jobs.indienen_reeks(a.config, a.parameter, a.waarden, tuple(a.gebied), straal=a.straal,
                                  breedte=a.breedte, spp=a.spp, seed=a.seed, ev=a.ev)
        return {"id": job.id, "status": job.status}

    @app.get("/api/reeks/{reeks_id}")
    def reeks_status(reeks_id: str) -> dict:
        """Status plus, zodra er metingen zijn, de JSON uit T14 en de URL's van de deelbeelden."""
        job = reeks_of_404(reeks_id)
        d = job.momentopname()
        r = job.resultaat
        if r is not None and r.metingen:
            d["resultaat"] = r.naar_dict()
            from carbonne.core.herkomst_cli import staal_rgb8

            hx = lambda rgb: "#{:02x}{:02x}{:02x}".format(*staal_rgb8(rgb))
            for m, dm in zip(r.metingen, d["resultaat"]["metingen"], strict=True):  # stalen zoals in de PNG's
                dm["hex"] = hx(m.rgb)
                for c, dc in zip(m.herkomst.categorieen, dm["herkomst"]["categorieen"], strict=True):
                    dc["hex"], dc["hex_per_pad"] = hx(c.rgb), hx(c.rgb_per_pad)
            basis = f"/api/reeks/{job.id}"
            d["urls"] = {"beelden": [f"{basis}/beeld/{i}.png" for i in range(len(r.metingen))],
                         "contact": f"{basis}/contact.png", "grafiek": f"{basis}/grafiek.png"}
        return d

    @app.delete("/api/reeks/{reeks_id}")
    def reeks_annuleer(reeks_id: str) -> dict:
        reeks_of_404(reeks_id)
        job = jobs.annuleer(reeks_id)
        return {"id": job.id, "status": job.status}

    @app.websocket("/api/reeks/{reeks_id}")
    async def reeks_ws(ws: WebSocket, reeks_id: str) -> None:
        job = jobs.reeksen.get(reeks_id)
        if job is None:
            await ws.close(code=4404)
            return
        await ws.accept()
        gezien = -1
        try:
            while True:
                if job.versie != gezien:
                    gezien = job.versie
                    await ws.send_json(job.momentopname())
                    if job.status in EINDSTATEN:
                        break
                await asyncio.sleep(0.1)
            await ws.close()
        except WebSocketDisconnect:
            pass  # de reeks loopt door; annuleren gaat via DELETE

    def reeks_klaar(reeks_id: str):
        job = reeks_of_404(reeks_id)
        if job.resultaat is None or not job.resultaat.metingen:
            raise HTTPException(409, f"reeks is {job.status} en heeft nog geen metingen")
        return job

    @app.get("/api/reeks/{reeks_id}/beeld/{nr}.png")
    def reeks_beeld(reeks_id: str, nr: int) -> Response:
        from carbonne.render.uitvoer import png_bytes, tonemap_srgb

        job = reeks_klaar(reeks_id)
        if not 0 <= nr < len(job.resultaat.beelden):
            raise HTTPException(404, "onbekend deelbeeld")
        return Response(png_bytes(tonemap_srgb(job.resultaat.beelden[nr], job.params["ev"])), media_type="image/png")

    @app.get("/api/reeks/{reeks_id}/contact.png")
    def reeks_contact(reeks_id: str) -> Response:
        from carbonne.analyse.uitvoer import contactblad_png

        job = reeks_klaar(reeks_id)
        return Response(contactblad_png(job.resultaat, job.params["ev"]), media_type="image/png")

    @app.get("/api/reeks/{reeks_id}/grafiek.png")
    def reeks_grafiek(reeks_id: str) -> Response:
        from carbonne.analyse.uitvoer import grafiek_png

        return Response(grafiek_png(reeks_klaar(reeks_id).resultaat), media_type="image/png")

    # --- configs ---
    def config_pad(naam: str) -> Path:
        if not NAAM_RE.match(naam):
            raise HTTPException(422, "naam: 1-64 tekens uit A-Z a-z 0-9 _ -")
        return configs_map / f"{naam}.json"

    @app.get("/api/configs")
    def configs_lijst() -> list[str]:
        return sorted(p.stem for p in configs_map.glob("*.json")) if configs_map.exists() else []

    @app.get("/api/configs/{naam}")
    def configs_lees(naam: str) -> dict:
        pad = config_pad(naam)
        if not pad.exists():
            raise HTTPException(404, "onbekende config")
        try:
            return TableConfig.model_validate(json.loads(pad.read_text())).model_dump(mode="json")
        except (ValidationError, ValueError) as e:
            raise HTTPException(500, f"opgeslagen config is ongeldig: {e}") from e

    @app.post("/api/configs", status_code=201)
    def configs_opslaan(inv: ConfigOpslaan) -> dict:
        pad = config_pad(inv.naam)
        configs_map.mkdir(parents=True, exist_ok=True)
        pad.write_text(json.dumps(inv.config.model_dump(mode="json"), indent=1))
        return {"naam": inv.naam}

    # --- verfbibliotheek (T18/T19); vaste paden vóór /{slug} ---
    def staal(v: Vertaling) -> str:
        return "#" + "".join(f"{round(lineair_naar_srgb(min(1.0, max(0.0, c))) * 255):02x}" for c in v.paint.color)

    def vertaal_of_422(e: VerfEigenschappen) -> Vertaling:
        try:
            return vertaal_verf(e)
        except VerfFout as ex:
            raise HTTPException(422, str(ex)) from ex

    def slug_of_404(slug: str):
        try:
            return bib.laad(slug, verven_map)
        except KeyError as ex:
            raise HTTPException(404, str(ex.args[0])) from ex
        except ValueError as ex:
            raise HTTPException(422, str(ex)) from ex

    @app.get("/api/verven/schema")
    def verven_schema() -> dict:
        return VerfEigenschappen.model_json_schema()

    @app.post("/api/verven/vertaal")
    def verven_vertaal(e: VerfEigenschappen) -> dict:
        return vertaal_of_422(e).model_dump(mode="json")

    @app.get("/api/verven/chatgpt-vraag")
    def verven_chatgpt_vraag(merk: str = "", product: str = "", kleur: str = "") -> dict:
        return {"vraag": vraag(merk, product, kleur)}

    @app.post("/api/verven/uit-tekst")
    def verven_uit_tekst(inv: TekstAanvraag) -> dict:
        try:
            e = uit_tekst(inv.tekst)
        except TekstFout as ex:
            raise HTTPException(422, {"melding": str(ex), "veld": ex.veld}) from ex
        return {"eigenschappen": e.model_dump(mode="json"), "vertaling": vertaal_of_422(e).model_dump(mode="json")}

    @app.get("/api/verven")
    def verven_lijst() -> list[dict]:
        return [{"slug": i.slug, "naam": " ".join(x for x in (i.eigenschappen.merk, i.eigenschappen.product,
                                                              i.eigenschappen.kleurnaam) if x) or i.slug,
                 "staal": staal(i.vertaling)} for i in bib.lijst(verven_map)]

    @app.get("/api/verven/{slug}")
    def verven_lees(slug: str) -> dict:
        return slug_of_404(slug).model_dump(mode="json")

    @app.post("/api/verven", status_code=201)
    def verven_bewaar(e: VerfEigenschappen, overschrijf: int = 0, slug: str | None = None) -> dict:
        vertaal_of_422(e)
        try:
            return bib.bewaar(e, overschrijf=bool(overschrijf), map_=verven_map, slug=slug).model_dump(mode="json")
        except FileExistsError as ex:
            raise HTTPException(409, str(ex)) from ex
        except ValueError as ex:
            raise HTTPException(422, str(ex)) from ex

    @app.delete("/api/verven/{slug}")
    def verven_verwijder(slug: str) -> dict:
        slug_of_404(slug)
        bib.verwijder(slug, verven_map)
        return {"slug": slug}

    if web_map.exists():  # laatst: anders vangt de statische mount de /api-routes af
        app.mount("/", StaticFiles(directory=web_map, html=True), name="web")
    return app


def main(argv: list[str] | None = None) -> None:
    """`carbonne-app [start] [--port N]`: alleen 127.0.0.1 (standaard poort 8011); serveert ook web/."""
    import argparse

    import uvicorn

    p = argparse.ArgumentParser(prog="carbonne-app", description=main.__doc__)
    p.add_argument("opdracht", nargs="?", default="start", choices=["start"])
    p.add_argument("--port", type=int, default=8011)
    a = p.parse_args(argv)
    uvicorn.run(maak_app(), host="127.0.0.1", port=a.port)


if __name__ == "__main__":
    main()
