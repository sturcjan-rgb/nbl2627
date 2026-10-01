"""Drobné společné pomůcky (čísla, čas, JSON zápis)."""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any


def num(value: Any, default: float = 0) -> float:
    """FIBA feed občas posílá čísla jako stringy nebo prázdné hodnoty."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def inum(value: Any, default: int = 0) -> int:
    return int(num(value, default))


def pct(a: float, b: float) -> float | None:
    return round(100.0 * a / b, 1) if b else None


def ratio(a: float, b: float, digits: int = 2) -> float | None:
    return round(a / b, digits) if b else None


def r1(x: float | None) -> float | None:
    return None if x is None else round(x, 1)


def mmss_to_sec(s: Any) -> int:
    """'09:18' / '199:60' / '00:22:50' (mm:ss:cc) -> sekundy."""
    parts = str(s or "0:0").split(":")
    try:
        m = int(parts[0] or 0)
        x = int(parts[1] or 0) if len(parts) > 1 else 0
    except ValueError:
        return 0
    return m * 60 + x


def sec_to_mmss(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60}:{sec % 60:02d}"


def write_json(path: Path, data: Any, *, compact: bool = False) -> bool:
    """Zapíše JSON jen když se obsah změnil (ať git nevidí zbytečné změny). Vrací True při změně."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(data, ensure_ascii=False, indent=1)
    text += "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_gz(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    # mtime=0 -> deterministický výstup, git nevidí změnu u stejných dat
    with open(path, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
        gz.write(raw)
