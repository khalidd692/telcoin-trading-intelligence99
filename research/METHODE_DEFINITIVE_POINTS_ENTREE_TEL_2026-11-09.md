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


## Synthèse contradictoire finale Gemini — 2026-11-09

### Portée
Gemini présente une synthèse contradictoire des quatre audits et un protocole minimal de recherche. Les propositions ci-dessous sont archivées comme recommandations à examiner, pas comme résultats empiriques. Aucune donnée de performance ou disponibilité de carnet n'est confirmée par cette synthèse seule.

### 1. Arbitrage des indicateurs
Gemini recommande de réduire fortement le noyau à :
- structure des prix / niveaux ;
- un indicateur de tendance (EMA) ;
- un indicateur de momentum (RSI) ;
- volume relatif.

Gemini propose d'ignorer CCI, AO, Stochastique et Bollinger, et de ne pas additionner plusieurs oscillateurs corrélés. Il estime que RSI, MACD, Stochastique et CCI dérivent d'informations de prix proches. Cette intuition de redondance est pertinente, mais l'affirmation selon laquelle les additionner n'augmente jamais la probabilité de succès est trop absolue : l'apport marginal doit être mesuré sur données TEL, avec tests hors échantillon. Le recours à SMC doit aussi être défini par des règles objectives, sans étiquettes discrétionnaires.

### 2. Régime et force relative
Gemini considère que TEL/BTC peut être un filtre d'entrée trop tardif sur une small cap. Il recommande de privilégier ADX ou pente EMA50 pour distinguer tendance et range, sans imposer la force relative TEL/BTC comme condition d'entrée. Cela diverge des audits Claude et Grok qui proposent d'étudier la force relative. Arbitrage à faire par comparaison expérimentale : filtre obligatoire, variable informative non bloquante, ou absence de filtre. Ne pas l'écarter sans test.

### 3. Timing et risque
Gemini propose un modèle « 1/3 précoce, 2/3 confirmation » : première exposition au signal précoce, puis ajout si la structure 4H casse à la hausse. Il traduit cela en 0,08 % et 0,17 % du capital virtuel, pour rester sous le plafond total de risque de 0,25 % par trade.

Réserve majeure : le plafond de 0,25 % est un budget de perte au stop, pas une fraction de capital à investir. La taille de chaque tranche doit être calculée à partir de la distance entre entrée et invalidation, des frais, du slippage et de l'exposition cumulée. Deux tranches ne peuvent être additionnées que si le risque total, après déplacement éventuel du stop et prise en compte des coûts, reste inférieur ou égal à 0,25 %. La règle « 1/3–2/3 » demeure une hypothèse non validée.

### 4. Entrées progressives
Gemini recommande de remplacer les tranches fixes 25/35/40 par un espacement lié à l'ATR. C'est une hypothèse à tester, pas une preuve. L'ATR seul ne garantit ni exécution ni liquidité ; l'espacement doit aussi respecter les niveaux structurels, la profondeur et le risque total.

### 5. Angles morts additionnels signalés
- **Tick size et granularité de cotation Kraken** : le tick size peut rendre certains mouvements de prix très petits relativement au prix unitaire ; son effet doit être calculé à partir des règles de cotation et données de marché réelles, pas d'un pourcentage supposé.
- **Prix de clôture vs exécution réelle** : ne pas simuler une exécution au close qui n'était pas connaissable au moment du signal. Signal sur bougie clôturée, exécution simulée au premier prix réalistement disponible ensuite, avec spread, slippage et latence.
- **Coût d'opportunité du capital immobilisé** : suivre durée d'immobilisation, rendement alternatif explicitement choisi et coût d'opportunité. Le taux sans risque pertinent dépend de la devise, de l'horizon et du véhicule réellement accessible ; ne pas en inventer un.

### 6. Protocole minimal proposé
**Benchmarks :**
- Buy & Hold : achat unique au début de la période.
- DCA : montant fixe chaque lundi à 00:00.
Gemini propose la période du 1er janvier 2024 à la date d'évaluation. Il faut d'abord vérifier que les données historiques Kraken sont complètes sur toute la période. Les benchmarks doivent utiliser les mêmes conventions de cashflows, frais, prix d'exécution et devise de référence ; préciser si le DCA garde du cash non investi et comment les dividendes/intérêts éventuels sont traités (aucun rendement de trésorerie ne doit être supposé).

**Extraction et paper trading :**
- Récupérer via les outils existants l'historique des signaux TradingView disponibles, sans présumer que l'historique complet des alertes existe.
- Conserver le journal horodaté des exécutions paper actuelles et futures.
- Aucun changement aux boards ou règles existantes pour ce travail d'évaluation.

**Stress test :**
Gemini propose d'ajouter 0,40 % au coût de chaque achat et 0,40 % à chaque vente. Ce scénario peut être conservé comme scénario de stress simple, mais ne doit pas être présenté comme le coût réel universel ni comme une représentation complète de la liquidité. Il faut distinguer frais maker/taker applicables, spread payé, slippage, impact et éventuel coût de non-exécution. Vérifier le barème individuel Kraken et éviter le double comptage du spread si la décote l'inclut déjà.

**Tests dans l'ordre proposés :**
1. Baselines Buy & Hold et DCA, avec rendement net et drawdown.
2. Performance brute des signaux actuels.
3. Performance nette avec scénarios de coûts.
4. Évaluation hors échantillon et par régime.

Gemini suggère mai–décembre 2022 comme période baissière de robustesse. Réserve : cette période ne peut être qualifiée d'out-of-sample que si elle n'a pas servi à concevoir, sélectionner ou ajuster les règles. Une période antérieure à la fenêtre de développement peut être un test historique de régime, mais un split chronologique cohérent doit être défini avant les analyses et tenir compte de la disponibilité des données Kraken TELUSD.

### 7. Critères de classification proposés par Gemini
Gemini propose :
- **Rejetée** : rendement net inférieur au Buy & Hold sur un an et drawdown supérieur au DCA.
- **Prometteuse** : rendement net supérieur au DCA et Profit Factor >1,5 sur au moins 50 trades.
- **Validée** : Profit Factor >1,5 après coût de 0,40 % par exécution, espérance positive et drawdown inférieur de moitié à Buy & Hold.

Ces seuils sont des propositions de gouvernance, pas des seuils universellement démontrés. Points à corriger avant adoption :
- Ne pas définir le rejet par une seule comparaison : accumulation et swing ont des objectifs et profils de risque différents. Comparer le swing à des benchmarks de même exposition/horizon et l'accumulation à DCA/Buy & Hold.
- Un Profit Factor élevé sur 50 trades ne suffit pas à prouver un avantage robuste ; considérer intervalles de confiance, dépendance entre trades, taille effective de l'échantillon, coûts, stabilité par régime et résultats hors échantillon.
- Drawdown « inférieur de moitié » à Buy & Hold est un objectif très exigeant et arbitraire tant que l'exposition et les flux de capitaux ne sont pas comparables.
- Le win rate et le ratio gain/perte doivent être calculés nets de coûts ; l'exemple 40 % × 2:1 donne une espérance positive brute de 0,2R seulement si le gain moyen est bien deux fois la perte moyenne et si ces valeurs incluent tous les coûts et pertes d'exécution.
- Pour une stratégie de swing peu fréquente, 50 trades peuvent nécessiter longtemps et rester insuffisants selon leur dépendance et la diversité des régimes.
- Séparer performance absolue, rendement sur capital immobilisé, rendement ajusté au risque, drawdown, turnover et durée d'exposition.

### 8. Décisions candidates et expérimentation
**Candidats à figer pour le protocole de recherche, après vérification :**
- KRAKEN:TELUSD exclusivement.
- Accumulation (1W/1D) et swing (4H/1H) évalués dans des livres et métriques distincts.
- 15m limité à l'affinage d'exécution si les données le justifient.
- Signal basé sur bougie clôturée et exécution à un prix disponible ensuite.
- Mesure explicite des coûts et de la liquidité.
- Comparaison aux benchmarks simples.
- Paper trading uniquement, spot, sans levier, risque maximal de 0,25 % du capital virtuel par trade.

**À maintenir en expérimentation :**
- 1/3 précoce et 2/3 confirmation.
- Espacement ATR des tranches.
- ADX vs pente EMA50 pour classifier les régimes.
- Utilité marginale du ratio TEL/BTC.
- Divergences RSI/CVD si données disponibles et fiables.
- Signaux éventuels MEXC/KuCoin comme information externe uniquement ; ils ne remplacent jamais l'instrument d'exécution KRAKEN:TELUSD et doivent être synchronisés et testés.
- Le scénario de coût fixe 0,40 % par côté.

### 9. Données manquantes à vérifier
- Couverture et qualité de l'historique OHLCV KRAKEN:TELUSD, notamment depuis janvier 2024 et mai–décembre 2022.
- Historique des signaux/alertes Smart View réellement récupérable.
- Tick size et tick precision applicables à la paire, historique éventuel des changements.
- Spread, profondeur bid/ask et slippage par taille d'ordre ; carnet historique si disponible.
- Frais maker/taker individuels et hypothèses d'exécution réalistes.
- Séries BTC/ETH et éventuellement BTC.D synchronisées, si testées.
- Disponibilité réelle de CVD et données on-chain ; ne pas les supposer disponibles.

### 10. Statut et garde-fous
Cette synthèse Gemini est enregistrée comme arbitrage proposé, pas comme validation empirique. Elle ne remplace pas les audits indépendants initiaux. Les points chiffrés et seuils doivent être justifiés et testés avant adoption. Aucun script, stratégie, board Smart View, alerte, paramètre, paper broker, compte ou ordre n'a été modifié.


## Synthèse contradictoire finale DeepSeek — 2026-11-09

### Portée et réserves
DeepSeek précise ne pas avoir accès aux trois autres audits (Gemini, Claude, Grok) et ne peut donc pas les comparer littéralement. Sa réponse est une analyse autonome des frictions méthodologiques probables et des contraintes décrites. Les chiffres publics, affirmations sur les frais, la liquidité, l'offre en circulation, les capacités API et les périodes historiques doivent être vérifiés avant utilisation. Aucun backtest privé n'a été exécuté dans cette réponse.

### 1. Réduction du noyau d'indicateurs
DeepSeek recommande quatre briques :
1. Structure des prix : swings, supports/résistances, consolidations.
2. Volume brut et volume relatif, par exemple rapport à la moyenne des 20 bougies.
3. ATR, uniquement pour dimensionner invalidation et taille, pas comme signal d'entrée.
4. RSI comme unique oscillateur de momentum.

DeepSeek propose de supprimer MACD, Stochastique, CCI, AO, OBV et les multiples moyennes mobiles. Le principe de réduction des degrés de liberté est pertinent ; la sélection exacte des variables doit toutefois être évaluée par disponibilité, qualité et apport marginal sur KRAKEN:TELUSD. Le volume relatif doit être interprété avec prudence sur une paire peu liquide. L'utilisation de SMC doit être traduite en règles explicites et reproductibles.

### 2. Séparation des livres accumulation et swing
DeepSeek recommande une séparation stricte des règles, budgets et mesures :
- **Accumulation** : horizon long, achats planifiés par paliers dans des zones hebdomadaires définies ex ante, plafond de déploiement et réserve préétablie ; pas de stop serré de swing. Les règles proposées (zones sous MM200 hebdomadaire ou value area) sont des exemples à tester, non des seuils adoptés.
- **Swing** : risque maximal de 0,25 % du capital virtuel par trade, invalidation structurelle ou ATR, une confirmation supplémentaire au maximum, et exécution simulée tenant compte des coûts.

DeepSeek suggère des ordres limites dans les zones. Une limite ne garantit pas l'exécution ; le risque de non-exécution et les mouvements pendant l'attente doivent être enregistrés. La séparation des livres et des métriques est retenue comme principe de recherche, sans modifier les stratégies actuelles.

### 3. Filtre BTC comme interrupteur
DeepSeek propose un filtre binaire pour le swing long :
- régime favorable : BTC au-dessus de sa MM200 journalière et dominance BTC stable ou en baisse sur 20 jours ;
- régime défavorable : BTC sous sa MM200 ou dominance BTC en hausse sur 20 jours ;
- dans le régime défavorable, swing désactivé ; accumulation poursuivie selon ses règles propres.

Ce filtre est qualifié de plausible, pas démontré sur TEL. Les seuils MM200 et 20 jours sont des hypothèses. Il faut tester filtre activé vs désactivé, avec règles figées et échantillon hors échantillon. Vérifier la disponibilité et la synchronisation des séries BTC.D avant de l'intégrer.

### 4. Plafond d'ordre et liquidité
DeepSeek rapporte des spreads observés de 0,33–0,44 % et des frais Kraken Pro variables selon les grilles, citant 0,40/0,80 % et ailleurs 0,25/0,40 %. Ces valeurs ne sont pas vérifiées dans cette réponse et sont potentiellement contradictoires selon le palier, le produit ou la date. Le barème individuel applicable doit être vérifié directement.

DeepSeek propose un plafond d'ordre tel que l'impact estimé ne dépasse pas 0,15 %, et évoque des tailles de quelques centaines de dollars dans les périodes peu liquides. Ces valeurs sont des hypothèses et ne doivent pas être traitées comme des limites validées. Le plafond doit être dérivé de données exécutables, de la profondeur réellement observée et de la tolérance au coût. Un carnet instantané ne prouve pas la profondeur historique ; des trades historiques seuls ne permettent pas de reconstruire le carnet passé.

### 5. Pistes à maintenir en expérimentation
- Order flow (delta, absorption), sous réserve de données tick et d'une méthode de calcul vérifiable.
- Force relative TEL/BTC, sans la rendre obligatoire avant comparaison expérimentale.
- Volume Profile, POC et value area, si les données et la méthode de calcul sont fiables.
- Seuils exacts du filtre BTC, à tester sur des plages raisonnables sans optimiser sur le test final.

### 6. Données manquantes selon DeepSeek
1. Trades tick historiques Kraken TELUSD pour examiner microstructure et coûts.
2. Snapshots historiques du carnet pour estimer la profondeur au moment des exécutions ; DeepSeek estime que ces données sont généralement commerciales. Disponibilité réelle à vérifier.
3. Journal des catalyseurs propres à TEL : annonces, partenariats, mises à jour réseau, gouvernance et distributions éventuelles.

DeepSeek affirme que l'API Kraken permettrait de télécharger l'historique complet des trades depuis l'origine. Cette capacité et ses limites doivent être vérifiées dans la documentation officielle et par un test réel : ne pas supposer que les endpoints publics exposent l'intégralité de l'historique exploitable ni un carnet historique. Les OHLCV TradingView et les trades bruts ne remplacent pas les snapshots de carnet.

DeepSeek rapporte aussi qu'environ 96 % de l'offre serait en circulation et qu'il n'y aurait pas de calendrier majeur d'unlock restant. Ces éléments ne sont pas vérifiés ici et ne doivent pas servir de prémisses sans source datée.

### 7. Ordre des tests proposé
**Test 1 — Coûts et microstructure :**
- Estimer frais maker/taker réellement applicables, spread, slippage et impact pour plusieurs tailles d'ordre (100, 500, 1 000 et 5 000 USD sont les tailles exploratoires proposées par DeepSeek).
- Séparer coût théorique, coût observable et coût non mesurable faute de données de carnet.
- DeepSeek propose 1,5 % aller-retour comme seuil d'invalidation du swing. Ce seuil est arbitraire à ce stade : la viabilité dépend de l'espérance brute, de la fréquence, du payoff, de l'exposition et de la distribution des coûts ; comparer des scénarios plutôt qu'utiliser un couperet non justifié.

**Test 2 — Évaluation chronologique :**
DeepSeek propose des segments 2019–2021, 2021–2022, 2022–2023 et 2023–2025, avec réoptimisation walk-forward. Ne retenir ces fenêtres que si KRAKEN:TELUSD dispose de données valides et suffisamment complètes sur chacune ; éviter les segments qui se chevauchent ambiguëment ou qui ont déjà servi à sélectionner les règles. Définir un vrai train/validation/test chronologique et ne jamais réutiliser le test final pour ajuster la stratégie.

**Test 3 — Accumulation seule :**
Comparer accumulation par paliers à DCA et Buy & Hold, avec mêmes dates, mêmes flux de capitaux, mêmes conventions de frais et exécution.

**Test 4 — Swing avec et sans filtre BTC :**
Comparer performance nette, Sortino et drawdown hors échantillon, sans retenir le filtre si son apport n'est pas robuste.

**Test 5 — Sensibilité des paramètres :**
DeepSeek propose de tester MM200 150/180/200/220/250 et volume relatif 1,2x/1,5x/2x. Ce sont des plages exploratoires, pas des paramètres à optimiser jusqu'à trouver un optimum. Évaluer la stabilité et limiter le nombre total d'essais.

### 8. Critères de classification proposés
DeepSeek propose :
- **Rejetée** : coût aller-retour >1,5 % pour la taille typique, ou performance hors échantillon négative après coûts, ou drawdown supérieur au Buy & Hold, ou accumulation ne battant pas le DCA.
- **Prometteuse** : coûts jugés raisonnables, dégradation OOS inférieure à 50 % de l'in-sample, Sortino OOS positif, et surperformance nette d'un benchmark pertinent sur au moins un livre.
- **Validée** : critères prometteurs, robustesse aux paramètres, paper trading prospectif au moins trois mois (ou nombre de trades suffisant et justifié), et Deflated/Probabilistic Sharpe Ratio significatif après correction des essais multiples.

Réserves :
- Le seuil de coût de 1,5 %, la dégradation maximale de 50 % et les durées sont des seuils proposés, pas des vérités universelles.
- L'accumulation doit être comparée au DCA et Buy & Hold ; le swing doit être comparé à des benchmarks compatibles avec son exposition et son horizon.
- Le drawdown doit être calculé avec des conventions cohérentes de cashflows et d'exposition.
- Un Sortino positif ou un Profit Factor isolé ne suffit pas à établir un avantage.
- Le nombre d'essais, les dépendances entre trades, les intervalles de confiance et la diversité des régimes doivent être pris en compte.

### 9. Timing : règle des deux conditions maximum
DeepSeek propose pour le swing :
1. Prix dans une zone de valeur/support identifiée à l'avance.
2. Une seule confirmation : volume relatif ≥1,5x sur la bougie de rejet OU divergence RSI sur l'unité supérieure, pas les deux.
3. Invalidation si clôture sous la zone avec volume supérieur à la moyenne ; pas de moyennage à la baisse.

Le seuil 1,5x et la règle d'invalidation sont des hypothèses à formaliser. Il faut définir précisément le niveau, le moment du signal, l'exécution à la bougie suivante et les cas de gap/slippage. Pour l'accumulation, DeepSeek recommande un plafond de déploiement par paliers plutôt qu'un stop serré ou un moyennage sans limite.

### 10. Angles morts résiduels signalés
- **Biais de survie de TEL** : étudier TEL ne renseigne pas sur le risque qu'un token individuel perde durablement sa liquidité ou soit délisté ; le paper trading ne modélise pas entièrement ce risque.
- **Qualité des données TradingView** : vérifier trous, agrégation de volume, prix et cohérence avec les données Kraken brutes.
- **Risque de contrepartie Kraken** : panne, restrictions, gel de retraits ou modification des conditions ; non capturé par un backtest.
- **Coûts de financement et conversion** : conversion EUR/USD, dépôts/retraits et frais éventuels peuvent compter pour l'accumulation réelle. Ces frais ne sont pas automatiquement des coûts de trading de la stratégie paper et doivent être séparés selon le scénario étudié.

### 11. Règle de timing proposée par DeepSeek
La règle « deux conditions maximum » vise à éviter le sur-filtrage :
- zone de valeur identifiée ex ante ;
- une seule confirmation minimale, volume relatif ou divergence RSI ;
- invalidation préétablie et pas de moyenne à la baisse.

C'est une hypothèse de protocole à tester face à une entrée purement structurelle et à une entrée confirmée plus tard. Elle ne doit pas être ajoutée aux boards avant autorisation.

### 12. Arbitrage provisoire et statut
**Principes retenus comme cadre de recherche :**
- simplifier et éviter le double comptage ;
- séparer accumulation et swing, règles, budgets et métriques ;
- mesurer les coûts avant de conclure sur le swing ;
- définir un filtre de régime quantifiable et tester son utilité ;
- utiliser des données KRAKEN:TELUSD, signaux clôturés et exécution réaliste ultérieure ;
- comparer aux benchmarks simples et évaluer hors échantillon ;
- rester en paper trading, spot, sans levier, risque maximal 0,25 % du capital virtuel par trade.

**À ne pas adopter sans test :**
- suppression définitive de chaque indicateur proposé ;
- seuil 1,5 % de coût, impact 0,15 %, MM200/20 jours comme interrupteur ;
- limite d'ordre en dollars ;
- score ou seuils de volume ;
- règle des deux conditions, règle 1,5x et scénarios d'allocation par paliers ;
- toute affirmation non sourcée sur les frais, le spread, l'offre en circulation ou les données tick.

Cette réponse est une proposition de protocole, pas une validation empirique. Aucun backtest n'est ajouté comme résultat. Aucun script, stratégie, board Smart View, alerte, paramètre, paper broker, compte ou ordre n'a été modifié.


## Synthèse contradictoire finale Grok — 2026-11-09

### Portée et limites de la comparaison
Grok précise ne pas avoir le texte intégral des audits Gemini, DeepSeek et Claude dans sa session. Il ne peut donc pas prétendre avoir comparé littéralement les quatre documents. Sa revue est une synthèse autonome fondée sur son premier audit et sur des divergences qu'il juge probables. Les contradictions qu'il attribue aux autres audits ne sont donc pas toutes confirmées par les textes. Cette limite est conservée explicitement.

Grok rappelle qu'aucun des quatre audits initiaux n'a produit de backtest réel sur les données privées KRAKEN:TELUSD. Les recommandations restent méthodologiques jusqu'à validation par des tests.

### 1. Arbitrage proposé par Grok
**Indicateurs :**
- Noyau proposé : structure, EMA 50/200, ATR, volume relatif, RSI comme filtre d'extrême.
- Ajouter une force relative binaire TEL/BTC (ratio au-dessus de sa MM20 ou MM50 en 1D).
- Reléguer/supprimer les autres oscillateurs redondants.
Réserve : ce choix est une proposition, pas un consensus démontré. DeepSeek recommandait un noyau encore plus réduit et ne voulait pas imposer TEL/BTC ; Gemini jugeait TEL/BTC potentiellement tardif ; Claude proposait de le mesurer. La force relative doit donc rester une variable expérimentale, pas une condition obligatoire.

**Régime :**
Grok propose ADX 1D, pente EMA 50/200 1D et BTC.D. Cette combinaison peut être redondante ou trop complexe ; comparer à un filtre simple et à l'absence de filtre. Les règles exactes doivent être définies avant les tests.

**Timeframes :**
- 1W/1D : contexte et accumulation.
- 4H : setup swing.
- 1H/15m : timing d'exécution progressive uniquement.
Cette hiérarchie est cohérente comme candidat de protocole, mais les unités retenues doivent dépendre de la qualité des données et être figées avant l'évaluation.

**Liquidité et coûts :**
Grok propose frais Tier 1 (0,40 % maker / 0,80 % taker), demi-spread observé et impact estimé, puis de rejeter les mouvements attendus inférieurs à trois fois le coût. Les frais doivent être vérifiés sur le compte et le type d'ordre ; le facteur 3× est arbitraire tant qu'il n'est pas relié à l'espérance, au risque et à la distribution des coûts.

**Entrées progressives :**
Grok suggère des tranches conditionnées au score et à l'ATR, mais le score et ses pondérations ne sont pas définis ni validés. Ne pas introduire un score opaque ; si un score est testé, chaque composante doit être objective et son apport marginal mesuré.

### 2. Preuves générales et hypothèses TEL
Grok classe comme principes généraux bien établis :
- risque de redondance entre oscillateurs et de faux sentiment de confirmation ;
- look-ahead bias et surapprentissage multi-paramètres ;
- importance des frais et du slippage ;
- nécessité de compter les coûts des entrées progressives.

Il classe comme non démontrés spécifiquement sur KRAKEN:TELUSD :
- nombre optimal d'indicateurs ;
- seuils de force relative ou de BTC.D ;
- avantage net des configurations existantes ou supplémentaires ;
- allocations 70/30 et tranches 25/35/40 ;
- edge net après coûts Kraken.

Réserve : la littérature générale ne prouve pas automatiquement qu'un indicateur ou filtre améliore les résultats de TEL. Chaque variable doit être testée sur données adaptées.

### 3. Angles morts communs proposés par Grok
- Règle d'exécution précise : signal sur bougie clôturée, exécution au premier prix disponible ensuite, jamais au close rétrospectif.
- Taux de participation : part des setups potentiels réellement pris et occasions écartées par les filtres.
- Sizing cohérent avec le risque maximal de 0,25 % au stop.
- Séparation du capital immobilisé en accumulation et du capital à risque swing dans les métriques.
- Journal des catalyseurs TEL : upgrades, TELx, annonces Telcoin Association et événements de gouvernance.
- Durée minimale de paper trading prospectif à définir ; Grok propose 3–6 mois dans son premier audit et au moins 3 mois ici.
- Vérification de la disponibilité historique exacte de KRAKEN:TELUSD.

### 4. Protocole minimal proposé
**Données candidates à réunir :**
- OHLCV KRAKEN:TELUSD sur 1W, 1D, 4H et 1H, sur la plus longue période de qualité disponible.
- Spread, volume et profondeur observables, avec horodatage.
- BTC/ETH et BTC.D synchronisés si les filtres sont évalués.
- Journal paper structuré : date, setup, état du régime, signal, taille, coût estimé, invalidation, exécution et résultat.

**Ordre des tests :**
1. Vérifier couverture, fraîcheur et cohérence des données ; estimer les coûts aller-retour.
2. Écrire et figer les règles simplifiées avant tout test.
3. Évaluer sur période de développement, avec signal clôturé et exécution au prix disponible ensuite ; intégrer les frais et spread.
4. Réaliser walk-forward ou séparation chronologique stricte train/validation/test.
5. Paper trading prospectif, risque maximal 0,25 % par trade, journal complet.
6. Comparer aux benchmarks DCA et Buy & Hold avec mêmes périodes, cashflows et conventions de coûts.

### 5. Timing : réduire les entrées trop précoces et trop tardives
Grok propose :
- éviter une entrée trop précoce par structure claire, volume relatif, contexte de force relative et régime non clairement baissier, avec invalidation préétablie ;
- éviter une entrée trop tardive en autorisant une première tranche de 30–40 % de la taille prévue sur signal précoce, puis des ajouts sur confirmation ;
- ne pas attendre six ou sept indicateurs convergents.

Les seuils 30–40 % et la combinaison des conditions sont des hypothèses non validées. Le sizing doit être calculé à partir du stop, des coûts et du risque cumulé. Le risque total de toutes les tranches d'un trade ne doit jamais dépasser 0,25 % du capital virtuel. Une tranche n'est pas 30–40 % du risque autorisé sans calcul de son risque réel.

### 6. Mesures et critères proposés
Grok recommande des mesures séparées :
- **Accumulation** : prix moyen d'acquisition en TEL, capital déployé, drawdown du capital immobilisé, résultat vs DCA et Buy & Hold.
- **Swing** : espérance nette, Profit Factor, drawdown, nombre de trades, taux de réussite, gain moyen/perte moyenne.
- **Global** : résultat net vs DCA et Buy & Hold, durée d'exposition et taux de participation.

Seuils proposés par Grok :
- **Rejetée** : espérance nette ≤0, ou drawdown >2× Buy & Hold, ou moins de 20 trades exploitables.
- **Prometteuse** : espérance nette positive, PF >1,3, drawdown acceptable et au moins 30 trades.
- **Validée** : critères prometteurs maintenus hors échantillon et en paper trading prospectif pendant au moins 3 mois sans dégradation majeure.

Réserves :
- Les seuils PF 1,3, 20/30 trades et drawdown 2× sont arbitraires tant qu'ils ne sont pas justifiés par la puissance statistique, la dépendance des trades et les objectifs de risque.
- Un nombre minimal de trades ne suffit pas à prouver la robustesse ; considérer intervalles de confiance, nombre effectif d'observations, régimes, coûts et correction des essais multiples.
- Les comparaisons de drawdown doivent employer des conventions identiques de capital, cashflows et exposition.
- La validation prospective de trois mois peut être trop courte si peu de signaux sont générés ; le nombre d'observations et leur diversité comptent aussi.

### 7. Décisions proposées et points expérimentaux
**Principes compatibles avec le cadre existant :**
- simplification des indicateurs ;
- séparation stricte accumulation/swing ;
- risque maximal de 0,25 % du capital virtuel par trade ;
- calcul explicite des coûts avant une entrée simulée ;
- règles et hiérarchie des timeframes figées avant évaluation ;
- aucun signal primaire sur 15m ;
- aucun changement des boards existants ; tests en parallèle uniquement après autorisation.

**À maintenir en expérimentation :**
- EMA50/200 et ADX comme noyau ou filtre de régime ;
- TEL/BTC au-dessus de sa MM20/MM50 ;
- BTC.D comme contexte ;
- facteur 3× coût ;
- score de setup et pondération ;
- première tranche de 30–40 % ;
- seuils PF et nombre minimal de trades ;
- filtres fondamentaux TEL.

### 8. Arbitrage transversal à conserver
Les audits et synthèses convergent sur la nécessité de réduire la redondance, séparer les horizons, contrôler les coûts, empêcher le look-ahead et mesurer hors échantillon. Ils divergent encore sur le noyau d'indicateurs, l'usage de TEL/BTC, le filtre BTC.D/ADX, les confirmations, les seuils de coût et les critères de validation.

Ces désaccords ne seront pas résolus par un vote ou par l'autorité d'un modèle. Ils seront arbitrés par :
1. disponibilité et qualité réelle des données ;
2. règles définies ex ante ;
3. comparaison de variantes simples ;
4. apport marginal hors échantillon ;
5. coûts et exécutions réalistes ;
6. stabilité par sous-période et régime.

### Statut
Cette revue finale Grok est enregistrée comme avis complémentaire, avec sa limite importante : Grok n'avait pas accès aux trois autres textes dans sa session et n'a donc pas effectué de comparaison littérale. Ses seuils et propositions restent des hypothèses à tester. Aucun backtest n'est ajouté comme résultat, et aucun script, stratégie, board Smart View, alerte, paramètre, paper broker, compte ou ordre n'a été modifié.


## Synthèse finale Claude — arbitrage personnel et protocole de travail — 2026-11-09

### Portée et limites
Claude indique n'avoir dans sa session que son propre audit et ne pas disposer des textes Gemini, DeepSeek et Grok ni d'un outil TradingView/Smart View. Sa réponse n'est donc pas une comparaison directe des quatre audits et ne contient aucune extraction ni aucun test TradingView. Les synthèses croisées précédentes ont été fournies séparément par Gemini, DeepSeek et Grok et sont archivées indépendamment.

### Critique de son premier audit
Claude corrige ses propres suggestions antérieures :
- Force relative TEL/BTC, percentile de volatilité et VWAP ancré restent en expérimentation, pas dans le noyau.
- Le « multiple de coût à estimer » peut être circulaire sur petit échantillon ; préférer simuler chaque trade net de coûts pessimistes sans seuil arbitraire.
- Les frais cités (0,40 % maker / 0,80 % taker au palier 1) doivent être confirmés pour le compte et le type d'ordre.

### Noyau et règles proposées
Claude propose comme noyau de protocole :
- prix et structure ;
- SMA 200 journalière ;
- volume relatif ;
- ATR pour stop et sizing.
Le reste est ignoré dans le protocole de recherche, sans toucher aux boards existants.

Régime : une seule variable, TEL au-dessus ou en dessous de sa SMA 200 journalière. Filtre BTC/ETH expérimental.

Timeframes :
- Moteur A accumulation : 1W/1D.
- Moteur B swing : 1D contexte, 4H signal, 1H affinage.
- 15m exclu du protocole candidat pour limiter le bruit et les coûts ; cette exclusion reste une hypothèse plausible, non démontrée.

Tranches : trois tranches égales comme référence de départ ; 25/35/40 et 70/30 restent des hypothèses. Aucune tranche ne doit être dimensionnée sans calcul de risque et d'exposition.

### Preuves générales et hypothèses
Claude classe comme principes méthodologiques généraux :
- tests multiples et surapprentissage peuvent faire apparaître de fausses stratégies gagnantes ;
- test hors échantillon avec purge lorsque nécessaire ;
- les coûts érodent les stratégies à rotation élevée ;
- le momentum observé sur le marché crypto large n'est pas une preuve de momentum exploitable sur TEL.

Plausible, mais non démontré sur TEL :
- filtre de tendance longue ;
- sizing par ATR ;
- entrées par tranches.

Hypothèses non démontrées :
- détection précoce de retournement ;
- distinction quantitative accumulation durable / rebond technique ;
- force relative et filtres BTC/ETH ;
- allocations et répartitions de tranches.

### Angles morts complémentaires identifiés
1. **Risque et frais** : 0,25 % fixe détermine le budget de perte au stop, pas la rentabilité. Claude illustre l'effet d'un coût aller-retour hypothétique de 1,6 % sur des stops de 5 % ou 2 %. L'arithmétique doit être recalculée avec les frais réellement applicables, le spread, le slippage et la taille.
2. **Budget accumulation** : le moteur A n'a pas nécessairement de stop de swing ; il lui faut donc un plafond d'exposition/déploiement distinct, défini à l'avance. Le plafond de risque swing de 0,25 % ne suffit pas à encadrer l'accumulation.
3. **Objectif en TEL** : mesurer les TEL détenus à la fin, pas seulement le rendement en dollars ; prix moyen d'acquisition et quantité finale sont des métriques importantes.
4. **Fills irréalistes** : les backtests sur bougies ne reconstituent pas le carnet. Une limite simplement touchée ne garantit pas l'exécution ; un stop peut être exécuté au-delà de son niveau. Les fills doivent être conservateurs.
5. **Puissance statistique** : le paper trading peut prendre longtemps sur un actif peu actif ; autoriser explicitement un verdict « non concluant ».
6. **Dépendance des trades** : les trades peuvent être regroupés par régime/événement et ne sont pas indépendants ; envisager un bootstrap par blocs plutôt qu'un bootstrap naïf.
7. **Pré-enregistrement** : dater et geler les règles et hypothèses avant de consulter les résultats du test final.

### Timing : trop précoce vs trop tardif
Claude reconnaît qu'aucune règle ne supprime les deux risques.
- Prématuré : première tranche plus petite, invalidation et budget de risque fixés ; mesurer MAE.
- Tardif : une seule confirmation (par exemple clôture 4H), puis ajout sur retest ; mesurer l'écart entre le prix d'entrée et le creux local.
- Comparer le coût net combiné des occasions manquées et des faux départs ; ne pas optimiser seulement le taux de réussite.

Ces règles sont des propositions à tester, pas des règles opérationnelles adoptées.

### Décisions recommandées par Claude
1. Métrique primaire accumulation : TEL accumulés par dollar investi.
2. Métrique primaire swing : R net après coûts.
3. Capitaux virtuels distincts pour accumulation et swing, sans signaux partagés.
4. Swing : tester en premier les deux configurations « repli en tendance » et « cassure/retest » ; balayage de support et accumulation après stabilisation restent expérimentaux.
5. Coûts : hypothèse taker + spread pessimiste par défaut. Un fill maker ne serait reconnu que si le prix a traversé le niveau ; cette convention doit être spécifiée précisément et comparée à des scénarios de non-exécution.
6. Aucun réglage de paramètres pendant les tests ; journaliser le nombre de variantes essayées.

### Expérimentation uniquement
- Force relative TEL/BTC.
- Filtre BTC/ETH.
- Régimes de volatilité.
- Répartitions 70/30 et 25/35/40.
- Détection d'accumulation durable.
- Tout indicateur hors noyau.

### Données manquantes
- Barème de frais réellement applicable au compte.
- Date de début, trous, volume et qualité de l'historique TradingView KRAKEN:TELUSD.
- Spread et profondeur Kraken, idéalement via relevés prospectifs horodatés ; sans données historiques de carnet, conserver un scénario de coûts élevé.
- Calendrier des déblocages/événements tokenomics, à vérifier avec sources datées.
- Budget maximal d'exposition du moteur A, à définir par l'utilisateur avant tout test d'accumulation réel ; en paper, le plafond virtuel doit être explicitement fixé.

### Ordre des tests proposé
1. Pré-enregistrer et dater les règles.
2. Contrôler la qualité des données et réserver une dernière période historique cachée, jamais consultée pour ajuster les règles.
3. Calculer DCA et Buy & Hold sur les mêmes périodes et conventions.
4. Backtest sur période de développement avec coûts pessimistes.
5. Évaluer une seule fois sur la période cachée.
6. Paper trading prospectif avec fills conservateurs (achat à l'ask, vente au bid, frais inclus) et journal complet.
7. Décider selon des critères définis avant le test.

### Critères de classification proposés par Claude
Claude propose des intervalles de confiance à 95 % par convention :
- **Rejetée** : résultat net inférieur ou égal à la baseline en développement ; ou borne haute de l'IC de surperformance négative sur test caché/prospectif ; ou perte au-delà du budget de 0,25 % hors slippage ; ou résultat qui disparaît avec les coûts pessimistes.
- **Prometteuse** : surperformance nette positive en développement et sur test caché, stabilité autour des paramètres et absence de contradiction majeure entre sous-périodes.
- **Validée / défendable** : nombre de trades prospectifs fixé par un calcul de puissance, borne basse de l'IC supérieure à zéro, drawdown acceptable et coûts observés cohérents avec le scénario.

Réserves :
- Les intervalles doivent être calculés avec une méthode adaptée à la dépendance temporelle et aux trades regroupés ; ne pas supposer des observations indépendantes.
- La règle « perte au-delà de 0,25 % hors slippage » doit être clarifiée : le budget de 0,25 % s'applique au risque prévu au stop ; les dépassements dus au slippage doivent être rapportés et stressés, sans les confondre avec un risque initial mal dimensionné.
- Pour accumulation et swing, les baselines et métriques sont distinctes.
- « Validée » signifie uniquement défendable sur les données et la période testées, jamais garantie de rentabilité future.
- Le verdict « non concluant » doit être disponible lorsque l'échantillon ou la puissance sont insuffisants.

### Arbitrage provisoire consolidé
Principes qui convergent avec les autres audits :
- réduire les indicateurs redondants ;
- séparer les livres accumulation et swing ;
- définir l'exécution après clôture, éviter les fills au close rétrospectifs ;
- intégrer frais, spread et slippage pessimistes ;
- comparer à DCA et Buy & Hold ;
- utiliser une période cachée, walk-forward adapté et pré-enregistrement ;
- suivre MAE/MFE, durée d'immobilisation, taux de participation et occasions manquées ;
- distinguer un résultat négatif d'un résultat non concluant.

Divergences non résolues à arbitrer avec les données :
- noyau exact : SMA200 seule vs EMA50/200, RSI et ADX ;
- filtre BTC/BTC.D et force relative TEL/BTC ;
- maintien ou exclusion du 15m ;
- règles d'entrée précoce et nombre de confirmations ;
- tranches égales vs ATR-conditionnées ;
- seuils de coûts et critères de classification.

### Statut
Synthèse finale personnelle Claude reçue et archivée. Claude ne prétend pas avoir accès aux audits des autres ni avoir consulté TradingView dans sa session. Aucun résultat de backtest n'est ajouté. Aucune stratégie, script, board Smart View, alerte, paramètre, paper broker, compte ou ordre n'a été modifié.


# Audit opérationnel initial TradingView / MCP — 2026-11-09

## 1. Cadre et sécurité vérifiés
Lecture seule uniquement. Aucun ordre, aucune modification de stratégie, de board, d'alerte, de paramètre, de paper broker ou de compte n'a été effectué.

État du connecteur trader :
- Instrument autorisé : KRAKEN:TELUSD uniquement.
- Spot, levier brut maximal 1x.
- Risque maximal : 0,25 % par trade.
- Perte quotidienne maximale : 1 %.
- Maximum une position ouverte ; maximum un pari corrélé.
- Stop et cible obligatoires.
- R:R minimum de la politique : 1,51.
- Aucun trade réel ; le paper broker est le seul environnement de simulation.
- Trading agent activé dans le connecteur, mais cela ne modifie pas l'interdiction utilisateur d'exécuter des ordres réels ou automatiques.

Paper broker au contrôle :
- Capital initial : 1 000 USD.
- Cash et equity : 997,50 USD.
- P&L réalisé cumulé : -2,50 USD (-0,25 %).
- Position ouverte : aucune.
- Ordres en attente : aucun.
- Dernier trade historique : achat paper de 33 500 TEL à 0,001680 USD, puis stop paper à 0,00160546 USD le 2026-11-07 ; perte réalisée de 2,50 USD.

## 2. Boards et stratégies primaires recensés
Trois boards principaux ont une stratégie primaire sur KRAKEN:TELUSD :
1. **TEL/USD — Radar de retournement précoce** (9f6534d9-4eb8-4ded-a6ca-b694fb98dfd3) : stratégie primaire « TEL retournement confirmé 15m », écrite par le board. Le déclencheur dépend d'un CHoCH, MACD et volume relatif supérieur à 1,5× ; le volume par barre est signalé NON DISPONIBLE dans la lecture du board. La lecture est périmée et aucun setup n'est signalé.
2. **TEL/USDT — Aide à la décision** (06d9cdf8-29ff-4d79-8d1c-5b5b7d1ed0ad) : stratégie primaire « TEL Kraken – repli 4h dans tendance », écrite par le propriétaire. Toutes ses règles sont classées unsettled par le connecteur : aucun backtest de ses règles complètes n'est encore reconnu. Dernier signal enregistré : WATCH, pas SETUP ; ancien plan indicatif entry 0,00151475 / stop 0,00145996 / target 0,001578, R:R 1,15, inférieur au minimum de politique 1,51. Lecture périmée.
3. **TEL/USD — Smart View propre (test)** (27b3b625-b1c9-4c18-9109-8b8c1181b85c) : stratégie primaire « TEL/USD 4h — cassure du swing high en tendance ». Règles d'entrée et niveaux partiellement classés history_approx ; aucun setup signalé, lecture périmée.

Un quatrième board primaire recensé est basé sur MEXC:TELUSDT (911228ef-44d6-4de7-8841-a9f1b366ff93) : exclu de toute décision et de tout benchmark décisionnel, car l'instrument de référence autorisé est KRAKEN:TELUSD.

### Incohérence importante de carte
La carte trade_box du board « Aide à la décision » a rendu un plan SHORT (entry 0,00151475, stop 0,00160129, target1 0,0014247, target2 0,001383) alors que sa stratégie primaire est strictement LONG. Cette contradiction signifie que cette carte ne doit pas être utilisée comme plan d'ordre ni comme signal exploitable sans clarification. Aucun ordre n'a été placé.

### Historique de signaux disponible
Le connecteur indique que l'enregistrement des signaux ne commence que le 2026-11-03 :
- Radar 15m : 28 runs, 0 setup, 4 watch, 5 none ; 0 trade scoré.
- Repli 4h : 14 runs, 0 setup, 10 watch ; 0 trade scoré.
- Smart View test 4h : 12 runs, 0 setup, 2 watch, 1 none ; 0 trade scoré.
- Les données sont insuffisantes pour évaluer l'effet des filtres ; le connecteur retourne too_early.
Ne pas interpréter l'absence de setup enregistré avant le 3 novembre comme preuve qu'aucun signal n'a existé avant cette date.

### Quota de refresh
Les trois boards ont refreshes_left=0 et l'allocation hebdomadaire est consommée jusqu'au 2026-11-13. Leurs lectures stratégiques restent donc périmées. Les cartes ont pu être relues sans lancer un refresh complet ; aucune tentative de refresh supplémentaire n'a été faite.

## 3. Couverture OHLCV TradingView réellement observée
Appels en lecture seule sur KRAKEN:TELUSD :
- **1D** : 292 barres, première disponible le 2026-01-22, dernière barre 2026-11-09 en formation ; dernière clôture complète le 2026-11-08.
- **1W** : 43 barres, première disponible semaine du 2026-01-19 ; insuffisant pour calculer une SMA200 hebdomadaire.
- **4H** : 1 743 barres paginées, du 2026-01-22 au 2026-11-09 ; dernière clôture complète le 2026-11-08 à 20:00 UTC.
- **1H** : 1 000 barres dans la première page, du 2026-09-28 au 2026-11-09 ; has_more=true, historique plus ancien à paginer.
- Requêtes quotidiennes ciblées 2024-01-01 → 2024-12-31 et 2022-05-01 → 2022-12-31 : échec explicite « no bars », historique TradingView disponible commençant le 2026-01-22.

Conséquence : le test suggéré par Gemini sur 2024 et le test de régime 2022 suggéré par DeepSeek ne peuvent pas être faits avec l'historique OHLCV TradingView actuellement exposé. La couverture observée ne représente qu'environ neuf mois de données quotidiennes/4H et un seul contexte de marché ; elle ne permet pas de démontrer la robustesse multi-cycle. La date du premier bar TradingView ne prouve pas à elle seule la date officielle de listing de la paire.

### Derniers repères calculés sur bougies clôturées
- Dernière clôture journalière complète (8 novembre) : 0,001500 USD.
- Dernière clôture 4H complète (8 novembre 20:00 UTC) : 0,001500 USD.
- Dernière clôture 1H complète (9 novembre 01:00 UTC) : 0,001477 USD.
- Cotation screener TradingView lue séparément : 0,0014942 USD ; elle n'est pas horodatée dans le retour et n'est pas substituée aux clôtures OHLCV.
- SMA journalières calculées sur l'historique disponible : SMA50 ≈ 0,00169248 ; SMA200 ≈ 0,00201188. EMA20 ≈ 0,00152729 ; EMA50 ≈ 0,00161634 ; EMA200 ≈ 0,00197640. Le dernier close complet est sous ces moyennes.
- Snapshot technique TradingView : RSI 1D ≈47, ADX 1D ≈16,3 ; RSI 4H ≈44,7, ADX 4H ≈35,1 ; recommandations agrégées SELL sur 1D et 4H. Ces indicateurs sont un snapshot de contexte, pas un signal de trading validé.

### Niveaux du snapshot des cartes (pas un plan d'ordre)
Au prix de référence de carte 0,001503 :
- Supports affichés : POC 0,001490 ; niveau 0,001486 ; Fib 78,6 % 0,0014247 ; swing low 0,001383 ; VAL 0,001310.
- Résistances affichées : Fib 61,8 % 0,00151475 ; Fib 50 % 0,001578 ; swing high 0,001624 ; VAH 0,001670.
Ces niveaux sont ceux des cartes à data_as_of=2026-11-09T02:56:xxZ, pas des niveaux garantis en temps réel.

## 4. Benchmark exploratoire DCA vs Buy & Hold sur l'historique disponible
Calcul exploratoire à partir des bougies journalières TradingView, du 2026-01-22 au 2026-11-08 :
- DCA : 1 USD investi à l'ouverture de chaque lundi UTC disponible, 41 achats du 2026-01-26 au 2026-11-02 ; total investi 41 USD.
- Buy & Hold : 41 USD investis à l'ouverture de la première bougie disponible (0,0044 USD).
- Dernière clôture complète utilisée : 0,0015 USD.
- **Sans frais** : DCA ≈19 862,45 TEL, coût moyen ≈0,0020642 USD/TEL, valeur finale ≈29,79 USD, rendement ≈-27,33 %. Buy & Hold ≈9 318,18 TEL, coût d'entrée 0,0044 USD, valeur finale ≈13,98 USD, rendement ≈-65,91 %.
- **Scénario frais Tier 1 maker 0,40 % à chaque achat et à la liquidation** : DCA ≈-27,91 %, Buy & Hold ≈-66,18 %.
- **Scénario frais Tier 1 taker 0,80 % à chaque achat et à la liquidation** : DCA ≈-28,49 %, Buy & Hold ≈-66,45 %.

Limites majeures : calcul préliminaire sur bougies, prix d'ouverture du lundi utilisé comme proxy d'exécution DCA ; pas de spread, slippage, impact, file d'attente, non-exécution, frais de conversion ou retrait. Il ne s'agit ni d'un backtest de stratégie d'accumulation, ni d'une recommandation d'investissement, ni d'une preuve que le DCA battra Buy & Hold sur une autre période. Les frais de compte exacts ne sont pas connus.

## 5. Résultats des tests automatiques de fréquence déjà disponibles
Les tests automatiques du connecteur sur KRAKEN:TELUSD 4H, fenêtre d'environ 1 000 barres du 2026-05-26 au 2026-11-09, mesurent des fréquences d'événements, pas des trades complets nets de coûts :
- RSI oversold : n=17, 10 succès (58,8 %), taux de base 38,9 %, rendement médian à 20 barres +1,20 % ; échantillon faible.
- RSI croise sa moyenne : n=82, 36 succès (43,9 %) contre taux de base 38,9 %, rendement médian -0,77 %.
- Bollinger lower reentry : n=30, 30/30 (100 %), mais taux de base également 100 % ; le taux de réussite ne démontre donc aucun avantage prédictif.
- Gap up fill : n=19, 16 succès (84,2 %), rendement médian -0,08 %.
- Gap down fill : n=16, 11 succès (68,8 %), rendement médian -0,78 %.

Aucun de ces tests ne fournit une expectancy nette en R, profit factor, drawdown d'une stratégie exécutée, ou exécution réaliste. Ne pas classer ces résultats comme des stratégies rentables.

## 6. Recherches déjà en file
Demandes toujours en attente au dernier relevé :
- rq_4f665100b71f4f6a : backtest complet de la règle repli swing low 4H.
- rq_81fc211a3a43405b : comparaison A/B/C de variantes du repli 4H.
- rq_919a53432a114077 : clarification de la règle et du sizing du repli 4H.
- rq_3fbd24d7858c4e9e : sweep/réintégration 15m et 1H.
- rq_304062157ba54962 : cassure/retest 4H.
Ne pas créer de doublons ; vérifier ces demandes avant d'en soumettre de nouvelles.

## 7. Capacité Kraken — documentation officielle vérifiée, exécution non disponible ici
- La documentation Kraken indique que l'endpoint public Trades permet de récupérer l'historique Time & Sales depuis le premier trade, en paginant via le curseur last/since à précision nanoseconde et jusqu'à 1 000 trades par lot. Sources : https://support.kraken.com/articles/360029077772-python-code-to-retrieve-historical-time-and-sales-trading-history- et https://support.kraken.com/articles/advanced-api-faq
- L'endpoint public Depth renvoie un snapshot courant du carnet ; le flux WebSocket Kraken fournit un snapshot initial puis des mises à jour en temps réel. Ces sources documentent une capture prospective du carnet, pas un historique public de snapshots passés. Sources : https://support.kraken.com/articles/360000919986-public-endpoint-examples-you-can-try-them-directly-in-a-web-browser- et https://support.kraken.com/articles/360027821131-websocket-api-v1-how-to-maintain-a-valid-order-book
- L'endpoint AssetPairs permet de vérifier symboles, pair_decimals, lot_decimals, frais et minimum d'ordre : https://support.kraken.com/articles/360000920306-api-symbols-and-tickers
- Barème Kraken mis à jour le 2026-10-30 : Tier 1 Spot 0,40 % maker / 0,80 % taker ; le palier réel dépend du volume Spot 30 jours ou des actifs détenus sur Kraken, selon le meilleur palier. Source : https://support.kraken.com/articles/cross-platform-fee-tier-changes
- **Limite de l'environnement actuel** : aucun connecteur Kraken API direct n'est exposé parmi les outils disponibles dans cette session. Les appels directs aux URL API Kraken n'ont pas été accessibles via le lecteur Web. Nous avons donc vérifié la documentation, mais pas extrait les trades bruts, le carnet courant, le tick size exact ou le palier de frais individuel. Ne pas prétendre que ces données ont été mesurées.

## 8. Décisions de recherche et prochaines actions
1. Garder tous les boards et toutes les règles inchangés ; ne pas utiliser le plan SHORT incohérent comme signal.
2. Attendre les recherches déjà en file sur les setups complets ; ne pas confondre tests automatiques de fréquence et backtests de stratégie.
3. Définir le protocole sur la couverture disponible, et marquer 2024/2022 comme indisponibles dans TradingView MCP.
4. Vérifier si un accès public Kraken peut être ajouté à l'environnement de recherche existant pour paginer Time & Sales et relever AssetPairs/Ticker/Depth ; sinon conserver un scénario de coûts pessimiste et commencer une collecte prospective de carnet seulement si une voie autorisée existe.
5. Ne jamais supposer que le carnet historique peut être reconstruit à partir des seules transactions.
6. Pré-enregistrer les règles et réserver une période cachée avant tout test confirmatoire.
7. Mesurer séparément accumulation (TEL accumulés par dollar, coût moyen, exposition immobilisée) et swing (R net, expectancy, PF, DD, MAE/MFE, durée, fills).
8. Comparer au DCA et Buy & Hold avec mêmes cashflows et coûts.
9. Autoriser le verdict « non concluant » si l'historique ou le nombre de trades ne suffit pas.

## Statut
Audit opérationnel initial effectué en lecture seule. Données partielles et limites documentées. Aucun ordre réel ou paper supplémentaire ; aucun compte Kraken réel consulté ; aucune stratégie, règle, board, alerte, paramètre ou paper broker modifié.


### Addendum vérifié — date de lancement du marché Kraken TEL/USD
Kraken a annoncé officiellement que le trading TEL sur Kraken était en ligne le **22 janvier 2026**. Source officielle : https://blog.kraken.com/product/asset-listings/tel-is-available-for-trading

Conséquence importante : il n'existe pas d'historique de transactions KRAKEN:TELUSD sur Kraken pour 2024 ni pour mai–décembre 2022, puisque le marché n'était pas encore ouvert. Les tests proposés sur ces périodes ne sont donc pas simplement absents du flux TradingView : ils sont impossibles sur cet instrument exact. Ne pas les remplacer par MEXC, KuCoin ou un autre exchange, car cela changerait le marché testé. La fenêtre historique de référence possible commence au lancement du marché, le 2026-01-22, sous réserve de la complétude des données réellement récupérables.


# Résultats de recherche opérationnelle — backtests indépendants préliminaires — 2026-11-09

## État du marché
Données TradingView en lecture seule :
- Cotation screener KRAKEN:TELUSD : 0,0014962 USD, variation -0,439 % ; volume screener non disponible.
- Dernière clôture 1D complète : 0,001500 USD (2026-11-08 00:00 UTC).
- Dernière clôture 4H complète : 0,001500 USD (2026-11-08 20:00 UTC).
- RSI 1D 47,11 ; ADX 1D 16,30. RSI 4H 44,73 ; ADX 4H 35,12.
- Prix sous SMA200 1D (~0,00200 USD), EMA20 1D (~0,001521), EMA50 1D (~0,001607), EMA200 1D (~0,002023).
- En 4H, prix sous EMA20 (~0,001554) et EMA50 (~0,001512), malgré EMA20 > EMA50.
- Recommandation agrégée TradingView : SELL en 1D et 4H.
Décision de recherche : ATTENDRE, aucun setup long confirmé. Les boards sont stale ; quota de refresh épuisé jusqu'au 2026-11-13. Aucun refresh forcé ni ordre.

## Backtest indépendant — cassure swing high 4H
Règles du board conservées : pivot high confirmé 5/5, clôture croise au-dessus, close au-dessus EMA20/EMA50, entrée open suivant, stop 1,5 ATR, cible 3 ATR, expiration 20 barres. OHLCV : 1 742 bougies 4H clôturées du 2026-01-22 12:00 au 2026-11-08 20:00 UTC. Signaux dédupliqués, trades non chevauchants, stop prioritaire en collision. Découpage chronologique 70/30, date de coupure 2026-08-13 20:00 UTC. Coût principal : taker Tier 1 0,80 % par côté + hypothèse de slippage 0,10 % par côté.
- Total : 23 trades, 8 positifs, 15 négatifs ; 13 stops, 8 targets, 2 expirations.
- Expectancy nette : -0,237 R/trade ; PF 0,696.
- Développement : 15 trades, 3 gagnants, expectancy -0,624 R, PF 0,331.
- Holdout chronologique : 8 trades, 5 gagnants, expectancy +0,491 R, PF 2,00.
- Sizing au risque 0,25 % d'equity par trade, frais inclus dans le stop et exposition plafonnée à 1x : 1 000 USD devient 985,51 USD (-1,20 %) sur la série ; développement -1,87 %, holdout +0,68 %.
Sensibilité : maker 0,40 % par côté + 0,10 % slippage : expectancy -0,087 R, PF 0,876. Taker + 0,20 % slippage par côté : expectancy -0,274 R, PF 0,658.
Conclusion : pas prometteuse à ce stade. Le holdout positif ne contient que 8 trades et contredit le développement négatif ; résultat global négatif même sous scénario maker.

## Backtest indépendant — repli 4H
Pour rendre le test calculable, proxy explicite : touche EMA20 dans les 5 bougies précédentes, bougie signal haussière et close au-dessus EMA20/EMA50, entrée open suivant ; stop sous dernier pivot low 5/5 moins 0,5 ATR ; cible dernier pivot high au-dessus de l'entrée uniquement si R:R brut >=1,51. Cette approximation n'encode pas complètement l'ancienne résistance devenue support.
Sous taker 0,80 % par côté + 0,10 % slippage par côté :
- 9 trades, 1 gagnant, 8 perdants ; 4 stops, 1 target, 4 expirations.
- Expectancy -0,775 R/trade ; PF 0,162.
- Développement : 7 trades, expectancy -0,768 R, PF 0,200.
- Holdout : 2 trades, 0 gagnant, expectancy -0,800 R.
- Sizing 0,25 % du capital au stop, frais inclus : rendement théorique -1,25 %.
Conclusion : résultat défavorable mais échantillon trop petit et proxy incomplet ; aucune modification de règle.

## Repli swing low 4H — pivot 10/10
Implémentation stricte du protocole en file : pivot low 10/10 confirmé, clôture dans la zone swing low à swing low +0,3 ATR, close > EMA20, ADX14 >=20, stop 0,5 ATR sous le swing low, cible 1,5 ATR, entrée open suivant, expiration 20 barres. Seulement 2 trades sur la période ; aucun dans le holdout. Non concluant. La recherche TradingView rq_4f665100b71f4f6a et la comparaison A/B/C rq_81fc211a3a43405b restent en attente.

## Sweep / réintégration — prototype 15m et 1H
Définition de cette première passe : support = dernier pivot low confirmé 5/5 ; sweep = low sous le support, close au-dessus, close précédent >= support ; entrée open suivant ; stop = extrême du sweep moins 0,25 ATR ; cible = dernier pivot high 5/5 au-dessus de l'entrée ; signaux dédupliqués, trades non chevauchants, 20 barres max, stop prioritaire en collision. Coûts : taker 0,80 % par côté + 0,10 % slippage par côté. Le stop 0,25 ATR est une hypothèse de prototype, pas une règle adoptée.
Données : 15m = 5 533 bougies clôturées du 2026-09-01 au 2026-11-09 02:30 UTC ; 1H = 5 999 bougies clôturées du 2026-02-25 au 2026-11-09 01:00 UTC.
- 15m sans filtre volume : 67 trades, 8 positifs, expectancy -0,710 R, PF 0,076, rendement moyen net/trade -1,79 %.
- 15m avec volume >1,5× moyenne 20 : 40 trades, 7 positifs, expectancy -0,571 R, PF 0,108.
- 15m avec volume >1,5× et R:R initial >=1,51 : 33 trades, 7 positifs, expectancy -0,591 R, PF 0,130.
- 1H sans filtre volume : 118 trades, 19 positifs, expectancy -0,620 R, PF 0,187, rendement moyen net/trade -1,92 %.
- 1H avec volume >1,5× : 59 trades, 14 positifs, expectancy -0,524 R, PF 0,196.
- 1H avec volume >1,5× et R:R initial >=1,51 : 36 trades, 6 positifs, expectancy -0,665 R, PF 0,187.
Lecture : prototype fortement pénalisé par les coûts et le stop serré ; plusieurs targets touchés restent négatifs nets. Cela n'invalide pas toute stratégie de sweep, mais ce prototype n'est pas prometteur. Les variantes sont des diagnostics de sensibilité, pas une optimisation adoptée.

## Coûts Kraken
Barème officiel Tier 1 : maker 0,40 % / taker 0,80 % par exécution. Le palier réel du compte reste inconnu. Avec slippage supposé de 0,10 % par côté, mouvement de break-even mécanique approximatif : +1,82 % en taker, +1,01 % en maker, avant spread et impact additionnels. Ce n'est pas une mesure du spread.
Source officielle : https://support.kraken.com/articles/cross-platform-fee-tier-changes

## Limites statistiques
OHLCV ne simule pas le carnet, le spread historique, la file d'attente, l'impact ou les non-fills. Les frais proviennent du barème Tier 1 ; slippage 0,10 % par côté = hypothèse. Stop/target simulés sur bougies, collisions stop d'abord. Les trades sont dépendants ; un bootstrap par blocs et des intervalles adaptés seront nécessaires. Le holdout 30 % a maintenant été consulté : il ne peut plus servir de période cachée pour de nouveaux réglages. Il faut réserver une nouvelle période prospective sans modifier les règles. Historique KRAKEN:TELUSD disponible seulement depuis le listing Kraken du 2026-01-22, donc pas de test multi-cycle sur cette paire.

## État paper et décisions
État vérifié : equity 997,50 USD, cash 997,50 USD, P&L réalisé -2,50 USD, aucune position, aucun ordre en attente. Risque maximal 0,25 %/trade, perte quotidienne 1 %, une position max, levier 1x, R:R min 1,51, stop et cible obligatoires. Dernier stop paper 2026-11-07 11:59 UTC ; cooldown 240 min écoulé.
Demandes TradingView toujours queued : rq_4f665100b71f4f6a, rq_81fc211a3a43405b, rq_3fbd24d7858c4e9e, rq_304062157ba54962, rq_919a53432a114077. Ne pas créer de doublons.
Aucun setup validé. Backtests cassure/repli défavorables ou insuffisants ; sweep prototype très négatif sous les coûts et le stop testés. Aucun changement de stratégie, board, règle, alerte, compte ou ordre.


---

# Complément de recherche — vérification des accès et tests automatiques du 2026-11-09

## Vérification des données TradingView MCP

Accès lecture seule testé sur `KRAKEN:TELUSD` :
- 1D : 292 bougies disponibles depuis la cotation ; dernière clôture rapportée 0,001506 USD.
- 4H : 1 743 bougies disponibles, sans page antérieure supplémentaire dans ce flux ; dernière clôture rapportée 0,001511 USD.
- 1H : première page de 5 000 bougies disponible, pagination antérieure annoncée ; fenêtre de la page affichée à partir du 2026-04-11.
- 15m : première page de 5 000 bougies disponible, pagination antérieure annoncée ; fenêtre de la page affichée à partir du 2026-09-08.
- Les réponses indiquent que la dernière bougie peut être en formation. Ne pas traiter cette dernière bougie comme une clôture confirmée.
- Les nombres de pages 1H/15m ne sont pas des historiques complets : poursuivre la pagination avant toute étude qui exige la couverture entière.

Le compte TradingView MCP permet donc de continuer des tests historiques sur 4H, 1H et 15m, mais les historiques intraday restent bornés par le flux et la pagination. L'archive officielle publique Kraken constitue une source complémentaire importante : fichiers OHLCVT de 1, 5, 15, 60, 240, 720 et 1440 minutes, du premier échange de chaque paire au 30 septembre 2026 dans la version documentée du 2 novembre 2026. Les données sont sans authentification ; les intervalles sans transaction sont absents, et non remplis artificiellement. Les bougies 1m/5m et les champs de nombre de trades peuvent enrichir les tests, mais il faut contrôler les trous et les conventions de bougies.
Source officielle : https://support.kraken.com/fr/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data

Les données publiques de marché Kraken (ticker, carnet L2, trades et OHLCV) ne nécessitent pas de clé privée. Une clé privée n'est pas le préalable aux backtests. Elle n'est utile que pour des données personnelles du compte et nécessite une intégration compatible distincte. Décision : ne pas créer la clé privée à ce stade.

## Tests historiques automatiques TradingView — 4H

Tests de fréquence / comportement, et non backtests de trades nets de frais :
- Bollinger lower re-entry : 30 succès / 30 cas évaluables, taux 100 %, IC95 88,6–100 %, taux de base 100 %, rendement médian prospectif rapporté +1,58 %, 1 cas encore en attente. Le taux de base étant déjà 100 %, aucun avantage prédictif n'est démontré.
- RSI croise au-dessus de sa moyenne : 36/82, taux 43,9 %, IC95 33,7–54,7 %, taux de base 38,9 %, rendement médian prospectif -0,77 %. Écart au taux de base faible et rendement médian négatif.
- RSI survendu (RSI < 30) : 10/17, taux 58,8 %, IC95 36,0–78,4 %, taux de base 38,9 %, rendement médian +1,20 %. Échantillon faible (n=17), non concluant.
- Gap haussier comblé : 16/19, taux 84,2 %, IC95 62,4–94,5 %, rendement médian -0,08 %. Petit échantillon ; événement de comblement intrabar, pas une stratégie.
- Gap baissier comblé : 11/16, taux 68,8 %, IC95 44,4–85,8 %, rendement médian -0,78 %. Petit échantillon ; pas d'avantage établi.

Définitions et limites : la réintégration Bollinger mesure un retour à l'intérieur de la bande dans les 20 bougies après une clôture extérieure ; le taux de base de 100 % rend le taux de succès inutilisable comme preuve d'edge. Les tests RSI/gaps mesurent des fréquences et rendements prospectifs, sans entrée exécutable, stop, cible, frais, spread, slippage ou non-fill. Ne pas adopter ces signaux comme stratégies.

## État du système relu

- Politique de risque lue : 0,25 % de risque max par trade, perte journalière 1 %, une position ouverte max, un pari corrélé max, levier brut max 1x, stop et cible obligatoires, R:R minimal 1,51, symbole autorisé KRAKEN:TELUSD.
- État Paper Trading : equity/cash 997,50 USD, P&L réalisé -2,50 USD, aucune position ouverte, aucun ordre en attente. Dernier trade : achat paper 33 500 TEL à 0,001680 USD le 2026-11-06, stop paper à 0,00160546 USD le 2026-11-07.
- Quatre boards primaires restent identifiés, dont le board MEXC qui est exclu de la recherche décisionnelle. La stratégie de repli 4H reste avec règles « unsettled » ; le board cassure 4H contient des approximations de structure ; le radar 15m contient également des règles approximatives.
- Demandes déjà en attente, ne pas dupliquer : rq_4f665100b71f4f6a (repli swing low 4H), rq_81fc211a3a43405b (variantes repli 4H), rq_3fbd24d7858c4e9e (sweep/reclaim 15m/1H), rq_304062157ba54962 (cassure/retest 4H), rq_919a53432a114077 (clarification règles et sizing).
- Aucun refresh de board, changement de stratégie, modification de règle, alerte ou ordre n'a été effectué pendant cette vérification.

## Conclusion de ce complément

L'accès OHLCV TradingView est suffisant pour poursuivre l'analyse et certains backtests, mais ne suffit pas à lui seul pour toutes les validations microstructurelles. Priorité suivante : exploiter l'archive OHLCVT officielle Kraken pour KRAKEN:TELUSD, vérifier les trous et le nombre de trades, puis construire des simulations d'exécution prudentes avec frais, spread/slippage documentés et non-fills. Garder une nouvelle période prospective intacte ; le holdout déjà consulté n'est plus un holdout vierge. Aucune stratégie n'est validée.
