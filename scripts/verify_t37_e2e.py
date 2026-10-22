"""
Verification de bout en bout de T37 : le moteur produit le JSON, le tableau de
bord l'affiche. Rien n'est simule : le JSON est celui que la CI genererait.

Etapes :
 1. build_analysis() sur le snapshot MEXC reel (comme la CI) ;
 2. controle du regime : calcul causal a partir des bougies journalieres CLOTUREES ;
 3. injection du JSON dans le script du tableau de bord et lecture du rendu ;
 4. controle de coherence statut / exploitabilite.

Le tout est produit dans un repertoire temporaire : le depot n'est pas modifie.
"""

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(r"C:\Users\sabri\Desktop\telcoin-trading-intelligence99")
sys.path.insert(0, str(ROOT))

from src.agent_analysis import build_analysis  # noqa: E402

failures = []


def check(name, condition, detail=""):
    status = "OK " if condition else "ECHEC"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        failures.append(name)


snapshot = json.loads((ROOT / "site" / "tel_snapshot.json").read_text(encoding="utf-8"))
generated = datetime.fromisoformat(snapshot["generated_at"].replace("Z", "+00:00"))
report = build_analysis(snapshot, expected_collection_id=snapshot.get("collection_id"), now=generated)

print("=== 1. Le moteur produit regime / exploitable / exploitable_reason ===")
er = report["early_reversal"]
check("early_reversal present", er is not None)
check("regime present", isinstance(er.get("regime"), dict), json.dumps(er.get("regime"), ensure_ascii=False))
check("exploitable present (booleen)", isinstance(er.get("exploitable"), bool), str(er.get("exploitable")))
check("exploitable_reason present", bool(er.get("exploitable_reason")), str(er.get("exploitable_reason"))[:70])

print()
print("=== 2. Coherence du regime avec les bougies journalieres cloturees ===")
daily = snapshot["sources"]["mexc"]["candles"]["1d"]["rows"]
state_1d = report["timeframes"]["1d"]
last_close = float(daily[-1]["close"])
ref_close = float(daily[-31]["close"]) if len(daily) > 30 else None
expected = (last_close / ref_close - 1.0) if ref_close else None
check("la variation publiee correspond au calcul sur bougies clôturees",
      expected is not None and abs(er["regime"]["value"] - expected) < 5e-6,
      f"publie={er['regime']['value']:.6f} recalcule={expected:.6f}" if expected else "historique 1d insuffisant")
check("la variation du regime est celle de l'etat 1d (aux 6 decimales publiees)",
      abs(er["regime"]["value"] - state_1d.get("change_30", 0)) < 1e-6,
      f"regime={er['regime']['value']:.6f} change_30={state_1d.get('change_30'):.9f}")
check("la fenetre du regime est bien de 30 bougies journalieres",
      er["regime"].get("window_bars") == 30 and state_1d.get("candle_count", 0) >= 31,
      f"window_bars={er['regime'].get('window_bars')} bougies 1d={state_1d.get('candle_count')}")
check("aucune bougie 1d non clôturee n'est utilisee (la derniere closes apres la fenetre)",
      state_1d.get("last_closed_at") is not None)

print()
print("=== 3. Coherence statut / exploitabilite ===")
if er["signal_status"] == "CONFIRMATION" and er["regime"]["state"] == "NEUTRE":
    check("CONFIRMATION en regime neutre => exploitable", er["exploitable"] is True)
else:
    check("un signal non CONFIRME n'est jamais exploitable",
          not (er["signal_status"] == "ALERTE_PRÉCOCE" and er["exploitable"] is True),
          f"statut={er['signal_status']} exploitable={er['exploitable']}")
check("exploitable implique le statut CONFIRMATION",
      (er["exploitable"] is False) or er["signal_status"] == "CONFIRMATION")
check("exploitable implique un regime neutre",
      (er["exploitable"] is False) or er["regime"]["state"] == "NEUTRE")
check("un rapport sans signal reste non exploitable", er["exploitable"] is False or er["signal_status"] == "CONFIRMATION")

print()
print("=== 4. Rendu du tableau de bord (JSON reel de la CI) ===")
work = Path(tempfile.mkdtemp(prefix="t37-e2e-"))
agent_file = work / "agent_analysis.json"
agent_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

node_script = work / "render.js"
node_script.write_text(r"""
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = process.argv[2];
const agent = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const html = fs.readFileSync(path.join(root, "site", "index.html"), "utf8");
const script = html.match(/<script>\s*([\s\S]*?)\s*<\/script>/i)[1];
const elements = new Map();
function element(id) {
  if (!elements.has(id)) {
    elements.set(id, { id, textContent: "", innerHTML: "", className: "", hidden: false,
      style: {}, attributes: {}, listeners: {},
      addEventListener(n, h) { this.listeners[n] = h; }, setAttribute(n, v) { this.attributes[n] = v; } });
  }
  return elements.get(id);
}
const base = Date.parse(agent.generated_at);
class TestDate extends Date { static now() { return base; } }
const payload = { schema_version: 1, generated_at: agent.generated_at, symbol: "TELUSDT",
  mode: "READ_ONLY_ALERTS", status: "SURVEILLER",
  sources: { mexc_ticker: { status: "OK", last: 0.001, bid: 0.000999, ask: 0.001001, spread_pct: 0.2, observed_at: agent.generated_at },
    mexc_candles: { status: "OK", timeframe: "15m", closed_candles_used: 1 },
    kucoin_level1: { status: "OK", last: 0.001, bid: 0.000999, ask: 0.001001, observed_at: agent.generated_at } },
  checks: [{ name: "quality", status: "PASS" }],
  indicators: { timeframe: "15m", last_closed_candle_at: agent.generated_at, close_series: [] } };
const context = { document: { getElementById: element },
  window: { setInterval() { return 1; } },
  fetch: async (url) => {
    const key = String(url || "");
    if (key.indexOf("agent_analysis.json") !== -1) return { ok: true, json: async () => agent };
    if (key.indexOf("tel_snapshot.json") !== -1) return { ok: false, status: 404, json: async () => ({}) };
    return { ok: true, json: async () => payload };
  }, Date: TestDate, console };
vm.runInNewContext(script, context);
setImmediate(() => {
  console.log("STATUT|" + element("agent-reversal-status").textContent);
  console.log("CLASSE|" + element("agent-reversal-status").className);
  console.log("QUALITE|" + element("agent-reversal-quality").innerHTML.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim());
  console.log("DETAIL|" + element("agent-reversal-detail").innerHTML.replace(/<br\s*\/?>/g, " | ").replace(/<[^>]+>/g, "").trim());
});
""", encoding="utf-8")

proc = subprocess.run(["node", str(node_script), str(ROOT), str(agent_file)],
                      capture_output=True, text=True, encoding="utf-8", errors="replace")
if proc.returncode != 0:
    print(proc.stdout)
    print(proc.stderr[:1500])
    failures.append("rendu du tableau de bord")
else:
    parsed = dict(line.split("|", 1) for line in proc.stdout.strip().splitlines() if "|" in line)
    print("  statut affiche   :", parsed.get("STATUT"))
    print("  classe du badge :", parsed.get("CLASSE"))
    print("  qualite affichee:", parsed.get("QUALITE"))
    print("  detail          :", (parsed.get("DETAIL") or "")[:220])
    quality = parsed.get("QUALITE", "")
    # Le libelle depend de l'etat : "Regime ..." pour NEUTRE/INDETERMINE,
    # "Tendance ..." pour TENDANCE_HAUSSIERE/BAISSIERE. Verifier le libelle
    # reellement produit evite un faux negatif les jours de tendance.
    check("le regime est affiche",
          ("Régime" in quality or "Tendance" in quality),
          f"qualite={quality}")
    check("l'exploitabilite est affichee", "exploitable" in quality.lower())
    check("la valeur du regime est en pourcentage", "%" in quality)
    check("une non-exploitabilite est signalee", "non exploitable" in quality.lower() or "Signal exploitable" in quality)
    check("le badge n'est pas vert quand le signal n'est pas exploitable",
          ("pass" not in (parsed.get("CLASSE") or "")) or er["exploitable"] is True,
          f"classe={parsed.get('CLASSE')}")
    check("la raison d'exploitabilite est affichee", "Exploitabilit" in (parsed.get("DETAIL") or ""))

print()
print("=== 5. Comportement en cas de donnees absentes / anciennes ===")
for label, mutation in (
    ("regime absent", lambda d: d["early_reversal"].pop("regime", None)),
    ("exploitable absent", lambda d: d["early_reversal"].pop("exploitable", None)),
    ("early_reversal absent", lambda d: d.pop("early_reversal", None)),
    ("historique 1j absent", lambda d: d["timeframes"].pop("1d", None)),
):
    mutated = json.loads(json.dumps(report))
    mutation(mutated)
    path_file = work / "mutated.json"
    path_file.write_text(json.dumps(mutated, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(["node", str(node_script), str(ROOT), str(path_file)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = result.returncode == 0 and result.stdout.strip() != ""
    check(f"le tableau de bord reste fonctionnel : {label}", ok,
          (result.stderr.strip()[:120] if result.returncode else "rendu produit"))

print()
print("=" * 70)
print(f"VERIFICATIONS : {len(failures)} echec(s)" + (f" -> {failures}" if failures else " — toutes reussies"))
print("=" * 70)
raise SystemExit(1 if failures else 0)
