# TEL99 — première campagne multi-issues, plafonnée à 60 minutes

## Portée et sécurité

Ce mode réutilise exactement le superviseur TEL99 `autonomy_runtime.py`,
le récepteur GitHub `github_local_code_campaign.py`, les contrats SHA-256,
le bus CAS, les ACK/EVIDENCE/RESULT, les deux modèles locaux et le validateur
Docker indépendant. Pas de nouveau superviseur, pas de fusion automatique,
pas d'ordre de trading, pas d'interface nouvelle.

La campagne existante #169–#171 et le ledger
`Desktop/TEL99_GITHUB_CODE_STATE_20261123` restent **intouchés**.

## Nouvelles tâches autorisées

Contrôleur : [#178](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/178).
Mandat propriétaire : commentaire `7114796910`, empreinte SHA-256
`85097fb5baaf114b71c2f3e9bed29a43457c6824604baf43d549ce6b9a44c1bf`.

Les trois nouvelles issues GitHub sont **de nouveaux tickets de livraison**
mais réutilisent les tests de trois fonctions déjà étudiées dans les premiers
benchmarks locaux. Ce n'est donc pas une preuve d'une capacité généralisée à
des problèmes totalement inédits.

- #179 : `git_changes` / `windows_diagnostic.py`; contrat
  `eb3ddbb7bb259273ac5630f43e02b40c760586376b2737da1a39af673520bed8`.
- #180 : `load_json` / `verify_runtime.py`; dépend de #179,
  contrat `55aa9313627b64b017d31c4e5ca0ee96f705f78b9a3dedbf184027d09607ec0c`.
- #181 : `inventory_view` / `pilot_recipe.py`; dépend de #180,
  contrat `455375c6a6e574c8172fd3623e8439350bbd26ace972456641d525b700b86a82`.

Base de code isolée : branche
`agents/tel99-code-pilot-base-20261123`, commit épinglé
`934d9fd8a3fd498c6e3e69226007dd46276aa6da`.
Mandat et contrats expirent le 01/12/2026 à 23:59:59 UTC.

Le superviseur ne crée aucun nouveau mandat de son propre chef et ne
réexécute pas de tâche dont le checkpoint RUNNING reste incertain.

## Commande PowerShell

Depuis le worktree TEL99 déjà existant, créer un worktree séparé pour la PR #177.
Le lanceur vérifie d'abord les tests offline, le propriétaire GitHub,
les approbations et la présence de toutes les missions. Ne lancer le
worker que si le pré-vol est READY.

~~~powershell
$base = "$HOME\Desktop\TEL99_GITHUB_CODE_20261123"
$checkout = "$HOME\Desktop\TEL99_HOUR_20261123"
$branch = "agents/tel99-hour-queue-20261123"
git -C $base fetch origin "refs/heads/$branch"
if ($LASTEXITCODE -ne 0) { throw "Erreur fetch" }
if (!(Test-Path $checkout)) {
    git -C $base worktree add --detach $checkout FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw "Erreur worktree" }
}
pwsh -NoProfile -ExecutionPolicy Bypass -File "$checkout\scripts\agents\automation\run_github_hour.ps1" -Mode Run -Minutes 60
~~~

Le ledger de cette nouvelle campagne est
`Desktop/TEL99_GITHUB_HOUR_STATE_20261123`.

Pour lire l'état dans une deuxième fenêtre PowerShell :

~~~powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "$checkout\scripts\agents\automation\run_github_hour.ps1" -Mode Status
~~~

Pour demander un arrêt propre :

~~~powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "$checkout\scripts\agents\automation\run_github_hour.ps1" -Mode Stop
~~~

**60 minutes est la durée MAXIMALE**, et non la durée minimale : si les
trois issues sont terminées avant, les agents s'arrêtent proprement.
Aucun faux travail ne sera inventé pour remplir l'heure.

## Critères de réussite

3 ACK, 3 corrections vérifiées indépendamment, 3 résultats GitHub,
3 PR brouillons distinctes, mémoire persistée, aucun replay, aucune
fusion dans main. Les échecs ou épuisements de quota doivent être affichés
comme tels ; la campagne ne doit pas présenter COMPLETE sans trois
RESULT valides.

La reprise après interruption réelle doit faire l'objet d'une
expérience contrôlée supplémentaire ; les tests offline seuls ne la
démontrent pas.

Cette nouvelle campagne n'active pas les neuf rôles réservés.
