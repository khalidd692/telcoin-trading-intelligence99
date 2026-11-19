---
name: market-data-quality-readonly
description: "Contrôler la qualité des données de marché Kraken (et sources associées) en lecture seule : fraîcheur, complétude, cohérence, anomalies — sans jamais modifier les données ni envoyer d'ordres."
---

# Skill: market-data-quality-readonly

**But :** Contrôler la qualité des données de marché Kraken (et sources associées) en **lecture seule** : fraîcheur, complétude, cohérence, anomalies — sans jamais modifier les données ni envoyer d'ordres.

---

## Quand déclencher

- Avant toute analyse/décision basée sur les données de marché.
- Après collecte (collector) pour valider l'artefact avant publication.
- Sur détection d'anomalie (spread anormal, gaps, prix aberrants).
- Demande explicite : "vérifie la qualité des données Kraken 15m".

---

## Principes fondamentaux

- **STRICTEMENT LECTURE SEULE** : aucune écriture sur fichiers de données, aucun ordre, aucune modification de la collecte.
- **Preuves d'exécution** : chaque contrôle produit un artefact JSON avec timestamp, métriques, empreinte SHA-256.
- **Fail-closed** : si une vérification ne peut pas s'exécuter (données manquantes, source indisponible), le statut est `DEGRADED` ou `FAIL`, jamais `OK` par défaut.

---

## Contrôles obligatoires

### 1. Fraîcheur (Freshness)
- **Entrée** : artefact `tel_snapshot.json` (ou `site/tel_snapshot.json` publié).
- **Vérification** : `age_seconds = now - snapshot.timestamp_ms/1000`.
- **Seuils** :
  - 15m : `age < 300s` (5 min) → `OK`, `300-900s` → `STALE`, `>900s` → `EXPIRED`.
  - 1h/4h/1d : seuils proportionnels.
- **Sortie** : `{ "timeframe": "15m", "age_seconds": 288, "status": "OK", "threshold_ok": 300, "threshold_warn": 900 }`.

### 2. Complétude (Completeness)
- **Vérification** : tous les timeframes attendus présents (`15m`, `1h`, `4h`, `1d`).
- **Champs requis par timeframe** : `open`, `high`, `low`, `close`, `volume`, `timestamp_ms`, `source`.
- **Gaps** : détection trous > 2 intervalles manquants consécutifs.
- **Sortie** : `{ "timeframe": "15m", "expected_bars": 96, "actual_bars": 96, "gaps": 0, "status": "OK" }`.

### 3. Cohérence OHLC (OHLC Consistency)
- **Règles** : `high >= max(open, close)`, `low <= min(open, close)`, `volume >= 0`.
- **Vérification** : sur chaque barre de chaque timeframe.
- **Sortie** : `{ "timeframe": "15m", "checked_bars": 96, "violations": 0, "status": "OK" }`.

### 4. Spread / Qualité livre d'ordres (Order Book Quality)
- **Si disponible** : `bid`, `ask`, `spread_bps = (ask-bid)/mid*10000`.
- **Seuil** : `spread_bps < 50` (0.5%) pour `OK`, `50-100` → `WARN`, `>100` → `FAIL`.
- **Sortie** : `{ "bid": 0.00612, "ask": 0.00615, "spread_bps": 48.7, "status": "OK" }`.

### 5. Détection anomalies prix (Price Anomalies)
- **Règles** : variation > 20% sur 1 barre (sauf gap connu), prix = 0 ou négatif, volume = 0 sur barre non-gap.
- **Méthode** : z-score sur returns (|z| > 4) + seuils absolus.
- **Sortie** : `{ "timeframe": "15m", "anomalies": [], "status": "OK" }`.

### 6. Provenance & Empreinte (Provenance & Fingerprint)
- **Vérification** : `collection_id` présent, `sha256` des données brutes calculable et cohérent.
- **Sortie** : `{ "collection_id": "abc-123", "sha256_raw": "ca7f46ee...", "status": "OK" }`.

---

## Agrégation finale

**Statut global** = pire statut parmi tous les contrôles (priorité : `FAIL` > `EXPIRED` > `DEGRADED` > `WARN` > `STALE` > `OK`).

**Format sortie standardisée :**
```json
{
  "timestamp_ms": 1732027200000,
  "source": "kraken",
  "symbol": "TEL/USDT",
  "overall_status": "OK",
  "checks": {
    "freshness": { "15m": {...}, "1h": {...}, "4h": {...}, "1d": {...} },
    "completeness": { "15m": {...}, ... },
    "ohlc_consistency": { "15m": {...}, ... },
    "spread_quality": { "15m": {...}, ... },
    "price_anomalies": { "15m": {...}, ... },
    "provenance": { "collection_id": "...", "sha256_raw": "...", "status": "OK" }
  },
  "sha256_report": "a1b2c3d4..."
}
```

---

## Entrées

- Artefact snapshot : `site/tel_snapshot.json` (publié) ou `artifacts/tel_snapshot_<timestamp>.json` (local).
- Optionnel : données brutes collector (`artifacts/raw/`) pour recalculer empreintes.
- Configuration seuils (optionnel, défauts ci-dessus).

## Sorties

- **Rapport de qualité** JSON (format ci-dessus) → `results/market_data_quality_<timestamp>.json`.
- **Empreinte SHA-256** du rapport.
- **Journal** : `.kilo/sessions/<id>/market-data-quality-log.jsonl`.
- **Statut exit code** : 0 = OK, 1 = WARN/STALE, 2 = DEGRADED/EXPIRED/FAIL.

---

## Permissions

- **Lecture seule** : `site/`, `artifacts/`, `results/`, `data/` (si existe).
- **Écriture** : **uniquement** `results/market_data_quality_*.json` et journal de session.
- **Interdits** : modifier `collector/`, `src/`, `site/tel_snapshot.json`, envoyer ordres, écrire sur sources de données.

---

## Exclusions (ne pas déclencher / ne pas faire)

- Ne pas collecter de données (rôle du `collector/`).
- Ne pas modifier les seuils de décision du détecteur (stratégie figée).
- Ne pas valider des données MEXC/KuCoin (seulement Kraken comme source de référence primaire).
- Ne pas déclencher si pas de snapshot disponible (bloquer + signaler).
- Ne jamais écrire hors `results/` et journal de session.

---

## Tests de validation

### Test positif — Snapshot OK
- `site/tel_snapshot.json` : 15m age 288s, 96 barres, 0 violations OHLC, spread 48bps, provenance OK.
- Rapport → `overall_status: "OK"`, exit code 0.
- Empreinte SHA-256 calculée et journalisée.

### Test positif — Données dégradées (STALE)
- Snapshot 15m age 600s (10 min), autres OK.
- Rapport → `overall_status: "STALE"`, exit code 1.
- Détail : `freshness.15m.status = "STALE"`.

### Test positif — Spread FAIL (cas réel MEXC)
- Spread 64bps > 50bps seuil.
- Rapport → `overall_status: "FAIL"`, exit code 2.
- Correspond au comportement live documenté (T53, T66).

### Test négatif — Pas de snapshot
- `site/tel_snapshot.json` absent ou vide.
- Skill → exit code 2, rapport `{ "overall_status": "FAIL", "error": "no_snapshot" }`.
- Ne pas inventer de données.

### Test sécurité — Lecture seule respectée
- Tentative d'écriture sur `collector/tel_collector.py` → refusée.
- Tentative d'envoi ordre → refusée.
- Aucune modification de `site/tel_snapshot.json`.

---

## Version

1.0

## Retour arrière

- Supprimer `results/market_data_quality_*.json` de la session échouée.
- Journal de session conservé pour audit.
- Aucune modification des données sources.

## Conflits connus

- Ne pas interférer avec le collector (`collector/tel_collector.py`) — lecture seule.
- Ne pas modifier les seuils de `src/agent_analysis.py` (stratégie figée, `PROTOCOLE_STRATEGIE_FIGE.md`).
- Utilise `autonomous-error-recovery` si erreur d'exécution (ex: JSON invalide).
- Complémentaire de `github-continuity` (vérifie artefact publié) et `safe-repo-change` (écriture seulement `results/`).