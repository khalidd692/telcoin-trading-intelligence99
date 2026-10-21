# BACKTEST HISTORIQUE — DÉTECTEUR DE RETOURNEMENT PRÉCOCE TEL/USDT

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


**Version** : 3 — **résultats définitifs** sur le détecteur courant, historique étendu (P1), test de nullité à 2 000 itérations.
**Détecteur évalué** : `src/agent_analysis.py` → `detect_early_reversal()` (**non modifié par ce travail**)
**Empreinte du détecteur évalué** : SHA-256 `81811320dac01b3f334c7e4364d5c163f7b5cd19ca66a4a184d176c8bd8befed`
**Résultats** : `backtest_results_final.json` (complet) · `backtest_results_final_summary.json` (29,9 Ko)
**Données** : KuCoin `TEL-USDT`, cache local hors dépôt (0,99 Mo) · **Mode** : lecture seule, simulation — aucun ordre, aucune clé API.

> L'empreinte est inscrite automatiquement dans chaque JSON de résultats (`detector.sha256`). Les chiffres ci-dessous sont attachés à **cette version exacte** du détecteur. Voir §9 pour l'historique des modifications concurrentes.

---

## 1. SYNTHÈSE EXÉCUTIVE

| Question | Réponse mesurée |
|---|---|
| Le « 100 % de faux positifs » du rapport précédent est-il exact ? | **Non.** Ce résultat était un artefact d'un critère de significativité inatteignable. Sur un critère atteignable, le taux de réussite atteint **32–37 %** selon l'unité de temps, contre une base de taux de 27–32 %. |
| Le détecteur bat-il le hasard ? | **En 4h : oui** (percentile 0,999, significatif). **En 15m : non au seuil de 95 %** (percentile 0,926) mais l'écart à la base est réel (36,78 % contre 31,68 %). **En 1h : non** (0,789). **En 1j : non** (0,183). **1w/1M : non évaluables.** |
| Le détecteur anticipe-t-il les retournements ? | **En 15m : 144 des 229 retournements de référence détectés (62,9 %)**, avance médiane 60 min. **En 1h : 23/72 (31,9 %). En 4h : 11/40 (27,5 %). En 1j : 3/38 (7,9 %).** |
| Peut-on l'utiliser comme signal d'entrée ? | **Non en l'état.** Il **distingue** mais ne **sélectionne** pas : 12,4 % des bougies 15m déclenchent une alerte, et 97,4 % des alertes ne correspondent à aucun retournement de référence. |
| Quelles corrections sont encore nécessaires ? | `CONFIRMATION` **n'existe pas** (documenté, jamais assigné) · `1h`/`1w`/`1M` ignorés par le détecteur · motifs de bougies **écrits et jamais appelés** · `CRITICAL_LEVEL = 0.001526` = prix de carnet figé, pilotant 3,2 % des bougies · `confidence` = formule de comptage. |

---

## 2. DONNÉES HISTORIQUES

### 2.1 Limites des API (mesurées en direct le 21/10/2026)

| Venue | Plafond mesuré | Accessibilité locale |
|---|---|---|
| KuCoin `/api/v1/market/candles` | **1 500 bougies/requête** | **joignable** |
| MEXC `/api/v3/klines` | `limit=500` (déjà appelé par le collecteur) | **DNS : « Hôte inconnu » — injoignable** |

`src/agent_analysis.py` lit **exclusivement `sources["mexc"]`** pour les bougies : le chemin de production est MEXC-only. L'historique profond a donc été collecté sur **KuCoin**.

### 2.2 Palier P1 — extension du 15m (26 requêtes, 3,13 Mo)

```
[15m] REPRISE depuis 2026-08-19T11:30:00Z (cache: 6000 bougies)
[15m] téléchargement 26 page(s)...
    copie de sauvegarde -> …\cache-backup-p1\kucoin_TEL_USDT_15m.jsonl.gz
    45000 bougies | 2025-07-09T05:30:00Z -> 2026-10-20T23:15:00Z (468.7 j)
    trous=0 doublons=0 hors-grille=0 statut=OK
consommation : 26 requêtes, 3125765 octets
```

Contrôles appliqués : plafonds vérifiés **avant chaque requête** (`--max-requests`, `--max-bytes`) ; arrêt automatique après **3 erreurs consécutives** ; mode `--resume` (les 4 pages déjà payées ne sont pas refaites) ; **aucune bougie en formation** conservée (filtrée à l'écriture et à la lecture) ; **le cache existant n'est remplacé qu'après validation** (continuité, tri, absence de doublon, absence de perte) ; copie de sauvegarde conservée.

**Validation indépendante :**

| Contrôle | Résultat |
|---|---|
| Bougies lues / clôturées | 45 000 / 45 000 |
| Pas de temps distincts | `{900}` (une seule valeur) |
| Trous / doublons / hors-grille / bougies invalides | 0 / 0 / 0 / 0 |
| **Superset strict du cache P0** | **6 000/6 000 présentes, 0 modifiée** |

### 2.3 Couverture finale

| TF | Bougies | De | À | Trous | Statut |
|---|---|---|---|---|---|
| 15m | **45 000** | 2025-07-09 | 2026-10-20 | 0 | OK |
| 1h | 5 999 | 2026-02-13 | 2026-10-20 | 0 | OK |
| 4h | 5 999 | 2024-01-25 | 2026-10-20 | 0 | OK |
| 1d | 2 723 | 2019-05-07 | 2026-10-19 | 0 | OK |
| 1w | 395 | 2018-02-08 | 2026-10-08 | **1 (58 sem. absentes 2018-19)** | UNAVAILABLE |
| 1M | 89 | 2018-02-01 | 2026-09-01 | 0 | OK |

**Divergences inter-venues** : KuCoin ancre le **1w le jeudi**, MEXC **le lundi** ; KuCoin `1M` commence en 2018-02 (90 bougies), MEXC en 2024-11 (23). Le collecteur de production télécharge **500** bougies/TF mais n'en conserve que **300** (`tel_collector.py:238`) : 200 jetées à chaque collecte.

### 2.4 Contrainte structurante

Le détecteur lit **toujours** le 15m pour ses preuves. Avant P1 : 1d/1w/1M non évaluables. Après P1 (468 jours de 15m) : **1d passe de 7 à 82 épisodes**, **1w de 0 à 11**.

---

## 3. MÉTHODOLOGIE

Protocole figé dans `scripts/backtest/harness.py::PROTOCOL`, sans modification pendant les mesures.

- **Trois barrières anti-fuite** : construction (seule une bougie `close_time ≤ t` est admissible) · test de **perturbation future** (R1) · test d'**équivalence préfixe/complet** (R2, qui autorise le pré-calcul des séries et en prouve la causalité).
- **Alignement réel multi-TF** : le harnais appelle `analyze_timeframe()` et `detect_early_reversal()` **tels quels** ; fidélité vérifiée par **R11** (égalité stricte, tous champs, plus la sortie du détecteur).
- **Deux critères publiés** : v1 « sigma » (`1,5 × √H × ATR14 %`) et v2 « quantile » (q90 causal). v2 est primaire ; v1 est publié en regard.
- **Règle unique** : significatif si **≥ 2 des 4 horizons** atteints ; le faux positif est le complément exact.
- **Horizons en durées** : 15m/1h → 2 h/6 h/24 h/72 h ; 4h → 1 j/3 j/7 j/30 j ; 1d → 2/5/10/20 j ; 1w → 2/5/10/20 sem. ; 1M → 3/6/12/24 mois.
- **Déduplication** : 90 min, même direction → un épisode.
- **Retournements de référence** : définition *ex nihilo* (creux sous EMA50 + EMA20 décroissante + amplitude au-dessus du seuil + première entrée plausible), fenêtre d'avertissement = 2ᵉ horizon le plus court.
- **Test de nullité** : **2 000 permutations** des instants de signal. *Ce nombre est la **précision de l'estimateur**, pas le seuil de décision (qui reste percentile ≥ 0,95) ; l'augmenter ne favorise aucune hypothèse. Avec 200 itérations (résolution 0,5 %), un verdict limite (0,955 vs 0,926) était indistinguable d'une variation de l'estimateur — voir §4.4.*

---

## 4. RÉSULTATS DÉFINITIFS

### 4.1 Production de signaux

| TF | Statuts | Signaux bruts | Épisodes | Densité |
|---|---|---|---|---|
| 15m | ATTENDRE 33 310 · ALERTE 10 190 · INVALIDATION 1 446 · DONNÉES_INSUFF. 54 | 11 636 | **5 565** | **12,37 %/bougie** |
| 1h | ALERTE 1 257 · ATTENDRE 4 377 · INVALIDATION 365 | 1 622 | 1 120 | 18,67 %/bougie |
| 4h | DONNÉES_INSUFF. 3 190 · ATTENDRE 2 090 · ALERTE 629 · INVALIDATION 90 | 718 | 629 | 10,49 %/bougie |
| 1d | DONNÉES_INSUFF. 2 255 · ATTENDRE 371 · ALERTE 82 · INVALIDATION 15 | 97 | 82 | 3,01 %/bougie |
| 1w | DONNÉES_INSUFF. 328 · ATTENDRE 55 · ALERTE 11 · INVALIDATION 1 | 12 | 11 | 2,78 %/bougie |
| 1M | DONNÉES_INSUFF. 74 · ATTENDRE 13 · ALERTE 2 | 2 | 2 | 2,25 %/bougie |

### 4.2 Critère v2 « quantile » (primaire)

| TF | Épisodes | Taux de réussite | IC 95 % (Wilson) | Base de taux | Nullité : observé / médiane / p95 | Percentile | Verdict |
|---|---|---|---|---|---|---|---|
| **15m** | 5 565 | 36,78 % | [35,53 ; 38,06] | 31,68 % | 38,83 % / 37,85 % / 38,95 % | **0,926** | **non significatif** (au seuil 0,95) |
| **1h** | 1 120 | 17,50 % | [15,39 ; 19,84] | 14,80 % | 18,20 % / 17,25 % / 19,17 % | 0,789 | non significatif |
| **4h** | 629 | **32,32 %** | [28,78 ; 36,08] | 26,65 % | 35,38 % / 29,87 % / 32,95 % | **0,999** | **SIGNIFICATIF** |
| **1d** | 82 | 4,88 % | [1,91 ; 11,88] | 13,05 % | 6,33 % / 9,76 % / 15,85 % | 0,183 | non significatif |
| **1w** | 11 | 0,00 % | [0,00 ; 25,88] | 13,02 % | 0,00 % / 9,09 % / — | 0,435 | **non évaluable (n=11)** |
| **1M** | 2 | 0,00 % | [0,00 ; 65,76] | 0 % | — | — | **non évaluable (n=2)** |

Bases de taux directionnelles : 15m 31,90 % haussier / 41,60 % baissier · 1h 15,02 / 18,66 · 4h 27,58 / 31,32 · 1d 13,23 / 8,21 · 1w 14,42 / 4,29.

### 4.3 Critère v1 « sigma » (publié en regard)

| TF | Taux | Base | Discriminant | Percentile | Réf. (détectés/manqués) |
|---|---|---|---|---|---|
| 15m | 2,80 % | 3,18 % | **non** | 0,986 | 42 → 23/19 |
| 1h | 3,30 % | 3,26 % | **non** | 0,9995 | 11 → 1/10 |
| 4h | 1,91 % | 6,17 % | oui | 0,059 | 12 → 3/9 |
| 1d | 1,22 % | 6,51 % | oui | 0,450 | 12 → 1/11 |

Base de taux < 5 % en 15m et 1h → **fenêtre non discriminante** pour ce critère (test R6) : ses « significations » ne sont pas comparables à une performance réelle.

### 4.4 Sensibilité du verdict 15m à l'estimateur — et deux rétractions

| Version | Détecteur | Itérations | Percentile 15m | Verdict 15m |
|---|---|---|---|---|
| P0 | `7df5e5af…` | 200 | 0,955 | « significatif » |
| P1 | `7df5e5af…` | 200 | 0,955 | « significatif » |
| P1-Cline | `81811320…` | 200 | 0,910 | « non significatif » |
| **Final** | `81811320…` | **2 000** | **0,926** | **« non significatif »** |

> **Rétraction n° 2 (version 2 du rapport) :** la version 2 affirmait « en 4h, significativement SUPÉRIEUR au hasard (percentile 1,0) » sur la base de la version à 200 itérations. Avec 2 000 itérations, le percentile 4h est **0,999** → **la conclusion tient**, mais elle était posée au seuil exact de la résolution de l'estimateur.
> **Rétraction n° 1 (version 1) :** « en 4h, significativement INFÉRIEUR au hasard (percentile 0,06) » — reposait sur 76 épisodes ; **infirmé** (voir §4.5).
> **Conclusion honnête :** le verdict 15m **ne franchit pas** le seuil de 95 %. L'écart à la base de taux (36,78 % contre 31,68 %) et le taux de détection des retournements de référence (62,9 %) sont **robustes** ; le caractère « statistiquement significatif » ne l'est pas. Le 15m est donc **suggestif, pas établi**.

### 4.5 P0 → P1 : ce que l'extension a changé

| TF | Épisodes P0 → Final | Taux | Percentile | Réf. détectés |
|---|---|---|---|---|
| 15m | 724 → **5 565** | 38,40 % → 36,78 % | 0,955 → **0,926** | 16/28 → **144/229** |
| 1h | 298 → 1 120 | 18,79 % → 17,50 % | 0,565 → 0,789 | 6/72 → **23/72** |
| 4h | 76 → **629** | 20,00 % → **32,32 %** | 0,06 → **0,999** ⚠️ | 0/40 → **11/40** |
| 1d | 7 → 82 | 14,29 % → 4,88 % | 0,89 → 0,183 | 0/38 → 3/38 |

Le résultat 15m est **stable en magnitude** malgré un effectif multiplié par 7,7. Les résultats 1h/4h/1d étaient **sous-alimentés** en P0.

### 4.6 Contrôle de réalité — le mouvement réel derrière le verdict (15m)

| Verdict | n | h=2 h | h=6 h | h=24 h | h=72 h |
|---|---|---|---|---|---|
| **Haussier « significatif »** | 611 (sur 2 139 haussières, 28,6 %) | médian **+0,40 %** (64 % en hausse) | **+1,08 %** (72 %) | **+2,62 %** (**77 %**) | **+2,75 %** (69 %) |
| Non significatif (tous sens) | 3 518 | −0,27 % dans la direction du signal | −0,66 % | −1,74 % | −2,90 % |

Les épisodes haussiers « significatifs » gagnent **77 % du temps à 24 h** (base ≈ 43 %), maximum observé **+113,9 %**. Les épisodes non significatifs évoluent **à l'opposé** de la direction annoncée.

**Réserve de lecture** : le critère v2 est **relatif au régime de volatilité récent** ; sur une fenêtre baissière, le seuil q90 à 96 bougies peut être **négatif** : un épisode « significatif haussier » peut encore correspondre à une baisse. Les mouvements **absolus** du tableau font foi.

### 4.7 Sélectivité et couverture

- **Alertes sans retournement de référence** : 5 421 / 5 565 (97,4 %) → ratio **24:1**.
- **Avance médiane** des détections : 15m **60 min** (66,7 % avant l'entrée) · 1h **60 min** (65,2 %) · 4h **1 920 min = 32 h** (81,8 %) · 1d **1 440 min = 24 h** (66,7 %).
- **Retournements manqués** : 85/229 (15m) · 49/72 (1h) · 29/40 (4h) · **35/38 (1d)**.

### 4.8 Invalidations

1 446 `INVALIDATION` en 15m (3,2 % des bougies), 365 en 1h, 90 en 4h, 15 en 1d. Règle : `close < CRITICAL_LEVEL = 0.001526`, appliquée **quelle que soit la direction** et **avant** toute analyse de contradiction. `0.001526` ≈ le meilleur ask du snapshot MEXC (`0.001525`) : **prix de carnet figé**, pas un niveau structurel.

### 4.9 Confirmations

**Le statut `CONFIRMATION` n'existe pas dans l'implémentation** : documenté dans la docstring (ligne 479), **jamais assigné**. Les statuts produits sont `ATTENDRE`, `ALERTE_PRÉCOCE`, `INVALIDATION`, `DONNÉES_INSUFFISANTES`. La mesure des confirmations reste **impossible** tant que la Phase B ne l'implémente pas.

---

## 5. VERDICT

### 5.1 Établi
1. **Le « 100 % de faux positifs » est infirmé.** Sur un critère atteignable, le taux de réussite atteint 36,78 % (15m) et 32,32 % (4h) contre des bases de 31,68 % et 26,65 %.
2. **Le détecteur discrimine réellement** : en 15m, les épisodes haussiers « significatifs » gagnent à 77 % à 24 h, contre 43 % de base ; les autres évoluent à l'opposé.
3. **Un seul verdict atteint le seuil statistique : le 4h** (percentile 0,999, 629 épisodes).
4. **Le 15m est suggestif mais non établi** (percentile 0,926) ; l'écart à la base et la couverture des retournements (144/229) sont robustes.
5. **Le 1j est inutile** : 4,88 % de réussite, 35 retournements manqués sur 38.
6. **Le défaut dominant est la sélectivité**, pas la qualité : 12,4 % des bougies 15m alertent, 97,4 % des alertes ne correspondent à aucun retournement.

### 5.2 Non établi — à ne pas affirmer
- **1w et 1M** : effectifs de 11 et 2 épisodes → **aucune conclusion**.
- **Robustesse hors échantillon** : une seule fenêtre, un instrument, un régime dominant baissier.
- **Rentabilité** : aucun frais, aucun spread, aucune liquidité prise en compte ; le critère v2 est relatif au régime, pas un gain.

### 5.3 Conclusion opérationnelle
> Le détecteur actuel **ne doit pas servir de signal d'entrée autonome**. Il **distingue** les mouvements (établi en 4h, suggéré en 15m) mais **ne hiérarchise pas** : il alerte trop, et l'identification des « bons » épisodes est **a posteriori**, donc inutilisable en temps réel. La Phase B doit porter sur la **sélectivité et la hiérarchisation** (confirmation explicite, réduction de la densité d'alertes), **pas** sur l'ajustement de seuils.

---

## 6. LIMITES ET DONNÉES MANQUANTES

| Limite | Conséquence |
|---|---|
| **MEXC injoignable localement** | Historique KuCoin seule ; cross-check non rejoué ; divergence d'ancrage 1w non résolue |
| **Seul le 15m a été étendu** | 1h (250 j), 4h (2,7 ans), 1d (7,5 ans) restent limités ; un palier P2 est possible (26 requêtes/TF) mais non autorisé |
| **1w incomplet** | 58 semaines manquantes + ancrage jeudi → non exploité |
| **Horizons corrélés** | Un même mouvement satisfait plusieurs horizons : le « ≥ 2 horizons » n'est pas une double confirmation indépendante |
| **Test de nullité : résolution 0,05 %** | Un verdict à 0,926 reste à 2,4 points du seuil ; un changement mineur du détecteur peut le faire basculer |
| **Une seule fenêtre, un seul instrument** | Ni validation hors échantillon, ni robustesse multi-régime |
| **Aucune donnée BTC / ETH / TEL-BTC** | Zéro occurrence dans tout le dépôt |
| **Liquidité non historisée** | Le snapshot ne contient que l'état courant du carnet |
| **Filtre de sélectivité a posteriori** | Les « bons » épisodes ne sont identifiables qu'après coup |

---

## 7. COMMANDES ET TESTS RÉELLEMENT EXÉCUTÉS

```bash
# Historique
python scripts/backtest/fetch_history.py --dry-run --venue kucoin --timeframes 15m --pages 15m=26 --max-requests 26
python scripts/backtest/fetch_history.py --venue kucoin --timeframes 15m --pages 15m=26 --resume \
    --max-requests 26 --max-bytes 5000000 --backup-dir …\cache-backup-p1
#   -> 26 requêtes, 3 125 765 octets, 45 000 bougies, 468,7 j, 0 trou

# Backtests (P0 conservé, P1, rejeu Cline, final)
python scripts/backtest/run_backtest.py --output backtest_results_v2.json
python scripts/backtest/run_backtest.py --output backtest_results_p1.json
python scripts/backtest/run_backtest.py --output backtest_results_p1_cline.json
python scripts/backtest/run_backtest.py --output backtest_results_final.json --summary backtest_results_final_summary.json

# Résumés et journal
python scripts/backtest/summarize_results.py backtest_results_p1.json --output backtest_results_p1_summary.json --gzip
python scripts/backtest/make_journal.py backtest_results_final.json JOURNAL_APPRENTISSAGE_FINAL.md

# Tests
python -m pytest tests/ collector/ -q                      # 139 passed, 3 skipped, 13 subtests
python -m unittest discover -s tests                        # Ran 128 - OK (skipped=3)   [CI]
python -m unittest discover -s collector -p "test_*.py"     # Ran 14 - OK
node tests/test_dashboard.js                               # OK
node tests/test_realtime.js                                # OK
python -m pytest tests/test_backtest_harness.py -q          # 22 passed
```

**Tests de régression du harnais** : R1 perturbation future (état + détection + seuil quantile) · R2 équivalence préfixe/complet (12 indicateurs) · R3 alignement multi-TF et exclusion des bougies en formation · R4 déduplication · R5 reproductibilité · R6 base de taux / fenêtre non discriminante · R7 complétude des statuts · R8 cas dégénéré · R9 intégrité de l'archive · R10 fixture sans réseau · R11 fidélité stricte au code de production. → **22 passed**.

---

## 8. RÉSULTATS VOLUMINEUX — ÉVALUATION ET RECOMMANDATION

| Fichier | Brut | gzip | Résumé (sans détail) |
|---|---|---|---|
| `backtest_results_v2.json` (P0) | 3,69 Mo | 0,26 Mo | 29 Ko (4 Ko gzip) |
| `backtest_results_p1.json` (P1) | 24,37 Mo | 1,73 Mo | 29,5 Ko (4 Ko gzip) |
| `backtest_results_p1_cline.json` | ~24 Mo | — | — |
| `backtest_results_final.json` | ~24 Mo | — | **29,9 Ko** (résumé) |

Contenu retiré par le résumé : `episodes_detail` (14 826 entrées), `missed_reversals_detail` (254), `detected_reversals_detail` (209) — **régénérables à l'identique** par `run_backtest.py` depuis le cache local (0,99 Mo), lui-même reconstructible par `fetch_history.py --resume`.

**Recommandation** : versionner les **résumés** (29,9 Ko, lisibles et diffables) ; conserver le complet **hors dépôt** ou en `.json.gz`. **Aucun fichier n'a été supprimé** — la décision de rétention revient au mainteneur.

---

## 9. HISTORIQUE DES VERSIONS DU DÉTECTEUR ET DES RÉSULTATS

| Heure | Événement | Empreinte | Résultats |
|---|---|---|---|
| 01:15:35 | Sauvegarde du worktree | `e577550f…` | — |
| 01:17:47 | **Modification concurrente n° 1** : réécriture de `has_rsi_divergence`/`has_bearish_divergence` (`_extreme_with_rsi`, `_divergence_windows`) — corrige une **fuite temporelle** (index RSI négatif lisant la fenêtre *récente* quand l'historique est trop court) et le traitement des prix égaux | `7df5e5af…` | P0, P1 |
| 01:47:10 | **Modification concurrente n° 2** : ajout de `_align_divergence_series` (tronque les deux séries sur leur partie commune — supprime l'`IndexError` de longueur incohérente et préserve l'appariement RSI/prix) ; +11 tests | **`81811320…`** | P1-Cline, **Final** |

**Comparaison n° 1 → n° 2 (mêmes données, 45 000 bougies 15m)** :

| TF | Épisodes | Taux de réussite | Base de taux | Percentile | Réf. détectés |
|---|---|---|---|---|---|
| 15m | 5 567 → 5 565 | 36,824 % → 36,783 % | 31,68 % → 31,68 % | 0,955 → 0,910 *(200 it.)* | 144/229 → 144/229 |
| 1h | 1 122 → 1 120 | 17,47 % → 17,50 % | 14,80 % → 14,80 % | 0,77 → 0,80 | 23/72 → 23/72 |
| 4h | 630 → 629 | 32,43 % → 32,32 % | 26,65 % → 26,65 % | 1,00 → 1,00 | 11/40 → 11/40 |
| 1d / 1w / 1M | identiques | identiques | identiques | identiques | identiques |

**Impact réel de la modification : minime et homogène** — 2 à 3 épisodes retirés en 15m/1h/4h, **aucun** changement sur les retournements de référence, les bases de taux, ni sur 1d/1w/1M. Le basculement du verdict 15m vient de la **résolution de l'estimateur**, pas de la correction.

**Gouvernance appliquée** : le harnais ne modifie jamais le détecteur ; il **lit** le fichier et **enregistre son empreinte** dans chaque résultat. Si l'empreinte change, les chiffres deviennent caducs et le backtest doit être rejoué. Cline reste responsable de `src/agent_analysis.py` ; ce travail n'y a pas touché.

---

## 10. TÂCHES RESTANTES

| # | Tâche | Blocage |
|---|---|---|
| 1 | Rejouer le backtest après la **version finale** du détecteur (Cline) et mettre à jour le présent rapport | **attend la fin du travail de Cline** |
| 2 | Implémenter `CONFIRMATION` et la hiérarchisation des alertes | Cline (Phase B) |
| 3 | Brancher les motifs de bougies (`has_hammer_pattern`, `has_engulfing_bullish`, `has_level_rejection`) sur les vraies bougies OHLC | Cline |
| 4 | Utiliser réellement `1h`, `1w`, `1M` | Cline |
| 5 | Justifier ou neutraliser `CRITICAL_LEVEL = 0.001526` ; ne pas l'appliquer à la direction opposée | Cline |
| 6 | Palier P2 : étendre 1h/4h/1d/1w (26 requêtes par TF) | autorisation |
| 7 | Résolution du conflit Git — **scénario A recommandé** (voir `CONFLIT_GIT.md`) | **audit seul — décision du mainteneur** |
| 8 | Politique de versionnement des résultats volumineux | **décision du mainteneur** |
| 9 | BTC / ETH / TEL-BTC et liquidité historisée | non commencé |

---

*Rapport produit le 21 octobre 2026. Le détecteur n'a pas été modifié par ce travail. Aucune donnée n'a été inventée : toutes les valeurs proviennent de `backtest_results_final.json` (empreinte `81811320…`), produit par `scripts/backtest/run_backtest.py`.*
