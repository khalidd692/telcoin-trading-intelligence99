---
name: market-data-quality-readonly
description: Permet à un agent de contrôler la fraîcheur, les horodatages UTC, les doublons et les données manquantes sur des fixtures synthétiques, strictement en lecture seule.
---

# Skill: market-data-quality-readonly

**But :** Permettre à un agent de contrôler la qualité des données de marché (fraîcheur, horodatages UTC, doublons, données manquantes) sur des fixtures synthétiques, strictement en lecture seule, sans aucun ordre financier ni modification de donnée de production.

**Quand déclencher :**
- Vérification de fraîcheur d'un snapshot de données de marché.
- Contrôle d'horodatages UTC sur des bougies Kraken.
- Détection de doublons dans une série de données.
- Détection de données manquantes (gaps temporels).

**Quand NE PAS déclencher :**
- Données de marché réelles en production (→ lire seulement, jamais modifier).
- Ordre d'achat/vente (interdit absolu).
- Erreur Python/JS (→ `python-test-triage` / `javascript-regression-triage`).

**Comment utiliser :**

### 1. Charger une fixture synthétique (lecture seule)

Utiliser un fichier de test synthétique (JSON, CSV) représentant des données de marché. Ne jamais charger de données de production réelles.

### 2. Contrôler la fraîcheur

Comparer l'horodatage le plus récent des données avec l'heure UTC actuelle :
- Si l'écart dépasse le seuil configuré (ex: 15 min pour des bougies 15m) → `STALE`.
- Sinon → `FRESH`.

### 3. Vérifier les horodatages UTC

- Tous les horodatages doivent être en UTC (suffixe `Z` ou offset `+00:00`).
- Pas d'horodatage naïf (sans fuseau) ni en heure locale.

### 4. Détecter les doublons

- Identifier les doublons sur la clé (symbole, timestamp).
- Signaler tout doublon comme `DUPLICATE`.

### 5. Détecter les données manquantes

- Identifier les gaps dans la série temporelle (ex: bougie manquante à t+15min).
- Signaler tout gap comme `MISSING`.

### 6. Produire un rapport de qualité

Format :
```markdown
## Rapport de qualité des données — <fixture>

**Fichier :** <chemin>
**Nombre de lignes :** <N>
**Fraîcheur :** FRESH | STALE (écart : <X> min)
**Horodatages UTC :** OK | KO (N non-UTC)
**Doublons :** 0 | <N> (ex: symbol=BTC/USD, ts=...)
**Données manquantes :** 0 | <N> (ex: ts=2026-11-19T14:00:00Z)
**Verdict :** VALIDE | INVALIDE
```

---

## Entrées

- Fixture synthétique (fichier JSON/CSV de données de marché).
- Seuil de fraîcheur configurable (en minutes).

## Sorties

- **Rapport de qualité** (Markdown) avec verdict VALIDE/INVALIDE.
- Jamais de modification de la fixture ni de donnée de production.

## Permissions

- **Lecture seule** : fichier de fixture, logs.
- **Interdits absolus** : écriture sur donnée de production, ordre d'achat/vente, modification de solde, clé API, secret.

## Exclusions (ne pas faire)

- Ne jamais envoyer d'ordre financier (réel ou simulé).
- Ne jamais modifier une donnée de marché de production.
- Ne pas utiliser de clé API ou de secret.
- Ne pas modifier `scripts/agents/native/*` (Codex G3).
- Ne pas déclarer une donnée valide sans avoir vérifié fraîcheur ET UTC ET doublons ET manquants.

## Tests de validation

### Test positif — Fixture valide
- Fixture synthétique : 100 bougies BTC/USD 15m, horodatages UTC, aucun doublon, aucun gap, fraîcheur < 15 min.
- Verdict : VALIDE.

### Test négatif — Fixture invalide (donnée manquante)
- Fixture synthétique avec une bougie manquante à t+15min.
- Verdict : INVALIDE, `MISSING` signalé.

### Test négatif — Fixture invalide (doublon)
- Fixture synthétique avec un doublon (symbole + timestamp identiques).
- Verdict : INVALIDE, `DUPLICATE` signalé.

### Test négatif — Fixture invalide (pas UTC)
- Fixture synthétique avec un horodatage sans fuseau horaire.
- Verdict : INVALIDE, `KO` sur horodatages UTC.

### Test sécurité — Aucun ordre financier
- Le Skill ne contient aucune logique d'achat/vente.
- Aucun secret ni clé API dans le rapport.

## Version

1.0

## Retour arrière

- Aucune modification effectuée (lecture seule).
- Fichiers de rapport temporaires supprimés.

## Conflits connus

- Ne pas modifier les données de marché de production.
- Ne pas interférer avec les travaux de l'autre chef (G0–G7).
- Ne pas modifier `scripts/agents/native/*` (Codex G3).
