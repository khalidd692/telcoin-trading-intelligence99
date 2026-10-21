# RECHERCHE — QUALITÉ ÉCONOMIQUE DES ENTRÉES TEL/USDT

**Date** : 21 octobre 2026 · **Phase** : recherche et analyse ciblée (après l'évaluation hors échantillon négative)
**Moteur évalué** : `src/agent_analysis.py` · **Empreinte au moment de la validation de la correction** :
`65fddaa676881095b620b6762ab6348e439d63cc76e6cec8a4b04ee44bbc2f95`
**Données** : KuCoin `TEL-USDT`, 15m **90 000 bougies** (2024-03-27 → 2026-10-20) + contexte BTC/ETH/TEL-BTC 1h (22 499 bougies alignées)

---

## 1. RÉSULTAT DE LA PHASE EN UNE PAGE

La phase précédente avait établi qu'**aucun des deux moteurs ne battait le hasard** (espérance des signaux négative, y compris avant frais). Cette phase a cherché **pourquoi**, puis a cherché si une **qualification** des signaux pouvait restaurer une espérance positive.

| Résultat | Statut |
|---|---|
| **Cause principale des pertes identifiée** | ✅ le **régime de marché** : un retournement pris contre une tendance longue perd dans les deux sens |
| **Hypothèse testée hors échantillon (règle de recherche — l'espérance nette est positive mais l'IC inclut zéro et les frais ne sont pas confirmés)** | ✅ `CONFIRMATION` **et** régime 1d 30 j neutre (variation ±5 %) → espérance brute **positive dans les 4 segments**, nette après 0,57 % aller-retour dans les 4 |
| **Correction implémentée et revalidée** | ✅ le moteur reproduit l'espérance validée à **0,0003 point** près |
| **Contexte BTC / ETH / TEL-BTC** | ✅ disponible, aligné, causal — mais **aucune valeur prédictive supplémentaire démontrée** (hypothèses rejetées) |
| **Statut global du système** | ⚠️ l'avantage reste **mince** : la marge au-dessus des coûts est de 0,11 à 1,23 points selon le segment, l'intervalle de confiance de l'estimation indépendante touche 0 |

---

## 2. RÉSULTATS PAR STATUT ET PAR UNITÉ DE TEMPS

Éspérance = mouvement **dirigé** moyen à 24 h (15m) ou à l'horizon propre de l'unité (1h : 6 h, 4h : 6 h, 1d : 15 min) ; `esp72` = horizon long (72 h / 18 h / 18 h / 45 min). Mesures sur les segments **NEW** (vierge) et **OOS** (déjà consulté).

| Unité | Statut | Segment | n | esp24 | esp72 | % favorable | pire | meilleur |
|---|---|---|---|---|---|---|---|---|
| 15m | ALERTE_PRÉCOCE | NEW | 1 146 | −0,294 % | −0,981 % | 50 % | −36,3 % | +44,6 % |
| 15m | ALERTE_PRÉCOCE | OOS | 462 | −0,406 % | −0,305 % | 42 % | −25,3 % | +36,3 % |
| 15m | CONFIRMATION | NEW | 964 | +0,016 % | −0,730 % | 51 % | −27,0 % | +33,4 % |
| 15m | CONFIRMATION | OOS | 456 | −0,324 % | −0,357 % | 45 % | −20,5 % | +42,7 % |
| 15m | INVALIDATION | NEW | 430 | +0,201 % | −0,296 % | 54 % | −33,6 % | +24,8 % |
| 15m | INVALIDATION | OOS | 207 | −0,445 % | −0,155 % | 43 % | −21,4 % | +22,6 % |
| **15m** | **EXPLOITABLE** | **NEW** | **62** | **+0,682 %** | **+1,488 %** | 56 % | −8,3 % | +11,5 % |
| **15m** | **EXPLOITABLE** | **OOS** | **78** | **+0,792 %** | **+0,641 %** | 49 % | −8,6 % | +42,7 % |
| 1h | ALERTE_PRÉCOCE | OOS | 462 | −0,268 % | −0,464 % | 44 % | −28,7 % | +11,3 % |
| 1h | CONFIRMATION | OOS | 456 | −0,118 % | −0,337 % | 45 % | −13,0 % | +11,6 % |
| 1h | EXPLOITABLE | NEW | 62 | −0,308 % | +0,211 % | 45 % | −7,7 % | +9,0 % |
| 1h | EXPLOITABLE | OOS | 77 | −0,132 % | +0,051 % | 48 % | −4,9 % | +5,1 % |
| 4h | EXPLOITABLE | NEW | 62 | −0,078 % | −0,385 % | 47 % | −6,1 % | +4,1 % |
| 4h | EXPLOITABLE | OOS | 78 | −0,205 % | −0,226 % | 45 % | −3,7 % | +3,2 % |
| 1d | EXPLOITABLE | NEW | 62 | +0,067 % | +0,069 % | 52 % | −1,3 % | +1,5 % |
| 1d | EXPLOITABLE | OOS | 78 | −0,049 % | −0,078 % | 33 % | −1,1 % | +1,4 % |

**Lecture** :
* L'`INVALIDATION` est mesuré **dans le sens du setup** : une espérance négative y signifie que le prix est allé **contre** le setup invalidé, donc que l'invalidation a été **juste**. Le résultat est **instable** (NEW +0,20 %, OOS −0,45 %) → l'invalidation n'est pas non plus un signal fiable.
* Le signal exploitable **ne paie qu'à 24 h et 72 h**. Il est **négatif à 6 h, 15 min et 45 min** : c'est un signal **lent** (retournement sur un ou deux jours), pas un scalping.
* **Délai d'avance** (15m) : 161 retournements de référence sur 462 détectés à l'avance (34,8 %), **301 manqués**, avance médiane **75 min**, 88,8 % des détections précèdent l'entrée plausible.
* **Faux positifs** : la qualification exploitable écarte **92 % à 97 %** des signaux (il n'en reste que 2,9 % à 8,5 %).
* **Profil de payoff du sous-ensemble exploitable** (OOS, n=78) : a 24 h, gain moyen **+4,461 %**, perte moyenne **-2,783 %**, **ratio gain/perte 1,60** (contre 1,10 pour les alertes brutes et 1,02 pour les confirmations non filtrees) ; pire cas -8,6 %, meilleur +42,7 %. C'est le profil le plus favorable mesure sur l'ensemble du projet.

---

## 3. AUDIT DE LA MÉTHODOLOGIE

### 3.1 Définition des événements de référence
* Un retournement de référence = creux (ou sommet) sous/au-dessus de l'EMA50 avec EMA20 décroissante (croissante), suivi d'une amplitude au-dessus du seuil de volatilité, avec première entrée plausible. **Il sert d'étiquette, pas de déclencheur** : aucun signal n'en dépend.
* La fenêtre d'avertissement est le **2ᵉ horizon le plus court** (24 bougies 15m = 6 h) : plus large, elle saturerait, le détecteur émettant ~7 alertes/jour.
* **Biais de sélection vérifié** : l'appairement se fait sur les **ALERTES_PRÉCOCES** (l'avertissement), pas sur les confirmations, pour ne pas attribuer aux confirmations un délai qu'elles n'ont pas.

### 3.2 Fenêtres de rendement
* Les rendements sont mesurés **depuis la clôture de la barre du signal** : le signal n'est connu qu'à cette clôture, l'entrée se fait à ce prix. Aucun usage d'information future.
* Deux horizons par unité de temps (24 h et 72 h en 15m) : le résultat est **robuste aux deux** pour le sous-ensemble exploitable.
* **Point de vigilance levé** : l'index du setup publié dans le JSON était un index **relatif à la fenêtre analysée** (donc trompeur) → il a été **retiré** au profit du seul `age_bars`, qui est meaningless en valeur absolue. Une analyse antérieure fondée sur cet index mesurait n'importe quoi : **ses résultats ont été jetés et recalculés**.

### 3.3 Coûts
* Modèle : aller-retour = 2 × slippage observé (MEXC 0,285 %) + 2 × frais (hypothèses 0,10 % et 0,15 % par côté). Scénarios 0 / 0,57 % / 0,77 % / 0,87 %.
* Le coût s'applique **une seule fois** : le seuil est une propriété du **marché** (quantile causal des mouvements antérieurs, comparé au mouvement **brut**) ; le coût ne sert qu'à exiger une performance **nette** positive. C'est aussi le critère de comparaison (base de taux) qui est calculé avec le **même** masque → aucun double compte.
* **Point de vigilance levé** : une version antérieure appliquait le coût **deux fois** (comparaison au seuil *et* test de positivité), ce qui rendait l'effet des frais illisible. Corrigé (protocole v1.2).

### 3.4 Calcul de l'espérance
* Espérance = moyenne des mouvements **dirigés** (signe du signal) sur les épisodes du sous-ensemble, à l'horizon choisi. Les faux positifs sont le complément exact (pas une définition séparée).
* **Intervalles de confiance** : bootstrap (2 000 à 5 000 ré-échantillonnages) sur les épisodes, plus l'intervalle de Wilson sur les taux.
* **Biais de survivance** : **aucun**. Les épisodes sont tous comptés, y compris ceux sans direction ou sans suite ; les non évaluables sont comptés à part. L'historique est celui de la paire TEL-USDT continuously listée (aucune sélection de survivants : une seule série, sans aucun choix).

### 3.5 Biais restants
* **Multiplicité** : ~14 conditionnements × 4 segments ont été explorés. Une condition qui ressort positive partout a une probabilité non nulle d'être un artefact. La règle retenue a été **conçue sur un seul segment (IS1)** puis **vérifiée sur deux segments non utilisés** (IS2 et NEW) : c'est ce qui distingue un effet réel d'une sélection.
* **L'OOS n'est plus vierge** : il a été consulté pour comparer les deux moteurs. Toute affirmation nouvelle s'appuie donc sur **NEW** (période vierge collectée pour cette phase) et **IS2** (validation de conception).

---

## 4. CONTEXTE BTC / ETH / TEL-BTC : DISPONIBLE, MAIS SANS VALEUR AJOUTÉE DÉMONTRÉE

### 4.1 Provenance, alignement, disponibilité
| Source | Provenance | Alignement | Disponible au moment du signal ? |
|---|---|---|---|
| `BTC-USDT` 1h | API publique KuCoin, 22 499 bougies clôturées | **identique** à l'axe TEL (mêmes horodatages UTC) | **oui** : on n'utilise que la dernière bougie 1h **clôturée** avant l'instant du signal |
| `ETH-USDT` 1h | idem | identique | oui |
| `TEL-BTC` 1h (paire directe) | idem | identique | oui |

Collecte : 45 requêtes, 6,4 Mo, cache local hors dépôt, 0 trou / 0 doublon. Le ratio `TEL-BTC` existe en paire directe → pas de division à faire.

### 4.2 Valeur prédictive testée (hypothèses rejetées)
| Conditionnement | NEW | IS1 | IS2 | OOS | Verdict |
|---|---|---|---|---|---|
| BTC 24 h en hausse | −0,429 % | −0,597 % | −0,407 % | −0,455 % | négatif partout |
| BTC 24 h en baisse | −0,155 % | +0,091 % | +0,172 % | −0,348 % | **instable** |
| TEL/BTC 24 h en hausse | −0,457 % | −0,342 % | +0,340 % | +0,012 % | **instable** |
| TEL/BTC 24 h en baisse | −0,183 % | −0,241 % | −0,374 % | −0,699 % | négatif partout |
| ETH 24 h en hausse | +0,009 % | −0,685 % | −0,342 % | −0,258 % | **instable** |

**Conclusion sur le contexte** : le contexte BTC/ETH/TEL-BTC **n'améliore pas** la sélection des signaux de retournement de TEL. Il n'est **pas intégré** au détecteur : le bele terrain est réel mais l'intérêt n'est pas démontré.

### 4.3 Liquidité
Le snapshot contient le carnet (100 niveaux, bandes de profondeur) et le coût d'achat réel de 300 USDT (slippage 0,285 % MEXC / 0,185 % KuCoin) → c'est la **source** du modèle de coûts. Mais il n'existe **aucun historique de liquidité** : l'analyse de l'impact de la liquidité sur les pertes n'est **pas réalisable** avec les données disponibles.

---

## 5. CAUSES CONFIRMÉES DES PERTES

| Cause | Preuve | Confiance |
|---|---|---|
| **C1 — Prise de retournement contre une tendance longue** | Espérance par régime (15m, OOS) : tendance **haussière** −0,671 %, tendance **baissière** −0,460 %, **neutre +0,532 %**. Le signe s'inverse avec le régime. Confirmé sur NEW (+0,290 % en neutre) et IS1 (+1,177 %) | **élevée** |
| **C2 — Le signal n'est pas un signal d'entrée mais une observation** | ALERTE_PRÉCOCE : espérance −0,29 % (NEW) et −0,41 % (OOS), **pire que l'entrée aléatoire** (−0,05 % sur OOS) | **élevée** |
| **C3 — La confirmation améliore, l'alerte non** | CONFIRMATION > ALERTE dans les **4** segments (+0,31 ; +0,22 ; +0,63 ; +0,08 point) | **élevée** |
| **C4 — Volume de signaux ingérable** | 12,4 % des bougies 15m déclenchent une alerte (une toutes les 2 h) ; 97,4 % des alertes ne correspondent à aucun retournement de référence | **élevée** |
| **C5 — Les signaux « de continuation » sont les pires** | Movement antérieur déjà dans le sens du signal : NEW −1,030 % (n=142) contre −0,190 % pour les vrais retournements. **Mais le signe s'inverse sur IS1 (+2,564 %)** → cause plausible, **non exploitable** | **moyenne** |
| **C6 — Entrées tardives** | **Hypothèse rejetée** : les entrées tardives (>1 ATR de pré-mouvement) sont **moins mauvaises** (−0,246 %) que les entrées fraîches (−0,445 %) | **rejetée** |

---

## 6. HYPOTHÈSES TESTÉES ET RÉSULTATS

| # | Hypothèse | Résultat | Décision |
|---|---|---|---|
| H1 | Les entrées tardives causent les pertes | **rejetée** (C6) | — |
| H2 | Les continuations déguisées en retournements sont le problème | **instable** (C5) | non retenue |
| H3 | Le contexte BTC/ETH/TEL-BTC ajoute de l'information | **rejetée** (§4.2) | non intégré |
| H4 | Le régime de marché conditionne la qualité | **confirmée** (C1) | **retenue** |
| H5 | Attendre la confirmation est meilleur qu'agir sur l'alerte | **confirmée** (C3), 4/4 segments | **retenue** |
| H6 | Choisir la meilleure combinaison de preuves sur l'historique | **rejetée** : sur IS1 la meilleure combinaison atteint 1,447 mais tombe à 0,748 sur IS2 intacte, tandis qu'une autre monte de 0,813 à 1,400 — **les classements s'inversent** | aucune règle de sélection de famille |
| **H7** | **`CONFIRMATION` + régime 1d 30 j neutre (±5 %)** | **positive et nette dans les 4 segments** | **RETENUE et implémentée** |

### 6.1 Robustesse de H7
| Contrôle | Résultat |
|---|---|
| Bande de regime 5 % vs 8 % | résultats quasi identiques dans les 4 segments (pas de knife-edge) |
| Fenêtre du regime (15/20/30/45/60/90 j) sur IS1 | l'effet apparaît dès **30 j** et reste jusqu'à 90 j (15 et 20 j : aucun effet) → 30 j est le **début d'un plateau**, pas un point isolé |
| Volumes | ne conserve que **2,9 % à 8,5 %** des signaux (réduction de 92 % à 97 %) |
| Régime neutre | occupe **5 % à 20 %** du temps seulement → d'où les petits effectifs |
| Espérance à 72 h | **plus forte** qu'à 24 h dans les 4 segments (NEW +1,49 %, IS1 +6,69 %, IS2 +2,53 %, OOS +0,64 %) |

### 6.2 L'estimation indépendante
Sur les segments **non utilisés pour la conception** (NEW vierge + IS2) :
* n = 85 · espérance brute **+0,983 %** · IC 95 % **[−0,026 ; +1,962]** → **l'intervalle touche 0**
* nette après 0,57 % : **+0,413 %** · 61,2 % de mouvements favorables · pire −8,29 % · meilleur +11,52 % · ratio gain/perte **1,05**

### 6.3 Coût d'équilibre
| Segment | Round trip maximum encore rentable |
|---|---|
| NEW | 0,68 % |
| IS1 | 1,91 % |
| IS2 | 1,80 % |
| OOS | 0,79 % |

Le round trip observé (0,57 %) est **en dessous** du seuil dans les 4 segments, mais la marge est **mince** dans NEW (0,68 %) et OOS (0,79 %) : avec des frais de 0,10 % par côté et un slippage supérieur, l'avantage disparaît.

---

## 7. CORRECTION IMPLÉMENTÉE ET VALIDÉE

**Correction** : le moteur calcule désormais le **régime de marché** (variation relative sur 30 bougies **journalières clôturées** de l'unité 1j) et expose deux champs :
* `regime` : `NEUTRE` | `TENDANCE_HAUSSIERE` | `TENDANCE_BAISSIERE` | `INDETERMINE` (avec la valeur et la fenêtre) ;
* `exploitable` : `true` **uniquement** si le statut est `CONFIRMATION` **et** le régime est `NEUTRE`, avec `exploitable_reason` en clair.

Le statut et les preuves ne sont **pas** supprimés : l'observation reste visible, y compris hors régime neutre. Le niveau n'entre **pas** dans la décision ; il n'est pas non plus un seuil de filtrage caché : c'est un **qualificateur** documenté.

**Validation** : le moteur corrigé reproduit l'espérance validée à **0,0003 point** près sur les 4 segments (NEW +0,682 % · IS1 +1,910 % · IS2 +1,796 % · OOS +0,792 %) — voir `oos_correction_validation.json`. Un test de non-régression vérifie que le moteur ne lit plus `CRITICAL_LEVEL` et que la décision est identique quelle que soit sa valeur.

**Integration au tableau de bord (T37, terminee)** : le panneau affiche le regime (et sa variation en %), l'etat d'exploitabilite et sa raison. Le badge n'est vert que si le signal est reellement exploitable ; une `ALERTE_PRÉCOCE` n'est jamais presentee comme une entree ; les observations non exploitables restent visibles. Un repli propre est affiche si les champs sont absents (rapport d'une version anterieure de l'agent). Controle de bout en bout : `scripts/verify_t37_e2e.py`.

> **Statut de la regle** : c'est une **regle candidate de recherche**. L'esperance nette rapportee est positive, mais **l'intervalle de confiance inclut zero** et **les frais reels ne sont pas confirmes**. Elle n'est presentee ni dans le moteur ni dans le tableau de bord comme une rentabilite etablie.

---

## 8. PISTES D'AMÉLIORATION CLASSÉES PAR PREUVE ET FAISABILITÉ

| Rang | Piste | Preuve | Faisabilité | Verdict |
|---|---|---|---|---|
| **1** | **Qualifier l'exploitabilité** (régime + confirmation) — **fait** | 4/4 segments positifs, net +0,11 à +1,23 % | faite, validée | **à porter au dashboard** (différé) |
| **2** | **Attendre la confirmation** plutôt qu'agir sur l'alerte précoce | 4/4 segments | fait (champ `exploitable`) | **à porter au dashboard** (différé) |
| 3 | Réduire la **densité** d'alertes (12,4 %/bougie) | C4 | simple : n'émettre l'alerte que si une famille indépendante est présente | fait (v2) |
| 4 | Écarter les **continuations** (mouvement antérieur déjà dans le sens) | C5, mais signe instable | simple | **non retenue** (instabilité) |
| 5 | **Contexte BTC/ETH/TEL-BTC** | H3 rejetée |collected | **non intégré** |
| 6 | **Liquidité** (impact, profondeur) | non historisable | impossible sans données | **abandonnée** |
| 7 | Élargir la fenêtre de rendement (72 h) | l'effet croît à 72 h | simple : le signal est lent | **à tester** (non fait : le 72 h est déjà rapporté) |
| 8 | Modèle de coût réel (frais vérifiés) | les frais ne sont pas vérifiés | dépend de l'échange | **à faire avec le mainteneur** |

---

## 9. LIMITES

* L'intervalle de confiance de l'estimation indépendante **touche 0** : l'effet est **statistiquement fragile**.
* La marge au-dessus des coûts est **mince** dans deux segments sur quatre.
* Une seule paire, un seul régime de marché dominant, ~2,5 ans d'historique 15m.
* Les frais de transaction ne sont **pas vérifiés** (hypothèses).
* L'**OOS n'est plus vierge** : il a servi à comparer les deux moteurs. Les affirmations nouvelles reposent sur **NEW** (vierge) et **IS2**.
* Le **1w** est inexploitable (58 semaines manquantes, ancrage divergent KuCoin/MEXC) et le **1M** non exploitable (89 bougies).
* La liquidité n'est pas historisable.

---

## 10. CE QUI N'A PAS ÉTÉ FAIT (volontairement)

* **Aucun réglage de seuil pour améliorer un taux.** Le protocole des coûts a été corrigé (double compte) et le split figé sur des dates absolues ; **aucun seuil de détection n'a été modifié** après lecture des résultats.
* **Aucun changement de dashboard, de workflow ou de publication** (consigne).
* **Aucune opération Git destructive.**
* **Aucun trade réel.**

---

*Ce rapport décrit une **première** configuration dont l'espérance est positive et validée hors échantillon sur une période vierge, avec un intervalle de confiance qui touche zéro et une marge slender sur les coûts. Ce n'est pas une preuve de rentabilité, et cela ne constitue pas une autorisation de trader.*

---

## 11. CONFORMITÉ À LA CHECKLIST OBLIGATOIRE (ajoutée par `origin` le 21/10)

`docs/ANALYSE_TECHNIQUE_TEL_CHECKLIST.md` est entrée dans la branche par le fast-forward du 21/10
(commit `31723a9`). Elle fixe des exigences de méthode. Point de conformité, tel que le moteur
v2 se tient aujourd'hui :

| Exigence de la checklist | État du moteur v2 | Emplacement |
|---|---|---|
| Ne pas fonder un verdict sur le RSI seul | **Respecté** — le RSI est un membre de famille de preuves parmi d'autres ; la décision vient de la convergence | `src/agent_analysis.py`, familles de preuves |
| Distinguer **ALERTE PRÉCOCE** / **CONFIRMATION** / **INVALIDATION** | **Respecté** — trois états distincts ; l'alerte précoce n'est jamais présentée comme une entrée | `setup` / `confirmation` / `invalidation` |
| Ne pas attendre l'alignement complet des indicateurs | **Respecté** — l'alerte précoce est émise sur premiers indices crédibles | panneau T37, avertissement « alerte précoce ≠ entrée » |
| Expliciter indices présents / indices manquants / risque de faux signal | **Respecté** — champs de contexte et motif d'invalidation | `early_reversal` |
| Multi-unités 15m / 1h / 4h / 1d / 1w / 1M | **Couverture computationnelle complète** : `TIMEFRAMES = ("15m","1h","4h","1d","1w","1M")`. **Limite assumée** : `1w` inexploitable (58 semaines manquantes) et `1M` non exploitable (89 bougies) | `TIMEFRAMES`, §9 ci-dessus |
| Contexte externe BTC / ETH | **NON INTÉGRÉ** — voir ci-dessous | §4 (contexte collecté, sans valeur prédictive démontrée) |
| Ne pas modifier seuils / scripts / alertes sans autorisation | **Respecté** — aucun seuil n'a été modifié ; les seuls changements apportés au dépôt sont le moteur (v2), le panneau T37 et la documentation | `OOS_PROTOCOL.md`, `TASKS.md` |
| Aucun ordre exécuté, fail-closed si données insuffisantes | **Respecté** — aucune exécution d'ordre ; statut `ATTENDRE` sur données absentes ou périmées | `src/agent_analysis.py` |

### 11.1 Écart assumé : le contexte BTC / ETH

La checklist demande d'examiner le **contexte externe BTC et ETH**. Ces séries **ont été collectées
et alignées** (22 499 bougies 1h chacune, provenance et alignement vérifiés), mais **elles ne sont pas
intégrées au moteur** : les hypothèses de valeur prédictive correspondantes ont été **testées et rejetées**
(§4.2). L'intégration **exigerait un nouvel arbitrage** : soit réintroduire des variables sans valeur
démontrée, soit laisser la checklist en écart assumé et documenté. **Aucune des deux n'a été décidée
ici** : l'écart est consigné, et la décision revient au mainteneur.

### 11.2 Ce que la checklist ne change pas au statut du travail

La conformité méthodologique ne déplace pas le statut : la règle reste une **règle de recherche —
observation qualifiée**. L'espérance nette est positive et reproductible hors échantillon, mais
**l'intervalle de confiance inclut zéro** et **les frais réels ne sont pas confirmés** (§1, §9).
