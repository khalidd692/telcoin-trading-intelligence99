"""
Moteur de backtest DÉDIÉ à la stratégie « TEL Kraken – repli 4h dans tendance ».

Ce moteur est indépendant de scripts/backtest/engine.py (ancien évaluateur du
détecteur de retournement). Il reproduit la spécification de
research/ETAT_CONTINUATION_TEL_2026-11-08.md. Aucune règle n'est ajustée ici.

Conventions fixées (voir PROTOCOLE_STRATEGIE_FIGE.md) :
- EMA : amorcée par la SMA des n premières valeurs (convention TradingView).
- ATR(14) Wilder : TR de la 1re barre = high-low ; amorçage SMA(14) du TR.
- Pivot haut 5/5 : high[i] strictement > les 5 hauts à gauche et >= les 5 hauts à droite.
  Pivot bas 5/5 : low[i] strictement < les 5 bas à gauche et <= les 5 bas à droite.
  Un pivot en i n'est connu qu'à la clôture de la barre i+5.
- Branche B : cassure = 1re clôture > niveau après confirmation du pivot ; retest = 1re barre
  suivante dont low <= niveau ; valide seulement si cette barre clôture > niveau, est haussière
  et clôture > EMA20 (la barre de retest EST la barre de confirmation).
- Les séries sont coupées aux trous de données (un trou = écart != 4h) ; rien n'est interpolé,
  et un trade dont la fenêtre complète (entrée + expiration) sort du segment est exclu.
"""
from __future__ import annotations

import csv
import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

BAR = dt.timedelta(hours=4)
UTC = dt.timezone.utc


@dataclass(frozen=True)
class Bar:
    ts: dt.datetime
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0

    @property
    def close_ts(self) -> dt.datetime:
        return self.ts + BAR


@dataclass(frozen=True)
class Params:
    ema_fast: int = 20
    ema_slow: int = 50
    atr_n: int = 14
    pivot: int = 5
    atr_stop_mult: float = 0.5
    rr_min: float = 1.51
    expiry_bars: int = 20
    capital: float = 1000.0
    risk_frac: float = 0.0025
    daily_loss_frac: float = 0.01
    cooldown_after_stop_bars: int = 1


@dataclass(frozen=True)
class Costs:
    name: str
    fee: float
    slip: float


COSTS = {
    "brut": Costs("brut", 0.0, 0.0),
    "central": Costs("central", 0.0025, 0.0010),
    "prudent": Costs("prudent", 0.0040, 0.0030),
}


def load_csv(path: str) -> List[Bar]:
    """Load hash-pinned Kraken history after quarantine; strategy stays 4h."""
    from scripts.strategy_backtest.history_quality import load_history
    history = load_history(path)
    if history.report['timeframe'] != '4h':
        raise ValueError('The existing Kraken strategy requires 4h bars')
    return [Bar(r['timestamp_utc'], r['open'], r['high'], r['low'], r['close'], r['volume'])
            for r in history.rows]


def split_segments(bars: List[Bar]) -> List[Tuple[int, int]]:
    if not bars:
        return []
    segs, s = [], 0
    for i in range(1, len(bars)):
        if bars[i].ts - bars[i - 1].ts != BAR:
            segs.append((s, i))
            s = i
    segs.append((s, len(bars)))
    return segs


def ema(values: List[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < n:
        return out
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    k = 2.0 / (n + 1)
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def true_range(bars: List[Bar]) -> List[float]:
    tr = []
    for i, b in enumerate(bars):
        if i == 0:
            tr.append(b.h - b.l)
        else:
            pc = bars[i - 1].c
            tr.append(max(b.h - b.l, abs(b.h - pc), abs(b.l - pc)))
    return tr


def atr_wilder(bars: List[Bar], n: int = 14) -> List[Optional[float]]:
    tr = true_range(bars)
    out: List[Optional[float]] = [None] * len(bars)
    if len(bars) < n:
        return out
    prev = sum(tr[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(bars)):
        prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


def pivots(bars: List[Bar], k: int = 5) -> Tuple[List[bool], List[bool]]:
    n = len(bars)
    ph, pl = [False] * n, [False] * n
    for i in range(k, n - k):
        left_h = max(b.h for b in bars[i - k:i]); right_h = max(b.h for b in bars[i + 1:i + k + 1])
        left_l = min(b.l for b in bars[i - k:i]); right_l = min(b.l for b in bars[i + 1:i + k + 1])
        ph[i] = bars[i].h > left_h and bars[i].h >= right_h
        pl[i] = bars[i].l < left_l and bars[i].l <= right_l
    return ph, pl


class Segment:
    """Indicateurs d'un segment continu ; indices LOCAUX, offset = indice global du début."""

    def __init__(self, bars: List[Bar], offset: int, p: Params):
        if any(b.ts.tzinfo is None or b.ts.utcoffset() != dt.timedelta(0) for b in bars):
            raise ValueError('Segment timestamps must be UTC')
        if any(b.ts - a.ts != BAR for a, b in zip(bars, bars[1:])):
            raise ValueError('Segment must contain consecutive 4h bars; use build_segments')
        self.bars, self.offset, self.p = bars, offset, p
        self.n = len(bars)
        self._run_states = {}
        closes = [b.c for b in bars]
        self.e_fast = ema(closes, p.ema_fast)
        self.e_slow = ema(closes, p.ema_slow)
        self.atr = atr_wilder(bars, p.atr_n)
        self.ph, self.pl = pivots(bars, p.pivot)
        self._retests = self._compute_retests()

    def last_pivot_low(self, t: int) -> Optional[Tuple[int, float]]:
        for i in range(t - self.p.pivot, -1, -1):
            if self.pl[i]:
                return i, self.bars[i].l
        return None

    def first_resistance_above(self, t: int, price: float) -> Optional[Tuple[int, float]]:
        best = None
        for i in range(0, t - self.p.pivot + 1):
            if self.ph[i] and self.bars[i].h > price and (best is None or self.bars[i].h < best[1]):
                best = (i, self.bars[i].h)
        return best

    def _compute_retests(self) -> Dict[int, List[float]]:
        """{barre de retest: [niveaux]} ; causal : le retest en r ne dépend que de barres <= r."""
        k, out = self.p.pivot, defaultdict(list)
        for pi in range(self.n):
            if not self.ph[pi]:
                continue
            level, conf = self.bars[pi].h, pi + k
            b = next((j for j in range(conf + 1, self.n) if self.bars[j].c > level), None)
            if b is None:
                continue
            r = next((j for j in range(b + 1, self.n) if self.bars[j].l <= level), None)
            if r is not None and self.bars[r].c > level:
                out[r].append(level)
        return out

    def signal(self, t: int) -> Optional[str]:
        e20, e50 = self.e_fast[t], self.e_slow[t]
        if e20 is None or e50 is None or self.atr[t] is None:
            return None
        b = self.bars[t]
        if not (e20 > e50 and b.c > e50):
            return None
        bull = b.c > b.o and b.c > e20
        a = b.l <= e20 and bull
        bb = bool(self._retests.get(t)) and bull
        return "A+B" if a and bb else "A" if a else "B" if bb else None


def build_segments(bars: List[Bar], p: Params) -> List[Segment]:
    return [Segment(bars[s:e], s, p) for s, e in split_segments(bars)]


@dataclass
class Candidate:
    t: int
    branch: str
    segment: Segment
    status: str = ""
    entry: float = 0.0
    stop: float = 0.0
    target: float = 0.0
    rr_gross: float = 0.0


@dataclass
class Trade:
    id: int
    branch: str
    signal_ts: str
    entry_ts: str
    exit_ts: str
    entry_ref: float
    stop: float
    target: float
    rr_gross: float
    exit_ref: float
    exit_reason: str
    bars_held: int
    qty: float
    risk_usd: float
    fees_usd: float
    slippage_usd: float
    pnl_usd: float
    r_multiple: float
    equity_after: float


def candidates(segments: List[Segment]) -> List[Candidate]:
    out = []
    for seg in segments:
        for t in range(seg.n):
            br = seg.signal(t)
            if br:
                out.append(Candidate(t + seg.offset, br, seg))
    return out


def build_order(c: Candidate, p: Params) -> Candidate:
    seg, tl = c.segment, c.t - c.segment.offset
    if tl + 1 >= seg.n:
        c.status = "rejet:pas_de_barre_suivante_dans_le_segment"; return c
    if tl + 1 + p.expiry_bars >= seg.n:
        c.status = "exclu:fenetre_incomplete_(fin_de_donnees_ou_trou)"; return c
    c.entry = seg.bars[tl + 1].o
    pl = seg.last_pivot_low(tl)
    if pl is None:
        c.status = "rejet:pas_de_pivot_bas"; return c
    c.stop = pl[1] - p.atr_stop_mult * seg.atr[tl]
    if c.stop <= 0 or c.stop >= c.entry:
        c.status = "rejet:stop_invalide_ou_au_dessus_de_l_entree"; return c
    res = seg.first_resistance_above(tl, c.entry)
    if res is None:
        c.status = "rejet:pas_de_resistance_au_dessus"; return c
    c.target = res[1]
    c.rr_gross = (c.target - c.entry) / (c.entry - c.stop)
    c.status = "ok" if c.rr_gross >= p.rr_min else "rejet:rr_inferieur_au_minimum"
    return c


def simulate_exit(seg: Segment, tl: int, stop: float, target: float, p: Params):
    i = tl + 1
    if tl < 0 or i + p.expiry_bars >= seg.n:
        raise ValueError('Trade horizon crosses segment boundary')
    for k in range(i, i + p.expiry_bars + 1):
        b = seg.bars[k]
        if b.o <= stop:
            return k, b.o, "stop_gap"
        if b.l <= stop:
            return k, stop, "stop"
        if b.h >= target:
            return k, target, "cible"
        if k == i + p.expiry_bars:
            return k, b.c, "expiration"
    raise AssertionError("inatteignable")


@dataclass
class RunState:
    """Portfolio shared by consecutive phase windows of one cost scenario.

    Trades belong to their signal phase and are simulated through their exit,
    even across a boundary; free_t keeps that position/cooldown reserved.
    """
    params: Params
    cost: Costs
    equity: float = field(init=False)
    free_t: int = -1
    tid: int = 0
    realized: Dict[dt.date, float] = field(default_factory=lambda: defaultdict(float))
    next_t: Optional[int] = None

    def __post_init__(self):
        self.equity = self.params.capital


def run(cands: List[Candidate], p: Params, cost: Costs, t_lo: int, t_hi: int,
        *, state: Optional[RunState] = None):
    """Run [t_lo, t_hi), retaining portfolio state across adjacent phases.

    Pass state explicitly when phases can have no candidates or use different
    segments. For existing callers, adjacent calls on shared segments resume
    automatically; a window starting at zero starts a fresh simulation.
    """
    segments = {c.segment for c in cands}
    key = (p, cost)
    if state is None:
        previous = [seg._run_states.get(key) for seg in segments]
        resumable = [s for s in previous if s is not None and s.next_t == t_lo]
        if t_lo != 0 and resumable:
            state = resumable[0]
            if any(s is not state for s in resumable):
                raise ValueError("Conflicting phase states; pass state explicitly")
        else:
            state = RunState(p, cost)
    if state.params != p or state.cost != cost:
        raise ValueError("Phase parameters and costs must match the portfolio state")
    if t_hi < t_lo or (state.next_t is not None and state.next_t != t_lo):
        raise ValueError("Portfolio phase windows must be adjacent and chronological")
    equity, trades, log = state.equity, [], []
    free_t, tid = state.free_t, state.tid
    realized = state.realized
    for c in cands:
        if not (t_lo <= c.t < t_hi):
            continue
        row = {"signal_ts": c.segment.bars[c.t - c.segment.offset].close_ts.isoformat(), "branch": c.branch,
               "statut": c.status, "rr_brut": round(c.rr_gross, 4) if c.rr_gross else ""}
        if c.status != "ok":
            log.append(row); continue
        seg, tl = c.segment, c.t - c.segment.offset
        if tl < 0 or tl + 1 + p.expiry_bars >= seg.n:
            row['statut'] = 'exclu:fenetre_incomplete_(fin_de_donnees_ou_trou)'
            log.append(row)
            continue
        if c.t < free_t:
            row["statut"] = "rejet:position_ouverte_ou_cooldown"; log.append(row); continue
        entry_day = seg.bars[tl + 1].ts.date()
        day_start = equity - realized[entry_day]
        if realized[entry_day] <= -p.daily_loss_frac * day_start:
            row["statut"] = "rejet:perte_quotidienne_max"; log.append(row); continue
        buy = c.entry * (1 + cost.slip)
        stop_sell = c.stop * (1 - cost.slip)
        loss_unit = buy - stop_sell + cost.fee * (buy + stop_sell)
        risk_usd = p.risk_frac * equity
        qty = risk_usd / loss_unit
        qty = min(qty, equity / (buy * (1 + cost.fee)))
        k, ref, why = simulate_exit(seg, tl, c.stop, c.target, p)
        sell = ref * (1 - cost.slip)
        fees = cost.fee * qty * (buy + sell)
        slip_usd = qty * (c.entry * cost.slip + ref * cost.slip)
        pnl = qty * (sell - buy) - fees
        equity += pnl
        exit_close = seg.bars[k].close_ts
        realized[exit_close.date()] += pnl
        free_t = c.segment.offset + k + (p.cooldown_after_stop_bars if why.startswith("stop") else 0)
        tid += 1
        trades.append(Trade(tid, c.branch, row["signal_ts"], seg.bars[tl + 1].ts.isoformat(), exit_close.isoformat(),
                            c.entry, c.stop, c.target, c.rr_gross, ref, why, k - tl, qty, risk_usd, fees, slip_usd,
                            pnl, pnl / risk_usd, equity))
        row["statut"] = "trade"; log.append(row)
    state.equity, state.free_t, state.tid = equity, free_t, tid
    state.next_t = t_hi
    for seg in segments:
        seg._run_states[key] = state
    return trades, log


def metrics(trades: List[Trade], capital: float) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0}
    w = [t.pnl_usd for t in trades if t.pnl_usd > 0]; l = [t.pnl_usd for t in trades if t.pnl_usd <= 0]
    eq, peak, mdd = capital, capital, 0.0
    for t in trades:
        eq = t.equity_after; peak = max(peak, eq); mdd = max(mdd, (peak - eq) / peak)
    gp, gl = sum(w), -sum(l)
    pnl = [t.pnl_usd for t in trades]
    top3 = sum(sorted(pnl, reverse=True)[:3])
    return {"n": n, "win_rate": len(w) / n, "avg_win_usd": gp / len(w) if w else 0.0,
            "avg_loss_usd": -gl / len(l) if l else 0.0, "expectancy_usd": sum(pnl) / n,
            "expectancy_R": sum(t.r_multiple for t in trades) / n,
            "profit_factor": (gp / gl) if gl > 0 else float("inf"),
            "net_return_pct": 100 * (trades[-1].equity_after - capital) / capital, "max_drawdown_pct": 100 * mdd,
            "avg_bars_held": sum(t.bars_held for t in trades) / n,
            "pnl_sans_top3_usd": sum(pnl) - top3, "exits": dict(Counter(t.exit_reason for t in trades))}
