"""
Stockage local de l'historique de bougies TEL (hors dépôt Git).

Format : JSONL compressé gzip, une bougie par ligne, clés abrégées.
    {"t": <open_time_ms>, "o": open, "h": high, "l": low, "c": close, "v": volume}

Le cache n'est jamais commité : il vit dans TEL_HISTORY_DIR (ou %LOCALAPPDATA%/telcoin/history).
Stdlib uniquement (contrainte CI : aucun requirements.txt, aucun package.json).
"""

from __future__ import annotations

import gzip
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

# Durées des unités de temps, en secondes. None = mois (durée variable).
PERIOD_SECONDS: dict[str, int | None] = {
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
    "1M": None,
}

# Identifiants de venue et de symbole.
KUCOIN = "kucoin"
KUCOIN_SYMBOL = "TEL-USDT"
MEXC = "mexc"
MEXC_SYMBOL = "TELUSDT"

_ROW_KEYS = ("t", "o", "h", "l", "c", "v")


def cache_dir() -> Path:
    """Répertoire de cache, configurable par TEL_HISTORY_DIR."""
    env = os.environ.get("TEL_HISTORY_DIR")
    if env:
        base = Path(env)
    else:
        local = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        base = Path(local) / "telcoin" / "history"
    base.mkdir(parents=True, exist_ok=True)
    return base


def cache_path(venue: str, symbol: str, timeframe: str) -> Path:
    slug = symbol.replace("/", "_").replace("-", "_")
    return cache_dir() / f"{venue}_{slug}_{timeframe}.jsonl.gz"


def _valid_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    try:
        t = int(row["t"])
        o, h, l, c, v = (float(row["o"]), float(row["h"]), float(row["l"]), float(row["c"]), float(row["v"]))
    except (KeyError, TypeError, ValueError):
        return False
    if not all(math.isfinite(x) for x in (o, h, l, c, v)):
        return False
    if min(o, h, l, c) <= 0 or v < 0:
        return False
    if h < max(o, c, l) or l > min(o, c) or h < l:
        return False
    return t > 0


def normalize_rows(raw_rows: Iterable[dict]) -> list[dict]:
    """Dédoublonne, trie, valide et normalise en lignes compactes."""
    unique: dict[int, dict] = {}
    for raw in raw_rows:
        if not _valid_row(raw):
            continue
        t = int(raw["t"])
        unique[t] = {"t": t, "o": float(raw["o"]), "h": float(raw["h"]),
                     "l": float(raw["l"]), "c": float(raw["c"]), "v": float(raw["v"])}
    return [unique[k] for k in sorted(unique)]


def write_rows(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    tmp.replace(path)
    return path


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_timeframe(venue: str, symbol: str, timeframe: str) -> list[dict]:
    """Charge un jeu de bougies en excluant toute bougie encore en formation.

    Garde-fou : meme si le cache contient une bougie non clôturée (téléchargement
    effectué juste avant sa clôture), elle n'est jamais utilisée.
    """
    import time as _time
    now_ms = int(_time.time() * 1000)
    rows = read_rows(cache_path(venue, symbol, timeframe))
    return [row for row in rows if close_time_ms(row, timeframe) <= now_ms]


def close_time_ms(row: dict, timeframe: str) -> int:
    """Timestamp de clôture d'une bougie (pour l'alignement multi-unités de temps)."""
    t = int(row["t"])
    seconds = PERIOD_SECONDS.get(timeframe)
    if seconds is None:  # 1M : fin du mois civil UTC
        import datetime as dt
        start = dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc)
        if start.month == 12:
            end = dt.datetime(start.year + 1, 1, 1, tzinfo=dt.timezone.utc)
        else:
            end = dt.datetime(start.year, start.month + 1, 1, tzinfo=dt.timezone.utc)
        return int(end.timestamp() * 1000)
    return t + seconds * 1000


def coverage(rows: list[dict], timeframe: str) -> dict:
    """Couverture temporelle, pas de temps et intégrité d'un jeu de bougies."""
    if not rows:
        return {"count": 0, "from_ms": None, "to_ms": None, "gaps": [], "duplicates": 0,
                "off_grid": 0, "status": "UNAVAILABLE"}
    seconds = PERIOD_SECONDS.get(timeframe)
    gaps: list[dict] = []
    off_grid = 0
    duplicates = 0
    for index, row in enumerate(rows):
        t = int(row["t"])
        if seconds:
            if t % (seconds * 1000) != 0:
                off_grid += 1
        if index == 0:
            continue
        prev = int(rows[index - 1]["t"])
        if prev == t:
            duplicates += 1
            continue
        step = (t - prev) / 1000
        if seconds and step != seconds:
            gaps.append({"after_ms": prev, "before_ms": t, "missing_intervals": int(step // seconds) - 1})
    return {
        "count": len(rows),
        "from_ms": int(rows[0]["t"]),
        "to_ms": int(rows[-1]["t"]),
        "gaps": gaps,
        "duplicates": duplicates,
        "off_grid": off_grid,
        "status": "UNAVAILABLE" if gaps else ("PARTIEL" if off_grid else "OK"),
    }


def to_snapshot_rows(rows: list[dict]) -> list[dict]:
    """Convertit vers le format du snapshot de production (open_time ISO + OHLCV)."""
    from datetime import datetime, timezone

    out = []
    for row in rows:
        opened = datetime.fromtimestamp(int(row["t"]) / 1000, timezone.utc)
        out.append({
            "open_time": opened.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "open": row["o"], "high": row["h"], "low": row["l"], "close": row["c"], "volume": row["v"],
        })
    return out
