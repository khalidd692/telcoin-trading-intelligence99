---
name: tel99-role-quant
description: Skill spécialisé vérifié (mentors Groq 120B/27B/20B sur train/dev) pour l'agent local tel99-quant.
---

# tel99-role-quant — Procédure vérifiée pour `tel99-quant`

## Règles critiques (contexte local 8k)
- Sortie ultra-concise (<= 30 lignes) : ZÉRO docstring, ZÉRO commentaire, ZÉRO bloc `if __name__ == '__main__'` ou exemple.
- Spécialité `tel99-quant` : Strictly causal math (index i uses ONLY indices <= i), reject bool/non-positive prices, round to exact requested decimals.
- Reject isinstance(x, bool) before int/float
- Check empty/negative inputs with ValueError
- Pièges évités : Truncation from verbose docstrings; lookahead leakage beyond index i; forgetting bool check inside list elements; rounding drift.

## Protocole de raisonnement & autocorrection
- Parse exact signature & return keys
- Validate bool/types/bounds first
- Write <=25 lines, zero docstrings
- Vérif : Verify all required keys/methods exist
- Vérif : Ensure zero trailing example code

## Exemple vérifié (train-only, 0 fuite held-out)
```python
def simple_returns(prices):
    if len(prices) < 2 or any(isinstance(p, bool) or p <= 0 for p in prices):
        raise ValueError
    return [round((prices[i] - prices[i - 1]) / prices[i - 1], 6) for i in range(1, len(prices))]
```

## Durcissement généralisable post-V3
- Toujours vérifier `if isinstance(x, bool):` AVANT `isinstance(x, (int, float))` et AVANT toute comparaison `== 0` ou `<= 0`.
- Toujours encoder les `str` en `bytes` (`s.encode('utf-8')`) avant `hmac.new(...)` ou `hashlib.*`.
- Respecter les préfixes optionnels (`v?X.Y.Z`) et initialiser toute variable locale avant les branches `if/else`.
