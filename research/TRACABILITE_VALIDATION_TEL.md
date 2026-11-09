# Traçabilité — validation TEL (9 nov. 2026)

## Données OBSERVÉES
- Fichier : `data/KRAKEN_TELUSD_4h_2026-01-22_2026-11-08.csv` (non modifié), 1 741 bougies 4h clôturées, 2026-01-22T12:00Z → 2026-11-08T16:00Z (ouverture).
- SHA-256 : `96b50ad431ff3c78cefc2a18b37d6cc3224ec82e9a67d7812a0e172535674aa4`
- Blob SHA-1 git : `3510de242d99533cb1fa941b9fb621d253a8b020`.
- SHA-1 du fichier brut : `c8c30a87150d0f28f8793d3d2118a9260a4f3d5e`.
- Un trou de 8 h entre les bougies 2 et 3 ; deux segments (2 et 1 739 barres), rien d'interpolé.
- MCP/Smart View TradingView et historiques 1h/15min non accessibles et non utilisés.

## HYPOTHÈSES
- Frais et slippage par côté : central 0,25 % + 0,10 % ; prudent 0,40 % + 0,30 % ; brut 0 %. Frais Kraken réels NON VÉRIFIÉS.
- Capital virtuel 1 000 USD ; risque 0,25 % ; conventions d'implémentation dans l'en-tête de `engine.py`.

## Versions
- Commit de base annoncé dans le rapport local : main @ a04ee926d64a7cdd6549a17b1ae1fd06778be219.
- Commit du protocole local annoncé : 44a9cb4 (avant exécution).
- Exécution annoncée : une seule, 9 nov. 2026, Python 3 stdlib, sans modification de règles après lecture des résultats.
