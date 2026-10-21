# PROPOSITION D'ARCHITECTURE — DÉTECTION PRÉCOCE DE RETOURNEMENT

> ⚠️ **Document de conception (21/10/2026), en partie dépassé.** Il décrit l'état
> *antérieur* du moteur. Ce qui a été effectivement implémenté et mesuré depuis :
>
> * `CONFIRMATION` **est** désormais attribué (moteur v2, machine à états reconstruite
>   depuis l'historique, sans état porté entre les appels) ;
> * les figures de bougies **sont** branchées (OHLC transmis et aligné) ;
> * `1h`, `1w` et `1M` **sont** utilisés ; le `1M` est déclaré non exploitable quand son
>   historique est insuffisant ;
> * le niveau fixe `0.001526` **a quitté** le chemin de décision (invalidation structurelle
>   sur l'ancre du setup) ; il subsiste comme simple observation de risque ;
> * `confidence` est un score de convergence, explicitement **ni une probabilité ni calibré**.
>
> **Résultat de l'évaluation hors échantillon (`OOS_RAPPORT.md`) : aucun des deux moteurs
> ne démontre de pouvoir prédictif.** Aucune règle n'a été réglée sur l'historique : la
> meilleure combinaison sur la zone de conception s'effondre sur la zone de validation.
>
> Documents de référence : `OOS_RAPPORT.md` (définitif), `OOS_PROTOCOL.md` (protocole figé),
> `DETECTEUR_V2_RAPPORT.md` (conception du moteur v2), `TASKS.md` (état du projet).


**Date**: 21 octobre 2026  
**Statut**: IMPLÉMENTÉ (Tâche 3)  
**Fichier concerné**: `src/agent_analysis.py`  
**Objectif**: Ajouter des statuts de signal distincts pour détecter les retournements précoces

---

## A. RÈGLES DE DÉCISION ACTUELLES

### Statuts existants

- **SURVEILLER**: Tous les contrôles OK, surveillance normale
- **ATTENDRE**: Données insuffisantes ou invalides (fail-closed)
- **PARTIEL**: Historique mensuel partiel (timeframe 1M)
- **UNAVAILABLE**: Timeframe spécifique indisponible
- **ATTENTION**: Bougie trop ancienne

### Règles de tendance (par timeframe)

```python
# Dans analyze_timeframe()
if e50 is not None and close > e20 > e50 and hist_now is not None and hist_now > 0:
    trend = "HAUSSIER"
elif e50 is not None and close < e20 < e50 and hist_now is not None and hist_now < 0:
    trend = "BAISSIER"
else:
    trend = "MIXTE" if e50 is not None else "INDETERMINE"
```

### Flags descriptifs actuels

- `RSI_SURVENDU_NE_CONFIRME_PAS_UN_REBOND`: RSI < 30
- `RSI_EN_HAUSSE_SUR_LES_DERNIERES_CLOTURES`: RSI en hausse sur 4 dernières bougies
- `TROIS_CLOTURES_EN_HAUSSE`: 3 clôtures consécutives en hausse
- `REPRISE_AVEC_VOLUME_SUPERIEUR_A_1_5X`: Volume ≥ 1.5x moyenne + 3 clôtures en hausse
- `HISTOGRAMME_MACD_EN_AMELIORATION`: MACD histogram en amélioration
- `NIVEAU_CRITIQUE_0_001526_CLOTURE_SOUS_NIVEAU_*`: Prix sous niveau critique

### Alignement multi-timeframe

```python
# Dans build_analysis()
long_trends = [timeframes[tf]["trend"] for tf in ("4h", "1d", "1w") if timeframes[tf]["status"] == "OK"]
if timeframes["1M"]["status"] == "OK":
    long_trends.append(timeframes["1M"]["trend"])

if len(long_trends) < 3:
    alignment = "INDETERMINE"
elif all(trend == "HAUSSIER" for trend in long_trends):
    alignment = "HAUSSIER_ALIGNE"
elif all(trend == "BAISSIER" for trend in long_trends):
    alignment = "BAISSIER_ALIGNE"
else:
    alignment = "MIXTE"
```

### Niveau critique

- **Niveau**: 0.001526 USDT
- **Comportement**: Signalé comme risque (flag), jamais comme signal d'achat
- **Timeframes**: 15m, 1h, 4h

---

## B. PROPOSITION D'ARCHITECTURE

### Nouveaux statuts proposés

#### 1. ALERTE_PRÉCOCE

**Définition**: Premiers signes crédibles de retournement, encore non confirmés

**Critères (conjonction de plusieurs preuves distinctes)**:

- Au moins 2 preuves parmi les catégories suivantes (maximum 1 par catégorie):
  - **Structure des prix**:
    - Divergence prix vs indicateur (ex: prix fait plus bas mais RSI fait plus haut)
    - Pattern de retournement sur 15m/1h (double bottom, hammer, engulfing)
  - **Momentum**:
    - Momentum croissant après baisse prolongé
    - Stochastique %K croise %D à la hausse depuis zone survendue (< 20)
  - **Volume**:
    - Volume anormalement élevé sur bougie de retournement potentiel
    - Accumulation sur plusieurs bougies (volume > moyenne)
  - **Réaction à niveau**:
    - Rejet d'un niveau de support (wicks longs en bas)
    - Test et rejet du niveau critique 0.001526
  - **Contexte unités supérieures**:
    - Alignement haussier sur 4h/1d alors que 15m est baissier (divergence temporelle)
    - ADX faible (< 20) sur unités supérieures (trend faible, retournement possible)

**Exemples de combinaisons valides**:

- Divergence RSI + Stochastique croisant à la hausse
- Rejet niveau support + Volume élevé
- Momentum croissant + Alignement haussier 4h/1d
- Pattern hammer + Stochastique survendu

**Exemples de combinaisons INVALIDES (corrélées)**:

- RSI survendu + Stochastique survendu (même catégorie momentum)
- EMA croisant + MACD histogram positif (tous deux trend)
- 3 clôtures en hausse + Volume élevé (tous deux momentum/volume)

**Seuils proposés (à valider historiquement)**:

- RSI survendu: < 30 (existant)
- Stochastique survendu: %K < 20
- Divergence: Δ prix > 1% sur 5 bougies, Δ RSI > 10 dans direction opposée
- Volume élevé: > 2x moyenne 20 périodes
- ADX faible: < 20
- Rejet niveau: wick bas > 50% du corps de la bougie

#### 2. CONFIRMATION

**Définition**: Convergence suffisante des preuves indépendantes

**Critères**:

- ALERTE_PRÉCOCE précédente toujours active
- Ajout d'au moins 1 preuve supplémentaire d'une catégorie différente
- OU renforcement des preuves existantes (ex: divergence RSI confirmée par divergence MACD)
- Alignement multi-timeframe cohérent (4h/1d dans même direction que signal 15m)

**Exemples**:

- ALERTE_PRÉCOCE (divergence RSI) + Stochastique croise %D à la hausse
- ALERTE_PRÉCOCE (rejet support) + Momentum croissant + Alignement 4h haussier

#### 3. INVALIDATION

**Définition**: Structure ou niveau critique invalidé

**Critères**:

- Prix clôture sous niveau critique 0.001526 sur 15m ET 1h ET 4h
- OU structure de tendance clairement brisée (ex: cassure support majeur)
- OU divergence temporelle inverse (15m haussier mais 4h/1d baissier sans signe de retournement)

#### 4. ATTENDRE

**Définition**: Signal insuffisant ou contradictoire

**Critères**:

- Données insuffisantes (existant)
- OU signaux contradictoires entre timeframes sans convergence
- OU absence de preuves suffisantes (moins de 2 catégories)

#### 5. DONNÉES_INSUFFISANTES

**Définition**: Données trop anciennes, incomplètes ou incohérentes

**Critères**:

- Snapshot périmé (> 20 min)
- OU timeframe requis indisponible
- OU historique insuffisant pour indicateurs clés

---

## C. IMPLÉMENTATION PROPOSÉE

### Nouvelle fonction: `detect_early_reversal()`

```python
def detect_early_reversal(timeframes: dict[str, Any]) -> dict[str, Any]:
    """
    Détecte les signaux précoces de retournement.
    Retourne un dictionnaire avec:
    - signal_status: ALERTE_PRÉCOCE | CONFIRMATION | INVALIDATION | ATTENDRE | DONNÉES_INSUFFISANTES
    - evidence: liste des preuves trouvées avec catégories
    - confidence: score de confiance (0-100)
    """
    evidence = []
    categories = set()

    tf_15m = timeframes.get("15m", {})
    tf_1h = timeframes.get("1h", {})
    tf_4h = timeframes.get("4h", {})

    # Vérifier disponibilité des données
    if tf_15m.get("status") != "OK":
        return {"signal_status": "DONNÉES_INSUFFISANTES", "evidence": [], "confidence": 0}

    # Catégorie: Structure des prix
    if has_rsi_divergence(tf_15m):
        evidence.append({"category": "structure", "type": "rsi_divergence"})
        categories.add("structure")

    if has_reversal_pattern(tf_15m):
        evidence.append({"category": "structure", "type": "reversal_pattern"})
        categories.add("structure")

    # Catégorie: Momentum
    if tf_15m.get("rsi14", 50) < 30:
        evidence.append({"category": "momentum", "type": "rsi_oversold"})
        categories.add("momentum")

    stoch_k = tf_15m.get("stoch_k")
    stoch_d = tf_15m.get("stoch_d")
    if stoch_k is not None and stoch_d is not None and stoch_k < 20 and stoch_k > stoch_d:
        evidence.append({"category": "momentum", "type": "stochastic_crossover"})
        categories.add("momentum")

    if tf_15m.get("momentum10", 0) > 0 and is_downtrend_ending(tf_15m):
        evidence.append({"category": "momentum", "type": "momentum_rising"})
        categories.add("momentum")

    # Catégorie: Volume
    vol_ratio = tf_15m.get("volume_ratio_20")
    if vol_ratio is not None and vol_ratio >= 2.0:
        evidence.append({"category": "volume", "type": "high_volume"})
        categories.add("volume")

    # Catégorie: Réaction à niveau
    if has_level_rejection(tf_15m, CRITICAL_LEVEL):
        evidence.append({"category": "level", "type": "critical_rejection"})
        categories.add("level")

    # Catégorie: Contexte unités supérieures
    if tf_4h.get("adx14", 0) < 20 and tf_15m.get("trend") != tf_4h.get("trend"):
        evidence.append({"category": "context", "type": "weak_trend_divergence"})
        categories.add("context")

    # Déterminer le statut
    if len(categories) >= 2:
        # Au moins 2 catégories distinctes
        signal_status = "ALERTE_PRÉCOCE"
        confidence = min(100, len(evidence) * 20 + 30)  # Base 30, +20 par preuve
    elif len(evidence) >= 1:
        signal_status = "ATTENDRE"
        confidence = min(50, len(evidence) * 15)
    else:
        signal_status = "ATTENDRE"
        confidence = 0

    # Vérifier invalidation
    if is_invalidated(timeframes):
        signal_status = "INVALIDATION"
        confidence = 90

    return {
        "signal_status": signal_status,
        "evidence": evidence,
        "confidence": confidence,
        "categories": list(categories)
    }
```

### Fonctions auxiliaires proposées

```python
def has_rsi_divergence(tf: dict[str, Any]) -> bool:
    """Détecte divergence RSI vs prix."""
    # Implémentation: comparer direction prix sur 5 bougies vs direction RSI
    pass

def has_reversal_pattern(tf: dict[str, Any]) -> bool:
    """Détecte patterns de chandelier de retournement."""
    # Implémentation: hammer, engulfing, doji, etc.
    pass

def is_downtrend_ending(tf: dict[str, Any]) -> bool:
    """Vérifie si une tendance baissière se termine."""
    # Implémentation: série de baisses suivie de hausse
    pass

def has_level_rejection(tf: dict[str, Any], level: float) -> bool:
    """Vérifie rejet d'un niveau (wick long)."""
    # Implémentation: wick bas > 50% corps, prix proche niveau
    pass

def is_invalidated(timeframes: dict[str, Any]) -> bool:
    """Vérifie invalidation du signal."""
    # Prix sous niveau critique sur 15m/1h/4h
    critical_timeframes = ("15m", "1h", "4h")
    below_critical = [
        tf for tf in critical_timeframes
        if timeframes[tf].get("status") == "OK"
        and timeframes[tf].get("close", float('inf')) < CRITICAL_LEVEL
    ]
    return len(below_critical) >= 2
```

### Intégration dans build_analysis()

```python
def build_analysis(snapshot: Any, expected_collection_id: str | None = None, now: datetime | None = None) -> dict[str, Any]:
    # ... code existant ...

    # Ajouter détection précoce
    early_reversal = detect_early_reversal(timeframes)

    # Intégrer dans le résultat
    result = {
        # ... champs existants ...
        "early_reversal": early_reversal,
        "signal_status": early_reversal["signal_status"],
    }

    return result
```

---

## D. TESTS NÉCESSAIRES

### Tests unitaires pour detect_early_reversal()

1. **test_alerte_precoce_with_divergence_and_stochastic**: Divergence RSI + Stochastique crossover
2. **test_alerte_precoce_with_rejection_and_volume**: Rejet niveau + Volume élevé
3. **test_attendre_with_single_evidence**: Une seule preuve → ATTENDRE
4. **test_attendre_with_correlated_evidence**: RSI survendu + Stochastique survendu → ATTENDRE (même catégorie)
5. **test_invalidation_below_critical**: Prix sous niveau critique → INVALIDATION
6. **test_confirmation_with_additional_evidence**: ALERTE_PRÉCOCE + preuve supplémentaire → CONFIRMATION
7. **test_donnees_insuffisantes_missing_timeframe**: Timeframe manquant → DONNÉES_INSUFFISANTES

### Tests d'intégration

1. **test_early_reversal_in_json_output**: Vérifier sérialisation JSON
2. **test_early_reversal_does_not_break_existing**: Tests existants toujours passent
3. **test_early_reversal_fail_closed**: Mode fail-closed préservé

---

## E. LIMITATIONS ET PRÉCAUTIONS

### Limites actuelles

- **Pas de backtest historique**: Les seuils proposés doivent être validés sur données historiques
- **Dépendance aux indicateurs existants**: La qualité dépend de la précision des indicateurs de base
- **Complexité accrue**: Plus de logique à maintenir et tester

### Précautions

- **Ne pas changer les décisions de production**: Implémenter d'abord en mode observation seule
- **Logging détaillé**: Tracer toutes les décisions pour audit postérieur
- **Seuils conservateurs**: Commencer avec des seuils conservateurs, ajuster après validation
- **Aucun ordre automatique**: Toujours en mode read-only, surveillance uniquement

---

## F. IMPLÉMENTATION RÉALISÉE (Tâche 3 - 21 octobre 2026)

### Fonctions implémentées

- `has_rsi_divergence()`: Divergence haussière RSI vs prix
- `has_bearish_divergence()`: Divergence baissière RSI vs prix
- `has_hammer_pattern()`: Pattern hammer (défini, non utilisé)
- `has_engulfing_bullish()`: Pattern engulfing (défini, non utilisé)
- `is_momentum_improving()`: Momentum en amélioration
- `is_macd_improving()`: MACD histogram en amélioration
- `has_level_rejection()`: Rejet de niveau (défini, non utilisé)
- `is_downtrend_ending()`: Fin de tendance baissière
- `is_uptrend_ending()`: Fin de tendance haussière
- `detect_early_reversal()`: Fonction principale avec logique de catégories

### Intégration

- Intégré dans `build_analysis()` en mode observation
- Champ `early_reversal` ajouté au rapport JSON
- Pas de modification du statut principal ou des décisions

### Tests ajoutés

- 10 tests dans `EarlyReversalTests` couvrant tous les scénarios demandés
- Total tests Python: 95 (92 OK, 3 skipped)

### Limites de l'implémentation

- **CONFIRMATION non implémenté**: Nécessiterait mémorisation état précédent
- **Patterns chandelier**: Fonctions définies mais non utilisées (nécessitent OHLC brut)
- **Validation historique**: Non réalisée (nécessite script dédié)
- **Seuils**: Non calibrés sur données historiques

---

## G. PROCHAINES ÉTAPES RECOMMANDÉES

1. Implémenter script de validation historique sans fuite temporelle
2. Calibrer les seuils sur données historiques réelles
3. Implémenter la logique CONFIRMATION avec mémorisation d'état
4. Intégrer les patterns de chandelier (accès OHLC brut)
5. Une fois validé, considérer utilisation du signal_status pour influencer le statut principal

---

**Document mis à jour le 21 octobre 2026 - Implémentation terminée**
