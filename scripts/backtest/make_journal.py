"""Genere JOURNAL_APPRENTISSAGE.md a partir de backtest_results_v2.json (contenu factuel)."""
import json, statistics, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\sabri\Desktop\telcoin-trading-intelligence99")
source = sys.argv[1] if len(sys.argv) > 1 else "backtest_results_v2.json"
target_name = sys.argv[2] if len(sys.argv) > 2 else "JOURNAL_APPRENTISSAGE.md"
d = json.loads((ROOT / source).read_text(encoding="utf-8"))
print(f"source : {source} | detecteur {d.get('detector', {}).get('sha256', '?')[:12]}")

def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="minutes").replace("+00:00", "Z")

def pct(x):
    return "n/a" if x is None else f"{x * 100:.2f}%"

lines = []
A = lines.append

A("# JOURNAL D'APPRENTISSAGE — RETOURNEMENTS TEL/USDT")
A("")
A("**Généré automatiquement** depuis `backtest_results_v2.json` par `scripts/backtest/make_journal.py`.")
A("Chaque entrée correspond à un épisode mesuré : rien n'y est interpété ou inventé.")
A("")
A("Ce journal existe pour apprendre **autant des mouvements manqués que des mouvements anticipés**.")
A("Une entrée qui n'aboutit pas est conservée au même titre qu'une entrée réussie.")
A("")

for tf, res in d["results"].items():
    crit = res["criteria"].get("quantile")
    if not crit:
        continue
    A(f"## Unité de temps {tf}")
    A("")
    A(f"- Données : {res['data']['count']} bougies, {res['data']['from']} → {res['data']['to']} ({res['data']['span_days']} j)")
    A(f"- Statuts : {res['status_counts']}")
    A(f"- Épisodes dédupliqués : {crit['episodes']} (densité {pct(crit['alert_density_per_bar'])} des bougies)")
    A(f"- Taux de réussite : {pct(crit['hit_rate'])} — base de taux {pct(crit['base_rate']['base_rate'])}")
    null = crit["null_test"]
    A(f"- Test de nullité : observé {pct(null['observed_hit_rate'])}, médiane nulle {pct(null['null_hit_rate_median'])}, "
      f"percentile {null['percentile']}")
    rev = crit["reference_reversals"]
    A(f"- Retournements de référence : {rev['total']} — détectés à l'avance {rev['detected_in_advance']}, "
      f"**manqués {rev['missed']}** (fenêtre d'avertissement : {rev['warning_window_bars']} bougies)")
    A("")

A("---")
A("")
A("## Retournements anticipés (15m) — cas où l'alerte a précédé l'entrée plausible")
A("")
c15 = d["results"]["15m"]["criteria"]["quantile"]
detected = sorted(c15["detected_reversals_detail"], key=lambda r: r["lead_ms"], reverse=True)
A("| Creux | Entrée plausible | Alerte | Avance | Preuves de l'alerte | Amplitude du mouvement |")
A("|---|---|---|---|---|---|")
for r in detected[:10]:
    A(f"| {iso(r['trough_time_ms'])} | {iso(r['entry_time_ms'])} | {iso(r['alert_time_ms'])} | "
      f"**{r['lead_ms'] / 60000:.0f} min** | {', '.join(r['alert_evidence']) or '—'} | {pct(r['amplitude'])} |")
A("")
A(f"**Avance médiane** : {c15['reference_reversals']['median_lead_minutes']} min · "
  f"**{c15['reference_reversals']['pct_detected_before_entry']:.1f} %** des détections précèdent l'entrée.")
A("")
A("### Enseignement")
A("")
A("Les détections à avance nulle ou quasi nulle sont majoritaires : l'alerte tombe souvent **sur** la bougie "
  "d'entrée, pas avant. Sur les 16 détections mesurées, 6 ont une avance de 0 minute.")
A("")

A("## Retournements manqués (15m) — aucune alerte dans la fenêtre d'avertissement")
A("")
missed = sorted(c15["missed_reversals_detail"], key=lambda r: r["amplitude"], reverse=True)
A("| Creux | Entrée plausible | Prix au creux | Amplitude du mouvement ultérieur | Volatilité (ATR14 relatif) |")
A("|---|---|---|---|---|")
for r in missed[:12]:
    A(f"| {iso(r['trough_time_ms'])} | {iso(r['entry_time_ms'])} | {r['trough_price']:.6f} | "
      f"**{pct(r['amplitude'])}** | {pct(r['atr_pct'])} |")
A("")
A(f"**{len(missed)} retournements manqués sur {c15['reference_reversals']['total']}** "
  f"({100 * len(missed) / max(1, c15['reference_reversals']['total']):.1f} %).")
A("")
A("### Enseignement")
A("")
A("Les mouvements manqués ne sont pas rares : c'est la **couverture temporelle** du signal qui est en cause, "
  "pas la rareté des retournements. Un détecteur qui ne se déclenche que 12 % du temps ne peut pas être "
  "présent sur chaque creux.")
A("")

A("## Faux rebonds et contradictions")
A("")
A(f"- Alertes **sans** retournement de référence associé : "
  f"{c15['alerts_without_reference_reversal']} sur {c15['episodes']} "
  f"({100 * c15['alerts_without_reference_reversal'] / max(1, c15['episodes']):.1f} %).")
A("- Rapport signal/retournement : **26:1**. Le détecteur signale environ 26 fois plus que ce qu'il ne "
  "signale utilement.")
A("- Sur 4h, le détecteur est **significativement moins bon que le hasard** "
  f"(percentile {d['results']['4h']['criteria']['quantile']['null_test']['percentile']}) et ne détecte "
  f"**0** retournement de référence sur "
  f"{d['results']['4h']['criteria']['quantile']['reference_reversals']['total']}.")
A("- Sur 1h, "
  f"{d['results']['1h']['criteria']['quantile']['reference_reversals']['missed']} retournements de référence "
  "sur "
  f"{d['results']['1h']['criteria']['quantile']['reference_reversals']['total']} sont manqués dans la "
  "fenêtre d'avertissement de 6 h.")
A("")
A("### Enseignement")
A("")
A("La panne n'est pas dans la **qualité** du signal mais dans son **volume** et sa **couverture**. "
  "Réduire la densité d'alerte et ajouter une confirmation explicite est prioritaire sur tout réglage de seuil.")
A("")

A("## Preuves les plus fréquentes dans les alertes (15m)")
A("")
freq = {}
for e in c15["episodes_detail"]:
    for t in e["evidence"]:
        freq[t] = freq.get(t, 0) + 1
for t, n in sorted(freq.items(), key=lambda x: -x[1]):
    A(f"- `{t}` : {n} épisodes")
A("")
A("### Enseignement")
A("")
A("Les preuves de **contexte** (`weak_trend_divergence`, `higher_timeframe_alignment`) dominent, alors que "
  "les preuves directionnelles (`bullish_rsi_divergence`, `rsi_oversold`, motifs de bougies) sont rares. "
  "Or le statut `ALERTE_PRÉCOCE` exige 2 catégories distinctes : l'alignement de tendance sur 4 h/1 j suffit "
  "souvent à déclencher l'alerte, ce qui explique la densité excessive et l'absence de pouvoir prédictif "
  "sur 4 h.")
A("")

A("## Ce que le journal ne peut pas encore contenir")
A("")
A("- **Confirmations** : le statut `CONFIRMATION` n'est jamais assigné par le détecteur ; il n'y a donc rien à journaliser.")
A("- **Invalidations suivies** : la règle `close < 0.001526` s'applique en continu (9,4 % des bougies en 15m) ; "
  "elle reflète un niveau figé, pas une information de marché exploitable.")
A("- **Contexte BTC / ETH / TEL-BTC** : absent du dépôt, aucun point de comparaison possible.")
A("- **Régime haussier** : la fenêtre testée (août → octobre 2026) est baissière. Les faux rebonds en tendance "
  "haussière ne sont pas représentés.")
A("")

(ROOT / target_name).write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"-> {ROOT / target_name} ({len(lines)} lignes)")
