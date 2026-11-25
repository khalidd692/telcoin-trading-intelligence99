---
name: tel99-role-monitoring
description: Skill spécialisé vérifié (mentors Groq 120B/27B/20B sur train/dev) pour l'agent local tel99-monitoring.
---

# tel99-role-monitoring — Procédure vérifiée pour `tel99-monitoring`

## Règles critiques (contexte local 8k)
- Sortie ultra-concise (<= 30 lignes) : ZÉRO docstring, ZÉRO commentaire, ZÉRO bloc `if __name__ == '__main__'` ou exemple.
- Spécialité `tel99-monitoring` : Distinguish resident vs pre-load RAM thresholds, exact nearest-rank p95 (`math.ceil(0.95*n)-1`), return exact JSON when asked.
- Reject isinstance(x, bool) before int/float
- Check empty/negative inputs with ValueError
- Pièges évités : Missing negative/bool/>1.0 validation in alert triage; nearest-rank p95 index formula `math.ceil(0.95*n)-1`; JSON key mismatch.

## Protocole de raisonnement & autocorrection
- Parse exact signature & return keys
- Validate bool/types/bounds first
- Write <=25 lines, zero docstrings
- Vérif : Verify all required keys/methods exist
- Vérif : Ensure zero trailing example code

## Exemple vérifié (train-only, 0 fuite held-out)
```python
def classify_ram_headroom(free_mb, *, model_resident=False):
    if isinstance(free_mb, bool) or not isinstance(free_mb, (int, float)) or free_mb < 0:
        raise ValueError
    ok = 950 if model_resident else 2200
    warn = 700 if model_resident else 1400
    return 'OK' if free_mb >= ok else 'WARN' if free_mb >= warn else 'CRITICAL'
```
