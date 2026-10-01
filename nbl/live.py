"""Živé statistiky všech právě hraných zápasů ligy.

    python -m nbl.live --out live-out             # sleduje, dokud nějaký zápas běží / brzy začne
    python -m nbl.live --out live-out --once      # jeden průchod (test)
    python -m nbl.live --out live-out --publish   # out je git checkout větve „live“ -> commit + force push

Každých --interval sekund stáhne data.json všech zápasů v živém okně (výkop −20 min … +3,5 h),
spočítá stejný rozbor jako pro dohrané zápasy (metrics.analyze_game, včetně live bloku: kdo je
na hřišti, aktuální série, týmové fauly, faulové potíže) a zapíše:

    <out>/index.json                 přehled živých/dnešních zápasů (skóre, perioda, čas)
    <out>/<fibaId>.json              plný živý rozbor zápasu
    <out>/<fibaId>/<epoch/5>.json    totéž po 5s oknech — raw.githubusercontent.com drží soubory
    <out>/index/<epoch/5>.json       v cache 5 min, nové jméno = vždy čerstvá data (jako srsni-data)

Dohraný zápas (v pbp „game end“) se uloží do archivu data/<sezóna>/raw/, odkud ho převezme
běžný build sezóny.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import fiba, metrics, schedule
from .build import fill_from_othermatches, load_schedule, raw_path, season_dir
from .util import write_json, write_json_gz

WINDOW_BEFORE = timedelta(minutes=20)
WINDOW_AFTER = timedelta(hours=3, minutes=30)
BUCKET_SECS = 5
KEEP_BUCKETS = 24          # 2 minuty historie po 5 s
END_CONFIRM = 3            # kolikrát za sebou musí být vidět konec zápasu


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def in_window(f: dict, now: datetime) -> bool:
    if not f.get("datetime"):
        return False
    t = datetime.fromisoformat(f["datetime"])
    return t - WINDOW_BEFORE <= now <= t + WINDOW_AFTER


def summary(f: dict, g: dict | None) -> dict:
    row = {"fibaId": f.get("fibaId"), "nblId": f.get("nblId"), "datetime": f.get("datetime"),
           "round": f.get("round"), "home": f.get("home"), "away": f.get("away"),
           "homeSlug": f.get("homeSlug"), "awaySlug": f.get("awaySlug"),
           "status": "scheduled", "score": None, "period": None, "clock": None,
           "file": f"{f['fibaId']}.json" if f.get("fibaId") else None}
    if g:
        row.update(status=g["status"], score=[g["home"]["score"], g["away"]["score"]],
                   period=g["periodLabel"], clock=g["clock"],
                   leader=(g["home"]["label"] if g["home"]["score"] > g["away"]["score"]
                           else g["away"]["label"] if g["away"]["score"] > g["home"]["score"] else None),
                   currentRun=(g.get("live") or {}).get("currentRun"))
    return row


def prune_buckets(d: Path, bucket: int) -> None:
    if not d.exists():
        return
    for p in d.glob("*.json"):
        if p.stem.isdigit() and int(p.stem) < bucket - KEEP_BUCKETS:
            p.unlink()


def write_bucketed(out: Path, name: str, data: dict, bucket: int) -> None:
    write_json(out / f"{name}.json", data, compact=True)
    write_json(out / name / f"{bucket}.json", data, compact=True)
    prune_buckets(out / name, bucket)


def publish(out: Path, msg: str) -> None:
    """Jediný commit bez historie + force push (větev live zůstává malá), jako live-relay v srsni-data."""
    def git(*args, check=True):
        return subprocess.run(["git", "-C", str(out), *args], check=check, capture_output=True, text=True)
    git("add", "-A", ".")
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return
    if git("commit", "-q", "--amend", "-m", msg, check=False).returncode != 0:
        git("commit", "-q", "-m", msg, check=False)
    r = git("push", "-q", "-f", "origin", "HEAD:live", check=False)
    if r.returncode != 0:
        print(f"WARN push: {r.stderr.strip()[-300:]}", file=sys.stderr)


def tick(season_label: str, out: Path, fixtures: list[dict], state: dict, session) -> dict:
    now = now_utc()
    sdir = season_dir(season_label)
    bucket = int(time.time()) // BUCKET_SECS
    todays = [f for f in fixtures if f.get("datetime") and
              datetime.fromisoformat(f["datetime"]).astimezone(schedule.PRAGUE).date() == now.astimezone(schedule.PRAGUE).date()]
    active = [f for f in fixtures if in_window(f, now) and f.get("fibaId") and f["fibaId"] not in state["done"]]
    games = {}
    for f in active:
        raw = fiba.fetch(f["fibaId"], session)
        if raw is None:
            continue
        if fill_from_othermatches(fixtures, raw, f["datetime"]):
            state["dirtySchedule"] = True
        g = metrics.analyze_game(raw, {"fibaId": f["fibaId"], **{k: f.get(k) for k in ("nblId", "round", "roundNum", "phase", "datetime", "date", "time")}})
        g["fibaId"] = f["fibaId"]
        g["updatedAt"] = now.isoformat(timespec="seconds")
        games[f["fibaId"]] = g
        write_bucketed(out, str(f["fibaId"]), metrics.public(g), bucket)
        if g["status"] == "final":
            state["ends"][f["fibaId"]] = state["ends"].get(f["fibaId"], 0) + 1
            if state["ends"][f["fibaId"]] >= END_CONFIRM:
                write_json_gz(raw_path(sdir, f["fibaId"]), raw)
                state["done"].add(f["fibaId"])
                state["finished"].append(f["fibaId"])
                print(f"konec zápasu {f['fibaId']} ({f.get('home')} – {f.get('away')}), uloženo do archivu")
        else:
            state["ends"][f["fibaId"]] = 0
    rows = [summary(f, games.get(f.get("fibaId")) or state["last"].get(f.get("fibaId"))) for f in sorted(todays, key=lambda x: x["datetime"])]
    state["last"].update(games)
    index = {"season": season_label, "updatedAt": now.isoformat(timespec="seconds"),
             "live": [r for r in rows if r["status"] == "live"], "today": rows}
    write_bucketed(out, "index", index, bucket)
    return {"active": len(active), "fetched": len(games), "live": len(index["live"])}


def upcoming_soon(fixtures: list[dict], now: datetime, within: timedelta) -> bool:
    return any(f.get("datetime") and now <= datetime.fromisoformat(f["datetime"]) - WINDOW_BEFORE <= now + within
               for f in fixtures)


def main(argv=None) -> int:
    import requests
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", default=None)
    ap.add_argument("--out", default="live-out")
    ap.add_argument("--interval", type=float, default=10)
    ap.add_argument("--max-hours", type=float, default=5.8, help="strop běhu (GitHub job má limit 6 h)")
    ap.add_argument("--wait-minutes", type=float, default=90, help="jak dlouho čekat na zápas, který teprve začne")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--publish", action="store_true", help="po každém průchodu commit + force push větve live")
    a = ap.parse_args(argv)

    season_label = a.season or schedule.current_season()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sdir = season_dir(season_label)
    fixtures = load_schedule(sdir)
    if not fixtures:
        print(f"Rozpis {sdir / 'schedule.json'} je prázdný — spusť nejdřív python -m nbl.build.")
        return 0
    session = requests.Session()
    state = {"done": {f["fibaId"] for f in fixtures if f.get("fibaId") and raw_path(sdir, f["fibaId"]).exists()},
             "ends": {}, "finished": [], "last": {}, "dirtySchedule": False}
    deadline = now_utc() + timedelta(hours=a.max_hours)
    while now_utc() < deadline:
        t0 = time.time()
        st = tick(season_label, out, fixtures, state, session)
        if a.publish:
            publish(out, f"live {now_utc().strftime('%H:%M:%S')} ({st['live']} živě)")
        if a.once:
            print(st)
            break
        now = now_utc()
        if st["active"] == 0:
            if not upcoming_soon(fixtures, now, timedelta(minutes=a.wait_minutes)):
                print("Žádný živý ani blížící se zápas — konec.")
                break
            time.sleep(60)
            continue
        time.sleep(max(1.0, a.interval - (time.time() - t0)))
    if state["finished"]:
        print("DOHRANÉ:", " ".join(map(str, state["finished"])))
    if state["dirtySchedule"]:
        # nově zjištěná FIBA ID z othermatches zapsat do rozpisu
        from .util import read_json
        doc = read_json(sdir / "schedule.json", {}) or {}
        doc["fixtures"] = fixtures
        write_json(sdir / "schedule.json", doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
