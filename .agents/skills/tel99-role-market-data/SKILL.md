---
name: tel99-role-market-data
description: Skill spécialisé vérifié (mentors Groq 120B/27B/20B sur train/dev) pour l'agent local tel99-market_data.
---

# tel99-role-market-data — Procédure vérifiée pour `tel99-market_data`

## Règles critiques (contexte local 8k)
- Sortie ultra-concise (<= 30 lignes) : ZÉRO docstring, ZÉRO commentaire, ZÉRO bloc `if __name__ == '__main__'` ou exemple.
- Spécialité `tel99-market_data` : Validate OHLCV inequalities, strictly check bid < ask, aggregate timestamps via `ts // bucket_s * bucket_s`.
- Reject bool values explicitly using isinstance(x, bool)
- Raise ValueError if ask < bid or any price <= 0
- Pièges évités : Truncation from verbose docstrings; missing non-monotonic vs duplicate vs gap distinction; OHLCV inequality or bucket floor `ts // bucket * 

## Protocole de raisonnement & autocorrection
- Parse input dicts, verify required keys exist and values are numeric non‑bool
- Apply business rules: reject bools, non‑positive prices, ask < bid, keep last ts
- Aggregate candles per bucket using ts // bucket_s * bucket_s and compute OHLCV
- Vérif : Run unit tests with typical, duplicate, and empty candle lists
- Vérif : Confirm rounding to 4 decimals and bucket timestamps align to bucket_s

## Exemple vérifié (train-only, 0 fuite held-out)
```python
def validate_ohlcv_candle(c):
    try:
        o, h, l, cl, v = (c[k] for k in ('open', 'high', 'low', 'close', 'volume'))
    except (KeyError, TypeError):
        return False
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in (o, h, l, cl, v)):
        return False
    return o > 0 and h > 0 and l > 0 and cl > 0 and v >= 0 and l <= min(o, cl) <= max(o, cl) <= h
```

## Durcissement généralisable post-V3
- Toujours vérifier `if isinstance(x, bool):` AVANT `isinstance(x, (int, float))` et AVANT toute comparaison `== 0` ou `<= 0`.
- Toujours encoder les `str` en `bytes` (`s.encode('utf-8')`) avant `hmac.new(...)` ou `hashlib.*`.
- Respecter les préfixes optionnels (`v?X.Y.Z`) et initialiser toute variable locale avant les branches `if/else`.
