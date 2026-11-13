# Validation scientifique des stratégies TEL/USD — Smart View — 13 novembre 2026

> **Provenance :** réponse Smart View Copilot transmise par l'utilisateur, avec extrait textuel du tableau de bord. Copilot indique n'avoir exécuté **aucun nouveau backtest ni aucune nouvelle requête** ; ses statistiques proviennent du rendu historique du 13/11/2026 15:42 UTC. Un extrait supplémentaire du board contient des données ultérieures, notamment une analyse à 16:10 UTC et un tableau Rule Scan, qui **ne doivent pas être confondus avec le run 15:42**. Aucune vérification indépendante de la performance des signaux n'a été exécutée. Archive documentaire seulement ; aucun ordre réel ou simulé.

## Verdict central
**AUCUNE STRATÉGIE TEL/USD STATISTIQUEMENT VALIDÉE DANS LES DONNÉES ACCESSIBLES.**

La seule famille avec une statistique de performance est le RSI(14) passant sous 30 en 1D, mesuré par Setup Stats. Toutes les autres familles ont des indicateurs ou états, mais pas de statistiques de performance exploitables dans Smart View. « Non testable dans Smart View » ne signifie **pas** « impossible à tester indépendamment dans TEL99 ».

## Seule configuration mesurée
| Champ | Observation rapportée |
|---|---|
| Source | Setup Stats, KRAKEN:TELUSD 1D |
| Définition | RSI(14) clôture <30 après une clôture >=30 ; succès si close +5 barres > close signal |
| Fenêtre | 22/01/2026–13/11/2026 ; 296 bougies 1D |
| Signaux | 5 |
| Succès | 2/5 = 40 % |
| IC95 rapporté | 11,8 %–76,9 % ; méthode de calcul non confirmée |
| Taux de base | 37,8 % |
| Médiane rendement +5 bougies | -4,63 % |
| Drapeaux | `low_sample:true`, `refused:true` |

**Interprétation :** résultat NON CONCLUANT, ni validé ni rejeté. L'intervalle contient le taux de base ; aucune supériorité démontrée. La médiane négative ne suffit pas à prouver une inefficacité avec n=5. L'assertion « n'apporte aucune information » serait trop forte : **aucune information prédictive supplémentaire n'a été démontrée**.

## Statut des neuf familles
| Famille | Résultats de performance accessibles | Statut |
|---|---|---|
| A. RSI survendu/sortie de survente | RSI<30 : n=5 seulement ; sortie non testée séparément | NON CONCLUANTE pour RSI<30 ; sortie NON TESTABLE |
| B. RSI croise au-dessus SMA(RSI14,14) | aucun | NON TESTABLE dans Smart View |
| C. MACD haussier | aucun | NON TESTABLE |
| D. Reprise EMA20/50 | aucun | NON TESTABLE |
| E. Volume relatif | aucun | NON TESTABLE |
| F. CHoCH/BOS | aucun | NON TESTABLE |
| G. Support/VAL/POC/OB | aucun | NON TESTABLE |
| H. Conditions Rule Scan combinées | booléens de conditions, **pas de statistiques de résultats futurs** | NON TESTABLE comme stratégie |
| I. Figures Pattern Scanner | 0 détection dans rendu, pas de résultats futurs | NON TESTABLE |

Aucune méthode classée VALIDÉE, PROMETTEUSE sur preuves positives, ou REJETÉE par un test suffisant.

## CORRECTION DOCUMENTAIRE IMPORTANTE — Rule Scan
L'extrait textuel **directement fourni par l'utilisateur** après la passation inclut le tableau visuel détaillé (barre clôturée) :

| Symbole | Alerte précoce (6 règles) | Invalidation (5 règles) |
|---|---:|---:|
| TELUSD | **1/6** | **4/5** |
| BTCUSD | **0/6** | **5/5** |
| ETHUSD | **0/6** | **5/5** |

Totaux : **0 correspondance complète** alerte précoce ; **2 correspondances complètes** invalidation (BTC/ETH).

Cela **résout la contradiction de lecture** du rapport navigateur antérieur (« TEL 1/6 » vs « 2 verts »). Ces comptes sont visibles dans l'extrait utilisateur ; les **valeurs numériques des 11 conditions et les booléens individuels ne sont toujours pas exportés**, et l'heure exacte de chaque évaluation n'est pas explicitement fournie. Ne pas transformer ces comptes en benchmark sans aligner exactement les barres.

L'extrait ultérieur indique TEL/USD ~0.001450, analyse narrative à 16:10 UTC, cotation Kraken à 16:09:50 UTC, dernière bougie 15m clôturée à 16:00 UTC (close 0.001449), tandis que la ligne Rule Scan indique TEL close 0.001451. **Ces valeurs ne sont pas parfaitement identiques : vérifier le timestamp et la provenance de chaque composant avant comparaison.** Les niveaux sont historiques, pas des ordres ni des seuils permanents.

Autres valeurs du tableau ultérieur : SMC FVG baissier 0.001453–0.001468 ; OB haussier 0.001310–0.001329 ; POC 0.001608, VAH 0.001725, VAL 0.001438. Données de marché anciennes au moment de toute utilisation future.

## Lacunes
Aucun export des cinq événements individuels RSI, ni résultats futurs +1h/+4h/+24h/+7j, MAE/MFE, frais, spread, carnet, faux positifs, faux négatifs, délais, rendement moyen, tests hors échantillon ou backtest intégré accessible. Le Rule Scan **fonctionne visuellement** et remonte des comptes par symbole, mais ne valide aucune stratégie.

## Hypothèses à tester indépendamment dans TEL99
A. RSI(14) sortie de survente ; B. RSI croise SMA(RSI,14) ; C. MACD12/26/9 croise signal ; D. reprise EMA20/50 ; E. RVOL >1.5 ; F. CHoCH haussier confirmé ; G. rebond sur zones définies ex ante ; H. combinaison F+E+B. Ne pas coder de nouvelles stratégies comme règles de production avant validation.

### Proposition Smart View de définition des rebonds — NON VALIDÉE
`close[i] > close[i-1]` ET `(max(high[i..i+12]) - close[i])/close[i] >= 2*ATR14[i]`, épisodes sans chevauchement sur 12 barres.

**Attention scientifique :** cette définition utilise des barres **futures** pour attribuer a posteriori une étiquette de rebond. C'est acceptable **uniquement pour évaluer des événements après expiration de la fenêtre**, pas pour produire une alerte en temps réel ni pour définir rétrospectivement une entrée réalisable. Ne jamais présenter le sommet futur comme connu à la barre i. Le début du rebond, la fenêtre et l'unité de temps doivent être fixés avant le test ; définir un protocole d'épisodes non chevauchants, contrôler les censures en fin de série. « 3 ans de données 1h » est une **demande d'historique**, pas une disponibilité établie (l'historique Kraken TEL/USD observé est plus court).

### Évaluation requise
- Mesurer séparément détection précoce (rappel, précision, faux positifs, faux négatifs, délai) et décision d'achat (RR net, spread, frais, profondeur, risque).
- Comparer à un taux de base calculé sur la **même unité d'observation** (épisodes vs barres) ; attention aux dépendances temporelles et aux horizons chevauchants.
- Chronologie stricte, bougies clôturées, pas de lookahead ; résultats prospectifs +1h/+4h/+24h/+7j.
- Tests multiples et surajustement ; partitions dev/validation/hors-échantillon si historique et nombre d'événements suffisants. Le seuil « >=300 rebonds » du rapport Smart View est une proposition arbitraire, **pas une règle scientifique universelle**.
- Mesurer spread/frais/slippage pour performance nette ; si indisponibles, ne jamais déclarer ACHAT CONFIRMÉ.
- Conserver chaque alerte de marché même si les critères de risque refusent l'achat.

## Conclusions et limites
Smart View ne démontre **aucune stratégie gagnante**. Il fournit les formules/états de marché utiles à une implémentation indépendante, mais pas les résultats nécessaires à une validation quantitative. Ne pas confondre score technique, règle visuelle, alerte, backtest et rentabilité. Pas d'autre extraction Smart View indispensable pour continuer TEL99. Les quatre passations précédentes restent archivées sans modification. Lire aussi issue #60, issue #61 et AGENTS.md.
