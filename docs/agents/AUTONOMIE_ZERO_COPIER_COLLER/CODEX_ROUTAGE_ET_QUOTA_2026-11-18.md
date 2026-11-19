# CODEX REVIENT : QUOTA PROTÉGÉ, QUATRE CHEFS, ROUTAGE PAR DIFFICULTÉ

**18 novembre 2026.** Le propriétaire confirme que son **quota hebdomadaire Codex est de nouveau disponible**, après quatre jours d'attente. Il demande un routage intelligent de ses meilleurs modèles selon les tâches et leur difficulté. Cette directive complète la mission permanente #94, sans nouvelle dépense payante, merge ni déploiement.

## Stratégie

**Codex est notre architecte / ingénieur senior de réserve pour les corrections à risque et la revue indépendante** ; OpenHands assure continuité cloud et tâches codables sur serveur ; Kilo couvre la réalité Windows/IDE et réception GitHub ; Hermes assure routeur, mémoire, Skills et apprentissage vérifié. Ils construisent le **noyau d'agents IA du propriétaire**, indépendant des trois plateformes.

**Un seul auteur principal par fichier/lot.** Ne pas lancer OpenHands, Codex et Kilo en parallèle pour implémenter le même bug. Une équipe implémente et une autre vérifie.

## Les quatre couloirs

| Chef | Écrire / tester | Ne PAS dupliquer |
|---|---|---|
| **Codex** | Revue P0 sécurité, faux succès / acceptance verifier, CAS/lock/race, audit du moteur natif, tests adversariaux, correctifs complexes ciblés | UI de Kilo ; tâches cloud répétitives déjà livrées par OpenHands |
| **OpenHands** | Orchestration cloud, jobs, progression #94, bugfix sur ses branches, tests CI, reprise, préparation du mode secours | Ne pas concurrencer Codex sur la même correction ni créer des sessions à chaque commentaire |
| **Kilo** | Pont GitHub sortant sur PC Windows, test réel du runtime natif et de l'Agent Manager, compatibilité sur Windows, validation indépendante des livrables | Ne pas reconstruire une deuxième mémoire, un deuxième bus ou le moteur natif déjà livré en PR #95 |
| **Hermes** | Mémoire inter-sessions et exportable, routage multi-modèles gratuits, Skills validés, tests de rappel, contrat de communication GitHub | Ne pas remplacer notre noyau par une dépendance Hermes Desktop |

## Niveau de modèle / raisonnement — si disponible dans le client

- **Faible / modèle économe** : recherche de fichiers, lecture de journaux, documentation, petits renommages, vérifications simples. S'ils sont déterministes, utiliser d'abord scripts/CI sans LLM.
- **Moyen (par défaut)** : correction simple et bien délimitée, tests unitaires, revue d'un fichier, passation entre chefs, petites PR.
- **Élevé** : intégration inter-modules, code de sécurité, migrations de mémoire, concurrence, analyse d'erreurs difficiles, PR #92/#95.
- **Extra High ou niveau le plus fort disponible** : uniquement pour un problème P0 ayant résisté à une tentative moyenne/élevée, une faille profonde, ou un arbitrage architectural dont les tests contradictoires sont documentés. Pas pour recopier des textes.

**Choisir seulement parmi les modèles réellement présents dans le client et les droits du compte.** Le plus puissant ne signifie pas toujours le meilleur rendement. Réduire l'effort dès que la tâche est bornée. Réutiliser la même session si elle garde un contexte fiable, mais recommencer avec un bref handoff si la conversation boucle sans progrès.

## Budget de pilotage — recommandations, PAS quotas officiels

Codex et OpenHands ont des jauges indépendantes ; ne pas additionner les pourcentages. Respecter en priorité la fenêtre 5 h et la fenêtre hebdomadaire **réellement affichées** par Codex. Les plafonds 5 h / semaine et les quotas modèles varient selon compte et usage ; ne jamais inventer leur valeur.

- **50 % de l'enveloppe Codex disponible** : audit P0, correctifs difficiles, revue indépendante à fort impact.
- **25 %** : tests de résistance, régression, validation du noyau natif et du pont GitHub.
- **25 % de réserve** : imprévus/bloquants, ne pas la dépenser sur documentation ou petits travaux.
- À **moins de 30 % du quota hebdomadaire restant**, ne lancer que des urgences P0 ou validation finale. Quand l'une des fenêtres 5 h / semaine bloque, basculer les tâches codables vers OpenHands/Kilo/Hermes si leur quota séparé est disponible.
- **Aucun crédit payant, auto-top-up, abonnement, upgrade ou réinitialisation achetée**. Pas de code review automatique sur toutes les PR ; revue Codex seulement ciblée, un lot à la fois.

### Économiser les contextes
Le chef lit le README et le BACKLOG, mais à Codex on transmet **le ticket ciblé, la SHA/base, les fichiers concernés, les tests, les critères** ; pas l'historique de toutes les conversations. Éviter plusieurs MCP inutiles, réutiliser les logs, faire un préflight git/CI déterministe avant l'appel coûteux, créer de petites PR testables.

## Première mission Codex — audit S-03, S-04, S-05, Z-01

Priorité **P0**, prise en charge uniquement si aucun autre chef n'est en train de modifier les mêmes fichiers :
1. Examiner l'existant sur `main`, les PR **#92** (reprise anti-duplication, correctifs #79) et **#95** (noyau natif, tests offline). Identifier les véritables changements avant/après, les tests exécutables et les impacts de conflits. **La PR #95 a eu une clé potentiellement sensible dans sa description ; le texte a été masqué le 18/11 mais la rotation reste obligatoire.** Ne jamais recopier sa valeur dans tests, logs, commentaires ou prompts.
2. Vérifier en adversarial `verify_outcome` : trois rapports PASS et un test métier échoué doivent produire FAIL/NEEDS_HUMAN, jamais ACCEPTED.
3. Revoir état/locks/conversation_id : race, crash après POST, error/unknown API, double lancement, lock fencing, reprise idempotente. Ne pas considérer la PR #92 déjà fusionnée.
4. Revoir `scripts/agents/native` sur PR #95 : CLI, fournisseurs interchangeables, sécurité des écritures et de l'exécution de code, tests négatifs, fausses preuves, quotas, vrai fournisseur gratuit non prouvé. Noter que démonstration `ScriptedProvider` != appel LLM réel.
5. **D'abord rapport d'audit ciblé avec preuve**. Ensuite corriger sur branche isolée seulement un P0 reproductible qui n'est pas déjà corrigé ; PR draft, tests positifs/négatifs, SHAs, pas de merge.

**Ne pas faire** : redévelopper la CLI déjà proposée, recopier #92, restructurer tout le dépôt, valider l'agent par la prose du modèle, utiliser une clé cloud affichée dans GitHub.

## Coordination / zéro copier-coller

- Le dossier/issue #94 est la seule passation commune. Après chaque lot : `TASK_ID, OWNER, STATUS, PR, SHA, COMMANDS, PROOFS, NEXT_TASK, CODEX_USAGE`.
- OpenHands n'active pas Codex automatiquement à chaque commentaire GitHub. **Une revue GitHub `@codex review` peut être déclenchée ponctuellement si l'intégration Codex Code Review est active** ; cela ne garantit pas le lancement d'une session de développement Codex.
- Une **mission Codex Cloud/CLI de développement** requiert un client Codex réellement connecté et un déclencheur autorisé. Le simple fichier GitHub ne suffit pas à lancer Codex ou Kilo/Hermes tout seuls.
- Si Codex est indisponible ou son quota épuisé, les tâches de développement cloud indépendantes continuent dans OpenHands. Les validations critiques attendent une preuve indépendante et ne sont jamais marquées PASS artificiellement.

## Sécurité

Aucun merge, déploiement, ordre financier réel/simulé, permission, achat ou scheduler permanent sans consentement. Secrets hors GitHub. Vérification systématique du périmètre TEL99. L'objectif d'un système autonome ne permet pas d'outrepasser ces limites.


## OBSERVATION REELLE — BLOCAGE CODE REVIEW DU 18 NOVEMBRE 2026

Une seule revue ciblée PR #95 a été demandée via `@codex review` : https://github.com/khalidd692/telcoin-trading-intelligence99/pull/95#issuecomment-6964819864

**Réponse vérifiée du bot Codex** : `You have reached your Codex usage limits for code reviews.` — https://github.com/khalidd692/telcoin-trading-intelligence99/pull/95#issuecomment-6964822922

**Action** : NE PAS relancer `@codex review` maintenant, ne pas activer les revues automatiques. La revue est **BLOCKED_CODE_REVIEW_QUOTA**, pas « FAIL du code » et pas un verdict de sécurité. Cette limite particulière peut différer du quota normal de Codex CLI/IDE/Cloud ; **ne pas inférer** que le quota de développement annoncé rétabli par le propriétaire est épuisé. Vérifier la jauge Codex normale dans l'application/CLI avant une mission P0 et rester en consommation incluse, sans achat.

En attendant, **OpenHands** poursuit les tâches cloud sûres et les tests déterministes indépendants ; **Kilo et Hermes** ont leurs tâches d'interface et de mémoire comme précédemment. Codex devient le renfort de correction P0 quand une exécution normale est réellement disponible, pas un nouveau déclencheur GitHub de revue qui épuiserait un quota distinct.
