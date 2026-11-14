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
