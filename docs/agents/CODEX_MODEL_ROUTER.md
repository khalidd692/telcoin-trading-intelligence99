# Routeur de modèles Codex pour le superviseur Windows

Le contrat s'applique au point d'appel de `codex exec` dans `scripts/agents/automation/local_codex.py`. Il couvre le pilote de la [PR #106](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/106) et la [branche CAS de Codex 1 au commit f374391d](https://github.com/khalidd692/telcoin-trading-intelligence99/commit/f374391d2482d33e1f2a8e708e6b7f2cfc1266d4), descendante de `2f351d7d` et de `f508fb08`. L'admission, le claim CAS, le verrou Windows, le clone de mission, le checkpoint `WORKER_EXITED` et la preuve d'acceptation restent gérés par le superviseur.

## Politique

- `routine` choisit Luna Low pour un travail répétitif. Le repli livré est Sol Low.
- `coding` choisit Sol Medium pour la programmation et les tests courants.
- `debug` commence par Sol High. Un échec confirmé par un test indépendant permet Astra High.
- `critical` commence par Astra High pour l'architecture critique, la sécurité défensive ou la concurrence CAS.
- Astra Extra High (`xhigh`) exige un échec de test sur Astra High et le SHA-256 d'un diagnostic qui justifie un effort supplémentaire. Trois tentatives maximum par mission, avec au plus un lancement par couple modèle/effort.

Le profil appartient à l'enveloppe approuvée ou à la politique locale de confiance. Choisir le profil d'après les critères d'acceptation, puis l'inclure dans l'empreinte d'approbation. `Policy` accepte un ordre de replis explicite par profil, une réserve de quota supérieure ou égale à 10 % et un plafond de une à trois tentatives. Un repli conserve l'effort du profil et n'est éligible que si le catalogue annonce le couple. Par défaut, l'indisponibilité de Sol ou Astra sur leurs profils conduit à `BLOCKED_MODEL`. Un refus d'exécution, un timeout, une interruption ou un quota atteint ne déclenchent aucun repli automatique.

## Raccordement pour Codex 1

1. Réutiliser le verrou et la validation de #106. Dans le clone de mission préparé, sous le même claim et avec le même environnement `model_environment()` que le worker, recharger le checkpoint du routeur depuis le registre existant. Pour une mission neuve, appeler `new_checkpoint(task_id, approval_sha256, profile)`. Vérifier l'identifiant, le profil et l'empreinte avec l'enveloppe avant chaque tentative.
2. Appeler `read_snapshot(cli, workspace, env)` immédiatement avant le lancement. App Server lit `account/read`, les pages visibles de `model/list` pour le provider OpenAI et `account/rateLimits/read`. Le libellé visible sert à choisir la famille. Le CLI reçoit uniquement la valeur exacte du champ `model` et un effort déclaré compatible. Des entrées contradictoires ou des candidats ambigus bloquent le choix. Les deux fenêtres partagées 5 h et 7 j doivent être connues depuis au plus 30 secondes, avec absence de crédits attestée. Le contrôle vérifie aussi les limites associées au modèle et celles dont l'association est inconnue. Un quota incomplet, épuisé ou incohérent conduit à `WAITING_QUOTA`.
3. Au point d'appel existant, appeler `plan, args = prepare_exec(args, checkpoint, approval_sha256, workspace_head_sha, snapshot, persist_route_checkpoint, policy=policy)`. Pour Extra High, passer aussi `escalation_evidence_sha256`. Le callback `persist_route_checkpoint` écrit le checkpoint atomiquement et de façon synchrone dans le registre existant sous le claim. Une exception d'écriture empêche le retour de la commande. L'adaptateur insère les arguments avant le dernier `-` et rejette les réglages concurrents. Conserver la vérification du claim (`fence()`) juste avant `call(args, ...)`, avec le même environnement déjà épuré, le sandbox et les restrictions réseau du pilote. Conserver le clone, les commits et les preuves pour tout nouvel essai autorisé.
4. Enregistrer la sortie du worker et sa durée mesurée, puis lire `read_snapshot(cli, workspace, env, include_catalog=False)` avec le même compte. Si cette lecture échoue, transmettre `quota_after=None`. Au checkpoint existant, appeler `record_result(plan.checkpoint, approval_sha256, plan.attempt["number"], status, duration_ms=..., artifact_sha256=..., test_evidence_sha256=..., quota_after=..., exec_jsonl=...)`. Les statuts `tests_passed` et `tests_failed` exigent l'empreinte du livrable et d'une preuve de test indépendante. Utiliser `worker_error` pour une erreur d'exécution. Persister le résultat et continuer la finalisation de #106 sous le même claim.
5. Au redémarrage, un essai `running` renvoie `RECONCILE_ATTEMPT`. Réconcilier d'abord le processus, le workspace et la preuve de sortie, puis terminer l'essai existant. Transformer `WAITING_QUOTA` en arrêt du lot comme dans #106. Remonter `BLOCKED_AUTH` et `BLOCKED_MODEL` au registre. Traiter `BLOCKED_CHECKPOINT` comme une réconciliation obligatoire. `ROUTE_FINISHED` et `ATTEMPT_LIMIT` terminent le routage de la mission. Les décisions du routeur ne confèrent aucune acceptation GitHub.

## Preuve de consommation

Le checkpoint conserve le couple demandé, le commit de départ, le motif, les fenêtres de quota horodatées avant et après, la durée et les empreintes de résultat. `codex exec --json` peut fournir un ID de session, un événement de fin et les tokens d'entrée, d'entrée en cache et de sortie. Le module conserve ces champs et exclut le texte des événements. Des événements de fin multiples rendent la mesure de tokens indéterminée. Interpréter les variations de quota à l'échelle du compte, qui peut aussi servir à d'autres sessions ou changer de fenêtre.

Si le superviseur dispose d'une télémétrie locale fiable qui confirme les réglages de la même exécution, transmettre `effective_settings={"model": ..., "effort": ..., "source_sha256": ...}`. Un écart termine l'essai en `worker_error`. Sans observation, `effective_settings` reste nul et les réglages demandés restent visibles séparément dans le checkpoint.

## Recette

La découverte App Server lit au plus 20 pages de 50 entrées et accepte des curseurs d’au plus 1 024 caractères. Les deux tubes du sous-processus utilisent les entrées-sorties non bloquantes de Python 3.12 avec une échéance globale de 25 secondes. Le tampon contient au plus 524 289 octets et le transport refuse les trames de plus de 524 288 octets. Une trame hors limite, un JSON hors contrat ou une page trop longue interrompt la découverte avant le lancement. Les libellés de famille avec espace ou tiret sont reconnus. Le modèle exécuté reste l’identifiant exact déclaré dans le champ `model`.

Les essais hors ligne exercent des sous-processus Python qui imitent App Server. Ils couvrent les notifications en rafale, une trame trop longue, un JSON de type invalide, un enfant qui cesse de lire et une sortie héritée par un descendant. Les tests de pagination vérifient qu’une page de 51 entrées et un curseur hors limite sont refusés avant la lecture du quota. Les règles de réserve et de réconciliation s’appliquent à tout lancement.

> Exécuter depuis la racine du clone avec Python 3.12 ou le Python du runtime Codex.

```powershell
python -m unittest discover -s tests -p 'test_*codex*.py' -v
```

Sur Windows 11 et Python 3.12.14, la commande passe 28 tests sur la pile #106 (`936ef0ba`). La suite composée du routeur, du superviseur et de la passation CAS passe 72 tests sur `2f351d7d` et 73 sur `f374391d`. Aucun test ciblé ignoré. La recette intercepte `local_codex.call` au niveau du sous-processus et vérifie deux missions de fixture aux réglages différents, la persistance préalable, le timeout et la reprise sans deuxième appel pour la mission interrompue.

Le CLI 0.170.0 expose `--model`, `--config` et `--json` dans `codex exec --help`. Dans l'environnement épuré du pilote, `codex login status` rend `Could not find home directory` et App Server rend `BLOCKED_MODEL` à `initialize`. Avec un répertoire vide transmis comme `CODEX_HOME` au seul processus enfant de diagnostic, le CLI indique `Not logged in` et App Server rend `BLOCKED_AUTH` à `account/read`. Le répertoire utilisateur du profil Windows principal reste hors de cette manipulation. La correction sûre consiste à exécuter la recette dans le contexte Windows autorisé qui résout déjà son profil Codex authentifié à ChatGPT. Vérifier `login status` et relire catalogue et limites dans l'environnement exact du worker avant d'interpréter les résultats. Le profil vide sert uniquement au diagnostic de résolution du répertoire.

Le catalogue du compte et les quotas réels n'ont pas été lus depuis Codex 2. Codex 1 doit vérifier les métadonnées du compte et faire la recette sur deux tickets effectivement approuvés sous le claim du superviseur. Le journal expurgé associe pour chaque ticket le SHA, le couple demandé, les réglages effectifs si observables, le quota avant/après et le verdict indépendant.

[Documentation App Server](https://developers.openai.com/codex/app-server) · [Options du CLI](https://developers.openai.com/codex/cli/reference) · [Configuration Codex](https://developers.openai.com/codex/config-reference)
