# JALON 1 — MOTEUR DE RETOURNEMENT v2 : CORRECTIONS, TESTS, ÉTAT GIT

> ⚠️ **Ce document est un jalon intermediate. L'évaluation définitive est
> `OOS_RAPPORT.md`** (protocole hors échantillon figé, séparation 60 % conception /
> 40 % validation, coûts appliqués une seule fois).
>
> Les chiffres de ce document ont été mesurés avec un **protocole antérieur** (v1.0/v1.1 du
> harnais), dont deux défauts ont été corrigés depuis : un seuil de significativité qui n'était
> pas spécifique à la direction, et un coût de transaction appliqué deux fois. Ils restent
> valides comme **mesures du comportement des signaux** (densité, couverture des
> retournements), mais **les taux de réussite et écarts à la référence doivent être lus dans
> `OOS_RAPPORT.md`**.
>
> **Conclusion d'ensemble, issue de l'évaluation hors échantillon : aucun des deux moteurs
> ne démontre de pouvoir prédictif.** Le moteur v2 est mieux instrumenté (densité d'alerte
> divisée par 2,4, invalidation structurelle, statuts cohérents) mais **pas plus juste**.


**Date** : 21 octobre 2026
**Périmètre** : Phase 1 (sauvegarde) + Phase 2 (moteur) + Phase 3 (tests). **Pas d'évaluation hors échantillon à ce jalon** (voir §7).
**Détecteur livré** : `src/agent_analysis.py` — SHA-256 `1dc21c0e475058269f252908a17fb92e2a7e46e624b8bcac0755be44b97ddd4a`
**Mode** : lecture seule. Aucun ordre, aucun trade, aucun workflow modifié, aucun déploiement, aucune opération Git.

---

## 1. SAUVEGARDE (PHASE 1) — VÉRIFIÉE EXPLOITABLE

`C:\Users\sabri\AppData\Local\Temp\opencode\backup-mission-20261021-022330\`

| Contrôle | Résultat |
|---|---|
| Fichiers copiés (worktree complet, hors `.git`/`__pycache__`) | **77** |
| Fichiers manquants dans la copie | **0** |
| Fichiers altérés dans la copie | **0** (empreinte SHA-256 comparée fichier à fichier) |
| `repo.bundle` clonable + `worktree.patch` applicable sur HEAD | **True** |
| Commit présent dans le bundle | `1b4fdd1 P0 provenance fix and audit bundle` |
| Fichiers de résultats lisibles + empreinte du détecteur conservée | **11 / 11** |
| Code de production vivant identique à la sauvegarde | **True** (`81811320…` au moment de la sauvegarde) |

---

## 2. DÉFAUTS CORRIGÉS — PREUVE POUR CHACUN

### D1 — `CONFIRMATION` n'existait pas → **corrigé**
*Cause racine* : le détecteur était une fonction **pure de l'état courant, sans mémoire** → il lui était structurellement impossible de distinguer « précoce » de « confirmée ».
*Correction* : le moteur reconstruit depuis la queue 15m qu'il reçoit déjà **le setup le plus récent** (barre `e`) et son état à la barre courante. La fonction reste **pure, déterministe, causale et rejouable** — aucun état n'est porté entre les appels.
*Preuve* : `tests/test_reversal_engine.py::TestStatusTransitions` (alerte → confirmation → invalidation, expiration du setup, precedence de l'invalidation) + mesure réelle (§5).

### D2 — 5 fonctions mortes → **corrigées**
`has_hammer_pattern`, `has_engulfing_bullish`, `has_level_rejection`, `is_momentum_improving`, `is_macd_improving` : définies, jamais appelées, **absentes des tests**.
*Cause racine* : `analyze_timeframe()` ne retournait pas l'OHLC → les figures de bougies étaient **inaccessibles**, pas seulement inutilisées.
*Correction* : `build_analysis()` transmet maintenant l'OHLC 15m **aligné sur les mêmes index** que `price_series_15m` ; les figures sont évaluées **à l'extrémité du setup**.
*Preuve* : `TestCandleFigures` (3 tests) + mesure réelle (§5).

### D3 — `1h`/`1w`/`1M` inutilisés → **corrigés**
*Preuve* : `tf_1h` passe de 1 occurrence (simple chargement) à un usage réel (famille de **confirmation** : retournement intermédiaire) ; `1w` et `1M` alimentent la famille **contexte** (RSI weekly extreme → *survendu*) et les **contradictions** (tendance weekly opposée).
*Nuance documentée* : le `1M` n'est exploitable qu'avec assez d'historique ; sur le snapshot MEXC (23 bougies) il est `PARTIEL` et son EMA50 est indisponible → il est **déclaré non exploitable** plutôt que forcé.

### D4 — `CRITICAL_LEVEL = 0.001526` → **sorti du chemin de décision**
*Constat* : valeur à 1·10⁻⁶ du meilleur ask du snapshot (prix de carnet figé), qui forçait `INVALIDATION` sur 3,2 % des bougies avec **confiance 90 et zéro preuve** — et dont le signal s'avérait **contre-productif** (le prix monte dans 69 % des cas à 72 h, médiane +6,2 %).
*Correction* : le moteur **ne lit plus** `CRITICAL_LEVEL` (vérifié par `inspect.getsource` dans les tests). L'invalidation repose désormais sur **l'ancre structurelle du setup** (l'extrémité qui l'a créé, ± tolérance ATR). La constante subsiste **uniquement** comme observation de risque informative dans `risk_checks`, avec sa mention explicite « jamais un signal d'achat ».
*Preuve* : `TestCriticalLevelIndependence` (3 tests, dont l'égalité stricte de la décision pour 5 valeurs de la constante) + `test_invalidation_below_critical_level` réécrit dans `tests/test_agent_analysis.py`.

### D8 — Direction par 3 clôtures consécutives → **corrigée**
La direction vient désormais de **l'extrémité structurelle** qui ancre le setup. Conséquence mesurable : les épisodes `INDETERMINE` passent de **767 à 0** (§5), et une hausse régulière n'est plus jamais considérée comme un retournement (nouveau test dédié).

### D9 — Preuves de continuation comptées comme preuves de retournement → **corrigées**
`higher_timeframe_alignment` (tendance 4h/1d dans le sens du mouvement) **n'est plus une preuve** : c'est une **observation** (`observations`), jamais comptée dans une famille. L'alerte exige désormais le setup (momentum) **+ au moins une famille indépendante** parmi `structure`, `volume`, `context`.

### D10 — `confidence` = formule de comptage → **redéfinie**
`confidence` = score de **convergence** (20 + 15 × familles indépendantes + 15 si confirmée − 10 × contradiction). Le champ `confidence_note` précise explicitement : *« score de convergence des familles de preuves (0-100) ; ce n'est pas une probabilité et n'a pas été calibré »*.

### D11 — Densité d'alerte de 12,4 % → **2,80 %** (mesuré, §5)

### D12 — Angle mort sur les coûts → **traité au jalon suivant** (§7)

### D5/D6 — Divergences, causalité, bougies clôturées → **confirmés corrigés, préservés**
Les correctifs de l'agent précédent (`_align_divergence_series`, `_divergence_windows`, `_extreme_with_rsi`) sont **conservés à l'identique** et **réutilisés** par le moteur v2. `candle_close_time()`, `is_candle_closed()`, `usable_rows()` (rejet des doublons, NaN, prix ≤ 0) sont inchangés.

### Point 7 — Cibles de prix : il n'en existait aucune
*Constat* : aucune logique de cible dans le code de production. *Correction* : `objectives` est ajouté — `short_term` (niveau opposé le plus proche) et `swing` (niveau majeur), **distances normalisées en ATR**, avec la mention *« une localisation, pas une prediction »*. **Ces objectifs n'entrent pas dans la décision** (aucun test ne les lie au statut).

### Défaut supplémentaire découvert et corrigé pendant la mission
**Bruit flottant lu comme un retournement.** Sur une série linéaire, le MACD converge vers zéro (~1e-21 sur un prix de 0,0017) et ses variations sont du bruit numérique : le moteur y lisait un « retournement » et déclenchait une alerte sur une simple tendance baissière. Correction : un retournement doit être **matériel** — amplitude ≥ `min_turn_atr` × ATR (5 %) et hausse de RSI ≥ 2 points (`REVERSAL_PARAMS`). Ce n'est pas un réglage de seuil pour satisfaire un test : c'est une condition de validité physique.

---

## 3. ARCHITECTURE DU MOTEUR v2

```
signal_status = ALERTE_PRÉCOCE   setup vivant + ≥1 famille indépendante, non confirmé
                CONFIRMATION      setup vivant + preuve de démarrage (structure / momentum / 1h)
                INVALIDATION      ancre structurelle du setup rompue (prioritaire)
                ATTENDRE          pas de setup / setup ambigu / données insuffisantes
                DONNÉES_INSUFFISANTES
```

* **Setup** : extrême structurel (la barre est l'extrême de sa fenêtre) **+** retournement de momentum matériel sur cette barre.
* **Ancre** : l'extrémité qui a créé le setup → sert d'invalidation (structurelle, valable à tout niveau de prix).
* **Familles de preuves** : `structure` (divergence, marteau, engulfing, rejet de niveau), `momentum` (MACD, momentum, RSI — **une seule famille, corrélés**), `volume` (climax à l'extrême), `context` (RSI 4h/1h/1d/1w étiré, ADX 4h faible, retournement 1h).
* **Horizons de recherche** : extrême sur 20 barres, fenêtre de setup 16 barres, tolérance d'invalidation 0,25 ATR.
* **Déterminisme** : fonction pure ; mêmes entrées → même sortie (testé).

---

## 4. FICHIERS MODIFIÉS ET MOTIFS

| Fichier | SHA-256 (16) | Nature |
|---|---|---|
| `src/agent_analysis.py` | `1dc21c0e47505826` | **Moteur v2** (1 368 lignes) : bloc `EARLY REVERSAL ENGINE (v2)`, `REVERSAL_PARAMS`, 8 helpers, `detect_early_reversal` réécrite, `build_analysis` transmet l'OHLC 15m. Les correctifs de divergence de l'agent précédent sont **préservés** |
| `tests/test_reversal_engine.py` | `29cf1e292157cd1e` | **Nouveau** — 27 tests unitaires du moteur |
| `tests/test_agent_analysis.py` | `b7a2d6795fc720fe` | 2 tests **adaptés** (comportement effectivement remplacé) + 1 test d'indépendance au niveau |
| `scripts/backtest/harness.py` | `35ffffe2768bf8f4` | L'OHLC transmis au détecteur + `call_detector(..., detector=)` pour rejouer un moteur antérieur |
| `scripts/backtest/engine.py` | `06a529659c3af7ff` | Enregistrement des `families`/`setup` + paramètre `detector` pour le A/B |
| `scripts/backtest/make_journal.py` | `6e6f7bce4b12264a` | **Réparation d'encodage uniquement** (voir §6) |

**Non touchés, vérifiés par empreinte :** `site/index.html`, `site/realtime.js`, `.github/workflows/monitor.yml`, `tests/test_dashboard.js`, `collector/tel_collector.py`, `src/monitor.py`, `src/tradingview_quality.py`, ainsi que **les 8 fichiers `_probe_*.py` de l'agent précédent** et son nouveau dossier `_reconstructions/`.

---

## 5. MESURES RÉELLES (15m, 45 000 bougies, 2025-07-09 → 2026-10-20)

Diagnostic A/B, **même données, même harnais**, ancien moteur chargé depuis la sauvegarde vérifiée.

| | Ancien moteur | **Moteur v2** |
|---|---|---|
| `ATTENDRE` | 33 310 | 32 688 |
| `ALERTE_PRÉCOCE` | 10 190 | **4 744** |
| `CONFIRMATION` | *inexistant* | **5 240** |
| `INVALIDATION` | 1 446 | 2 274 |
| `DONNÉES_INSUFFISANTES` | 54 | 54 |
| **Épisodes dédupliqués** | 5 565 | **1 259** |
| **Densité d'alerte** | **12,37 %/bougie** | **2,80 %/bougie** (÷ 4,4) |
| Directions | HAUSSIER 2 139 · BAISSIER 2 659 · **INDETERMINE 767** | HAUSSIER 708 · BAISSIER 551 · **INDETERMINE 0** |

**Matrice de transition sur 3 144 positions communes** (31,1 % de statuts identiques) :

| ancien → v2 | nb |
|---|---|
| `ALERTE_PRÉCOCE` → `CONFIRMATION` | 1 212 |
| `ALERTE_PRÉCOCE` → `ALERTE_PRÉCOCE` | 941 |
| `ALERTE_PRÉCOCE` → `INVALIDATION` | 731 |
| `INVALIDATION` → `ALERTE_PRÉCOCE` | 132 |
| `INVALIDATION` → `CONFIRMATION` | 92 |
| `INVALIDATION` → `INVALIDATION` | 36 |

**Chemin de production** (snapshot MEXC réel) : le détecteur renvoie désormais `ATTENDRE` — « Aucun setup de retournement structurel detecte » — au lieu de l'ancien `INVALIDATION` à confiance 90 **sans la moindre preuve**. `risk_checks` conserve le niveau critique comme observation de risque, avec sa mention « jamais un signal d'achat ».

> ⚠️ **Ces chiffres sont un contrôle de santé du moteur, pas un verdict de performance.** Ils ne disent rien du taux de réussite, des faux positifs ni des retournements manqués : l'évaluation hors échantillon est l'étape suivante (§7).

---

## 6. INCIDENT D'ENCODAGE (transparence)

Trois de mes fichiers (`scripts/backtest/harness.py`, `scripts/backtest/make_journal.py`, `CONFLIT_GIT.md`, les journaux et les JSON de résultats) avaient subi un **double encodage UTF‑8 → cp1252 → UTF‑8** lors d'éditions effectuées via PowerShell. Détecté par signature (prefixe de double encodage devant une lettre accentuee), **réparé** par substitution chirurgicale (uniquement les séquences UTF‑8 invalides), puis vérifié : **0 signature résiduelle** dans tout le dépôt, et **les 166 tests repassent**. Les contenus numériques des résultats n'ont jamais été altérés (seules des chaînes françaises d'affichage l'étaient) ; les fichiers ont été réécrits à l'identique côté données.

---

## 7. TESTS EXÉCUTÉS — RÉSULTATS EXACTS

```
python -m pytest tests/ collector/ -q              166 passed, 3 skipped, 13 subtests passed
python -m unittest discover -s tests                Ran 155 tests - OK (skipped=3)      [commande CI]
python -m unittest discover -s collector -p "test_*.py"   Ran 14 tests - OK
node tests/test_dashboard.js                       Dashboard freshness tests: OK
node tests/test_realtime.js                        Real-time stream protocol/fail-closed tests: OK
python -m pytest tests/test_reversal_engine.py -q   27 passed
```

Avant mission : **139 passés / 3 ignorés / 13 subtests**. Après : **166 / 3 / 13** → **+27 tests**, **0 régression**.

### Couverture demandée, test par test

| Exigence | Test | État |
|---|---|---|
| Transitions entre statuts | `test_alert_then_confirmation`, `test_invalidation_when_the_anchor_is_broken`, `test_invalidation_takes_precedence_over_confirmation`, `test_setup_expires_and_status_returns_to_attendre` | ✅ 4 |
| Indépendance au niveau fixe | `test_decision_is_independent_from_critical_level` (5 valeurs), `test_critical_level_is_not_read_by_the_detector` (inspection du source), `test_invalidation_below_critical_level` (réécrit) | ✅ 3 |
| Absence de fuite temporelle | `test_future_bars_do_not_change_the_decision`, `test_decision_only_uses_bars_up_to_the_current_one`, + R1 du harnais (perturbation future sur l'état, la détection **et** le seuil quantile) | ✅ 3 |
| Bougies clôturées / données incomplètes | `test_missing_15m_gives_insufficient_data`, `test_short_history_gives_insufficient_data`, `test_empty_series_does_not_raise`, `test_nan_values_are_tolerated`, `test_misaligned_series_are_reported`, `test_figures_are_absent_when_ohlc_is_unavailable` + `test_closed_candles_only` (existant) | ✅ 6 |
| Figures de bougies | `test_hammer_pattern_is_detected_and_reported`, `test_bullish_engulfing_is_reported`, + `test_figures_are_absent_when_ohlc_is_unavailable` | ✅ 3 |
| Cas limites / contradictions | `test_contradiction_with_opposite_higher_timeframe_trend`, `test_trend_alignment_is_an_observation_not_evidence`, `test_setup_without_independent_family_is_attendre`, `test_steady_rise_is_not_a_reversal_setup`, `test_direction_comes_from_the_extreme_not_from_three_candles` | ✅ 5 |
| Reproductibilité | `test_reproducibility`, `test_parameters_are_exposed_and_frozen`, `test_every_evidence_has_a_known_family`, `test_confidence_is_labelled_as_not_a_probability`, `test_objectives_are_informative_only` | ✅ 5 |

**2 tests préexistants adaptés** (justifié : leur comportement attendu est *effectivement* remplacé) :
* `test_invalidation_below_critical_level` → `test_decision_does_not_depend_on_critical_level` : le prix sous 0,001526 **ne force plus** `INVALIDATION`, et la décision est vérifiée **identique** pour 5 valeurs de la constante.
* `test_confirmed_bullish_reversal_multiple_categories` → `test_steady_rise_is_not_a_reversal_setup` : une hausse régulière **n'est pas** un retournement ; l'ancien test encodait « 3 clôtures ascendantes + volume = preuve », qui n'est plus une preuve de retournement.

---

## 8. ÉTAT GIT FINAL

| Élément | État |
|---|---|
| Branche | `wip/p0-provenance`, **inchangée**, 6 commits derrière `origin`, 0 devant |
| Opérations Git | **aucune** (ni commit, push, merge, reset, rebase, checkout, stash) |
| Dépôts modifiés | `src/agent_analysis.py` (moteur v2), `tests/test_agent_analysis.py` (2 tests adaptés), `scripts/backtest/harness.py`, `scripts/backtest/engine.py`, `scripts/backtest/make_journal.py` (encodage) |
| Dépôts **créés** | `tests/test_reversal_engine.py` |
| Modifications **préexistantes** (agent précédent) | `.github/workflows/monitor.yml`, `site/index.html`, `site/realtime.js`, `tests/test_dashboard.js` → **intacts, vérifiés par empreinte** |
| Fichiers non suivis de l'agent précédent (`_probe_*.py`, `_reconstructions/`) | **intacts, non supprimés** |
| Workflows GitHub / dashboard / déploiement | **non touchés** (`site/agent_analysis.json` publié non régénéré) |

---

## 9. PROCHAINE ÉTAPE RECOMMANDÉE

**Évaluation hors échantillon chronologique, protocole figé avant lecture des résultats.**

1. **Figer le protocole** dans `scripts/backtest/harness.py` : critères de significativité, horizons, coûts, définition des retournements de référence — **avant** de regarder l'OOS.
2. **Séparer** : conception sur les **60 %** les plus anciens (≈ 9 mois), validation sur les **40 %** les plus récents (≈ 6 mois).
3. **Comparer ancien / nouveau moteur** avec la même méthodologie : taux de réussite **par statut**, base de taux, faux positifs, retournements manqués, délai d'avance, densité.
4. **Coûts** : slippage observé (0,285 % MEXC / 0,185 % KuCoin) + scénarios de frais (non vérifiés) — vérifier que la base de comparaison et le traitement des coûts **ne comptent pas deux fois** le même coût. Rappel établi : au seuil de 0,57 % aller-retour, l'avantage 15m de l'ancien moteur tombait à 32,52 % contre une base de 31,68 %, et sous la base à 0,87 %.
5. **Publier séparément** conception et hors échantillon, et **dire clairement** si l'avantage disparaît après coûts ou ne se généralise pas d'une unité de temps à l'autre.

**Je n'engage rien de tout cela sans votre feu vert** : la prochaine étape modifie le harnais de métriques (frais, statuts, séparation IS/OOS), ce qui reste dans mes fichiers, mais elle est distincte du livrable de ce jalon.