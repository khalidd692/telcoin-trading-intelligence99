# Routeur de modèles Codex pour le superviseur Windows

Le contrat s'applique au point d'appel de `codex exec` dans `scripts/agents/automation/local_codex.py`. Il couvre le pilote de la [PR #106](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/106) et son [raccordement de coordination au commit f508fb08](https://github.com/khalidd692/telcoin-trading-intelligence99/commit/f508fb08118c1d711a45faf926a8032426db0b45). L'admission, le claim CAS, le verrou Windows, le clone de mission, le checkpoint `WORKER_EXITED` et la preuve d'acceptation restent gérés par le superviseur.

## Politique

- `routine` choisit Luna Low pour un travail répétitif. Le repli livré est Sol Low.
- `coding` choisit Sol Medium pour la programmation et les tests courants.
- `debug` commence par Sol High. Un échec confirmé par un test indépendant permet Astra High.
- `critical` commence par Astra High pour l'architecture critique, la sécurité défensive ou la concurrence CAS.
- Astra Extra High (`xhigh`) exige un échec de test sur Astra High et le SHA-256 d'un diagnostic qui justifie un effort supplémentaire. Trois tentatives maximum par mission, avec au plus un lancement par couple modèle/effort.

Le profil appartient à l'enveloppe approuvée ou à la politique locale de confiance. Choisir le profil d'après les critères d'acceptation, puis l'inclure dans l'empreinte d'approbation. `Policy` accepte un ordre de replis explicite par profil, une réserve de quota supérieure ou égale à 10 % et un plafond de une à trois tentatives. Un repli conserve l'effort du profil et n'est éligible que si le catalogue annonce le couple. Par défaut, l'indisponibilité de Sol ou Astra sur leurs profils conduit à `BLOCKED_MODEL`. Un refus d'exécution, un timeout, une interruption ou un quota atteint ne déclenchent aucun repli automatique.

## Raccordement pour Codex 1

1. Réutiliser le verrou et la validation de #106. Dans le clone de mission préparé, sous le même claim et avec le même environnement `model_environment()` que le worker, recharger le checkpoint du routeur depuis le registre existant. Pour une mission neuve, appeler `new_checkpoint(task_id, approval_sha256, profile)`. Vérifier l'identifiant, le profil et l'empreinte avec l'enveloppe avant chaque tentative.
2. Appeler `read_snapshot(cli, workspace, env)` immédiatement avant le lancement. La connexion App Server lit `account/read`, les pages visibles de `model/list`, puis `account/rateLimits/read`. Le choix exige un abonnement ChatGPT reconnu, l'absence attestée de crédits et des mesures des fenêtres 5 h et 7 j datant d'au plus 30 secondes. Le contrôle inclut toute limite déclarée pour le modèle. L'absence d'une fenêtre, y compris sur un plan qui n'expose pas de limite 5 h, conduit à `WAITING_QUOTA` avec la politique livrée.
3. Appeler `prepare_attempt(checkpoint, approval_sha256, workspace_head_sha, snapshot, policy=policy)`. Pour Extra High, transmettre aussi `escalation_evidence_sha256`. Persister atomiquement `plan.checkpoint` sous le claim existant avant d'utiliser `plan.exec_args`. Insérer ces arguments avant le dernier `-` de la commande existante. Ils ajoutent `--model`, `-c model_reasoning_effort=...`, OpenAI standard, l'authentification ChatGPT et `--json`. Conserver `--ignore-user-config`, le sandbox, l'absence d'approbation interactive et les restrictions réseau du pilote. Conserver le clone, les commits et les preuves des essais précédents pour tout nouvel essai autorisé.
4. Enregistrer la sortie du worker et sa durée mesurée, puis lire `read_snapshot(cli, workspace, env, include_catalog=False)` avec le même compte. Si cette lecture échoue, transmettre `quota_after=None`. Au checkpoint existant, appeler `record_result(plan.checkpoint, approval_sha256, plan.attempt["number"], status, duration_ms=..., artifact_sha256=..., test_evidence_sha256=..., quota_after=..., exec_jsonl=...)`. Les statuts `tests_passed` et `tests_failed` exigent l'empreinte du livrable et d'une preuve de test indépendante. Utiliser `worker_error` pour une erreur d'exécution. Persister le résultat et continuer la finalisation de #106 sous le même claim.
5. Au redémarrage, un essai `running` renvoie `RECONCILE_ATTEMPT`. Réconcilier d'abord le processus, le workspace et la preuve de sortie, puis terminer l'essai existant. Transformer `WAITING_QUOTA` en arrêt du lot comme dans #106. Remonter `BLOCKED_AUTH` et `BLOCKED_MODEL` au registre. Traiter `BLOCKED_CHECKPOINT` comme une réconciliation obligatoire. `ROUTE_FINISHED` et `ATTEMPT_LIMIT` terminent le routage de la mission. Les décisions du routeur ne confèrent aucune acceptation GitHub.

## Preuve de consommation

Le checkpoint conserve le couple demandé, le commit de départ, le motif, les fenêtres de quota horodatées avant et après, la durée et les empreintes de résultat. `codex exec --json` peut fournir un ID de session, un événement de fin et les tokens d'entrée, d'entrée en cache et de sortie. Le module conserve ces champs et exclut le texte des événements. Le quota du compte peut évoluer du fait d'une autre session ou d'une réinitialisation. Les deux mesures ne constituent donc pas une facture ni une attribution exclusive à la mission.

Si le superviseur dispose d'une télémétrie locale fiable qui confirme les réglages de la même exécution, transmettre `effective_settings={"model": ..., "effort": ..., "source_sha256": ...}`. Un écart termine l'essai en `worker_error`. Sans observation, `effective_settings` reste nul et les réglages demandés restent visibles séparément dans le checkpoint.

## Recette

> Exécuter depuis la racine du clone avec Python 3.12 ou le Python du runtime Codex.

```powershell
python -m unittest discover -s tests -p 'test_*codex*.py' -v
```

Les tests hors ligne enchaînent deux missions de fixture avec des réglages différents, simulent le catalogue et les quotas et vérifient le transport App Server dans un processus local. La commande passe 21 tests sur la base de #106 et 25 en présence du superviseur au commit `f508fb08`, dont les tests Windows de verrou et de CAS du pilote. Le CLI 0.170.0 a reconnu les options demandées en mode aide. Dans l'environnement de développement isolé, la lecture de configuration du CLI a échoué avec `Could not find home directory`. La disponibilité du catalogue du compte, l'exécution de deux missions approuvées et la consommation réelle restent à mesurer avec le superviseur raccordé et une session ChatGPT utilisable, sous le claim existant.

[Documentation App Server](https://developers.openai.com/codex/app-server) · [Options du CLI](https://developers.openai.com/codex/cli/reference) · [Configuration Codex](https://developers.openai.com/codex/config-reference)
