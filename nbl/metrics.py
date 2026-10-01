"""Rozbor jednoho zápasu z FIBA LiveStats data.json — metriky po vzoru srsni-data.

Čisté funkce bez sítě; funguje pro dohraný i právě běžící zápas (live).

Co se počítá (pro oba týmy):
- box score z oficiálních součtů (tot_*), čtvrtiny, body z paintu / protiútoků / druhých šancí /
  lavičky / po ztrátách soupeře
- držení míče (FGA − ORB + TO + 0,44·FTA), pace (držení na 40 min), ORtg / DRtg / Net
- Four Factors (eFG%, TOV%, ORB%, FT rate = FTM/FGA) + TS%, 3PAr, AST%, AST/TO, STL%, BLK%
- hráči: minuty, střelba, TS%, eFG%, USG%, EFF, Game Score, +/−, ±/40, on/off net rating
- pětky, trojice, dvojice na hřišti (čas, skóre, ORtg/DRtg/Net, eFG my/soupeř)
- asistenční dvojice (nahrávač → střelec)
- střelecké zóny (paint, střední dvojka, roh, oblouk) + souřadnice střel
- body podle času útoku (0–5 / 5–10 / 10–15 / 15–20 / 20+ s) — rekonstrukce držení z pbp
- průběh: série bez odpovědi, největší vedení, střídání vedení, čas ve vedení, clutch
- live: kdo je na hřišti, aktuální série, týmové fauly v periodě, hráči ve faulových potížích
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from itertools import combinations
from typing import Any

from .teams import identify
from .util import inum, mmss_to_sec, num, pct, r1, ratio, sec_to_mmss

RUN_MIN = 8                 # série bez odpovědi, která se vypisuje
CLUTCH_SECS = 300           # clutch = posledních 5 min Q4/prodloužení …
CLUTCH_MARGIN = 5           # … při rozdílu skóre nejvýš 5 bodů
LINEUP_MIN_SECS = {5: 60, 3: 90, 2: 120}
PTS = {"2pt": 2, "3pt": 3, "freethrow": 1}
ATTACK_BANDS = ["0-5", "5-10", "10-15", "15-20", "20+"]
ZONES = ["paint", "mid", "corner3", "above3"]
ZONE_LABELS = {"paint": "Dvojka v paintu", "mid": "Střední dvojka",
               "corner3": "Trojka z rohu", "above3": "Trojka z oblouku"}


# ---------------------------------------------------------------- čas a pořadí

def abs_period(period: Any, period_type: Any = None) -> int:
    """FIBA čísluje prodloužení znovu od 1 (period=1, periodType="OVERTIME") -> 5, 6, …"""
    p = max(1, inum(period, 1))
    return p + 4 if str(period_type or "").upper() == "OVERTIME" else p


def period_label(p: int) -> str:
    return f"Q{p}" if p <= 4 else ("OT" if p == 5 else f"OT{p - 4}")


class Clock:
    """Převod (perioda, zbývající čas) na uplynulé sekundy zápasu, i pro prodloužení."""

    def __init__(self, raw: dict):
        self.pl = inum(raw.get("periodLengthREGULAR") or raw.get("periodLength"), 10) or 10
        self.ot = inum(raw.get("periodLengthOVERTIME"), 5) or 5

    def period_secs(self, p: int) -> int:
        return (self.pl if p <= 4 else self.ot) * 60

    def period_start(self, p: int) -> int:
        if p <= 4:
            return (p - 1) * self.pl * 60
        return 4 * self.pl * 60 + (p - 5) * self.ot * 60

    def elapsed(self, period: int, gt: Any) -> int:
        period = max(1, int(period or 1))
        return self.period_start(period) + self.period_secs(period) - mmss_to_sec(gt)

    def of(self, e: dict) -> int:
        return self.elapsed(abs_period(e.get("period"), e.get("periodType")), e.get("gt"))


def sorted_pbp(raw: dict, clock: Clock) -> list[dict]:
    """Řadit podle herního času, ne actionNumber: zapisovatel občas doplní akci zpětně
    (vyšší actionNumber, starý čas). Při shodě času rozhoduje actionNumber."""
    evs = [e for e in (raw.get("pbp") or []) if isinstance(e, dict)]
    return sorted(evs, key=lambda e: (clock.of(e), inum(e.get("actionNumber"))))


def is_finished(raw: dict) -> bool:
    return any(e.get("actionType") == "game" and e.get("subType") == "end" for e in raw.get("pbp") or [])


def game_status(raw: dict) -> str:
    if is_finished(raw):
        return "final"
    return "live" if raw.get("pbp") else "scheduled"


# ---------------------------------------------------------------- box score

TOT_FIELDS = {
    "pts": "tot_sPoints", "fgm": "tot_sFieldGoalsMade", "fga": "tot_sFieldGoalsAttempted",
    "tpm": "tot_sThreePointersMade", "tpa": "tot_sThreePointersAttempted",
    "twopm": "tot_sTwoPointersMade", "twopa": "tot_sTwoPointersAttempted",
    "ftm": "tot_sFreeThrowsMade", "fta": "tot_sFreeThrowsAttempted",
    "oreb": "tot_sReboundsOffensive", "dreb": "tot_sReboundsDefensive", "reb": "tot_sReboundsTotal",
    "ast": "tot_sAssists", "to": "tot_sTurnovers", "stl": "tot_sSteals", "blk": "tot_sBlocks",
    "blkr": "tot_sBlocksReceived", "pf": "tot_sFoulsPersonal", "foulon": "tot_sFoulsOn",
    "paint": "tot_sPointsInThePaint", "fast": "tot_sPointsFastBreak", "second": "tot_sPointsSecondChance",
    "bench": "tot_sBenchPoints", "offto": "tot_sPointsFromTurnovers",
}
PLAYER_FIELDS = {
    "pts": "sPoints", "fgm": "sFieldGoalsMade", "fga": "sFieldGoalsAttempted",
    "tpm": "sThreePointersMade", "tpa": "sThreePointersAttempted",
    "twopm": "sTwoPointersMade", "twopa": "sTwoPointersAttempted",
    "ftm": "sFreeThrowsMade", "fta": "sFreeThrowsAttempted",
    "oreb": "sReboundsOffensive", "dreb": "sReboundsDefensive", "reb": "sReboundsTotal",
    "ast": "sAssists", "to": "sTurnovers", "stl": "sSteals", "blk": "sBlocks",
    "blkr": "sBlocksReceived", "pf": "sFoulsPersonal", "foulon": "sFoulsOn",
    "pm": "sPlusMinusPoints", "paint": "sPointsInThePaint", "fast": "sPointsFastBreak",
    "second": "sPointsSecondChance",
}
BOX_KEYS = list(TOT_FIELDS)


def blank_box() -> dict:
    return {k: 0 for k in BOX_KEYS}


def team_box(tm: dict, pbp_counts: dict | None = None) -> dict:
    """Oficiální týmové součty. Když tot_* chybí (velmi rané live snímky), dopočítá se z hráčů."""
    box = {}
    players = (tm.get("pl") or {}).values()
    for k, f in TOT_FIELDS.items():
        if f in tm:
            box[k] = inum(tm.get(f))
        elif k in PLAYER_FIELDS:
            box[k] = sum(inum(p.get(PLAYER_FIELDS[k])) for p in players)
        else:
            box[k] = 0
    if not box["pts"]:
        box["pts"] = inum(tm.get("score"))
    return box


def possessions(b: dict) -> float:
    return b["fga"] - b["oreb"] + b["to"] + 0.44 * b["fta"]


def advanced(b: dict, o: dict, minutes: float) -> dict:
    """Pokročilé týmové metriky z box score týmu (b) a soupeře (o). minutes = délka zápasu."""
    poss, oposs = possessions(b), possessions(o)
    avg_poss = (poss + oposs) / 2
    ortg = 100 * b["pts"] / poss if poss > 0 else None
    drtg = 100 * o["pts"] / oposs if oposs > 0 else None
    return {
        "poss": r1(poss),
        "pace": r1(avg_poss * 40 / minutes) if minutes else None,
        "ortg": r1(ortg), "drtg": r1(drtg),
        "net": r1(ortg - drtg) if ortg is not None and drtg is not None else None,
        "efg": pct(b["fgm"] + 0.5 * b["tpm"], b["fga"]),
        "ts": pct(b["pts"], 2 * (b["fga"] + 0.44 * b["fta"])),
        "tov": pct(b["to"], b["fga"] + 0.44 * b["fta"] + b["to"]),
        "orb": pct(b["oreb"], b["oreb"] + o["dreb"]),
        "drb": pct(b["dreb"], b["dreb"] + o["oreb"]),
        "ftr": pct(b["ftm"], b["fga"]),
        "fta_rate": pct(b["fta"], b["fga"]),
        "three_par": pct(b["tpa"], b["fga"]),
        "fg": pct(b["fgm"], b["fga"]), "two": pct(b["twopm"], b["twopa"]),
        "three": pct(b["tpm"], b["tpa"]), "ft": pct(b["ftm"], b["fta"]),
        "ast_pct": pct(b["ast"], b["fgm"]),
        "ast_to": ratio(b["ast"], b["to"]),
        "stl_pct": pct(b["stl"], oposs),
        "blk_pct": pct(b["blk"], o["twopa"]),
        "pts_per_shot": ratio(b["pts"], b["fga"] + 0.44 * b["fta"]),
    }


def four_factors(adv: dict, opp_adv: dict) -> dict:
    return {
        "efg": adv["efg"], "tov": adv["tov"], "orb": adv["orb"], "ftr": adv["ftr"],
        "opp_efg": opp_adv["efg"], "opp_tov": opp_adv["tov"], "drb": adv["drb"], "opp_ftr": opp_adv["ftr"],
    }


# ---------------------------------------------------------------- střely

def norm_shot(x: float, y: float) -> tuple[float, float]:
    if x > 50:
        x, y = 100 - x, 100 - y
    return x, y


def shot_dist_m(nx: float, ny: float) -> float:
    return math.hypot((nx - 5.2) / 100 * 28, (ny - 50) / 100 * 15)


def zone_of(nx: float, ny: float, three: bool) -> str:
    if three:
        return "corner3" if nx < 13 and abs(ny - 50) > 32 else "above3"
    return "paint" if shot_dist_m(nx, ny) < 4 else "mid"


def blank_zones() -> dict:
    return {z: {"m": 0, "a": 0} for z in ZONES}


# ---------------------------------------------------------------- hráči

def player_name(p: dict) -> str:
    full = " ".join(x for x in (p.get("firstName"), p.get("familyName")) if x) or p.get("name", "")
    return " ".join(full.split())


def eff(s: dict) -> int:
    """Efektivita (EFF) jako v highlights-engine: PTS+REB+AST+STL+BLK − minuté střely − ztráty."""
    return int(s["pts"] + s["reb"] + s["ast"] + s["stl"] + s["blk"]
               - (s["fga"] - s["fgm"]) - (s["fta"] - s["ftm"]) - s["to"])


def game_score(s: dict) -> float:
    """Hollingerovo Game Score."""
    return round(s["pts"] + 0.4 * s["fgm"] - 0.7 * s["fga"] - 0.4 * (s["fta"] - s["ftm"])
                 + 0.7 * s["oreb"] + 0.3 * s["dreb"] + s["stl"] + 0.7 * s["ast"] + 0.7 * s["blk"]
                 - 0.4 * s["pf"] - s["to"], 1)


def usage(s: dict, minutes: float, team: dict, team_minutes: float) -> float | None:
    """USG% = podíl akcí týmu zakončených hráčem, když byl na hřišti."""
    denom = minutes * (team["fga"] + 0.44 * team["fta"] + team["to"])
    if not denom:
        return None
    return round(100 * (s["fga"] + 0.44 * s["fta"] + s["to"]) * (team_minutes / 5) / denom, 1)


# ---------------------------------------------------------------- jednotky na hřišti

STINT_KEYS = ["secs", "pf", "pa", "fga", "fgm", "tpm", "fta", "oreb", "to",
              "ofga", "ofgm", "otpm", "ofta", "ooreb", "oto"]


def new_stint() -> dict:
    return {k: 0 for k in STINT_KEYS}


def unit_ratings(v: dict) -> dict:
    """ORtg/DRtg/Net jednotky: držení = FGA − OREB + TO + 0,44·FTA (zvlášť my a soupeř)."""
    p_for = v["fga"] - v["oreb"] + v["to"] + 0.44 * v["fta"]
    p_ag = v["ofga"] - v["ooreb"] + v["oto"] + 0.44 * v["ofta"]
    ortg = 100 * v["pf"] / p_for if p_for > 0 else None
    drtg = 100 * v["pa"] / p_ag if p_ag > 0 else None
    return {
        "min": round(v["secs"] / 60, 1), "pf": v["pf"], "pa": v["pa"], "pm": v["pf"] - v["pa"],
        "poss": r1((p_for + p_ag) / 2), "pF": r1(p_for), "pA": r1(p_ag),
        "ortg": r1(ortg), "drtg": r1(drtg),
        "net": r1(ortg - drtg) if ortg is not None and drtg is not None else None,
        "efg": pct(v["fgm"] + 0.5 * v["tpm"], v["fga"]),
        "oefg": pct(v["ofgm"] + 0.5 * v["otpm"], v["ofga"]),
    }


def add_stint(dst: dict, src: dict) -> None:
    for k in STINT_KEYS:
        dst[k] += src[k]


def derive_combos(fives: dict[tuple, dict], size: int) -> dict[tuple, dict]:
    if size == 5:
        return fives
    out: dict[tuple, dict] = {}
    for key, v in fives.items():
        for c in combinations(key, size):
            add_stint(out.setdefault(c, new_stint()), v)
    return out


# ---------------------------------------------------------------- hlavní průchod pbp

def _team_no(e: dict) -> int:
    t = inum(e.get("tno"))
    return t if t in (1, 2) else 0


def walk_pbp(raw: dict, clock: Clock) -> dict:
    """Jeden průchod play-by-play: jednotky na hřišti, on-court hráčů, průběh skóre, série,
    clutch, asistence, čas útoku. Vrací surové struktury pro analyze_game."""
    pbp = sorted_pbp(raw, clock)
    tm = raw.get("tm") or {}
    starters = {t: {str(k) for k, p in ((tm.get(str(t)) or {}).get("pl") or {}).items() if inum(p.get("starter")) == 1}
                for t in (1, 2)}
    on = {t: set(starters[t]) for t in (1, 2)}
    fives = {1: {}, 2: {}}
    on_player = {1: defaultdict(new_stint), 2: defaultdict(new_stint)}
    secs_played = {1: defaultdict(float), 2: defaultdict(float)}

    def five_key(t):
        return tuple(sorted(on[t], key=int))

    def unit_add(ev_team: int, field: str, n: int = 1) -> None:
        for s in (1, 2):
            prefix = "" if ev_team == s else "o"
            if len(on[s]) == 5:
                fives[s].setdefault(five_key(s), new_stint())[prefix + field] += n
            for p in on[s]:
                on_player[s][p][prefix + field] += n

    score = {1: 0, 2: 0}
    prev_el = 0
    timeline = [[0, 0]]                       # [elapsed s, s1 − s2] po každé změně skóre
    lead = {"max": {1: 0, 2: 0}, "changes": 0, "ties": 0, "time": {1: 0, 2: 0, 0: 0}}
    last_leader = 0
    runs = []
    run = None
    clutch = {t: {"pts": 0, "fga": 0, "fgm": 0, "fta": 0, "ftm": 0, "to": 0, "players": defaultdict(int)}
              for t in (1, 2)}
    by_period = defaultdict(lambda: {1: 0, 2: 0})
    assists: dict[int, defaultdict] = {1: defaultdict(lambda: [0, 0]), 2: defaultdict(lambda: [0, 0])}
    by_number = {inum(e.get("actionNumber")): e for e in pbp}
    period_fouls = defaultdict(lambda: {1: 0, 2: 0})
    timeouts = {1: 0, 2: 0}
    last_period = 1

    # --- čas útoku (port attackPoints ze srsni-data, varianta „doskok v útoku pokračuje“)
    att = {"P": {1: defaultdict(lambda: [0] * 6), 2: defaultdict(lambda: [0] * 6)},
           "team": {1: [0] * 6, 2: [0] * 6}, "sec": {1: [0, 0], 2: [0, 0]}, "poss": {1: 0, 2: 0}, "approx": 0}
    st = {"owner": 0, "start": 0, "prev": None, "keep": 0}

    def a_gain(t, el):
        if st["owner"] and st["owner"] != t:
            st["prev"] = {"team": st["owner"], "start": st["start"], "end": el}
        if st["owner"] != t or not st["owner"]:
            att["poss"][t] += 1
        st["owner"], st["start"] = t, el

    def a_ensure(t, el):
        if st["owner"] == t:
            return
        if not st["owner"]:
            st["owner"] = t
            att["poss"][t] += 1
            return
        att["approx"] += 1
        a_gain(t, el)

    def a_add(t, p, pts, length):
        b = 5 if length is None else (0 if length <= 5 else 1 if length <= 10 else 2 if length <= 15 else 3 if length <= 20 else 4)
        att["P"][t][p][b] += pts
        att["team"][t][b] += pts
        if length is not None:
            att["sec"][t][0] += length * pts
            att["sec"][t][1] += pts

    def attack(e, el, t, at, ok):
        sub = e.get("subType") or ""
        if at == "period" and sub == "start":
            st.update(owner=0, start=el, prev=None)
            return
        if not t:
            return
        o = 3 - t
        pno = str(inum(e.get("pno")))
        if at == "foul" and sub in ("unsportsmanlike", "disqualifying"):
            st["keep"] = o
        elif at == "jumpball" and sub == "won":
            a_gain(t, el)
        elif at == "rebound":
            if sub == "defensive":
                a_gain(t, el)
            elif sub == "offensive":
                a_ensure(t, el)
        elif at == "turnover":
            a_ensure(t, el)
            a_gain(o, el)
        elif at in ("2pt", "3pt"):
            a_ensure(t, el)
            if ok:
                a_add(t, pno, PTS[at], el - st["start"])
                a_gain(o, el)
        elif at == "freethrow":
            m = re.match(r"^(\d)of(\d)$", sub)
            last = not m or m.group(1) == m.group(2)
            length = None
            prev = st["prev"]
            if st["owner"] == t:
                length = el - st["start"]
            elif prev and prev["team"] == t and prev["end"] == el:
                length = el - prev["start"]          # and-one po proměněném koši
            if ok:
                a_add(t, pno, 1, length)
            if length is not None and st["owner"] != t:
                st["owner"], st["start"] = t, prev["start"]
                att["poss"][o] -= 1
                st["prev"] = None
            if last and st["keep"] == t:
                st["keep"] = 0
                if st["owner"] != t:
                    a_gain(t, el)
                else:
                    st["start"] = el
                    att["poss"][t] += 1
            elif last and st["owner"] == t and ok:
                a_gain(o, el)

    def credit_time(el):
        nonlocal prev_el
        dt = max(0, el - prev_el)
        if dt:
            for t in (1, 2):
                if len(on[t]) == 5:
                    fives[t].setdefault(five_key(t), new_stint())["secs"] += dt
                for p in on[t]:
                    secs_played[t][p] += dt
                    on_player[t][p]["secs"] += dt
            ldr = 1 if score[1] > score[2] else 2 if score[2] > score[1] else 0
            lead["time"][ldr] += dt
        prev_el = el

    for e in pbp:
        el = clock.of(e)
        credit_time(el)
        t = _team_no(e)
        at = e.get("actionType")
        sub = e.get("subType") or ""
        ok = inum(e.get("success")) == 1
        pno = str(inum(e.get("pno")))
        period = abs_period(e.get("period"), e.get("periodType"))
        last_period = max(last_period, period)
        gt = mmss_to_sec(e.get("gt"))
        margin_before = score[1] - score[2]
        in_clutch = period >= 4 and gt <= CLUTCH_SECS and abs(margin_before) <= CLUTCH_MARGIN

        attack(e, el, t, at, ok)

        if t:
            if at in ("2pt", "3pt"):
                unit_add(t, "fga")
                if ok:
                    unit_add(t, "fgm")
                    if at == "3pt":
                        unit_add(t, "tpm")
                if in_clutch:
                    clutch[t]["fga"] += 1
                    clutch[t]["fgm"] += int(ok)
            elif at == "freethrow":
                unit_add(t, "fta")
                if in_clutch:
                    clutch[t]["fta"] += 1
                    clutch[t]["ftm"] += int(ok)
            elif at == "rebound" and sub == "offensive":
                unit_add(t, "oreb")
            elif at == "turnover":
                unit_add(t, "to")
                if in_clutch:
                    clutch[t]["to"] += 1
            elif at == "foul" and sub not in ("technical", "benchTechnical", "coachTechnical", "adminTechnical"):
                period_fouls[period][t] += 1
            elif at == "timeout":
                timeouts[t] += 1
            elif at == "assist":
                shot = by_number.get(inum(e.get("previousAction")))
                if shot and _team_no(shot) == t and str(inum(shot.get("pno"))) != pno:
                    pair = assists[t][(pno, str(inum(shot.get("pno"))))]
                    pair[0] += 1
                    pair[1] += PTS.get(shot.get("actionType"), 0)

        if t and ok and at in PTS:
            pts = PTS[at]
            score[t] += pts
            by_period[period][t] += pts
            for s in (1, 2):
                if len(on[s]) == 5:
                    f = fives[s].setdefault(five_key(s), new_stint())
                    f["pf" if s == t else "pa"] += pts
                for p in on[s]:
                    on_player[s][p]["pf" if s == t else "pa"] += pts
            if in_clutch:
                clutch[t]["pts"] += pts
                if pno != "0":
                    clutch[t]["players"][pno] += pts
            margin = score[1] - score[2]
            timeline.append([el, margin])
            for s in (1, 2):
                my = margin if s == 1 else -margin
                lead["max"][s] = max(lead["max"][s], my)
            leader = 1 if margin > 0 else 2 if margin < 0 else 0
            if leader == 0 and margin_before != 0:
                lead["ties"] += 1
            if leader and last_leader and leader != last_leader:
                lead["changes"] += 1
            if leader:
                last_leader = leader
            # série bez odpovědi
            if run and run["team"] == t:
                run["pts"] += pts
            else:
                if run:
                    runs.append(run)
                run = {"team": t, "pts": pts, "from": [score[1] - (pts if t == 1 else 0), score[2] - (pts if t == 2 else 0)],
                       "start": el, "startClock": f"{period_label(period)} {sec_to_mmss(gt)}"}
            run["to"] = [score[1], score[2]]
            run["end"] = el
            run["endClock"] = f"{period_label(period)} {sec_to_mmss(gt)}"

        if at == "substitution" and t:
            if sub == "in":
                on[t].add(pno)
            elif sub == "out":
                on[t].discard(pno)

    if run:
        runs.append(run)
    return {
        "pbp": pbp, "fives": fives, "on_player": on_player, "secs": secs_played, "score": score,
        "timeline": timeline, "lead": lead, "runs": runs, "current_run": run, "clutch": clutch,
        "by_period": by_period, "assists": assists, "attack": att, "on": on,
        "period_fouls": period_fouls, "timeouts": timeouts, "last_period": last_period,
        "elapsed": prev_el,
    }


# ---------------------------------------------------------------- výstup

def _lineups(t: int, w: dict, names: dict) -> dict:
    out = {}
    for size, label in ((5, "fives"), (3, "trios"), (2, "pairs")):
        rows = []
        for key, v in derive_combos(w["fives"][t], size).items():
            if v["secs"] < LINEUP_MIN_SECS[size]:
                continue
            rows.append({"players": [names.get(p, "#" + p) for p in key], "pnos": [int(p) for p in key],
                         **unit_ratings(v)})
        rows.sort(key=lambda r: (-r["min"], -(r["net"] if r["net"] is not None else -999)))
        out[label] = rows
    return out


def _quarters(raw: dict, w: dict) -> list[dict]:
    """Body po periodách: oficiální p1..p4_score (+ ot_score u jediného prodloužení), jinak z pbp."""
    t1, t2 = raw["tm"].get("1", {}), raw["tm"].get("2", {})
    out = []
    n_ot = max(0, w["last_period"] - 4)
    for p in range(1, max(4, w["last_period"]) + 1):
        if p <= 4:
            h, a = t1.get(f"p{p}_score"), t2.get(f"p{p}_score")
        elif n_ot == 1:
            h, a = t1.get("ot_score"), t2.get("ot_score")
        else:
            h = a = None
        if h in (None, "") or a in (None, ""):
            h, a = w["by_period"][p][1], w["by_period"][p][2]
        if p > w["last_period"] and not inum(h) and not inum(a):
            break
        out.append({"period": p, "label": period_label(p), "home": inum(h), "away": inum(a)})
    return out


def _game_minutes(raw: dict, clock: Clock, w: dict, final: bool) -> float:
    """Délka zápasu v minutách (40 + prodloužení), u live jen odehraný čas."""
    if final:
        last = max(4, w["last_period"])
        return (clock.period_start(last) + clock.period_secs(last)) / 60
    return max(w["elapsed"], 1) / 60


def public(game: dict) -> dict:
    """Kopie rozboru bez interních polí (_agg) — to, co se zapisuje do matches/<id>.json."""
    out = dict(game)
    for side in ("home", "away"):
        out[side] = {k: v for k, v in game[side].items() if not k.startswith("_")}
    return out


def analyze_game(raw: dict, fixture: dict | None = None) -> dict:
    """Kompletní rozbor jednoho zápasu (data.json z FIBA LiveStats)."""
    clock = Clock(raw)
    status = game_status(raw)
    final = status == "final"
    tm = raw.get("tm") or {}
    w = walk_pbp(raw, clock)
    minutes = _game_minutes(raw, clock, w, final)

    boxes = {t: team_box(tm.get(str(t)) or {}) for t in (1, 2)}
    advs = {t: advanced(boxes[t], boxes[3 - t], minutes) for t in (1, 2)}
    teams = {}
    for t in (1, 2):
        T = tm.get(str(t)) or {}
        o = 3 - t
        slug, label = identify(T.get("name", ""), T.get("shortName", ""))
        names = {str(k): player_name(p) for k, p in (T.get("pl") or {}).items()}
        players = _players(t, T, w, boxes[t], minutes, clock)
        zones = blank_zones()
        shots = []
        for s in T.get("shot") or []:
            three = s.get("actionType") == "3pt"
            nx, ny = norm_shot(num(s.get("x")), num(s.get("y")))
            z = zone_of(nx, ny, three)
            made = inum(s.get("r")) == 1
            zones[z]["a"] += 1
            zones[z]["m"] += int(made)
            shots.append([round(nx, 1), round(ny, 1), int(made), int(three), inum(s.get("pno")),
                          abs_period(s.get("per"), s.get("perType"))])
            pz = next((p for p in players if p["pno"] == inum(s.get("pno"))), None)
            if pz is not None:
                pz["zones"][z]["a"] += 1
                pz["zones"][z]["m"] += int(made)
        for z in zones.values():
            z["pct"] = pct(z["m"], z["a"])
        att = w["attack"]
        attack = {
            "bands": ATTACK_BANDS, "team": att["team"][t][:5], "unassigned": att["team"][t][5],
            "possessions": att["poss"][t],
            "ptsPerPoss": ratio(sum(att["team"][t]), att["poss"][t]),
            "avgSec": r1(att["sec"][t][0] / att["sec"][t][1]) if att["sec"][t][1] else None,
            "players": sorted(({"pno": int(p), "name": names.get(p, "#" + p), "bands": v[:5], "pts": sum(v)}
                               for p, v in att["P"][t].items() if p in names and sum(v)), key=lambda r: -r["pts"]),
        }
        ast_pairs = sorted(({"passer": names.get(a, "#" + a), "scorer": names.get(b, "#" + b), "ast": v[0], "pts": v[1]}
                            for (a, b), v in w["assists"][t].items()), key=lambda r: (-r["ast"], -r["pts"]))
        cl = w["clutch"][t]
        teams[t] = {
            "tno": t, "name": " ".join((T.get("name") or "").split()),
            "short": " ".join((T.get("shortName") or T.get("name") or "").split()),
            "code": T.get("code", ""), "slug": slug, "label": label,
            "coach": T.get("coach", ""), "logo": (T.get("logoS") or {}).get("url") or (T.get("logoT") or {}).get("url"),
            "score": inum(T.get("score")) if T.get("score") not in (None, "") else w["score"][t],
            "box": boxes[t], "adv": advs[t], "factors": four_factors(advs[t], advs[o]),
            "zones": zones, "shots": shots, "attack": attack, "assistPairs": ast_pairs[:15],
            "lead": {"max": w["lead"]["max"][t], "timeLeadingSec": w["lead"]["time"][t]},
            "biggestRun": max((r["pts"] for r in w["runs"] if r["team"] == t), default=0),
            "clutch": {"pts": cl["pts"], "fgm": cl["fgm"], "fga": cl["fga"], "ftm": cl["ftm"], "fta": cl["fta"],
                       "to": cl["to"], "players": sorted(({"name": names.get(p, "#" + p), "pts": v}
                                                          for p, v in cl["players"].items()), key=lambda r: -r["pts"])},
            "players": players,
            "lineups": _lineups(t, w, {k: _short(v) for k, v in names.items()}),
            "timeouts": w["timeouts"][t],
            # surová data pro sezónní agregaci (build je před zápisem zápasu odstraní)
            "_agg": {
                "fives": [[[names.get(p, "#" + p) for p in key], v] for key, v in w["fives"][t].items()],
                "on": {names.get(p, "#" + p): v for p, v in w["on_player"][t].items()},
                "assists": [[names.get(a, "#" + a), names.get(b, "#" + b), v[0], v[1]]
                            for (a, b), v in w["assists"][t].items()],
                "attackPlayers": {names.get(p, "#" + p): v for p, v in att["P"][t].items() if p in names},
                "attackSec": att["sec"][t],
            },
        }

    s1, s2 = teams[1]["score"], teams[2]["score"]
    out = {
        "fibaId": (fixture or {}).get("fibaId"),
        "nblId": (fixture or {}).get("nblId"),
        "status": status,
        "period": abs_period(raw.get("period"), raw.get("periodType")),
        "periodLabel": period_label(abs_period(raw.get("period"), raw.get("periodType"))),
        "clock": raw.get("clock"),
        "minutes": round(minutes, 2),
        "attendance": inum(raw.get("attendance")) or None,
        "home": teams[1], "away": teams[2],
        "score": {"home": s1, "away": s2},
        "winner": ("home" if s1 > s2 else "away" if s2 > s1 else None) if final else None,
        "quarters": _quarters(raw, w),
        "pace": r1((possessions(boxes[1]) + possessions(boxes[2])) / 2 * 40 / minutes) if minutes else None,
        "flow": {
            "leadChanges": w["lead"]["changes"], "ties": w["lead"]["ties"],
            "timeline": w["timeline"],
            "runs": [{"team": "home" if r["team"] == 1 else "away", "pts": r["pts"], "from": r["from"], "to": r["to"],
                      "start": r["startClock"], "end": r["endClock"]} for r in w["runs"] if r["pts"] >= RUN_MIN],
        },
        "officials": _officials(raw),
    }
    if fixture:
        out["fixture"] = {k: fixture.get(k) for k in ("nblId", "fibaId", "round", "roundNum", "phase", "datetime", "date", "time")}
    if not final:
        out["live"] = _live_block(raw, w, teams, clock)
    return out


def _short(name: str) -> str:
    parts = name.split()
    return f"{parts[0][0]}. {' '.join(parts[1:])}" if len(parts) > 1 else name


def _officials(raw: dict) -> list[str]:
    off = raw.get("officials") or {}
    names = []
    for v in off.values() if isinstance(off, dict) else []:
        if isinstance(v, dict):
            n = " ".join(x for x in (v.get("firstName"), v.get("familyName")) if x) or v.get("name")
            if n:
                names.append(n)
    return names


def _players(t: int, T: dict, w: dict, team_b: dict, game_minutes: float, clock: Clock) -> list[dict]:
    team_secs = sum(w["secs"][t].values()) or game_minutes * 60 * 5
    team_minutes = team_secs / 60
    team_on = new_stint()
    for f in w["fives"][t].values():
        add_stint(team_on, f)
    rows = []
    for k, p in (T.get("pl") or {}).items():
        s = {f: inum(p.get(src)) for f, src in PLAYER_FIELDS.items()}
        mins_official = mmss_to_sec(p.get("sMinutes")) / 60
        mins = mins_official or w["secs"][t].get(str(k), 0) / 60
        played = mins > 0 or s["fga"] or s["fta"] or s["pts"] or s["reb"]
        if not played:
            continue
        on_v = w["on_player"][t].get(str(k)) or new_stint()
        off_v = {key: team_on[key] - on_v[key] for key in STINT_KEYS}
        on_r, off_r = unit_ratings(on_v), unit_ratings(off_v)
        rows.append({
            "pno": inum(k), "name": player_name(p), "short": p.get("scoreboardName") or _short(player_name(p)),
            "shirt": str(p.get("shirtNumber", "")), "pos": p.get("playingPosition") or "",
            "starter": inum(p.get("starter")) == 1, "min": round(mins, 1),
            **s,
            "eff": eff(s), "gmsc": game_score(s),
            "ts": pct(s["pts"], 2 * (s["fga"] + 0.44 * s["fta"])),
            "efg": pct(s["fgm"] + 0.5 * s["tpm"], s["fga"]),
            "usg": usage(s, mins, team_b, team_minutes),
            "astTo": ratio(s["ast"], s["to"]),
            "pm40": r1(s["pm"] * 40 / mins) if mins else None,
            "pts40": r1(s["pts"] * 40 / mins) if mins else None,
            "on": {k2: on_r[k2] for k2 in ("min", "pf", "pa", "ortg", "drtg", "net")},
            "off": {k2: off_r[k2] for k2 in ("min", "ortg", "drtg", "net")},
            "onOff": r1(on_r["net"] - off_r["net"]) if on_r["net"] is not None and off_r["net"] is not None else None,
            "zones": blank_zones(),
            "fouledOut": s["pf"] >= 5,
        })
    rows.sort(key=lambda r: (-r["pts"], -r["min"]))
    return rows


def _live_block(raw: dict, w: dict, teams: dict, clock: Clock) -> dict:
    per = abs_period(raw.get("period"), raw.get("periodType"))
    run = w["current_run"]
    out = {
        "onCourt": {}, "teamFoulsPeriod": {}, "foulTrouble": {}, "timeoutsUsed": {},
        "currentRun": ({"team": "home" if run["team"] == 1 else "away", "pts": run["pts"], "since": run["startClock"]}
                       if run else None),
        "last5min": None,
    }
    for t, side in ((1, "home"), (2, "away")):
        T = raw["tm"].get(str(t)) or {}
        pls = T.get("pl") or {}
        out["onCourt"][side] = [{"pno": inum(p), "name": player_name(pls.get(p, {})), "shirt": str(pls.get(p, {}).get("shirtNumber", ""))}
                                for p in sorted(w["on"][t], key=int)]
        out["teamFoulsPeriod"][side] = w["period_fouls"][per][t]
        out["timeoutsUsed"][side] = w["timeouts"][t]
        half = per <= 2
        out["foulTrouble"][side] = [
            {"name": pl["name"], "shirt": pl["shirt"], "pf": pl["pf"]}
            for pl in teams[t]["players"] if pl["pf"] >= 4 or (half and pl["pf"] >= 3)
        ]
    # skóre za posledních 5 minut hry
    tl = w["timeline"]
    now = w["elapsed"]
    before = 0
    for el, m in tl:
        if el <= now - 300:
            before = m
    cur = tl[-1][1] if tl else 0
    out["last5min"] = {"margin": cur - before}
    return out
