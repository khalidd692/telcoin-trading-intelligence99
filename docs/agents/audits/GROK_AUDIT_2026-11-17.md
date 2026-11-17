# AUDIT EXTERNE — GROK — RAPPORT A–K (17 novembre 2026)
**Provenance :** texte fourni par le propriétaire avant le rapport Claude final.
**Nature :** avis externe, non vérification en direct. Les formulations « prouvé » sont celles de Grok, et non une certification indépendante.

## A. Verdict
Prototype multi-environnements avancé, pas encore produit généraliste autonome opérationnel. Existent : 3 rôles actifs + rôles de réserve ; garde PreToolUse, config unique, tests ; intelligence router/mémoire/amélioration ; bus v1 ; runs cloud ponctuels ; mémoire inter-run en PR ; cockpit/MCP/automation pilote ; charte. Non prouvés : autonomie longue, Kilo connecté, mémoire dans tous les runtimes, gain continu et supervision permanente. Fusion/sécurité/quota restent bloquants.

**Correction factuelle à l'avis Grok :** PR #76 est FUSIONNÉE sur main depuis le 16/11/2026 ; elle ne fait pas partie des PR encore ouvertes.

## B. Audit capacités selon Grok
- Collecte/analyse TEL déterministe : PROUVÉ selon Grok, sans valider qualité prédictive.
- Trois agents et PreToolUse : code+tests PROUVÉS ; délégation cloud ponctuelle PROUVÉE selon rapports.
- Déclenchement planifié PC éteint : PARTIEL, run ponctuel rapporté.
- Routeur, mémoire, auto-amélioration, bus : PARTIEL.
- Reprise interruptions, Kilo Windows intégré, cockpit temps réel, multi-projets isolés, benchmark commun, sécurité et utilisabilité non-programmeur : PARTIEL / NON PROUVÉ.

## C. Dix angles morts
1. Dette de fusion, divergence main et branches, surtout #79.
2. Machine à états et idempotence forte non démontrées en concurrence.
3. Absence de contrat de résultat strict et vérificateur indépendant instrumental.
4. Mémoire sans expiration/conflits de connaissances démontrés.
5. Quotas gratuits et disponibilité réelle des modèles sans sonde globale et budget dur.
6. Isolation multi-projets + injection de prompt non testées adversarialement.
7. Observabilité unifiée, signalement du blocage/échec/crash.
8. Coût de maintenance de triple pile (trois mémoires, hooks, UI).
9. Benchmark 24–72h d'autonomie multi-missions et interruptions.
10. Sur-ingénierie de chartes/bus pendant que l'exécution reste fragile.

## D. Corrections critiques
- P0 : révocation/rotation jeton exposé dans PR #88 et recherche des copies ; examen de #79 et intégration contrôlée dans main ; protection main et branche produit.
- P1 : mémoire inter-session réelle pour Hermes/Kilo/OpenHands ; seuil quotas uniforme ; modèle gratuit vérifié ; bus fail-closed / idempotence.
- P2 : inventaire MCP #88, pilote #89 et cockpit #87 après fiabilisation.

## E. Dix optimisations
1. Correction #79 + smoke ciblé.
2. Un modèle gratuit vérifié et routage vrai dans orchestrateur.
3. Test mémoire inter-session.
4. Benchmark minimal, 3 missions + interruption, scores.
5. Un bus plus simple avec CAS existant.
6. Vérificateur obligatoire avec verdict publié dans bus.
7. Geler les 9 rôles réservés s'ils sont inutiles ; ne pas les supprimer sans preuves.
8. Quotas durs et kill switch.
9. Logs structurés et statut unifié.
10. Skills minimaux réutilisables au lieu de nouveaux agents.

## F. Auto-amélioration
Observer vraies missions et verdict indépendant → proposer Skill ou règle versionnée → tester isolé → comparer succès/régressions/coût → conserver ou rejeter → mémoire + rollback possible. Ne pas entraîner les poids du modèle ; ne pas pousser directement la production.

## G. Bus GitHub
Contrat enveloppes existant, Kilo client en polling/webhook léger depuis Windows, scopes minimaux, corrélation unique, état durable CAS, acks, retries, offline explicite, garde-fous. Pas de second protocole.

## H. Répartition
Hermes = intelligence, routage, mémoire, Skills et évaluations.
OpenHands = cloud, quotas, planification, reprise et preuve.
Kilo = Windows, UI locale, livrables et validation indépendante.
Partagé = protocole, workflows, sécurité et changements mémoire affectant plusieurs équipes, revue croisée.

## I. Plan
1. Sécurité du jeton et des branches.
2. Orchestrateur corrigé #79 + run après revue/autorisation.
3. Mémoire prouvée dans trois environnements.
4. Modèle gratuit et router réellement testés.
5. Benchmark commun minimal.
6. Bus Kilo réel.
7. Un Skill amélioré avec rollback.
8. Cockpit, MCP et pilote ensuite.

## J. Critique
Trop de PR parallèles partagées ; triple pile fragmentée ; catalogue modèles vérifiés=False et fail-closed ; charte n'est pas mémoire effective ; rôle réserves non utilisés peuvent distraire ; risque de double UI.

## K. Trois découvertes et verdict
1. Bug #79 absent de main.
2. Kilo disconnected.
3. Auto-amélioration et mémoire non validées en continu.
Conseil Grok : geler nouveaux développements, traiter sécurité et #79, prouver mémoire, vérifier un modèle gratuit, mesurer cinq missions, livrer cockpit ensuite et archiver les doublons sans supprimer aveuglément.

**Attention :** Grok affirmait à tort que #76 était ouverte. Des états « PROUVÉ » du rapport sont déclarés par l'auditeur et doivent être recroisés avec code, CI et exécutions.
