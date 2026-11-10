# PASSATION OBLIGATOIRE — TEL99 Quant Intelligence Terminal

Mise à jour : 2026-11-10. Ce document est la référence de continuité pour tout nouvel agent (Astra, ChatGPT, Claude ou autre). **Lire ce fichier, `docs/terminal/DELIVERY.md` et le code actuel AVANT de modifier quoi que ce soit.** Ne jamais supposer qu'une fonctionnalité est absente sans la rechercher.

## Périmètre, branches et non-interférence

Dépôt : `khalidd692/telcoin-trading-intelligence99`. Branche terminal : `codex/tel99-quant-terminal`. `main` a une surveillance MEXC/KuCoin distincte, existante, avec `.github/workflows/monitor.yml`, `src/monitor.py`, `src/agent_analysis.py`, `src/alert_state.py` et publications `site/report.json`, `site/agent_analysis.json`. **Ne pas la reconstruire** et ne pas mélanger automatiquement MEXC/KuCoin TEL/USDT avec Kraken TEL/USD.

Astra travaille également sur le terminal : avant tout changement, vérifier l'état du dépôt et les commits récents, identifier le propriétaire fonctionnel du code, et préférer une intervention minimale. Ne pas écraser ses modifications ni prétendre s'être coordonné avec elle sans preuve. La branche terminal diverge de `main` : aucune fusion implicite.

## Éléments préexistants : ne pas refaire

- `scripts/terminal/collect.py` : collecteur public Kraken OHLC, TEL 15m/1h/4h/1D et BTC/ETH 4h. Limite API récente, bougie finale potentiellement en formation.
- `scripts/terminal/build.py` : analyse multifactorielle depuis captures, avec historique de recherche épinglé ; `src/terminal/model.py` pour qualité/indicateurs/décision.
- `site/terminal/index.html`, `app.js`, `core.js`, `data.json` : terminal statique, onglets Marché/Laboratoire/Risque/Données. `data.json` est chargé à l'ouverture ; le ticker public est distinct du snapshot analytique.
- `scripts/terminal/research.py`, `results/terminal/experiments.json`, `results/strategy_validation/results.json` : résultats expérimentaux et stratégie primaire figée. **Aucune rentabilité robuste démontrée**. Backtest primaire : 53 candidats, zéro trade admissible, RR maximum 0,8011. Ne pas modifier les règles ou réécrire les résultats.
- `.github/workflows/tel99-terminal.yml` : tests et packaging du terminal ; aucun déploiement.

## Changements effectués par ChatGPT le 10 novembre 2026

1. Commit `c41508310db6e2f5f1b5464e4c03dc3fe5b5369b` : sécurité du ticker (`freshQuote` 120s, `parseTelTicker` paire exacte) et tests JS. CI #7 réussie.
2. Commit `c8a8ce277e909fa75b88968321520eae17ac008a` : audit indépendant, documentation seulement.
3. Commit `0fa1d09514caeab102a067bf322c70118ee5d19e` : `site/terminal/app.js` récupère automatiquement le **ticker public Kraken TEL/USD** à l'ouverture puis toutes les 60s si la page est visible, évite les requêtes simultanées et invalide la cotation en cas d'échec. **N'actualise pas les indicateurs.** CI #8 réussie.
4. Commit `b4626f8882ff529bfda48123a0dcb100752bea3e` : nouveau workflow `.github/workflows/tel99-kraken-snapshot.yml`, **déclenchement manuel uniquement**, collecte Kraken, reconstruction en /tmp, vérification des invariants, artifact ; permissions GitHub `contents: read`, aucun push/déploiement/ordre.
5. Commit `83cd700782e29c87b2182dc2c273251f6d01f325` : option `--no-study-write` dans `scripts/terminal/build.py` pour empêcher l'écriture de `results/terminal/experiments.json` pendant une actualisation de marché.
6. Commit `fc24d6e8243177457f45bf4ea5a50bad6c8df1a3` : workflow Kraken utilise `--no-study-write`.
7. Commit `aabf278412f4a6fd1c77d5a758a31975b41829df` : test de non-régression de l'absence de réécriture des expériences.
8. Commit `4d2f5e9bd83405019e601f8261bcb5b68378224c` : correction du test CI de déterminisme, qui compare maintenant deux constructions à paramètres identiques en /tmp, sans comparer à tort un fichier historiquement construit avec une autre version du code.

## Preuves vérifiées / limites explicites

- Workflow `tel99-terminal.yml` : CI #7, #8 et **#11 réussies** (dernier état consulté le 10/11/2026) ; #9 et #10 ont échoué à l'étape « Deterministic terminal build » avant la correction #11. L'échec ne doit pas être caché, ni présenté comme persistant après correction sans re-vérification.
- L'API publique Kraken a répondu sans erreur pour six endpoints : TEL/USD 15m/1h/4h (721 lignes chacun), TEL/USD 1D (293 lignes), XBT/USD 4h (721), ETH/USD 4h (721). Cela prouve la disponibilité de l'API au moment du contrôle, **pas** l'exécution du workflow complet.
- Le workflow `tel99-kraken-snapshot.yml` n'a **pas** encore de run réel confirmé. Aucun artifact de capture récente confirmé. Le nouveau snapshot analytique n'est pas encore relié à un rafraîchissement automatique du navigateur. **Ne pas annoncer le terminal analytique temps réel comme terminé.**
- GitHub Actions planifié sur une branche non-default ne s'exécute pas automatiquement. Ne pas déplacer le workflow vers `main` sans autorisation.
- Les snapshots portent leurs horodatages : une donnée jadis valide peut être périmée. Jamais d'invention de cours ou de signal.

## Prochaines tâches, dans cet ordre

1. Vérifier la branche HEAD et les modifications récentes d'Astra ; éviter tout conflit et réévaluer ce qui est déjà livré.
2. Exécuter et examiner un run **manuel** de `tel99-kraken-snapshot.yml` si l'accès Actions write est disponible ; vérifier artifact, qualité, invariants et absence de mutation des résultats historiques. Sinon documenter exactement la limite, sans simuler un succès.
3. Après preuve d'exécution, définir une publication sûre et autorisée du snapshot récent, puis un rafraîchissement navigateur de `data.json` avec contrôles d'intégrité, provenance et fraîcheur, sans altérer l'historique figé.
4. Tests end-to-end et non-régression ; distinguer disponibilité des données, CI, fonctionnement navigateur et validation scientifique des stratégies.

## Règles non négociables

Référence `KRAKEN:TELUSD` spot, levier 1x, capital virtuel $1 000, risque max 0,25 % par trade, RR requis >1,5. Lecture seule. **Aucun ordre réel, aucun paper order, aucune connexion au compte Kraken réel.** Aucun push vers `main`, merge, déploiement, modification des stratégies ou publication sans autorisation. Fail closed si données manquantes/périmées/incohérentes. Ne pas confondre hypothèse, backtest incomplet et avantage validé. Ne pas réintroduire Cline, Nemotron, Cursor ou une ancienne architecture.

## Liens de continuité

- Branche : https://github.com/khalidd692/telcoin-trading-intelligence99/tree/codex/tel99-quant-terminal
- CI : https://github.com/khalidd692/telcoin-trading-intelligence99/actions/workflows/tel99-terminal.yml
- Workflow de capture : `.github/workflows/tel99-kraken-snapshot.yml`
- Audit indépendant : `docs/terminal/AUDIT_INDEPENDANT_2026-11-10.md`

**Instruction au prochain agent : reprendre les tâches non validées, ne pas recommencer les composants existants. Vérifier chaque affirmation dans le dépôt et les runs GitHub.**

## Complément de passation — rafraîchissement analytique navigateur (10/11/2026)

- `be6e88cab8453f91ba4772f70ed12b733be38172` : `site/terminal/core.js` ajoute `acceptSnapshot(current,next,now)`. Refuse une capture non récente, future hors tolérance, un autre marché/source, des séries absentes, toute modification de `lab`, de la provenance historique ou des garde-fous.
- `65c41a4593179602b312a2dc10180597a39885ea` : `site/terminal/app.js` interroge `data.json` toutes les 60 secondes si page visible ; remplace les graphiques, indicateurs, décision et preuves **uniquement si** le nouveau snapshot passe les contrôles. Les valeurs saisies dans le simulateur de risque ne sont pas réinitialisées.
- `f74fe2ed08bd1e81d1e07422a0f411994c205850` puis `cc04b197545620055c78ee6dfba8355cbb11e23d` : huit assertions de sécurité supplémentaires dans `tests/test_terminal.js` (33 annoncées), avec correction de l'horodatage de test futur.
- CI #15 sur `cc04b19` était **en cours** lors de la rédaction : vérifier son statut et ses logs avant d'affirmer la réussite.
- **Bloquant restant** : `site/terminal/data.json` n'est PAS encore alimenté par le workflow Kraken en continu. `tel99-kraken-snapshot.yml` produit seulement un artifact manuel en /tmp, sans publication sur un serveur. Ne pas annoncer l'actualisation analytique complète. Aucun déploiement ou merge autorisé.
- **Limite scientifique** : le rechargement des données et la complétude de l'analyse ne prouvent pas un avantage prédictif ni une rentabilité. Les stratégies restent non validées.

## Tentative de validation réelle de la collecte (10/11/2026)

- Une automatisation navigateur a tenté d'ouvrir et de déclencher `.github/workflows/tel99-kraken-snapshot.yml`. **Non déclenché** : navigateur non authentifié GitHub, workflow absent de la branche par défaut `main` (présent uniquement sur la branche de travail). Aucune exécution ni artifact confirmé.
- Le navigateur a prétendu que le fichier contenait seulement un déclencheur `schedule` ; **c'est inexact** : lecture directe du dépôt prouve `workflow_dispatch` et pas de `schedule`. Ne pas reprendre cette erreur.
- Ne pas annoncer une publication analytique ou un flux end-to-end validé. La tâche de reprise automatique programmée n'est pas une preuve de résultat.

## Intégration Kraken réelle ajoutée (10/11/2026)

- Commit `567dbf82437f17cffbb6772e0a7860c6e0b70521` : `.github/workflows/tel99-terminal.yml` possède désormais un second job `live-kraken-integration` déclenché automatiquement lors d'un push sur la branche terminal. Il appelle réellement le collecteur Kraken public pour six flux, reconstruit le snapshot en /tmp avec `--no-study-write`, vérifie schéma, source, fraîcheur, séries TEL, BTC/ETH, laboratoire figé et absence de mutation, puis téléverse un artifact privé temporaire. Aucun compte, ordre ou déploiement.
- **CI #16 pour le commit `567dbf8` : GitHub Actions indique « completed successfully »** (10 novembre 2026). C'est une preuve d'exécution réussie du workflow à deux jobs, plus forte qu'une simple disponibilité d'API. Pour un audit approfondi, récupérer le détail des jobs et artifact avant de publier un snapshot.
- **Toujours non fait :** alimenter le site public avec un snapshot périodique et prouver que le navigateur reçoit effectivement les nouveaux fichiers. Le job actuel ne publie pas ; ne pas confondre intégration en CI et déploiement.

## Aperçu autonome avec données réelles (10/11/2026)

- Audit approfondi du run #16 : les jobs `verify` et `live-kraken-integration` ont tous deux réussi. Logs de collecte : 721 bougies retournées pour TEL 15m/1h/4h, BTC/ETH 4h, 293 pour TEL 1D ; 720 bougies 15m et 1h validées, sans trous, `fresh=true`. La décision calculée à 20:19 UTC était `ATTENDRE`. Artifact réel `TEL99-live-kraken-567dbf8...` ID 13798529377, téléversé avec succès. Run : https://github.com/khalidd692/telcoin-trading-intelligence99/actions/runs/42894062177
- Commit `433d6947fa0e179a8958249bc0f94557236b6cd2` : le job d'intégration prépare maintenant un ZIP **isolé** `TEL99-live-preview.zip` avec l'interface statique et le snapshot Kraken validé du run. Aucun déploiement, aucune mutation de `main` ; aperçu daté (pas un flux continu). Artifact `TEL99-live-preview-433d694...` ID 13800481355, run #17 https://github.com/khalidd692/telcoin-trading-intelligence99/actions/runs/42894392710 ; le job live était **réussi** à la vérification, le workflow complet encore en cours.
- Restent à traiter : déploiement et alimentation périodique d'un snapshot sur le site (sans casser le moniteur historique MEXC/KuCoin) ; vérification navigateur sur site effectivement publié ; étude de performance hors échantillon. Le ZIP ne prouve pas une publication web.

## Vérification HTTP de l'aperçu (10/11/2026, run automatisé)

- Le run #17 `42894392710` a terminé avec succès dans ses **deux jobs** (`verify`, `live-kraken-integration`). Trois artifacts confirmés : ZIP terminal, snapshot Kraken et ZIP aperçu Kraken. Pas de déploiement.
- Commit `fae17ad710104c27de63f67e8fd5ba71c864179d` : ajout d'un test HTTP dans le job live. Il sert `site/terminal/` sur 127.0.0.1:8765, récupère `index.html`, `data.json`, `app.js`, `core.js`, `terminal.css`, et vérifie que le JSON HTTP est identique au snapshot Kraken validé. Ce test vérifie la livraison des fichiers via HTTP **mais ne simule pas un vrai navigateur ni la mise à jour après 60 secondes**.
- Run #18 https://github.com/khalidd692/telcoin-trading-intelligence99/actions/runs/42894853081 : le job `live-kraken-integration` est **success** lors de la dernière interrogation ; le job `verify` était encore en cours. Vérifier la conclusion finale avant toute affirmation globale.
- Non validé : déploiement public, actualisation périodique de `site/terminal/data.json` et vérification en navigateur réel. Ne pas annoncer « end-to-end en production ».
