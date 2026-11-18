# TEL99 — Instructions de continuité pour agents (Codex, Copilot, Hermes et autres)

**Avant toute modification :** lire [issue #61](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/61) et [incident #60](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/60), puis consulter **les quatre documents** sur la branche `codex/tel99-quant-terminal` :
1. [Passation initiale](https://github.com/khalidd692/telcoin-trading-intelligence99/blob/codex/tel99-quant-terminal/docs/smart-view/PASSATION_SMART_VIEW_2026-11-13.md)
2. [Passation finale avec 11 expressions](https://github.com/khalidd692/telcoin-trading-intelligence99/blob/codex/tel99-quant-terminal/docs/smart-view/PASSATION_SMART_VIEW_2026-11-13_FINAL.md)
3. [Passation ultime — limites](https://github.com/khalidd692/telcoin-trading-intelligence99/blob/codex/tel99-quant-terminal/docs/smart-view/PASSATION_SMART_VIEW_2026-11-13_ULTIME.md)
4. [Vérification visuelle directe — correction importante](https://github.com/khalidd692/telcoin-trading-intelligence99/blob/codex/tel99-quant-terminal/docs/smart-view/VERIFICATION_VISUELLE_FINALE_2026-11-13.md)

**Ordre de préséance documentaire :** les constatations les plus récentes corrigent les affirmations anciennes lorsqu'elles portent sur la même chose ; conserver les anciennes archives intactes. Inventaire **21 widgets**, pas 22. Le Rule Scan affiche **visuellement** des cercles vrai/faux, contrairement aux rendus textuels initiaux ; 0 match complet alerte précoce, 2 matches complets invalidation (BTC/ETH) au moment de l'inspection. Les comptes individuels TEL étaient **contradictoires** et ne sont **pas un jeu de vérité terrain**. Les 11 expressions sont archivées ; **aucune performance statistique démontrée**. La saisonnalité « 5 ans » est un paramètre de fenêtre, pas cinq années de données.

## Branches et protection
- Produit : `codex/tel99-quant-terminal` ; workflows : `main` ; données : `tel99-live-data` ; évaluation : `tel99-evaluation-data`.
- Inspecter état des branches, workflows, code, tests, publications et journal avant tout changement. Pas de refonte, pas de suppression, pas de force-push, pas d'écrasement des snapshots, alertes, historiques ou évaluations. Modifications minimales, additives, versionnées, testées.
- Les liens des documents pointent vers la **branche produit** ; leur présence sur `main` n'est **pas** garantie. Ce fichier ne crée pas de fusion implicite.
- Aucun ordre réel **ni simulé**.

## Séparation des concepts
- `market_early_alert`, `market_confirmation`, `market_invalidation` et `risk_checked_buy` sont des objets distincts.
- Ne jamais présenter une alerte de marché comme achat confirmé. Sans frais, spread, liquidité, fraîcheur et RR net vérifiés, aucune confirmation d'achat.
- Ne pas bloquer le journal des alertes précoces avec les critères de risque d'exécution ; évaluer les rebonds manqués, faux positifs, latences et résultats 1h/4h/24h/7j **sans fuite temporelle**.
- Les niveaux de prix datés du 13/11/2026 ne sont pas des constantes de stratégie.
- **Sept alertes TradingView affichées ≠ watchers Smart View `w15`/`w1h` fonctionnels.** Les deux watchers avaient des résultats `skipped_plan`. Ne pas inférer une livraison effective.
- Ne pas déclarer autonomie cloud, fiabilité des alertes, stratégie rentable ou terminal opérationnel sans preuves de runs planifiés et de données prospectives.

## Avant de livrer
Tests reproductibles et CI, sources/horodatages, vérification du site et JSON déployés, observation de runs automatiques indépendants du PC, contrôle des alertes et du journal, compte rendu des limites. Ne pas modifier Smart View.

## Équipe d'agents (branche `agents/hermes-simple-team-20261114`)
- Trois agents actifs en lecture seule : `.agents/agents/tel99-{dev,analyst,verifier}.md`. Neuf spécialisations réservées, non actives, dans `.agents/agents/reserve/` (le SDK ne charge que les `*.md` de premier niveau).
- Configuration unique : `scripts/agents/team_config.py`. Les fichiers d'agents sont générés : `python scripts/agents/render_agents.py` puis `--check` en CI.
- Sécurité : garde-fou `PreToolUse` (`scripts/agents/guard/guard.py`, sortie 2 = blocage), outils réduits à `terminal`, `sub_agent_scope`, noms d'agents uniques par exécution, budgets plafonnés.
- Relance complète : `docs/agents/RELAUNCH_TEAM.md`.
- Ces fichiers n'activent aucune planification cloud, aucune fusion, aucun ordre. Ne pas ajouter de secret au dépôt.


## Mission prioritaire des AGENTS PERSONNELS — zéro copier-coller (18 novembre 2026)

**Ceci ne remplace pas les contraintes TEL99 ci-dessus.** Pour toute mission sur le noyau généraliste des agents, consulter d'abord le [dossier GitHub de conduite autonome](docs/agents/AUTONOMIE_ZERO_COPIER_COLLER/README.md), le [backlog 20 tâches](docs/agents/AUTONOMIE_ZERO_COPIER_COLLER/BACKLOG.json), le [protocole de reprise](docs/agents/AUTONOMIE_ZERO_COPIER_COLLER/EXECUTION_CONTINUE.md), et l'[issue maître #94](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/94).

**But impératif de l'utilisateur :** ne plus lui demander de copier-coller les réponses entre ChatGPT, Hermes, Kilo et OpenHands. Les trois chefs doivent utiliser GitHub comme registre de travail, produire les preuves, se transmettre les tâches, puis continuer la tâche suivante admissible sans solliciter le propriétaire pour des passations.

Les applications Hermes, Kilo, OpenHands sont des ateliers temporaires ; le **moteur d'agents appartient au propriétaire** et doit rester indépendant des trois interfaces. Réutiliser bus.py, store.py, memory.py, router.py, les guards et adapters déjà présents. Ne pas recréer l'existant.

Ce dossier est une **prescription de travail**, pas une preuve que les applications locales ont déjà un service GitHub automatique. Le transport Kilo est encore déclaré disconnected ; Hermes et Kilo nécessitent chacun une prise en charge runtime réelle. La PR #92 reprend déjà des travaux #79 et #89 : consulter son diff avant toute duplication.

**Ne pas s'arrêter après une PR ou une réponse :** valider les critères, enregistrer l'état et avancer à la tâche suivante, sauf quota/permissions/sécurité ou besoin humain réel. Aucun merge/déploiement/cron permanent/service payant/ordre financier sans autorisation.

## Codex — autonomie agents, issue #94

Pour toute mission Codex de finition du noyau d'agents (issue #94), consulter `docs/agents/AUTONOMIE_ZERO_COPIER_COLLER/CODEX_AUTONOMIE_EXECUTION.md` et les critères G0–G7 avant d'écrire. Respecter le rôle indépendant de Codex, les claims/leases, les PR existantes et l'interdiction de modifier en parallèle les mêmes fichiers qu'OpenHands, Kilo ou Hermes. Commencer par audit et tests reproductibles, puis PR draft isolée ; passer à la prochaine tâche admissible dans la limite du quota. Ni ce fichier ni `AGENTS.md` ne lancent Codex automatiquement ; aucune fusion, dépense, permission, mise en production, planification permanente ni ordre financier ne sont autorisés.
