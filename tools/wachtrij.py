#!/usr/bin/env python3
"""Wachtrij-gereedschap voor docs/tasks/T*.md en docs/queue/state.json (alleen stdlib).

Gebruik:
  wachtrij.py [status]               tabel van alle taken
  wachtrij.py volgende [--n N]       uitvoerbare taken (afhankelijkheden klaar, zelf nog niet gestart)
  wachtrij.py zet TNN STATUS         status in de dossierkop zetten (klaar zet ook laatste_meting)
  wachtrij.py controle               koppen valideren: velden, statussen, afhankelijkheden, cycli
  wachtrij.py state                  state.json tonen
  wachtrij.py start TNN PAD BRANCH [AGENT_ID] [MODEL]
  wachtrij.py geparkeerd TNN "vraag"
  wachtrij.py gemerged TNN
  wachtrij.py next-step "tekst voor een koude sessie"
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "docs" / "tasks"
STATE = ROOT / "docs" / "queue" / "state.json"

STATUSSEN = ["gepland", "bezig", "geparkeerd", "geblokkeerd", "klaar", "geschrapt"]
VELDEN = ["taak", "titel", "status", "deelsysteem", "hangt_af_van", "model",
          "afrondingscriterium", "zichtbare_stap", "laatste_meting"]


def lees_kop(pad: Path) -> dict:
    tekst = pad.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", tekst, re.DOTALL)
    if not m:
        return {"_fout": "geen kop"}
    kop: dict = {}
    for regel in m.group(1).splitlines():
        if ":" not in regel:
            continue
        sleutel, waarde = regel.split(":", 1)
        waarde = waarde.strip()
        if waarde.startswith("[") and waarde.endswith("]"):
            kop[sleutel.strip()] = [v.strip() for v in waarde[1:-1].split(",") if v.strip()]
        else:
            kop[sleutel.strip()] = waarde.strip('"')
    return kop


def alle_taken() -> dict[str, dict]:
    taken = {}
    for pad in sorted(TASKS.glob("T*.md"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)):
        kop = lees_kop(pad)
        kop["_pad"] = pad
        taken[pad.stem] = kop
    return taken


def cmd_status(_: list[str]) -> int:
    taken = alle_taken()
    print(f"{'taak':5} {'status':11} {'deel':11} {'hangt af van':14} titel")
    for naam, k in taken.items():
        deps = ",".join(k.get("hangt_af_van", [])) or "-"
        print(f"{naam:5} {k.get('status', '?'):11} {k.get('deelsysteem', '?'):11} {deps:14} {k.get('titel', '')}")
    return 0


def uitvoerbaar(taken: dict[str, dict]) -> list[str]:
    klaar = {n for n, k in taken.items() if k.get("status") == "klaar"}
    return [n for n, k in taken.items()
            if k.get("status") == "gepland" and set(k.get("hangt_af_van", [])) <= klaar]


def cmd_volgende(args: list[str]) -> int:
    n = int(args[args.index("--n") + 1]) if "--n" in args else 1
    lijst = uitvoerbaar(alle_taken())[:n]
    print("\n".join(lijst) if lijst else "(niets uitvoerbaar)")
    return 0


def cmd_zet(args: list[str]) -> int:
    naam, status = args[0].upper(), args[1]
    if status not in STATUSSEN:
        print(f"onbekende status {status!r}; kies uit {STATUSSEN}")
        return 1
    pad = TASKS / f"{naam}.md"
    tekst = pad.read_text(encoding="utf-8")
    tekst = re.sub(r"^status: .*$", f"status: {status}", tekst, count=1, flags=re.MULTILINE)
    if status == "klaar":
        tekst = re.sub(r"^laatste_meting: .*$", f"laatste_meting: {dt.date.today()}", tekst, count=1, flags=re.MULTILINE)
    pad.write_text(tekst, encoding="utf-8")
    print(f"{naam}: {status}")
    return 0


def cmd_controle(_: list[str]) -> int:
    taken = alle_taken()
    fouten = []
    for naam, k in taken.items():
        if "_fout" in k:
            fouten.append(f"{naam}: {k['_fout']}")
            continue
        for veld in VELDEN:
            if veld not in k:
                fouten.append(f"{naam}: veld {veld} ontbreekt")
        if k.get("taak") != naam:
            fouten.append(f"{naam}: taak-veld is {k.get('taak')!r}")
        if k.get("status") not in STATUSSEN:
            fouten.append(f"{naam}: status {k.get('status')!r} onbekend")
        for dep in k.get("hangt_af_van", []):
            if dep not in taken:
                fouten.append(f"{naam}: hangt af van onbekende taak {dep}")
    # cycli
    bezocht: dict[str, int] = {}

    def dfs(n: str, pad: list[str]) -> None:
        if bezocht.get(n) == 1:
            fouten.append("cyclus: " + " -> ".join(pad + [n]))
            return
        if bezocht.get(n) == 2 or n not in taken:
            return
        bezocht[n] = 1
        for d in taken[n].get("hangt_af_van", []):
            dfs(d, pad + [n])
        bezocht[n] = 2

    for n in taken:
        dfs(n, [])
    print("\n".join(fouten) if fouten else "ok")
    return 1 if fouten else 0


def lees_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"lopend": {}, "geparkeerd": {}, "gemerged": [], "next_step": ""}


def schrijf_state(state: dict) -> None:
    state["bijgewerkt"] = dt.datetime.now().isoformat(timespec="seconds")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cmd_state(_: list[str]) -> int:
    print(json.dumps(lees_state(), indent=2, ensure_ascii=False))
    return 0


def cmd_start(args: list[str]) -> int:
    naam, pad, branch = args[0].upper(), args[1], args[2]
    s = lees_state()
    s["geparkeerd"].pop(naam, None)
    s["lopend"][naam] = {"worktree": pad, "branch": branch,
                         "agent_id": args[3] if len(args) > 3 else None,
                         "model": args[4] if len(args) > 4 else None,
                         "gestart": dt.datetime.now().isoformat(timespec="seconds")}
    schrijf_state(s)
    return cmd_zet([naam, "bezig"])


def cmd_geparkeerd(args: list[str]) -> int:
    naam = args[0].upper()
    s = lees_state()
    s["geparkeerd"][naam] = {"vraag": args[1], **s["lopend"].pop(naam, {})}
    schrijf_state(s)
    return cmd_zet([naam, "geparkeerd"])


def cmd_gemerged(args: list[str]) -> int:
    naam = args[0].upper()
    s = lees_state()
    s["lopend"].pop(naam, None)
    s["geparkeerd"].pop(naam, None)
    s["gemerged"].append(naam)
    schrijf_state(s)
    return 0


def cmd_next_step(args: list[str]) -> int:
    s = lees_state()
    s["next_step"] = args[0]
    schrijf_state(s)
    return 0


COMMANDO = {"status": cmd_status, "volgende": cmd_volgende, "zet": cmd_zet, "controle": cmd_controle,
            "state": cmd_state, "start": cmd_start, "geparkeerd": cmd_geparkeerd,
            "gemerged": cmd_gemerged, "next-step": cmd_next_step}

if __name__ == "__main__":
    argv = sys.argv[1:] or ["status"]
    if argv[0] not in COMMANDO:
        print(__doc__)
        sys.exit(2)
    sys.exit(COMMANDO[argv[0]](argv[1:]))
