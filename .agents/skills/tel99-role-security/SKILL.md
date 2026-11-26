---
name: tel99-role-security
description: Skill spécialisé vérifié (mentors Groq 120B/27B/20B sur train/dev) pour l'agent local tel99-security.
---

# tel99-role-security — Procédure vérifiée pour `tel99-security`

## Règles critiques (contexte local 8k)
- Sortie ultra-concise (<= 30 lignes) : ZÉRO docstring, ZÉRO commentaire, ZÉRO bloc `if __name__ == '__main__'` ou exemple.
- Spécialité `tel99-security` : Use pathlib.Path.resolve() for containment, hmac.compare_digest for digests, regex redaction without mutating input dicts.
- Reject target_rel if Path(target_rel).is_absolute() or contains '..'.
- After resolve, ensure target_path.is_relative_to(workspace_root).
- Pièges évités : Incomplete path traversal checks (empty, absolute, '..', resolve containment); leaking raw secrets in regex redaction; non-constant-time dig

## Protocole de raisonnement & autocorrection
- Parse inputs, validate path components, resolve against workspace root.
- Compile secret patterns, replace matches with placeholder of same length.
- Use constant‑time comparison for digests to avoid timing leaks.
- Vérif : All functions return False/empty list on safe inputs.
- Vérif : Unit tests cover empty strings, absolute paths, and overlapping allowed paths.

## Exemple vérifié (train-only, 0 fuite held-out)
```python
import re

def contains_secret_token(text):
    return bool(re.search(r'ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{16,}', text))
```

## Durcissement généralisable post-V3
- Toujours vérifier `if isinstance(x, bool):` AVANT `isinstance(x, (int, float))` et AVANT toute comparaison `== 0` ou `<= 0`.
- Toujours encoder les `str` en `bytes` (`s.encode('utf-8')`) avant `hmac.new(...)` ou `hashlib.*`.
- Respecter les préfixes optionnels (`v?X.Y.Z`) et initialiser toute variable locale avant les branches `if/else`.
