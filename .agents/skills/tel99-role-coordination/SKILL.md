---
name: tel99-role-coordination
description: Skill spécialisé vérifié (mentors Groq 120B/27B/20B sur train/dev) pour l'agent local tel99-coordination.
---

# tel99-role-coordination — Procédure vérifiée pour `tel99-coordination`

## Règles critiques (contexte local 8k)
- Sortie ultra-concise (<= 30 lignes) : ZÉRO docstring, ZÉRO commentaire, ZÉRO bloc `if __name__ == '__main__'` ou exemple.
- Spécialité `tel99-coordination` : Deterministic sorting, Kahn's algorithm for DAG topological sort, strict lease ownership (never release foreign active lease).
- Reject isinstance(x, bool) before int/float
- Check empty/negative inputs with ValueError
- Pièges évités : Unclosed parentheses from long output; non-deterministic tie-breaking; missing `max_parallel < 1` or bool validation.

## Protocole de raisonnement & autocorrection
- Parse exact signature & return keys
- Validate bool/types/bounds first
- Write <=25 lines, zero docstrings
- Vérif : Verify all required keys/methods exist
- Vérif : Ensure zero trailing example code

## Exemple vérifié (train-only, 0 fuite held-out)
```python
import posixpath

def detect_path_overlap(paths_a, paths_b, *, case_insensitive=False):
    def norm(p):
        p = posixpath.normpath(p.replace('\\', '/'))
        return p.lower() if case_insensitive else p
    a = {norm(p) for p in paths_a}
    b = {norm(p) for p in paths_b}
    return sorted(a & b)
```
