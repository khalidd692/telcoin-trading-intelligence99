# Superviseur Codex local TEL99

Depuis le dossier isolé, lancer dans PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\run_autonomous_loop.ps1
```

`RemoteSigned` s'applique au PowerShell lancé. Le superviseur requiert Python 3, Git, GitHub CLI et le CLI Codex natif pour les missions. Le lanceur recherche aussi le Python du runtime Codex et le CLI installé sous `.tel99-automation-state/codex-cli`. La recette utilise Codex CLI 0.170.0 et le sandbox Windows MXC.

Le superviseur synchronise #94 et les 20 entrées du backlog de #93, épinglé par SHA. L'option `-Once` fait un passage. L'option `-Demo` fait la recette locale et s'arrête. Une nouvelle recette isolée peut utiliser `-DemoAttempt 2` ou un autre numéro inutilisé. Relancer avec le même numéro conserve les preuves et évite de réexécuter les essais déjà validés.

## File GitHub

La file de départ est vide. Le backlog est un inventaire et ses statuts historiques ne valent pas une validation. Une entrée exécutable associe un identifiant du backlog à une issue ouverte de `khalidd692`, étiquetée `codex-local/mission`, affectée au compte unique indiqué par l'approbation. L'approbation locale est un tableau JSON dans `.tel99-automation-state/local-codex/approvals.json`, ou dans le fichier passé avec `-Approvals`. Chaque entrée contient `id`, `issue`, `assignee`, `issue_sha256` (SHA-256 de l'UTF-8 exact du corps retourné par l'API), `expires_at` (UTC `YYYY-MM-DDTHH:MM:SSZ`), `base_sha`, `path`, `objective` et `expected_sha256`. Le texte transmis à Codex est l'objectif de ce fichier local de confiance. Ce fichier reste hors Git.

Le pilote GitHub est limité aux nouveaux fichiers `docs/agents/codex-local-results/<nom>.md` dont le résultat attendu peut être vérifié par SHA-256. Le superviseur initialise un clone indépendant et coupe son remote avant d'exécuter Codex. Le worker peut lire, écrire et tester dans le clone avec `workspace-write`, `never` et les commandes réseau désactivées. Le superviseur vérifie ensuite que le diff porte uniquement sur le fichier approuvé et que le blob committé a l'empreinte prévue. Le dossier de preuve local inclut une fiche de PR. `PREPARED` signifie que le commit et cette fiche existent. Une dépendance attend une acceptation vérifiée par le registre.

Sur la branche d’intégration #104, les entrées exigent en plus `role: "codex"` et le marqueur d’approbation v1 de #104 confirmé par un commentaire GitHub récent, inchangé, du propriétaire. Une mission portant aussi le label de la file OpenHands est refusée. La prise s’appuie sur le verrou existant `active_mission_lock`, puis sur une réservation durable en CAS du même service. Le superviseur relit la propriété du verrou avant de lancer Codex et avant le commit. Sans accès HTTPS au KV de #94, la file reste en attente de coordination. Les deux paramètres d’accès sont ceux du module existant, `AUTOMATION_API_URL` et `AUTOMATION_KV_TOKEN`.

Les preuves de dépendance sont configurées dans `dependency_evidence`, une correspondance entre identifiant de dépendance et politique vérifiée. Chaque politique épingle `issue`, `issue_sha256`, `mission_digest`, `commit_sha`, `conversation_id`, `work_branch`, `criteria`, `verifiers` et `trusted_workflows` (identifiant de workflow vers SHA-256 du YAML). L’attestation est relue dans #94 et le vérificateur de #104 contrôle la référence GitHub, les octets du livrable et les jobs réels au SHA. Le rapport `ledger/github/admission.json` indique les propriétaires, les dépendances sans preuve et le motif d’exclusion de chaque tâche.

## Tickets de développement Codex pour #105

Un ticket distinct et authentifié de la file `codex-local/mission` peut admettre un contrat `kind: "code"` et un identifiant `CODEX105-…`. Il épingle le HEAD de `codex/native-v1-delivery-20261118`. Le champ `files` contient jusqu’à huit chemins Python exacts sous `scripts/agents/native/` ou `tests/`. Le fournisseur natif et l’initialisation du package restent réservés au chantier #105. Le test indépendant `test_file` doit exister à la base et son blob Git doit rester identique dans le commit. Les autres champs du contrat sont `id`, `issue`, `role`, `assignee`, `base_sha`, `objective`, `priority`, `dependencies` et `expires_at`. La ligne `codex-contract-sha256: <empreinte>` couvre ces champs, `files` et `test_file` via `local_code.contract_digest` et fait partie du ticket authentifié.

Le superviseur vérifie les chevauchements dans les PR ouvertes avant le départ, bloque les suppressions et renommages, puis lance les tests dans le checkout propre du commit sous MXC en lecture seule. Le résultat contient les SHA de base et de tête, les chemins modifiés, le blob du test et le nombre de tests réussis. La fiche de PR et le commit sont préparés localement. Le résultat reste `PREPARED` en attente d’une preuve externe.

Le contrat peut épingler un `test_selector` sans caractères génériques pour sélectionner des tests compatibles avec le sandbox en lecture seule dans la suite indépendante. Un `supplemental_test` explicitement autorisé peut vérifier une nouvelle suite ajoutée dans le même commit. Les deux champs sont liés à l’empreinte approuvée. En mode code, l’empreinte exacte du corps peut rester absente lors de la préparation du fichier privé. L’approbation v1 authentifie alors le titre et le corps, et l’empreinte du contrat les lie aux options locales. Une empreinte brute fournie reste obligatoire à vérifier.

`-CodeDemo` exécute deux missions synthétiques de code séquentielles avec de vrais appels Codex. Il utilise le même verrou Windows que la file GitHub. Le contrôle d’accès au KV est disponible avec `-Preflight`. Il lit les métadonnées de version et le registre, sans prendre le verrou ni lancer Codex. `BLOCKED_KV` signale l’absence de configuration ou l’échec de lecture. `KV_READ_READY` laisse le CAS d’écriture à vérifier par une vraie prise.

## Reprise

Les modes GitHub et démo partagent le verrou Windows et gardent chacun leur dossier d’état sous `.tel99-automation-state/local-codex`. `events.jsonl` donne la chronologie, le `ledger` donne le dernier état par mission. Après un arrêt, relancer dans le même mode. Au checkpoint `WORKER_EXITED`, la vérification et la préparation du commit reprennent sans nouvel appel Codex. Une mission `RUNNING` au redémarrage devient `INTERRUPTED` et conserve son clone pour réconciliation. Les tâches indépendantes continuent. Le quota est relu avant chaque appel modèle. `WAITING_QUOTA` arrête le lot et autorise une nouvelle lecture au prochain lancement. `AWAITING_HUMAN` indique un problème d'autorisation ou de coordination. `BLOCKED` et `FAILED` conservent les artefacts pour diagnostic.

Pour la bascule, exécuter d’abord `-Preflight` dans le shell qui recevra la configuration KV existante. Attendre la fin d’une éventuelle mission du superviseur en place en vérifiant son journal, son PID et son processus enfant. À partir de cette version, créer `github/stop.request` sous le dossier d’état demande un arrêt entre deux lots. La version `f508fb08` antérieure à ce signal doit être arrêtée dans sa console ou, si elle tourne en arrière-plan, seulement après avoir vérifié qu’elle est en attente et identifié son processus Python précis. Après la sortie du processus et la libération du verrou, archiver le signal d’arrêt s’il existe, puis utiliser `-Once` pour le premier lancement avec la configuration KV. Conserver le même dossier d’état pour la reprise.

## Activation Upstash Redis Free

Depuis le clone d’intégration, exécuter

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\activate_upstash_free.ps1
```

Le script ouvre la console Upstash. Créer une base Redis dédiée **Free**, sans moyen de paiement, avec **Auto Upgrade** et **Eviction** désactivés. Le jeton REST lecture-écriture est saisi dans une invite masquée, puis chiffré avec DPAPI pour l’utilisateur Windows local seulement si le précontrôle passe. L’URL et le jeton chiffré restent dans le dossier d’état hors Git. Les deux backends sont exclusifs. [Tarif Free](https://upstash.com/pricing/redis) · [Paramètre Auto Upgrade](https://upstash.com/docs/redis/features/auto-upgrade)

Le précontrôle `KV_CAS_READY` exige un gagnant unique entre deux clients REST, une réservation durable, un refus d’écriture et de libération pour l’ancien propriétaire, puis la reprise du CAS. Le verrou expire côté Redis. Le jeton de propriétaire et la valeur précédente sont vérifiés dans un seul script Lua pour chaque mutation de la réservation. Si un résultat de worker reste ambigu, la réservation reste en place et la tâche n’est pas rejouée.

Le namespace Redis sert la file réservée à Codex Windows. Un processus cloud qui utilise un autre KV reste hors de ce verrou. La file refuse les tickets également étiquetés OpenHands. Ce choix évite le détournement du dépôt GitHub en registre de baux. GitHub expose la création de référence et le fast-forward, alors que cette intégration a besoin d’un CAS sur le propriétaire et le résultat sous un même TTL. [CAS Lua sur REST](https://upstash.com/blog/lua-scripting-on-upstash-redis-atomic-operations-over-http) · [Références GitHub](https://docs.github.com/en/rest/git/refs)

## File GitHub, routeur et moteur natif

En l’absence de manifeste privé, le superviseur découvre les nouveaux tickets de la file contenant une ligne `tel99-contract:v1 <JSON>`. Le contrat lie le numéro réel, le périmètre, les dépendances et les limites au corps authentifié. Les tickets historiques sans contrat intégré continuent de dépendre de leur manifeste privé. `-DiscoverOnly` affiche les demandes en attente sans worker. `-AwaitIssue 112` attend l’approbation de ce seul ticket jusqu’à son expiration, exécute un passage puis sort. Le verrou Windows reste commun à tous les modes d’exécution. Le passage ordinaire poursuit les autres contrats admis et rapporte les résultats `PREPARED` dans #94 avec un marqueur qui évite de publier deux fois le même SHA.

Les nouveaux contrats de code épinglent un `routing_profile` du routeur #108. Le catalogue et les limites sont relus auprès d’App Server. Le modèle et l’effort sont journalisés avant le départ, et le résultat est rapproché des empreintes du diff et de la vérification locale. Une interruption avec exécution incertaine bloque la relance.

Le contrat natif #110 épingle le SHA du moteur et l’image Docker, avec une consigne synthétique fixe et un appel maximum. Le claim Upstash précède l’appel. Après un worker terminé ou un checkpoint récupérable, le superviseur consulte `status` et rejoue le vérificateur Docker sans appel modèle. Les deux artefacts vérifiés sont committés seuls. Un résultat local `PREPARED` doit ensuite recevoir une attestation externe conforme à #94.

Le nouvel essai de format conserve le même moteur et le même budget. Sa consigne fixe précise que les deux blocs de réponse commencent par le nom exact du fichier attendu par le parseur. Le choix de consigne est lié à l’empreinte de l’approbation. Une mission dont l’appel précédent a échoué conserve son claim terminal et ne peut pas autoriser cet essai.

Une publication `PREPARED` dans #94 exige une relecture du CAS correspondant au numéro de ticket, au SHA et à l’empreinte d’approbation. Le mode d’attente peut repoller un blocage de coordination ou de dépendance avant démarrage, jusqu’à expiration du contrat. Les checkpoints qui impliquent une exécution incertaine restent traités séparément et ne déclenchent aucun second appel modèle.

## Session supervisée et diagnostic natif

Lancer volontairement une session bornée depuis ce clone.

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\run_autonomous_loop.ps1 -SessionMinutes 30
```

Dans un autre terminal, remplacer `-SessionMinutes 30` par `-Status` pour lire le PID, le heartbeat et le dernier état. Un heartbeat arrêté ou périmé ne fait pas présumer un worker actif. Utiliser `-RequestStop` pour demander la sortie entre deux missions. Le signal est archivé à la sortie, ce qui permet un redémarrage volontaire. Une session ne démarre pas de nouvelle mission après sa limite ou après une demande d’arrêt.

Le moteur natif utilise un stockage de staging court sous le dossier d’état Windows. Le checkout Git et les preuves historiques restent en place. La sortie JSON terminale conserve uniquement les champs autorisés, dont le verdict, les compteurs, les empreintes et les résultats des contrôles. Les états `BLOCKED`, `PREPARED` et d’attente remontent dans #94 de façon idempotente. L’échec de syntaxe sur une écriture `__pycache__` est enregistré comme `BYTECODE_IO`. La publication conserve la distinction entre un résultat local et une preuve externe.
