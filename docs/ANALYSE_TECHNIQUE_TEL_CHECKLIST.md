# Checklist obligatoire — Analyse technique TEL
Date d'ajout : 2026-10-20

## Règle non négociable
Ne jamais fonder une analyse ou un verdict d'entrée TEL sur le RSI seul. Examiner toutes les captures TradingView fournies par l'utilisateur et relever les informations visibles avant de conclure. Ne jamais prétendre qu'une capture ou une unité de temps a été vérifiée si ce n'est pas le cas.

## Lecture des captures
Pour chaque capture, noter :
- la paire et la plateforme (ex. TEL/USDT, KuCoin/MEXC) ;
- l'unité de temps sélectionnée ;
- le résumé TradingView et les décomptes Buy/Neutral/Sell ;
- tous les oscillateurs visibles, leurs valeurs et leurs actions ;
- toutes les moyennes mobiles visibles, leurs valeurs et leurs actions ;
- pivots/niveaux visibles, si présents ;
- le prix/candles/volume visibles si présents ;
- les informations manquantes ou illisibles.

Ne pas déduire de valeur non visible. Si la capture montre seulement la table technique, préciser qu'elle ne permet pas de vérifier directement la structure des bougies ou le volume.

## Checklist d'analyse multi-unités
Vérifier autant que les données sont disponibles :
- 15 min : réaction précoce et momentum ;
- 1 h : évolution du momentum et structure ;
- 4 h : confirmation après clôture ;
- 1 jour : tendance et résistances de fond ;
- 1 semaine et 1 mois : contexte de plus long terme.

Examiner conjointement :
1. Prix, bougies clôturées/en formation, structure, sommets/creux, supports/résistances, cassures et faux départs.
2. Tendance : EMA/SMA (10, 20, 30, 50, 100, 200 si disponibles), Ichimoku et autres moyennes visibles.
3. Momentum/oscillateurs : RSI, MACD (ligne, signal, histogramme), Stochastique, Williams %R, CCI, Momentum, ADX/DMI, Ultimate Oscillator et autres indicateurs disponibles.
4. Volume : volume courant contre moyenne, confirmation ou absence de participation acheteuse, liquidité et spread si accessibles.
5. Contexte externe : BTC et ETH, volatilité et contexte de marché.
6. Qualité des données : horodatage, fraîcheur, bougie clôturée ou en formation, cohérence entre sources et indépendance réelle des plateformes.

## États de signal à distinguer
- ALERTE PRÉCOCE : des signes initiaux de changement apparaissent, sans confirmation suffisante.
- CONFIRMATION : plusieurs éléments concordants, structure et clôtures pertinentes confirmant le scénario.
- INVALIDATION : les conditions observées contredisent le scénario.
- ATTENDRE / DONNÉES INSUFFISANTES : données périmées, incohérentes ou manquantes. Ne pas inventer de confirmation.

Un marché survendu (RSI/Stochastique/Williams %R bas) rend un rebond possible mais ne confirme pas un retournement. À l'inverse, ne pas attendre que tous les indicateurs deviennent acheteurs avant de détecter une alerte précoce.

## Compte rendu obligatoire
- Horodatage et sources utilisées ;
- unités de temps effectivement examinées et celles manquantes ;
- résumé de chaque famille d'indicateurs ;
- arguments haussiers ET baissiers ;
- niveaux observés, sans transformer une observation en nouveau seuil stratégique non autorisé ;
- statut des données et bougies ;
- distinction explicite entre alerte précoce, confirmation et invalidation ;
- verdict pratique et incertitudes ;
- journaliser les retournements et vérifier ensuite quels signaux ont réellement précédé le mouvement.

## Protections du projet
Ne pas modifier des seuils, stratégies, scripts, alertes, ordres ou déploiements sans autorisation explicite. Aucune exécution d'ordre. Si données insuffisantes ou incohérentes : ATTENDRE.
