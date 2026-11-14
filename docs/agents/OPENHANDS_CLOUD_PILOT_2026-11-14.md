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
| Branche et SHA de départ | |
| Modèle et coût réellement affiché | |
| Vérifications initiales | |
| Nombre de délégations observées | |
| Résultat de `verify_delegation.py` | |
| État final du dépôt (`git status`) | |
| Correction réalisée (essai 2) | |
| Tests, erreurs et limites | |

Ne pas déclarer la relance ou la correction validée sans exécution réelle dans OpenHands Cloud.
