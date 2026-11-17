# MISSION PERMANENTE — FINIR NOS AGENTS SANS COPIER-COLLER

**Ordre du propriétaire, 18 novembre 2026. Statut : dossier de conduite, pas un automate déjà activé.**

> « Je ne veux plus copier les réponses entre ChatGPT, mes trois conversations, Hermes, Kilo et OpenHands. Je veux que les chefs prennent eux-mêmes la suite et TERMINENT mon système personnel d'agents. »

## Règle maîtresse

**NE PLUS DEMANDER AU PROPRIÉTAIRE DE TRANSMETTRE UNE RÉPONSE OU UN PROMPT ENTRE AGENTS.**

Ce dépôt GitHub est le registre de missions et de livrables commun. Chaque chef le consulte, réalise sa part, vérifie les preuves, publie le résultat et poursuit la prochaine tâche admissible. Quand une action exige vraiment une autorisation humaine ou est techniquement inaccessible, il la marque BLOCKED/AWAITING_HUMAN avec la raison exacte et **continue toutes les autres tâches indépendantes**. Il ne s'arrête pas après une simple réponse, un rapport ou une PR.

L'objectif final est **notre moteur d'agents IA personnel**, portable et exploitable sans ouvrir Hermes, Kilo Agent Manager ou OpenHands. Ces plateformes ne sont que des ateliers temporaires. Le moteur aura toujours besoin d'un fournisseur de modèle et d'un environnement d'exécution disponibles : ils doivent être interchangeables.

## Sources de vérité

1. **CE DOSSIER :** ordre permanent, protocole de travail, tâches restantes et preuves de réception.
2. **BACKLOG.json :** liste stable d'objectifs, propriétaires, dépendances et tests. Ce n'est pas un état live : comparer aux PR/CI/runs avant d'agir.
3. **EXECUTION_CONTINUE.md :** boucle obligatoire « prendre → exécuter → vérifier → publier → reprendre », limites d'autonomie et traitement des blocages.
4. **CRITERES_DE_FIN.md :** conditions qui permettent de dire réellement « projet terminé ».
- **RECETTE_LIVE_ET_MODE_SECOURS_OPENHANDS.md :** preuve de l'enchaînement A→B avec un seul déclenchement, différence intra/inter-session, et mode de secours cloud si Kilo/Hermes ne se connectent pas.

5. **ETAT_ET_PR_EXISTANTES.md :** acquis, PR ouvertes, problèmes à ne pas recoder.
6. **INTERFACES_ET_PASSATIONS.md :** responsabilités et format unique de handoff.

Archive des quatre audits + plan :
https://github.com/khalidd692/telcoin-trading-intelligence99/pull/90

Directive propriété des agents :
https://github.com/khalidd692/telcoin-trading-intelligence99/blob/coordination/agent-team-boundaries-memory-20261117/docs/agents/audits/DIRECTIVE_SOUVERAINETE_AGENTS_2026-11-18.md

Mission précédente :
https://github.com/khalidd692/telcoin-trading-intelligence99/issues/67

## Ordre de priorité

**P0 sécurité / vérité :** ancien token OpenHands exposé, revue de la PR #79 et maintenant #92, protections de branches, état CAS/idempotence, validation réelle des critères, approbation sécurisée des missions.

**P1 autonomie sans copier-coller :** 1 entrée native de mission, protocole et transport utilisables, Kilo et Hermes capables de prendre leurs tâches sans intervention de l'utilisateur, reprise après crash/offline, mémoire par projet portable, router de modèles gratuits vérifiés.

**P2 fiabilité et qualité :** évaluation indépendante, Skills testés sur jeu réservé, rollback contrôlé, observations/alertes, cockpit sur preuves réelles, tests d'isolation multi-projets.

**P3 recette finale :** création d'une application neuve sans message manuel intermédiaire, preuve d'une tâche TEL99 protégée, reprise après interruption, deux projets isolés, fonctionnement du noyau quand un des trois ateliers est indisponible.

## Qui fait quoi

- **OpenHands** : chef exécution cloud / sécurité des runs / état CAS / continuité et intégration ; ne devient pas indispensable au noyau.
- **Kilo** : chef atelier Windows / lanceur natif / pont sortant GitHub / vérification de livrables ; ne prend pas un second verrou central.
- **Hermes** : chef intelligence / routeur gratuit / mémoire / Skills / évaluation de progrès ; ne valide jamais ses propres propositions.
- **Propriétaire** : définition du but et validations sensibles seulement. Pas de copier-coller ni arbitrages quotidiens de sous-tâches.

## Ne pas recommencer ce qui existe

La PR #76 a fusionné le socle. Sur main, scripts/agents/protocol/bus.py possède une machine à états ; store.py implémente FileStore/KvStore ; intelligence/memory.py a déjà versions et séparation par projet ; policy.py exclut déjà les PR prises pour des missions ; l'interface intelligence/cli.py actuelle est **hors-ligne de démonstration** et n'est pas une exécution d'agent LLM. L'adaptateur Kilo contient connected=False. **PR #92 est un correctif nouveau à examiner avant de recopier les changements de #79.**

## Ce qui est autorisé sans nouvelle intervention humaine

Inspecter, écrire des tests, corriger des bugs dans une branche isolée, produire des artefacts de démonstration, ouvrir/mettre à jour une PR en brouillon, consigner des preuves, s'échanger des messages sûrs dans GitHub, choisir le prochain objectif non bloqué. Utiliser uniquement les quotas gratuits vérifiés dans les limites déjà fixées ; STOP si quota inconnu/insuffisant ou autorisation douteuse.

**Non autorisé :** consommer un service payant, faire des ordres financiers réels/simulés, déployer en production, fusionner automatiquement, modifier les permissions, révoquer des secrets au nom de l'utilisateur, activer un cron permanent, exposer des secrets ou exécuter du code non fiable sans isolation.

## Vérité sur l'automatisation aujourd'hui

Ce dossier constitue **le travail commun**, mais un fichier GitHub n'allume pas à lui seul un agent. OpenHands a déjà répondu à des mentions GitHub dans l'issue #86 ; cela ne prouve pas qu'il poursuive indéfiniment. Kilo et Hermes locaux ne disposent pas encore d'un réceptionnaire GitHub réellement démontré. Leurs ponts d'entrée sont donc **la première condition du zéro copier-coller**. Ne jamais déclarer AUTO_CONTINUATION=PASS sans test réel : émission → réception → action → preuve → tâche suivante.

## Première action de chaque chef

Lire ce dossier, lire les PR existantes, déterminer sa première tâche admissible, travailler sans autre demande de prompt, enregistrer la preuve dans **l'issue de pilotage unique** et continuer la tâche suivante. Si son runtime n'a pas accès à cette issue, ouvrir un PR draft/une issue de relais sur GitHub et marquer le transport BLOCKED ; ne jamais inventer une réception.

**Définition de réussite :** le propriétaire donne une seule mission à son programme, ne transmet aucun message intermédiaire, et reçoit un livrable effectivement validé, avec mémoire récupérable et reprise après incident.

