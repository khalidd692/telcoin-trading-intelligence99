---
name: tel99-role-mobile
description: Skill spécialisé vérifié (mentors Groq 120B/27B/20B sur train/dev) pour l'agent local tel99-mobile.
---

# tel99-role-mobile — Procédure vérifiée pour `tel99-mobile`

## Règles critiques (contexte local 8k)
- Sortie ultra-concise (<= 30 lignes) : ZÉRO docstring, ZÉRO commentaire, ZÉRO bloc `if __name__ == '__main__'` ou exemple.
- Spécialité `tel99-mobile` : Use exact regex/string checks for HTML/CSS/ARIA, handle comments when balancing braces, reject bool in numeric formatters.
- Reject isinstance(x, bool) before int/float
- Check empty/negative inputs with ValueError
- Pièges évités : Truncation in long regex/HTML scripts; missing case-insensitive checks or `<script>` vs `<script src=...>` distinction; CSS comment brace ba

## Protocole de raisonnement & autocorrection
- Parse exact signature & return keys
- Validate bool/types/bounds first
- Write <=25 lines, zero docstrings
- Vérif : Verify all required keys/methods exist
- Vérif : Ensure zero trailing example code

## Exemple vérifié (train-only, 0 fuite held-out)
```python
def check_css_braces_balanced(css_text):
    depth = 0
    i = 0
    n = len(css_text)
    while i < n:
        if css_text[i] == '/' and i + 1 < n and css_text[i + 1] == '*':
            j = css_text.find('*/', i + 2)
            if j == -1:
                i = n
            else:
                i = j + 2
            continue
        if css_text[i] == '{':
            depth += 1
        elif css_text[i] == '}':
   
```
