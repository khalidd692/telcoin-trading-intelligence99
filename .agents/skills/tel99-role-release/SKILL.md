---
name: tel99-role-release
description: Skill spécialisé vérifié (mentors Groq 120B/27B/20B sur train/dev) pour l'agent local tel99-release.
---

# tel99-role-release — Procédure vérifiée pour `tel99-release`

## Règles critiques (contexte local 8k)
- Sortie ultra-concise (<= 30 lignes) : ZÉRO docstring, ZÉRO commentaire, ZÉRO bloc `if __name__ == '__main__'` ou exemple.
- Spécialité `tel99-release` : Enforce strict semver/40-hex SHA/ISO UTC parsing, never allow auto-merge on main/master, return exact JSON when asked.
- Reject isinstance(x, bool) before int/float
- Check empty/negative inputs with ValueError
- Pièges évités : Missing semver/40-hex SHA validation; allowing main/master without owner approval; JSON schema mismatch.

## Protocole de raisonnement & autocorrection
- Parse exact signature & return keys
- Validate bool/types/bounds first
- Write <=25 lines, zero docstrings
- Vérif : Verify all required keys/methods exist
- Vérif : Ensure zero trailing example code

## Exemple vérifié (train-only, 0 fuite held-out)
```python
import re

def parse_semver(tag: str) -> tuple[int, int, int]:
    m = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', tag)
    if not m:
        raise ValueError(f"Invalid semver: {tag!r}")
    return tuple(int(g) for g in m.groups())
```

## Durcissement généralisable post-V3
- Toujours vérifier `if isinstance(x, bool):` AVANT `isinstance(x, (int, float))` et AVANT toute comparaison `== 0` ou `<= 0`.
- Toujours encoder les `str` en `bytes` (`s.encode('utf-8')`) avant `hmac.new(...)` ou `hashlib.*`.
- Respecter les préfixes optionnels (`v?X.Y.Z`) et initialiser toute variable locale avant les branches `if/else`.
