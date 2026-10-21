# LISTE DE TÂCHES — TELCOIN TRADING INTELLIGENCE

Mise à jour : 21 octobre 2026 (réconciliation Git locale exécutée — opération T40/1 ; étapes 2 à 5 non autorisées). États : **TERMINÉ** · **EN COURS** · **À FAIRE** · **BLOQUÉ** · **ÉCARTÉ**.

---

## TERMINÉ

| # | Tâche | Preuve | Fichiers |
|---|---|---|---|
| T01 | Sauvegarde intégrale + vérification d'exploitabilité | 77 fichiers, 0 manquant/altéré, bundle clonable | `%TEMP%\opencode\backup-mission-20261021-022330` |
| T02 | Audit du dépôt et des 7 points de la mission | causes racines + mesures | `DETECTEUR_V2_RAPPORT.md` |
| T03 | Moteur de retournement v2 (setup / confirmation / invalidation) | 27 tests unitaires | `src/agent_analysis.py` |
| T04 | `CRITICAL_LEVEL` hors du chemin de décision | 3 tests d'indépendance | `src/agent_analysis.py` |
| T05 | Figures de bougies branchées (OHLC aligné) | 3 tests | `src/agent_analysis.py` |
| T06 | Usage réel de 1h / 1w / 1M ; 1M non exploitable si historique court | inspection | `src/agent_analysis.py` |
| T07 | `confidence` = score de convergence, non calibré | `confidence_note` + test | `src/agent_analysis.py` |
| T08 | Objectifs structurels court terme / swing, normalisés en ATR, hors décision | 2 tests | `src/agent_analysis.py` |
| T09 | Bruit flottant (MACD ≈ 0) plus lu comme un retournement | seuil de materialité | `src/agent_analysis.py` |
| T10 | Protocole hors échantillon figé (v1.0 → v1.2) | `OOS_PROTOCOL.md` | `OOS_PROTOCOL.md`, `scripts/backtest/protocol.py` |
| T11 | Seuil de significativité rendu directionnel | symétrie de mesure | `scripts/backtest/harness.py` |
| T12 | Coût appliqué **une seule fois** (seuil = marché, coût = trade) | règle de non-double-compte | `scripts/backtest/evaluation.py` |
| T13 | Causalité vérifiée sur données réelles | 468 positions, 0 divergence | `scripts/backtest/check_causality.py` |
| T14 | Panneau « détection de retournement » intégré au dashboard | 3 scénarios de test | `site/index.html` |
| T15 | Tests d'intégration du panneau | `node tests/test_dashboard.js` | `tests/test_dashboard.js` |
| T16 | Vérification bout en bout : affichage = calcul | contrôle de concordance | script e2e (hors dépôt) |
| T17 | Faisabilité BTC / ETH / TEL-BTC / liquidité | sonde en direct | README §6 |
| T18 | Chaîne de collecte vérifiée (fail-closed sans MEXC) | exécution réelle | — |
| T19 | Documentation d'exécution et de maintenance | README réécrit | `README.md` |
| T20 | Audit des workflows Git + recommandation | permissions, déclencheurs | `CONFLIT_GIT.md` §3 |
| T21 | **Évaluation hors échantillon** (protocole v1.2) : ancien vs v2, IS 60 % / OOS 40 %, brut et net | `oos_results.json`, `OOS_RAPPORT.md` | `scripts/backtest/run_oos.py` |
| T22 | Diagnostic de la non-généralisabilité (IS1 vs IS2, isolés) | les classements s'inversent | `scripts/backtest/analyse_families.py` |
| T23 | Rapport OOS publié | IS/OOS, brut/net, limites | `OOS_RAPPORT.md` |
| T24 | Journal d'apprentissage complété par l'OOS | conclusion négative + enseignements | `JOURNAL_APPRENTISSAGE_FINAL.md` |
| T25 | Vérification complète du projet (36 contrôles) | 36/36 réussis | `scripts/verify_project.py` |
| T26 | Résultats volumineux archivés **hors dépôt**, empreintes vérifiées | 5 fichiers déplacés, 0 suppression | `%LOCALAPPDATA%\telcoin\history\oos_archive` |
| T28 | **Recherche sur la qualite economique des entrees** (esperance, reference aleatoire, regime, continuation, entree tardive, contexte BTC/ETH/TEL-BTC) | causes confirmees, hypotheses rejetees | `RECHERCHE_QUALITE_ENTREES.md` |
| T29 | **Periode vierge collectee** : historique 15m prolonge de 45 000 a 90 000 bougies (2024-03-27), 30 requetes | NEW = 471 jours jamais consultes | `scripts/backtest/fetch_history.py` |
| T30 | **Contexte BTC / ETH / TEL-BTC** collecte et aligne (22 499 bougies 1h chacun) | provenance, alignement et disponibilite au moment du signal verifies | cache local |
| T31 | **Regle retenue (regle de recherche, non une strategie rentable)** : `CONFIRMATION` + regime 1j 30 j neutre (+5 % / +1,91 % / +1,80 % / +0,79 % sur NEW/IS1/IS2/OOS) | reproduite par le moteur corrige a 0,0003 point pres | `oos_correction_validation.json` |
| T32 | **Correction implementee** dans le moteur : champs `regime` et `exploitable` (+ `exploitable_reason`) | 5 tests dedies + non-regression | `src/agent_analysis.py` |
| T33 | **Index trompeur retire** : `setup.index` etait un index relatif a la fenetre analysee -> publie uniquement `age_bars` | une analyse anterieure etait invalide, elle a ete jetee et refaite | `src/agent_analysis.py` |
| T34 | **Frontieres du backtest figees sur des DATES ABSOLUES** (plus de coupure en pourcentage) | l'allongement de l'historique deplacait silencieusement le segment publie | `scripts/backtest/run_oos.py` |
| T35 | **Regle de cout corrigee** : le cout s'applique une seule fois (seuil = marche, cout = trade) | double compte corrige (protocole v1.2) | `OOS_PROTOCOL.md` |
| T27 | Bandeaux de renvoi ajoutés aux rapports intermédiaires (éviter les contradictions) | 2 fichiers | `BACKTEST_HISTORIQUE_TEL.md`, `DETECTEUR_V2_RAPPORT.md` |

| T37 | **Dashboard integre (T37)** : le panneau affiche le regime de marche, l'etat d'exploitabilite et sa raison ; une ALERTE_PRÉCOCE n'est plus presentee comme une entree ; badge vert reserve aux signaux reellement exploitables ; repli propre si les champs sont absents | 8 assertions JS + controle de bout en bout (`scripts/verify_t37_e2e.py`) | `site/index.html`, `tests/test_dashboard.js` |
| T48 | **Réconciliation Git locale EXÉCUTÉE (opération T40/1)** : `monitor.yml` aligné sur `origin/wip/p0-provenance`, puis fast-forward strict | HEAD `1b4fdd1` → `ee77552` ; **0 commit de fusion** ; branche à 0 ahead / 0 behind ; 109 fichiers de sauvegarde vérifiés 0 divergence ; suite complète verte (182 tests, 36/36, 20/20) | `CONFLIT_GIT.md` §9 |

## À FAIRE (décisions ou travaux restants)

| # | Tâche | Justification / condition |
|---|---|---|
| T36 | **Statuer sur l'usage opérationnel** : l'avantage mesuré est mince (IC qui touche 0, marge de 0,11 à 1,23 point sur les coûts) ; publier comme « observation qualifiée » (recommandé) ou neutraliser | décision du mainteneur |
| T38 | Intégrer BTC / ETH / TEL-BTC au contexte du détecteur | **écarté sur preuve** (aucune valeur prédictive démontrée) — à ne faire que si de nouvelles données changent la donne |
| T39 | Collecte P2 (historique 1h/4h/1d supplémentaires) | non nécessaire : la contrainte mesurée est le **15m**, pas la profondeur des autres unités |
| T40 | Réconciliation Git — **étape 1 (local) exécutée** ; étapes 2 à 5 (commit, push, fusion `main`, publication) | **autorisation requise pour les étapes 2 à 5** — voir `CONFLIT_GIT.md` §9 |
| T41 | Publication / déploiement du dashboard | **autorisation requise** ; la CI régénère `site/agent_analysis.json` |

## BLOQUÉ

| # | Tâche | Blocage | Sortie possible |
|---|---|---|---|
| T41 | Collecte MEXC en local | `api.mexc.com` ne résout pas (DNS) depuis ce poste | la CI a un DNS normal ; en local l'analyse reste fail-closed |
| T42 | Opérations Git 2 à 5 (commit / push / merge `main` / publication) | autorité non accordée | dépôt réconcilié et sûr (HEAD `ee77552`, 0 ahead / 0 behind), sauvegardes vérifiées, répétition à blanc de l'étape 2 validée en bac à sable |
| T43 | Déploiement / publication | autorité non accordée | aucun artefact publié |

## ÉCARTÉ (décidé et documenté)

| # | Sujet | Décision |
|---|---|---|
| T44 | **Réglages de la règle de décision du détecteur** | **écarté sur preuve** : la meilleure combinaison sur la zone de conception tombe à 0,748 sur la zone de validation intacte, tandis qu'une autre y monte à 1,400. Aucun réglage ne se généralise → le moteur est conservé tel quel, et le résultat négatif est publié tel quel |
| T45 | Correction de `src/monitor.py`, `src/tradingview_quality.py`, `collector/tel_collector.py` | aucun défaut mesuré ; hors périmètre |
| T46 | Suppression des `_probe_*.py` / `_reconstructions/` de l'agent précédent | appartiennent à un autre travail ; préservés (laissés non suivis et non commités) ; leurs 25 points de contrôle Git sont en outre protégés de l'élagage par `refs/backup/cline-checkpoints/` |
| T47 | Suppression des résultats volumineux | **archivés hors dépôt avec empreinte vérifiée**, jamais supprimés |
