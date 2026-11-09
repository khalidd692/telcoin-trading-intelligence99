# PROTOCOLE FIGÉ — validation de « TEL Kraken – repli 4h dans tendance »

Statut : FIGÉ avant toute exécution du moteur `scripts/strategy_backtest/engine.py` sur les données. Toute modification ultérieure = révision de protocole datée et justifiée.

## Données
- `data/KRAKEN_TELUSD_4h_2026-01-22_2026-11-08.csv` : 1 741 bougies 4h clôturées, 22 janv. → 8 nov. 2026.
- Un trou de 8 h entre les bougies 2 et 3 : séries coupées, rien d'interpolé.
- Aucune donnée 1h/15min exploitée : non accessible depuis cet environnement.

## Règles
EMA amorcée SMA ; ATR Wilder ; pivots 5/5 connus à i+5 ; branche B : barre de retest = barre de confirmation ; expiration à la clôture de la barre d'entrée + 20 ; sorties stop prioritaires ; gap sous stop rempli à l'ouverture ; gap au-dessus cible rempli à la cible. Aucun paramètre optimisé.

## Découpage chronologique
- IS : barres 0–1043 (60 %)
- VAL : barres 1044–1391 (20 %)
- OOS : barres 1392–1740 (20 %)
- Équité remise à 1 000 USD au début de chaque phase ; trade affecté à la phase de sa barre de signal.
- Réserve : un replay préliminaire a parcouru l'ensemble des données en diagnostic ; aucune règle n'a été ajustée.

## Coûts hypothétiques par côté
- brut : 0 % / 0 %
- central : frais 0,25 % + slippage 0,10 %
- prudent : frais 0,40 % + slippage 0,30 %
- Frais Kraken réels NON VÉRIFIÉS.

## Risque
Capital virtuel 1 000 USD ; risque 0,25 % ; spot sans levier ; une position ; cooldown 240 min après stop ; perte quotidienne maximale 1 % ; RR brut minimum 1,51.

## Verdict figé
DONNÉES INSUFFISANTES si N_total < 30. VALIDÉE exige N_oos ≥ 100 et espérance nette positive en central et prudent, PnL OOS positif sans les 3 meilleurs trades, espérance centrale positive en IS et VAL. NON RENTABLE si N_total ≥ 30 et espérance centrale ≤ 0 sur l'ensemble ou PnL négatif sans les 3 meilleurs trades. Autres cas avec N_total ≥ 30 : PROMETTEUSE MAIS NON VALIDÉE.
