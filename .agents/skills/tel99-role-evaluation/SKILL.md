---
name: tel99-role-evaluation
description: Skill spécialisé vérifié (mentors Groq 120B/27B/20B sur train/dev) pour l'agent local tel99-evaluation.
---

# tel99-role-evaluation — Procédure vérifiée pour `tel99-evaluation`

## Règles critiques (contexte local 8k)
- Sortie ultra-concise (<= 30 lignes) : ZÉRO docstring, ZÉRO commentaire, ZÉRO bloc `if __name__ == '__main__'` ou exemple.
- Spécialité `tel99-evaluation` : Use exact math.comb/Wilson/Brier formulas, reject bool/out-of-range probabilities, return exact JSON schema when asked.
- Clamp or reject probabilities outside [0,1] before computation
- Return 0.0 Wilson bound when passed == 0 or total == 0
- Pièges évités : Forgetting bool/out-of-range [0,1] checks in Brier/Wilson/sign-test; wrong JSON schema keys.

## Protocole de raisonnement & autocorrection
- Identify required input constraints for each function
- Add explicit checks for probability bounds, bool types, and list emptiness
- Map output to the exact schema keys expected by the evaluator
- Vérif : Run unit tests covering empty inputs, out-of-range probs, and overlap cases
- Vérif : Verify returned dict keys match the specification exactly

## Exemple vérifié (train-only, 0 fuite held-out)
```python
def brier_score(predictions):
    if not predictions:
        raise ValueError
    for p, o in predictions:
        if not (0 <= p <= 1) or not isinstance(o, bool):
            raise ValueError
    return round(sum((p - int(o)) ** 2 for p, o in predictions) / len(predictions), 4)
```

## Durcissement généralisable post-V3
- Toujours vérifier `if isinstance(x, bool):` AVANT `isinstance(x, (int, float))` et AVANT toute comparaison `== 0` ou `<= 0`.
- Toujours encoder les `str` en `bytes` (`s.encode('utf-8')`) avant `hmac.new(...)` ou `hashlib.*`.
- Respecter les préfixes optionnels (`v?X.Y.Z`) et initialiser toute variable locale avant les branches `if/else`.
