---
name: tel99-role-documentation
description: Skill spécialisé vérifié (mentors Groq 120B/27B/20B sur train/dev) pour l'agent local tel99-documentation.
---

# tel99-role-documentation — Procédure vérifiée pour `tel99-documentation`

## Règles critiques (contexte local 8k)
- Sortie ultra-concise (<= 30 lignes) : ZÉRO docstring, ZÉRO commentaire, ZÉRO bloc `if __name__ == '__main__'` ou exemple.
- Spécialité `tel99-documentation` : Preserve exact Markdown formatting, escape pipes in tables, parse ISO dates strictly (YYYY-MM-DD), return exact JSON when asked.
- Reject isinstance(x, bool) before int/float
- Check empty/negative inputs with ValueError
- Pièges évités : Missing exact heading/status token matching; case-sensitivity mismatches; unescaped Markdown pipes; invalid ISO YYYY-MM-DD date parsing.

## Protocole de raisonnement & autocorrection
- Parse exact signature & return keys
- Validate bool/types/bounds first
- Write <=25 lines, zero docstrings
- Vérif : Verify all required keys/methods exist
- Vérif : Ensure zero trailing example code

## Exemple vérifié (train-only, 0 fuite held-out)
```python
import re

def extract_markdown_headings(md_text):
    return [(len(m.group(1)), m.group(2).strip()) for m in re.finditer(r'^(#{1,6})\s+(.*)$', md_text, re.M)]
```
