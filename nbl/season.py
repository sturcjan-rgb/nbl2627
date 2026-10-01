"""Sezónní agregace přes všechny dohrané zápasy ligy.

Pokročilé metriky se počítají ze SOUČTŮ (ne průměrem zápasových procent) — stejně jako
to dělá srsni-data/srsni-truth pro jednotlivé zápasy, jen nad celou sezónou.

Výstupy:
- standings(): tabulka (výhry, skóre, doma/venku, série, forma, vzájemné zápasy při rovnosti)
- team_seasons(): sezóna každého týmu (box, soupeři, ratingy, four factors, zóny, čas útoku,
  clutch, čtvrtiny, pětky/dvojice/trojice, asistenční dvojice, hráči, zápasy) + pořadí v lize
- players(): všichni hráči ligy (součty, průměry, na 40 min, TS/eFG/USG, on/off, deník)
- leaders(): žebříčky hráčů
"""
from __future__ import annotations

import math
from collections import defaultdict
from itertools import combinations

from .metrics import (BOX_KEYS, PLAYER_FIELDS, STINT_KEYS, ZONES, add_stint, advanced, blank_box,
                      four_factors, new_stint, unit_ratings)
from .teams import slugify
from .util import pct, r1, ratio

SEASON_LINEUP_MIN = {5: 150, 3: 300, 2: 180}   # s pohromadě za sezónu (pětky 2,5 min, trojice 5, dvojice 3 — matice)

# metriky pro pořadí týmů v lize: (klíč, kde, vyšší = lepší)
RANKED = [
    ("ppg", "perGame", True), ("oppg", "perGame", False), ("diff", "perGame", True),
    ("ortg", "adv", True), ("drtg", "adv", False), ("net", "adv", True), ("pace", "adv", True),
    ("efg", "adv", True), ("ts", "adv", True), ("tov", "adv", False), ("orb", "adv", True),
    ("drb", "adv", True), ("ftr", "adv", True), ("three_par", "adv", True), ("three", "adv", True),
    ("two", "adv", True), ("ft", "adv", True), ("ast_pct", "adv", True), ("ast_to", "adv", True),
    ("stl_pct", "adv", True), ("blk_pct", "adv", True),
    ("opp_efg", "oppAdv", False), ("opp_tov", "oppAdv", True), ("opp_ftr", "oppAdv", False),
    ("opp_three", "oppAdv", False),
]


def _side(game: dict, slug: str) -> tuple[str, str] | None:
    if game["home"]["slug"] == slug:
        return "home", "away"
    if game["away"]["slug"] == slug:
        return "away", "home"
    return None


def _date(game: dict) -> str:
    return ((game.get("fixture") or {}).get("datetime") or "")


# ------------------------------------------------------------------ tabulka

def _record_rows(games: list[dict]) -> dict:
    rows = {}
    for g in sorted(games, key=_date):
        for me, op in (("home", "away"), ("away", "home")):
            T, O = g[me], g[op]
            r = rows.setdefault(T["slug"], {
                "slug": T["slug"], "name": T["name"], "label": T["label"], "logo": T.get("logo"),
                "gp": 0, "w": 0, "l": 0, "pf": 0, "pa": 0, "homeW": 0, "homeL": 0, "awayW": 0, "awayL": 0,
                "results": [], "h2h": defaultdict(lambda: [0, 0, 0]), "ot": 0, "closeW": 0, "closeL": 0,
            })
            won = T["score"] > O["score"]
            r["gp"] += 1
            r["w" if won else "l"] += 1
            r["pf"] += T["score"]
            r["pa"] += O["score"]
            r[(me + ("W" if won else "L"))] += 1
            r["results"].append("W" if won else "L")
            h = r["h2h"][O["slug"]]
            h[0] += int(won)
            h[1] += T["score"]
            h[2] += O["score"]
            if (g.get("period") or 4) > 4:
                r["ot"] += 1
            if abs(T["score"] - O["score"]) <= 5:
                r["closeW" if won else "closeL"] += 1
    return rows


def _streak(results: list[str]) -> str:
    if not results:
        return ""
    last, n = results[-1], 0
    for x in reversed(results):
        if x != last:
            break
        n += 1
    return f"{last}{n}"


def standings(games: list[dict]) -> list[dict]:
    """Pořadí: výhry (resp. % výher) → vzájemné zápasy mezi týmy se shodou (výhry, rozdíl skóre)
    → celkový rozdíl skóre → dané body. Zjednodušení pravidel NBL, při nerozhodnutelné
    shodě rozhoduje celkové skóre."""
    rows = _record_rows(games)
    for r in rows.values():
        r["pct"] = round(r["w"] / r["gp"], 3) if r["gp"] else 0
        r["diff"] = r["pf"] - r["pa"]

    def group_key(r):
        return (r["pct"], r["w"])

    ordered = sorted(rows.values(), key=lambda r: (-r["pct"], -r["w"], -r["diff"], -r["pf"]))
    result = []
    i = 0
    while i < len(ordered):
        j = i
        while j < len(ordered) and group_key(ordered[j]) == group_key(ordered[i]):
            j += 1
        group = ordered[i:j]
        if len(group) > 1:
            slugs = {r["slug"] for r in group}

            def h2h(r):
                w = sum(r["h2h"][s][0] for s in slugs if s in r["h2h"])
                d = sum(r["h2h"][s][1] - r["h2h"][s][2] for s in slugs if s in r["h2h"])
                return (-w, -d, -r["diff"], -r["pf"])
            group.sort(key=h2h)
        result.extend(group)
        i = j
    out = []
    for pos, r in enumerate(result, 1):
        out.append({
            "pos": pos, "slug": r["slug"], "name": r["name"], "label": r["label"], "logo": r["logo"],
            "gp": r["gp"], "w": r["w"], "l": r["l"], "pct": r["pct"],
            "pf": r["pf"], "pa": r["pa"], "diff": r["diff"],
            "ppg": r1(r["pf"] / r["gp"]) if r["gp"] else None, "oppg": r1(r["pa"] / r["gp"]) if r["gp"] else None,
            "home": f"{r['homeW']}-{r['homeL']}", "away": f"{r['awayW']}-{r['awayL']}",
            "close": f"{r['closeW']}-{r['closeL']}", "ot": r["ot"],
            "streak": _streak(r["results"]), "last5": "".join(r["results"][-5:]),
        })
    return out


# ------------------------------------------------------------------ týmy

def _sum_box(dst: dict, src: dict) -> None:
    for k in BOX_KEYS:
        dst[k] += src.get(k, 0)


def _lineup_rows(stints: dict, size: int, games: dict | None = None) -> list[dict]:
    rows = []
    for key, v in stints.items():
        if v["secs"] < SEASON_LINEUP_MIN[size]:
            continue
        rows.append({"players": list(key), **unit_ratings(v), **({"games": len(games[key])} if games else {})})
    rows.sort(key=lambda r: -r["min"])
    return rows


def team_seasons(games: list[dict]) -> dict[str, dict]:
    teams: dict[str, dict] = {}
    for g in sorted(games, key=_date):
        for me, op in (("home", "away"), ("away", "home")):
            T, O = g[me], g[op]
            t = teams.setdefault(T["slug"], {
                "slug": T["slug"], "name": T["name"], "label": T["label"], "short": T["short"], "code": T["code"],
                "logo": T.get("logo"), "coach": T.get("coach"),
                "games": 0, "minutes": 0.0, "box": blank_box(), "opp": blank_box(),
                "zones": {z: {"m": 0, "a": 0} for z in ZONES}, "oppZones": {z: {"m": 0, "a": 0} for z in ZONES},
                "attack": [0] * 6, "attackPoss": 0, "attackSec": [0, 0],
                "clutch": {"pts": 0, "opp": 0, "fgm": 0, "fga": 0, "ftm": 0, "fta": 0, "to": 0, "games": 0, "w": 0, "l": 0},
                "quarters": defaultdict(lambda: [0, 0, 0]),
                "fives": defaultdict(new_stint), "assists": defaultdict(lambda: [0, 0]),
                "runs": [0, 0], "leadChanges": 0, "biggestLead": 0, "biggestDeficit": 0,
                "log": [], "fiveGames": defaultdict(set), "shots": [], "shotPlayers": {},
                "attackPlayers": defaultdict(lambda: [0] * 6),
                "segments": {k: [0, 0] for k in ("first3", "last3", "last5")},
            })
            t["games"] += 1
            t["minutes"] += g["minutes"]
            if T.get("coach"):
                t["coach"] = T["coach"]
            _sum_box(t["box"], T["box"])
            _sum_box(t["opp"], O["box"])
            for z in ZONES:
                t["zones"][z]["m"] += T["zones"][z]["m"]
                t["zones"][z]["a"] += T["zones"][z]["a"]
                t["oppZones"][z]["m"] += O["zones"][z]["m"]
                t["oppZones"][z]["a"] += O["zones"][z]["a"]
            for i, v in enumerate(T["attack"]["team"] + [T["attack"]["unassigned"]]):
                t["attack"][i] += v
            t["attackPoss"] += T["attack"]["possessions"]
            t["attackSec"][0] += T["_agg"]["attackSec"][0]
            t["attackSec"][1] += T["_agg"]["attackSec"][1]
            cl = t["clutch"]
            cl["pts"] += T["clutch"]["pts"]
            cl["opp"] += O["clutch"]["pts"]
            for k in ("fgm", "fga", "ftm", "fta", "to"):
                cl[k] += T["clutch"][k]
            had_clutch = T["clutch"]["fga"] + T["clutch"]["fta"] + O["clutch"]["fga"] + O["clutch"]["fta"] > 0
            won = T["score"] > O["score"]
            if had_clutch:
                cl["games"] += 1
                cl["w" if won else "l"] += 1
            for q in g["quarters"]:
                key = q["period"] if q["period"] <= 4 else 5
                acc = t["quarters"][key]
                acc[0] += q[me]
                acc[1] += q[op]
                acc[2] += 1
            for names, v in T["_agg"]["fives"]:
                add_stint(t["fives"][tuple(sorted(names))], v)
                if v["secs"]:
                    t["fiveGames"][tuple(sorted(names))].add(g.get("fibaId"))
            pname = {p["pno"]: p["name"] for p in T["players"]}
            for sh in T["shots"]:
                nm = pname.get(sh[4], "")
                pi = t["shotPlayers"].setdefault(nm, len(t["shotPlayers"]))
                t["shots"].append(sh[:4] + [pi])
            for nm, bands in T["_agg"]["attackPlayers"].items():
                acc = t["attackPlayers"][nm]
                for i, v in enumerate(bands):
                    acc[i] += v
            for k in t["segments"]:
                t["segments"][k][0] += T["segments"][k]
                t["segments"][k][1] += O["segments"][k]
            for a, b, n, p in T["_agg"]["assists"]:
                acc = t["assists"][(a, b)]
                acc[0] += n
                acc[1] += p
            t["leadChanges"] += g["flow"]["leadChanges"]
            t["biggestLead"] = max(t["biggestLead"], T["lead"]["max"])
            t["biggestDeficit"] = max(t["biggestDeficit"], O["lead"]["max"])
            t["runs"][0] = max(t["runs"][0], T["biggestRun"])
            t["runs"][1] = max(t["runs"][1], O["biggestRun"])
            fx = g.get("fixture") or {}
            t["log"].append({
                "fibaId": g.get("fibaId"), "nblId": g.get("nblId"), "date": fx.get("date"), "round": fx.get("round"),
                "venue": me, "opponent": O["name"], "opponentSlug": O["slug"], "opponentLabel": O["label"],
                "score": [T["score"], O["score"]], "result": "W" if won else "L", "ot": (g.get("period") or 4) > 4,
                "ortg": T["adv"]["ortg"], "drtg": T["adv"]["drtg"], "net": T["adv"]["net"], "pace": g.get("pace"),
                "efg": T["adv"]["efg"], "tov": T["adv"]["tov"], "orb": T["adv"]["orb"], "ftr": T["adv"]["ftr"],
                "topScorer": (max(T["players"], key=lambda p: p["pts"])["name"] if T["players"] else None),
                "oppEfg": O["adv"]["efg"], "oppOrb": O["adv"]["orb"],
                "tp": [T["box"]["tpm"], T["box"]["tpa"]], "ft": [T["box"]["ftm"], T["box"]["fta"]],
                "second": [T["box"]["second"], O["box"]["second"]], "bench": [T["box"]["bench"], O["box"]["bench"]],
                "paint": [T["box"]["paint"], O["box"]["paint"]],
                "leading": [round(T["lead"]["timeLeadingSec"] / 60, 1), round(O["lead"]["timeLeadingSec"] / 60, 1)],
                "leadChanges": g["flow"]["leadChanges"], "maxLead": [T["lead"]["max"], O["lead"]["max"]],
                "maxRun": [T["biggestRun"], O["biggestRun"]],
                "astFg": [[T["box"]["ast"], T["box"]["fgm"]], [O["box"]["ast"], O["box"]["fgm"]]],
                "quarters": [[q[me], q[op]] for q in g["quarters"]],
                "segments": {k: [T["segments"][k], O["segments"][k]] for k in T["segments"]},
            })

    out = {}
    for slug, t in teams.items():
        gp = t["games"]
        adv = advanced(t["box"], t["opp"], t["minutes"])
        oadv = advanced(t["opp"], t["box"], t["minutes"])
        per_game = {k: r1(v / gp) for k, v in t["box"].items()}
        per_game["ppg"] = per_game["pts"]
        per_game["oppg"] = r1(t["opp"]["pts"] / gp)
        per_game["diff"] = r1((t["box"]["pts"] - t["opp"]["pts"]) / gp)
        opp_pg = {k: r1(v / gp) for k, v in t["opp"].items()}
        oppAdv = {"opp_" + k: v for k, v in oadv.items() if k in ("efg", "tov", "ftr", "ts", "three", "two", "three_par", "fg", "ft")}
        fives = dict(t["fives"])
        units = {"fives": _lineup_rows(fives, 5, t["fiveGames"])}
        for size, label in ((3, "trios"), (2, "pairs")):
            combo = defaultdict(new_stint)
            for key, v in fives.items():
                for c in combinations(key, size):
                    add_stint(combo[c], v)
            units[label] = _lineup_rows(combo, size)
        for z in list(t["zones"].values()) + list(t["oppZones"].values()):
            z["pct"] = pct(z["m"], z["a"])
            z["share"] = None
        tot_a = sum(z["a"] for z in t["zones"].values())
        for z in t["zones"].values():
            z["share"] = pct(z["a"], tot_a)
        out[slug] = {
            "slug": slug, "name": t["name"], "label": t["label"], "short": t["short"], "code": t["code"],
            "logo": t["logo"], "coach": t["coach"], "games": gp, "minutes": round(t["minutes"], 1),
            "totals": t["box"], "oppTotals": t["opp"], "perGame": per_game, "oppPerGame": opp_pg,
            "adv": adv, "oppAdv": oppAdv, "factors": four_factors(adv, oadv),
            "zones": t["zones"], "oppZones": t["oppZones"],
            "attack": {"bands": ["0-5", "5-10", "10-15", "15-20", "20+"], "pts": t["attack"][:5],
                       "unassigned": t["attack"][5], "possessions": t["attackPoss"],
                       "ptsPerPoss": ratio(sum(t["attack"]), t["attackPoss"]),
                       "avgSec": r1(t["attackSec"][0] / t["attackSec"][1]) if t["attackSec"][1] else None},
            "clutch": {**t["clutch"], "fgPct": pct(t["clutch"]["fgm"], t["clutch"]["fga"]),
                       "net": t["clutch"]["pts"] - t["clutch"]["opp"]},
            "quarters": [{"period": k, "label": f"Q{k}" if k <= 4 else "OT", "ppg": r1(v[0] / v[2]),
                          "oppg": r1(v[1] / v[2]), "diff": r1((v[0] - v[1]) / v[2]), "n": v[2]}
                         for k, v in sorted(t["quarters"].items())],
            "flow": {"biggestLead": t["biggestLead"], "biggestDeficit": t["biggestDeficit"],
                     "biggestRun": t["runs"][0], "biggestRunAllowed": t["runs"][1],
                     "leadChangesPerGame": r1(t["leadChanges"] / gp)},
            "lineups": units,
            "assistPairs": sorted(({"passer": a, "scorer": b, "ast": v[0], "pts": v[1]} for (a, b), v in t["assists"].items()),
                                  key=lambda r: (-r["ast"], -r["pts"]))[:25],
            "log": t["log"],
            "shots": {"players": list(t["shotPlayers"]), "list": t["shots"]},
            "attackPlayers": sorted(({"name": n, "bands": v[:5], "pts": sum(v)} for n, v in t["attackPlayers"].items() if sum(v)),
                                    key=lambda r: -r["pts"]),
            "segments": t["segments"],
        }
    _rank(out)
    return out


def _rank(teams: dict[str, dict]) -> None:
    for key, where, higher in RANKED:
        vals = [(t[where].get(key), slug) for slug, t in teams.items() if t[where].get(key) is not None]
        vals.sort(key=lambda x: -x[0] if higher else x[0])
        prev, rank = None, 0
        for i, (v, slug) in enumerate(vals, 1):
            if v != prev:
                rank, prev = i, v
            teams[slug].setdefault("ranks", {})[key] = rank
    for t in teams.values():
        t["ranks"]["of"] = len(teams)


def league_averages(teams: dict[str, dict]) -> dict:
    box, opp = blank_box(), blank_box()
    minutes, games = 0.0, 0
    for t in teams.values():
        _sum_box(box, t["totals"])
        _sum_box(opp, t["oppTotals"])
        minutes += t["minutes"]
        games += t["games"]
    if not games:
        return {}
    adv = advanced(box, opp, minutes)
    return {"teamGames": games, "perGame": {k: r1(v / games) for k, v in box.items()}, "adv": adv}


# ------------------------------------------------------------------ hráči

def players(games: list[dict]) -> list[dict]:
    acc: dict[tuple, dict] = {}
    for g in sorted(games, key=_date):
        for me, op in (("home", "away"), ("away", "home")):
            T, O = g[me], g[op]
            team_minutes = sum(p["min"] for p in T["players"]) or g["minutes"] * 5
            for p in T["players"]:
                if not p["min"] and not p["fga"] and not p["pts"]:
                    continue
                key = (T["slug"], slugify(p["name"]))
                a = acc.setdefault(key, {
                    "id": f"{T['slug']}/{slugify(p['name'])}", "name": p["name"], "team": T["slug"],
                    "teamName": T["name"], "teamLabel": T["label"], "shirt": p["shirt"], "pos": p["pos"],
                    "gp": 0, "gs": 0, "min": 0.0, **{k: 0 for k in PLAYER_FIELDS},
                    "eff": 0, "gmsc": 0.0, "dd": 0, "td": 0, "high": 0,
                    "usgNum": 0.0, "usgDen": 0.0, "on": new_stint(), "off": new_stint(),
                    "zones": {z: {"m": 0, "a": 0} for z in ZONES}, "log": [],
                })
                a["gp"] += 1
                a["gs"] += int(p["starter"])
                a["min"] += p["min"]
                a["shirt"] = p["shirt"] or a["shirt"]
                for k in PLAYER_FIELDS:
                    a[k] += p[k]
                a["eff"] += p["eff"]
                a["gmsc"] += p["gmsc"]
                a["high"] = max(a["high"], p["pts"])
                tens = sum(1 for k in ("pts", "reb", "ast", "stl", "blk") if p[k] >= 10)
                a["dd"] += int(tens >= 2)
                a["td"] += int(tens >= 3)
                # USG ze součtů: Σ(akce hráče × min týmu/5) / Σ(min hráče × akce týmu)
                tb = T["box"]
                a["usgNum"] += (p["fga"] + 0.44 * p["fta"] + p["to"]) * (team_minutes / 5)
                a["usgDen"] += p["min"] * (tb["fga"] + 0.44 * tb["fta"] + tb["to"])
                on_v = T["_agg"]["on"].get(p["name"])
                if on_v:
                    add_stint(a["on"], on_v)
                    team_tot = new_stint()
                    for _n, v in T["_agg"]["fives"]:
                        add_stint(team_tot, v)
                    add_stint(a["off"], {k: team_tot[k] - on_v[k] for k in STINT_KEYS})
                for z in ZONES:
                    a["zones"][z]["m"] += p["zones"][z]["m"]
                    a["zones"][z]["a"] += p["zones"][z]["a"]
                fx = g.get("fixture") or {}
                a["log"].append({"fibaId": g.get("fibaId"), "date": fx.get("date"), "opponent": O["label"],
                                 "venue": me, "result": "W" if T["score"] > O["score"] else "L",
                                 "min": p["min"], "pts": p["pts"], "reb": p["reb"], "ast": p["ast"],
                                 "stl": p["stl"], "blk": p["blk"], "to": p["to"], "fg": f"{p['fgm']}/{p['fga']}",
                                 "tp": f"{p['tpm']}/{p['tpa']}", "ft": f"{p['ftm']}/{p['fta']}",
                                 "pm": p["pm"], "eff": p["eff"], "ts": p["ts"]})
    out = []
    for a in acc.values():
        gp, mins = a["gp"], a["min"]
        on_r, off_r = unit_ratings(a["on"]), unit_ratings(a["off"])
        tot = {k: a[k] for k in PLAYER_FIELDS}
        out.append({
            "id": a["id"], "name": a["name"], "team": a["team"], "teamName": a["teamName"], "teamLabel": a["teamLabel"],
            "shirt": a["shirt"], "pos": a["pos"], "gp": gp, "gs": a["gs"], "min": round(mins, 1),
            "totals": tot,
            "perGame": {**{k: r1(v / gp) for k, v in tot.items()}, "min": r1(mins / gp),
                        "eff": r1(a["eff"] / gp), "gmsc": r1(a["gmsc"] / gp)},
            "per40": {k: r1(tot[k] * 40 / mins) for k in ("pts", "reb", "ast", "stl", "blk", "to")} if mins else {},
            "ts": pct(tot["pts"], 2 * (tot["fga"] + 0.44 * tot["fta"])),
            "efg": pct(tot["fgm"] + 0.5 * tot["tpm"], tot["fga"]),
            "fg": pct(tot["fgm"], tot["fga"]), "two": pct(tot["twopm"], tot["twopa"]),
            "three": pct(tot["tpm"], tot["tpa"]), "ft": pct(tot["ftm"], tot["fta"]),
            "usg": round(100 * a["usgNum"] / a["usgDen"], 1) if a["usgDen"] else None,
            "astTo": ratio(tot["ast"], tot["to"]),
            "pm": tot["pm"], "pm40": r1(tot["pm"] * 40 / mins) if mins else None,
            "on": {k: on_r[k] for k in ("min", "pf", "pa", "ortg", "drtg", "net")},
            "off": {k: off_r[k] for k in ("min", "ortg", "drtg", "net")},
            "onOff": r1(on_r["net"] - off_r["net"]) if on_r["net"] is not None and off_r["net"] is not None else None,
            "dd": a["dd"], "td": a["td"], "high": a["high"],
            "zones": {z: {**v, "pct": pct(v["m"], v["a"])} for z, v in a["zones"].items()},
            "log": a["log"],
        })
    out.sort(key=lambda p: (-(p["perGame"]["pts"] or 0), p["name"]))
    return out


LEADER_STATS = [
    # (klíč, popisek, getter, minimum: "games" | ("fga", n) | ("fta", n) | ("tpa", n) | ("min", n))
    ("pts", "Body na zápas", lambda p: p["perGame"]["pts"], "games"),
    ("reb", "Doskoky na zápas", lambda p: p["perGame"]["reb"], "games"),
    ("ast", "Asistence na zápas", lambda p: p["perGame"]["ast"], "games"),
    ("stl", "Zisky na zápas", lambda p: p["perGame"]["stl"], "games"),
    ("blk", "Bloky na zápas", lambda p: p["perGame"]["blk"], "games"),
    ("eff", "Efektivita (EFF) na zápas", lambda p: p["perGame"]["eff"], "games"),
    ("gmsc", "Game Score na zápas", lambda p: p["perGame"]["gmsc"], "games"),
    ("tpm", "Trojky na zápas", lambda p: p["perGame"]["tpm"], "games"),
    ("ts", "True shooting %", lambda p: p["ts"], ("fga", 5)),
    ("efg", "Effective FG %", lambda p: p["efg"], ("fga", 5)),
    ("three", "Trojky %", lambda p: p["three"], ("tpa", 2)),
    ("ft", "Trestné hody %", lambda p: p["ft"], ("fta", 2)),
    ("usg", "Usage %", lambda p: p["usg"], ("min", 15)),
    ("pm", "Plus/minus celkem", lambda p: p["pm"], "games"),
    ("onOff", "On/off net rating", lambda p: p["onOff"], ("min", 15)),
    ("dd", "Double-double", lambda p: p["dd"], None),
]


def leaders(pl: list[dict], team_games: dict[str, int], limit: int = 15) -> dict:
    max_gp = max(team_games.values(), default=0)
    min_games = max(1, math.ceil(0.4 * max_gp))
    out = {"minGames": min_games}
    for key, label, get, rule in LEADER_STATS:
        def ok(p):
            if p["gp"] < (min_games if rule == "games" or isinstance(rule, tuple) else 1):
                return False
            if isinstance(rule, tuple):
                k, n = rule
                base = p["min"] if k == "min" else p["totals"][k]
                return base >= n * p["gp"]
            return True
        rows = [p for p in pl if ok(p) and get(p) is not None]
        rows.sort(key=lambda p: (-get(p), -p["min"]))
        out[key] = {"label": label, "rows": [{"id": p["id"], "name": p["name"], "team": p["team"],
                                                "teamLabel": p["teamLabel"], "gp": p["gp"], "value": get(p)}
                                               for p in rows[:limit]]}
    return out


def strip_player_logs(pl: list[dict]) -> list[dict]:
    return [{k: v for k, v in p.items() if k not in ("log", "zones")} for p in pl]

