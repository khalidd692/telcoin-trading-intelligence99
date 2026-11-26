---
name: tel99-role-quality
description: Skill spécialisé vérifié (mentors Groq 120B/27B/20B sur train/dev) pour l'agent local tel99-quality.
---

# tel99-role-quality — Procédure vérifiée pour `tel99-quality`

## Règles critiques (contexte local 8k)
- Sortie ultra-concise (<= 30 lignes) : ZÉRO docstring, ZÉRO commentaire, ZÉRO bloc `if __name__ == '__main__'` ou exemple.
- Spécialité `tel99-quality` : Use `ast.parse` and `hashlib.sha256` cleanly; verify non-empty check lists and exact bool checks (`is True`/`is False`).
- Trim exception messages to a safe length to avoid output truncation
- Use `result.get('ok') is True` instead of truthiness for strict checks
- Pièges évités : Truncation from verbose try/except examples; missing `is True` strict bool check on dict fields; missing AST walk edge cases.

## Protocole de raisonnement & autocorrection
- Wrap ast.parse in try/except, catch SyntaxError and capture its message
- Construct result dict with explicit `is True` checks for boolean fields
- Traverse AST safely, handling missing body nodes with defaults
- Vérif : Verify returned dict exactly matches {'ok': bool, 'error': str|None}
- Vérif : Run tests for empty code, syntax errors, and boolean edge cases

## Exemple vérifié (train-only, 0 fuite held-out)
```python
import ast

def check_syntax_valid(code_str):
    if not isinstance(code_str, str):
        raise ValueError
    try:
        ast.parse(code_str)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "error": None}
```

## Durcissement généralisable post-V3
- Toujours vérifier `if isinstance(x, bool):` AVANT `isinstance(x, (int, float))` et AVANT toute comparaison `== 0` ou `<= 0`.
- Toujours encoder les `str` en `bytes` (`s.encode('utf-8')`) avant `hmac.new(...)` ou `hashlib.*`.
- Respecter les préfixes optionnels (`v?X.Y.Z`) et initialiser toute variable locale avant les branches `if/else`.
