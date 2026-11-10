# TEL99 Quant Terminal — incrément 1, 2026-11-10

Mandat : MASTER PROMPT fourni le 10 novembre ; exécution autonome autorisée, aucun ordre réel/paper, aucune fusion ni publication publique.
Base isolée : b7cccbb9ef672f6f7da543c0159c7c025d79c995 (branche de recherche avec corrections des phases et historique vérifié).

## Choix
Conserver le dashboard et les moteurs existants ; ajouter `site/terminal/` et un adaptateur Python standard-library. Une réécriture React/backend permanent ajouterait installation et hébergement sans résoudre le manque d'historique. Un nouvel iframe TradingView ne donnerait pas accès au laboratoire. Le terminal statique reste portable, rapide, vérifiable et compatible GitHub Pages après autorisation. Graphe Lightweight Charts local, version figée, licence et attribution conservées.

## Contrats et ordre d'exécution
1. Audit : inventaire complet, lecture des composants et workflows, état des tests, exports MCP bruts horodatés. Conserver les empreintes et anomalies. Base : 425 tests Python, 3 skips.
2. `src/terminal/model.py` : `validate_dataset(dataset, as_of)` produit barres fermées, segments, exclusions ; `analyze(dataset, as_of)` produit séries/indicateurs par segment ; `decision(frames, as_of)` produit observation expérimentale, preuves, contradictions, invalidation ; `risk_plan(...)` refuse paramètres invalides et plafonne risque/cash frais inclus. Tests avant implémentation : bougie ouverte, doublon, ordre, OHLC, mèche, trous, données périmées, causality, RR/capital.
3. `scripts/terminal/research.py` : deux variantes séparées figées avant exécution (cassure 20 / reprise RSI30), cible 2R, stop creux des 10 dernières barres -0,5 ATR, expiration moteur existant (entrée +20, soit 21 barres inspectées). Réutiliser EMA/ATR, simulateur et coûts ; aucune optimisation. Trois fenêtres d'évaluation après 50 % d'amorçage, exclusion des positions traversant la fin d'un fold. Données déjà exposées ; aucune validation statistique possible. Comparaisons cash/buy-hold descriptives et drawdown sur capital réalisé explicitement limité.
4. `scripts/terminal/build.py` : construire un JSON strict et déterministe, séries réelles, diagnostic de provenance, résultats existants et nouvelles simulations. Un import MCP ou collecte publique Kraken explicite permet une reconstruction. Empreintes des sources et du code. Aucun compte ni secret.
5. Interface sombre responsive : Marché / Laboratoire / Risque / Données ; chart 15m/1h/4h/1j avec volume et EMA/SMA, RSI/MACD ; facteurs, études filtrables, exports, personnalisation locale. Cours public ponctuel séparé du snapshot analytique, aucune fausse fraîcheur.
6. Tests Python + JS et contrôle navigateur bureau/mobile. CI finie, lecture seule, 10 min maximum, déclenchement sur cette branche, aucun cron. Commit/push branche uniquement. Livraison + passation.

## Risques de revue
- Horloge navigateur invalide ou snapshot périmé : décision fail-closed, prix historique reste étiqueté.
- Une bougie invalide finale ne doit pas révéler un signal antérieur comme actuel.
- Aucune série indicateur ne traverse un trou ; pas de remplissage artificiel.
- Cible de variante 2R clairement expérimentale, aucun changement de stratégie primaire.
- Valeurs NaN/inf, fichiers non fiables et champs HTML ne doivent pas devenir chiffres/scripting.

## Limites prévues
Pas de portefeuille exécutant des ordres. Calculateur et simulations historiques seulement. Pas de macro automatique, carnet historique, probabilité calibrée, multi-exchange ou alertes serveur persistantes. Publication publique soumise à autorisation.
