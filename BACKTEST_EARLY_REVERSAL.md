# RAPPORT DE BACKTEST — DÉTECTEUR DE RETOURNEMENT PRÉCOCE

**Date**: 21 octobre 2026  
**Script**: `scripts/backtest_early_reversal.py`  
**Données**: `site/tel_snapshot.json`  
**Objectif**: Évaluer les performances réelles du détecteur sur données historiques

---

## 1. DONNÉS HISTORIQUES UTILISÉES

### Caractéristiques
- **Source**: Snapshot MEXC du 19 octobre 2026
- **Timeframes disponibles**: 15m, 1h, 4h, 1d, 1w, 1M
- **Nombre de bougies par timeframe**: 300 pour chaque timeframe
- **Période 15m**: 2026-10-16T14:00:00.000Z à 2026-10-19T16:45:00.000Z (3.1 jours)
- **Période 1h**: 2026-10-07T05:00:00.000Z à 2026-10-19T16:00:00.000Z (12.5 jours)
- **Période 4h**: 2026-08-30T16:00:00.000Z à 2026-10-19T12:00:00.000Z (50 jours)
- **Période 1d**: 2025-12-23T00:00:00.000Z à 2026-10-18T00:00:00.000Z (300 jours)

### Qualité des données
- **Doublons**: Non détectés
- **Trous**: Non détectés
- **Valeurs invalides**: Non détectées
- **Bougies incomplètes**: Non détectées
- **Origine**: Exchange MEXC via collecteur public

---

## 2. MÉTHODOLOGIE DE BACKTEST

### Critères de mouvement significatif (définis avant analyse)
Un mouvement est considéré significatif s'il satisfait au moins la moitié des critères disponibles:
- **+2% sur 3 bougies**
- **+3% sur 6 bougies**
- **+5% sur 12 bougies**
- **+7% sur 24 bougies**

### Définition de faux positif
Un signal est considéré comme faux positif si:
- Le mouvement est < 1% sur tous les horizons disponibles, OU
- Il y a une baisse sur au moins un horizon

### Prévention des fuites de données futures
- Les indicateurs sont recalculés à chaque index en utilisant uniquement les données disponibles
- Le backtest commence à l'index 50 pour avoir assez d'historique pour SMA50
- Les séries temporelles sont tronquées à l'index courant
- Les mouvements futurs sont mesurés uniquement après l'émission du signal

### Limitations de l'implémentation
- **Synchronisation multi-timeframe**: Simplifiée - les indicateurs des timeframes supérieurs utilisent les mêmes valeurs que le timeframe cible (statut PARTIEL)
- **Volume ratio**: Calculé sur 20 périodes
- **Tendance**: Déterminée par SMA20 vs SMA50
- **Indicateurs calculés**: RSI14, MACD histogram, Stochastic %K/%D, Momentum10, ADX14, volume ratio

---

## 3. RÉSULTATS PAR TIMEFRAME

### Timeframe 15m
- **Signaux ALERTE_PRÉCOCE**: 24
- **Signaux évaluables**: 22
- **Signaux non évaluables**: 2 (données insuffisantes en fin de période)
- **Mouvements significatifs**: 0
- **Faux positifs**: 22
- **Taux de réussite**: 0.0%
- **Taux de faux positifs**: 100.0%

### Timeframe 1h
- **Signaux ALERTE_PRÉCOCE**: 0
- **Signaux évaluables**: 0
- **Mouvements significatifs**: 0
- **Faux positifs**: 0

### Timeframe 4h
- **Signaux ALERTE_PRÉCOCE**: 0
- **Signaux évaluables**: 0
- **Mouvements significatifs**: 0
- **Faux positifs**: 0

### Timeframe 1d
- **Signaux ALERTE_PRÉCOCE**: 0
- **Signaux évaluables**: 0
- **Mouvements significatifs**: 0
- **Faux positifs**: 0

---

## 4. RÉSUMÉ GLOBAL

- **Total signaux (tous timeframes)**: 24
- **Total évaluables**: 22
- **Total non évaluables**: 2
- **Total mouvements significatifs**: 0
- **Total faux positifs**: 22
- **Taux de réussite global**: 0.0%
- **Taux de faux positifs global**: 100.0%

---

## 5. ANALYSE DES SIGNAUX (15m)

### Distribution des directions
- **Signaux haussiers**: 12
- **Signaux baissiers**: 12

### Catégories de preuves observées
- **Momentum (MACD histogram)**: 24/24 signaux
- **Volume (moderate/high increase)**: 16/24 signaux
- **Structure (RSI divergence)**: 8/24 signaux

### Exemples de signaux et leurs résultats

#### Signal 1 (Index 70)
- **Timestamp**: 2026-10-17T07:30:00.000Z
- **Prix**: 0.001699
- **Direction**: BAISSIER
- **Preuves**: MACD histogram worsening + moderate volume increase (1.78x)
- **Confidence**: 60
- **Mouvements futurs**: +0.41% (3c), -0.24% (6c), -0.41% (12c), -0.53% (24c)
- **Résultat**: FAUX POSITIF (baisse sur horizons 6, 12, 24)

#### Signal 2 (Index 120)
- **Timestamp**: 2026-10-17T20:00:00.000Z
- **Prix**: 0.001667
- **Direction**: HAUSSIER
- **Preuves**: Bullish RSI divergence + MACD histogram improving
- **Confidence**: 60
- **Mouvements futurs**: -0.66% (3c), -2.64% (6c), -2.04% (12c), -3.36% (24c)
- **Résultat**: FAUX POSITIF (baisse sur tous horizons)

#### Signal 3 (Index 126)
- **Timestamp**: 2026-10-17T21:30:00.000Z
- **Prix**: 0.001623
- **Direction**: BAISSIER
- **Preuves**: MACD histogram worsening + high volume spike (2.13x)
- **Confidence**: 60
- **Mouvements futurs**: +0.62% (3c), +0.62% (6c), -0.25% (12c), -0.86% (24c)
- **Résultat**: FAUX POSITIF (baisse sur horizons 12, 24)

---

## 6. DIAGNOSTIC DES PROBLÈMES

### Problème principal: Taux de faux positifs de 100%
Le détecteur génère des signaux ALERTE_PRÉCOCE mais aucun ne correspond à un mouvement haussier significatif sur les horizons mesurés.

### Causes probables

#### 1. Critères de mouvement trop stricts
Les critères définis (+2%, +3%, +5%, +7%) peuvent être trop élevés pour la volatilité actuelle de TEL/USDT.

#### 2. Période de test trop courte
3.1 jours de données 15m (300 bougies) sont insuffisants pour capturer des retournements significatifs. La période correspond à une tendance baissière générale (prix de 0.001792 à 0.001524).

#### 3. Simplification multi-timeframe
L'utilisation des indicateurs du timeframe cible pour tous les timeframes (statut PARTIEL) réduit la qualité des signaux de contexte multi-timeframe.

#### 4. Seuils de détection non calibrés
Les seuils actuels (RSI < 30, volume > 2x, etc.) ne sont pas calibrés sur les données historiques réelles.

#### 5. Absence de mouvements haussiers significatifs
La période testée (16-19 octobre 2026) correspond à une tendance baissière continue. Il est possible qu'il n'y ait eu aucun retournement haussier significatif à détecter.

---

## 7. LIMITES DE L'ÉVALUATION

### Données
- **Période courte**: 3.1 jours pour 15m, insuffisant pour évaluer la performance
- **Tendance unidirectionnelle**: Période de baisse continue, pas de retournements
- **Volume de données**: 300 bougies par timeframe, limite la profondeur d'analyse

### Méthodologie
- **Synchronisation timeframe**: Simplifiée, impact sur qualité des signaux de contexte
- **Critères de mouvement**: Non ajustés à la volatilité spécifique de TEL/USDT
- **Absence de benchmark**: Pas de comparaison avec une stratégie naïve

### Implémentation
- **CONFIRMATION non implémenté**: Impossible de mesurer les confirmations de signaux
- **Patterns chandelier**: Non utilisés dans la détection actuelle

---

## 8. CONCLUSIONS

### Faits mesurés
- Le détecteur a généré 24 signaux ALERTE_PRÉCOCE sur 3.1 jours de données 15m
- Aucun de ces signaux n'a été suivi d'un mouvement haussier significatif selon les critères définis
- Le taux de faux positifs est de 100% sur la période testée
- Aucun signal n'a été généré sur les timeframes 1h, 4h, 1d

### Interprétation
**Le détecteur dans son état actuel ne fonctionne pas correctement sur les données historiques testées.** Les signaux générés ne prédisent pas les mouvements haussiers significatifs.

### Recommandations

#### Immédiates
1. **Ne pas utiliser le détecteur en production** dans son état actuel
2. **Étendre la période de test** à plusieurs mois pour capturer différents régimes de marché
3. **Ajuster les critères de mouvement** à la volatilité réelle de TEL/USDT
4. **Implémenter la synchronisation multi-timeframe correcte**

#### À moyen terme
1. **Calibrer les seuils** sur un historique plus long
2. **Ajouter la logique CONFIRMATION** pour valider les signaux
3. **Intégrer les patterns de chandelier** pour améliorer la détection
4. **Comparer avec un benchmark** (ex: croisement EMA, RSI survendu seul)

#### À long terme
1. **Validation sur plusieurs années de données**
2. **Tests de robustesse** sur différents régimes de marché
3. **Optimisation des seuils** par apprentissage automatique
4. **Intégration dans le système de décision** uniquement après validation réussie

---

## 9. FICHIERS CRÉÉS

- `scripts/backtest_early_reversal.py`: Script de backtest
- `backtest_results.json`: Résultats détaillés des signaux
- `BACKTEST_EARLY_REVERSAL.md`: Ce rapport

---

## 10. VÉRIFICATIONS

### Absence de fuite de données futures
- ✅ Les indicateurs sont recalculés à chaque index avec uniquement les données disponibles
- ✅ Les séries sont tronquées à l'index courant
- ✅ Les mouvements futurs sont mesurés après l'émission du signal

### Données d'entrée non modifiées
- ✅ Le fichier `site/tel_snapshot.json` n'a pas été modifié
- ✅ Le détecteur `detect_early_reversal()` n'a pas été modifié
- ✅ Les seuils du détecteur n'ont pas été ajustés

### Tests exécutés
- ✅ Script de backtest exécuté avec succès
- ✅ Résultats sauvegardés en JSON
- ✅ Aucune erreur d'exécution

---

**Rapport rédigé le 21 octobre 2026**
**Conclusion: Le détecteur nécessite une révision majeure avant toute utilisation en production.**
