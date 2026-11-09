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


## Audit indépendant DeepSeek — 2026-11-09

### Portée et niveau de preuve
DeepSeek précise ne pas avoir exécuté de backtest pour le compte de l'utilisateur. Il classe ses recommandations en [Démontré], [Plausible] et [Hypothétique]. Les chiffres de carnet, spread, volume et corrélation qu'il cite sont des observations publiques rapportées par DeepSeek, non vérifiées indépendamment dans cet échange ; leur date précise et leur méthode d'observation ne sont pas fournies. Ils ne doivent donc pas être traités comme des conditions actuelles de marché.

### Diagnostic central
DeepSeek estime que la méthode doit être davantage ancrée dans la microstructure réelle de KRAKEN:TELUSD. Son argument principal est que la profondeur exécutable de la paire Kraken pourrait être faible au point de rendre les backtests au prix moyen irréalistes, surtout si les frais, le spread et l'impact de marché ne sont pas modélisés.
Il identifie aussi trois faiblesses de gouvernance : indicateurs redondants, filtre BTC/ETH non formalisé et séparation insuffisante entre accumulation et swing.

### Dix angles morts identifiés
1. **Liquidité exécutable Kraken** : plafond de taille et type d'ordre à définir selon la profondeur réelle, le spread et l'impact. DeepSeek rapporte, sans vérification indépendante ici, un instantané de 6 710 USD de profondeur bid et 11 550 USD ask à ±2 %, spread 0,36 % et volume 24 h proche de 24 000 USD. Ces chiffres sont datés/non datés de façon précise et ne sont pas des données actuelles garanties.
2. **Redondance des indicateurs** : RSI, Stochastique, CCI, MACD et AO sont des variables de momentum partiellement corrélées ; multiples EMA/SMA et Bollinger/ATR ajoutent aussi des degrés de liberté.
3. **Filtre BTC/ETH non testable** : transformer le contexte en règles mesurables et versionnées plutôt qu'en jugement subjectif.
4. **Conflit accumulation/swing** : règles, capitaux, horizons, entrées et mesure de performance séparés.
5. **Absence de flux d'ordres** : envisager delta, absorption et déséquilibre des flux pour étudier les retournements précoces, sous réserve de données fiables.
6. **Cassures inadaptées à la faible liquidité** : un pic de volume relatif sur une base faible peut être trompeur ; tester clôture, persistance, mèches de rejet et continuité des flux.
7. **Invalidation et risque incomplets** : préciser invalidation, risque par trade, R:R minimal, taille et méthode de stop avant entrée ; empêcher le moyennage à la baisse non contrôlé.
8. **Validation historique insuffisamment spécifiée** : walk-forward avec purge des observations chevauchantes, période et taille d'échantillon, métriques de risque, turnover et sensibilité aux paramètres.
9. **Catalyseurs propres à TEL** : partenariats, annonces réseau, staking/validateurs/gouvernance, tokenomics/unlocks et listings peuvent modifier le contexte technique.
10. **Mesure de performance trop pauvre** : suivre au minimum rendement net, Sharpe/Sortino, drawdown maximal, taux de réussite, gain/perte moyen, turnover, coûts et comparaison à DCA et buy-and-hold.

### Améliorations prioritaires proposées
**Priorité 1 — Microstructure et impact de marché**
- Chercher des données tick-by-tick et carnets historiques Kraken ; DeepSeek cite CryptoHFTData et CryptoStruct comme pistes commerciales, non vérifiées ici.
- Estimer le slippage selon taille d'ordre et profondeur ; fixer un plafond de taille par ordre. Le seuil illustratif de 0,2 % d'impact proposé par DeepSeek est un choix de risque à tester, pas une règle adoptée.
- Préférer les ordres limites lorsque cela est cohérent avec le plan ; une limite ne garantit ni exécution ni sortie. L'urgence d'une invalidation peut nécessiter une autre décision, mais aucune exécution réelle n'est autorisée ici.
- Distinguer frais maker/taker, spread, slippage et exécution partielle.

**Priorité 2 — Réduction du noyau d'indicateurs**
- Noyau candidat : structure des prix ; volume brut/relatif et éventuellement Volume Profile (POC/value area) ; ATR ; un seul oscillateur de momentum ; une paire de moyennes mobiles (par exemple 20/50) et une moyenne longue (200) pour le contexte.
- DeepSeek propose de supprimer MACD, Stochastique, CCI, AO, OBV et la multiplication EMA/SMA ; Bollinger pourrait rester visuel mais pas signal de sizing.
- Ces suppressions ne sont pas adoptées automatiquement : mesurer la corrélation et l'apport marginal hors échantillon avant arbitrage. L'OBV peut être bruité sur faible liquidité, mais cela doit être vérifié sur les données TEL.

**Priorité 3 — Filtre de régime BTC mesurable**
- Exemple de régime favorable proposé : BTC au-dessus de sa MM200 journalière, dominance BTC stable/en baisse sur 20 jours et volatilité réalisée hors zone de panique.
- Exemple défavorable : BTC sous MM200 ou dominance BTC en forte hausse.
- Ces seuils sont des hypothèses de recherche, pas des règles acceptées. Mesurer retards, faux filtres et occasions manquées ; l'accumulation doit rester régie séparément.

**Priorité 4 — Séparation des livres**
- Accumulation : horizon pluriannuel, DCA et/ou paliers de valorisation hebdomadaire, réserve de capital, pas de stop serré de swing.
- Swing : horizon heures/semaines, risque défini, stop structurel ou ATR, R:R défini, entrées planifiées et performance isolée.
- DeepSeek donne 1–2 % de risque par trade du livre swing comme exemple. Cette proposition est incompatible avec la règle de projet déjà fixée à 0,25 % maximum du capital virtuel par trade : elle est donc explicitement rejetée comme règle applicable, sauf décision ultérieure expresse de l'utilisateur. Le plafond existant de 0,25 % reste prioritaire.

**Priorité 5 — Order flow**
- Calculer le volume delta à partir des trades Kraken (achats taker moins ventes taker), détecter les ventes agressives absorbées sans baisse proportionnelle du prix et exploiter le Volume Profile.
- Les données tick-by-tick historiques peuvent être payantes ; une approximation à partir des bougies est moins précise. Ne jamais prétendre disposer d'un CVD/footprint fiable si le flux n'est pas réellement exposé pour KRAKEN:TELUSD.

### Autres règles et hypothèses de DeepSeek à évaluer
- Cassure : tester clôture au-delà du niveau, volume en multiple de sa moyenne, persistance sur plusieurs bougies, mèches de rejet et continuité de l'order flow.
- Stops : invalidation par structure ou ATR ; ne jamais renforcer seulement parce que le prix baisse.
- Régime : comparer MM200 BTC, dominance et volatilité réalisée, en tenant compte du retard de ces filtres.
- Catalyseurs TEL : intégrer un calendrier d'événements vérifiés ; ne pas spéculer sur des annonces non confirmées.
- Benchmarks : comparer aux stratégies simples DCA et buy-and-hold.
- Métriques : Sharpe, Sortino, drawdown, turnover, coût total, taux de réussite et ratio gain/perte.
- Validation : walk-forward chronologique avec purge si les labels/horizons se chevauchent ; réserver un échantillon final non utilisé pour sélectionner les paramètres.

### Réserves et points à ne pas reprendre tels quels
- Les chiffres de profondeur, spread, volume 24 h et corrélation TEL/BTC (~0,6 en 2025) sont des chiffres rapportés par DeepSeek ; ils ne sont ni confirmés comme actuels ni vérifiés indépendamment dans cet audit.
- Le coût aller-retour 1,2–1,6 % est une estimation illustrative de DeepSeek, dépendante du spread et du barème maker/taker ; recalculer avec le barème réel, la taille, le carnet et le mode d'exécution.
- L'usage systématique des ordres limites n'assure pas une exécution : risque de non-exécution, exécution partielle et sélection adverse.
- Les seuils BTC MM200, dominance 20 jours, impact 0,2 % et risque 1–2 % sont des propositions, pas des décisions.
- L'affirmation que les données de carnet historiques sont disponibles commercialement auprès des fournisseurs cités doit être vérifiée avant achat ou intégration.
- L'extrait fourni par l'utilisateur s'interrompt au milieu d'un tableau de classification des indicateurs, après le début de la ligne « Momentum ». La suite éventuelle de l'audit DeepSeek n'a pas été reçue ; cette capture ne prétend pas être complète.

### Arbitrage provisoire
Convergences Gemini + DeepSeek :
- réduire le nombre d'indicateurs et mesurer leur redondance ;
- formaliser le régime BTC/ETH ;
- isoler accumulation et swing ;
- intégrer liquidité, spread, frais et slippage dans les simulations ;
- renforcer la validation hors échantillon et éviter le look-ahead ;
- étudier CVD/order flow et les phases de faible volatilité, sans supposer leur disponibilité.

Points spécifiques à DeepSeek à investiguer :
- profondeur exécutable réelle sur Kraken et plafond de taille ;
- données tick-by-tick, trades taker et carnet historique ;
- Volume Profile ;
- calendrier des catalyseurs TEL ;
- métriques de performance ajustées au risque et benchmarks.

### Actions de recherche
1. Mesurer à nouveau le carnet et le spread KRAKEN:TELUSD au moment de chaque analyse, avec horodatage et taille d'ordre de référence.
2. Vérifier ce que TradingView MCP et les connecteurs réellement disponibles exposent : OHLCV, trades, bid/ask, carnet, delta, Volume Profile, dominance BTC et données de dérivés.
3. Vérifier la provenance, la période et la qualité des chiffres publics cités par DeepSeek avant de les utiliser.
4. Comparer un noyau réduit d'indicateurs aux variantes actuelles, en mesurant l'apport marginal.
5. Définir séparément le livre accumulation et le livre swing ; conserver le plafond de risque swing de 0,25 % du capital virtuel.
6. Construire un protocole walk-forward avec purge, coûts réalistes, impact de marché, exécutions partielles et benchmarks.
7. Comparer les audits de Claude et Grok avant de décider ; pas de vote majoritaire, les arguments doivent être vérifiés.

### Statut
Audit DeepSeek reçu et capturé comme avis indépendant, avec une limite de complétude de l'extrait. Aucune stratégie, script, board Smart View, alerte, paramètre, paper broker, compte ou ordre n'a été modifié. Les recommandations restent des hypothèses de recherche ; les règles de sécurité existantes restent en vigueur.


## Audit indépendant Claude — 2026-11-09

### Portée et niveau de preuve
Claude indique n'avoir effectué aucun backtest et ne disposer d'aucune donnée TEL pour cet audit. Il s'agit d'une critique méthodologique, pas d'un conseil financier ni d'une validation de stratégie. Les références académiques et les chiffres de frais rapportés ci-dessous doivent être distingués des données propres à notre compte et vérifiés avant usage.

### Diagnostic
La méthode produit potentiellement beaucoup de signaux sans définir assez précisément ce qu'est un bon point d'entrée. Elle peut compter plusieurs fois la même information, ne chiffre pas suffisamment les coûts d'exécution et comporte de nombreux degrés de liberté. Risque principal : rationaliser après coup des entrées qui semblent bonnes sur un échantillon court.

### Dix angles morts
1. **Absence de critère de succès et de baseline** : définir à l'avance un benchmark simple (DCA périodique) et mesurer prix moyen d'acquisition, MAE/MFE, rebonds manqués et performance nette.
2. **Coûts sous-estimés** : Claude rapporte qu'à partir du 9 juillet 2026 le palier 1 Kraken Pro serait à 0,40 % maker / 0,80 % taker, soit jusqu'à 1,6 % aller-retour taker avant spread et slippage. Ce barème, sa date d'effet et son applicabilité au compte de l'utilisateur ne sont pas vérifiés ici ; les frais personnels doivent être vérifiés directement avant calcul.
3. **Indicateurs corrélés** : RSI, Stochastique, CCI, AO et MACD mesurent des dimensions proches du momentum dérivé du prix.
4. **Surapprentissage et tests multiples** : multiplication des setups, indicateurs, timeframes et paramètres ; références citées par Claude : Sullivan, Timmermann & White (1999), Bajgrowicz & Scaillet (2012). Les références doivent être consultées avant d'en tirer des affirmations précises.
5. **Échantillon court et mono-régime** : l'historique disponible de TEL peut être insuffisant et dominé par un ou deux cycles ; tester la couverture réelle avant de conclure.
6. **Risque idiosyncratique** : token unlocks, narratif, réglementation, listings et événements propres à TEL peuvent invalider une lecture technique.
7. **Conflit des deux moteurs** : capital et signaux peuvent être mélangés ; un swing peut vendre ce que l'accumulation vient d'acheter. Examiner aussi les conséquences fiscales selon la résidence, sans présumer la situation fiscale de l'utilisateur.
8. **Hiérarchie des timeframes** : cinq horizons sans règle de priorité laissent choisir après coup la lecture favorable ; réduire et fixer une hiérarchie par moteur.
9. **Régimes insuffisamment définis** : formaliser le régime et le filtre BTC/ETH ; bêta et corrélation de TEL peuvent varier.
10. **Coût de l'attente non mesuré** : chiffrer les rebonds manqués par l'attente des confirmations, ainsi que les faux départs évités.

### Biais de données signalés
- Bougies non clôturées et look-ahead.
- Trous de cotation et faibles volumes sur TEL/USD.
- OBV et VWAP potentiellement bruités sur une paire peu liquide.

### Améliorations prioritaires
- Définir les métriques et la baseline avant tout test.
- Réduire à deux timeframes principaux par moteur ; 15m uniquement pour affiner l'exécution.
- Mesurer spread et profondeur réels de TEL/USD ; n'envisager une opération que si l'avantage attendu dépasse les coûts de façon suffisamment robuste, multiple à estimer sur données et non à choisir arbitrairement.
- Geler les règles avant évaluation.
- Lancer un paper trading prospectif horodaté, sans retoucher les règles pendant la période de mesure. C'est un complément important aux tests historiques, qui restent exposés au biais de sélection.

### Indicateurs — proposition de Claude, non adoptée
- **Garder comme noyau candidat** : structure/niveaux, ATR pour la taille et les stops, volume relatif, une moyenne longue (SMA ou EMA 200), un seul oscillateur.
- **Retirer du moteur principal selon Claude** : CCI, Stochastique, AO, moyennes intermédiaires redondantes, Bollinger, OBV et VWAP glissant sur cette paire.
- **Ajouter comme variables candidates** : ratio TEL/BTC (force relative), distance au plus haut/drawdown, percentile de volatilité, VWAP ancré sur un creux majeur, calendrier des déblocages.
- Les flux on-chain vers les exchanges sont qualifiés de plausibles mais peu démontrés pour les petites capitalisations.
- Ne pas supprimer définitivement les variables avant d'avoir mesuré leur apport marginal, leur stabilité et la qualité de leurs données sur TEL.

### Configurations manquantes proposées
1. Capitulation avec volume extrême suivie d'absorption.
2. Compression de volatilité en range avant expansion.
3. Faux breakdown / Spring dans un range large.
4. Divergence de force relative TEL/BTC.
5. Configuration explicite « ne rien faire » lorsque le marché manque de structure.

Ces configurations sont des hypothèses à formaliser et tester, pas des signaux validés.

### Méthode améliorée proposée
1. **Régime (1W/1D)** : tendance, volatilité et contexte BTC ; il détermine les conditions et le budget autorisés, pas le déclencheur précis.
2. **Moteur A — accumulation** : entrées sur valeur (zones 1D/1W), pas uniquement sur retournement ; première tranche limitée, suivantes conditionnées à l'amélioration de la structure (creux relevé, reprise de niveau).
3. **Moteur B — swing** : structure 4H/1H, sorties et invalidations définies avant l'entrée, taille adaptée à l'ATR.
4. **Filtre de coûts** avant toute simulation d'exécution ou recommandation.
5. **Réduction du risque de rebond manqué** : tester des entrées par tranches plutôt qu'une décision tout-ou-rien ; hypothèse plausible, pas encore démontrée.

Claude décrit comme hypothèse d'accumulation durable : base longue, volume qui se tarit puis absorption, volatilité comprimée et force relative stable. Cela reste à vérifier empiriquement.

### Tests indispensables proposés
- Walk-forward chronologique avec purge/embargo lorsque les horizons de labels ou positions se chevauchent.
- Deflated Sharpe Ratio et/ou Reality Check pour tenir compte des tests multiples, selon disponibilité des données et protocole statistique approprié.
- Stabilité des paramètres : rechercher des plateaux robustes plutôt qu'un optimum isolé.
- Scénario pessimiste avec coûts doublés.
- Résultats séparés par sous-période et régime.
- Comparaison systématique au DCA.
- Paper trading prospectif horodaté après gel des règles.
- Mesure des MAE/MFE et des occasions manquées pour arbitrer entre précocité et confirmation.

### Risques non résolubles soulignés
- Historique potentiellement trop court pour conclure sur le swing.
- Liquidité future incertaine.
- Risque émetteur et réglementaire.
- Régime de marché futur inconnu.
- Absence possible d'un historique fiable du carnet d'ordres.

### Réserves et arbitrage
- Le chiffre de frais Kraken cité par Claude est à vérifier dans les conditions en vigueur et le barème individuel ; ne pas le présenter comme confirmé.
- Réduire les timeframes à deux par moteur est une proposition méthodologique ; la sélection finale doit être justifiée par l'usage et les données disponibles.
- Le paper trading prospectif est précieux pour éviter de sélectionner rétrospectivement une règle gagnante, mais ne remplace pas les tests historiques et ne garantit pas de représentativité de tous les régimes.
- La proposition de supprimer OBV/VWAP doit être évaluée sur les données de la paire, pas acceptée par autorité.
- Claude déconseille d'optimiser 70/30 et 25/35/40 : ces répartitions restent des hypothèses de discussion, pas des décisions de l'utilisateur.
- Le cadre de risque existant reste prioritaire : paper trading seulement, plafond 0,25 % du capital virtuel par trade, KRAKEN:TELUSD, spot, sans levier, aucune opération réelle ou automatique.

### Convergences avec Gemini et DeepSeek
- Simplifier le noyau d'indicateurs et éviter le double comptage.
- Quantifier les coûts, spread, profondeur et slippage.
- Formaliser le régime BTC/ETH.
- Séparer rigoureusement accumulation et swing.
- Prévenir look-ahead et surapprentissage ; utiliser walk-forward hors échantillon.
- Tester les setups de compression et de faux breakdown.
- Ne pas confondre hypothèses, résultats incomplets et avantage démontré.

### Apports spécifiques de Claude à investiguer
- Définir la baseline DCA et les métriques avant les tests.
- Mesurer MAE/MFE et rebonds manqués pour quantifier le coût de l'attente.
- Limiter les timeframes par moteur et fixer leur hiérarchie à l'avance.
- Ajouter ratio TEL/BTC, distance au plus haut, percentile de volatilité et calendrier d'unlocks.
- Utiliser Deflated Sharpe / Reality Check et analyse de stabilité des paramètres.
- Geler les règles et compléter les backtests par du paper trading prospectif.

### Actions de recherche
1. Établir la couverture réelle des historiques KRAKEN:TELUSD et la disponibilité des bougies clôturées.
2. Vérifier le barème Kraken actuel et les frais applicables au compte ; mesurer spread, profondeur et slippage par taille d'ordre.
3. Définir à l'avance les métriques de succès et les benchmarks DCA/buy-and-hold.
4. Fixer les timeframes et la hiérarchie de chaque moteur avant les tests.
5. Ajouter MAE/MFE, rebonds manqués, coûts et turnover au protocole.
6. Préparer un protocole walk-forward avec purge/embargo, correction des tests multiples et stress test des coûts.
7. Geler une version candidate puis lancer un journal de paper trading prospectif.
8. Attendre l'audit Grok avant arbitrage global ; ne pas décider par vote majoritaire.

### Statut
Audit Claude reçu et enregistré comme avis indépendant. Aucun backtest Claude n'a été effectué et aucune donnée TEL n'a été consultée par Claude selon son avertissement. Les recommandations restent des hypothèses à tester. Aucune stratégie, script, board Smart View, alerte, paramètre, paper broker, compte ou ordre n'a été modifié.


## Audit indépendant Grok — 2026-11-09

### Portée et réserves
Grok précise ne pas avoir accès aux backtests privés, aux résultats exacts de paper trading ni au détail des boards TradingView/MCP. Il ne prétend pas avoir validé empiriquement la méthode. Ses observations sont méthodologiques. Les volumes TEL/USD et les frais cités doivent être revérifiés à la source et à la date de toute utilisation ; ils ne sont pas des mesures actuelles garanties.

### Diagnostic général
Grok juge la méthode conceptuellement cohérente pour un investisseur à deux horizons (accumulation pluriannuelle et swing), notamment grâce à la séparation des horizons, au contexte BTC/ETH, à la prise en compte des coûts et à la volonté de validation hors échantillon. Il relève toutefois :
- trop d'indicateurs redondants ;
- des confirmations techniques qui peuvent arriver après le mouvement ;
- une formalisation insuffisante des régimes et du coût d'exécution Kraken ;
- un risque simultané de sur-filtrage (rebonds manqués) et de sous-filtrage structurel (entrer dans une baisse prolongée ou un rebond seulement technique).

### Dix angles morts classés par Grok
1. **Coût d'exécution et liquidité** : Grok rapporte des frais Kraken Pro Tier 1 de 0,40 % maker / 0,80 % taker et estime qu'avec spread et impact le coût aller-retour pourrait atteindre 1,5–3 % ou davantage pour certaines tailles. Il cite aussi des volumes quotidiens souvent sous 100 kUSD sur Kraken. Ces chiffres et leur période de référence ne sont pas confirmés ici ; vérifier le barème individuel, les volumes et le carnet au moment des tests. Les entrées en plusieurs tranches peuvent multiplier les frais.
2. **Régime non formalisé** : distinguer explicitement marché haussier, baissier, range et forte volatilité ; les setups ne sont pas nécessairement transférables entre régimes.
3. **Redondance indicateurs** : RSI, Stochastique, CCI, MACD, AO et Momentum sont largement corrélés ; ADX/DMI et plusieurs moyennes peuvent aussi doubler l'information.
4. **Retard des confirmations** : les confirmations multi-timeframes, volume et structure peuvent faire manquer une part importante du rebond initial. L'estimation Grok de 30–50 % n'est pas mesurée sur TEL et ne doit pas être traitée comme un fait.
5. **Force relative insuffisamment quantifiée** : formaliser TEL/BTC, TEL/ETH et éventuellement BTC.D plutôt que laisser le filtre macro subjectif.
6. **Accumulation vs rebond technique** : quantifier durée de stabilisation, volume cumulé et succession de higher lows sur plusieurs horizons.
7. **Tranches progressives** : les répartitions 25/35/40 restent hypothétiques ; la taille devrait être étudiée en fonction de l'ATR, de la liquidité et de la distance au support.
8. **Overfitting et look-ahead** : formaliser le protocole hors échantillon, walk-forward et purge des données/paramètres optimisés.
9. **Catalyseurs fondamentaux et on-chain** : examiner upgrades réseau, migration v3, liquidité TELx, émissions et annonces Telcoin Association ; disponibilité et pertinence de ces données restent à établir.
10. **Mesure de performance duale** : suivre séparément le coût moyen d'accumulation en TEL et la performance ajustée au risque du swing, ainsi que le drawdown du capital immobilisé.

### Améliorations prioritaires proposées
- Filtre de régime candidat : ADX, pente des EMA 50/200 sur 1D et BTC.D ; seuils et règles à définir/tester, non à adopter tels quels.
- Réduire le noyau à 4–5 variables suffisamment orthogonales.
- Construire une force relative TEL/BTC et TEL/ETH, avec contexte BTC.D.
- Conditionner les tranches à l'ATR et au spread observé.
- Écrire un protocole de validation strict avant de tester.
- Inclure les frais, une estimation du demi-spread et l'impact d'exécution dans le filtre de coût.

### Indicateurs — proposition de Grok, non adoptée
**À conserver comme candidats :**
- structure des prix, supports et résistances ;
- EMA/SMA 50/200 et ATR ;
- volume relatif et OBV ;
- RSI(14) uniquement comme filtre d'extrême, pas comme signal primaire ;
- ADX/DMI.

**À supprimer ou reléguer selon Grok :**
- Stochastique, CCI, AO, Momentum 10 ;
- MACD histogramme comme signal d'entrée ;
- Bollinger comme signal principal ;
- VWAP glissant en daily/weekly sur cette paire ;
- moyennes 10/20/100 redondantes avec 50/200.

**À ajouter comme variables candidates :**
- ratios TEL/BTC et TEL/ETH, avec moyenne mobile des ratios ;
- BTC.D ;
- spread et profondeur approximative ;
- nombre de higher lows et contraction d'ATR sur 1D/4H ;
- Volume Profile/POC si réellement disponible sur TradingView.

Ces propositions divergent partiellement des audits précédents sur OBV, VWAP et le choix du noyau. Aucun indicateur ne doit être supprimé ou retenu par vote ; mesurer la disponibilité, la qualité et l'apport marginal sur KRAKEN:TELUSD.

### Configurations supplémentaires proposées
1. Failed breakdown / Spring : balayage du support puis clôture rapide au-dessus, avec volume.
2. Séquence de higher lows et reprise de l'EMA 50 en 4H/1D, dans un contexte de force relative positive.
3. Compression ATR suivie d'expansion avec volume, en zone de valeur.
4. Divergence RSI/prix sur timeframe supérieur, pas sur 15m.
5. Entrée post-catalyseur avec confirmation technique minimale.

Toutes sont des hypothèses ; edge sur TEL non démontré.

### Méthode améliorée proposée par Grok
1. Filtre de régime 1D/1W : tendance BTC, BTC.D et ADX TEL.
2. Score de setup 0–5 composé de structure, force relative, volume, stabilisation et coût acceptable.
3. Entrée progressive uniquement si score ≥3 ; tranche initiale de 25 % sur signal précoce, tranches suivantes après confirmation et selon ATR.
4. Budgets séparés : accumulation/DCA intelligent en zones de valeur et swing avec risque par trade limité.
5. Invalidation définie avant entrée (sous le creux structurel ou multiple ATR).
6. Paper trading exclusivement avec journal de la raison, du score, du coût estimé et du résultat.

Le score ≥3, la première tranche de 25 % et les autres règles chiffrées sont des propositions non testées, pas des seuils validés. Ne pas remplacer le plafond de risque existant de 0,25 % du capital virtuel par trade.

### Tests indispensables proposés
- Backtest point-in-time KRAKEN:TELUSD uniquement ; frais réels applicables, demi-spread et impact estimé ; signal à la clôture et exécution au début de la bougie suivante pour éviter le look-ahead.
- Walk-forward ou séparation stricte train/validation/test.
- Sensibilité des paramètres (±20 % comme scénario de test proposé, pas une norme universelle).
- Performances accumulation et swing séparées.
- Analyse par régime.
- Comptage des signaux et du taux de participation pour détecter le sur-filtrage.
- Paper trading prospectif de 3–6 mois proposé par Grok, sans en faire une garantie de validation.

### Risques non résolubles
- Faible liquidité structurelle et slippage imparfaitement modélisable.
- Événements fondamentaux et réglementaires imprévisibles.
- Changement durable de régime crypto.
- Biais comportementaux.
- Historique Kraken potentiellement incomplet et absence possible de données tick-by-tick.

### Arbitrage et réserves
- Les volumes 24h 40–100 kUSD mentionnés par Grok, les frais Tier 1 et l'estimation de coût aller-retour 1,5–3 % ou plus ne sont pas vérifiés indépendamment ici. Les vérifier avec données horodatées avant toute conclusion.
- Le chiffre 30–50 % de rebond manqué n'est pas démontré sur TEL.
- Le score 0–5, le seuil ≥3, les tranches proposées et les seuils de régime doivent être testés ; ne pas les introduire dans les boards existants.
- L'indicateur BTC.D et les ratios TEL/BTC/TEL/ETH ne sont candidats que si des séries fiables et synchronisées sont accessibles.
- Le Volume Profile/POC, le carnet, les données on-chain et les catalyseurs doivent être vérifiés en disponibilité réelle ; ne jamais simuler leur présence.
- Les audits divergent sur OBV, VWAP, MACD, RSI et la composition du noyau. Résoudre ces désaccords par tests d'apport marginal et qualité de données, pas par vote.
- Cadre impératif inchangé : KRAKEN:TELUSD, spot, sans levier, paper trading uniquement, capital virtuel, risque maximal 0,25 % par trade, aucune connexion/commande sur compte réel, aucun ordre automatique, aucune modification des stratégies ou boards sans autorisation.

### Convergences avec Gemini, DeepSeek et Claude
- Simplifier les indicateurs et contrôler leur redondance.
- Formaliser les régimes et la force relative BTC/ETH.
- Séparer accumulation et swing, budgets et métriques.
- Mesurer frais, spread, profondeur, slippage et impact.
- Contrôler look-ahead, surapprentissage et sélection de paramètres.
- Faire du walk-forward et comparer les résultats à des références simples.
- Étudier les springs/faux breakdowns et les compressions de volatilité.
- Distinguer strictement hypothèse, test incomplet et preuve empirique.

### Apports spécifiques de Grok à investiguer
- BTC.D et force relative TEL/BTC, TEL/ETH.
- Mesure de stabilisation par higher lows et contraction ATR.
- Mesure du taux de participation pour détecter le sur-filtrage.
- Catalyseurs fondamentaux TEL et événements tokenomics.
- Sensibilité des paramètres et paper trading prospectif de plusieurs mois.
- Score de setup, uniquement comme hypothèse à comparer à une approche sans score.

### Actions de recherche
1. Vérifier les frais Kraken réellement applicables, puis relever spread/profondeur/volume horodatés sur la paire.
2. Vérifier la disponibilité des séries BTC.D, TEL/BTC et TEL/ETH, ainsi que des données fondamentales/on-chain ; documenter les absences.
3. Définir un filtre de régime mesurable et une hiérarchie de timeframes avant toute évaluation.
4. Comparer un noyau réduit d'indicateurs par tests d'apport marginal, sans supprimer définitivement des variables sur avis externe.
5. Mesurer taux de participation, rebonds manqués, coûts et performances par régime.
6. Comparer les moteurs accumulation/swing séparément à leurs benchmarks.
7. Rédiger puis geler le protocole hors échantillon avant tout test confirmatoire.
8. Conserver les règles et boards actuels inchangés jusqu'à autorisation explicite.

### Statut
Audit Grok reçu et archivé comme avis indépendant. Grok n'a pas exécuté les backtests privés ni consulté les boards selon son avertissement. Aucun chiffre de performance n'est ajouté au dossier comme résultat vérifié. Aucune stratégie, script, board Smart View, alerte, paramètre, paper broker, compte ou ordre n'a été modifié.
