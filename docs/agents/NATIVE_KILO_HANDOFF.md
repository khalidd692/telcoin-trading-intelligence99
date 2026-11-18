# Raccordement du moteur natif au superviseur #106

Le moteur de la [PR #105](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/105)
produit les fichiers, exécute les contrôles métier et publie le journal local.
Le [superviseur #106](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/106)
reste responsable de l’admission GitHub, du clone isolé, du suivi et de la
validation externe. Son pilote au SHA `936ef0ba2e3d4448bd09c5e54b9a0246df2321f2`
admet un fichier de preuve Markdown au chemin et au SHA attendus. Le raccord
ci-dessous nécessite une évolution ultérieure de son exécuteur.

## Contrat proposé

1. Le superviseur contrôle l’autorisation authentifiée, la date de validité,
   l’attribution et le SHA-256 exact de l’objectif approuvé. Il réutilise
   l’`Envelope` existante, avec `mission.id` pour l’identifiant de tâche,
   `envelope_id` comme `request_id` stable et le projet et les limites dans le
   contexte approuvé. Chaque rediffusion conserve cet identifiant.
2. Le superviseur réserve le `request_id` via `Inbox.receive()` et le CAS
   de `KvStore` de #104, avec le même `receiver_id` pour tous les exécuteurs
   natifs. Seul le détenteur du claim appelle la CLI. Si le CAS est absent
   ou échoue, la mission reste en attente. Après interruption ou ACK perdu,
   consulter `status` et le claim avant toute relance.
3. Dans un clone au SHA approuvé, invoquer la commande native décrite dans le
   [guide de démarrage](DEMARRAGE_NATIVE_V1.md), via un tableau d’arguments.
   Passer un projet approuvé, un `mission_id` stable dérivé du `request_id`,
   les chemins privés `--state` et `--memory`, le budget, l’image épinglée et
   le texte approuvé à `--mission`. Les chemins, le profil, le budget et les
   paramètres fournisseur viennent de la configuration de confiance du
   worker. L’option `--synthetic-data` requiert une mission synthétique
   approuvée. Conserver le même répertoire d’état lors d’une reprise locale.
4. Lire le JSON et le code de sortie de `run` (`0` pour `PASS`, `2` pour refus,
   `3` pour échec de validation). Vérifier `status`, `artifact_integrity`,
   la liste exacte des fichiers et leurs SHA-256. Rejouer `verify-task-app`
   dans un processus distinct avec l’image épinglée. Relier la preuve au
   `request_id`, au SHA de l’objectif, au SHA du clone et aux fichiers
   vérifiés. Un `PASS` local permet `PREPARED`. L’acceptation authentifiée et
   la preuve d’intégration du CAS restent requises pour `ACCEPTED`.

Le raccordement devra démontrer deux appels concurrents pour un seul claim et
une seule exécution, puis une reprise après ACK perdu sans nouvel appel au
modèle. Le lot fournisseur livre l’interface CLI et le journal nécessaires à
cette recette. La coordination distribuée avec #106 reste à vérifier.

## Recette réelle du 18 novembre 2026

Le catalogue anonyme `GET https://ai-gateway.kilo.ai/api/v1/models` a renvoyé
HTTP 200 à 21:42:08 UTC. L’entrée `kilo-auto/free` indiquait `isFree=true`,
`mayTrainOnYourPrompts=true` et zéro sur les huit champs de `pricing`.
SHA-256 du corps de ce relevé préliminaire
`7c95ce94fea4b0fa5280d02e0ba924efac8e9cc3fe5ade3eae1c89c3c5457c7b`.
Sources de référence. [Conclusion OpenHands](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94#issuecomment-6991245321),
[documentation Kilo](https://kilo.ai/docs/gateway/models-and-providers).

Le moteur natif a lancé trois `POST /api/v1/chat/completions` anonymes avec
`kilo-auto/free`. Chacun a renvoyé HTTP 200, `usage.cost=0` et
`model=nvidia/nemotron-3-ultra-550b-a55b:free`. Le catalogue revérifié avant
chaque appel conservait l’indicateur d’entraînement et le même SHA-256
`ec7e8217dc15b3903420a8f3880e86b7c7d28daa78c300bbd9d216483b367c96`.

- `kilo-tasks-live01`, 21:52:39 UTC, `FAIL`, un appel. Le README extrait
  s’arrêtait avant les exemples, ce qui est cohérent avec une clôture de
  bloc Markdown imbriquée. `tasks.py` a passé les six contrôles
  lors du rejeu indépendant. SHA-256 du corps HTTP
  `df7acfa4b957e52f22d34bf836222b43f09bd5cb715282c3553cd50edc206ef4`.
- `kilo-tasks-live02`, 21:56:01 UTC, `PASS`, deux appels avec
  `--quota 13 --max-repairs 1`. La consigne demandait cinq commandes fictives
  en texte simple. À la première tentative, l’extracteur ne reconnaissait
  aucun des deux fichiers. SHA-256 du corps HTTP
  `b35d5909b84de287868f6ad1011acb12d8d59288bdb6aeff8a0cbb664d389e49`.
  La réparation automatique a fourni les deux fichiers et validé la syntaxe
  ainsi que les six contrôles métier. SHA-256 du corps HTTP
  `5250919b5d7723f0d22f2f6a2adb7c252abeaf53b7885973966894a3b625296f`.

Les corps HTTP complets et les prompts ne sont pas conservés par le moteur.
L’archive contient les deux fichiers du `PASS` avec leurs octets d’origine.
SHA-256 du ZIP `3f760857a138f93f642a94138df4b23a3b8cfe2e60ed7c860553436f3bbcaf26`.
[Télécharger les deux livrables synthétiques](native-kilo-20261118-artifacts.zip).

- `tasks.py` — `8007704b4adca570ff7808c0ab0857cde36b4fae72712f9ddd6244b2d027cc1c`.
- `README.md` — `6a8367d3d04cc434a6e2db878a2b9e16cc709b08a54a65ff68c143c5860b108b`.
- Contrôles métier et image — `3579a9ed5580e45ee8e11532f927d6f0cfe277460b06234cefb1f7863cafeded`.

Après le `PASS`, `Get-FileHash` et un contrôle direct du ZIP avec `zipfile`
ont retrouvé les deux empreintes. Les cinq commandes du README ont été
vérifiées séparément. `verify-task-app` a rejoué les six contrôles dans un
nouveau conteneur et a renvoyé `exit=0` avec la même empreinte de `tasks.py`.
`status` a renvoyé `artifact_integrity=matched`. La reprise de la même
mission sans quota a renvoyé `reused=true` et `provider_calls=0`.

Pour rejouer sans fournisseur, extraire le ZIP dans un répertoire neuf et
exécuter les commandes suivantes depuis le dépôt. L’image publique doit
être présente dans Docker local.

```powershell
$Image = 'docker.io/library/python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b'
Get-FileHash -Algorithm SHA256 ./preuves/tasks.py, ./preuves/README.md
python -m scripts.agents.native.cli verify-task-app --file ./preuves/tasks.py --sandbox-image $Image
python -m unittest discover -s tests -p test_agent_native.py -v
$env:TEL99_TEST_SANDBOX_IMAGE = $Image
python -m unittest discover -s tests -p test_agent_native.py -k task_app_mission -v
python -m unittest discover -s tests -p test_agent_native.py -k test_native_sandbox_accepts_only_the_observed_output -v
```

La suite native finale a exécuté 56 tests sous Linux hors réseau, dont 54 ont
réussi et 2 nécessitant Docker ont été ignorés. Ces deux tests ont
réussi séparément sous Windows avec Docker local. La suite équipe a réussi
52 tests. La suite protocole a exécuté 42 tests, dont 39 réussis et 3
ignorés. `render_agents.py --check` a validé les 13 définitions.
