# Audit de reprise — TEL Kraken « repli 4h dans tendance » (9 nov. 2026)

## Accès réels
- Dépôt GitHub en lecture accessible.
- TradingView Smart View / MCP non disponible dans la session de préparation ; aucune donnée TradingView lue.
- Historiques 1h (~6 777) et 15 min (~5 525) inaccessibles et non utilisés.

## Données contrôlées
- 1 741 bougies 4h, 2026-01-22 12:00 → 2026-11-08 16:00 UTC (ouverture) ; dernière clôturée à 20:00.
- Un trou de 8 h au début (entre les bougies 2 et 3) → segments de 2 et 1 739 barres.
- Blob SHA-1 git `3510de242d99533cb1fa941b9fb621d253a8b020` n'est pas un SHA256. SHA256 réel : `96b50ad431ff3c78cefc2a18b37d6cc3224ec82e9a67d7812a0e172535674aa4`.
- Le prix passe d'environ 0,0040 à 0,00155 USD sur la période, régime fortement baissier.

## Scripts existants
`scripts/backtest/*` évalue l'ancien détecteur (KuCoin 15m, protocole OOS 60/40) ; non réutilisé comme moteur de la stratégie.

## Écarts
1. Ancien moteur : ATR simple au lieu de Wilder et branche résistance/support absente ; moteur dédié séparé dans `scripts/strategy_backtest/engine.py`.
2. Conventions figées : barre de retest = barre de confirmation ; expiration à la clôture de la barre d'entrée + 20 ; pivots causaux ; gap haussier rempli à la cible.
3. Huit rule_checks TradingView étaient « unsettled » : la spécification testée est celle du document de reprise, pas une lecture du Pine.
