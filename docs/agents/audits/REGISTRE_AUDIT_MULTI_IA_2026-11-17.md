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
