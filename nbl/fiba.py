"""FIBA LiveStats: stažení data.json a archiv surových dat.

FIBA starší zápasy časem přestává servírovat, proto se každý dohraný zápas ukládá
gzipnutý do data/<sezóna>/raw/<fibaId>.json.gz — z archivu se pak dá všechno kdykoliv
přepočítat bez sítě.
"""
from __future__ import annotations

import sys
import time

DATA_URL = "https://fibalivestats.dcd.shared.geniussports.com/data/{fid}/data.json"


def fix_mojibake(text: str) -> str:
    """Stejná pojistka jako v srsni-data: UTF-8 přečtené jako Latin-1 („Å¡“ místo „š“)."""
    import re
    bad = len(re.findall(r"Ã.|Å.|Â.|â€|Ä.", text))
    if not bad:
        return text
    try:
        fixed = text.encode("latin-1", errors="strict").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return fixed if len(re.findall(r"Ã.|Å.|Â.|â€|Ä.", fixed)) < bad else text


def fetch(fid: int, session=None, timeout: int = 15) -> dict | None:
    import json
    import requests
    s = session or requests.Session()
    try:
        r = s.get(DATA_URL.format(fid=fid), timeout=timeout,
                  headers={"User-Agent": "nbl2627-stats/1.0", "Cache-Control": "no-cache"})
    except Exception as e:
        print(f"WARN FIBA {fid}: {e}", file=sys.stderr)
        return None
    if r.status_code != 200:
        if r.status_code != 404:
            print(f"WARN FIBA {fid}: HTTP {r.status_code}", file=sys.stderr)
        return None
    try:
        d = json.loads(fix_mojibake(r.content.decode("utf-8", errors="replace")))
    except ValueError:
        return None
    return d if isinstance(d, dict) and d.get("tm") else None


def fetch_many(ids, delay: float = 0.4) -> dict[int, dict]:
    import requests
    s = requests.Session()
    out = {}
    for fid in ids:
        d = fetch(fid, s)
        if d:
            out[fid] = d
        time.sleep(delay)
    return out


def other_matches(raw: dict) -> list[dict]:
    """FIBA v data.json posílá i souběžné zápasy soutěže (othermatches) — zdroj FIBA ID."""
    out = []
    for m in raw.get("othermatches") or []:
        try:
            out.append({"fibaId": int(m["id"]), "home": (m.get("team1") or {}).get("teamName") or m.get("team1Name"),
                        "away": (m.get("team2") or {}).get("teamName") or m.get("team2Name")})
        except (KeyError, TypeError, ValueError):
            continue
    return out
