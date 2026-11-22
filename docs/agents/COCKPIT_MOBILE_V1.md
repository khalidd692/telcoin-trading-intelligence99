# Cockpit mobile V1

Interface française locale, en lecture seule. Elle réutilise l’état et les reçus du lanceur #149, les événements de `HandoffLedger`, le planificateur et le catalogue des douze rôles. La collecte paginée OpenHands de #79 reste une source en amont. Le cockpit charge uniquement des instantanés fournis localement. Le backend KV historique de #85 reste indépendant de cette interface.

## Démonstration

```sh
python -B -m scripts.agents.cockpit --demo
```

Ouvrir `http://127.0.0.1:8787/`. Les deux missions et leurs événements proviennent d'un vrai superviseur local avec fournisseur scripté, dans un état temporaire. Le quota et les PR restent `INCONNU` dans cette démonstration. Pour la mise en page Android, ouvrir le navigateur avec une largeur de 360 ou 412 pixels.

## Lire ses instantanés

```sh
python -B -m scripts.agents.cockpit --repository owner/repository \
  --status /chemin/status.json --plan /chemin/plan.json \
  --handoffs /chemin/ledger-v1.json --pulls /chemin/pulls.json
```

Tous les fichiers sont facultatifs. `status.json` est la sortie JSON du mode `status` Kilo ou Hermes. `plan.json` est la sortie du planificateur. `ledger-v1.json` est le document existant `handoff/ledger-v1`. `pulls.json` est une liste locale extraite de GitHub avec les champs `number`, `html_url`, `state` et `draft`. Réexporter les instantanés selon le besoin. Le bouton Actualiser effectue une lecture et une attente maximale de cinq secondes.

« Configuré » vient du catalogue. « Planifié » vient d'un plan valide. L'activité d'exécution d'un rôle reste `INCONNU` si une source ne la prouve pas. La date est celle fournie par le superviseur. Les budgets affichés sont des estimations, avec le quota affiché séparément lorsqu'il est numérique.

Le serveur écoute sur loopback, expose trois fichiers UI et une projection JSON bornée. Les identifiants, états et liens sont filtrés. Les champs texte libres, chemins locaux et artefacts complets sont omis. Aucun contrôle de mission et aucune clé côté navigateur.

```sh
python -B -m unittest tests.test_agent_cockpit
```
