# Recherche parallèle — structure Sweep → CHoCH sur KRAKEN:TELUSD

Date de collecte : 2026-11-09 UTC
Branche : research/tel-discovery-unrestricted
Statut : exploration, non validée. Aucun ordre passé et aucune stratégie/board modifié.

## Données
- 1h : 6 798 bougies au total; 2 935 bougies retenues dans 12 segments d'au moins 120 bougies, après segmentation stricte.
- 4h : 1 748 bougies, série suffisamment continue pour le contexte.
- 15m : non inclus dans ce test structurel car la série reste très fragmentée (801 interruptions relevées sur l'historique consolidé).
- Les bougies terminales peuvent être en formation; les résultats doivent être reproduits sur données clôturées.

## Définition causale testée
- Pivot high / pivot low symétrique 5/5, publié seulement cinq bougies après le pivot.
- Sweep : le plus bas d'une bougie passe sous le dernier pivot low confirmé, puis clôture au-dessus de ce pivot.
- CHoCH haussier simplifié : clôture qui franchit à la hausse le dernier pivot high confirmé, après un sweep intervenu dans les 12 dernières bougies.
- Entrée à l'ouverture suivante.
- Variante volume : volume de la bougie de cassure >= 1,2 fois la moyenne des 20 volumes précédents.
- Contexte 4h optionnel : dernière bougie 4h entièrement clôturée au-dessus de son EMA20; variante stricte exige aussi EMA20 > EMA50.
- Stop sous le pivot low avec marge de 0,1 ATR, distance minimale 0,8 ATR et maximale 2 ATR.
- Cible 1,5R, durée maximale 24 bougies 1h, stop prioritaire en cas de collision.
- Coût stress : 0,80 % taker + 0,15 % slippage par côté, soit application multiplicative aux deux extrémités.

## Résultats exploratoires 1h
Découpage chronologique approximatif : séparation autour du 12 septembre 2026 (60/40 du flux brut; les segments exclus réduisent la représentativité).

| Variante | Trades | Win % | Espérance nette/trade | PF | Avant séparation | Après séparation |
|---|---:|---:|---:|---:|---:|---:|
| Sweep→CHoCH, sans filtre volume ni filtre 4h | 11 | 45,5 | -1,261 % | 0,55 | -2,863 % (5) | +0,075 % (6) |
| Volume >=1,2×, sans filtre 4h | 10 | 50,0 | -1,294 % | 0,57 | -3,347 % (4) | +0,075 % (6) |
| Volume >=1,2× + close 4h > EMA20 | 6 | 50,0 | -2,897 % | 0,30 | -4,197 % (2) | -2,247 % (4) |
| Volume >=1,2× + EMA20 4h > EMA50 et close > EMA20 | 5 | 60,0 | -2,688 % | 0,36 | -4,197 % (2) | -1,682 % (3) |

## Interprétation
- La configuration Sweep→CHoCH est rare : 5 à 11 transactions selon le filtre. Échantillon insuffisant.
- Le filtre de tendance 4h réduit encore le nombre de cas et n'améliore pas l'espérance nette sur cet échantillon.
- Les coûts et les stops éloignés pénalisent fortement les résultats. Les stops plafonnés à 2 ATR sont utilisés pour éviter des risques illimités.
- Aucune variante n'a démontré un avantage. Ne pas activer en paper comme stratégie active sur la base de ces chiffres.
- Ce test ne comprend pas de test de randomisation ni de p-value, et le découpage chronologique est seulement indicatif; pas de conclusion statistique.

## Snapshot technique TradingView récupéré
Prix de référence affiché par le snapshot : 0,0014882 USD.
- 15m : recommandation BUY; RSI 54,0; ADX 17,6; prix au-dessus EMA20/50 mais sous EMA200.
- 1h : recommandation SELL; RSI 46,2; ADX 35,3; prix sous EMA20/50/200.
- 4h : recommandation SELL; RSI 45,5; ADX 26,0; prix sous EMA20 et EMA200, au-dessus EMA50.
Lecture : rebond très court terme contre un contexte 1h/4h encore faible. Ce snapshot n'est pas un signal d'achat validé; les trois timeframes ne sont pas alignés.

## Suite
1. Tester une définition alternative de CHoCH : changement de séquence LH/LL vers HH/HL, sans exiger sweep dans les 12 bougies.
2. Tester des sorties alternatives et stop basé ATR/swing avec plafonnement explicite, sans optimiser sur l'échantillon complet.
3. Ajouter une comparaison à des entrées aléatoires appariées par régime et volatilité.
4. Ne pas activer de paper strategy avant reproduction exacte, échantillon plus large et contrôle OOS.
