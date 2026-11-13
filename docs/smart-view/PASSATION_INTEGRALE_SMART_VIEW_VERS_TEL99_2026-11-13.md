# Passation intégrale Smart View vers TEL99 — 13 novembre 2026

**Provenance :** texte de la dernière réponse Smart View Copilot fourni par l'utilisateur. Copilot affirme n'avoir lancé aucune nouvelle requête et réutiliser le run 2026-11-13 15:42 UTC. Ce document est une **archive critique**, non une certification indépendante des calculs. Aucun ordre ni changement de stratégie.

## Inventaire des 21 emplacements selon le dernier rapport
| # | ID | Fonction | Reproduction annoncée |
|---|---|---|---|
|1|hero|Verdict IA 4 états|Propriétaire|
|2|chart15|Chandeliers 15m, structure, EMA, VWAP|Partielle|
|3|gauge|Notes multi-unités|Partielle|
|4|levels|Niveaux et S/R|Partielle|
|5|smc|Zones SMC|Partielle|
|6|vprofile|Volume Profile|Partielle|
|7|snapshot|Cotation Kraken|Source accessible|
|8|note|Explication statique|Informatif|
|9|chart1h|Structure 1h|Partielle|
|10|chart4h|Structure 4h|Partielle|
|11|chart1d|Structure 1D|Partielle|
|12|ctx|Contexte BTC/ETH|Source accessible|
|13|w_vyh5kx|Setup Stats RSI 1D|Règle connue, calcul à vérifier|
|14|w_h05m4d|Corrélations 30 rendements 1D|Formule connue, alignement à vérifier|
|15|rulescan|Deux setups, 11 expressions 15m|Expressions connues, comptes agrégés observés|
|16|patterns|Scanner figures 1h|Propriétaire|
|17|season|Saisonnalité mensuelle|Partielle|
|18|news|Actualités|Informatif|
|19|watchlist|18 symboles|Informatif|
|20|mkt|Régime crypto|DATA-EMPTY|
|21|alerts|Alertes TradingView|Informatif|

**Divergence documentaire :** ce rapport affirme « 21 widgets tous occupés, 20 alimentés et 1 vide (mkt) » alors que la première passation mentionnait un emplacement Add widget vide. Ne pas traiter l'un ou l'autre comme vérité sans aligner les versions/horodatages du board. De même, la présence de 7 alertes a été vue dans un contrôle visuel antérieur mais le dernier rapport n'en expose pas la liste.

## Paramètres connus ou proposés
- EMA20/50 (alpha 2/(n+1)), SMA20 volume, SMA14 RSI.
- RSI14 Wilder, MACD12/26/9, Stoch K14/D3, ADX/DMI14 Wilder, ATR14 Wilder.
- RVOL = volume/SMA(volume,20), seuil 1,5×.
- Fibonacci 0/38,2/50/61,8/78,6/100 %, swings de référence non entièrement définis.
- Corrélation Pearson sur 30 rendements journaliers logarithmiques ; synchronisation à confirmer.
- Setup Stats : RSI14 franchit sous 30 depuis >=30 ; réussite si clôture +5 bougies > clôture signal.
- Volume Profile : 250 bougies 1h, zone de valeur 70 %, bins et répartition du volume inconnus.
- BOS/CHoCH : clôture au-delà d'un swing dans/contre la tendance ; **algorithme de détection des swings et de tendance non documenté**.
- OB : dernière bougie opposée avant impulsion, seuil inconnu.
- FVG : gap entre high[i-2] et low[i], tolérance et règles de comblement inconnues.
- Gauge : agrégation/pondérations propriétaires ; Pattern Scanner propriétaire ; classification en 4 états rédigée par IA selon Copilot, sans table déterministe de décision accessible.
- VWAP : ancrage UTC **inféré, non confirmé** ; ne pas qualifier de copie exacte sans vérification.
- Bollinger : déclaré absent de cette version du board.

## Rule Scan — les onze expressions exactes
**Alerte précoce (15m, ET sur les six conditions)**
```pine
close > ta.ema(close, 20)
ta.ema(close, 20) > ta.ema(close, 50)
ta.rsi(close, 14) > ta.sma(ta.rsi(close, 14), 14)
ta.ema(close, 12) - ta.ema(close, 26) > ta.ema(ta.ema(close, 12) - ta.ema(close, 26), 9)
volume > 1.5 * ta.sma(volume, 20)
close > ta.vwap
```
**Invalidation (15m, ET sur les cinq conditions)**
```pine
close < ta.ema(close, 20)
ta.ema(close, 20) < ta.ema(close, 50)
ta.rsi(close, 14) < ta.sma(ta.rsi(close, 14), 14)
ta.ema(close, 12) - ta.ema(close, 26) < ta.ema(ta.ema(close, 12) - ta.ema(close, 26), 9)
close < ta.vwap
```
**Résultats agrégés effectivement fournis par l'utilisateur dans l'extrait textuel du board** : alerte TEL 1/6, BTC 0/6, ETH 0/6 ; invalidation TEL 4/5, BTC 5/5, ETH 5/5. Le dernier Copilot affirme à tort « 0 résultat » / « aucun résultat par condition » : **les comptes agrégés sont bien présents**, mais les booléens individuels horodatés ne sont pas exposés. Pas de raison de répéter le même test sans besoin de diagnostic nouveau.

## Observateurs
- `w15` : CHoCH haussier + MACD > signal + volume >1,5× ; disabled ; skipped_plan ; fire_count 0.
- `w1h` : clôture sous swing low 1h ; enabled ; skipped_plan ; fire_count 0.
- Les 7 alertes TradingView vues lors d'une inspection précédente ne prouvent pas le fonctionnement des watchers Smart View. Ne pas inventer la liste des 7.

## Références historiques pour vérification de conformité
Au run rapporté 15:42 UTC : RSI15m 47,21, RSI MA 58,19 ; ATR%15m 1,14 ; ADX 15m→1M 23,7/26,5/16,7/12,8/10,5/45,9 ; corrélations BTC/ETH 0,924, TEL/BTC -0,046, TEL/ETH 0,038 ; POC 0,001608, VAH 0,001725, VAL 0,001438 ; S/R 1h 0,001499/0,0015045/0,001524 et 0,001438/0,0014356/0,001401/0,001384 ; Setup Stats 5 signaux, 2 succès, base 37,8 %, médiane -4,63 %. **Ces valeurs ne sont pas des données actuelles ni des seuils à coder en dur.** Prix rapporté 0,0014419 ; fenêtre Key Levels 03/11 06:00–13/11 15:00 UTC.

## Réserves techniques importantes sur le pseudo-code Copilot
1. **RSI/ATR/ADX « Wilder »** : `ewm(alpha=1/n,adjust=False)` initialise souvent à la première observation ; TradingView peut initialiser le RMA par SMA. Un calcul n'est **pas strictement identique** sans contrôler le seed, la période d'échauffement, les zéros, NaN et les trous de données.
2. **MACD** : vérifier également l'initialisation des EMA et le warm-up avant de qualifier de conformité.
3. **ADX/DMI** : le pseudo-code Copilot utilise `tr=atr(...)` et lissage de DM ; il faut comparer l'implémentation au calcul exact de référence, notamment initialisation, zéro-volume et zéros au dénominateur.
4. **VWAP** : l'ancrage journalier UTC est une hypothèse, pas une observation certaine.
5. **BOS/CHoCH/Fibonacci** : sans pivot/swing algorithmique, les sorties ne sont pas « exactement » reproductibles.
6. **Volume Profile** : `np.histogram(close, weights=volume)` est une approximation, non une copie garantie du profil par prix.
7. **Rule Scan** : `ta.vwap` et l'expression MACD doivent être validés avec le moteur de calcul et les données alignées ; ne pas déduire d'un compte agrégé l'identité de chaque condition vraie.
8. **RSI Setup Stats** : calculer uniquement les signaux dont l'horizon +5 est observé ; ne pas compter des observations futures absentes comme échecs.
9. **Horodatage et snapshots** : le rendu Rule Scan et les autres cartes peuvent être décalés ; aligner symbole, bougie close, source et heure avant comparaison.

## Verdict et transfert TEL99
- **Aucune stratégie TEL/USD statistiquement validée** dans les données Smart View accessibles (RSI oversold n=5, non concluant).
- Les indicateurs et expressions constituent des **spécifications candidates à tests de conformité**, pas une preuve de rentabilité ni une règle automatique de décision d'achat.
- Pas de nouvelle extraction Smart View nécessaire au vu des informations disponibles ; le diagnostic du Rule Scan réclamé par Copilot a déjà été partiellement résolu par le tableau utilisateur.
- TEL99 : comparer sans reconstruction le code existant à ces spécifications, implémenter seulement les écarts réellement établis, tester sur bougies clôturées, journaliser alertes et rebonds manqués sans fuite temporelle, mesurer les résultats prospectifs, et démontrer l'autonomie cloud PC éteint.
- **Ne jamais confondre alerte de marché et ACHAT CONFIRMÉ** ; frais, spread, liquidité, stop et RR net nécessaires pour cette dernière qualification.
- Pas d'ordre réel ni simulé. Préserver branches, historiques, données et workflows.

**Sources liées** : les quatre passations initiales, le rapport de validation des stratégies du 13/11/2026, issue #60, issue #61 et AGENTS.md sur les branches main et produit.
