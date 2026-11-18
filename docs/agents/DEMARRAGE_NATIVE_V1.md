# Démarrer le moteur d’agents natif

Cette version manuelle utilise Python 3.12 et, pour les tests du gestionnaire
de tâches, un Docker local en mode conteneurs Linux. Les commandes se lancent
à la racine de la branche de livraison. Le moteur et le programme livré
s’utilisent depuis le terminal.

## Essayer hors ligne

```text
python -m scripts.agents.native.cli demo
```

Cette démonstration emploie des réponses enregistrées. Elle permet de vérifier
l’installation et la mémoire locale avant de raccorder un modèle.

## Lancer la mission

Dans PowerShell, préparer un dossier de travail privé, distinct du dépôt.
Précharger l’image Python sur le Docker local.

```powershell
$Travail = Join-Path $env:LOCALAPPDATA "Tel99Agents"
$Etat = Join-Path $Travail "etat"
$Memoire = Join-Path $Travail "memoire"
$Image = "docker.io/library/python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b"
docker pull $Image
```

Utiliser un endpoint compatible OpenAI dont l’accès et le quota inclus ont
été vérifiés. Définir `TEL99_NATIVE_BASE_URL` et `TEL99_NATIVE_MODEL` selon
ce runtime. Le cas échéant, renseigner `TEL99_NATIVE_API_KEY` dans
l’environnement privé. Pour un runtime indépendant sur `127.0.0.1`, définir
`TEL99_NATIVE_INCLUDED_MODEL` à l’identifiant exact du modèle approuvé.
Cette valeur déclare le modèle choisi par l’opérateur. La preuve du quota
vient du runtime. Remplacer `$QuotaRestant` par la valeur réellement vérifiée.
Le modèle n’est appelé que lorsque le quota est fourni et atteint la réserve.

```powershell
python -m scripts.agents.native.cli --state $Etat --memory $Memoire --quota $QuotaRestant run `
  --project perso --mission-id taches-01 --profile tasks --sandbox-image $Image `
  --mission "Crée une petite application de gestion de tâches, permettant d'ajouter, modifier, terminer et supprimer une tâche, avec stockage local et tests automatisés."
```

Le profil demande `tasks.py` et son guide `README.md`. Le moteur exécute
ses propres contrôles en conteneur : ajout, relecture dans un autre
processus, modification, clôture, séparation de deux bases et suppression.
En cas d’échec, il peut demander deux réparations au maximum, dans la limite
du quota et de la durée. Le journal donne chaque verdict, le modèle
effectivement appelé et l’empreinte des fichiers.

## Retrouver et vérifier un résultat

La commande `status` indique le dossier exact des fichiers et le journal
sans consommer de quota. Une fois le résultat accepté, ouvrir son
`README.md`. Le vérificateur est rejouable dans un conteneur indépendant.

```powershell
python -m scripts.agents.native.cli --state $Etat status --project perso --mission-id taches-01
python -m scripts.agents.native.cli verify-task-app --file "CHEMIN_AFFICHE/tasks.py" --sandbox-image $Image
python -m scripts.agents.native.cli --memory $Memoire recall --project perso --query "taches-01"
```

Pour une nouvelle mission, choisir un nouvel identifiant. Pour sauvegarder la
mémoire du projet et la restaurer ailleurs, utiliser `export-memory` et
`restore-memory` décrits dans [le guide natif](NATIVE_MISSION_RUNNER.md).

## Validation reproductible

La recette intégrée utilise un fournisseur scripté qui produit d’abord une
application qui échoue au contrôle de clôture, puis une version corrigée.
Docker vérifie réellement les deux versions. Le test couvre le journal, les
fichiers et la vérification rejouée. Exécution avec une image locale :

```powershell
$env:TEL99_TEST_SANDBOX_IMAGE = $Image
python -m unittest discover -s tests -p test_agent_native.py -k task_app_mission
```

L’environnement de livraison cloud valide cette recette sous Linux.
L’accès à un modèle réellement inclus et l’exécution sur le PC Windows
du propriétaire restent à vérifier.
