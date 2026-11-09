# Méthode de recherche des points d'entrée TEL — décision de travail


Date de capture : 2026-11-09

## Objectif de l'investisseur

L'objectif déclaré est **les deux** :
- accumuler TEL sur plusieurs années ;
- exploiter aussi les mouvements de quelques heures à quelques semaines (swing trading).

L'horizon déclaré est également **les deux** : court et moyen terme, selon les occasions.

## Cadre non négociable

- Instrument de référence : KRAKEN:TELUSD.
- Spot uniquement, sans levier.
- Aucune connexion ni intervention sur le compte Kraken réel ; aucun ordre réel passé par l'assistant.
- Paper trading pour les tests et simulations.
- Aucun trading automatique.
- Ne pas modifier les stratégies, boards, alertes, paramètres, broker ou branche principale sans autorisation explicite.
- Ne pas confondre hypothèse, test incomplet et résultat validé.
- Utiliser des données fraîches, horodatées et des bougies clôturées pour les confirmations. Signaler les retards TradingView et les données manquantes.
- Ne pas se limiter au RSI et ne pas attendre systématiquement toutes les confirmations : distinguer alerte précoce, confirmation, invalidation et attente.

## Architecture de décision à deux moteurs

### Moteur A — Accumulation long terme
Chercher des zones de valeur sur les graphiques hebdomadaire et journalier. Entrer progressivement, garder une réserve pour les corrections et ne pas vendre automatiquement la réserve long terme sur un signal de swing.

### Moteur B — Swing trading
Chercher des replis dans une tendance haussière, des reprises après balayage de support, des cassures suivies de retests et des sorties planifiées. Chaque opération doit avoir entrée, invalidation, objectifs, coûts et rapport rendement/risque définis avant décision.

Les deux moteurs doivent avoir des enveloppes comptables et des règles de décision séparées. Les TEL déjà détenus à long terme ne sont pas assimilés au capital de swing.

## Filtre de régime de marché

Avant d'évaluer une entrée TEL, classer le contexte :
- HAUSSIER : structure ascendante, momentum positif ;
- NEUTRE : marché en range, direction incertaine ;
- BAISSIER : sommets et creux descendants ;
- STRESS : chute brutale, volatilité ou liquidité dégradée.

Examiner BTC et ETH sur 1D/1W, la force relative de TEL, la dominance BTC si disponible, la volatilité, les actualités pertinentes et la liquidité. Un signal TEL ne doit pas être évalué isolément.

## Quatre configurations d'entrée à rechercher

1. **Retournement après balayage de support** : passage sous un support puis réintégration en clôture, réaction acheteuse, volume et structure 1h qui s'améliorent.
2. **Repli dans une tendance haussière** : structure 4h/journalière ascendante, retour vers une zone de support ou EMA 20/50, pression vendeuse qui diminue, reprise en 1h.
3. **Cassure et retest** : clôture 4h au-dessus d'une résistance, participation/volume crédible, retest réussi de l'ancienne résistance.
4. **Accumulation après stabilisation** : arrêt de la succession de plus bas, support testé, volatilité qui se contracte et pression acheteuse qui progresse.

Aucune configuration n'est garantie. Une mèche isolée, un RSI bas ou une EMA brièvement reprise ne suffisent pas seuls.

## Familles d'indicateurs

- Structure : pivots, sommets/creux ascendants ou descendants.
- Tendance : EMA/SMA 10, 20, 50, 100, 200.
- Momentum : RSI 14, MACD et histogramme.
- Force : ADX/DMI.
- Volume : volume relatif, OBV.
- Volatilité : ATR 14, bandes de Bollinger.
- Prix/valeur : VWAP.
- Contexte : BTC/ETH, force relative, spread, profondeur et liquidité.
- Stochastique, CCI et Awesome Oscillator : outils secondaires, pas des votes indépendants supplémentaires.

Éviter le double comptage : RSI, Stochastique et CCI sont en partie corrélés. Ne pas fabriquer un score arbitraire sur 100 ; expliquer la convergence et les conditions éliminatoires.

## Multi-timeframes

- 1W et 1D : régime et zones de valeur pour l'accumulation.
- 4H : structure, supports, retournements et cassures.
- 1H : déclencheur et validation tactique.
- 15m : affiner l'exécution seulement, jamais décider seul d'un investissement.

## Gestion progressive proposée — à tester, pas une règle statistiquement validée

Pour une enveloppe d'accumulation nouvelle, une hypothèse de répartition a été proposée :
- 25 % après une première réaction crédible sur support ;
- 35 % après confirmation sur clôture 4h ;
- 40 % après retest réussi ou nouvelle configuration valable sur correction.

Les tranches ne sont pas automatiques. Si le support est invalidé, suspendre les achats et réévaluer ; ne pas moyenner aveuglément.

Une répartition de nouveaux capitaux 70 % accumulation / 30 % swing a également été proposée comme point de départ de discussion, non comme allocation adoptée ou obligatoire. Elle doit rester ajustable et ne s'applique pas aux TEL déjà détenus.

## Gestion du risque et coûts

- Calculer les frais Kraken réellement applicables, le spread et le glissement ; ne pas présumer du palier personnel.
- Évaluer le résultat net, pas seulement le mouvement brut.
- Pour le swing, définir entrée, invalidation, objectifs et taille avant décision ; objectif de rapport rendement/risque supérieur à 1,5 comme filtre de travail.
- Ne pas renforcer automatiquement une position perdante.
- Ne pas utiliser la réserve long terme pour renflouer le swing.

## Validation historique — ne pas confondre avec l'analyse ponctuelle

Tester sur des données historiques KRAKEN:TELUSD, sans substituer KuCoin/MEXC, avec bougies clôturées, calcul sans fuite de futur, validation chronologique/walk-forward/hors échantillon et coûts réalistes. Comparer aux références achat-conservation et accumulation périodique. Segmenter les résultats par régime de marché.

Critères de travail proposés, non encore démontrés :
- au moins 100 opérations hors échantillon ;
- espérance nette positive ;
- profit factor supérieur à 1,20 ;
- borne basse de l'intervalle de confiance de l'espérance positive ;
- frais, spread et glissement inclus.

Aucun résultat n'est validé avant vérification sur données suffisantes. Les seuils sont des critères de gouvernance proposés, pas une garantie d'avantage.

## Format obligatoire des futures analyses

Chaque rapport doit afficher :
1. horodatage, fraîcheur et qualité des données ;
2. contexte BTC/ETH et régime du marché ;
3. lecture TEL en 1W/1D/4H/1H, 15m seulement pour l'exécution ;
4. configuration observée et éléments favorables/défavorables ;
5. décision séparée pour accumulation et swing ;
6. zone(s) d'entrée, déclencheur, invalidation et objectifs, si les données le permettent ;
7. frais, spread, liquidité et risque ;
8. ce qui ferait changer la décision.

Statuts possibles : ALERTE PRÉCOCE, ACHAT PROGRESSIF, ACHAT CONFIRMÉ, SWING ACHAT, ATTENDRE, INVALIDATION / NE PAS ACHETER, DONNÉES INSUFFISANTES. Ne pas recommander d'attendre indéfiniment ; expliciter le compromis entre entrée précoce et confirmation.

## Test réel éventuel de 30 €

L'utilisateur a évoqué la possibilité d'utiliser 30 € d'argent réel pour tester. C'est une possibilité discutée, **pas une autorisation de passer un ordre ni une décision de déploiement**. La proposition évoquée était trois tranches conditionnelles de 10 € ; aucune tranche n'est automatique. Avant toute recommandation d'achat réel, vérifier les frais minimaux/réels, le spread, les conditions de perte acceptable et les règles Kraken. Aucun ordre ne sera passé par l'assistant. Le « peu importe » de l'utilisateur ne doit pas être interprété comme une confirmation qu'il accepte de perdre les 30 €.

## Décisions et propositions — distinction explicite

**Confirmé par l'utilisateur :**
- objectif accumulation + swing ;
- horizons courts et longs ;
- souhaite conserver durablement le travail dans GitHub/Notion pour éviter les pertes ;
- référence de marché KRAKEN:TELUSD et cadre spot sans automatisme conservés du projet.

**Propositions de travail de l'assistant, à ne pas présenter comme décisions définitivement adoptées :**
- répartition 70/30 entre accumulation et swing ;
- tranches d'accumulation 25/35/40 ;
- seuils statistiques de validation listés ci-dessus ;
- éventuel test réel de 30 € en trois tranches de 10 €.

## Règle de continuité

Reprendre ce document comme référence de travail. Ne pas relancer une architecture abandonnée ni demander à l'utilisateur d'exécuter des commandes PC lorsqu'il est sur mobile. Avant chaque conseil de marché, récupérer les données fraîches disponibles. Aucune modification de code, stratégie, board, compte ou ordre sans autorisation explicite.


## Audit indépendant Gemini — 2026-11-09

### Diagnostic
Gemini juge la méthode sérieuse dans ses intentions, mais trop chargée en indicateurs et vulnérable à la redondance, au double comptage et au surapprentissage. Le risque est de croire disposer de plusieurs confirmations alors que RSI, MACD, Stochastique, CCI et AO reflètent en partie le même phénomène de momentum.

### Angles morts à examiner
1. Colinéarité des indicateurs de momentum : mesurer l'apport marginal de chaque variable, ne pas compter des indicateurs corrélés comme des confirmations indépendantes.
2. Régime de marché insuffisamment formalisé : distinguer tendance, range, baisse et stress ; tester les règles par régime.
3. Volume historique différent de la liquidité exécutable : le volume d'une bougie ne garantit pas la profondeur du carnet Kraken.
4. Dérivés externes : l'Open Interest et le funding sur les marchés perpétuels peuvent influencer TEL même pour une approche spot ; disponibilité des données à vérifier.
5. Dimensionnement fixe : étudier un espacement et une taille adaptés à la volatilité via ATR, sans présumer que cette méthode améliore les résultats.
6. Risque macro : prévoir des conditions d'invalidation lorsque BTC/ETH ou la liquidité se dégradent.
7. Confusion des horizons : une position swing invalidée ne doit jamais être requalifiée en investissement long terme pour éviter de prendre une perte.
8. Contexte BTC subjectif : tester corrélation glissante et bêta de TEL par rapport à BTC, avec fenêtres et stabilité à évaluer.
9. Retest trop strict : mesurer les départs impulsifs sans retest propre afin de ne pas manquer systématiquement les mouvements.
10. Accumulation horizontale : rechercher les longues phases de stabilisation et de contraction de volatilité.

### Nettoyage proposé par Gemini — non adopté à ce stade
- Noyau candidat : structure des prix, EMA 20/50/200, RSI, ADX/DMI, ATR, OBV et volume relatif.
- Réduire le rôle ou retirer du moteur principal SMA si EMA conservées, MACD, CCI, Stochastique, AO et Bollinger.
- Tester VWAP ancré sur événements pertinents.
- Variables expérimentales à vérifier : déséquilibre du carnet Kraken à ±2 %, CVD, corrélation/bêta BTC.
- Ne pas implémenter ces suppressions/ajouts avant d'avoir vérifié disponibilité des données et mesuré leur apport hors échantillon.

### Deux setups supplémentaires à tester
1. Compression de volatilité : contraction de l'ATR/volatilité, stabilisation du prix et évolution de l'OBV ; comparer entrée anticipée avant cassure et entrée après cassure.
2. Failed Breakdown / Spring : passage sous un support puis réintégration confirmée en clôture 4H ; tester l'entrée sur réintégration sans exiger systématiquement un retest ultérieur.

Ces setups sont des hypothèses de recherche, pas des signaux validés.

### Points méthodologiques quantitatifs
- Prévenir le look-ahead bias : signal calculé à la clôture de la barre n, exécution simulée au plus tôt à l'ouverture de n+1.
- Surapprentissage : utiliser une validation chronologique walk-forward, par exemple optimisation sur 6 mois puis test sur les 3 mois suivants, en répétant le cycle. Les fenêtres restent à justifier selon l'historique disponible.
- Tester séparément plusieurs régimes et conserver un véritable échantillon final hors optimisation.
- Modéliser les frais maker/taker, spread et slippage séparément ; faire des stress tests de coûts. Le chiffre de 0,40 % avancé par Gemini n'est pas adopté comme coût universel ni comme coût total garanti.
- Mesurer l'exécution simulée en fonction de la profondeur réellement disponible, si le carnet Kraken historique ou temps réel est accessible.

### Réserves critiques sur l'audit Gemini
- ADX > 25 ou ADX 1D < 20 ne doivent pas devenir des interdictions automatiques : ce sont des seuils candidats à tester, pas des lois de marché.
- Les notions SMC, Fair Value Gap et Order Block doivent être définies objectivement avant backtest, sinon elles introduisent de la subjectivité.
- Le CVD et le carnet ne doivent être utilisés que si des données fiables et spécifiques à KRAKEN:TELUSD sont réellement accessibles.
- La suppression définitive d'indicateurs doit être décidée à partir de leur apport marginal mesuré, pas sur affirmation seule.
- ATR-based scaling est une piste, pas une garantie de meilleur dimensionnement.
- Une corrélation ou un bêta BTC sur 14 jours peut être instable ; tester plusieurs fenêtres et régimes.
- Le chiffre de stress de coûts doit être décomposé entre frais, spread et slippage et confronté au barème réel du compte.

### Conclusion de travail
L'audit Gemini est une contribution indépendante utile, mais ne valide ni la méthode ni une stratégie rentable. Il justifie une phase de simplification expérimentale et d'analyse des données. Aucun changement n'est autorisé à ce stade sur les stratégies, scripts, boards Smart View, alertes, paramètres, paper broker ou comptes.

### Actions de recherche à mener
1. Vérifier quelles données TradingView MCP expose réellement pour KRAKEN:TELUSD : OHLCV, historique, volume, indicateurs, carnet, CVD et données dérivées.
2. Établir la fraîcheur, profondeur et complétude des historiques disponibles.
3. Mesurer les corrélations entre indicateurs et leur apport marginal.
4. Comparer les six setups (quatre initiaux + compression + failed breakdown) sur le même protocole.
5. Ajouter régime de marché, ATR sizing et filtre macro comme variantes expérimentales, pas comme règles imposées.
6. Construire un walk-forward sans fuite de futur avec frais, spread et slippage explicitement modélisés.
7. Obtenir les audits indépendants de Claude, Grok et DeepSeek avant arbitrage final ; ne pas décider par vote majoritaire.

### Statut
Audit reçu de Gemini et enregistré comme avis indépendant. Les recommandations restent des hypothèses à vérifier. Les règles de sécurité existantes et le cadre KRAKEN:TELUSD spot/paper-only restent inchangés.
