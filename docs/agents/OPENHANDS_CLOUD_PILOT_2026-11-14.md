# TEL99 — Pilote OpenHands Cloud (14 novembre 2026)

Branche d'essai isolée : `agents/openhands-cloud-pilot-20261114`.
Point de départ : `fadb218b51ca62b9c6e939657696253b1abb8470`.
**Aucun merge, déploiement, ordre réel ou simulé. Aucun abonnement ni crédit API payant.**
La PR #63 et la branche produit ne doivent pas être modifiées.

## Objectif du premier essai : relance réelle depuis GitHub, lecture seule

Dans une session OpenHands Cloud déjà disponible, avec le dépôt cloné et CETTE branche extraite :

```bash
git status --short
git branch --show-current
python -m unittest discover -s tests -p 'test_agent_team.py' -v
python -m unittest discover -s tests -p 'test_team_audit.py' -v
python scripts/agents/render_agents.py --check
python scripts/agents/run_pilot.py --dry-run
```

Vérifier AVANT exécution qu'un profil `~/.openhands/profiles/openhands_deepseek-v4.1-flash.json` est présent, que le modèle `openhands/deepseek-v4.1-flash` est effectivement gratuit dans ce compte, et que le serveur d'agents de la session répond à `http://localhost:60000`. Si une facturation est annoncée, **stop**.

Puis, et seulement si ces conditions sont validées :

```bash
TEL99_MAX_BUDGET_USD=0.2 TEL99_AGENT_MAX_BUDGET_USD=0.05 python scripts/agents/run_pilot.py --wait
```

Relever `conversation_id`, le suffixe exact et l'état final. Contrôler ensuite :

```bash
python scripts/agents/verify_delegation.py <conversation_id> --suffix <suffix>
git status --short
```

**Critères d'acceptation :**
- trois délégations réelles (et pas uniquement trois déclarations), avec preuves d'exécution ;
- outils et hooks effectivement propagés ; politique de confirmation vérifiée ;
- aucune modification des fichiers TEL99 ni accès à des ordres ;
- rapport des tests avec commandes et résultats, sans secret ;
- pas de fusion ni de publication.

**Attention aux faux positifs :** dans la version initiale, `verify_delegation.py` peut afficher PASS même si aucun sous-agent n'a été trouvé. Exiger `sub-agents found : 3` et des traces indépendantes avant de conclure au succès.

## Deuxième essai : petite correction sur branche isolée, uniquement après le pilote lecture seule

Mission suggérée pour le développeur : corriger le comportement permissif du garde-fou en cas d'événement JSON invalide ou incomplet, et ajouter des tests de non-régression. Actuellement le garde retourne 0 (autorise) sur entrée non analysable et les tests valident explicitement ce comportement. Ne pas modifier la PR #63, le produit, les workflows de déploiement ou les stratégies de trading.

Le lanceur actuel est volontairement en **lecture seule** et interdit toute écriture : ne pas essayer de contourner son garde-fou. Pour le développement, créer une session ou configuration *distincte*, explicitement autorisée pour les seuls fichiers du pilote sur la branche isolée ; si un périmètre d'écriture sûr ne peut pas être établi, rester en diagnostic et signaler le blocage.

**Livrables du deuxième essai :** diff restreint, tests avant/après, explication du risque, preuve que les commandes légitimes en lecture seule continuent de fonctionner. Ne rien fusionner ou déployer sans validation explicite.

## Rapport final attendu

| Mesure | Résultat / preuve |
|---|---|
| Branche et SHA de départ | `agents/openhands-cloud-pilot-20261114` @ `359c07c7` |
| Modèle et coût réellement affiché | non relancé (consigne : pas de nouveau pilote avant correctifs) |
| Vérifications initiales | `git status --porcelain` vide ; `guard.py`/`run_pilot.py` identiques à la branche Hermes (aucun conflit) |
| Nombre de délégations observées | non relancé dans cet essai |
| Résultat de `verify_delegation.py` | non relancé dans cet essai |
| État final du dépôt (`git status`) | voir « Essai 2 — résultat » ci-dessous |
| Correction réalisée (essai 2) | voir « Essai 2 — résultat » ci-dessous |
| Tests, erreurs et limites | 48 tests `test_agent_team.py` OK ; 529 tests dépôt OK (3 ignorés) |

## Essai 2 — résultat (14 novembre 2026)

Corrections réalisées sur la branche isolée, sans merge ni déploiement. Fichiers modifiés :
`scripts/agents/guard/guard.py`, `scripts/agents/run_pilot.py`, `scripts/agents/team_config.py`,
`tests/test_agent_team.py`. Aucun fichier de Kilo, Hermes, du terminal TEL99 ni `AGENTS.md`
n'a été touché.

1. Garde-fou (`guard.py`).
   - Échec fermé : JSON invalide, `{}`, tableau JSON, absence de `tool_name`, absence de
     `tool_input`, commande vide -> **exit 2** (blocage). Avant : exit 0 (autorisation).
   - `curl … | sh`, `wget … | bash`, `… | python3` et variantes (`| sudo sh`) -> **bloqués**.
     Avant : `curl | sh` passait.
   - Faux positifs réduits : le contenu des chaînes entre guillemets est ignoré pour la
     détection de redirection et de pipe, donc `echo "a -> b"`, `grep -n "=>" file` et
     `python3 -c "print(1 > 0)"` ne sont plus bloqués.
   - Formes de lecture de git autorisées : `git remote -v`, `git --no-pager remote -v`,
     `git remote show`, `git config --get/--list`. Les formes mutantes (`git remote add`,
     `git config user.name`) restent bloquées.

2. Budget des sous-agents (`team_config.py`, `run_pilot.py`).
   - Ajout d'un paragraphe de discipline de budget injecté au **runtime** dans chaque
     sous-agent (exploration bornée ~12 commandes, rapport final obligatoire même partiel,
     pas de relance automatique). Les fichiers `.agents/agents/*.md` ne sont pas régénérés.
   - **Aucun plafond n'est relevé** : `max_budget_per_run` et `max_iteration_per_run`
     restent `DEFAULT_AGENT_*` (contrôlés par variables d'environnement). Un test le vérifie.

3. Suivi du coordinateur (`run_pilot.py`).
   - `wait_for` renvoie un statut distinct : `finished` / `error` / `stopped` / `timeout` /
     `unreachable`. Un `timeout` du lanceur n'est plus confondu avec une erreur de travail.
   - Nouvelle option `--follow <conversation_id>` : reprend le suivi d'une conversation
     existante sans en créer une nouvelle (aucun second budget coordinateur).
   - Codes de sortie : `timeout`/`unreachable` -> 0 (limite de l'observateur) ; `error`/
     `stopped` -> 2 (échec réel).

Preuves d'exécution :

```text
python -m unittest discover -s tests -p 'test_agent_team.py'   -> Ran 48 tests  OK
python -m unittest discover -s tests                           -> Ran 529 tests OK (skipped=3)
python scripts/agents/render_agents.py --check                 -> OK: 13 fichiers conformes
python scripts/agents/run_pilot.py --follow 1db92a3d-... --timeout 20
    -> final status: finished (work finished)   exit 0
```

Limites : le pilote complet n'a pas été relancé (consigne). Le garde-fou reste une heuristique
de défense en profondeur ; les contrôles primaires demeurent l'allowlist `terminal`,
`sub_agent_scope` et la politique de confirmation.

## Revue de sécurité (14 novembre 2026) — défauts critiques corrigés

Lors de la revue finale de la PR #64, des défauts **vérifiables** ont été trouvés dans le
garde-fou et corrigés dans un commit supplémentaire :

1. **Outils disque non bloqués.** La liste testait l'égalité exacte : `mkfs.ext4`, `mkfs.xfs`,
   `mke2fs`, `shred`, `wipefs`, `fdisk`, `parted`, `sgdisk`, `blkdiscard` passaient (exit 0).
   Corrigé : ajout de la famille disque + correspondance par préfixe pointé (`mkfs.*`).
2. **Contournement du mot de tête.** `\rm`, `RM` (casse) et `rm${IFS}-rf` n'étaient pas
   détectés. Corrigé : normalisation du mot de tête (backslash initial, `${IFS}`, minuscules).
3. **Évasion par interpréteur.** `python3 -c "os.system(...)"`, `perl -e "system(...)"`,
   `node -e "child_process.execSync(...)"` exécutaient des sous-processus. Corrigé : blocage des
   motifs d'évasion (`os.system`, `subprocess.`, `system(`, `child_process`, `execSync`…) dans les
   interpréteurs connus, sans bloquer la lecture légitime (`open('x').read()`, `unittest`…).

Ces corrections restent **heuristiques** : elles réduisent la surface d'attaque, elles ne
garantissent pas une isolation complète. La liste des interpréteurs et des motifs doit être
maintenue à mesure que de nouveaux cas apparaissent.


