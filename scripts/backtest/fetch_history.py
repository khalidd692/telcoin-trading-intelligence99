#!/usr/bin/env python3
"""
Téléchargement de l'historique de bougies TEL (lecture seule, API publiques).

Aucune clé API, aucun ordre, uniquement des requêtes GET publiques.
Le cache est local et hors dépôt Git (voir history_store.cache_dir).

Palier P0 par défaut (17 requêtes, ~2 Mo) :
    15m : 4 pages  -> 6000 bougies (~62 j)
    1h  : 4 pages  -> 6000 bougies (~250 j)
    4h  : 4 pages  -> 6000 bougies (~2,7 ans)
    1d  : 2 pages  -> 3000 bougies (~8,2 ans)
    1w  : 1 page   -> 396 bougies (~7,6 ans)
    1M  : 1 page   -> 90 bougies (~7,5 ans)

Exemples :
    python scripts/backtest/fetch_history.py --dry-run
    python scripts/backtest/fetch_history.py --venue kucoin --pages 15m=4,1h=4
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.backtest import history_store as store  # noqa: E402

UA = "telcoin-trading-intelligence-read-only/1.0"
KUCOIN_BASE = "https://api.kucoin.com"
MEXC_BASE = "https://api.mexc.com"

# Une "page" = une requête. KuCoin renvoie au maximum 1500 bougies par appel.
KUCOIN_PAGE_LIMIT = 1500
MEXC_PAGE_LIMIT = 1000

KUCOIN_TYPES = {"15m": "15min", "1h": "1hour", "4h": "4hour", "1d": "1day", "1w": "1week", "1M": "1month"}
MEXC_INTERVALS = {"15m": "15m", "1h": "60m", "4h": "4h", "1d": "1d", "1w": "1W", "1M": "1M"}

# Palier P0 : nombre de pages par unité de temps.
DEFAULT_PAGES = {"15m": 4, "1h": 4, "4h": 4, "1d": 2, "1w": 1, "1M": 1}

MAX_BYTES_DEFAULT = 20_000_000


def now_ms() -> int:
    return int(time.time() * 1000)


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class Budget:
    """Plafond dur de requêtes et d'octets, avec arrêt sur erreurs répétées."""

    def __init__(self, max_requests: int, max_bytes: int, max_consecutive_errors: int = 3) -> None:
        self.max_requests = max_requests
        self.max_bytes = max_bytes
        self.max_consecutive_errors = max_consecutive_errors
        self.requests = 0
        self.bytes = 0
        self.consecutive_errors = 0
        self.stopped = False

    def ok(self) -> bool:
        if self.stopped:
            return False
        if self.consecutive_errors >= self.max_consecutive_errors:
            self.stopped = True
            return False
        return self.requests < self.max_requests and self.bytes < self.max_bytes

    def record_error(self) -> None:
        self.consecutive_errors += 1
        if self.consecutive_errors >= self.max_consecutive_errors:
            self.stopped = True

    def record_success(self) -> None:
        self.consecutive_errors = 0


def http_get(url: str, budget: Budget) -> tuple[Any | None, str | None]:
    budget.requests += 1
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            body = res.read(30_000_000)
    except urllib.error.HTTPError as exc:
        return None, f"HTTP_{exc.code}"
    except Exception as exc:  # pragma: no cover - dépend du réseau
        return None, f"{type(exc).__name__}: {exc}"
    budget.bytes += len(body)
    try:
        return json.loads(body.decode("utf-8")), None
    except json.JSONDecodeError:
        return None, "BAD_JSON"


def fetch_kucoin(timeframe: str, pages: int, budget: Budget, resume_end_s: int | None = None,
                 symbol: str = "TEL-USDT") -> list[dict]:
    """Récupère jusqu'à `pages` pages de 1500 bougies en remontant dans le temps.

    `resume_end_s` : borne haute (secondes) pour continuer une historique
    existante au lieu de refetcher les pages déjà téléchargées.
    """
    period = store.PERIOD_SECONDS[timeframe] or 2678400  # 1M ~ 31 j pour le fenêtrage
    kind = KUCOIN_TYPES[timeframe]
    end = resume_end_s if resume_end_s is not None else (now_ms() // 1000)
    collected: list[dict] = []
    for _ in range(pages):
        if not budget.ok():
            break
        start = end - KUCOIN_PAGE_LIMIT * period
        url = (f"{KUCOIN_BASE}/api/v1/market/candles?"
               + urllib.parse.urlencode({"symbol": symbol, "type": kind,
                                        "startAt": start, "endAt": end}))
        payload, error = http_get(url, budget)
        if error:
            print(f"    ERREUR {timeframe}: {error}", file=sys.stderr)
            budget.record_error()
            continue
        budget.record_success()
        if not isinstance(payload, dict) or payload.get("code") != "200000":
            print(f"    ERREUR {timeframe}: réponse inattendue", file=sys.stderr)
            budget.record_error()
            continue
        rows = payload.get("data") or []
        if not rows:
            break
        for item in rows:
            try:
                collected.append({
                    "t": int(item[0]) * 1000,
                    "o": float(item[1]), "c": float(item[2]),
                    "h": float(item[3]), "l": float(item[4]), "v": float(item[5]),
                })
            except (TypeError, ValueError, IndexError):
                continue
        if len(rows) < KUCOIN_PAGE_LIMIT:
            break  # début de l'historique atteint
        end = min(int(item[0]) for item in rows)
        time.sleep(0.35)
    return collected


def fetch_mexc(timeframe: str, pages: int, budget: Budget, resume_end_s: int | None = None) -> list[dict]:
    """Variante MEXC (structure identique). Non testée localement : api.mexc.com
    ne résout pas depuis ce poste (DNS). À exécuter depuis la CI."""
    interval = MEXC_INTERVALS[timeframe]
    end = resume_end_s if resume_end_s is not None else now_ms()
    collected: list[dict] = []
    for _ in range(pages):
        if not budget.ok():
            break
        url = (f"{MEXC_BASE}/api/v3/klines?"
               + urllib.parse.urlencode({"symbol": store.MEXC_SYMBOL, "interval": interval,
                                        "limit": MEXC_PAGE_LIMIT, "endTime": end}))
        payload, error = http_get(url, budget)
        if error:
            print(f"    ERREUR MEXC {timeframe}: {error}", file=sys.stderr)
            budget.record_error()
            continue
        budget.record_success()
        if not isinstance(payload, list) or not payload:
            break
        for item in payload:
            try:
                collected.append({
                    "t": int(item[0]), "o": float(item[1]), "h": float(item[2]),
                    "l": float(item[3]), "c": float(item[4]), "v": float(item[5]),
                })
            except (TypeError, ValueError, IndexError):
                continue
        if len(payload) < MEXC_PAGE_LIMIT:
            break
        end = min(int(item[0]) for item in payload)
        time.sleep(0.35)
    return collected


def parse_pages(spec: str | None) -> dict[str, int]:
    pages = dict(DEFAULT_PAGES)
    if not spec:
        return pages
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise SystemExit(f"--pages: fragment invalide {chunk!r} (attendu tf=n)")
        tf, value = chunk.split("=", 1)
        tf = tf.strip()
        if tf not in pages:
            raise SystemExit(f"--pages: unité de temps inconnue {tf!r}")
        pages[tf] = int(value)
    return pages


def main() -> int:
    parser = argparse.ArgumentParser(description="Historique de bougies TEL (lecture seule)")
    parser.add_argument("--venue", default="kucoin", choices=["kucoin", "mexc"])
    parser.add_argument("--symbol", default=None,
                        help="symbole KuCoin (ex. TEL-USDT, BTC-USDT, ETH-USDT, TEL-BTC)")
    parser.add_argument("--pages", default=None, help="ex. 15m=4,1h=4,4h=4,1d=2,1w=1,1M=1")
    parser.add_argument("--timeframes", default=None, help="liste séparée par des virgules")
    parser.add_argument("--dry-run", action="store_true", help="affiche le plan sans télécharger")
    parser.add_argument("--refresh", action="store_true", help="re-télécharge même si le cache existe")
    parser.add_argument("--max-requests", type=int, default=40)
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES_DEFAULT)
    parser.add_argument("--resume", action="store_true",
                        help="continue une historique existante vers le passe (ne re-telecharge pas les pages deja prises)")
    parser.add_argument("--backup-dir", default=None,
                        help="copie du cache existant avant ecriture (aucune suppression)")
    args = parser.parse_args()

    pages = parse_pages(args.pages)
    timeframes = ([tf.strip() for tf in args.timeframes.split(",")] if args.timeframes
                  else ["15m", "1h", "4h", "1d", "1w", "1M"])
    symbol = args.symbol or (store.KUCOIN_SYMBOL if args.venue == "kucoin" else store.MEXC_SYMBOL)
    budget = Budget(args.max_requests, args.max_bytes)

    print(f"venue={args.venue} symbol={symbol} cache={store.cache_dir()}")
    print(f"plafonds: {budget.max_requests} requêtes / {budget.max_bytes} octets")
    print("plan de téléchargement :")
    for tf in timeframes:
        print(f"  {tf:>3} : {pages[tf]} page(s) ~ {pages[tf] * (KUCOIN_PAGE_LIMIT if args.venue == 'kucoin' else MEXC_PAGE_LIMIT)} bougies")
    if args.dry_run:
        print("\n--dry-run : aucune requête effectuée.")
        return 0

    for tf in timeframes:
        path = store.cache_path(args.venue, symbol, tf)
        existing = store.read_rows(path) if path.exists() else []
        resume_end = None
        if args.resume and existing:
            # On ne refait pas les pages deja telechargees : on repart de la
            # bougie la plus ancienne du cache et on remonte encore de `pages` pages.
            resume_end = min(int(row["t"]) for row in existing) // 1000 - 1
            print(f"\n[{tf}] REPRISE depuis {iso(min(int(r['t']) for r in existing))} "
                  f"(cache: {len(existing)} bougies)")
        elif path.exists() and not args.refresh:
            rows = store.read_rows(path)
            cov = store.coverage(rows, tf)
            print(f"\n[{tf}] cache présent, ignoré ({cov['count']} bougies) -> {path}")
            continue
        print(f"\n[{tf}] téléchargement {pages[tf]} page(s)...")
        raw = (fetch_kucoin(tf, pages[tf], budget, resume_end, symbol) if args.venue == "kucoin"
               else fetch_mexc(tf, pages[tf], budget, resume_end))
        rows = store.normalize_rows(raw + existing)
        # Exclusion des bougies encore en formation : elles ne doivent jamais
        # alimenter un indicateur ni un signal.
        cutoff = now_ms()
        before = len(rows)
        rows = [r for r in rows if store.close_time_ms(r, tf) <= cutoff]
        if before != len(rows):
            print(f"    {before - len(rows)} bougie(s) en formation exclue(s)")
        if not rows:
            print(f"    AUCUNE DONNEE pour {tf}")
            continue
        cov = store.coverage(rows, tf)
        # VALIDATION AVANT ECRITURE : le cache existant n'est remplace que si le
        # nouveau jeu est continu, trie, sans doublon et sans trou.
        problems = []
        if cov["duplicates"]:
            problems.append(f"{cov['duplicates']} doublon(s)")
        if cov["gaps"]:
            problems.append(f"{len(cov['gaps'])} trou(s)")
        if cov["off_grid"]:
            problems.append(f"{cov['off_grid']} hors-grille")
        if existing and cov["count"] < len(existing):
            problems.append(f"perte de bougies ({len(existing)} -> {cov['count']})")
        if problems:
            print(f"    REFUS D'ECRITURE : {', '.join(problems)}")
            print(f"    (le cache existant est conserve intact)")
            continue
        if args.backup_dir and existing:
            backup_dir = Path(args.backup_dir)
            backup_dir.mkdir(parents=True, exist_ok=True)
            store.write_rows(backup_dir / path.name, existing)
            print(f"    copie de sauvegarde -> {backup_dir / path.name}")
        store.write_rows(path, rows)
        span_days = (cov["to_ms"] - cov["from_ms"]) / 86_400_000
        print(f"    {cov['count']} bougies | {iso(cov['from_ms'])} -> {iso(cov['to_ms'])} ({span_days:.1f} j)")
        print(f"    trous={len(cov['gaps'])} doublons={cov['duplicates']} hors-grille={cov['off_grid']} statut={cov['status']}")
        print(f"    -> {path}")

    print(f"\nconsommation : {budget.requests} requêtes, {budget.bytes} octets"
          + (" (ARRÊT : erreurs répétées)" if budget.stopped else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
