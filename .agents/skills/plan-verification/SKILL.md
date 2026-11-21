---
name: plan-verification
description: Choisir les contrôles à exécuter pour couvrir les critères d’acceptation d’une mission avec un budget limité. À utiliser pendant la planification ou après une proposition de réduction des tests.
---

# Planifier la vérification

L’agent chargé du plan recueille les critères d’acceptation auprès du demandeur. Avec le spécialiste du projet, il associe à chaque contrôle connu les critères qu’il vérifie réellement. Il reprend les contrôles obligatoires de la politique du projet, y compris ceux qui ne couvrent directement aucun critère. Le vérificateur relit ces associations. Une couverture inconnue ou un prérequis non représenté demande une clarification.

Estimer tous les coûts dans la même unité additive, par exemple des minutes de calcul. Pour des contrôles qui doivent être exécutés ensemble, chiffrer l’ensemble comme un contrôle. Le calcul accepte jusqu’à 12 critères, 64 contrôles et 64 Kio de JSON. Il convient aux petits lots dont les coûts peuvent être additionnés.

Depuis la racine du dépôt, fournir le contrat sur l’entrée standard du planificateur. Exemple de contrat pour une modification de la reprise après interruption :

```json
{"budget":5,"obligations":["load","resume"],"mandatory":["policy"],"checks":[
  {"id":"load","cost":3,"covers":["load"]},
  {"id":"resume","cost":3,"covers":["resume"]},
  {"id":"combined","cost":4,"covers":["load","resume"]},
  {"id":"policy","cost":1,"covers":[]}]}
```

```sh
python -IB .agents/skills/plan-verification/scripts/plan_checks.py < contract.json
```

- **planned** donne les identifiants de coût total minimal. À coût égal, le plan privilégie le plus petit nombre de contrôles, puis un ordre stable. Dans l’exemple, conserver `combined` et `policy` coûte 5 unités sur les 11 de la stratégie qui lance tous les contrôles pertinents.
- **blocked** indique les critères sans contrôle ou le coût minimal qui dépasse le budget. Rapporter le blocage au responsable de la mission. Conserver les obligations et les contrôles imposés dans toute demande de révision.
- **invalid** avec le code de sortie 2 signale un contrat à corriger. Les contrôles sont des identifiants à rapprocher ensuite des procédures approuvées du projet. Le planificateur lit le JSON et affiche un plan.

Le vérificateur consigne les résultats des contrôles effectivement exécutés. Le coût proposé et la couverture déclarée sont des estimations. Un verdict d’acceptation demande les preuves de ces exécutions.

## Replanifier après une interruption

Reprendre le catalogue, les critères et les contrôles obligatoires du contrat initial. Mettre dans `contract.budget` le budget restant après les dépenses déjà engagées. Dans `passed`, inscrire uniquement les contrôles dont les preuves de succès ont été vérifiées pour la même mission, le même état des fichiers et les mêmes conditions pertinentes. Si une preuve est périmée ou incertaine, le contrôle reste à planifier. `unavailable` contient les contrôles temporairement impossibles à exécuter. Traiter un contrôle exécuté en échec selon la procédure du projet avant de reprendre la planification.

Dans l’exemple initial, `load` et `policy` ont réussi, `combined` est indisponible et il reste 3 unités. Enregistrer la demande suivante dans `resume.json` :

```json
{"contract":{"budget":3,"obligations":["load","resume"],"mandatory":["policy"],"checks":[
  {"id":"load","cost":3,"covers":["load"]},
  {"id":"resume","cost":3,"covers":["resume"]},
  {"id":"combined","cost":4,"covers":["load","resume"]},
  {"id":"policy","cost":1,"covers":[]}]},"passed":["load","policy"],"unavailable":["combined"]}
```

```sh
python -IB .agents/skills/plan-verification/scripts/plan_checks.py --replan < resume.json
```

Le plan renvoie `resume` pour un coût additionnel de 3 et liste `load` et `policy` dans `reused`. Les identifiants de `passed` et `unavailable` doivent être connus et distincts. `unavailable_mandatory` signale un contrôle obligatoire impossible à exécuter. Les autres blocages indiquent les critères restants sans couverture (`uncovered`) ou le coût additionnel minimal (`minimum_cost`). Un plan vide à coût zéro indique que toutes les obligations sont déjà couvertes par les preuves fournies.

## Expérimenter une amélioration de stratégie

1. Relever une faiblesse sur une mission de développement, par exemple un budget dépassé à cause de contrôles redondants. Garder le contrat initial et le résultat de référence. Formuler un seul changement de sélection et le gain attendu.
2. Demander à un vérificateur distinct de figer les critères de succès, la stratégie de référence et des missions représentatives tenues en réserve. Consigner leurs empreintes avant de figer le commit candidat dans un worktree isolé. Le proposant travaille sur les exemples de développement.
3. Sur le candidat figé, le vérificateur compare chaque paire de plans avec le comparateur du projet. Il exige la couverture de chaque critère, les contrôles imposés et le respect du budget. Une impossibilité doit être confirmée indépendamment. Une régression sur un cas précédemment réussi conduit au rejet.
4. Archiver dans la PR le SHA, les empreintes, les résultats et la décision. Un gain mesuré permet de conserver le candidat en brouillon pour revue. En cas de rejet, poursuivre avec la référence. Pour une nouvelle itération, constituer une nouvelle réserve indépendante dès que les cas précédents sont révélés.

Rejouer l’expérience livrée, depuis la racine du worktree :

```sh
python -IB tests/plan_verification/evaluate.py --root .
```
