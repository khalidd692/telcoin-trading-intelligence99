# PROTOCOLE D'ÉVALUATION HORS ÉCHANTILLON — FIGÉ AVANT EXÉCUTION

**Statut : FIGÉ.** Ce document est écrit **avant** toute exécution du backtest et avant
toute lecture d'un résultat hors échantillon. Toute modification ultérieure doit être
signalée comme une révision de protocole, avec sa justification ; **aucun critère ne
sera retouché après observation des résultats OOS**.

**Date de gel** : 21 octobre 2026
**Moteurs comparés** : moteur **ancien** (empreinte `81811320dac01b3f334c7e4364d5c163f7b5cd19ca66a4a184d176c8bd8befed`,
chargé depuis la sauvegarde vérifiée) et moteur **v2** (empreinte `1dc21c0e475058269f252908a17fb92e2a7e46e624b8bcac0755be44b97ddd4a`).
**Données** : cache local KuCoin `TEL-USDT` (aucune collecte nouvelle).
**Période couverte par les données 15m** : 2025-07-09 05:30 → 2026-10-20 23:15 (468,7 jours).

---

## 1. SÉPARATION CHRONOLOGIQUE

La séparation est **absolue dans le temps** et appliquée à **toutes** les unités de temps,
afin que l'ancien et le nouveau moteur soient évalués sur les mêmes périodes.

* Point de coupure : `SPLIT = premier__15m + 0,60 × (dernier__15m − premier__15m)`,
  calculé sur l'axe 15m (le plus fin, donc le plus contraignant).
* **Conception (IS)** : barres dont `close_time ≤ SPLIT`.
* **Validation (OOS)** : barres dont `close_time > SPLIT`.
* Une barre appartient à un segment **par son instant de clôture**, quelle que soit son TF.

**Contrainte structurelle à documenter** : le détecteur lit toujours le 15m pour ses
preuves. Toute barre d'un TF supérieur antérieure au début de l'historique 15m **ne peut
pas être évaluée** (statut `DONNÉES_INSUFFISANTES`). Pour ces TF, la période utile est
donc bornée par la couverture 15m, et le nombre de points non évaluables est **compté et
publié**, jamais assimilé à un échec.

---

## 2. CRITÈRE DE MOUVEMENT SIGNIFICATIF (inchangé, déjà validé)

Identique au protocole v1.1 des travaux précédents, **non modifié** :

* Seuil à l'horizon H : **quantile empirique causal q90** des mouvements avant à
  l'horizon H, calculé sur une fenêtre glissante retardée de `h_max` (causalité stricte).
* Un mouvement est **significatif** si **≥ 2 des 4 horizons disponibles** sont atteints.
* **Règle de positivité (v1.1)** : le mouvement **net du coût** doit être **strictement
  positif** dans la direction du signal, en plus de dépasser le seuil.
* Le « faux positif » est **exactement le complément** de cette règle.
* Horizons exprimés en durées : 15m/1h → 2 h/6 h/24 h/72 h ; 4h → 1 j/3 j/7 j/30 j ;
  1d → 2/5/10/20 j ; 1w → 2/5/10/20 sem. ; 1M → 3/6/12/24 mois.

> **Révision v1.0 → v1.1 (appliquée AVANT toute lecture de résultat hors échantillon,
> avant le run unique).** Motif : le seuil q90 des mouvements avant peut être **négatif**
> en régime baissier (−4,5 % sur la fenêtre 15m mesurée). Sans condition de positivité,
> un mouvement baissier pouvait être qualifié de « significatif haussier », et les deux
> directions pouvaient être significatives simultanément — ce qui fausse la référence de
> comparaison. La règle de positivité rend la mesure **économiquement interprétable**
> (un mouvement « significatif » est nécessairement un gain net dans la direction
> annoncée). Les deux moteurs sont réévalués avec la **même** règle : la comparaison
> reste juste.

Le critère v1 « sigma » est conservé et publié **en regard** (il est non discriminant :
base de taux < 5 % en 15m et 1h).

---

## 3. SCÉNARIOS DE COÛTS (figés)

Le slippage est **observé** sur le carnet du snapshot : MEXC **0,285 %** pour 300 USDT
(4 niveaux de profondeur), KuCoin **0,185 %**. Les **frais ne sont pas vérifiés**
(`fees: verified = False`) → ils sont traités en scénarios, jamais affirmés.

| Scénario | Composition | Coût aller-retour |
|---|---|---|
| **S0 — brut** | aucun coût | 0,00 % |
| **S1 — slippage seul** | 2 × 0,285 % (entrée à l'ask + sortie au bid) | 0,57 % |
| **S2 — S1 + frais 0,10 %/côté** | 0,57 % + 0,20 % | 0,77 % |
| **S3 — S1 + frais 0,15 %/côté** | 0,57 % + 0,30 % | 0,87 % |

### 3.1 Règle de non-double-compte (obligatoire)

Le seuil de significativité est une **propriété du marché** (quantile empirique des
mouvements antérieurs) : il se compare au mouvement **brut**. Le coût est une
**propriété du trade** : il sert à exiger que la **performance nette** soit strictement
positive. Le coût n'entre donc qu'**une fois** dans le test :

```
significatif(barre k, direction D, coût c) =
      mouvement_brut(D) >= seuil(D)      # le marché a-t-il assez bougé ?
   ET mouvement_brut(D) - c > 0          # le trade a-t-il été rentable ?
```

Appliquer le coût **aux deux** endroits le compterait deux fois : c'est précisément
l'erreur corrigée en v1.2 (voir ci-dessous), et cela faussait aussi le sens de l'effet
des frais lorsque le seuil était négatif.

Le détecteur et la **référence de comparaison** utilisent **exactement le même test**,
sur le **même jeu de seuils**, pour un segment donné : la référence ne peut donc pas
diverger du détecteur, et aucun coût n'est compté deux fois.

La référence de comparaison est, pour chaque scénario :
`base_rate(coût) = proportion de barres du segment qui seraient « significatives »
si un signal y était émis` (mélange de directions identique à celui des épisodes).

> **Révision v1.1 → v1.2.** Appliquée **après lecture des résultats de conception
> (IS) uniquement**, et **non** pour améliorer une performance : le coût était appliqué
> deux fois, ce que la règle de non-double-compte ci-dessus interdit. La correction
> s'applique **identiquement** aux deux moteurs ; elle ne favorise aucun des deux. Les
> résultats OOS publiés proviennent de la version v1.2 ; ceux de v1.1 sont également
> conservés pour transparence (`oos_results_v1.1.json`).

---

## 4. MESURES (par TF, par segment, par statut)

| Mesure | Définition |
|---|---|
| **Densité** | épisodes (dédupliqués) / nombre de barres évaluables du segment |
| **Taux de réussite** | épisodes significatifs / épisodes évaluables (brut et net) |
| **Référence** | `base_rate(coût)` sur les mêmes barres |
| **Écart (lift)** | taux du détecteur / référence |
| **Faux positifs** | épisodes non significatifs (complément exact de la règle) |
| **IC 95 %** | intervalle de Wilson sur le taux |
| **Test de nullité** | 2 000 permutations de bars du segment → percentile de la taux observé |
| **Retournements de référence** | définition *ex nihilo* (crease sous EMA50 + EMA20 en baisse + amplitude au-dessus du seuil + première entrée plausible), **hors coût** (c'est un phénomène de marché, pas un P&L) |
| **Retournements manqués** | retournements de référence sans alerte dans la fenêtre d'avertissement |
| **Délai d'avance** | `entrée plausible − alerte` (positif = alerte avant l'entrée) |
| **INVALIDATION** | mesuré **en sens inverse** : un invalidation est **correct** si le mouvement va dans la direction **opposée** au setup qu'il a invalidé |

**Déduplication** : 90 minutes, même direction → un épisode, daté du **premier** signal
(aucune anticipation dans l'attribution).

**Statuts** : `ALERTE_PRÉCOCE`, `CONFIRMATION`, `INVALIDATION`, et une vue « tout signal »
(ALERTE + CONFIRMATION). `ATTENDRE` et `DONNÉES_INSUFFISANTES` ne sont pas des signaux.

---

## 5. CONTRÔLES D'EXPLOITABILITÉ ET DE NON-BIAIS (exécutés AVANT les résultats)

1. **Causalité sur données réelles** : pour un échantillon de barres réparties sur
   l'historique, le détecteur est recalculé sur la série **tronquée** à la barre `i` puis
   la série est **perturbée après `i`** ; la sortie doit être **strictement identique**.
2. **Causalité structurelle** : test R1 du harnais (état, détection et seuil quantile).
3. **Fidélité au code de production** : test R11 (le chemin rapide du harnais reproduit
   `analyze_timeframe()` strictement).
4. **Pas de sélection** : tous les épisodes du segment sont comptés, sans filtre de
   performance ; les non-evaluables sont comptés à part.
5. **Attribution sans anticipation** : un épisode est daté de son **premier** signal ;
   la mesure des mouvements futurs sert uniquement à l'évaluation, jamais à la décision.

---

## 6. LIMITES DÉCLARÉES AVANT EXÉCUTION

* Une seule fenêtre, un seul instrument, un seul régime dominant.
* Le 1M n'a que 89 bougies et le 1w est incomplet (58 semaines manquantes en 2018-2019) :
  **aucune conclusion** n'en sera tirée.
* La couverture 15m borne les TF supérieurs.
* Les corrélations entre horizons ne sont pas indépendantes : « ≥ 2 horizons » n'est pas
  une double confirmation indépendante.
* Les frais ne sont pas vérifiés : les scénarios S2/S3 sont des **hypothèses**.
* La significativité statistique d'un taux est une question de **puissance** : un
  pourcentage calculé sur 7 épisodes ne dit rien.

---

## 7. RÈGLES DE CONCLUSION

* Une amélioration n'est **pas** déclarée démontrée si l'OOS ne la confirme pas.
* Les segments **IS** et **OOS** sont présentés **séparément**, jamais fusionnés.
* Les résultats **bruts et nets** sont présentés pour chaque scénario de coûts.
* Si la méthodologie ne permet pas de mesurer correctement (effectif insuffisant,
  non-evaluabilité), le problème est **énoncé** et aucune conclusion n'est tirée.
* Aucun paramètre du détecteur ni du protocole n'est modifié après lecture de l'OOS.
