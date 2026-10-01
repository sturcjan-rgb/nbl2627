"""Kanonické identity týmů.

NBL web a FIBA LiveStats píší jména týmů různě (sponzorské názvy se mění), proto se tým
pozná podle klíčového slova a dostane stabilní slug — ten se používá v názvech souborů
(data/<sezóna>/teams/<slug>.json) i jako klíč v agregacích.
"""
from __future__ import annotations

import re
import unicodedata

# (regex nad celým jménem, slug, krátké jméno pro grafiku) — pořadí rozhoduje
TEAMS = [
    (r"sr[sš]n|p[ií]sek", "pisek", "Písek"),
    (r"hradec", "hradec", "Hradec"),
    (r"pardubic", "pardubice", "Pardubice"),
    (r"ostrav", "ostrava", "Ostrava"),
    (r"opav", "opava", "Opava"),
    (r"olomou", "olomoucko", "Olomoucko"),
    (r"plze", "plzen", "Plzeň"),
    (r"brno", "brno", "Brno"),
    (r"d[eě][cč][ií]n", "decin", "Děčín"),
    (r"slavia", "slavia", "Slavia"),
    (r"\busk\b", "usk", "USK"),
    (r"sluneta|[uú]st[ií]", "usti", "Ústí"),
    (r"nymburk", "nymburk", "Nymburk"),
    (r"kol[ií]n", "kolin", "Kolín"),
    (r"jindřich|jindrich", "jindrichuv-hradec", "J. Hradec"),
]
_COMPILED = [(re.compile(rx, re.I), slug, label) for rx, slug, label in TEAMS]


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def identify(*names: str) -> tuple[str, str]:
    """(slug, krátké jméno) podle libovolného jména týmu (NBL, FIBA name/shortName)."""
    joined = " ".join(n for n in names if n)
    for rx, slug, label in _COMPILED:
        if rx.search(joined):
            return slug, label
    first = next((n for n in names if n), "")
    return slugify(first) or "unknown", first


def team_slug(*names: str) -> str:
    return identify(*names)[0]
