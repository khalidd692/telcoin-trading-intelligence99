# TEL99 — Mise en service du 25 novembre 2026

## Verdict

**GO pour le cockpit local et la préparation de la recette. NO-GO pour déclarer l’autonomie GitHub opérationnelle.** Le contrôleur [#211](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/211) attend la signature du propriétaire. Les deux missions postérieures, leurs approbations, les résultats et l’endurance restent à exécuter.

## Réconciliation des preuves

- `TEL99_FINAL_20261125` reste sur `04169a04`, avec ses modifications et fichiers non suivis. Le backend SDK et ses tests sont conservés dans ce worktree. `TEL99_SDK_TEST` est un dossier de validation distinct.
- Le benchmark existant `TEL99_FINAL_EVIDENCE_20261125/benchmark_models_and_backends.json` a pour SHA-256 `62e0311341d6486b4440b9656f698b481befb7a59a9c0d2c3ecacd6879dd821a`. Sur une comparaison par backend, Ollama natif et le SDK obtiennent chacun une acceptation en 50,594 s et 262,875 s respectivement. Sur deux essais par modèle, Gemma 4 obtient deux acceptations, Qwen 7B zéro et Qwen 9B une. Ces petits échantillons guident le choix local. Le SDK démontre des capacités d’intégration sur des exercices séparés, avec un coût en temps accru sur le chemin quotidien testé. Sa promotion est différée.
- Les traces d’endurance locales `hour_timeseries.jsonl` s’arrêtent à 185,39 s. Les checkpoints conservés montrent trois acceptations, un échec de réparation et un crash passé à `AWAITING_HUMAN`. Cette preuve historique est partielle.
- Diagnostic actuel du chemin de production. GitHub, Ollama et Docker disponibles. Le superviseur existant utilise un verrou de session pour le dossier d’état et exécute ses campagnes en série. Les contrats #211 imposent Ollama loopback et la vérification Docker. L’exécution réelle indépendamment de l’IDE reste à observer après admission.
- Cockpit à 01:05:08 UTC. L’ancien PID 29648 avait `/health` en 404. Le nouveau PID 5780 écoute en loopback sur 8765 et a rendu `{"ok":true}` ainsi qu’un snapshot JSON. Aucun worker de campagne et aucun bail actif observés avant le remplacement. L’état de #205 a été lu uniquement.
- 26 tests ciblés réussis avec `python -B -m unittest tests.test_github_owner_feed tests.test_github_multi_mandate_session tests.test_autonomous_platform_e2e`.

## Recette #211

La branche `agents/tel99-code-base-coordination-211` est épinglée au SHA `402d38c81028b6779d59369aaaf57ef5f774af17`. [Contrats sources](RECETTE_COORDINATION_211.json). L’ordre fonctionnel est A puis B. Le second contrat vise les collisions entre contrôleurs sur un même chemin Windows. Le protocole exige que les deux contrats ciblent des fichiers différents.

- A, propriété du bail, SHA-256 `9c703ae1c46248111d7628ace1eeb59bbd0757064448b46c5c52d9e692d48834`. Docker a échoué sur l’assertion attendue à la ligne 25.
- B, collision Windows, SHA-256 `b2b2a67d17cea652afd58a3569f255ad98d5ee1ab8fc45951a4e4e2c65f80b04`. Docker a échoué sur l’assertion attendue à la ligne 20.

Le propriétaire publie le bloc affiché dans le corps de #211 en nouveau commentaire immuable. Après vérification de l’auteur, de la date et du SHA-256 du commentaire, créer deux issues `enhancement` portant la ligne `tel99-code-campaign: <ID-commentaire>`. Les deux dates de création doivent suivre celle du commentaire. Les valeurs `212` et `213` dans le fichier source sont des emplacements provisoires. Remplacer ces valeurs par les vrais numéros et renseigner `mandate_comment_id` dans une copie de la spécification. Le générateur existant produit alors les deux blocs d’approbation en une fois, avec les mêmes empreintes de contrat.

```powershell
python -B -m scripts.agents.automation.proposal_builder --spec $specRecette --output $dossierApprobations
```

Le propriétaire relit et publie les deux approbations, puis active le marqueur sur une ligne seule dans le corps de #211. Laisser le marqueur inactif durant la préparation évite qu’un contrôleur incomplet bloque la découverte. Lire le flux pour prouver la découverte de #211, puis construire un manifeste limité à ce seul contrôleur avec l’identifiant et le SHA-256 du commentaire réellement relus. Cette restriction d’exécution préserve les anciens reçus et exclut #205, #206 et #207.

## Commandes quotidiennes

Depuis la racine du worktree. Pour cette recette, `$manifest` désigne le fichier JSON du contrôleur #211 après admission. Utiliser le dossier d’état par défaut pour conserver le verrou unique et les reçus entre sessions.

```powershell
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Start -Manifest $manifest -ExitWhenDone -Minutes 60
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Status
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Leases
Invoke-RestMethod http://127.0.0.1:8765/health
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Stop
pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Recover
```

Après un arrêt volontaire, utiliser `Recover -ClearStop` seulement après réconciliation du worker et des baux, puis reprendre avec le même manifeste et le même état. Pour redémarrer le cockpit dans une console indépendante quand le port est libre, utiliser `pwsh -NoProfile -File scripts/agents/automation/tel99-agent.ps1 -Mode Cockpit -Port 8765 -AllowControls`.
