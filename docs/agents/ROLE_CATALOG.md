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
