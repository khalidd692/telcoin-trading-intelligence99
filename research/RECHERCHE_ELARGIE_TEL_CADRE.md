# Recherche élargie TEL — cadre de découverte (branche isolée)

Date : 2026-11-09
Instrument : KRAKEN:TELUSD uniquement
Statut : protocole de recherche, aucune stratégie validée, aucun ordre

## Décision méthodologique

Ne pas utiliser le R/R brut minimal de 1,51 comme filtre d'entrée dans la phase de découverte. Ce seuil a éliminé les 53 candidats de la stratégie « repli 4h dans tendance » (maximum observé : 0,801), sans permettre de savoir si d'autres familles de signaux ont une espérance nette positive.

Le R/R reste une mesure à publier, pas un couperet universel au stade exploratoire. La sélection finale se fait sur les résultats nets de frais et slippage, la stabilité hors échantillon, le drawdown, le nombre de trades et la robustesse aux hypothèses de coûts. Aucun seuil ne sera modifié après observation des résultats.

## Périmètre strict

- KRAKEN:TELUSD spot, long-only.
- Recherche et paper trading uniquement.
- Aucun accès à un compte Kraken réel, aucun ordre réel, aucun trading automatique.
- Les règles du board TradingView existant restent intactes.
- Le protocole historique « repli 4h » reste un benchmark figé ; ne pas réécrire ses résultats.
- Données absentes, trouées, périmées ou incohérentes : pas de conclusion exploitable.
- Séparer explicitement observation, hypothèse, résultat exploratoire et validation.

## Familles à explorer séparément

1. Repli / continuation : pullback EMA, retour sur niveau, reprise après consolidation.
2. Réversion à la moyenne : excès de volatilité, retour vers VWAP/EMA ou bandes, uniquement avec filtre de régime.
3. Cassure : breakout de range, clôture confirmée, retest et échec de cassure.
4. Momentum / tendance : accélération prix-volume, structure de sommets/creux, filtre multi-timeframe.
5. Compression / expansion : contraction ATR ou largeur de range suivie d'expansion.
6. Régime « rester en cash » : filtres de tendance/volatilité pour éviter les périodes défavorables.

Ne pas combiner les familles avant de les mesurer séparément. Inclure des baselines simples (buy-and-hold sur la même période, entrée aléatoire contrôlée, cash) pour détecter les faux avantages.

## Recherche multi-unités de temps

- 4h : contexte et régime.
- 1h : construction du setup.
- 15m : précision de l'entrée et de l'invalidation, seulement si la couverture est suffisante.
- Aligner toutes les décisions sur les timestamps réellement clôturés ; aucune bougie en formation.
- Ne jamais compter les bougies 15m/1h comme des observations indépendantes si elles appartiennent au même setup 4h.
- Segmenter chaque série à chaque rupture d'horodatage ; ne jamais interpoler les bougies manquantes.
- Paginer l'historique TradingView avant de conclure sur la profondeur disponible.

## Grille exploratoire

Tester une grille annoncée à l'avance, sans optimisation opportuniste :
- R/R brut descriptif : 0,8 ; 1,0 ; 1,2 ; 1,5 ; sans seuil pré-filtrant.
- Stops : structurels, ATR et volatilité, chacun évalué séparément.
- Sorties : cible fixe, sortie temporelle, trailing/structure, évaluées comme variantes distinctes.
- Frais/slippage : scénario bas, central, stress ; hypothèses et provenance affichées. Utiliser les coûts de carnet quand ils sont disponibles et horodatés.
- Sensibilité : résultats avec et sans coûts, puis sous stress ; ne pas présenter le brut comme résultat tradable.

Cette grille sert à découvrir et comparer. Elle ne modifie pas les règles du paper broker ni le seuil d'admission d'un trade en paper trading sans validation explicite.

## Validation et garde-fous

- Découpage chronologique strict et walk-forward ; holdout final fermé jusqu'à ce que les choix soient figés.
- Pas de fuite temporelle : pivots confirmés seulement après leurs barres de droite ; signal à clôture, entrée à la barre suivante.
- Simuler les positions à travers les frontières des fenêtres ; ne pas réinitialiser artificiellement l'état au changement de phase.
- Une seule position à la fois ; spot sans levier ; risque paper max 0,25 % par trade ; perte quotidienne max 1 % ; cooldown après stop.
- Les limites de risque sont des garde-fous, pas des paramètres d'optimisation.
- Publier n, espérance nette en R et USD, profit factor, drawdown, durée, frais, slippage, périodes et segments.
- Minimum de 100 trades OOS pour prétendre à une validation robuste ; en dessous, rester exploratoire. Si l'historique ne permet pas ce volume, l'indiquer sans fabriquer d'échantillons.
- Toute stratégie doit battre des baselines pertinentes et rester viable en scénario de coûts stressé ; aucune validation sur le seul win rate.

## Données observées au 2026-11-09

- TradingView MCP expose KRAKEN:TELUSD en 4h, 1h et 15m.
- Derniers appels observés : 4h environ 1 743 barres ; 1h 5 000 barres avec pagination disponible ; 15m 5 000 barres avec de nombreuses ruptures d'horodatage.
- Ces chiffres sont des réponses de session, pas une garantie de couverture complète ni une cotation temps réel.
- Les historiques 1h/15m doivent être paginés, dédupliqués, triés et audités avant backtest.

## Résultat de la stratégie repli 4h existante

Benchmark inchangé : 53 candidats, aucun R/R brut >= 1,51, maximum 0,801. Cela invalide l'admissibilité de ces candidats sous le protocole actuel, pas toutes les familles de stratégies possibles.

## Interdictions

Aucun changement de main, aucune fusion, aucun déploiement, aucune modification des boards/alertes TradingView, aucun ordre réel. Cette branche sert uniquement à la recherche et à la traçabilité.
