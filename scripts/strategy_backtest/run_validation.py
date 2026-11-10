"""Rejeu unique selon PROTOCOLE_STRATEGIE_FIGE.md. Écrit results/strategy_validation/*."""
import csv, dataclasses, hashlib, json, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.strategy_backtest import engine as E
from scripts.strategy_backtest import history_quality as Q

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
       "validated_data": Q.load_history(
           DATA, as_of=Q.utc_timestamp(Q.manifest()[DATA]["closed_before"])).report,
       "params": dataclasses.asdict(p),
       "costs_hypothetical_per_side": {k: dataclasses.asdict(v) for k,v in E.COSTS.items()},
       "phase_diagnostics": {},
       "holdout_status": "already exposed; not an untouched final test",
       "results": {}}
rrs = sorted((c.rr_gross for c in cands if c.rr_gross), reverse=True)
res["rr_gross_top10"] = [round(x, 3) for x in rrs[:10]]
res["candidates_with_rr"] = len(rrs)

journal, clog = [], []
for cname, cost in E.COSTS.items():
    res["results"][cname] = {}
    state = E.RunState(p, cost)
    for ph, (a, b) in PH.items():
        phase_capital = state.equity
        tr, log = E.run(cands, p, cost, a, b, state=state)
        res["results"][cname][ph] = E.metrics(tr, phase_capital)
        for t in tr:
            journal.append({"scenario": cname, "phase": ph, **dataclasses.asdict(t)})
        if cname == "central":
            res["phase_diagnostics"][ph] = {
                "candidates": len(log),
                "branches": dict(Counter(r['branch'] for r in log)),
                "statuses": dict(Counter(r['statut'] for r in log)),
                "starting_equity": phase_capital, "ending_equity": state.equity}
            clog += [{"phase": ph, **r} for r in log]
    tot = [r["n"] for r in res["results"][cname].values()]
    res["results"][cname]["N_total"] = sum(tot)
    # Verify the production phase runner against one chronological simulation.
    continuous, _ = E.run(cands, p, cost, 0, N)
    phased = [r for r in journal if r['scenario'] == cname]
    if [dataclasses.asdict(t) for t in continuous] != [
            {k:v for k,v in row.items() if k not in ('scenario','phase')} for row in phased]:
        raise AssertionError('Continuous and phase simulations differ')

json.dump(res, open(OUT / "results.json", "w"), indent=2, default=str)
for name, rows in (("journal_trades.csv", journal), ("journal_candidats.csv", clog)):
    if rows:
        with open(OUT / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    else:
        # An empty journal still publishes its schema; zero trades is a result.
        columns = ['scenario', 'phase'] + [f.name for f in dataclasses.fields(E.Trade)]
        with open(OUT / name, 'w', newline='') as f:
            csv.writer(f, lineterminator='\n').writerow(columns)
print(json.dumps({k: v for k, v in res.items() if k != "results"}, indent=1, default=str))
print(json.dumps(res["results"], indent=1, default=str))
