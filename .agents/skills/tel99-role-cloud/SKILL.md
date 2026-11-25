---
name: tel99-role-cloud
description: Skill spécialisé vérifié (mentors Groq 120B/27B/20B sur train/dev) pour l'agent local tel99-cloud.
---

# tel99-role-cloud — Procédure vérifiée pour `tel99-cloud`

## Règles critiques (contexte local 8k)
- Sortie ultra-concise (<= 30 lignes) : ZÉRO docstring, ZÉRO commentaire, ZÉRO bloc `if __name__ == '__main__'` ou exemple.
- Spécialité `tel99-cloud` : Enforce loopback-only URLs, pinned @sha256 digests (64 hex chars), strict no-extra-spend billing rules, never mutate input env dict.
- Reject isinstance(x, bool) before int/float
- Check empty/negative inputs with ValueError
- Pièges évités : Missing `pull_request_target` list/dict trigger handling; mutating input dicts; missing @sha256 64-hex length check or loopback host validat

## Protocole de raisonnement & autocorrection
- Parse exact signature & return keys
- Validate bool/types/bounds first
- Write <=25 lines, zero docstrings
- Vérif : Verify all required keys/methods exist
- Vérif : Ensure zero trailing example code

## Exemple vérifié (train-only, 0 fuite held-out)
```python
def is_loopback_url(url: str) -> bool:
    u = url.lower()
    return ('@' not in u) and (u.startswith('http://127.0.0.1') or u.startswith('http://localhost'))
```

## Durcissement généralisable post-V3
- Toujours vérifier `if isinstance(x, bool):` AVANT `isinstance(x, (int, float))` et AVANT toute comparaison `== 0` ou `<= 0`.
- Toujours encoder les `str` en `bytes` (`s.encode('utf-8')`) avant `hmac.new(...)` ou `hashlib.*`.
- Respecter les préfixes optionnels (`v?X.Y.Z`) et initialiser toute variable locale avant les branches `if/else`.
