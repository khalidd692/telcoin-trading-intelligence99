# Mesures et évaluation des missions TEL99

## Archiver une campagne GitHub

Depuis la racine du dépôt, sous PowerShell, renseigner les trois chemins ou valeurs de la campagne concernée. Le dossier des rapports doit déjà exister et le fichier doit être nouveau.

```powershell
$etat = Join-Path $HOME 'Desktop\TEL99_GITHUB_CODE_STATE_20261123'
$mandat = 'd22c14d046c53deed84894fdfbdeb1c015043e91a8406c37a6540beeefaf1e7d'
$rapport = Join-Path $HOME 'Desktop\tel99-mesures-169.json'
python -B -m scripts.agents.automation.campaign_learning --state $etat --mandate-sha256 $mandat --output $rapport
```

Cette commande lit les approbations archivées, les checkpoints et reçus locaux déjà présents. Elle vérifie la correspondance du mandat, du contrat, des preuves Docker et des fichiers matérialisés. Le checkout doit disposer du commit de base épinglé par la campagne. Le résumé contient le verdict, le modèle, les tentatives, les contrôles échoués, les temps mesurés et la RAM disponible lorsqu'elle figure dans le reçu. Le transfert analyste → développeur est représenté par son empreinte et ses rôles. L'objectif et le test sont représentés par leurs empreintes. Les mesures de RAM concernent l'hôte aux points observés. Les valeurs absentes sont `null`.

Le rapport est destiné à une archive locale. La commande crée un fichier hors du ledger avec une écriture exclusive. Les données sont issues du registre local de l'opérateur et des preuves liées à celui-ci. En cours de campagne, le rapport conserve les missions déjà terminées et signale les autres au moyen de leur dernier checkpoint.

## Utiliser des mesures pour un nouveau registre routé

La décision ne peut choisir qu'une liaison déjà autorisée dans le nouveau contrat. Le routeur réutilise les verdicts Docker des checkpoints CAS de même projet, de même base et d'une difficulté comparable. Les échantillons ont au plus 30 jours. Il conserve une observation par fonction et modèle, plafonne la comparaison à 20 échantillons par niveau et modèle, et exige 5 cas distincts pour substituer le taux observé à l'estimation du catalogue. Qwen3.5 doit disposer de ces mesures avant tout choix automatique. Un essai Qwen3.5 en mode fixe et sous contrat approuvé permet de recueillir ces premières preuves. Le routeur contrôle aussi l'identité locale du modèle et la RAM hôte disponible. Pour Ollama la réserve de 1 Gio s'ajoute à la mémoire estimée du modèle, y compris pour une génération en mode fixe.

Pour exploiter un ancien essai Night Lab terminé avec un seul modèle en mode fixe individuel, ajouter un ou plusieurs couples dossier et SHA du registre à la commande du superviseur local. Utiliser un dossier d'état neuf et un registre de nouvelles missions déjà approuvées.

```powershell
python -B -m scripts.agents.automation.autonomy_runtime run --local-code --once --seconds 1800 `
  --state $nouvelEtat --registry $nouveauRegistre --registry-sha256 $nouvelleEmpreinte `
  --calibration-session $ancienNightLab $ancienneEmpreinte
```

La RAM, la disponibilité et les seuils de qualité sont recontrôlés. Un mode fixe GitHub continue d'exécuter le modèle précisément scellé dans son approbation. En cas de blocage de mission ou de reprise, le superviseur conserve ses contrôles habituels de consentement, de preuve Docker et de liaison du modèle. Les archives de comparaison restent locales et les changements de méthode sont proposés pour examen.

## Comparer sur une cohorte réservée

Préparer, avant le benchmark, deux nouveaux registres scellés pour les mêmes missions réservées, avec des IDs distincts et la même base. Évaluer les deux modèles par deux campagnes Night Lab indépendantes. Fournir chaque registre utilisé pour apprendre ou choisir la proposition, par répétition de `--learning-source`.

```powershell
python -B -m scripts.agents.automation.compare_local_code `
  --baseline $sessionAvant --baseline-sha256 $shaAvant `
  --candidate $sessionApres --candidate-sha256 $shaApres `
  --learning-source $registreApprentissage $shaApprentissage `
  --output $comparaisonPrivee
```

Les empreintes sont vérifiées. La comparaison refuse toute fonction ou tout test commun avec les registres d'apprentissage déclarés, y compris si l'objectif a été reformulé. Les critères appariés et le verdict proviennent de l'évaluateur déterministe existant. Une dégradation rejetée ou un test inconclusif reste visible. Pour atteindre le seuil de dix cas appariés, ajouter une deuxième paire avec `--pair $sessionAvant2 $shaAvant2 $sessionApres2 $shaApres2`. Les paires doivent garder le même checkout et les mêmes modèles de référence et de comparaison, avec des fonctions et tests distincts au sein de la cohorte. Une recommandation exige aussi le seuil de significativité existant. Les jeux doivent rester réservés avant l'évaluation. L'outil vérifie les sources fournies par l'opérateur.

## Rejouer la vérification hors ligne

```powershell
python -B -m unittest tests.test_local_learning tests.test_compare_local_code tests.test_evidence_route tests.test_local_model_routing tests.test_local_runtime_routing tests.test_ollama_native_code
```

Les tests construisent des reçus synthétiques et des entrées réservées pour vérifier l'isolation, les analyses d'échec, les projections et les seuils de routage. La comparaison réelle des modèles et le taux de réussite sur des missions inédites dépendent de nouvelles campagnes instrumentées.
