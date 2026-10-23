# Rapport externe — Claude
**Projet :** `khalidd692/telcoin-trading-intelligence99`  
**Statut :** avis externe non vérifié indépendamment  
**Source :** rapport transmis par l'utilisateur  
**Date d'enregistrement :** 2026-10-23  
**Important :** Claude indique avoir consulté uniquement la page d'accueil et le README, sans lire le code ni les workflows. Les éléments non explicitement vus sont des hypothèses à confirmer.

---

## Rapport original

**Limite d'accès : je n'ai pu lire que la page d'accueil et le README du dépôt.** GitHub bloque l'accès automatisé aux sous-pages (`src/`, `tests/`, workflows). Je n'ai donc vu aucun code, aucun test et aucun workflow. Je ne peux pas faire l'audit A fichier par fichier sans inventer, ce que tu m'interdis.

**1. Faits vérifiés (README et racine du dépôt)**
- Le dépôt est public, la branche `main` compte 49 commits, avec 1 issue et 1 PR ouvertes.
- Le dossier racine contient `.github/workflows`, `deploy/cloudflare-relay`, `docs`, `site`, `src`, `tests`.
- Le README décrit un moniteur en lecture seule : MEXC (ticker et bougies 15 min), prix KuCoin en simple comparaison, EMA 12/26/50, RSI, ATR, âge de bougie, volume. Les statuts sont ATTENDRE et SURVEILLER, avec fail-closed, un cron de 15 min et aucun backtest.
- **Écart à vérifier :** le README ne mentionne ni `agent_analysis.py`, ni `alert_state.py`, ni `publication_cadence.py`, ni le multi-timeframes. Il n'y a pas non plus de dossier `collector/` à la racine. Soit le README est obsolète, soit ces chemins sont ailleurs.

**2. Angles morts probables (hypothèses, à confirmer dans le code)**
1. Aucun mécanisme externe ne te prévient si le système lui-même s'arrête. Les crons GitHub sont retardés ou sautés, il faut un heartbeat avec un seuil d'absence (gravité haute, probabilité haute).
2. Les bougies viennent d'une seule source (MEXC). KuCoin ne sert qu'au prix, donc il n'y a pas de recoupement des bougies ni de contrôle de leur alignement horaire.
3. Il n'existe aucun journal « signal → résultat à 1h/4h/24h ». Sans lui, la valeur de SURVEILLER n'est pas mesurable, et ton verdict historique « PAS D'EDGE » reste la seule mesure disponible.
4. Les exécutions concurrentes ne sont peut-être pas protégées. Vérifier `concurrency:` dans `monitor.yml`, ainsi que les commits d'état et de publication.
5. Le carnet d'ordres et les transactions sont absents du pipeline décrit. Ton `tel_orderbook.py` existe séparément, donc il faut l'intégrer et non le réécrire.
6. Les permissions du workflow (`permissions:` explicites, secrets) sont à auditer.
7. Les dérives de schéma d'API et la détection de bougie non clôturée par horodatage sont à tester.
8. Pas de LLM aujourd'hui, donc pas d'injection de prompt pour l'instant. Le risque apparaîtra avec les actualités ou le sentiment.

**3 à 5. Architecture recommandée (recommandation)**
Un seul pipeline déterministe, avec une couche LLM optionnelle et en lecture seule :

`collecte → validation (fail-closed) → moteur quantitatif → journal des signaux → [LLM : explication seule] → alerte` ; `superviseur indépendant (heartbeat)` en parallèle.

- **Conserver :** la collecte, la validation et le fail-closed.
- **Ajouter :** un journal append-only (JSONL dans le dépôt suffit), un évaluateur de résultats, un watchdog externe.
- **Pas d'agents multiples.** Le LLM ne décide jamais, il explique des chiffres déjà validés.

**6 à 8. Tests, plan et coûts**
- **Tests prioritaires :** données périmées, bougie non clôturée, exchanges en désaccord, exécution double, panne API simulée, heartbeat manquant.
- **Étape 1 (coût nul) :** heartbeat, `concurrency`, journal des signaux.
- **Étape 2 (coût nul) :** évaluation hors échantillon, intégration du carnet d'ordres.
- **Étape 3 (API, quelques euros par mois) :** LLM d'explication, seulement si les étapes 1 et 2 montrent une valeur.

**9. Incertitudes :** le contenu réel de `src/`, la couverture des tests, l'état de l'issue et de la PR ouvertes, et le canal d'alerte actuel.

**10. Construire en premier :** la supervision, puis le journal d'évaluation. **À ne pas construire maintenant :** agent autonome, récupération automatique, multi-LLM, base de données.

Claude demande ensuite que le contenu de `monitor.yml`, `src/agent_analysis.py` et `src/alert_state.py` soit fourni afin de transformer les hypothèses en constats sourcés.

---

## Notes de synthèse (à compléter après comparaison)

- **Convergences provisoires avec Gemini :** priorité à la fiabilité des données et à la supervision; moteur quantitatif déterministe avant LLM; mémoire/évaluation des alertes; pas de multi-LLM au départ.
- **Différences avec Gemini :** Claude propose un journal append-only JSONL et un watchdog externe comme premières étapes peu coûteuses; Gemini recommande plus tôt une base SQLite/Turso et une ingestion WebSocket continue.
- **Faits à vérifier dans le dépôt :** fréquence effective du cron, vrai contenu et état des chemins mentionnés, présence d'un carnet séparé, protection de concurrence, permissions GitHub Actions, existence d'un journal de résultats et d'un canal d'alerte.
- **Précaution :** ne pas considérer comme établis les constats basés seulement sur README ou sur l'architecture décrite.
