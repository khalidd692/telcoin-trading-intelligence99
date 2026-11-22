# AUDIT EXTERNE — CLAUDE — RAPPORT FINAL A–K (17 novembre 2026)
**Provenance :** texte intégral des conclusions opérationnelles de Claude transmis par le propriétaire dans la conversation le 17 novembre 2026.
**Nature :** avis externe, non validation du système. Ne pas confondre [P] (Claude a lu), [T] (tiers), [R] (risque à reproduire), [H] (hypothèse).
**Périmètre réellement lu par Claude :** orchestrator.py, kilo.py, improvement.py, PR #79 et #90. Claude n'a PAS lu policy.py, bus.py, store.py, router.py, memory.py, workflows ni log CI. **Aucune modification du dépôt par Claude.**

## A. Verdict indépendant
Le garde-fou d'exécution dispose d'un verrou CAS, d'un comportement fail-closed, d'un frein d'urgence et d'un mode dry_run par défaut. La preuve de délégation de trois sous-agents et production de texte ne prouve ni la justesse des résultats, ni la vérification indépendante, ni l'amélioration mesurée.

## B. Audit de vérité
- PROUVÉ [P] : mécanisme CAS tel qu'écrit ; échec fermé avant dépense ; défauts de main corrigés en PR #79.
- PROUVÉ [T] : CI de #79 rapportée comme verte, environ 696 tests ; contrôler la preuve sur le commit exact.
- PARTIEL [P] : exécutions cloud rapportées par #79, mais automations INACTIVE. Le prompt/tags indiquent « lecture seule » : une automation programmée qui produit du code n'est pas démontrée.
- NON PROUVÉ : récupération mémoire Hermes/Kilo en nouvelle session, autonomie longue ou multi-projets, gain réel de l'auto-amélioration.
- BLOQUÉ : adaptateur Kilo déclaré déconnecté sur GitHub.

## C. Dix angles morts
1. Vérificateur et développeur héritent du même modèle (model='inherit') : indépendance **cognitive** non garantie, bien que rôles distincts ; ceci ne remplace pas une vérification déterministe.
2. validated ne juge pas les critères d'acceptation, seulement la présence de rapports.
3. Au crash, active n'a pas forcément conversation_id ; réconciliation peut remettre en file pendant qu'une conversation ancienne fonctionne.
4. Journal monolithique et non borné dans une clé KV.
5. load_state avant verrou / save_state sur chemins sans verrou : risque de mises à jour perdues.
6. Corps d'issue GitHub inséré tel quel dans le prompt, risque de modification post-approbation et injection.
7. Filtre pull_request potentiellement absent selon Claude [R], **à vérifier séparément** (voir registre de vérification).
8. Jeux réservés exposés aux agents si stockés en public [H], risque de contamination.
9. Kilo exécutant du code sur Windows hôte, risque d'exécution arbitraire sans isolation [H].
10. record_outcome peut contenir 2 000 caractères de résultat par rôle ; risque de fuite de secrets si artefacts sont publiés [R].

## D. Corrections : critères de réussite réels
### D1. Juger les critères d'acceptation
- Chaque critère doit avoir un ID et un contrôle indépendant du modèle : ci (run/check sur SHA), diff (chemins autorisés), grep (interdictions), file (existence/conformité), human (approbation explicite).
- Sans contrôle exécutable ou approbation humaine : NEEDS_HUMAN, jamais PASS.
- verify_outcome exige criteria_checked et tous PASS pour MISSION_ACCEPTED. Séparer EXÉCUTION_TERMINÉE, RÔLES_RAPPORTÉS, MISSION_ACCEPTÉE.
- Vérificateur retourne JSON structuré (criterion_id, verdict, evidence_ref). Orchestrateur rejoue les preuves peu coûteuses, sinon UNVERIFIED.
- Si possible et gratuit : verifier_model d'une autre famille, mais cela ne remplace pas les contrôles déterministes.
- Tests négatifs : rapport « PASS » contradictoire aux artefacts ; observation completed mais pas de preuve ; rejeu de run identique donnant verdict identique.

### D2. État, crash, idempotence
- Réutiliser CAS existant (kv_get_meta, if_version) via cas_update(key, fn), retraiter 409. Ne pas créer de deuxième service de verrou.
- État par mission : project/mission/id avec status, attempt, conversation_id, SHA, résultat ; journal par run, borné/archivé.
- Avant possession vérifiée du verrou, seulement journal propre au run ; vérifier ownership (« fencing ») avant écriture.
- Persister conversation_id immédiatement après création et confronter état live avant relance ; interrompre uniquement si autorisé/possible, confirmer la fin plutôt que supposer.
- Identifiant stable de mission/corps approuvé/tentative. Commentaires GitHub idempotents, rechercher marqueur déjà publié.
- Tests stress : 2 processus/1 000 courses ; jamais deux conversations vivantes ni perte processed ; kill -9 injecté à des étapes critiques puis reprise exacte ; diagnostic KV meta supported=true sur environnement réel.

### D3. Approbation sûre des missions GitHub
- Approbation explicite par acteur autorisé, portant hash normalisé du titre, corps et critères, revalidé juste avant démarrage.
- Vérifier auteur, association, labeler et état de l'issue ; ignorer PR étiquetée.
- Limiter longueur/contrôler caractères spéciaux/Unicode invisibles, HTML et confusions de délimiteurs ; traiter les textes de mission comme données non fiables.
- Défense principale = permissions, confinement, garde d'outils, règles de sécurité et validateur déterministe, pas le simple prompt.
- Tests : édition après approbation bloquée, mauvais auteur ignoré, tentative d'injection neutralisée, PR filtrée, 20 tentatives d'injection sans effet interdit.

### Autres corrections P0/P1
- Révoquer et faire tourner le jeton exposé, prouver l'échec de l'ancien.
- PR #79 : revue indépendante, tests puis fusion SEULEMENT sur autorisation propriétaire ; tester ensuite main.
- Protection main via ruleset, checks obligatoires et interdiction force-push ; ne pas imposer une revue impossible sur compte solo.
- Token GitHub dédié à privilèges minimaux ; scanner secret dans sorties bus.
- Cockpit #87 et autres PR : à intégrer après fiabilisation, pas à reconstruire.

## E. Dix optimisations à fort rendement
1. Vérificateur avec famille de modèle différente, **si accessible gratuitement**.
2. Borner journal, archivage.
3. Persister conversation_id.
4. Filtrer PR hors liste missions.
5. Contrôles déterministes ci/diff/grep/file/human.
6. Marqueurs idempotents dans commentaires.
7. Requêtes conditionnelles ETag, à vérifier selon limites GitHub.
8. Identité/version de clés par projet.
9. Coûts (tokens, secondes) dans outcomes.
10. Campagne de tests d'injection sur chaque PR.

## F. Auto-amélioration crédible
- Constats : min_delta=0 peut produire KEEP sur petit échantillon ; confiance 0.5+|delta| sans n ; success fourni par appelant ; verified_by=improvement-loop (auto-évaluation) ; sans held-out ni rollback ; compare des modèles, pas des Skills.
- Remplacer modèle isolé par config_id versionné/hash (modèle, prompt, version des Skills) ; conserver API compare avec adaptation.
- Sous effectif insuffisant : INCONCLUSIVE. Proposition initiale Claude : 30 tâches indépendantes ×3 répétitions À CALIBRER PAR SIMULATION, pas un chiffre validé.
- Paires appariées et McNemar exact si adapté ; exemple 6 paires favorables/0 contraires donne p voisin de 0,03 bilatéral ; importance des répétitions, variabilité et unité statistique = tâche.
- Confiance avec n, répétitions, intervalles (Wilson) et p ; éviter équivalence automatique entre p et qualité réelle.
- Développement sur dev, adoption sur held-out protégé de l'agent candidat (environnement privé/isolé ; pas nécessairement tout le dépôt privé).
- grader_id externe au proposant, tests déterministes ou autre juge et contrôles humains échantillonnés ; vérification séparée.
- Budget/latence plafonnés ; version active de Skill déployée uniquement par PR et autorisation ; rollback PR proposé après régression sans autofusion.
- Tests : taux faux KEEP simulé <=5% (cible à valider), puissance 80% pour gain réel +20 points (déduire n de simulation), « 3 tâches +33% » = INCONCLUSIVE.

## G. Bus GitHub / Kilo
- Pas de second verrou : OpenHands seul propriétaire de la machine d'états partagée et du verrou ; Kilo client répondeur avec idempotence locale.
- Transport candidat : commentaires GitHub structurés d'une issue autorisée ; request_id, correlation_id, expires_at ; enveloppe result/evidence ; accusé de réception avec ID/hash.
- Identité via compte/token GitHub autorisé ; **attention** aux éditions, rejeu, compromise du compte et données non fiables. Pas de cryptographie superflue si mécanisme autorisé et authentifié suffit.
- Jeton fine-grained pour Kilo : dépôt précis ; Issues read/write pour messages ; pas d'admin, PR, Actions ou Contents write ; lecture du code avec credentials lecture seule si nécessaire ; stockage dans gestionnaire d'identifiants Windows.
- SHA approuvé, exécution isolée dans Windows Sandbox/VM sans secrets. Pas d'exécution arbitraire sur la machine hôte.
- PC éteint : demande en file, état awaiting_validation, 0 dépense, reprise à la reconnexion.
- Tests : message émis par mauvais compte rejeté, doublon sans effet double, push interdit renvoie 403, 48 h hors ligne sans coût, édition détectée.

## H. Responsabilités
- OpenHands : exécution cloud, état et verrou uniques de mission, journal, livraison cloud.
- Hermes : routeur, mémoire, proposition Skills ; ne s'auto-note pas.
- Kilo : vérification indépendante et tests réservés dans environnement isolé ; ne prend pas le verrou cloud.
- Revue croisée et accord propriétaire pour verify_outcome, policy, garde, protection, adoption des Skills, opérations sensibles.

## I. Plan ordonné
1. Révoquer secret, faire échouer ancien token.
2. Préparer/revoir PR #79, obtenir autorisation de fusion, vérifier sur main et environnement réel.
3. Corriger état/concurrence/conversation orpheline, puis critères d'acceptation et preuves.
4. Approbation par hash et tests injection.
5. Ruleset branches + jeton moindre privilège.
6. Boucle statistique + held-out isolé.
7. Transport Kilo réel + tests.
8. Réviser les PR restantes une à une, rebase ciblé sans reconstruction.

## J. Critiques
- Faux serveur e2e ayant imité ancien endpoint ; tests ne remplacent pas API réelle.
- Même modèle pour verifier/developer n'est pas un contrôle critique indépendant suffisant.
- Rapports rédigés par agents comme preuve unique.
- base_branch par défaut = agents/hermes-simple-team-20261114, pas main.
- Risques de conflits de PR et de redondances UI/mémoires.
- Dépôt public : ne pas y mettre secrets, tests réservés exposés, journaux privés.

## K. Trois découvertes principales
1. Le vérificateur et validated donnent une illusion de fiabilité tant que les critères ne sont pas vraiment jugés.
2. Conversations orphelines après interruption et état active insuffisant.
3. Besoin d'un stockage isolé pour jeux d'évaluation réservés et résultats potentiellement privés du bus.

**Position finale de Claude :** traiter dans l'ordre sécurité, #79, état, validation des critères, approbation, permissions ; chaque étape par petite PR et preuves. Les recommandations détaillées au-delà de son périmètre restent à reproduire, pas à considérer comme des bugs confirmés.
