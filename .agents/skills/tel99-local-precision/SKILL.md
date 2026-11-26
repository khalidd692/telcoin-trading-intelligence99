---
name: tel99-local-precision
description: Procédures vérifiées issues du transfert mentor cloud→local pour les 12 agents locaux TEL99 (validation stricte bool/int, math causale sans fuite, AST/sécurité, JSON structuré et réparation ciblée sur contexte 8k).
---

# TEL99 — Skill de Précision Locale (Distillé depuis Mentors Vérifiés)

Ce Skill concentre les règles vérifiées issues des échecs et réussites sur le jeu `train`/`dev` afin d'augmenter la réussite au premier essai des agents locaux (`gemma4:e4b-tel99-8k`) **sans assistance cloud**.

## 1. Validation stricte des types Python (`ValueError` vs `TypeError`)
- En Python, `isinstance(True, int)` vaut `True`. Toujours rejeter explicitement `isinstance(x, bool)` **avant** `isinstance(x, (int, float))`.
- Lever **`ValueError`** (et non `TypeError`) lorsqu'un contrat demande de rejeter `bool`, `None`, des bornes invalides, des listes vides ou des valeurs négatives.
- Ne jamais muter les dictionnaires ou listes d'entrée (`dict(orig)` / copie défensive).

## 2. Mathématiques quantitatives & données de marché causales
- Fenêtre strictement causale : pour l'indice `i`, lire uniquement `values[max(0, i - window + 1) : i + 1]` — **jamais** d'élément `j > i`.
- Arrondir exactement au nombre de décimales demandé (`round(..., 4)` ou `round(..., 6)`).
- OHLCV : vérifier `open/high/low/close > 0`, `volume >= 0` et `low <= min(open, close) <= max(open, close) <= high`.

## 3. Sécurité, AST, Coordination & Serveur Loopback
- Utiliser `http.server.ThreadingHTTPServer` (jamais `socketserver.ThreadingHTTPServer`).
- Liaison réseau strictement locale : autoriser uniquement `127.0.0.1`, `localhost`, `::1` ; rejeter `0.0.0.0`.
- Chemins sûrs : vérifier absence de `..`, chemin non absolu, sans `:` ni `~`, et confinement via `Path.resolve()`.
- Aucun `eval`, `exec`, `compile`, `__import__`, `shell=True`, `<script>` inline, `javascript:` ni `document.write`.
- Baux CAS : un bail actif ne peut jamais être libéré par un autre acteur ; comparer les hashes via `hmac.compare_digest`.

## 4. Sorties structurées JSON & Concision 8k
- Quand un JSON exact est demandé, renvoyer **uniquement** l'objet JSON conforme aux clés et types exacts, sans texte autour.
- Produire un code concis (< 65 lignes par module), sans longues docstrings redondantes qui provoquent une troncature de tokens sur CPU.
