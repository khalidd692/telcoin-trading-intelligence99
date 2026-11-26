---
name: tel99-role-development
description: Skill spécialisé vérifié (mentors Groq 120B/27B/20B sur train/dev) pour l'agent local tel99-development.
---

# tel99-role-development — Procédure vérifiée pour `tel99-development`

## Règles critiques (contexte local 8k)
- Sortie ultra-concise (<= 30 lignes) : ZÉRO docstring, ZÉRO commentaire, ZÉRO bloc `if __name__ == '__main__'` ou exemple.
- Spécialité `tel99-development` : Handle edge cases strictly: reject bool when int/float expected (`isinstance(x, bool)`), validate bounds and types cleanly.
- Reject isinstance(x, bool) before int/float
- Check empty/negative inputs with ValueError
- Pièges évités : Truncation at line ~90 from docstrings/example blocks; bool accepted as int; missing class method attributes; off-by-one quota/bounds checks

## Protocole de raisonnement & autocorrection
- Parse exact signature & return keys
- Validate bool/types/bounds first
- Write <=25 lines, zero docstrings
- Vérif : Verify all required keys/methods exist
- Vérif : Ensure zero trailing example code

## Exemple vérifié (train-only, 0 fuite held-out)
```python
def clamp_value(x, lo, hi):
    if isinstance(x, bool) or x is None or isinstance(lo, bool) or lo is None or isinstance(hi, bool) or hi is None:
        raise ValueError
    if lo > hi:
        raise ValueError
    return max(lo, min(x, hi))
```

## Durcissement généralisable post-V3
- Toujours vérifier `if isinstance(x, bool):` AVANT `isinstance(x, (int, float))` et AVANT toute comparaison `== 0` ou `<= 0`.
- Toujours encoder les `str` en `bytes` (`s.encode('utf-8')`) avant `hmac.new(...)` ou `hashlib.*`.
- Respecter les préfixes optionnels (`v?X.Y.Z`) et initialiser toute variable locale avant les branches `if/else`.
