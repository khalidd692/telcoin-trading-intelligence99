# Couche d'intelligence des agents TEL99

Statut : **première amélioration mesurée, testée hors ligne**. Aucune
automatisation permanente, aucun appel payant, aucun ordre.

Cette couche répond à l'issue #67 (routeur multi-modèles, mémoire partagée,
auto-amélioration contrôlée). Elle **réutilise** l'existant
(`team_config.py`, `guard/guard.py`) et n'y touche pas.

## Composants

| Fichier | Rôle |
|---|---|
| `scripts/agents/intelligence/catalog.py` | Catalogue de modèles, chaque entrée portant sa **preuve** et son statut `verified` |
| `scripts/agents/intelligence/router.py` | Routeur déterministe : difficulté, coût, quota, disponibilité, fallback, journal |
| `scripts/agents/intelligence/memory.py` | Mémoire versionnée, provenance, isolation par projet, recherche, erreurs capitalisées |
| `scripts/agents/intelligence/improvement.py` | Boucle `observer → proposer → tester → comparer → conserver/rejeter` |
| `scripts/agents/intelligence/cli.py` | Interface réutilisable (`route`, `remember`, `recall`, `improve`, `demo`) |
| `scripts/agents/intelligence/demo.py` | Démonstration de bout en bout (preuve chiffrée) |
| `tests/test_agent_intelligence.py` | 33 tests stdlib, sans réseau |

## 1. Routeur de modèles

Le routeur classe la difficulté à partir de signaux observables (type de tâche,
nombre de fichiers, volume estimé, besoin d'outils, confidentialité), puis
filtre le catalogue par contraintes **dures** :

- **coût** : seuls les modèles `free` sont éligibles (règle « aucune dépense ») ;
- **outils** : un modèle sans appel d'outils est exclu si la tâche en a besoin ;
- **disponibilité** : un modèle non `verified` est **refusé en run réel**
  (fail-closed). On ne peut pas inventer la disponibilité d'un modèle ;
- **quota** : un quota inconnu ou trop bas **refuse** un run réel ;
- **local** : un modèle local est exclu d'un run réel car le PC peut être éteint.

Le classement est déterministe : qualité (mesurée si disponible, sinon prior) ×
localité (si confidentiel) × latence. Chaque rejet est écrit dans le journal de
décision avec sa raison.

```bash
python -m scripts.agents.intelligence.cli route --kind code --files 6 --dry-run
```

## 2. Mémoire partagée versionnée

- **Versionnée** : re-enregistrer un même `id` incrémente la version et
  conserve l'historique. Rien n'est écrasé silencieusement.
- **Provenance** : `source`, `commit`, `author`, `created_at`, `verified_by`.
- **Isolation par projet** : un projet ne voit que ses entrées et le pool
  `common`. L'isolation est **appliquée en code**, pas par convention.
- **Recherche** : `search` classe les expériences par recouvrement de mots,
  avec bonus pour les entrées vérifiées ; les entrées **remplacées** sont
  exclues par défaut (sinon on rejouerait une croyance déjà corrigée).
- **Erreurs capitalisées** : une entrée `fix` peut remplacer une entrée `error`
  via `supersede`, qui garde l'ancienne traçable.

```bash
python -m scripts.agents.intelligence.cli remember --project tel99 \
  --kind fix --title "…" --body "…" --tag guard --verified
python -m scripts.agents.intelligence.cli recall --project tel99 --query "guard git"
```

## 3. Boucle d'amélioration contrôlée

`improvement.compare` compare un candidat à une base **sur les seules tâches
exécutées par les deux**. Une paire incomplète rend l'évaluation inconclusive.
`KEEP` enregistre une proposition à vérifier indépendamment. La CLI peut
exporter les taux et le verdict avec `--measured-out` vers un nouveau fichier.
Le routeur continue de lire son fichier de mesures approuvées
`memory/measured_quality.json`. Il ignore le format du rapport d'évaluation.

## 4. Démonstration (preuve)

```bash
python -m scripts.agents.intelligence.cli demo
```

Pour utiliser un répertoire mémoire préparé et isolé, placez
`--memory-root /chemin/vers/memoire` avant `demo`. Le rapport est alors archivé
dans le sous-répertoire `evaluations/` de cette mémoire.

Le tableau décrit la démonstration hors ligne actuelle. La mesure historique
du 15 novembre reste documentée dans l’historique de ce fichier.

| Étape | Résultat |
|---|---|
| 1. Choisir un modèle | `openhands/deepseek-v4.1-flash` (moyen) ; `gpt-5.6` refusé (coût inconnu) |
| 2. Retrouver une connaissance | entrée `guard-git-value-options` (vérifiée) |
| 3. L'utiliser sur une tâche neuve | `git -C … push` → **BLOCKED** par la règle rappelée |
| 4. Mesurer avant/après | comportement historique pré-#71 **65 %** → garde durci **100 %** (**+35 points**, 0 régression sur le jeu de la démo) |
| 5. Enregistrer | proposition `keep` et rapport dans `memory/evaluations/` |

La démo reproduit le comportement du filtre historique avant #71, puis évalue
la fonction `decide()` du garde durci déjà présent sur le même jeu étiqueté.
Celui-ci couvre notamment les options git avec valeur, les arguments de wrapper
et les actions destructives de `find`. Le rapport archive ce résultat comme
proposition à examiner. [Durcissement #71](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/71)

## Limites honnêtes

- **Aucun appel LLM réel** n'est fait ici : la couche est déterministe et hors
  ligne. Les taux de qualité du catalogue sont des **priors**. Les résultats de
  la démonstration figurent dans son rapport d'évaluation.
- **Aucun modèle n'est `verified`** dans cet environnement : le routeur refuse
  donc un run réel (fail-closed). C'est voulu, pas un défaut.
- La démo mesure un jeu étiqueté du dépôt. L’attestation du jeu réservé et la
  preuve de retour arrière d’un Skill déployé restent à établir dans I-03.
- La mémoire est un JSON sur disque, pas une base : pas d'index sémantique
  vectoriel à ce stade.

## Prochaine étape (non faite)

1. Sonder réellement la disponibilité d'un modèle gratuit et marquer
   `verified = True` (puis relancer la démo en run réel).
2. Brancher `router.route` dans `orchestrator.py` à la place du modèle unique.
3. Étendre `measured_quality.json` avec de vrais résultats de missions.
