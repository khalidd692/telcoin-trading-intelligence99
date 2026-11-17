# PLAN MAÎTRE CONSOLIDÉ — QUATRE AUDITS IA (CLAUDE, GROK, GEMINI, DEEPSEEK)
**Version 1 — 17 novembre 2026.** Coordination de Hermes, Kilo Crew, OpenHands Cloud.
**Statut : PR documentaire DRAFT ; proposition de travaux vérifiables, pas autorisation de merge, dépense, déploiement ou exécution financière.**
**Projet :** Notre système généraliste multi-agents personnel. TEL99 reste protégé. Ne pas reconstruire ni multiplier agents, routeurs, mémoires, UIs ou bus sans défaut prouvé.
**Sources :** docs/agents/audits/{CLAUDE_AUDIT_FINAL,GROK_AUDIT,GEMINI_AUDIT,DEEPSEEK_AUDIT}_2026-11-17.md ; PR #76 fusionnée, #79/#83/#85/#87/#88/#89/#90/#91 draft ; issue #67.

## 0. Discipline de preuve et arbitrage des quatre modèles
- CONFIRMÉ = code GitHub lu sur version/commit explicite ou GitHub Actions réellement observée ; preuves métier = artefacts et checks exécutés au SHA, test du composant réel.
- DOCUMENTÉ = rapport d'agent ou description de PR avec identifiants ; n'implique pas succès de l'objectif.
- RISQUE À REPRODUIRE = défaut possible vu par inspection, sans reproduction réelle.
- PROPOSITION = conseil d'architecte IA, chiffrage à mesurer, sans réalisation.
- RÉFUTÉ / DÉJÀ FAIT = ne pas recréer.
- Tout changement critique a test négatif (FAUX POSITIF/CRASH/CONCURRENCE/QUOTA) et preuve de non-régression.

### État directement vérifié
- PR #76 est fusionnée ; #79/#83/#85/#87/#88/#89/#90/#91 restent ouvertes dans dernier inventaire.
- Sur main, orchestrator.py a encore confirm_unknown=True et GET .../events ; #79 contient une correction proposée, non intégrée.
- verify_outcome valide la fin, les observations des rôles, et la déclaration d'un critère ; il NE juge PAS si le critère est atteint.
- state active n'enregistre pas toujours conversation_id ; save_state recopie l'état entier sans CAS sur plusieurs chemins ; journal monolithique non borné ; vraies conséquences à reproduire.
- scripts/agents/protocol/adapters/kilo.py = connected=False, pas de transport Windows live.
- scripts/agents/protocol/bus.py CONTIENT DÉJÀ une machine à états et des enveloppes ; protocol/store.py propose FileStore et KvStore ; réutiliser, vérifier atomicité des writes, ne pas reconstruire.
- scripts/agents/intelligence/memory.py CONTIENT DÉJÀ SCHEMA_VERSION, entrées versionnées et séparation projet/common ; tester strictement scoping et backend inter-runs, ne pas inventer un « projet » nouveau.
- scripts/agents/automation/policy.py EXCLUT DÉJÀ les PR de is_eligible_mission ; ne pas recoder ce filtre. Il faut plutôt contrôler identités, approbation par hash et branche produit.
- catalog.py déclare plusieurs modèles avec verified=False ; router.py les rejette sur run réel ; santé dynamique des providers à établir.
- improvement.py : KEEP sur petit échantillon, confidence ne dépend pas de n, verified_by=improvement-loop ; pas de held-out ni promotion sûre démontrée.
- Les PR de tests sont vertes pour plusieurs commits, mais cela prouve les tests présents, pas la réussite des missions générales.
- Jeton OpenHands exposé en PR #88 dans passé ; rotation non vérifiée.
- Local LLMs sont écartés **par décision du propriétaire** : utiliser les modèles cloud gratuits disponibles et gratuits réellement vérifiés.
- Aucun achat financier réel/simulé ou modification du terminal TEL99 public n'est autorisé.

## 1. Trois chefs et propriété explicite
**OpenHands — propriétaire de l'exécution cloud :** orchestrateur, run/mission state, lock CAS existant, journal, quota, sécurité exécution, API, validation automatique de résultat, cockpit cloud, scheduler OFF sauf accord. Seul écrivain de l'état global de mission cloud.
**Hermes — propriétaire de l'intelligence :** catalogue/routeur, apprentissage mesuré, mémoire commune, Skills candidates et évaluations. Ne peut jamais auto-certifier une amélioration.
**Kilo — propriétaire de l'exécution Windows et validation indépendante :** applications locales, runner Kilo pull GitHub, statuts/workspaces Windows, tests indépendants et benchmark tenu à l'écart du proposant. Kilo ne prend pas un second verrou central, n'écrit pas l'état maître OpenHands.
**Partagé sous revue croisée :** envelope/protocol v1, sécurité, schémas, mémoire commune, GitHub workflows, définition de DONE, protections de branches. Chaque changement a un unique auteur responsable et un réviseur non auteur. Pas de modifications simultanées d'un même fichier partagé.

## 2. Phases et portes d'acceptation

### PHASE P0-A — Incident de secret et contrôle de la production [OpenHands + propriétaire]
- L'ancien token OpenHands en PR #88 doit être considéré compromis. Le PROPRIÉTAIRE révoque/rotater le jeton dans le fournisseur et ajuste les secrets autorisés ; les agents peuvent inspecter les références SANS révéler la valeur. Prouver l'invalidation de l'ancien par un résultat synthétique sans secret.
- Scanner repo, descriptions, commentaires, journaux, artefacts historiques, .env et historique Git ; ne pas publier la valeur.
- Vérifier GitHub rulesets réels sur main et codex/tel99-quant-terminal, pas interpréter un simple HTTP 403 comme absence certaine ; plan compatible repo solo, checks CI obligatoire, pas de direct push/force-push ; secrets et permissions dédiés.
- **GATE** : accès compromis désactivé attesté ; permissions vérifiées ; aucune automatisation sensible sur credentials incertains.

### PHASE P0-B — Compléter la PR #79 avant tout mode unattended [OpenHands + Kilo relecteur]
- Comparer #79 à main (PR #76 déjà fusionnée), vérifier lecture paginée /events/search sur vraie API et politique confirm_unknown. La correction 'confirm_unknown=False' est acceptable uniquement si les actions à risque inconnu restent bloquées par un garde déterministe ; tester actions interdites avant changement d'autorisation.
- CI, tests API réels à coût borné, tests de sécurité, puis préparer merge limité pour accord humain ; tester SHA intégré sur main après autorisation.
- **GATE** : pas de waiting_for_confirmation non résoluble, 1/1/1 observations réelles (pas qualité de la mission), tous cas dangereux refusés, aucun faux skip. #83 documentaire ne signifie pas production continue.

### PHASE P0-C — Mission-state, verrou CAS, crash, observabilité durable [OpenHands]
- **Réutiliser** CAS déjà dans acquire_lock et stockage actuel, introduire CAS updates pour état par mission ou clé versionnée, journal par run borné/archivé. États : queued→approved→running→awaiting_validation→accepted/rejected/blocked, et stop/retry avec transitions explicites.
- Persister conversation_id dès retour create; idempotence mission_id = project + issue + hash d'approbation, tentative versionnée; avant retry interroger état vrai de conversation précédente, interrompre si autorisé puis confirmer arrêt, sinon BLOCKED. Verrou expiré ne prouve pas que conversation ancienne est terminée.
- Fencing : contrôler ownership de lock avant chaque écriture ; éviter double exécution, status perdu, processed régressif ; anti-boucles (max hops, source événement, budget).
- **GATE** : deux runners concurrents en KV factice CAS avec ≥1000 interleavings testés, aucun double start ; injection interruption/crash aux principaux points de commit et reprise sans travail/ack dupliqué ; diagnostique API réel ; ne pas publier logs secrets.

### PHASE P0-D — Contrat de résultat et vérificateur indépendant [OpenHands implémente, Kilo vérifie, Hermes définit grades]
- Distinguer RUN_FINISHED (exécution), AGENTS_REPORTED (rôles), CRITERIA_CHECKED (tests), MISSION_ACCEPTED (résultat), AWAITING_HUMAN (critère manuel).
- Définir pour chaque critère id/type/commande sûre/preuve/SHA : ci, diff, file, grep, schema, tests du code exécuté, human. Le rapport LLM du Vérificateur est informatif ; l'orchestrateur REJOUE les checks déterministes sur le commit/artefact ; JSON strict et provenance.
- Un critère non mesurable => NEEDS_HUMAN/UNVERIFIED, jamais PASS ; FAIL du vérificateur ne doit jamais enregistrer verified=True sur le bus ou dans la mémoire.
- Si quota gratuit le permet, famille de modèle différente pour audit critique, mais tests déterministes sont l'ancre.
- **GATE** : fixtures négatives où trois agents disent « PASS » mais fichier/test faux -> MISSION_ACCEPTED=false ; run sans artefact réel -> unverified ; PASS complet seulement avec preuves et relecture.

### PHASE P0-E — Chaîne d'approbation GitHub et hygiène entrées [OpenHands + Kilo]
- Labels seuls insuffisants. Approbation explicite par acteur autorisé, liée à un hash du titre/corps/critères, fixée avant run et comparée juste avant action. Vérifier author/labeler, ignorer PR (déjà codé), contrôles non modifiables silencieusement.
- Traiter Issues, commentaires, logs, documents et Skills reçus comme données NON FIABLES. Tailles, caractères invisibles, in-band injections, secrets et exfiltration ; confinement outils.
- Tests de prompt injection : édition après approbation, auteur interdit, issue/PR malveillante, commentaires modifiés, logs piégés, 20 scénarios variés selon niveau de risque ; aucune opération interdite.
- **GATE** : pas de mission non approuvée, pas de contournement des garde-fous, piste d'audit reproductible.

### PHASE P1-A — Mémoire inter-environnements et reprise [Hermes propriétaire + OpenHands/Kilo contributeurs]
- Comparer #85/#91, réutiliser version, projet/common, provenance, dédup, expiry déjà existants. Prouver l'accès inter-sandbox KV et Hermes/Kilo nouvelle session locale. Donner schéma de communication/transport, pas supposer même disque/compte.
- Pas de données sensibles privées dans Git public. Sauvegarde privée/chiffrée du KV et test réel de restauration d'un échantillon; ne pas exporter logs/secrets en public.
- Rotation des connaissances obsolètes, contradictions, origine, âge, scope de lecture, suppression logique du cache; defense prompt injection en mémoire.
- **GATE** : écrit A/Rappel B sans injecter le texte, recherche correcte, refus inter-projets non autorisé, export/restore sur backend vierge, pas de fuite.

### PHASE P1-B — Modèles gratuits disponibles, quotas, routeur [Hermes + OpenHands]
- Probes authentifiés réels, free-only, quota, contexte maximum, tool support, statut/TTL et fallback ; aucun verified=True si simple déclaration. Router intelligent branché sur les résultats mesurés.
- Unifier les seuils de quotas entre config main et #89 sans contourner plafond ; conserver réserve définie par propriétaire, 0 modèles payants, stop on UNKNOWN.
- Prioriser tests et déterminisme avant appel LLM ; context pruning avec fichiers/diffs/rappel ciblé. Ne pas réactiver les LLM locaux.
- **GATE** : test routage disponible/unavailable/fallback sans coût imprévu ; preuve de run modèle gratuit et refus de lancer si quota inconnu ; coût/latence réellement consignés.

### PHASE P1-C — Bus GitHub réel vers Kilo local [Kilo auteur runner + OpenHands transport + Hermes contrat]
- Conserver protocol/envelope/bus.py ; GitHub sert au transport et aux messages durables, PAS serrure transactionnelle implicite. Un seul arbitre de mission (OpenHands KV CAS pour missions cloud, ou stratégie CAS explicite et démontrée pour mission pure GitHub).
- Kilo Windows POLL sortant, sans port entrant/tunnel. Comptes/scopes GitHub dédiés : préférer Issues read/write + Contents read, pas Contents write large sans nécessité; si écriture code requise, branch/worktree isolé et règles.
- request_id, correlation_id, approved_sha, expire_at, destinataire, ack et résultat; Kilo déduplique requests; refuse les étrangers, un message signé par login non autorisé, une réponse modifiée, sortie de scope. État OFFLINE honnête, cloud poursuit indépendamment les missions qui n'exigent pas Kilo.
- Tests livraisons au moins une fois + dedup côté récepteur, fenêtre crash entre claim et publication, Kilo absent 48h, retour, deux consommateurs simulés, données non fiables, aucun doublon et aucune dépense quand absent.
- Kilo exécute le code non fiable en Windows Sandbox/VM ou conteneur isolé, sans secrets, pas sur Windows hôte administrateur.
- **GATE** : GitHub Issue A -> Kilo reçoit/traite -> résultat réel et SHA -> OpenHands retrouve/verifie -> Hermes mémorise uniquement outcome validé ; PC OFF en attente/reconnexion sans fausse réussite.

### PHASE P1-D — Self-improvement vérifiée [Hermes propriétaire + Kilo grader + OpenHands runner]
- Garder improvement.py comme base, revoir compare/KEEP et réutiliser router/measured_quality/memory. outcome réel = tests/grader externe, et non success déclaré par candidat. config_id = hash (modèle+prompt+Skill version).
- Après erreur répétée : proposer Skill/recette versionnée en branche isolée ; test smoke/development ; test held-out protégé du candidat et non publiquement accessible s'il contient réponses sensibles ; mesurer qualité, sécurité, coût, tokens/latence, réussite par tâche, variabilité, usage sur une tâche NOUVELLE.
- INCONCLUSIVE si échantillon insuffisant ; seuil/gate à calibrer expérimentalement, pas « 3 tâches +33% » ni 20 tâches automatiquement concluantes ; envisager test apparié, intervalle de confiance et répétitions selon type de données.
- Kilo indépendant note les preuves, Hermes ne signe jamais sa propre réussite ; aucune altération des garde-fous, évaluateur ou politique par candidat.
- Adoption dans environnement test seulement si preuves et autorisation ; version immuable/rollback, surveillance et PR réversion si régression. Ne jamais autofusionner, autodeployer ni modifier poids modèle.
- **GATE** : un bon Skill adopté en test puis réutilisé sur tâche inconnue ; un mauvais Skill rejeté ; un échantillon minuscule déclaré INCONCLUSIVE ; rollback testé sans perte.

### PHASE P2 — Produit Android et gestion multi-projets [OpenHands + Kilo + Hermes]
- Réutiliser #87 cockpit lecture seule, pas le reconstruire ; état sourcé avec horodatage/staleness, RUNNING/WAITING/FAILED/ACCEPTED réels, quota inconnu affiché inconnu, links vers preuves.
- Alerte hors LLM si blocage, quota, crash ; aucun bouton Stop/Lancer sans API vraiment branchée/autorisée. Alternative légère STATUS.md possible, non « temps réel ».
- Gérer projet B sandbox non financier et TEL99 chacun avec workspace, mémoire, permissions, quota et barrière stricte ; ne pas découpler par nouvelle réarchitecture/dépôt tant que isolation logique suffit.
- Anti-boucles des workflows GitHub et ordres multiples, éviter double UI (Windows Kilo versus observabilité OpenHands), procédures de stop/recovery indépendantes de l'agent.
- Pilote #89 doit rester inactif tant que gate P0/P1 non franchie ; activation uniquement sur accord propriétaire.
- **GATE** : démo d'un projet B de test, pas de fuite TEL99 ; cockpit mobile affiche données provenant réellement des runs ; panne/STOP/QUOTA visible ; une mission planifiée ponctuelle autorisée avec budget.

### PHASE P3 — Endurance et livraison [tous]
- Benchmark minimal de développement (p.ex. 10–20 tâches de formation et un ensemble de contrôle indépendant ; ajuster par puissance et quotas). Évaluer : succès de critères, fausses acceptations=0 sur fixtures négatives, coût, délai, intervention humaine, reprise, mémoire, stabilité et refus d'actions interdites.
- Campagne d'endurance graduée : 3 missions puis 5, puis 24h et 48–72h seulement si budget et accès le permettent. Éteindre PC/Kilo, injecter crash cloud simulé, garder cloud indépendant des tâches Kilo, examiner erreurs. Ne pas promettre qu'un plan gratuit permet 20 missions/jour.
- Bilan par chef : PASS/FAIL/BLOCKED avec SHA, logs, commandes, captures et coûts, run IDs ; un seul tableau de suivi source #67 et PR de livraison ; marquer 'terminé' uniquement quand les gates essentielles sont prouvées.

## 3. Fusion / PR existantes
- Ne **pas** fusionner ni fermer automatiquement. Revoir #79 avec priorité critique, sans ouvrir second correctif concurrent si cherry-pick/rebase suffit.
- #90 contient charte et audits sur une branche de coordination : documentation seule, pas mémoire runtime ; à revoir.
- #85/#91 mémoire : vérifier si #91 est seulement doc de charte et #85 backend, ne pas les « fusionner » automatiquement comme deux moteurs concurrents.
- #83 et #78 contiennent les preuves ; garder comme archivage, pas forcer code non nécessaire.
- #88 inventaire MCP : choisir uniquement outils dont utilité est démontrée, scanner sécurité avant toute intégration.
- #89 recette d'automation inactive ; ne pas activer avant gates.
- #87 UI déjà développée : gel modification des fonctionnalités, seulement correctifs sourçage/sécurité après backend.
- Anciennes #63/#66/#71–#75 reprises par #76, pas de merge aveugle.
- Branch rulesets et merges nécessitent accord propriétaire et vérification des permissions du dépôt.

## 4. Échecs fréquents à éviter (confrontation critique)
- **Labels GitHub ≠ CAS** : plusieurs modifications concurrentes peuvent se marcher dessus. Une « PUT file » simple ne prouve pas, à elle seule, acquisition exclusive d'un lease ; tester vraie API / KV CAS.
- **GitHub fine-grained PAT n'offre pas une autorisation Contents write par chemin**. Si un runner local n'a besoin que d'issues, ne pas lui donner droits d'écrire code.
- **Stop global** : le flag KV n'interrompt pas magiquement une conversation lancée sur un autre hôte ; arrêt chez fournisseur/révocation puis réconciliation.
- **Protéger le dépôt de benchmarks** : un jeu de régression public est utile, mais la décision held-out ne doit pas être contrôlée par l'auteur de Skill. Ne pas exposer données privées.
- **Même modèle pour vérificateur** : risque de biais partagé ; modèle de famille différente est un complément seulement, pas substitution à critères exécutables.
- **Séparation du code TEL99** : bonne idée à étudier, mais aucune migration lourde tant que l'isolation actuelle peut être vérifiée et renforcée.
- **Quotas 10/j ou 20/j** : métriques de compte varient ; lire source exacte, ne pas citer plan hypothétique.
- **Économies tokens 20–60%, sprint de dix jours, 100% endurance** : chiffres non observés, à traiter comme objectifs à mesurer.
- **Filtre PR comme mission** : policy.py le fait déjà ; ne pas recoder.
- **Mémoire par projet et machine d'états** : existent déjà ; vérifier fonctionnement, corriger atomicité et inter-runs, ne pas recoder.

## 5. Contrat de livraison pour chefs
Chaque chef publie dans issue #67 et sa PR un résumé format :
CHEF | SHA_BRANCHE | QUOI_MODIFIÉ | TESTS_COMMANDES_RÉSULTATS | CAS_NÉGATIFS | RUN_RÉEL_OU_SIMULATION | QUOTA_AVANT_APRÈS | MÉMOIRE_RAPPEL_PREUVE | DEPENDANCES | PROCHAINE_ACTION | PASS/FAIL/BLOCKED.
Pas de réponse « 100% terminé » sans démonstration. Pas de nouveau routeur, mémoire, bus ou UI sans analyse de l'existant. Travail autonome borné dans des branches isolées, interdit merge, production, secrets, finance et modèles payants sans accord.

## 6. Références
- Mission maîtresse : https://github.com/khalidd692/telcoin-trading-intelligence99/issues/67
- Charte : https://github.com/khalidd692/telcoin-trading-intelligence99/pull/90
- #76 fusionnée ; #79 correctif ; #83 cloud preuves ; #85 mémoire ; #87 cockpit ; #88 MCP ; #89 pilote ; #91 mémoire charte.
- Dossiers audits : docs/agents/audits/CLAUDE_AUDIT_FINAL_2026-11-17.md ; GROK_AUDIT_2026-11-17.md ; GEMINI_AUDIT_2026-11-17.md ; DEEPSEEK_AUDIT_2026-11-17.md.

**Règle finale :** transformer les recommandations des modèles en corrections testables, ne pas confondre rapports et exécution. Aucun de ces documents n'active les agents. Les chefs doivent accepter explicitement la mission dans leurs environnements pour la réaliser.


---
## ADDENDUM PRIORITAIRE — 18 novembre 2026 : LA LIBERTÉ DU PROPRIÉTAIRE PRIME
Le propriétaire confirme : **« Hermes, Kilo et OpenHands m'aident à construire mes agents. C'est ça le but. Je veux être libre. »**

**Référence complète et critères de sortie :** [DIRECTIVE_SOUVERAINETE_AGENTS_2026-11-18.md](DIRECTIVE_SOUVERAINETE_AGENTS_2026-11-18.md).

**Changement d'interprétation obligatoire pour les chefs :** Hermes, Kilo Crew et OpenHands sont des ATELIERS ET ADAPTATEURS FACULTATIFS qui aident à développer et tester le **moteur d'agents personnel possédé par l'utilisateur**. Ils ne doivent pas devenir des dépendances obligatoires du noyau. Le travail sur le bus GitHub reste demandé pour collaborer entre ateliers, mais le système natif doit également pouvoir exécuter des missions locales avec FileStore sans GitHub, dans les limites de ses modèles et ressources.

**Ajout au gate P1 :** démontrer au moins une mission réellement exécutée depuis notre propre entrée native (CLI/application) sans aucune des trois applications ouvertes : modèle interchangeable réellement accessible et gratuit, exécution contrôlée, fichiers, tests déterministes, mémoire, reprise et preuves ; et tester l'absence de chaque plateforme. Les tests purement offline/démonstration existants ne suffisent PAS.

Conserver la priorité P0 sécurité/validation/reprise. Ne pas reconstruire bus.py/router.py/memory.py. Pas de nouveau framework ni de nouveau service payant. Le moteur IA a toujours besoin d'un modèle et de calcul ; « indépendance » signifie PORTABILITÉ ET CONTRÔLE, pas une ressource cloud infinie.
