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
| T49 | **Suivi d'alertes persistant** : déduplication (identité = symbole + direction + ancre), résolution exigeant des données exploitables (une panne de flux ne résout **jamais**), persistance atomique, reprise après redémarrage, historique borné | 36 tests dédiés + 40 contrôles opérationnels ; bloc CI fail-soft (`continue-on-error`) | `src/alert_state.py`, `tests/test_alert_state.py`, `scripts/verify_states.py` |
| T50 | **Journal prospectif** : une ligne par exécution, append-only, pour distinguer un résultat **historique** (backtest) d'un résultat **prospectif** (mesuré en avant) | aucun résultat prospectif n'existe encore : le journal démarre, la mesure exigera de la donnée future ; rien n'est estimé | `src/alert_state.py` (`--ledger`), `alerts/prospective.jsonl` |
| T51 | **Contrôle opérationnel des 4 états** (ALERTE PRÉCOCE / CONFIRMATION / INVALIDATION / ATTENDRE) de bout en bout : moteur → rapport → état d'alerte → contrat du tableau de bord | 40/40 contrôles ; branché en CI (`p0-validation.yml`) | `scripts/verify_states.py` |
| T52 | **Couverture du tableau de bord complétée** : l'état `INVALIDATION` n'était pas testé | test ajouté (badge jamais vert, raison affichée, pas d'ancre affichée) | `tests/test_dashboard.js` |
| T53 | **Chaîne de collecte vérifiée en local** : le collecteur fonctionne (KuCoin vérifié, MEXC non joignable en local → fail-closed, aucune donnée inventée) ; le moteur n'utilise que la source MEXC comme série de référence (choix fail-closed assumé) ; l'artefact **réellement publié** par la CI montre les 6 unités de temps `OK` (15m : âge 288 s) | diagnostic sur données réelles, aucune régression | `EXPLOITATION.md` §6 |
| T54 | **Durcissement des contrôles pour le runner CI** : deux échecs réels de la CI diagnostiqués et corrigés (checkout **HEAD détaché** ; `pytest` **absent** du runner, projet stdlib-only). La CI est repassée au vert | échec CI reproduit localement (venv sans pytest), correction validée dans une simulation fidèle du runner | `scripts/verify_project.py`, `.github/workflows/p0-validation.yml` |
| T55 | **Vérification de bout en bout sur données de marché réelles** : collecte locale → moteur → rapport (`regime` NEUTRE −2,11 %, `exploitable` false) → état d'alerte ; les 4 états et le comportement fail-closed sont couverts par un contrôle reproductible | 40/40 contrôles ; aucun artefact du dépôt régénéré | `scripts/verify_states.py`, `EXPLOITATION.md` |
| T56 | **Défaut de production corrigé** : la porte de provenance exigeait un marqueur `collection_status` que le collecteur n'écrivait pas → **publication impossible** depuis la fusion. La porte est extraite dans `src/publication_gate.py` (partagée par le workflow et les tests), le collecteur écrit le marqueur (`VALID` si et seulement si l'empreinte est calculable), l'instantané de repli est marqué `FALLBACK`, et un test vérifie la **compatibilité réelle** collecteur ↔ porte | échec de production reproduit et corrigé ; 16 tests de porte ; un test existant qui passait **à vide** (copie du script, échec sur l'import) a été réparé | `src/publication_gate.py`, `collector/tel_collector.py`, `tests/test_publication_gate.py`, `tests/test_provenance.py` |
| T57 | **Mise en production** : PR #31 puis #32 fusionnées (commits de fusion traçables), run `monitor.yml` **vert sur les 18 étapes** (collecte → analyse → alertes → porte de provenance → commit des artefacts → **déploiement GitHub Pages**) | artefact publié avec `early_reversal` + `regime` + `exploitable`, 6 unités de temps `OK` (15m ≈ 4 min), même `collection_id` sur les 3 artefacts, journal prospectif marqué `live` | `EXPLOITATION.md` §9 |
| T58 | **Conciliation d'une modification concurrente** : une autre session a étendu la ligne du journal prospectif (champs du protocole Phase 10 §2E) dans le même worktree. Travail **conservé** ; réconciliation additive (champs de fraîcheur restaurés, `at` publié avec `time_ms`, `fees_note` explicite, CLI étiquetée `live` et non `historical`) | 39 tests du module ; la distinction historique/prospectif n'est plus corrompue | `src/alert_state.py`, `tests/test_alert_state.py` |
| T59 | **Cadence de publication corrigée** : la cadence **observée** était de **229 min** pour un cron `*/15` (45 exécutions sur 168 h, retard de l'ordonnanceur plateforme) → le tableau de bord publié reposait sur des données de 27 à 290 min, donc en ATTENDRE « périmé » presque en permanence. Auto-relance **auto-limitée** (12 min) ajoutée, avec reprise à 45 min après un échec | cadence cible 12-15 min ; 20 tests ciblés ; le module ne peut jamais faire échouer une publication (3 tests de robustesse) | `src/publication_cadence.py`, `tests/test_publication_cadence.py`, `.github/workflows/monitor.yml` |
| T60 | **Fail-closed des alertes** : un rapport dégradé portant encore un signal résiduel pouvait ouvrir (ou modifier) une alerte sur des données inexploitables. `advance()` ignore désormais tout signal si les données ne sont pas exploitables | 3 tests de régression ; 260 tests au total | `src/alert_state.py`, `tests/test_alert_state.py` |
| T61 | **Défaut de la première exécution de l'étape de cadence** : `GITHUB_WORKFLOW` contient le *nom d'affichage* du workflow et non son nom de fichier → URL de déclenchement invalide ; l'exception n'était pas attrapée et faisait rougir le run | corrigé (nom de fichier, capture large, filet de sécurité global) ; dispatch réel vérifié de bout en bout (run `39676509123`, 19 étapes vertes) | `src/publication_cadence.py`, `tests/test_publication_cadence.py` |
| T62 | **Boucle de publications (~50 s) due au checkout de profondeur 1** : l'historique des publications était indisponible, l'âge restait inconnu et le module relançait à chaque exécution. L'âge est désormais lu dans l'artefact publié au commit de checkout, et un âge inconnu ne déclenche plus rien | 22 tests de cadence ; la boucle est arrêtée | `src/publication_cadence.py`, `tests/test_publication_cadence.py`, `.github/workflows/monitor.yml` |

## À FAIRE (décisions ou travaux restants)

| # | Tâche | Justification / condition |
|---|---|---|
| T36 | **Statuer sur l'usage opérationnel** : l'avantage mesuré est mince (IC qui touche 0, marge de 0,11 à 1,23 point sur les coûts) ; publier comme « observation qualifiée » (recommandé) ou neutraliser | **Appliqué dans le produit** (mode observation, réserve explicite, `exploitable` très conservateur) ; **décision résiduelle du mainteneur** : conserver le panneau publié ou le neutraliser — voir `EXPLOITATION.md` §9 |
| T38 | Intégrer BTC / ETH / TEL-BTC au contexte du détecteur | **écarté sur preuve** (aucune valeur prédictive démontrée) — à ne faire que si de nouvelles données changent la donne ; **écart acté et documenté** au regard de la checklist obligatoire (`RECHERCHE_QUALITE_ENTREES.md` §11) |
| T39 | Collecte P2 (historique 1h/4h/1d supplémentaires) | non nécessaire : la contrainte mesurée est le **15m**, pas la profondeur des autres unités |
| T40 | Réconciliation Git et mise en production | **TERMINÉ** : PR #31 et #32 fusionnées, publication et déploiement vérifiés — voir `EXPLOITATION.md` §9 et `CONFLIT_GIT.md` §9 |
| T41 | Publication / déploiement du dashboard | **TERMINÉ** : le cron */15 collecte, analyse, commite les artefacts et déploie GitHub Pages ; l'artefact publié contient `early_reversal`, `regime` et `exploitable` |

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
