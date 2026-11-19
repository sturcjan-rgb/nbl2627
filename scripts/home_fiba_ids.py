"""Dohledání FIBA ID z nbl.basketball — spouští se z domácího počítače.

nbl.basketball vrací serverům GitHub Actions HTTP 403, z běžného připojení ale odpovídá.
Tenhle skript (spouštěný naplánovaně doma, viz scripts/home_sync.sh) stáhne jednu stránku
ligového rozpisu a u zápasů kolem dneška, kterým ještě chybí FIBA ID, otevře stránku detailu
zápasu. Nalezená ID zapíše do data/<sezóna>/fiba_overrides.json; zbytek (stažení FIBA dat,
přepočet, srsni-truth a srsni-data) pak udělají workflowy na GitHubu.

Jen pár dotazů za běh (1 + počet zápasů bez ID v okně −10…+3 dny), s pauzou mezi nimi.
Vypíše počet nově nalezených ID; návratový kód 0 = v pořádku (i když nic nového).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nbl import schedule  # noqa: E402
from nbl.util import read_json, write_json  # noqa: E402


def main() -> int:
    season = schedule.current_season()
    sdir = ROOT / "data" / schedule.season_key(season)
    fixtures = (read_json(sdir / "schedule.json", {}) or {}).get("fixtures", [])
    if not fixtures:
        print(f"chybí {sdir / 'schedule.json'}", file=sys.stderr)
        return 1
    known = {f["nblId"]: f.get("fibaId") for f in fixtures}
    fetcher = schedule.Fetcher()

    # 1) jedna stránka ligového rozpisu (u blízkých zápasů bývá FIBA odkaz přímo v tabulce)
    y = schedule.season_start_year(season)
    html = fetcher.get(schedule.SCHEDULE_URL, {"y": y, "p1": 0, "k": 0, "d_od": "", "d_do": ""})
    if html is None:
        print("nbl.basketball nedostupné", file=sys.stderr)
        return 2
    found: dict[int, int] = {}
    for r in schedule.parse_rows(html, list(schedule.KNOWN_TEAMS)):
        if r.get("fibaId") and r["nblId"] in known and not known[r["nblId"]]:
            found[r["nblId"]] = r["fibaId"]

    # 2) zbylé zápasy bez ID kolem dneška -> stránka detailu zápasu
    rest = [dict(f) for f in fixtures if not f.get("fibaId") and f["nblId"] not in found]
    schedule.resolve_fiba_ids(rest, fetcher)
    for f in rest:
        if f.get("fibaId"):
            found[f["nblId"]] = f["fibaId"]

    path = sdir / "fiba_overrides.json"
    overrides = read_json(path, {}) or {}
    new = {str(k): v for k, v in found.items() if overrides.get(str(k)) != v}
    if new:
        overrides.update(new)
        write_json(path, dict(sorted(overrides.items())))
    print(f"nová FIBA ID: {len(new)} {new if new else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
