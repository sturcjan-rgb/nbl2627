"""Sestaví všechna JSON data sezóny do data/<sezóna>/.

    python -m nbl.build                    # rozpis + FIBA + přepočet (výchozí sezóna podle data)
    python -m nbl.build --season 2026/27
    python -m nbl.build --offline          # jen přepočet z archivu raw/ (bez sítě)
    python -m nbl.build --debug            # vypíše ukázku HTML rozpisu (ladění scraperu)

Struktura výstupu (data/2026-27/):
    index.json              manifest: sezóna, čas, počty, týmy, cesty k souborům
    schedule.json           všechny zápasy ligy (odehrané i budoucí, s FIBA ID a odkazy)
    standings.json          tabulka
    league.json             ligové průměry + srovnávací tabulka týmů (ratingy, four factors, pořadí)
    leaders.json            žebříčky hráčů
    players.json            všichni hráči (sezónní součty, průměry, pokročilé metriky)
    teams/<slug>.json       sezóna týmu (+ hráči s deníkem, pětky, zápasy)
    matches/<fibaId>.json   rozbor zápasu
    raw/<fibaId>.json.gz    archiv surového FIBA data.json (zdroj pravdy pro přepočet)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import fiba, metrics, schedule, season
from .teams import identify
from .util import read_json, write_json, write_json_gz

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("NBL_DATA_DIR") or ROOT / "data")


def season_dir(season_label: str) -> Path:
    return DATA / schedule.season_key(season_label)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ rozpis

def load_schedule(sdir: Path) -> list[dict]:
    return (read_json(sdir / "schedule.json", {}) or {}).get("fixtures", [])


def update_schedule(season_label: str, fixtures: list[dict], *, debug: bool = False) -> tuple[list[dict], dict]:
    fetcher = schedule.Fetcher()
    res = schedule.discover(season_label, fetcher, fixtures, debug=debug)
    found = res["fixtures"]
    if not found and fixtures:
        print("WARN rozpis se nepodařilo stáhnout — ponechávám uložený", file=sys.stderr)
        return fixtures, res
    n = schedule.resolve_fiba_ids(found, fetcher)
    print(f"rozpis: {len(found)} zápasů, {len(res['teams'])} týmů, zdroje {res['sources']}, nově FIBA ID: {n}")
    return found, res


# ------------------------------------------------------------------ FIBA

def raw_path(sdir: Path, fid: int) -> Path:
    return sdir / "raw" / f"{fid}.json.gz"


def fill_from_othermatches(fixtures: list[dict], raw: dict, ref_date: str | None) -> int:
    """FIBA ID souběžných zápasů z othermatches -> zápasy rozpisu bez FIBA ID (stejné týmy, ±2 dny)."""
    n = 0
    for om in fiba.other_matches(raw):
        hs, as_ = identify(om["home"] or "")[0], identify(om["away"] or "")[0]
        for f in fixtures:
            if f.get("fibaId") or f.get("homeSlug") != hs or f.get("awaySlug") != as_:
                continue
            if ref_date and f.get("datetime"):
                d = abs((datetime.fromisoformat(f["datetime"]) - datetime.fromisoformat(ref_date)).days)
                if d > 2:
                    continue
            f["fibaId"] = om["fibaId"]
            schedule.finalize(f)
            n += 1
    return n


def fetch_games(sdir: Path, fixtures: list[dict]) -> dict:
    """Stáhne FIBA data pro zápasy, které už začaly a ještě nemají archiv dohraného stavu."""
    import requests
    session = requests.Session()
    now = now_utc()
    stats = {"fetched": 0, "final": 0, "live": 0, "missing": 0, "idsFromOther": 0}
    queue = [f for f in fixtures if f.get("fibaId") and f.get("datetime")]
    seen = set()
    while queue:
        f = queue.pop(0)
        fid = f["fibaId"]
        if fid in seen:
            continue
        seen.add(fid)
        kickoff = datetime.fromisoformat(f["datetime"])
        if kickoff - timedelta(minutes=15) > now:
            continue
        rp = raw_path(sdir, fid)
        if rp.exists() and metrics.is_finished(read_json(rp)):
            continue
        raw = fiba.fetch(fid, session)
        if raw is None:
            stats["missing"] += 1
            continue
        stats["fetched"] += 1
        n = fill_from_othermatches(fixtures, raw, f["datetime"])
        stats["idsFromOther"] += n
        if n:  # nově nalezená ID rovnou zpracovat ve stejném běhu
            queue += [x for x in fixtures if x.get("fibaId") and x["fibaId"] not in seen]
        if metrics.is_finished(raw):
            write_json_gz(rp, raw)
            stats["final"] += 1
        else:
            stats["live"] += 1
            # rozehraný stav se do archivu neukládá, jen když už zápas dávno měl skončit
            # (zapisovatel nezadal konec) — pak je to nejlepší data, která máme
            if kickoff + timedelta(hours=6) < now:
                write_json_gz(rp, raw)
    return stats


# ------------------------------------------------------------------ přepočet

def analyze_archive(sdir: Path, fixtures: list[dict]) -> list[dict]:
    by_fid = {f["fibaId"]: f for f in fixtures if f.get("fibaId")}
    games = []
    for rp in sorted((sdir / "raw").glob("*.json.gz")):
        fid = int(rp.name.split(".")[0])
        raw = read_json(rp)
        fx = by_fid.get(fid)
        fixture = {"fibaId": fid, **({k: fx.get(k) for k in ("nblId", "round", "roundNum", "phase", "datetime", "date", "time")} if fx else {})}
        try:
            g = metrics.analyze_game(raw, fixture)
        except Exception as e:  # jeden rozbitý zápas nesmí shodit celou sezónu
            print(f"WARN rozbor {fid} selhal: {e!r}", file=sys.stderr)
            continue
        g["fibaId"] = fid
        if fx:
            # skóre a stav z FIBA mají přednost před tabulkou na webu
            fx["status"] = "final" if g["status"] == "final" else fx.get("status")
            fx["score"] = {"home": g["home"]["score"], "away": g["away"]["score"]}
            if g["home"]["slug"] != fx.get("homeSlug") and g["home"]["slug"] == fx.get("awaySlug"):
                print(f"WARN {fid}: FIBA má domácí/hosty prohozené oproti rozpisu", file=sys.stderr)
        games.append(g)
    return games


def build(season_label: str, *, scrape: bool = True, fetch: bool = True, debug: bool = False) -> dict:
    sdir = season_dir(season_label)
    fixtures = load_schedule(sdir)
    teams_meta = (read_json(sdir / "schedule.json", {}) or {}).get("teams", {})
    if scrape:
        fixtures, res = update_schedule(season_label, fixtures, debug=debug)
        teams_meta.update(res.get("teams") or {})
    if fetch:
        st = fetch_games(sdir, fixtures)
        print(f"FIBA: {st}")
    games = analyze_archive(sdir, fixtures)
    final_games = [g for g in games if g["status"] == "final"]

    for g in games:
        write_json(sdir / "matches" / f"{g['fibaId']}.json", metrics.public(g), compact=True)

    table = season.standings(final_games)
    teams = season.team_seasons(final_games)
    pl = season.players(final_games)
    league_avg = season.league_averages(teams)
    team_games = {s: t["games"] for s, t in teams.items()}
    by_team: dict[str, list] = {}
    for p in pl:
        by_team.setdefault(p["team"], []).append(p)

    generated = now_utc().isoformat(timespec="seconds")
    for f in fixtures:
        schedule.finalize(f)
    fixtures.sort(key=lambda f: (f.get("datetime") or "", f["nblId"]))
    played_fids = {g["fibaId"] for g in games}
    for f in fixtures:
        f["hasStats"] = f.get("fibaId") in played_fids

    write_json(sdir / "schedule.json", {
        "season": season_label, "generatedAt": generated, "source": schedule.SCHEDULE_URL,
        "counts": {"total": len(fixtures), "final": sum(f["status"] == "final" for f in fixtures),
                   "scheduled": sum(f["status"] == "scheduled" for f in fixtures),
                   "withFiba": sum(bool(f.get("fibaId")) for f in fixtures)},
        "teams": teams_meta, "fixtures": fixtures,
    })
    write_json(sdir / "standings.json", {"season": season_label, "generatedAt": generated, "table": table})
    league_rows = []
    for row in table:
        t = teams.get(row["slug"])
        if not t:
            continue
        league_rows.append({
            "slug": t["slug"], "name": t["name"], "label": t["label"], "logo": t["logo"], "games": t["games"],
            "w": row["w"], "l": row["l"], "perGame": t["perGame"], "adv": t["adv"], "oppAdv": t["oppAdv"],
            "factors": t["factors"], "ranks": t["ranks"], "clutch": t["clutch"], "attack": t["attack"],
        })
    write_json(sdir / "league.json", {"season": season_label, "generatedAt": generated,
                                      "averages": league_avg, "teams": league_rows})
    write_json(sdir / "leaders.json", {"season": season_label, "generatedAt": generated,
                                       **season.leaders(pl, team_games)})
    write_json(sdir / "players.json", {"season": season_label, "generatedAt": generated,
                                       "players": season.strip_player_logs(pl)})
    for slug, t in teams.items():
        fx = [f for f in fixtures if slug in (f.get("homeSlug"), f.get("awaySlug"))]
        write_json(sdir / "teams" / f"{slug}.json", {
            "season": season_label, "generatedAt": generated, **t,
            "standing": next((r for r in table if r["slug"] == slug), None),
            "players": by_team.get(slug, []),
            "fixtures": [{k: f.get(k) for k in ("nblId", "fibaId", "round", "datetime", "home", "away",
                                                 "homeSlug", "awaySlug", "status", "score", "links")} for f in fx],
        })

    index = {
        "season": season_label, "generatedAt": generated,
        "counts": {"fixtures": len(fixtures), "final": len(final_games), "teams": len(teams), "players": len(pl)},
        "teams": [{"slug": r["slug"], "name": r["name"], "label": r["label"], "logo": r["logo"],
                   "file": f"teams/{r['slug']}.json"} for r in table],
        "files": {"schedule": "schedule.json", "standings": "standings.json", "league": "league.json",
                  "leaders": "leaders.json", "players": "players.json",
                  "team": "teams/{slug}.json", "match": "matches/{fibaId}.json", "raw": "raw/{fibaId}.json.gz"},
        "games": [{"fibaId": g["fibaId"], "date": (g.get("fixture") or {}).get("date"),
                   "home": g["home"]["slug"], "away": g["away"]["slug"],
                   "score": [g["home"]["score"], g["away"]["score"]], "status": g["status"]}
                  for g in sorted(games, key=lambda g: ((g.get("fixture") or {}).get("datetime") or "", g["fibaId"]))],
    }
    write_json(sdir / "index.json", index)
    print(f"hotovo: {len(final_games)} dohraných zápasů, {len(teams)} týmů, {len(pl)} hráčů -> {sdir}")
    return index


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", default=None, help='např. "2026/27" (výchozí: podle dnešního data)')
    ap.add_argument("--offline", action="store_true", help="bez sítě, jen přepočet z archivu")
    ap.add_argument("--no-scrape", action="store_true", help="nestahovat rozpis z nbl.basketball")
    ap.add_argument("--no-fetch", action="store_true", help="nestahovat FIBA data")
    ap.add_argument("--debug", action="store_true", help="vypsat ukázky HTML rozpisu")
    a = ap.parse_args(argv)
    season_label = a.season or schedule.current_season()
    build(season_label, scrape=not (a.offline or a.no_scrape), fetch=not (a.offline or a.no_fetch), debug=a.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
