"""Rozpis celé ligy z nbl.basketball.

Dva zdroje, oba ověřené v předchozích projektech:
1. týmové stránky https://nbl.basketball/tym/<slug> (srsni-data/season-scraper.mjs) — tabulka
   „Zápasy YYYY/YY“ s koly, datem, skóre, čtvrtinami a u blízkých zápasů i FIBA LiveStats ID.
   Slugy všech týmů se seberou z odkazů /tym/<slug> na stránkách (tabulka ligy, rozpis).
2. ligový rozpis https://nbl.basketball/zapasy?y=<rok>&c=<id týmu> (srsni-truth/discovery.py) —
   datum v atributu data-sort, týmy v listových <div>, u některých řádků i FIBA odkaz.

Výsledek se slučuje podle nblId (merge-not-overwrite) do data/<sezóna>/schedule.json, takže
jednou zjištěné FIBA ID ani skóre se dalším během neztratí.
"""
from __future__ import annotations

import re
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .teams import identify

BASE = "https://nbl.basketball"
SCHEDULE_URL = BASE + "/zapasy"
SEED_TEAM_SLUGS = ["srsni-photomate-pisek"]
USER_AGENT = "nbl2627-stats/1.0 (osobni statisticky projekt; github.com/sturcjan-rgb/nbl2627)"
DELAY = 0.8
PRAGUE = ZoneInfo("Europe/Prague")

MATCH_RE = re.compile(r"/zapas/(\d+)")
FIBA_RE = re.compile(r"fibalivestats\.com/webcast/[^/\s\"']+/(\d+)")
TEAM_LINK_RE = re.compile(r"^(?:https?://nbl\.basketball)?/tym/([a-z0-9-]+)/?$")
DATE_SORT_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})$")
DATE_TEXT_RE = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\s+(\d{1,2}):(\d{2})")
SCORE_RE = re.compile(r"(?<![\d:.])(\d{1,3})\s*[:–-]\s*(\d{1,3})(?![\d:.])")

# Kanonická jména (rozdělení buňky „domácí / hosté“ podle pozice) — doplňuje se o jména
# nalezená v tabulce ligy, takže nový sponzorský název nevadí.
KNOWN_TEAMS = [
    "Sršni Photomate Písek", "USK Praha", "SLUNETA Ústí nad Labem", "SK Slavia Praha ERA NBK",
    "PUMPA Basket Brno", "NH Ostrava", "BK Opava", "BK Olomoucko", "BK Loko BaliMania Plzeň",
    "BK Lokomotiva Plzeň", "BK KVIS Pardubice", "BK GAPA Hradec Králové", "BK ARMEX ENERGY Děčín",
    "ERA Basketball Nymburk",
]


def season_start_year(season: str) -> int:
    return int(season.split("/")[0])


def season_key(season: str) -> str:
    a, b = season.split("/")
    return f"{a}-{b}"


def current_season(today: datetime | None = None) -> str:
    today = today or datetime.now(timezone.utc)
    y = today.year if today.month >= 7 else today.year - 1
    return f"{y}/{str(y + 1)[-2:]}"


def to_iso(y: int, mo: int, d: int, h: int, mi: int) -> str:
    return datetime(y, mo, d, h, mi, tzinfo=PRAGUE).isoformat()


# ------------------------------------------------------------------ síť

class Fetcher:
    def __init__(self):
        import requests
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self.last = 0.0

    def get(self, url: str, params: dict | None = None) -> str | None:
        wait = DELAY - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = self.s.get(url, params=params, timeout=20)
            self.last = time.time()
            if r.status_code != 200:
                print(f"WARN {url} {params or ''} -> HTTP {r.status_code}", file=sys.stderr)
                return None
            return r.text
        except Exception as e:  # síťové chyby nesmí shodit celý build
            self.last = time.time()
            print(f"WARN {url} -> {e}", file=sys.stderr)
            return None


def soup_of(html: str):
    from bs4 import BeautifulSoup
    # lxml: některé řádky rozpisu mají poškozené HTML, html.parser by je ztratil (viz srsni-truth)
    return BeautifulSoup(html, "lxml")


# ------------------------------------------------------------------ parsování

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def split_teams(text: str, known: list[str]) -> tuple[str | None, str | None]:
    found = sorted(((text.find(t), t) for t in known if t in text), key=lambda x: x[0])
    # vyhodit jména, která jsou podřetězcem delšího nalezeného jména na stejné pozici
    uniq = []
    for idx, t in found:
        if any(idx >= i and idx + len(t) <= i + len(u) and t != u for i, u in found):
            continue
        uniq.append((idx, t))
    if len(uniq) >= 2:
        return uniq[0][1], uniq[1][1]
    return None, None


def _teams_from_cell(cell, known: list[str]) -> tuple[str | None, str | None]:
    leaf = [d for d in cell.find_all(["div", "span", "a"]) if not d.find(["div", "span", "a"])]
    texts = [_norm(d.get_text(" ")) for d in leaf]
    texts = [t for t in texts if t and not SCORE_RE.fullmatch(t) and not re.fullmatch(r"[-–:/\s]+", t)]
    if len(texts) >= 2:
        return texts[0], texts[1]
    return split_teams(_norm(cell.get_text(" ")), known)


def _date_from_row(cells) -> tuple[str | None, str | None]:
    for c in cells:
        raw = c.get("data-sort") or ""
        m = DATE_SORT_RE.match(raw)
        if m:
            y, mo, d, h, mi = map(int, m.groups())
            return to_iso(y, mo, d, h, mi), f"{h:02d}:{mi:02d}"
    for c in cells:
        m = DATE_TEXT_RE.search(_norm(c.get_text(" ")))
        if m:
            d, mo, y, h, mi = map(int, m.groups())
            return to_iso(y, mo, d, h, mi), f"{h:02d}:{mi:02d}"
    return None, None


def _header_map(table) -> dict:
    first = table.find("tr")
    if not first:
        return {}
    cols = {}
    for i, c in enumerate(first.find_all(["th", "td"])):
        t = _norm(c.get_text(" ")).lower()
        if "kolo" in t:
            cols["round"] = i
        elif "datum" in t:
            cols["date"] = i
        elif "domácí" in t or "hosté" in t:
            cols["teams"] = i
        elif "skóre" in t or "skore" in t:
            cols["score"] = i
        elif "čtvrtin" in t:
            cols["quarters"] = i
        elif "fáze" in t:
            cols["phase"] = i
    return cols


def quarters_from(nums: list[int], fh: int, fa: int) -> list[dict]:
    """Kumulativní mezistavy z NBL tabulky -> body po periodách (stejně jako srsni-data)."""
    pairs = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
    checkpoints = pairs + [(fh, fa)]
    out, ph, pa = [], 0, 0
    for h, a in checkpoints:
        if h < ph or a < pa:  # nesedí (tabulka posílá něco jiného) -> radši nic
            return []
        out.append({"home": h - ph, "away": a - pa})
        ph, pa = h, a
    return out


def parse_rows(html: str, known: list[str]) -> list[dict]:
    """Projde všechny tabulky stránky a vytáhne řádky se zápasy (odkaz /zapas/<id>)."""
    soup = soup_of(html)
    main = soup.find("main") or soup
    out: dict[int, dict] = {}
    for table in main.find_all("table"):
        cols = _header_map(table)
        for tr in table.find_all("tr"):
            row_html = str(tr)
            m = MATCH_RE.search(row_html)
            if not m:
                continue
            nbl_id = int(m.group(1))
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            dt, tm = _date_from_row(cells)
            teams_cell = cells[cols["teams"]] if "teams" in cols and cols["teams"] < len(cells) else None
            if teams_cell is None:
                teams_cell = next((c for c in cells if len([d for d in c.find_all("div") if not d.find("div")]) >= 2), None)
            home, away = _teams_from_cell(teams_cell, known) if teams_cell is not None else (None, None)
            if not home:
                home, away = split_teams(_norm(tr.get_text(" ")), known)
            # skóre: buňka „skóre“, jinak odkaz na detail odehraného zápasu (#tab-pane-one)
            score = None
            score_text = ""
            if "score" in cols and cols["score"] < len(cells):
                score_text = _norm(cells[cols["score"]].get_text(" "))
            else:
                for a in tr.find_all("a", href=True):
                    if MATCH_RE.search(a["href"]) and "tab-pane-two" not in a["href"]:
                        score_text = _norm(a.get_text(" "))
                        if SCORE_RE.search(score_text):
                            break
            sm = SCORE_RE.search(score_text)
            if sm:
                score = {"home": int(sm.group(1)), "away": int(sm.group(2))}
            elif "score" in cols:
                nums = re.findall(r"\d+", score_text)  # srsni-data: „78 80“ bez oddělovače
                if len(nums) >= 2:
                    score = {"home": int(nums[0]), "away": int(nums[1])}
            round_txt = _norm(cells[cols["round"]].get_text(" ")) if "round" in cols and cols["round"] < len(cells) else ""
            if not round_txt:
                rm = re.search(r"(\d+)\.\s*kolo", tr.get_text(" "))
                round_txt = rm.group(0) if rm else ""
            phase = _norm(cells[cols["phase"]].get_text(" ")) if "phase" in cols and cols["phase"] < len(cells) else ""
            quarters = []
            if score and "quarters" in cols and cols["quarters"] < len(cells):
                nums = [int(x) for x in re.findall(r"\d+", cells[cols["quarters"]].get_text(" "))]
                quarters = quarters_from(nums, score["home"], score["away"])
            fm = FIBA_RE.search(row_html)
            rec = {
                "nblId": nbl_id, "fibaId": int(fm.group(1)) if fm else None,
                "round": round_txt or None, "phase": phase or None,
                "datetime": dt, "time": tm, "home": home, "away": away,
                "score": score, "quarters": quarters or None,
            }
            prev = out.get(nbl_id)
            out[nbl_id] = merge_fixture(prev, rec) if prev else rec
    return list(out.values())


def team_links(html: str) -> dict[str, str]:
    """slug -> jméno týmu ze všech odkazů /tym/<slug> na stránce."""
    soup = soup_of(html)
    out = {}
    for a in soup.find_all("a", href=True):
        m = TEAM_LINK_RE.match(a["href"].split("?")[0].split("#")[0])
        if m:
            name = _norm(a.get_text(" "))
            if m.group(1) not in out or (name and len(name) > len(out[m.group(1)])):
                out[m.group(1)] = name
    return out


def team_select_options(html: str) -> dict[str, str]:
    """<select name="c"> na /zapasy: id týmu -> jméno."""
    soup = soup_of(html)
    sel = soup.find("select", attrs={"name": "c"})
    if not sel:
        return {}
    return {o.get("value"): _norm(o.get_text(" ")) for o in sel.find_all("option")
            if (o.get("value") or "0") not in ("", "0")}


def season_heading(html: str) -> str | None:
    m = re.search(r"Zápasy\s+(\d{4})/(\d{2})", html)
    return f"{m.group(1)}/{m.group(2)}" if m else None


# ------------------------------------------------------------------ slučování

FIELDS = ["fibaId", "round", "phase", "datetime", "time", "home", "away", "score", "quarters"]


def merge_fixture(old: dict | None, new: dict) -> dict:
    """Nové hodnoty přepíšou staré, ale prázdné (None) hodnoty nic nesmažou."""
    out = dict(old or {})
    for k, v in new.items():
        if v not in (None, "", []) or k not in out:
            out[k] = v
    return out


def finalize(f: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    rm = re.match(r"(\d+)", f.get("round") or "")
    f["roundNum"] = int(rm.group(1)) if rm else None
    if f.get("datetime"):
        f["date"] = f["datetime"][:10]
    hs, hl = identify(f.get("home") or "")
    as_, al = identify(f.get("away") or "")
    f["homeSlug"], f["awaySlug"] = hs, as_
    f["homeLabel"], f["awayLabel"] = hl, al
    if f.get("status") != "final":
        started = f.get("datetime") and datetime.fromisoformat(f["datetime"]) <= now
        if f.get("score") and started:
            f["status"] = "final"
        elif started and datetime.fromisoformat(f["datetime"]) + timedelta(hours=3) > now:
            f["status"] = "live"
        else:
            f["status"] = f.get("status") if f.get("status") in ("postponed",) else ("scheduled" if not started else "unknown")
    fid = f.get("fibaId")
    f["links"] = {
        "nbl": f"{BASE}/zapas/{f['nblId']}",
        "livestats": f"https://www.fibalivestats.com/webcast/CBFFE/{fid}/" if fid else None,
        "fibaData": f"https://fibalivestats.dcd.shared.geniussports.com/data/{fid}/data.json" if fid else None,
        "stats": f"matches/{fid}.json" if fid else None,
    }
    return f


# ------------------------------------------------------------------ hlavní běh

def discover(season: str, fetcher: "Fetcher", existing: list[dict] | None = None, *, debug: bool = False) -> dict:
    """Stáhne rozpis celé ligy. Vrací {"fixtures": [...], "teams": {slug: name}, "sources": {...}}."""
    known = list(KNOWN_TEAMS)
    by_id: dict[int, dict] = {f["nblId"]: dict(f) for f in existing or []}
    sources = {"teamPages": 0, "schedulePages": 0, "rows": 0}
    team_pages: dict[str, str] = {}

    # 1) ligový rozpis bez filtru + seznam týmů ze <select name="c">
    y = season_start_year(season)
    base_params = {"y": y, "p1": 0, "k": 0, "d_od": "", "d_do": ""}
    html = fetcher.get(SCHEDULE_URL, base_params)
    options = {}
    if html:
        options = team_select_options(html)
        team_pages.update(team_links(html))
        known += [n for n in options.values() if n and n not in known]
        rows = parse_rows(html, known)
        sources["schedulePages"] += 1
        sources["rows"] += len(rows)
        _absorb(by_id, rows)
        if debug:
            _debug_dump("zapasy", html)

    # 2) rozpis po týmech (filtr c=<id>) — jistota, že máme všechny zápasy všech týmů
    for cid in options:
        html = fetcher.get(SCHEDULE_URL, {**base_params, "c": cid})
        if not html:
            continue
        rows = parse_rows(html, known)
        sources["schedulePages"] += 1
        sources["rows"] += len(rows)
        _absorb(by_id, rows)

    # 3) týmové stránky (FIBA ID u blízkých zápasů, čtvrtiny) — slugy z odkazů + seed
    seeds = list(dict.fromkeys(SEED_TEAM_SLUGS + list(team_pages)))
    seen = set()
    while seeds:
        slug = seeds.pop(0)
        if slug in seen:
            continue
        seen.add(slug)
        html = fetcher.get(f"{BASE}/tym/{slug}")
        if not html:
            continue
        head = season_heading(html)
        links = team_links(html)
        for s2, n in links.items():
            team_pages.setdefault(s2, n)
            if s2 not in seen and len(seen) < 30:
                seeds.append(s2)
        if head and head != season:
            continue  # stránka už/ještě ukazuje jinou sezónu -> nemíchat
        rows = parse_rows(html, known)
        sources["teamPages"] += 1
        sources["rows"] += len(rows)
        _absorb(by_id, rows)
        if debug and slug == SEED_TEAM_SLUGS[0]:
            _debug_dump("tym", html)

    fixtures = [finalize(f) for f in by_id.values() if f.get("datetime")]
    fixtures = [f for f in fixtures if _in_season(f, season)]
    fixtures.sort(key=lambda f: (f["datetime"], f["nblId"]))
    teams = {}
    for f in fixtures:
        for side in ("home", "away"):
            if f.get(side):
                teams.setdefault(f[side + "Slug"], f[side])
    return {"fixtures": fixtures, "teams": teams, "teamPages": team_pages, "sources": sources}


def _in_season(f: dict, season: str) -> bool:
    y = season_start_year(season)
    d = f["datetime"][:10]
    return f"{y}-07-01" <= d <= f"{y + 1}-06-30"


def _absorb(by_id: dict, rows: list[dict]) -> None:
    for r in rows:
        by_id[r["nblId"]] = merge_fixture(by_id.get(r["nblId"]), r)


def _debug_dump(name: str, html: str) -> None:
    soup = soup_of(html)
    main = soup.find("main") or soup
    rows = [tr for tr in main.find_all("tr") if MATCH_RE.search(str(tr))]
    print(f"--- DEBUG {name}: {len(rows)} řádků se zápasem, {len(main.find_all('table'))} tabulek")
    for tr in rows[:3]:
        print(str(tr)[:3000])
        print("...")
    sel = soup.find("select", attrs={"name": "c"})
    print("select c:", str(sel)[:1500] if sel else None)


def resolve_fiba_ids(fixtures: list[dict], fetcher: "Fetcher", *, days_back: int = 10, days_ahead: int = 3) -> int:
    """Zápasům bez FIBA ID v okně kolem dneška zkusí ID najít na stránce detailu zápasu."""
    now = datetime.now(timezone.utc)
    n = 0
    for f in fixtures:
        if f.get("fibaId") or not f.get("datetime"):
            continue
        t = datetime.fromisoformat(f["datetime"])
        if not (now - timedelta(days=days_back) <= t <= now + timedelta(days=days_ahead)):
            continue
        html = fetcher.get(f"{BASE}/zapas/{f['nblId']}")
        m = FIBA_RE.search(html or "")
        if m:
            f["fibaId"] = int(m.group(1))
            finalize(f)
            n += 1
    return n
