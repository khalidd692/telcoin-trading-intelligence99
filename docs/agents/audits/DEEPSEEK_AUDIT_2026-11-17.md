# AUDIT EXTERNE — DEEPSEEK — RAPPORT A–K
**Réception : 17 novembre 2026.** Source : réponse DeepSeek fournie par le propriétaire dans cette conversation.
**Périmètre déclaré par DeepSeek :** lecture des pages dépôt, issue #67, PR #76/#79/#83/#85/#87/#88/#89/#90/#91, mais ni exécution du code, ni runs cloud, ni audit intégral de sources. Ceci est une **retranscription structurée détaillée**, non copie littérale mot à mot. Les chiffres et délais de son rapport sont des propositions ou observations indirectes.

## A. Verdict
Pile prometteuse, critique non fusionnée/non prouvée en conditions réelles. Trois constats centraux selon DeepSeek : #79 contient deux correctifs de confirmation et lecture événements pourtant non intégrés ; mémoire inter-sandboxes #85 prouvée pour un composant, pas pour Hermes/Kilo ; bus GitHub n'offre pas exactly-once ou claim atomique natif.

## B. Audit de vérité selon DeepSeek
| Capacité | Statut attribué | Observations de DeepSeek |
|---|---|---|
| 3 rôles cloud | Partiel | #79 cite run 58126453 avec 1/1/1 après patch ; valeur validée ne prouve pas qualité métier |
| Run sans PC | Prouvé ponctuel | #83 manuel/événement/cron ; automations actuellement inactives |
| Cron | Prouvé ponctuel | horaire cité 59 12 * * * ; ne promet pas ponctualité exacte |
| Mémoire KV inter-sandbox | Prouvé composant | #85 run A écrit, B rappelle ; pas généralisé |
| Hermes↔Kilo↔OpenHands | Non prouvé | Kilo connected=False, rappel non démontré |
| Routeur | Partiel | catalogue unverified, pas benchmark robuste |
| Auto-amélioration avec rollback | Non prouvé | pas de boucle réelle complète |
| Cockpit mobile | Partiel | #87 lecture seule, 22 tests cités, snapshot quota 2/20 |
| Sécurité des secrets | Risque connu | #88 token exposé, révocation non attestée |
| Branche main protégée | Non démontré | DeepSeek rapporte GET protection 403 et rulesets [] depuis #83 ; **403 ne prouve PAS automatiquement l'absence de protection** sans privilèges de lecture nécessaires |
| Tests nombreux | Prouvés comme runs rapportés | #85 711 tests, #83 691 tests selon descriptions |
| Autonomie longue, multi-projets | Non prouvé | pas de traces >20 minutes et 2 projets isolés |

## C. Dix angles morts
1. **Kill-switch externe** : flag KV dépend de la consultation par l'orchestrateur. Désactivation de l'automatisation et révocation de credentials constituent des recours d'urgence hors modèle. **Révocation n'interrompt pas nécessairement une conversation déjà en cours**, ne pas promettre stop instantané.
2. **Bus GitHub sans transaction label+commentaire** : risque double claim; besoin d'autorité unique et opération atomique testée.
3. **Skill drift** : nouveaux Skills sans tests comportementaux peuvent dégrader compétences.
4. **Contamination mémoire inter-projets** : scoping d'écriture/lecture et partage explicite à valider. **La mémoire du dépôt a déjà une isolation logique**, ne pas la présenter comme absente.
5. **Modèles gratuits** : coût non monétaire de quotas et limites de tokens, disponibilité variable ; DeepSeek cite 10 conversations/jour en BYOK, **pas applicable universellement ni confirmé pour le compte actuel**.
6. **Disaster recovery mémoire** : KV/stockage perdu ou indisponible ; export sécurisé, chiffré et restauration testée, pas dump privé dans Git public.
7. **PR croisées et conflits sémantiques** : #85/#87/#88/#89/#91 à examiner une par une, tests cumulés sur SHA final.
8. **Cockpit sans alerte proactive** : signaler blocage, quota, crash indépendamment du modèle en panne.
9. **Vérificateur same-model/same-memory** : indépendance nominale ; contrôles déterministes et diversité de famille si gratuit.
10. **Multi-projets** : identifier projet, politiques, budgets, mémoires propres ; ne pas mélanger TEL99 et projet B.

## D. Corrections critiques proposées
P0 :
- Révoquer/rotater OPENHANDS_API_KEY exposée en #88 ; vérifier invalidation et ne pas publier preuve contenant un secret.
- Revoir #79, confirmer endpoint /events/search et comportement confirmation UNKNOWN, exécuter CI puis test réel intégré ; toute fusion autorisée séparément.
- Branch ruleset : bloque push direct, checks obligatoires ; proposer 1 review si réalisable pour un repo solo, sinon contrôle compensatoire.
- Prise en charge idempotente ; **ne pas prétendre que label atomique ou un fichier GitHub fournit le même CAS que KV sans test de course**.
P1 :
- Mémoire Hermes/Kilo en nouvelle session, backend pertinent et sauvegardes ; projet isolé.
- Procédure stop externe ; prochaine action interdite quand credentials retirés, mais pas arrêt immédiat garanti.
- Benchmark qualité/coût/durée ; DeepSeek propose 20 tâches TEL99.
P2 :
- Alerte via webhook/email indépendante des agents ; polling cockpit avec timestamp et stale indication ; tests de crash.

## E. Dix optimisations et quantifications suggérées
1. Router par difficulté, règles/embeddings ; cible théorique -40 à -60% tokens, à mesurer.
2. Cache sémantique des réponses répétées ; -20 à -30% appels estimés, **danger de réponse périmée**, ne pas cacher prix/états de sécurité.
3. Retrieval ciblé au lieu de dump mémoire ; -30% tokens estimés, à mesurer.
4. Sous-tâches indépendantes parallèles ; -30% temps estimé ; attention ordre Analyst→Dev→Vérif, ne pas paralléliser les dépendants.
5. Test comportements Skill (5 cas/Skill proposés), et benchmark global.
6. Claim par label + lease TTL proposé ; label non atomique, donc corriger protocole.
7. Export mémoire « Git toutes N écritures » proposé ; **jamais le privé en dépôt public**, préférer sauvegarde chiffrée privée/restauration.
8. Vérificateur distinct et données brutes.
9. Budget dur durée/jetons avec arrêt statut BUDGET_EXCEEDED.
10. Secrets injectés côté environnement et scan gitleaks, jamais code/prompts.

## F. Auto-amélioration proposée
Observer échecs, timeouts, quotas ; Hermes émet hypothèse de correction sur branche self-improve ; tests déterministes / benchmark figé ; vérification indépendante autre modèle/outils ; décision keep/reject ; versionner Skill, rollback contrôlé ; mémoire sourcée mentionnant proposition, résultats et évaluateur.
**Critique :** benchmark visible au modèle proposant risque overfit. Prévoir ensemble tenu à l'écart, evaluator indépendant, tailles adéquates, coût et risque; ne pas autoriser auto-fusion ni promotion en prod.

## G. Bus GitHub proposé
- Identifiant de mission déterministe (project_id + issue_number + goal_hash).
- Claim via écriture conditionnelle d'un fichier de claim et lease TTL ; commentaires pour journaux.
- Scopes minimaux par acteur.
- **Corrections à intégrer :** GitHub Contents write ne permet pas de restreindre un token à un sous-dossier ; PUT sur un fichier et échec 409/422 n'est pas automatiquement un verrou prouvé. Le lock KV CAS déjà présent ne doit pas être remplacé inutilement ; choisir une unique autorité pour un type de mission.
- Acks, idempotence, reprise et tests deux concurrents ; Kilo pull et PC offline.

## H. Responsabilités proposées
Hermes = routage et mémoire, Skills ; Kilo = Windows/UI/livrables/vérification indépendante ; OpenHands = cloud/exécution/quotas/planification ; bus, protocole, sécurité, mémoire partagée = revue des trois et propriétaire.

## I. Plan DeepSeek
1. Révoquer ancien token, confirmer.
2. Revoir #79 et sécuriser l'intégration en main.
3. Activer protection main compatible permissions effectives.
4. Claim atomique + lease/règles idempotence.
5. Mémoire inter-session sur Hermes/Kilo/Cloud avec séparation par projet.
6. Benchmark 20 tâches TEL99, coûts/latences.
7. Cycle Skills auto-amélioration contrôlé, rollback.
8. Alertes indépendantes quota/blocage.
9. Cockpit actualisé avec horodatage.
10. Test de reprise crash et DR mémoire.
**Délais 30 minutes, 2 heures, 1 jour, 2 jours et garanties économiques ne sont pas validés par des tests sur ce projet.**

## J. Critiques
Ambition généraliste avant fiabilité TEL99, GitHub Issues comme bus best-effort, dépendance aux quotas/cloud provider, routeur sans sondes modèles réelles, charte sans tests et contrôles exécutable.

**Nuance :** recommandation « terminer TEL99 trading prédictif avant le noyau agents » ne suit pas nécessairement la priorité actuelle de l'utilisateur : nous devons terminer les trois environnements et conserver TEL99 sans l'altérer ; ne pas redéfinir son objectif à sa place.
**Nuance 2 :** GitHub Actions auto-hébergé dépendrait aussi d'un PC allumé ; un VPS peut être payant. Aucun « plan B cloud gratuit » garanti.
**Nuance 3 :** règles de branche et quotas dépendent des droits et plans réellement accessibles.

## K. Trois découvertes et conclusion
1. #79 reste la dette d'intégration bloquante, mais un correctif de sécurité et la validation de vrais critères doivent précéder toute activation sensible.
2. Mémoire inter-sandbox ≠ mémoire commune au bon agent au bon moment.
3. Bus GitHub = transport best-effort nécessitant autorité/claim et tests de concurrence, non simple gestion de labels.
Conclusion DeepSeek : geler nouvelles fonctionnalités, assurer P0, démontrer bus/mémoire/benchmarks avant auto-amélioration ; ne pas proclamer l'autonomie générale sans traces réelles.

## NOTE DE CONFRONTATION
Rapport reçu sans code exécuté par DeepSeek. Sur GitHub nous avons vérifié que bus.py fournit déjà une machine à états et memory.py contient des espaces projet ; aucun nouveau bus ou export privé dans le dépôt public ne doit être imposé. Les affirmations sur les quotas du plan gratuit et les protections GitHub nécessitent preuve contextualisée.
