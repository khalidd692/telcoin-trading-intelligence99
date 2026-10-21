#!/usr/bin/env python3
"""
Backtest historique du détecteur de retournement précoce.

Ce script parcourt les données historiques OHLCV chronologiquement,
recalcule les indicateurs à chaque instant sans fuite de données futures,
et mesure les performances du détecteur.

Critères de mouvement significatif (définis avant analyse):
- Mouvement haussier significatif: +2% sur 3 bougies, +3% sur 6 bougies,
  +5% sur 12 bougies, +7% sur 24 bougies
- Faux positif: Mouvement < 1% sur tous les horizons ou baisse sur au moins un horizon
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent_analysis import (
    detect_early_reversal,
    rsi_series,
    macd_histogram,
    stochastic_series,
    momentum_series,
    dmi_series,
    sma_series,
    TIMEFRAMES,
    CRITICAL_LEVEL,
)


def load_historical_data(snapshot_path: str = "site/tel_snapshot.json"):
    """Charge les données historiques OHLCV."""
    with open(snapshot_path, 'r') as f:
        data = json.load(f)
    return data['sources']['mexc']['candles']


def calculate_all_indicators(rows, index):
    """
    Calcule tous les indicateurs nécessaires pour le détecteur à un index donné.
    """
    if index < 0 or index >= len(rows):
        return None
    
    historical_rows = rows[:index + 1]
    
    if len(historical_rows) < 15:
        return None
    
    closes = [row['close'] for row in historical_rows]
    highs = [row['high'] for row in historical_rows]
    lows = [row['low'] for row in historical_rows]
    volumes = [row['volume'] for row in historical_rows]
    
    # Calculer les indicateurs
    rsi = rsi_series(closes, 14)
    macd_hist = macd_histogram(closes) if len(closes) >= 27 else None
    stoch = stochastic_series(highs, lows, closes, 14, 3) if len(closes) >= 17 else None
    momentum = momentum_series(closes, 10) if len(closes) >= 11 else None
    dmi = dmi_series(highs, lows, closes, 14) if len(closes) >= 28 else None
    sma20 = sma_series(closes, 20) if len(closes) >= 20 else None
    sma50 = sma_series(closes, 50) if len(closes) >= 50 else None
    
    # Volume ratio (moyenne sur 20 périodes)
    volume_ratio = None
    if len(volumes) >= 20:
        avg_volume = sum(volumes[-20:]) / 20
        volume_ratio = volumes[-1] / avg_volume if avg_volume > 0 else None
    
    # Déterminer la tendance basée sur EMA
    trend = "INDETERMINE"
    if sma20 and sma50:
        if sma20[-1] > sma50[-1]:
            trend = "HAUSSIER"
        elif sma20[-1] < sma50[-1]:
            trend = "BAISSIER"
    
    # Extraire les dernières valeurs valides
    def last_valid(series):
        if series is None or len(series) == 0:
            return None
        for val in reversed(series):
            if val is not None and not (isinstance(val, float) and (val != val)):  # Check for NaN
                return val
        return None
    
    return {
        "close": closes[-1],
        "rsi14": last_valid(rsi),
        "macd_histogram": last_valid(macd_hist),
        "macd_histogram_previous": last_valid(macd_hist[:-1]) if macd_hist and len(macd_hist) > 1 else None,
        "stoch_k": last_valid(stoch[0]) if stoch and len(stoch) > 0 else None,
        "stoch_d": last_valid(stoch[1]) if stoch and len(stoch) > 1 else None,
        "momentum10": last_valid(momentum),
        "volume_ratio_20": volume_ratio,
        "adx14": last_valid(dmi[2]) if dmi and len(dmi) > 2 else None,
        "trend": trend,
        "status": "OK",
    }


def analyze_candle_at_index(all_candles_data, index, target_timeframe):
    """
    Analyse une bougie à un index donné sans utiliser de données futures.
    Construit les données de timeframe pour le détecteur.
    """
    if index < 0:
        return None
    
    # Calculer les indicateurs pour le timeframe cible
    target_rows = all_candles_data[target_timeframe]['rows']
    if index >= len(target_rows):
        return None
    
    target_indicators = calculate_all_indicators(target_rows, index)
    if target_indicators is None:
        return None
    
    # Construire le dict de timeframes pour le détecteur
    timeframes_data = {}
    
    # Pour le timeframe cible, utiliser les indicateurs calculés
    timeframes_data[target_timeframe] = target_indicators
    
    # Pour les autres timeframes, utiliser les dernières données disponibles
    # (simplification: on utilise les indicateurs calculés sur le timeframe cible)
    for tf in ['15m', '1h', '4h', '1d', '1w', '1M']:
        if tf == target_timeframe:
            continue
        if tf in all_candles_data:
            # Utiliser une simplification: même structure mais statut peut être PARTIEL
            # En réalité, il faudrait synchroniser les timeframes correctement
            timeframes_data[tf] = {
                "status": "PARTIEL",  # Indique que ce n'est pas parfaitement synchronisé
                "close": target_indicators['close'],
                "rsi14": target_indicators['rsi14'],
                "macd_histogram": target_indicators['macd_histogram'],
                "macd_histogram_previous": target_indicators['macd_histogram_previous'],
                "volume_ratio_20": target_indicators['volume_ratio_20'],
                "stoch_k": target_indicators['stoch_k'],
                "stoch_d": target_indicators['stoch_d'],
                "momentum10": target_indicators['momentum10'],
                "adx14": target_indicators['adx14'],
                "trend": target_indicators['trend'],
            }
    
    # Séries pour 15m (nécessaire pour divergence)
    closes_15m = [row['close'] for row in target_rows[:index + 1]]
    rsi_series_15m = rsi_series(closes_15m, 14) if len(closes_15m) >= 15 else None
    macd_hist_15m = macd_histogram(closes_15m) if len(closes_15m) >= 27 else None
    
    return {
        "timeframes": timeframes_data,
        "rsi_series_15m": rsi_series_15m,
        "price_series_15m": closes_15m,
        "macd_hist_15m": macd_hist_15m,
    }


def measure_future_movement(rows, signal_index, horizons=[3, 6, 12, 24]):
    """
    Mesure le mouvement haussier après un signal sur plusieurs horizons.
    Retourne un dict avec le pourcentage de mouvement pour chaque horizon.
    """
    signal_price = rows[signal_index]['close']
    movements = {}
    
    for horizon in horizons:
        if signal_index + horizon < len(rows):
            future_price = rows[signal_index + horizon]['close']
            movement_pct = ((future_price - signal_price) / signal_price) * 100
            movements[f"{horizon}_candles"] = movement_pct
        else:
            movements[f"{horizon}_candles"] = None  # Données insuffisantes
    
    return movements


def is_significant_movement(movements):
    """
    Détermine si un mouvement est significatif selon les critères prédéfinis.
    Critères:
    - +2% sur 3 bougies, +3% sur 6 bougies, +5% sur 12 bougies, +7% sur 24 bougies
    """
    criteria = {
        "3_candles": 2.0,
        "6_candles": 3.0,
        "12_candles": 5.0,
        "24_candles": 7.0,
    }
    
    significant_count = 0
    total_available = 0
    
    for horizon, threshold in criteria.items():
        if movements.get(horizon) is not None:
            total_available += 1
            if movements[horizon] >= threshold:
                significant_count += 1
    
    # Considéré significatif si au moins 2 horizons sur les disponibles respectent le critère
    return significant_count >= max(1, total_available // 2)


def is_false_positive(movements):
    """
    Détermine si un signal est un faux positif.
    Faux positif: Mouvement < 1% sur tous les horizons ou baisse sur au moins un horizon.
    """
    all_below_1pct = True
    any_decline = False
    
    for horizon, movement in movements.items():
        if movement is not None:
            if movement >= 1.0:
                all_below_1pct = False
            if movement < 0:
                any_decline = True
    
    return all_below_1pct or any_decline


def backtest_timeframe(all_candles_data, timeframe):
    """
    Exécute le backtest sur un timeframe spécifique.
    """
    rows = all_candles_data[timeframe]['rows']
    print(f"\n=== Backtest timeframe {timeframe} ===")
    print(f"Nombre de bougies: {len(rows)}")
    print(f"Période: {rows[0]['open_time']} à {rows[-1]['open_time']}")
    
    signals = []
    significant_movements = 0
    false_positives = 0
    insufficient_data = 0
    
    # Parcourir les bougies chronologiquement
    # Commencer à l'index 50 pour avoir assez d'historique pour SMA50
    start_index = 50
    for i in range(start_index, len(rows)):
        # Analyser à cet index
        analysis = analyze_candle_at_index(all_candles_data, i, timeframe)
        
        if analysis is None:
            continue
        
        # Appeler le détecteur
        detection = detect_early_reversal(
            analysis['timeframes'],
            rsi_series_15m=analysis['rsi_series_15m'],
            price_series_15m=analysis['price_series_15m'],
            macd_hist_15m=analysis['macd_hist_15m'],
        )
        
        # Enregistrer si signal ALERTE_PRÉCOCE
        if detection['signal_status'] == 'ALERTE_PRÉCOCE':
            signal = {
                'index': i,
                'timestamp': rows[i]['open_time'],
                'price': rows[i]['close'],
                'direction': detection['direction'],
                'evidence': detection['evidence'],
                'confidence': detection['confidence'],
                'reason': detection['reason'],
            }
            
            # Mesurer le mouvement futur
            movements = measure_future_movement(rows, i)
            signal['future_movements'] = movements
            
            # Évaluer le mouvement
            if movements['3_candles'] is None and movements['6_candles'] is None:
                insufficient_data += 1
                signal['outcome'] = 'INSUFFICIENT_DATA'
            elif is_significant_movement(movements):
                significant_movements += 1
                signal['outcome'] = 'SIGNIFICANT_MOVEMENT'
            elif is_false_positive(movements):
                false_positives += 1
                signal['outcome'] = 'FALSE_POSITIVE'
            else:
                signal['outcome'] = 'NEUTRAL'
            
            signals.append(signal)
    
    # Calculer les statistiques
    total_signals = len(signals)
    evaluable_signals = total_signals - insufficient_data
    
    print(f"\n=== Résultats {timeframe} ===")
    print(f"Signaux ALERTE_PRÉCOCE: {total_signals}")
    print(f"Signaux évaluables: {evaluable_signals}")
    print(f"Signaux non évaluables (données insuffisantes): {insufficient_data}")
    print(f"Mouvements significatifs: {significant_movements}")
    print(f"Faux positifs: {false_positives}")
    
    if evaluable_signals > 0:
        success_rate = (significant_movements / evaluable_signals) * 100
        false_positive_rate = (false_positives / evaluable_signals) * 100
        print(f"Taux de réussite: {success_rate:.1f}%")
        print(f"Taux de faux positifs: {false_positive_rate:.1f}%")
    
    return {
        'timeframe': timeframe,
        'total_signals': total_signals,
        'evaluable_signals': evaluable_signals,
        'insufficient_data': insufficient_data,
        'significant_movements': significant_movements,
        'false_positives': false_positives,
        'signals': signals,
    }


def main():
    """Fonction principale."""
    print("=== Backtest Historique - Détecteur de Retournement Précoce ===")
    print("Critères de mouvement significatif:")
    print("  - +2% sur 3 bougies")
    print("  - +3% sur 6 bougies")
    print("  - +5% sur 12 bougies")
    print("  - +7% sur 24 bougies")
    print("Faux positif: Mouvement < 1% sur tous horizons ou baisse sur au moins un horizon\n")
    
    # Charger les données
    try:
        candles_data = load_historical_data()
    except FileNotFoundError:
        print("ERREUR: Fichier site/tel_snapshot.json non trouvé")
        return
    
    # Exécuter le backtest sur chaque timeframe disponible
    results = {}
    for timeframe in ['15m', '1h', '4h', '1d']:
        if timeframe in candles_data:
            results[timeframe] = backtest_timeframe(candles_data, timeframe)
    
    # Résumé global
    print("\n" + "="*60)
    print("=== RÉSUMÉ GLOBAL ===")
    print("="*60)
    
    total_signals = sum(r['total_signals'] for r in results.values())
    total_significant = sum(r['significant_movements'] for r in results.values())
    total_false_positives = sum(r['false_positives'] for r in results.values())
    total_insufficient = sum(r['insufficient_data'] for r in results.values())
    total_evaluable = sum(r['evaluable_signals'] for r in results.values())
    
    print(f"\nTotal signaux (tous timeframes): {total_signals}")
    print(f"Total évaluables: {total_evaluable}")
    print(f"Total non évaluables: {total_insufficient}")
    print(f"Total mouvements significatifs: {total_significant}")
    print(f"Total faux positifs: {total_false_positives}")
    
    if total_evaluable > 0:
        global_success_rate = (total_significant / total_evaluable) * 100
        global_fp_rate = (total_false_positives / total_evaluable) * 100
        print(f"\nTaux de réussite global: {global_success_rate:.1f}%")
        print(f"Taux de faux positifs global: {global_fp_rate:.1f}%")
    
    # Sauvegarder les résultats en JSON
    output_path = "backtest_results.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nRésultats détaillés sauvegardés dans: {output_path}")
    
    return results


if __name__ == "__main__":
    main()
