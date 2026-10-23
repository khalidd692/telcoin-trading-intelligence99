# Rapport externe — DeepSeek
**Projet :** khalidd692/telcoin-trading-intelligence99  
**Statut :** rapport transmis par l'utilisateur ; affirmations techniques à vérifier indépendamment avant toute modification  
**Date d'enregistrement :** 2026-10-23

> DeepSeek indique avoir inspecté le dépôt public. Le texte transmis mentionne des références fichier/ligne, mais ne fournit pas les lignes précises. Les affirmations spécifiques sont conservées comme conclusions de DeepSeek, non comme vérifications indépendantes de cet archivage.

---

## Rapport original transmis

Rapport d’audit et d’architecture — Agent IA autonome TEL/USDT

Ce rapport s’appuie sur l’inspection du dépôt public khalidd692/telcoin-trading-intelligence99. Les faits vérifiés sont référencés par fichier et ligne ; les hypothèses et recommandations sont explicitement distinguées.

---

1. Diagnostic factuel du dépôt

1.1 Ce qui existe réellement (faits vérifiés)

Le dépôt n’est pas un prototype vide. Il contient déjà une base sérieuse, entièrement déterministe, sans LLM ni exécution d’ordres.

Collecte de données robuste. collector/tel_collector.py interroge MEXC et KuCoin en lecture seule, avec gestion des timeouts, des erreurs SSL/DNS, des schémas invalides et des données non finies. La collecte échoue en mode fermé si une source est indisponible : snapshot_id nul, statut ATTENDRE.

Analyse multi-timeframes déterministe. src/agent_analysis.py est une fonction pure : mêmes entrées → mêmes sorties, sans état persistant. Les bougies non clôturées sont explicitement exclues des indicateurs et des signaux. Le module detect_early_reversal() construit un setup à partir d’un extrême structurel et d’un retournement de momentum, avec des statuts explicites (ALERTE_PRÉCOCE, CONFIRMATION, INVALIDATION, ATTENDRE). La direction vient de l’extrême structurel, jamais d’une simple série de bougies, et une alerte exige plusieurs familles de preuves indépendantes.

Gestion d’état des alertes. src/alert_state.py assure la déduplication, l’identité stable des setups, la persistance atomique et l’interdiction de résoudre une alerte sur des données inexploitables. C’est un composant opérationnel mature.

Cadence de publication adaptative. src/publication_cadence.py a été créé parce que le cron GitHub ne tient pas ses promesses : 44 exécutions sur 168 h théoriques, soit 6,5 % de livraison. Le module met en place une chaîne auto-portée avec porte de publication et détection de chaîne morte.

Tests et backtest. Le dépôt contient de nombreux tests unitaires (test_agent_analysis.py, test_alert_state.py, test_backtest_harness.py, test_evaluate_prospective.py, etc.) et un protocole de backtest hors échantillon figé (OOS_PROTOCOL.md). Le workflow monitor.yml exécute ces tests avant toute collecte.

Backtest OOS : un résultat critique. OOS_RAPPORT.md et BACKTEST_HISTORIQUE_TEL.md sont sans ambiguïté : aucun des deux moteurs ne démontre de pouvoir prédictif. En 15m, 1h et 1j, le détecteur ne bat pas le hasard au seuil de 95 % ; seul le 4h montre un résultat marginalement significatif. Ce n’est pas un échec du système, c’est une information fondamentale pour la suite : l’agent ne doit pas être présenté comme un prédicteur.

1.2 Ce qui est absent ou seulement simulé

- Interprétation par IA (LLM) : absente ; système décrit comme 100 % déterministe.
- Mémoire structurée des décisions : partielle. alert_state.py conserve l’état des alertes, mais pas les raisonnements, contradictions détectées ni résultats prospectifs.
- Superviseur opérationnel : absent selon le rapport ; pas de composant vérifiant les échecs de workflow, la publication silencieuse ou des données trop anciennes.
- Récupération automatique contrôlée : limitée aux retries réseau dans monitor.yml (for attempt in 1 2 3), sans procédure de récupération suivie de vérification.
- Évaluation prospective automatisée des alertes : test_evaluate_prospective.py suggère une évaluation à 24 h, mais pas une boucle de rétroaction intégrée en production.
- Gestion du risque (taille de position, invalidation, slippage) : absente ; système en lecture seule.
- Intégration de la liquidité, du spread et du carnet d’ordres dans le signal : très partielle. tel_collector.py collecterait le carnet, mais agent_analysis.py ne l’utiliserait pas dans detect_early_reversal().
- Classification de régime de marché : champ regime rudimentaire, non utilisé pour moduler les seuils du détecteur.

1.3 Risques de divergence et dépendances fragiles

- continue-on-error: true sur la collecte (monitor.yml, étape Collect public market data). Après trois échecs, le workflow pourrait continuer et publier des données absentes ou périmées. Le fail-closed de agent_analysis.py protégerait l’analyse mais pas explicitement la publication.
- Dépendance à GitHub Actions pour orchestration, cadence et publication. Une panne GitHub ou une limitation de débit pourrait interrompre la surveillance sans alerte externe. publication_cadence.py atténuerait le problème du cron sans résoudre l’absence de dead man’s switch.
- Duplication potentielle entre monitor.py et tel_collector.py. monitor.py serait une version simplifiée pour la collecte 15m, tandis que tel_collector.py gérerait toutes les unités de temps et plusieurs exchanges. Il faut vérifier que les validations sont identiques.

---

2. Les 10 angles morts les plus importants

Classement par gravité × probabilité.

1. Absence de superviseur de santé système — gravité élevée, probabilité moyenne. Si monitor.yml échoue ou est désactivé, aucune alerte n’est envoyée ; le système peut être silencieusement mort.
2. continue-on-error: true sur la collecte — gravité moyenne, probabilité élevée. Une collecte en échec pourrait laisser passer une publication incomplète.
3. Pas d’évaluation prospective systématique des alertes — gravité élevée, probabilité certaine. Le backtest évalue le détecteur mais pas la valeur opérationnelle des alertes en production.
4. Mémoire limitée à l’état des alertes — gravité moyenne, probabilité certaine. Difficile d’auditer les raisons, contradictions et évolutions du contexte.
5. Pas de dead man’s switch externe — gravité élevée, probabilité faible mais impact potentiellement catastrophique.
6. Spread et liquidité non intégrés au signal — gravité moyenne, probabilité élevée. Un signal peut être techniquement correct mais économiquement inexploitable.
7. Régime de marché non utilisé pour moduler les seuils — gravité moyenne, probabilité moyenne.
8. Pas de tests d’intégration de bout en bout — gravité moyenne, probabilité moyenne.
9. agent_analysis.py ne bloque pas la publication en cas de UNAVAILABLE — gravité faible, probabilité moyenne ; le rapport peut être publié avec ATTENDRE sans incident explicite.
10. Pas de rotation ou limitation des permissions — gravité et probabilité faibles. Le workflow aurait contents: write, pages: write, id-token: write, actions: write ; permissions larges pour un système en lecture seule.

---

3. Améliorations à plus fort rendement

1. Ajouter un superviseur de santé avec alerte externe. Un workflow séparé ou un service comme healthchecks.io vérifie que site/agent_analysis.json est rafraîchi toutes les 20 minutes et envoie une alerte indépendante.
2. Supprimer continue-on-error: true sur la collecte et rendre l’échec bloquant. Après les retries, le workflow doit échouer et déclencher une alerte plutôt que publier un rapport dégradé.
3. Étendre alert_state.py en journal structuré des décisions. Ajouter un JSONL par analyse : timestamp, snapshot_id, statut, preuves, contradictions, confiance et résultat prospectif à 24 h.
4. Intégrer une évaluation prospective automatique. Réutiliser test_evaluate_prospective.py pour calculer quotidiennement précision et rappel des alertes de la veille et publier les métriques.
5. Ajouter un interpréteur LLM optionnel, strictement limité à l’explication. Il résume les preuves, signale les contradictions entre unités de temps et rédige un commentaire ; il ne produit pas de signaux.

---

4. Architecture cible recommandée

Architecture hybride : cœur décisionnel déterministe et vérifiable ; IA générative en périphérie pour l’interprétation et la communication.

4.1 Flux textuel

Collecteur (MEXC, KuCoin) → Validateur (fail-closed) → Moteur quantitatif (agent_analysis.py) → Mémoire structurée (JSONL / SQLite) ↔ Évaluateur prospectif (précision, rappel) → Superviseur (santé, fraîcheur) → Alertes et rapports (dashboard, e-mail). Interpréteur LLM optionnel en lecture seule.

Règles :
- Le moteur quantitatif seul décide du statut (ALERTE_PRÉCOCE, CONFIRMATION, etc.).
- Le LLM ne reçoit que les sorties du moteur et les preuves associées ; il commente sans modifier le statut.
- Le superviseur peut bloquer la publication si les données sont périmées ou incohérentes.
- La mémoire est écrite par le moteur et l’évaluateur prospectif, jamais par le LLM.

4.2 Responsabilités

- Collecteur (tel_collector.py) : APIs publiques MEXC/KuCoin → tel_snapshot.json ; pas d’ordres ni de clés ; fail-closed si une source manque.
- Moteur quantitatif (agent_analysis.py) : snapshot validé → agent_analysis.json ; ne prédit pas et ne dimensionne pas ; fonction pure sans état.
- Mémoire (nouveau src/memory_store.py) : sorties moteur et résultats prospectifs → journal JSONL ou SQLite légère ; append-only, horodaté, schéma versionné.
- Évaluateur prospectif (nouveau src/prospective_evaluator.py) : journal et prix futurs → métriques précision/rappel ; fenêtre glissante, tests hors échantillon.
- Superviseur (nouveau src/supervisor.py) : heartbeats, âge des fichiers, codes de sortie → alertes de panne et blocage publication ; ne remplace pas le moteur ; dead man’s switch externe.
- Interpréteur LLM (nouveau src/llm_interpreter.py) : sorties et preuves → commentaire ; pas de modification de statut ; filtrage des prompts et budget plafonné.
- Publication (publication_cadence.py) : statut et commentaire → commit Git/dashboard ; ne publie pas si le superviseur est en alerte ; porte de publication et déduplication.

---

5. Composants existants : conserver, modifier, ajouter

À conserver tels quels selon DeepSeek :
- src/agent_analysis.py : cœur déterministe, bien testé et fail-closed.
- src/alert_state.py : base pour déduplication et historique.
- collector/tel_collector.py : collecte multi-exchange.
- src/publication_cadence.py : solution pragmatique au cron GitHub.
- tests/test_backtest_harness.py, tests/test_agent_analysis.py, tests/test_alert_state.py : socle de non-régression.

À modifier :
- monitor.yml : retirer continue-on-error: true ; ajouter superviseur avant publication et job séparé de health check.
- alert_state.py : ajouter reasoning (preuves, contradictions) et lien vers snapshot.
- publication_cadence.py : contrôle de santé avant republication ; ne pas relancer si superviseur en alerte.

À ajouter :
- src/memory_store.py : journal JSONL append-only avec schéma versionné.
- src/prospective_evaluator.py : précision/rappel à 24 h et 72 h, intervalles de confiance de Wilson.
- src/supervisor.py : âge des fichiers, cohérence des collection_id, exécution des workflows et alertes indépendantes.
- src/llm_interpreter.py : commentaire LLM avec plafond de tokens et fallback déterministe.
- tests/test_supervisor.py, tests/test_memory_store.py, tests/test_prospective_evaluator.py : tests de résilience et non-régression.

---

6. Tests indispensables et critères de réussite

- Panne de collecte : simuler indisponibilité MEXC et KuCoin ; superviseur alerte et publication bloquée. Le workflow échoue avec code non nul ; alerte externe reçue en moins de 5 minutes.
- Données périmées : snapshot âgé de plus de 20 minutes ; statut ATTENDRE et aucune alerte ALERTE_PRÉCOCE ou CONFIRMATION.
- Incohérence multi-exchange : prix MEXC/KuCoin divergents au-delà d’un seuil ; snapshot rejeté et incident journalisé.
- Non-régression LLM : même snapshot avec/sans LLM ; statut et preuves identiques.
- Évaluation prospective : rejouer 100 alertes avec résultats à 24 h ; métriques reproductibles et compatibles avec le backtest OOS.
- Injection de prompt : texte malveillant dans un champ de données ; réponse neutre ou erreur, aucun effet de bord.
- Dead man’s switch : désactiver le workflow principal 30 minutes ; service externe envoie une alerte.

---

7. Plan de réalisation le plus rapide et le plus sûr

Phase 0 — Immédiat (0–2 jours, coût nul)
- Fichiers : monitor.yml, src/supervisor.py minimal.
- Retirer continue-on-error: true ; job health-check vérifiant âge de site/agent_analysis.json et échouant si >20 min ; configurer healthchecks.io gratuit avec ping toutes les 15 minutes.
- Test : test_supervisor.py avec panne simulée.
- Acceptation : panne de collecte ou arrêt du workflow déclenche une alerte externe en moins de 5 minutes.

Phase 1 — Première version fonctionnelle de l’agent (3–5 jours)
- Fichiers : src/memory_store.py, src/prospective_evaluator.py, alert_state.py.
- Journaliser chaque analyse en JSONL ; calculer quotidiennement précision/rappel des alertes de la veille ; champ reasoning.
- Tests : test_memory_store.py, test_prospective_evaluator.py.
- Acceptation : dashboard des métriques des 7 derniers jours ; au moins 50 analyses journalisées.

Phase 2 — Interprétation par LLM (5–7 jours, coût API optionnel)
- Fichiers : src/llm_interpreter.py, monitor.yml.
- Intégrer un LLM (ex. GPT-4o-mini ou modèle local via Ollama) pour commenter les preuves ; maximum un appel/analyse et 500 tokens ; fallback déterministe.
- Tests : test_llm_interpreter.py, non-régression et injection de prompt.
- Acceptation : commentaire ne contredisant jamais le statut ; coût mensuel inférieur à 10 $ pour une exécution toutes les 15 minutes.

Phase 3 — Apprentissage et amélioration continue (2–4 semaines)
- Étendre scripts/backtest/run_oos.py et src/prospective_evaluator.py.
- Tester les nouveaux seuils hors production avec validation croisée temporelle ; ne jamais modifier la production sur quelques observations.
- Acceptation : toute modification de seuil justifiée par un test hors échantillon avec intervalle de confiance à 95 %.

---

8. Coût estimé

- Coût nul : GitHub Actions déjà utilisé, healthchecks.io gratuit, JSONL dans le dépôt, tests unitaires.
- Infrastructure : 5–10 €/mois pour un petit VPS facultatif si le superviseur doit être indépendant de GitHub Actions ; sinon healthchecks.io pourrait suffire.
- API LLM : 0–10 €/mois selon le modèle et le nombre d’appels (rapport : environ 1 000 appels/mois à 0,001–0,01 $/appel). Ollama évite le coût d’API mais nécessite une machine adaptée ou accepte plus de latence.

Indispensable : superviseur, évaluation prospective et journal structuré. Intéressant mais différé : LLM tant que le pouvoir prédictif du moteur n’est pas démontré.

---

9. Désaccords et incertitudes nécessitant des preuves supplémentaires

1. Utilité réelle d’un LLM : le backtest OOS rapporté ne montre pas de pouvoir prédictif sur la plupart des unités de temps. Il faut prouver que l’interprétation LLM améliore précision/rappel ; sinon, le LLM reste un outil de communication.
2. Pertinence du 15 minutes pour TEL/USDT : spread et liquidité peuvent rendre les signaux inexploitable. Mesurer le spread moyen et la profondeur sur les 1 000 dernières bougies 15m ; si le spread dépasse 0,5 %, dégrader les alertes 15m en observation.
3. Fréquence optimale : publication_cadence.py publierait toutes les 13 minutes environ. Comparer la stabilité des alertes à 15m, 1h et 4h.
4. Charge cognitive : comparer l’usage avec/sans commentaire LLM et mesurer la confiance calibrée.

---

10. Recommandation finale

À construire en premier :
1. Superviseur de santé et dead man’s switch, pour détecter les arrêts silencieux.
2. Journal structuré des décisions et évaluation prospective.
3. Suppression de continue-on-error sur la collecte.

À ne pas construire maintenant :
- Un LLM qui génère des signaux ; le backtest OOS ne justifie pas de lui confier la décision.
- Un module d’exécution d’ordres ; rester en lecture seule tant qu’un avantage statistique n’est pas prouvé.
- Une base lourde ou un framework ; JSONL append-only et Python standard suffisent au départ.
- Un deuxième agent ou une architecture multi-agents ; privilégier la qualité des contrôles.

En résumé : rendre le système observable, mesurable et incapable de mourir silencieusement avant d’ajouter de l’IA générative. Le LLM pourra être une couche de communication, jamais le cœur décisionnel.

---

## Notes de synthèse (à compléter après comparaison)

- Convergences avec Gemini et Claude : supervision indépendante, mémoire/évaluation prospective, moteur déterministe souverain, LLM optionnel d'explication, pas de multi-agents ni d'ordres réels pour l'instant.
- Apport distinctif de DeepSeek : insiste sur l'échec statistique du backtest OOS, le risque de continue-on-error sur la collecte, les permissions du workflow, et l'intégration insuffisante du carnet/spread dans le signal.
- Vérifications prioritaires avant d'agir : confirmer le résultat « 44 exécutions sur 168 h (6,5 %) », la configuration continue-on-error, les permissions, la structure réelle du backtest OOS, et si le carnet collecté est réellement absent du moteur.
- Les chiffres de coût, seuils de spread (0,5 %), délais (20 minutes / 5 minutes) et budgets sont des propositions du rapport, pas des valeurs validées pour le projet.
