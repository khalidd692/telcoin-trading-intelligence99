"""Rejeu unique selon PROTOCOLE_STRATEGIE_FIGE.md. Écrit results/strategy_validation/*."""
import csv, dataclasses, hashlib, json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.strategy_backtest import engine as E

DATA = "data/KRAKEN_TELUSD_4h_2026-01-22_2026-11-08.csv"
OUT = Path("results/strategy_validation"); OUT.mkdir(parents=True, exist_ok=True)
p = E.Params()
bars = E.load_csv(DATA)
N = len(bars); b1, b2 = int(.6 * N), int(.8 * N)
PH = {"IS": (0, b1), "VAL": (b1, b2), "OOS": (b2, N)}
segs = E.build_segments(bars, p)
cands = [E.build_order(c, p) for c in E.candidates(segs)]

res = {"data_sha256": hashlib.sha256(open(DATA, "rb").read()).hexdigest(), "n_bars": N,
       "segments": [(s.offset, s.n) for s in segs],
       "phases": {k: [bars[a].ts.isoformat(), bars[b - 1].close_ts.isoformat()] for k, (a, b) in PH.items()},
       "candidates_total": len(cands), "candidates_by_branch": dict(Counter(c.branch for c in cands)),
       "candidate_status": dict(Counter(c.status for c in cands)),
       "rr_gross_max": max((c.rr_gross for c in cands if c.rr_gross), default=None),
       "results": {}}
rrs = sorted((c.rr_gross for c in cands if c.rr_gross), reverse=True)
res["rr_gross_top10"] = [round(x, 3) for x in rrs[:10]]
res["candidates_with_rr"] = len(rrs)

journal, clog = [], []
for cname, cost in E.COSTS.items():
    res["results"][cname] = {}
    for ph, (a, b) in PH.items():
        tr, log = E.run(cands, p, cost, a, b)
        res["results"][cname][ph] = E.metrics(tr, p.capital)
        for t in tr:
            journal.append({"scenario": cname, "phase": ph, **dataclasses.asdict(t)})
        if cname == "central":
            clog += [{"phase": ph, **r} for r in log]
    tot = [r["n"] for r in res["results"][cname].values()]
    res["results"][cname]["N_total"] = sum(tot)

json.dump(res, open(OUT / "results.json", "w"), indent=2, default=str)
for name, rows in (("journal_trades.csv", journal), ("journal_candidats.csv", clog)):
    if rows:
        with open(OUT / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    else:
        open(OUT / name, "w").write("")
print(json.dumps({k: v for k, v in res.items() if k != "results"}, indent=1, default=str))
print(json.dumps(res["results"], indent=1, default=str))
