# RAPPORT DE VÉRIFICATION OPÉRATIONNELLE — Telcoin Trading Intelligence

Date : 21 octobre 2026 · Périmètre : vérification du système en exploitation,
correction des défauts reproductibles, préparation de la fin de mission.

> **Statut inchangé : « règle de recherche — observation qualifiée ».**
> L'espérance nette est positive et reproductible hors échantillon, mais
> **l'intervalle de confiance inclut zéro** et **les frais réels ne sont pas
> confirmés**. Ce n'est pas une preuve de rentabilité. Aucun ordre n'a été passé.

---

## 1. Faits vérifiés (observation directe)

| Sujet | Constat |
|---|---|
| `main` | porte le moteur v2, le suivi d'alertes, la porte de publication et la cadence auto-limitée (8 commits de fusion : PR #31 à #38) |
| Moteur `src/agent_analysis.py` | **inchangé** — empreinte `ca7f46ee2b7e1a06122eaf584ce18db1450fc6b766a8ec843a69ee5b08f0a600` |
| Collecte en CI | **MEXC `VÉRIFIÉ`** (âge 0,8 s) et **KuCoin `VÉRIFIÉ`** (0,4 s) ; `confirmation indépendante : OUI` ; divergence 3,3 bps |
| Six unités de temps | `15m` OK (300 bougies, âge 547 s), `1h`/`4h` OK, `1d` OK, `1w` OK (100 bougies), `1M` PARTIEL (23 bougies) — **0 doublon, 0 trou, 0 bougie à volume nul** |
| Fraîcheur publiée | instantané 0,4 min, rapport 0,7 min, analyse 0,4 min au moment du contrôle |
| Provenance | même `collection_id` sur les 3 artefacts ; `snapshot_id` = empreinte déterministe ; porte de publication acceptante |
| Signal TEL/USDT courant | `ATTENDRE`, `direction INDETERMINE`, `confidence 0`, raison « Aucun setup de retournement structurel detecte », **régime NEUTRE (−1,85 % sur 30 j)**, `exploitable = false` |
| Alertes | `evaluations` progresse de **+1 à chacune des 11 publications** (preuve de persistance et de reprise sur runner neuf) ; 0 fausse alerte ; 0 résolution |
| Journal prospectif | 11 lignes réelles, **toutes `period_type = live`**, 0 doublon, **0 rendement 24 h renseigné** (aucune échéance atteinte) |
| Tableau de bord déployé | HTTP 200 ; **code déployé = fichier du dépôt à l'octet** ; rend les **4 états** (badge vert **uniquement** pour `CONFIRMATION` exploitable) ; dégradation de fraîcheur → `ATTENDRE` + « PÉRIMÉ » + prix effacés, **sans requête marché** |
| Site déployé | sert l'artefact courant (6 unités de temps, `early_reversal` présent) |

## 2. Cadence : prévu ≠ observé (deux causes distinctes, corrigées)

| | Valeur |
|---|---|
| Cadence **configurée** (cron `*/15`) | 15 min |
| Cadence **observée** avant correction | **229 min** (45 exécutions planifiées sur 168 h ; intervalles 104 à 387 min ; attente de démarrage nulle ; 4 créations sur 45 alignées sur un slot) |
| Cause n°1 | bradage de l'ordonnanceur de la plateforme (le cron GitHub n'est pas une garantie de fréquence) |
| Cause n°2 (mesurée le 22/10) | **le garde-fou de cadence lisait l'âge de l'artefact que l'exécution venait de publier** (l'étape de publication commite sur la branche locale *avant* l'étape de cadence) → âge ≈ 0,2 min → « inutile » → **la chaîne s'arrêtait à chaque maillon** |
| Mesure du cron reprise le 22/10 | **44 exécutions planifiées sur 168 h** pour un `*/15` qui en attendrait 672 → **livraison 6,5 %**, intervalle **médian 252 min**, min 104 min, max 387 min ; livraisons **non alignées** sur un slot `*/15` (minutes observées : 56, 56, 04, 49, 57, 31, 27, 15…) → ce sont des exécutions **rattrapées**, livrées une par une des heures plus tard |
| Conséquence mesurée | le tableau de bord publié reposait sur des données de **27 à 290 min**, au-delà de sa fenêtre de fraîcheur (20 min analyse / 30 min rapport) → `ATTENDRE « périmé »` presque en permanence |
| Correction | **créneau** : le maillon de chaîne **attend** le prochain créneau (13 min) puis relance ; **porte de publication** (12 min) : deux publications ne peuvent pas tomber dans la même fenêtre ; **une seule chaîne** : seuls les maillons explicites (`workflow_dispatch` `mode=chain`) se relancent, une exécution ponctuelle ne relance qu'une chaîne **arrêtée** (30 min) ; **repli** : 45 min après un échec ; âge inconnu ⇒ **aucune relance** et attente d'un créneau complet |
| Cadence **re-mesurée** après correction | **13,73 min** puis **13,63 min** entre deux publications de chaîne (22:32:35 → 22:46:19 → 22:59:57), contre un étalement de **1,35 à 37,83 min** avant correction |
| Chaîne observée en production | maillon 1 `39688273028` (relance acceptée, `mode chain`) → maillon 2 `39688796167` (20 étapes vertes, publication + déploiement) → maillon 3 `39690361887` ; artefact servi : `generated_at = 2026-10-21T22:46:19`, HTTP 200 |

## 3. Défauts trouvés et corrigés

| # | Défaut | Gravité | Correctif | Preuve |
|---|---|---|---|---|
| 1 | La porte de provenance exigeait `collection_status`, que le collecteur n'écrivait jamais | **publication impossible** | porte extraite dans `src/publication_gate.py` (partagée workflow/tests), collecteur corrigé, instantané de repli marqué `FALLBACK` | 16 tests de porte + compatibilité réelle collecteur ↔ porte |
| 2 | Un test passait **à vide** (copie du script, échec sur l'import) | non-régression déguisée | le test exerce la vraie porte et exige que le refus vienne d'elle | 14 tests de provenance |
| 3 | Runner CI : HEAD détaché, `pytest` absent | CI rouge | contrôles compatibles CI (`--quick`, repli `unittest`, HEAD détaché accepté) | CI verte sur 8 PR |
| 4 | `GITHUB_WORKFLOW` = nom d'affichage → URL de dispatch invalide, exception non attrapée | run rouge | nom de fichier, capture large, filet de sécurité global | dispatch réel vérifié (run vert) |
| 5 | Checkout de profondeur 1 ⇒ âge inconnu ⇒ **boucle de publications (~50 s)** | débordement | âge lu dans l'artefact publié au commit de checkout ; âge inconnu ⇒ aucune relance | 22 tests de cadence, boucle arrêtée |
| 6 | Un rapport dégradé portant un signal résiduel pouvait ouvrir une alerte | fail-closed incomplet | `advance()` ignore tout signal si les données ne sont pas exploitables | 3 tests de régression |
| 7 | `period_type` par défaut `historical` sur des lignes réelles | corruption historique/prospective | CLI étiquetée `live` | 39 tests du module |
| 8 | `returns_24h_*` jamais renseignés | prospective non mesurable | `scripts/backtest/evaluate_prospective.py` (n'évalue que les échéances atteintes) | 12 tests + journal réel (0 renseigné) |
| 9 | **Garde-fou de cadence auto-saboté** : l'âge lu était celui de la publication que l'exécution venait de faire (0,1 à 0,7 min sur les 4 derniers runs de `main`) ⇒ chaîne arrêtée à chaque maillon | **cadence perdue** | création du **créneau** (attente puis relance), **porte de publication** (12 min), **chaîne unique** (`mode=chain`), **repli** (45 min) | PR #39 et #40 fusionnées ; 49 tests de cadence dont une **simulation du runner** (24 tours, intervalles 12-16 min) |
| 10 | La relance d'une chaîne morte testait la **vive** de la chaîne sur la publication **que l'exécution venait de faire** ⇒ une chaîne morte ne pouvait jamais être relancée | chaîne non récupérable | l'état de la chaîne se mesure **au commit de checkout** (`CHECKOUT_SHA`), le créneau continue d'utiliser la dernière publication | PR #40 ; test de régression dédié ; run réel `39687968845` : « chaine vue au demarrage 6.9 min → aucune relance » |


## 4. Tests exécutés

| Suite | Résultat |
|---|---|
| `pytest tests/ collector/` | **274 passés, 3 skipped, 13 subtests** |
| `scripts/verify_project.py` | **36/36** |
| `scripts/verify_states.py` | **40/40** |
| `scripts/verify_t37_e2e.py` | **20/20** |
| `node tests/test_dashboard.js` | **OK** (fraîcheur, panneau, `INVALIDATION`) |
| `node tests/test_realtime.js` | **OK** (fail-closed) |
| Rendu des 4 états par le **code déployé** | conforme |
| Dégradation de fraîcheur du **code déployé** | conforme (`ATTENDRE`, « PÉRIMÉ », aucune requête marché) |
| `validate_correction.py` | reproduction exacte, écart 0,00029 pt |
| CI GitHub | **verte** sur chacune des 8 PR fusionnées |

## 5. Performances — historique vs prospectif

| Nature | Élément | Valeur |
|---|---|---|
| Historique (OOS-1.2 figé) | espérance nette exploitable | +0,11 / +1,34 / +1,23 / +0,22 % |
| | pool indépendant NEW+IS2 | **+0,98 %, IC95 [−0,03 ; +1,96]** → inclut zéro |
| | coûts | slippage observé 0,285 %/sens ; frais **hypothèses** 0,10–0,15 % ; 4 scénarios ; coût appliqué **une fois** |
| Prospectif | **aucun résultat** | 11 observations consignées, 0 évaluable (échéance 24 h non atteinte) ; l'outil n'annonce rien |

## 6. Points non vérifiables / hors périmètre

* Le comportement du cron **au-delà de quelques heures** : la mesure porte sur 168 h
  d'historique ; le comportement de l'ordonnanceur sur plusieurs jours n'est pas
  extrapolable.
* La **rentabilité prospective** : impossible avant d'avoir accumulé 24 h de
  données réelles et des échéances de signal ; l'outil est prêt, la donnée
  n'existe pas encore.
* La **valeur prédictive de BTC/ETH** : non intégrée (hypothèses rejetées sur
  preuve) ; c'est un écart assumé, pas une mesure manquante.
* L'**identité de l'ordonnanceur GitHub** derrière le bradage du cron : le
  mécanisme est déduit de faits observables (aucune attente locale, créations
  décalées), pas d'une documentation interne.
* Les **timeouts TLS** rencontrés depuis ce poste ont interrompu certains de
  mes scripts de mesure (les fusions correspondantes, elles, ont réussi) : c'est
  une limite du poste, pas du système.

## 7. Blocages restants

1. **Décision du mainteneur** : T36 (conserver le panneau en observation qualifiée
   ou le neutraliser) et écart BTC/ETH (acté, ou réintégrer avec revalidation).
2. **Rien ne bloque l'exploitation** : le système surveille, qualifie, persiste,
   déduplique, consigne et publie en continu ; il reste en **mode observation**.
