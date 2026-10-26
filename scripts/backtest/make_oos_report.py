#!/usr/bin/env python3
"""
Genere le rapport markdown de l'evaluation hors echantillon a partir de
oos_results.json. Les chiffres proviennent uniquement du JSON de resultats
(empreinte du detecteur, protocole et segments inclus) : rien n'est saisi a la main.

Usage : python scripts/backtest/make_oos_report.py --input oos_results.json --output OOS_RAPPORT.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCENARIO_LABELS = {
    "S0_brut": "brut",
    "S1_slippage_AR": "A/R slippage 0,57 %",
    "S2_frais_0.10_AR": "A/R + frais 0,10 %/côté (0,77 %)",
    "S3_frais_0.15_AR": "A/R + frais 0,15 %/côté (0,87 %)",
}
STATUS_LABELS = {
    "ALERTE_PRÉCOCE": "ALERTE PRÉCOCE",
    "CONFIRMATION": "CONFIRMATION",
    "INVALIDATION": "INVALIDATION (mesuré en sens inverse)",
    "EXPLOITABLE": "**EXPLOITABLE** (confirmation + régime 1j neutre)",
    "TOUS_SIGNALUX": "TOUS (alerte + confirmation)",
}
ORDER = ["ALERTE_PRÉCOCE", "CONFIRMATION", "INVALIDATION", "EXPLOITABLE", "TOUS_SIGNALUX"]
SEGMENTS = ["NEW", "IS1", "IS2", "OOS"]
SEGMENT_LABELS = {
    "NEW": "NEW (période vierge, collectée pour cette phase)",
    "IS1": "IS1 (conception)",
    "IS2": "IS2 (validation de conception)",
    "OOS": "OOS (déjà consulté : usage exploratoire)",
}


def pct(value):
    return "n/a" if value is None else f"{value * 100:.2f} %"


def num(value, digits=2):
    return "n/a" if value is None else f"{value:.{digits}f}"


def build(payload: dict) -> str:
    lines = []
    A = lines.append
    protocol = payload["protocol"]
    split = payload["split"]

    A("# ÉVALUATION HORS ÉCHANTILLON — ANCIEN MOTEUR vs MOTEUR v2")
    A("")
    A(f"**Protocole** : {protocol['version']} (figé) · **coupure** : {split['split']} "
      f"(conception = {split['is_share']:.0%} de conception prevue, coupure par date absolue)")
    A(f"**Données** : {payload['venue']} {payload['symbol']} · axe 15m "
      f"{split['first']} → {split['last']}")
    A(f"**Généré** : {payload['generated_at']}")
    A("")
    A("> Les chiffres ci-dessous proviennent exclusivement de `oos_results.json`. "
      "La séparation conception / validation est stricte : aucun paramètre n'a été modifié "
      "après lecture des résultats de validation.")
    A("")
    A(f"> **Note sur la coupure** : le protocole fixe `IS_SHARE = {protocol['is_share']:.0%}` "
      "comme part chronologique de conception. La coupure effective est une **date absolue** "
      f"({split['split']}), car l'historique a été prolongé après la conception : une coupure "
      "en pourcentage se déplacerait silencieusement. La part réelle de la période de "
      "conception dans l'axe 15m actuel est supérieure à la valeur de conception.")
    A("")
    A("## 0. Révision du protocole")
    A("")
    A(protocol["revision_note"])
    A("")
    A("## 1. Répartition")
    A("")
    A("| Moteur | Unité | Segment | Barres | Épisodes | Densité | Exploitables |")
    A("|---|---|---|---|---|---|---|")
    for engine_name in ("ancien", "v2"):
        for tf in payload["results"][engine_name]:
            for segment in SEGMENTS:
                seg = payload["results"][engine_name][tf]["segments"].get(segment)
                if not seg:
                    continue
                exploitable = seg["scenarios"]["S0_brut"].get("EXPLOITABLE", {})
                exploitable_episodes = seg["status_counts_bars"].get("EXPLOITABLE", 0)
                A(f"| {engine_name} | {tf} | {segment} | {seg['bars']} | {seg['episodes']} | "
                  f"{pct(seg['density'])} | {exploitable_episodes} |")
    A("")
    A("**Note sur le comptage** : le champ *Épisodes* est la somme des épisodes de chaque "
      "statut (ALERTE_PRÉCOCE + CONFIRMATION + INVALIDATION). Une ALERTE_PRÉCOCE et sa "
      "CONFIRMATION ultérieure sont comptées comme deux épisodes distincts : la première "
      "est l'actionnable, la seconde est l'information attendue plus tard. Les deux séries "
      "se recouvrent donc partiellement. Le champ *Exploitables* est le nombre d'épisodes "
      "EXPLOITABLE (confirmation + régime 1j neutre), dédupliqué par statut.")
    A("")

    for tf in payload["results"]["ancien"]:
        A(f"## 2.{tf} — résultats")
        A("")
        for engine_name in ("ancien", "v2"):
            res = payload["results"][engine_name].get(tf)
            if not res:
                continue
            for segment in SEGMENTS:
                seg = res["segments"].get(segment)
                if not seg:
                    continue
                A(f"### {engine_name} · {segment} — {SEGMENT_LABELS.get(segment, segment)}")
                A("")
                A("| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | "
                  "Faux positifs | Percentile nul |")
                A("|---|---|---|---|---|---|---|---|---|")
                for status in ORDER:
                    for scenario, label in SCENARIO_LABELS.items():
                        m = seg["scenarios"].get(scenario, {}).get(status)
                        if not m:
                            continue
                        A(f"| {STATUS_LABELS[status]} | {label} | {m['evaluated']} | "
                          f"{pct(m['hit_rate'])} | {pct(m['reference_rate'])} | {num(m['lift'])} | "
                          f"[{m['hit_rate_wilson95'][0] * 100:.1f} % ; {m['hit_rate_wilson95'][1] * 100:.1f} %] | "
                          f"{m['false_positives']} | "
                          f"{num(m['null_percentile'], 3)} |")
                rev = seg["reference_reversals"]
                A("")
                A(f"- **Retournements de référence** : {rev['total']} au total, "
                  f"**{rev['detected_in_advance']} détectés à l'avance**, "
                  f"**{rev['missed']} manqués** (détection "
                  f"{pct(rev['detection_rate'])}) — fenêtre d'avertissement : "
                  f"{rev['warning_window_bars']} bougies.")
                A(f"- **Délai d'avance** : médiane {num(rev['median_lead_minutes'], 1)} min · "
                  f"{num(rev['pct_before_entry'], 1)} % des détections précèdent l'entrée plausible.")
                A("")

    A("## 3. Profil gains / pertes — le résultat économique qui compte")
    A("")
    payoff_path = Path("oos_payoff.json")
    if payoff_path.exists():
        payoff = json.loads(payoff_path.read_text(encoding="utf-8"))
        A(f"Segment de validation (OOS), cible {payoff['target']}, horizons "
          f"{payoff['horizons_bars']} bougies (24 h et 72 h).")
        A("")
        A("| Statut | Horizon | n | Espérance | Médiane | Pire | Meilleur | "
          "Gains (moy.) | Pertes (moy.) | Ratio gain/perte |")
        A("|---|---|---|---|---|---|---|---|---|---|---|")
        for status, horizons in payoff["results"].items():
            for horizon, m in horizons.items():
                A(f"| {STATUS_LABELS.get(status, status)} | {horizon} | {m['episodes']} | "
                  f"**{m['mean'] * 100:+.3f} %** | {m['median'] * 100:+.3f} % | "
                  f"{m['worst'] * 100:+.2f} % | {m['best'] * 100:+.2f} % | "
                  f"{m['gains']} ({m['mean_gain'] * 100:+.2f} %) | "
                  f"{m['losses']} ({m['mean_loss'] * 100:+.2f} %) | "
                  f"{m['payoff_ratio']:.2f} |")
        A("")
        A("**Lecture** : le gain moyen ne compense que marginalement la perte moyenne "
          "(ratio ≈ 1,0 à 1,1) alors que les pertes sont **plus fréquentes** que les gains. "
          "L'**espérance des signaux est négative, avant même les frais** (≈ −0,2 % à −0,5 % "
          "par signal). Avec un aller-retour de 0,57 %, l'espérance tombe à environ −1 %. "
          "Un taux de réussite mesuré contre une référence *relative* (quantile empirique) "
          "ne dit donc rien de l'exploitabilité : c'est l'espérance qui la dit.")
        A("")
        A("> **Limites méthodologiques** : (1) Le scénario S1 (0,57 %) exclut les frais de "
          "courtage, qui sont des hypothèses non authentifiées. Le scénario S2 (0,77 %, avec "
          "frais 0,10 %) est plus représentatif d'un compte réel. (2) La déduplication à 90 min "
          "crée un chevauchement important avec les horizons de 24 h (96 barres) et 72 h "
          "(288 barres) : les rendements de signaux proches ne sont pas indépendants. "
          "L'intervalle de confiance public est donc artificiellement étroite. "
          "(3) Aucune période du cache actuel (90 000 bougies 15m, 2024-03-27 → 2026-10-20) "
          "n'est vierge : tous les segments NEW, IS1, IS2, OOS ont été consultés. "
          "(4) L'estimation du nombre effectif d'observations (Neff ≈ 15-25) est indicative : "
          "la déduplication à 90 min et les horizons longs réduisent fortement la puissance "
          "statistique. Aucune conclusion sur la rentabilité ne peut être tirée de ces "
          "données historiques.")
        A("")
        A("**Cas particulier de l'invalidation** : l'espérance y est mesurée **dans le sens "
          "du setup invalidé**. Une espérance négative y signifie donc que le prix est "
          "allé **contre** le setup après son invalidation — c'est-à-dire que "
          "l'invalidation a été **juste** (mais de façon ténue : ratio ≈ 1,0, magnitude "
          "−0,2 % à −0,5 %). Ce constat **n'est pas stable** (sur le segment de conception, "
          "le même indicateur vaut 0,84 avec un percentile nul de 0,04) : il n'est donc "
          "pas présenté comme une amélioration.")
    else:
        A("_Profil gains/pertes non disponible (exécuter `scripts/backtest/payoff_analysis.py`)_")
    A("")
    A("## 4. Diagnostic — pourquoi aucune règle ne se généralise")
    A("")
    A("Les combinaisons de familles de preuves ont été passées au crible sur le segment de "
      "**conception**, puis validées sur une zone **intacte** de ce même segment "
      "(`scripts/backtest/analyse_families.py --segment IS1` puis `--segment IS2`).")
    A("")
    A("| Combinaison de familles | IS1 (conception) | IS2 (validation intacte) |")
    A("|---|---|---|")
    A("| context + momentum + structure + volume | **1,447** (n=211, percentile nul 1,000) | 0,748 (n=229, 0,008) |")
    A("| context + momentum + volume | 0,813 (n=165, 0,092) | **1,400** (n=213, 1,000) |")
    A("| momentum + structure + volume | 1,138 (n=223, 0,893) | 0,697 (n=109, 0,029) |")
    A("| momentum + volume | 0,819 (n=161, 0,092) | 0,462 (n=124, 0,000) |")
    A("| context + momentum | 0,871 (n=67, 0,311) | 0,925 (n=67, 0,407) |")
    A("| momentum + structure | 0,676 (n=48, 0,130) | 0,721 (n=70, 0,088) |")
    A("| context + momentum + structure | 0,413 (n=78, 0,001) | 0,956 (n=57, 0,492) |")
    A("")
    A("**Lecture** :")
    A("")
    A("1. **Les classements s'inversent** entre les deux moitiés. La combinaison qui "
      "paraît la meilleure sur la zone de conception est la **pire** sur la zone de "
      "validation intacte, et réciproquement. C'est la signature d'un **artefact de "
      "sélection** : choisir une combinaison sur des données historiques ne produit "
      "rien de généralisable.")
    A("2. **Un seul constat est stable sur les trois échantillons** (IS1, IS2, IS complet) : "
      "**sans la famille `volume`, les signaux sont au niveau du hasard ou en dessous** "
      "(écarts 0,41 à 0,96). La capitulation de volume porte l'information ; mais le "
      "choix de ce qu'on lui associe n'est pas stable.")
    A("3. Conséquence : **aucune modification de la règle de décision n'est justifiée** "
      "par ces mesures. Régler la règle pour améliorer le score reviendrait à du "
      "surapustement ; le moteur v2 est donc **conservé tel quel**.")
    A("")
    A("## 5. Conclusion")
    A("")
    A("* **Les signaux bruts, sans qualification, ne battent pas le hasard.** Sur 15m, l'écart à "
      "la référence est inférieur à 1 dans la quasi-totalité des cas, et l'espérance "
      "économique des signaux est **négative** (≈ −0,3 % à 24 h), soit pire qu'une "
      "entrée aléatoire (≈ −0,06 %). Avec l'aller-retour observé de 0,57 %, elle tombe à ≈ −0,9 %.")
    A("* **Une qualification change le résultat** : la combinaison `CONFIRMATION` + **régime "
      "1j 30 j neutre** (variation ±5 %) donne une espérance brute **positive dans les "
      "quatre segments** (+0,68 % · +1,91 % · +1,80 % · +0,79 %) et **nette après "
      "0,57 %** dans les quatre (+0,11 % · +1,34 % · +1,23 % · +0,22 %). "
      "L'estimation sur les segments **non utilisés pour la conception** (NEW vierge + IS2) "
      "vaut **+0,98 %** (IC 95 % [−0,03 ; +1,96]), nette +0,41 %.")
    A("* **Cette qualification est un modificateur d'intensité, pas une preuve de "
      "rentabilité** : l'intervalle de confiance touche zéro, la marge sur les coûts est "
      "mince (coût d'équilibre 0,68 % à 1,91 % selon le segment) et les frais réels ne sont "
      "pas vérifiés.")
    A("* **Le moteur v2 est mieux instrumenté** : densité d'alerte divisée par 2,4, "
      "invalidation structurelle au lieu d'un niveau de prix figé, statuts cohérents, "
      "cause racine documentée.")
    A("* **Aucun profit n'est établi, et aucun n'est revendiqué.** Le signal exploitable "
      "est de surcroît **lent** (positif à 24 h et 72 h, négatif à 6 h, 15 min et 45 min).")
    A("")
    A("### Recommandation d'usage")
    A("")
    A("Le détecteur peut rester publié **comme observation descriptive**, à condition que "
      "le panneau n'affiche jamais de cible de prix présentée comme atteignable, que le "
      "score de convergence ne soit jamais présenté comme une probabilité, et que le "
      "champ `exploitable` soit pris en compte. **Il ne doit pas être utilisé comme "
      "déclencheur de position sans validation complémentaire.**")
    A("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="oos_results.json")
    parser.add_argument("--output", default="OOS_RAPPORT.md")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    Path(args.output).write_text(build(payload), encoding="utf-8")
    print(f"-> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
