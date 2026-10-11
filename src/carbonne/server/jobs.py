"""Renderjobs: een wachtrij met een werkthread (één render tegelijk)."""

from __future__ import annotations

import base64
import queue
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from carbonne.core.config import TableConfig
from carbonne.render.pipeline import RenderOpties, RenderResultaat, Voortgang, render
from carbonne.render.uitvoer import schrijf_exr

Renderer = Callable[[TableConfig, RenderOpties, Callable[[Voortgang], None] | None, threading.Event | None],
                    RenderResultaat]

WACHTEND, BEZIG, KLAAR, FOUT, GEANNULEERD = "wachtend", "bezig", "klaar", "fout", "geannuleerd"
EINDSTATEN = (KLAAR, FOUT, GEANNULEERD)


@dataclass
class Job:
    id: str
    config: TableConfig
    opties: RenderOpties
    status: str = WACHTEND
    versie: int = 0  # telt op bij elke wijziging; websockets pollen hierop
    voortgang: dict | None = None
    tussen_png: bytes | None = None
    resultaat: RenderResultaat | None = None
    fout: str | None = None
    annuleer: threading.Event = field(default_factory=threading.Event)
    exr_pad: Path | None = None

    def momentopname(self, met_beeld: bool = True) -> dict:
        d = {"id": self.id, "status": self.status, "versie": self.versie, "voortgang": self.voortgang,
             "fout": self.fout}
        if self.resultaat is not None:
            r = self.resultaat
            d["resultaat"] = {"spp": r.spp, "ruis": r.ruis, "tijd_s": r.tijd_s, "reden": r.reden,
                              "sleutel": r.sleutel, "uit_cache": r.uit_cache}
        if met_beeld and self.tussen_png is not None:
            d["png_base64"] = base64.b64encode(self.tussen_png).decode()
        return d


class JobManager:
    """Neemt jobs aan en draait ze één voor één in een daemonthread."""

    def __init__(self, renderer: Renderer = render, cache_map: Path = Path("cache"),
                 uit_map: Path = Path("out/server")) -> None:
        self.renderer = renderer
        self.cache_map = cache_map
        self.uit_map = uit_map
        self.jobs: dict[str, Job] = {}
        self._rij: queue.Queue[Job | None] = queue.Queue()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._werk, name="render-werker", daemon=True)
        self._thread.start()

    def indienen(self, config: TableConfig, opties: RenderOpties) -> Job:
        opties = opties.model_copy(update={"cache_map": self.cache_map})
        job = Job(uuid.uuid4().hex[:12], config, opties)
        with self._lock:
            self.jobs[job.id] = job
        self._rij.put(job)
        return job

    def annuleer(self, job_id: str) -> Job | None:
        job = self.jobs.get(job_id)
        if job is None:
            return None
        with self._lock:
            if job.status in (WACHTEND, BEZIG):
                job.annuleer.set()
                if job.status == WACHTEND:  # de werker slaat hem over
                    job.status = GEANNULEERD
                    job.versie += 1
        return job

    def exr_pad(self, job: Job) -> Path:
        """Pad van de EXR van een klaar resultaat (cachemap of een los geschreven bestand)."""
        r = job.resultaat
        assert r is not None
        if r.pad is not None and (r.pad / "beeld.exr").exists():
            return r.pad / "beeld.exr"
        if job.exr_pad is None or not job.exr_pad.exists():
            self.uit_map.mkdir(parents=True, exist_ok=True)
            job.exr_pad = self.uit_map / f"{job.id}.exr"
            schrijf_exr(job.exr_pad, r.beeld, r.kanaalnamen)
        return job.exr_pad

    def _zet(self, job: Job, **kw) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(job, k, v)
            job.versie += 1

    def _werk(self) -> None:
        while True:
            job = self._rij.get()
            if job is None:
                return
            if job.status == GEANNULEERD:
                continue
            self._zet(job, status=BEZIG)
            t0 = time.perf_counter()

            def voortgang(v: Voortgang, job: Job = job, t0: float = t0) -> None:
                self._zet(job, tussen_png=v.png, voortgang={
                    "pass_nr": v.pass_nr, "spp": v.spp, "max_spp": v.max_spp, "ruis": v.ruis,
                    "tijd_s": v.tijd_s, "klaar": v.klaar, "reden": v.reden})

            try:
                r = self.renderer(job.config, job.opties, voortgang, job.annuleer)
            except Exception as e:  # noqa: BLE001 - elke renderfout wordt aan de client gemeld
                status = GEANNULEERD if job.annuleer.is_set() else FOUT
                self._zet(job, status=status, fout=f"{type(e).__name__}: {e}")
                continue
            self._zet(job, resultaat=r, tussen_png=r.png,
                      status=GEANNULEERD if r.reden == "geannuleerd" else KLAAR)
