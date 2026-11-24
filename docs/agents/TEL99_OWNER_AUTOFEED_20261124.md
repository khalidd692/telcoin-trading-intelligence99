# TEL99 — auto-alimentation à partir de mandats approuvés

Cette nouvelle entrée **réutilise** le moteur de la PR #190, le récepteur
`LocalCodeCampaign`, les contrats SHA-256, les rôles analyste/dev/vérificateur,
Docker, les checkpoints CAS et les PR brouillons. Aucun nouveau superviseur.

## Ce qui est automatique

- Le PC sonde GitHub pour découvrir de **nouveaux** contrôleurs approuvés,
  sans qu'un opérateur copie leurs numéros/empreintes dans un manifeste.
- Chaque contrôleur doit être une issue **créée par le propriétaire**,
  ouverte, et comporter une ligne exacte dans son texte :

  `tel99-autofeed-controller/v1`

- L'issue doit posséder **un unique commentaire de mandat propriétaire non
  modifié** au format `tel99-code-campaign/v1`, une base Git isolée épinglée,
  et 2 à 10 contrats approuvés dans des issues `enhancement`.
- Le moteur relit et vérifie l'identité GitHub, le mandat, l'expiration,
  chaque approbation, le graphe des dépendances et la base avant chaque worker.
- Les mandats découverts sont persistés dans `feed-ledger/` par CAS.
  Retrait, changement de SHA ou commentaire édité => **blocage**.
- Une campagne peut finir rapidement ; le processus continue à surveiller
  jusqu'au plafond défini. Temps maximal **60 minutes**, pas une obligation de
  fabriquer du travail.

## Ce qui reste interdit

Le système **ne peut pas** inventer de mandat, de signature ou
d'approbation. Il ne crée, ne modifie ou n'approuve aucune issue GitHub
dans son mécanisme de découverte, et ne s'auto-attribue aucune mission.
Une proposition d'amélioration non approuvée n'est **jamais** exécutable.
La sécurité du compte GitHub propriétaire et la séparation entre proposition
et approbation restent importantes.

Aucun contrôleur historique jusqu'au numéro #203 ne peut être découvert
par ce nouveau mode. L'ancien état de recette ne doit pas être recyclé.
Pas de trading, de fusion automatique ou de cloud implicite.

## Windows, nouveau dossier d'état

~~~powershell
$work = "$HOME\Desktop\TEL99_OWNER_AUTOFEED"
$runner = "$work\scripts\agents\automation\run_github_multi_mandate.ps1"
$state = "$HOME\Desktop\TEL99_OWNER_AUTOFEED_STATE"

pwsh -NoProfile -File $runner -Mode Preflight -AutoFeed -StateDir $state
pwsh -NoProfile -File $runner -Mode Run -AutoFeed -StateDir $state -Minutes 60 -PollInterval 30
~~~

`WAITING_OWNER_APPROVAL` signifie qu'aucun mandat admissible n'est encore
présent, **pas** une erreur ni une preuve de travail. Depuis une autre console :

~~~powershell
pwsh -NoProfile -File $runner -Mode Status -StateDir $state
pwsh -NoProfile -File $runner -Mode Stop -StateDir $state
~~~

L'arrêt demande une intervention explicite avant reprise ; on ne supprime
ni les journaux ni les reçus. Le mode manuel `-Manifest` demeure disponible.

## Recette et limites

`python -B -m unittest tests.test_github_owner_feed tests.test_github_multi_mandate_session`

La CI vérifie les tests hors ligne sous Windows et Linux. La découverte
effectivement alimentée **à chaud** par une nouvelle issue propriétaire
et une heure complète avec Ollama/Docker restent à éprouver sur un PC
allumé avec des mandats nouveaux.

## Mandat de recette (nouveau, à exécuter localement)

- Contrôleur GitHub [#205](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/205), marqué `tel99-autofeed-controller/v1` et doté d'un mandat propriétaire SHA-256.
- Missions [#206](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/206) (`tool_names`) et [#207](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/207) (`dedup_key`), toutes deux approuvées séparément et dépendantes dans cet ordre.
- Base Git isolée `agents/tel99-code-base-autofeed-20261124`, commit épinglé `934d9fd8a3fd498c6e3e69226007dd46276aa6da`.

Le système doit reconnaître ce contrôleur **sans manifeste** depuis un nouveau dossier d'état et produire deux PR brouillons avec reçus indépendants. Les tests CI seuls ne remplacent pas cette recette réelle.
