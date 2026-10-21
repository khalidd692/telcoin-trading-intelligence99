# Telcoin Trading Intelligence

Système **en lecture seule** de surveillance du marché TEL/USDT : collecte de données publiques,
calcul d'indicateurs déterministes, analyse multi-unités de temps, détection de retournements
et backtest historique hors échantillon.

> **Aucune clé d'API, aucun accès à un compte, aucun ordre passé.** Le système ne peut pas
> trader. « SURVEILLER » signifie que les contrôles de flux ont réussi — **ce n'est ni un signal
> d'achat, ni une preuve d'avantage statistique**.

---

## 1. Architecture

```
collector/tel_collector.py   collecte publique MEXC + KuCoin (carnet, trades, bougies 15m→1M)
        │
        ▼  site/tel_snapshot.json          (snapshot détaillé, horodaté, empreinte SHA-256)
src/agent_analysis.py        analyse multi-unités + détection de retournement
        │                    (statuts ALERTE_PRÉCOCE / CONFIRMATION / INVALIDATION / ATTENDRE)
        ▼  site/agent_analysis.json       (rapport d'analyse, statut global + early_reversal)
site/index.html + realtime.js tableau de bord statique + flux WebSocket temps réel
```

Le **dashboard** consomme `report.json` (collecte 15m), `tel_snapshot.json` (détail) et
`agent_analysis.json` (analyse). Il **rejette** toute donnée périmée (> 20 min), incohérente ou
d'ascendance différente (`collection_id`), et affiche alors `ATTENDRE` sans rien inventer.

## 2. Unités de temps et indicateurs

Unités couvertes : **15m, 1h, 4h, 1d, 1w, 1M** (bougies **clôturées uniquement** ; la bougie en
formation n'alimente jamais un indicateur, une preuve ou un signal).

Indicateurs calculés par unité de temps : EMA 20/50, SMA 10/20/50/100/200, RSI 14, MACD
(histogramme), ATR 14, Momentum 10, CCI 20, Stochastic %K/%D, DMI/ADX 14, Awesome Oscillator,
volume relatif, tendance (EMA + signe du MACD).

Manques de données, valeurs manquantes, doublons, incohérences OHLC → l'unité de temps est
marquée `UNAVAILABLE` / `PARTIEL` et **aucune valeur n'est inventée**.

## 3. Détection de retournement

`detect_early_reversal()` reconstruit, **depuis l'historique uniquement**, le *setup* de
retournement le plus récent : un extrême structurel (la barre est l'extrême de sa fenêtre)
auquel s'ajoute un **retournement de momentum matériel** (amplitude ≥ 5 % de l'ATR, ou RSI en
hausse d'au moins 2 points).

| Statut | Signification |
|---|---|
| `ALERTE_PRÉCOCE` | un setup existe et attend encore confirmation (le mouvement n'est pas encore parti) |
| `CONFIRMATION` | le setup tient et une preuve indépendante montre que le retournement a démarré |
| `INVALIDATION` | l'ancre structurelle du setup est rompue : le scénario qu'elle décrivait ne tient plus |
| `ATTENDRE` | aucun setup, setup ambigu, ou données insuffisantes |
| `DONNÉES_INSUFFISANTES` | unité de temps 15m indisponible |

Règles structurantes :
* la **direction vient de l'extrême structurel**, jamais d'une série de bougies ;
* une alerte exige le setup **plus au moins une famille de preuves indépendante**
  (`structure`, `volume`, `context`) ; la famille `momentum` ne compte qu'une fois ;
* l'**alignement de tendance** n'est **pas** une preuve de retournement : c'est une observation ;
* l'invalidation repose sur l'**ancre structurelle** du setup, pas sur un niveau de prix fixe ;
* les figures de bougies (marteau, engulfing, rejet de niveau) n'entrent en jeu qu'**à
  l'extrémité du setup** ;
* `confidence` est un **score de convergence** (0-100), **pas une probabilité** et non calibré.

Le moteur est une **fonction pure** : mêmes entrées → même sortie, rejouable sur l'historique,
sans aucun état porté entre les appels.

## 4. Exécution

```bash
# tests (aucune dépendance externe)
python -m unittest discover -s tests -v
python -m unittest discover -s collector -p "test_*.py" -v
node tests/test_dashboard.js
node tests/test_realtime.js

# collecte publique (read-only) puis analyse
python collector/tel_collector.py --out site/tel_snapshot.json --passes 3 --interval 3 --notional 300
python -m src.agent_analysis --input site/tel_snapshot.json --output site/agent_analysis.json
```

**Prérequis** : Python 3.11+ (bibliothèque standard uniquement) et Node.js pour les tests
JavaScript. Aucun `pip install`, aucun secret, aucune clé.

> MEXC et KuCoin sont tous deux interrogés. Si une venue est injoignable, la collecte
> **échoue en mode fermé** (`ATTENDRE`, `snapshot_id` nul) plutôt que de produire un rapport
> partiel. C'est le comportement attendu hors de la CI.

## 5. Backtest historique hors échantillon

```bash
# 1. historique (cache local, hors dépôt ; aucune écriture dans le dépôt)
python scripts/backtest/fetch_history.py --dry-run
python scripts/backtest/fetch_history.py --venue kucoin

# 2. backtest complet (ancien moteur vs moteur v2, IS/OOS, brut et net de frais)
python scripts/backtest/run_oos.py --output oos_results.json

# 3. contrôles
python scripts/backtest/check_causality.py     # aucune fuite temporelle sur données réelles
```

* **Protocole figé** : `OOS_PROTOCOL.md` (séparation 60 % conception / 40 % validation,
  critères de significativité, scénarios de frais, mesures).
* **Garde-fous** : le seuil de significativité est une propriété du **marché** (quantile
  empirique causale des mouvements antérieurs) ; le coût de transaction est une propriété du
  **trade** et n'entre qu'une fois, dans la condition de performance nette. Le détecteur et la
  référence de comparaison utilisent **exactement le même test**.
* **Contrôles** : R1 (perturbation du futur), R2 (équivalence préfixe/complet), R3 (alignement
  multi-unités), R4 (déduplication), R5 (reproductibilité), R6 (atteignabilité), R7 (complétude
  des statuts), R8 (cas dégénéré), R9 (intégrité de l'archive), R10 (fixture sans réseau),
  R11 (fidélité au code de production) — dans `tests/test_backtest_harness.py`.

## 6. Exploitabilité et régime de marché (affichés par le tableau de bord)

Le moteur qualifie chaque situation :

* `regime` : `NEUTRE` | `TENDANCE_HAUSSIERE` | `TENDANCE_BAISSIERE` | `INDETERMINE`,
  d'après la variation relative sur 30 bougies **journalières clôturées** ;
* `exploitable` : `true` uniquement si le statut est `CONFIRMATION` **et** le régime est
  `NEUTRE`, avec `exploitable_reason` en clair.

Le tableau de bord affiche cette qualification : le **régime** (et sa variation en %),
l'**état d'exploitabilité** et la **raison** correspondante. Un badge vert n'est réservé
qu'aux signaux réellement exploitables, et une `ALERTE_PRÉCOCE` n'est jamais présentée
comme une entrée. Les observations non exploitables (preuves, contradictions, objectifs)
restent visibles.

Cette qualification vient d'une **validation hors échantillon** (période vierge incluse) :
l'espérance des signaux non qualifiés est **négative** (pire qu'une entrée aléatoire), tandis
que celle du sous-ensemble exploitable est **positive dans les quatre segments** — avec un
intervalle de confiance qui **touche zéro** et une marge slender sur les coûts. Elle réduit
le volume de signaux de **92 % à 97 %**. **C'est une règle de recherche, pas une preuve de
rentabilité** : les frais réels ne sont pas confirmés et l'intervalle de confiance inclut
zéro. Voir `RECHERCHE_QUALITE_ENTREES.md`.

## 7. Contexte de marché (BTC, ETH, TEL/BTC)

Vérifié disponible sur la même venue et **aligné sur la même grille de bougies** :
`BTC-USDT`, `ETH-USDT` et la paire directe `TEL-BTC` existent sur KuCoin. La profondeur du
carnet (liquidité) est un **état instantané** : il n'existe pas d'historique de liquidité.

Ces sources ont été **collectées, alignées et testées** : elles sont disponibles, horodatées
et accessibles au moment du signal. **Elles n'apportent pas de valeur prédictive
démontrée** pour les signaux de retournement de TEL (quatre conditionnements testés, tous
instables ou négatifs) : elles ne sont donc **pas intégrées** au détecteur. Aucune
substitution ni simulation n'est effectuée.

## 8. Rapports produits

| Fichier | Contenu |
|---|---|
| `DETECTEUR_V2_RAPPORT.md` | conception du moteur v2, défauts corrigés, tests, mesures |
| `RECHERCHE_QUALITE_ENTREES.md` | recherche sur la qualité économique : causes des pertes, hypothèses rejetées, règle validée |
| `OOS_PROTOCOL.md` | protocole d'évaluation hors échantillon (figé) |
| `BACKTEST_HISTORIQUE_TEL.md` | évaluation historique complète, limites |
| `JOURNAL_APPRENTISSAGE*.md` | journal des retournements détectés, manqués et contradictoires |
| `CONFLIT_GIT.md` | audit des workflows et résolution de divergence recommandée |

## 9. Sécurité et limites

* Lecture seule stricte : aucun ordre, aucune clé, aucun accès compte.
* Le dashboard **fail-closed** : donnée absente, périmée ou incohérente ⇒ `ATTENDRE`.
* Les performances historiques **ne sont pas une garantie**. Les limites statistiques
  (effectifs, regimes de marché, coûts réels non vérifiés) sont explicitées dans les rapports.
* `site/agent_analysis.json` et `site/tel_snapshot.json` sont des **artefacts régénérés par la
  CI** ; les versions committées peuvent être anciennes — c'est signalé par l'âge affiché.

---

*Outil d'aide à la décision. Ce n'est pas un conseil financier, et cela ne constitue pas une
autorisation de trader.*
