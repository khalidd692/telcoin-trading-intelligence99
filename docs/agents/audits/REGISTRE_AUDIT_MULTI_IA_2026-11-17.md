# REGISTRE MAÎTRE D'AUDIT CONTRADICTOIRE — 17 novembre 2026
Objet : préserver sans perte les avis de Claude et Grok, vérifier les assertions et préparer la confrontation avec DeepSeek/Gemini. Ne pas confondre les rapports de modèles avec des faits.

## Sources versionnées
- Charte des chefs : PR #90, docs/agents/TEAM_CHARTER_MEMORY_2026-11-17.md.
- Claude intégralement conservé dans CLAUDE_AUDIT_FINAL_2026-11-17.md (ce dossier).
- Grok intégralement conservé dans GROK_AUDIT_2026-11-17.md (ce dossier).
- Rapport actuel des autres IA : DeepSeek et Gemini non encore reçus.
- PR #76 fusionnée sur main ; #79, #83, #85, #87–#91 ouvertes lors du dernier contrôle.
- Source de vérité : https://github.com/khalidd692/telcoin-trading-intelligence99/issues/67

## Points confirmés par lecture de fichiers GitHub
C1. scripts/agents/automation/orchestrator.py, main : verify_outcome ne juge PAS la satisfaction des critères ; statut « validated » = seulement run terminé, rôles ont rapporté, critère déclaré.
C2. main contient confirm_unknown=True et GET /events non paginé ; PR #79 correctifs non fusionnés.
C3. scripts/agents/intelligence/improvement.py : min_delta=0, aucune taille minimale, confidence basée sur delta et verified_by='improvement-loop' ; ne prouve pas auto-amélioration statistique, docstring dit non autonome.
C4. scripts/agents/protocol/adapters/kilo.py : connected=False, inbox/outbox sont des dossiers locaux au sandbox sans runner Windows.
C5. automation.config.json : quota_min_remaining=2, recette #89 = 12 ; incohérence pour objectif de réserve.
C6. scripts/agents/automation/policy.py : branche codex/tel99-quant-terminal non protégée explicitement dans PROTECTED_BRANCHES ; mission filtrée par label; IMPORTANT : la fonction is_eligible_mission CONTIENT DÉJÀ « if issue.get("pull_request"): return False ». La suggestion de Claude « filtre pull_request absent » est donc déjà traitée.
C7. load_state et save_state utilisent état complet sans CAS, avec chemins d'écriture avant/sans verrou ; risque de lost update à reproduire.
C8. state['active'] conserve issue, work_branch, started_at, owner mais pas cid quand conversation créée ; reprise potentiellement orpheline.
C9. github_token tombe sur GITHUB_TOKEN ; session_key peut lire /proc/1/environ ; corps de l'issue envoyé tel quel.
C10. CI GitHub Actions audit #79, #85, #89, #91 SUCCESS sur commits PR respectifs (tests unitaires réels, pas critères métier).
C11. L'ancienne exposition d'un jeton OpenHands dans PR #88 a été identifiée ; son retrait/rotation chez le fournisseur n'a pas été attesté. NE PAS recopier de token.
C12. Hermes adapter en processus présent dans repo, mais ne prouve pas lien avec Hermes Desktop local. Trois agents OpenHands cloud ont des runs ponctuels documentés #80/#84, non démonstration générale.
C13. PR #91 persiste fichier mémoire OpenHands dans GitHub, mais rappel automatique par nouveau sandbox non prouvé ; charte #90 ne suffit pas comme mémoire active.

## Risques / hypothèses NON confirmés comme exploits
R1. Journal KV monolithique : risque de dépasser limites à tester, pas observation réelle de saturation.
R2. Exécution arbitraire Windows depuis Kilo : risque préventif, pas compromission démontrée.
R3. Fuites des résultats dans bus public : vérifier où se trouve le stockage effectif avant de conclure.
R4. Validateur de PR GitHub : **déjà filtré par policy.py** ; ne pas réimplémenter.
R5. Différentes familles de modèles pour le vérificateur = diversité de jugement, PAS garantie d'indépendance ; preuves déterministes d'abord, si quota gratuit.
R6. Taille de benchmark (30 tâches×3, 24–72h) et tests statistiques = propositions de dimensionnement à calibrer et non invariants acquis.
R7. Le bus GitHub n'est pas un moteur de livraison temps réel garanti ; Windows offline = état en attente.

## Ordre de correction P0/P1 à soumettre aux chefs
P0 SECURITE : rotation clé compromise et preuve d'invalidation, scopes minimaux, branch rulesets.
P0 INTÉGRITÉ : prévenir double exécution/orphelins, état CAS/fencing, bornage journaux.
P0 VÉRITÉ : validateur d'acceptation par preuves, FAIL et NEEDS_HUMAN non publiés comme success verified.
P0 CORRECTION #79 : revue diff/CI/guard puis proposition de merge avec accord propriétaire, valider main après.
P0 APPROBATION : contenu de mission épinglé par hash et auteur/labeler autorisés + tests injection.
P1 MÉMOIRE : intégration #85/#91 et nouveau sandbox avec logs ; nouveaux processus Hermes et Kilo.
P1 MODELS : vérifier catalogue, disponibilité réelles modèles gratuits et quota unifié.
P1 BUS : Kilo client Windows pull + outbox/ack idempotent, aucun second verrou partagé ; authentification GitHub.
P1 APPRENTISSAGE : vrais outcomes grader externe, échantillon suffisant, held-out inaccessible au proposant, coût, rollback, nouvelles tâches.
P1 PRODUIT : cockpit #87 clairement lecture des dernières preuves, automate #89 inactif jusqu'à accord, tests multi-projets.

## Propriétaires
- Hermes : qualité/routeur/mémoire et propositions de Skill ; ne jamais s'attribuer verified à lui-même.
- OpenHands : orchestrateur, état/verrou, validation d'acceptation, exécution, quota et publication cloud.
- Kilo : validation externe, jeu réservé, Windows runner vers GitHub et test applications.
- Changements protocoles/workflows/garde/mémoire commune => revue croisée.
- Aucune fusion, déploiement, activation non autorisée ; aucun ordre financier réel ou simulé.

## Règle de consolidation ultérieure
Pour chaque idée DeepSeek/Gemini/Claude/Grok : source, affirmation, preuve fichier+commit/CI ou log de run, statut CONFIRMÉ/REPRODUIRE/HYPOTHÈSE/ERREUR, propriétaire, priorité, dépendances, test négatif, preuve d'acceptation.
Ne jamais supprimer une ancienne observation : l'annoter par correction datée. Aucun de ces avis n'autorise l'automatisation dangereuse.


---
## ADDENDUM — 17 NOVEMBRE 2026 — GEMINI + DEEPSEEK + PLAN FINAL
Les deux nouvelles analyses sont archivées distinctement :
- docs/agents/audits/GEMINI_AUDIT_2026-11-17.md (avis externe Gemini, sans accès GitHub direct)
- docs/agents/audits/DEEPSEEK_AUDIT_2026-11-17.md (avis externe DeepSeek, pages PR consultées mais code non exécuté)
- docs/agents/audits/PLAN_MAITRE_4_IA_2026-11-17.md (**consolidation et portes de validation**)
Règle : préserver les conclusions antérieures, appliquer les correctifs de vérification sans effacer l'historique.

### Nouveaux points utiles
N1. Gemini : prévention de boucles webhook/cron, bornes d'événements et hop_count, context pruning et tests déterministes avant dépense LLM ; économie annoncée NON mesurée.
N2. Gemini : scénarios de saturation RAM Windows lorsque plusieurs outils lancés, mais **les modèles locaux sont mis de côté**, donc ne pas les relancer.
N3. Gemini/DeepSeek : isoler noyau/TEL99, projets et secrets ; l'extraction vers un nouveau repo ne doit PAS être automatique.
N4. DeepSeek : plan de sauvegarde/restauration privée et chiffrée du KV ; aucun export de mémoire sensible dans un dépôt public.
N5. DeepSeek : alertes hors modèle, kill-switch fournisseur, et gestion de l'état inconnu ; la révocation n'interrompt pas instantanément toutes conversations.
N6. Tous : banc de tests comportementaux indépendant des agents candidats et vérificateur jugeant critères réellement exécutés.

### Réfutations / restrictions vérifiées
R8. bus.py contient déjà une machine à états, et store.py FileStore/KvStore : **ne pas recréer un bus entier**.
R9. memory.py expose déjà schéma versionné et isolation par projet/common : **tester la persistance inter-runs plutôt que recoder ces deux principes**.
R10. Les labels GitHub ne sont pas un claim atomique/CAS ; aucune garantie exactly-once native. Proposition Gemini de changement atomique par label à REJETER comme mécanisme de verrou.
R11. Un PAT fine-grained GitHub donne des droits au dépôt et à une catégorie, pas un scope natif « seulement bus/ ». Éviter Contents write si issues suffisent.
R12. DeepSeek annonce 10 conversations/jour, d'anciens rapports mentionnent 20 : **quota actuel inconnu**, lire API propre au compte.
R13. Les chiffres de performance (-20/-60% de tokens, 20 tâches, 24–72h, délais en jours) sont des hypothèses de planification, pas des faits établis.
R14. Le correctif PR #79 change une politique de confirmation : revue de sécurité obligatoire avant fusion. Aucune fusion demandée ni réalisée dans cet archivage.
R15. PR #90 et #91 ne sont pas preuve que Hermes/Kilo/OpenHands CHARGENT cette charte automatiquement ; il faut test fresh session réel.

### Plan validable retenu
0) Clé exposée / branch rulesets et sécurité
1) Revoir #79, tests garde et vraie API, intégrer SEULEMENT sur accord
2) Solidifier état CAS / conversation_id / journal / anti-boucles
3) Vérification déterministe par critère et mémoire seulement sur mission acceptée
4) Approbation mission hash / contrôle identité / injections
5) Mémoire inter-session et sauvegarde sûre
6) Modèles gratuits, quotas et routeur mesuré
7) Kilo pull GitHub et preuve e2e OFFLINE/reconnexion
8) Auto-amélioration held-out et rollback
9) Cockpit sourcé, alertes et deuxième projet isolé
10) Endurance graduelle et rapport PASS/FAIL/BLOCKED
Les owners précis, tests négatifs et portes d'acceptation sont dans PLAN_MAITRE_4_IA_2026-11-17.md.

### Statut d'archivage
Les quatre analyses externes sont enregistrées sous forme de **retranscriptions structurées détaillées**, et non comme copies littérales garanties mot pour mot. Les messages originaux demeurent dans cette conversation. Le plan est un document DRAFT sur une branche isolée, aucune activation, fusion ou modification production.
