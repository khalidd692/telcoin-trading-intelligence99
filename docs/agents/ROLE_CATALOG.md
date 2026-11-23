# TEL99 — Catalogue extensible de 12 rôles
Les rôles sont des spécialisations logiques, **pas 12 processus autonomes actifs**.

| Rôle | Responsabilité |
|---|---|
| coordination | Découpage, dépendances, synthèse |
| development | Python, JavaScript, correctifs ciblés |
| quant | Indicateurs et validité des signaux |
| cloud | CI, horaires, déploiements contrôlés |
| quality | Tests, régressions, reproductibilité |
| security | Permissions, secrets, lecture seule |
| mobile | Expérience Android sans refonte |
| documentation | Passations, décisions, traçabilité |
| evaluation | Mesure prospective, biais temporels |
| market_data | Fraîcheur, Kraken, qualité des bougies |
| monitoring | Journaux, alertes, incidents |
| release | Comparaison, contrôle avant publication |

**Stratégie d'échelle :** 12 rôles, au plus 2 à 4 exécutions concurrentes lorsque le moteur Hermes le permet et que ses limites sont vérifiées. Des rôles supplémentaires sont possibles si un besoin réel est mesuré. 250 agents simultanés ne sont pas un objectif de qualité.

**Exécution actuelle :** le script `python scripts/agents/team_audit.py` vérifie les chemins associés à chaque rôle. Le workflow manuel produit un artefact JSON. Ce n'est pas un moteur de sous-agents IA; aucune intégration Hermes locale/cloud n'est prétendue. Pour connecter Hermes, il faudra vérifier ses commandes et ses capacités réelles dans l'environnement où il tourne. Aucun secret ni ordre de trading ne doit être ajouté.

## Exécution dans le superviseur local

Les trois profils OpenHands chargés restent définis dans `team_config.py`. Le profil `tel99-builder` de Kilo et les profils OpenHands en réserve sont des points d'entrée distincts du pilote Ollama. Le tableau décrit les capacités du superviseur local et leur état de vérification.

| Agent | Moteur et état dans le superviseur local | Outils et permissions | Entrée → sortie vérifiable | Mémoire et condition d'activation |
|---|---|---|---|---|
| `tel99-coordination` | Python déterministe, raccordé et vérifié sur fixture Linux | Catalogue et contrat local en lecture seule | Contrat scellé et fonction épinglée → affectation des étapes, modèles et SHA-256 du périmètre | Reçu `coordination_role` dans le checkpoint CAS. Activé avant les appels de chaque nouvelle mission d'équipe autorisée. La vérification recalcule le plan et refuse un reçu discordant. |
| `tel99-analyst` | Gemma 4 E4B via Ollama, vérifié sur Windows | Appel loopback borné et lecture de la fonction approuvée | Objectif et fonction → avis de 1 200 octets maximum avec SHA-256 | Reçu d'analyste en CAS, empreinte conservée après vérification. Activé sur les contrats d'équipe si le modèle est disponible. Un avis absent, trop long ou ayant la forme d'un programme bloque le worker. |
| `tel99-dev` | Modèle local épinglé au contrat, Gemma 4 ou Qwen2.5-Coder sur la campagne attestée | Génération locale bornée dans le worker existant, sans outil attribué au modèle | Objectif, fonction et avis non fiable → proposition de fonction et reçu SHA-256 | Candidat et diagnostic en CAS. Activé après autorisation et prévol. Le nombre d'essais est borné par le contrat et une exécution incertaine exige une réconciliation. |
| `tel99-verifier` | Docker indépendant, vérifié sur Windows et sur fixture Linux | Source Git épinglée, conteneur isolé, preuves locales sous le dossier d'état | Candidat et test approuvé → base rouge, candidat vert et empreintes des preuves | Reçu Docker et preuve de l'artefact conservés dans CAS. Activé après les contrôles du worker et de portée. Un conteneur indisponible ou un résultat inconnu bloque l'acceptation. |
| `tel99-security` | Python déterministe, raccordé et vérifié sur fixture Linux | AST Python et comparaison de source en lecture seule | Base et candidat → identité des lignes hors fonction, détection de nouveaux imports directs non standard, empreinte et verdict | Reçu `security_role` en CAS. Activé à la vérification d'une mission d'équipe. Refus avant Docker avec diagnostic borné. La vérification Docker reste obligatoire. |
| `tel99-cloud` | Réservé | Aucun outil attribué dans ce pilote | Run CI et mandat → rapport horodaté de fiabilité | Activation après vérification en lecture seule des permissions, du SHA et d'un run réel. |
| `tel99-mobile` | Réservé | Aucun outil attribué dans ce pilote | Parcours et tailles d'écran → observations et captures | Activation après une recette navigateur avec mesures reproductibles, sur bureau et mobile. |
| `tel99-documentation` | Réservé | Aucun outil attribué dans ce pilote | Décisions et preuves caviardées → passation versionnée | Activation après des contrôles de liens, de provenance et de confidentialité. |
| `tel99-evaluation` | Réservé dans la chaîne du worker | Aucun outil attribué dans ce pilote | Candidats et jeu réservé → comparaison indépendante | Activation dans la chaîne après preuve d'une comparaison reproductible et protection du jeu réservé. |
| `tel99-market-data` | Réservé | Aucun accès de marché attribué dans ce pilote | Instantané sourcé → contrôle de fraîcheur et de qualité | Activation après tests sur instantanés réels et périmés. |
| `tel99-monitoring` | Réservé | Aucun outil attribué dans ce pilote | Checkpoints et heartbeats → état et diagnostic horodatés | Activation après preuve de détection d'un worker interrompu et d'une donnée périmée. |
| `tel99-release` | Réservé | Aucun accès d'écriture attribué à ce rôle | Preuves vérifiées → manifeste de préparation de livraison | Activation après un test indépendant de la préparation et des contrôles de publication. |

La chaîne exécutée est **Coordination → Analyste → Développeur → Sécurité → Vérificateur**. Les deux contrôles Python interviennent dans le worker et le vérificateur existants. La liste `team` reste celle du mandat à trois rôles et continue à être vérifiée à l'admission GitHub. Les reçus antérieurs dépourvus de plan peuvent être vérifiés avec leur schéma historique. Dans ce cas, le rapport omet le reçu de Coordination.

Les reçus ajoutés sont des observations enregistrées, avec `role`, `engine`, `ok` et une empreinte ou un diagnostic borné. La Coordination et la Sécurité sont des fonctions déterministes locales sans identifiants ni accès GitHub propres. Le périmètre de Sécurité couvre les lignes hors fonction et les imports statiques directs. Les traces d'exécution et la vérification Docker apportent des preuves complémentaires.

Les preuves Windows de l'équipe initiale proviennent des [reçus du pilote à trois rôles](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94#issuecomment-7110099309) et des [résultats de la campagne GitHub à deux missions](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94#issuecomment-7114469111).

### Vérification des rôles déterministes

```sh
python -B -m unittest -v tests.test_local_team_roles
```

Pour la recette avec Docker réel, renseigner `TEL99_ROLE_TEST_DOCKER_IMAGE` avec le digest d'une image Python déjà disponible localement. Depuis PowerShell, par exemple avec cette image Python 3.12 utilisée dans la recette Linux si elle est présente sur le PC.

```powershell
$env:TEL99_ROLE_TEST_DOCKER_IMAGE = "python@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89"
python -B -m unittest -v tests.test_local_team_roles
```

La recette utilise un nouveau contrat de test et un répertoire CAS temporaire. Le superviseur, les rôles déterministes et Docker s'exécutent réellement. Les réponses de l'analyste et du développeur sont scriptées. Le résultat attendu est `ACCEPTED`, avec les deux reçus de rôle confirmés, le test de la base qui échoue (sortie 1) et le test du candidat qui réussit (sortie 0).
