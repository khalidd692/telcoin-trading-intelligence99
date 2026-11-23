# TEL99 — deux nouvelles missions GitHub vers les agents Ollama

## État

Ce pilote ne change pas le superviseur : il utilise
\`autonomy_runtime.Runtime\`, \`kilo_github_adapter.KiloGitHubHandoff\`,
les claims CAS, les ACK et la mémoire existants. Seuls les contrats de
code \`owner=local\`, \`project=tel99\` avec les trois rôles explicitement
approuvés sont admis. Les tests de régression Python tournent avant la
moindre génération.

La PR #168 (empilée sur #167 puis #166) est **brouillon**.

## Campagne GitHub réelle, préparée

- Contrôleur : https://github.com/khalidd692/telcoin-trading-intelligence99/issues/169
- Mandat signé par compte propriétaire, commentaire : 7113655599
- Mandat SHA-256 : \`d22c14d046c53deed84894fdfbdeb1c015043e91a8406c37a6540beeefaf1e7d\`
- Mission code #170 : correction locale de \`kv_env\`, SHA contrat
  \`2f913e157b8149f4dbe040e6f02fd7f2f2b8de3e01706f2d20470628db7ba929\`
- Mission code #171 : correction locale de \`load_tasks\`, SHA contrat
  \`b4bb526aff1b78db6b21a085d9e4cbf7fc192c2cefb2289018551b785acecccb\`
  (dépend du premier RESULT accepté)
- Base de code isolée : \`agents/tel99-code-pilot-base-20261123\`
  au commit fixé \`934d9fd8a3fd498c6e3e69226007dd46276aa6da\`.
- Date d'expiration des deux approbations et du mandat :
  \`2026-12-01T23:59:59Z\`.

Les deux issues sont nouvelles et distinctes des tickets historiques.
Un simple label ne vaut jamais approbation : seul un commentaire
\`tel99-code-mission/v1\` émis par le compte propriétaire et lié au
mandat, au contenu, à l'issue, à l'expiration et à l'empreinte est admis.

## Une commande de démarrage contrôlé sur Windows

Depuis l'ancien worktree TEL99_TEAM_PILOT_20261123 (branché sur PR #167) :

~~~powershell
$base = "$HOME\Desktop\TEL99_TEAM_PILOT_20261123"
$checkout = "$HOME\Desktop\TEL99_GITHUB_CODE_20261123"
$branch = "agents/tel99-github-local-code-20261123"
if (!(Test-Path $base)) { throw "Ancien worktree introuvable" }
if (!(Test-Path $checkout)) {
    git -C $base fetch origin "refs/heads/$branch"
    if ($LASTEXITCODE -ne 0) { throw "GitHub fetch failed" }
    git -C $base worktree add --detach $checkout FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw "Worktree creation failed" }
}
pwsh -NoProfile -ExecutionPolicy Bypass -File "$checkout\scripts\agents\automation\run_github_code.ps1" -Mode Run
~~~

Ce lanceur exécute d'abord la suite Python offline. Il effectue
ensuite un pré-vol **lecture seule** auprès de GitHub, vérifie
l'identité authentifiée et les autorisations signées, puis démarre
l'exécution bornée (7200 secondes au plus) en premier plan sur Windows.

Le ledger persistant (hors dépôt Git) est
\`Desktop\TEL99_GITHUB_CODE_STATE_20261123\`.
Ne jamais supprimer ou écraser ce ledger pour relancer une mission RUNNING
dont le résultat est incertain.

Si l'un des pré-vols échoue, **aucun worker n'est lancé**.

## Lire l'état / demander l'arrêt

~~~powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "$checkout\scripts\agents\automation\run_github_code.ps1" -Mode Status
pwsh -NoProfile -ExecutionPolicy Bypass -File "$checkout\scripts\agents\automation\run_github_code.ps1" -Mode Stop
~~~

Le STOP est une demande d'arrêt volontaire; les checkpoints sont
conservés. Pour une reprise après arrêt ou crash, effectuer une
réconciliation du worker et du stop marker avant de reprendre. Le système
ne réexécute **pas** silencieusement un worker RUNNING incertain.

## Résultats attendus (à constater, jamais supposer)

1. Découverte de #170 puis #171 via mandat authentifié, 2 ACK corrélés.
2. À chaque mission : tel99-analyst (Ollama lecture seule), tel99-dev
   (Ollama code), tel99-verifier (vérification Docker indépendante).
3. Baseline rouge, candidat vert, reçu de hash, diff exactement une
   fonction du fichier approuvé.
4. Deux branches distinctes \`agents/tel99-code/...\` sur base
   historique fixe ; deux PR **brouillons** seulement après preuve
   indépendante. Le modèle ne publie aucun code sans validation.
5. RESULT GitHub lié à la PR, état persistant. Si la réponse API de
   création PR est perdue, l'agent réconcilie par GET et n'envoie
   pas un nouveau POST non assuré.
6. Une interruption simulée et reprise, sans duplicata, reste
   encore à attester par des preuves Windows.

## Limites

Le pilote démontre un transfert entre agents existants, pas
l'activation magique des neuf rôles réservés ni l'autonomie PC éteint.
Les tâches locales ne tournent que si le PC est allumé, connecté et
doté d'Ollama et Docker déjà installés. Aucune fusion dans main,
aucun ordre de trading, aucune dépense ni nouveau scheduler Windows.
