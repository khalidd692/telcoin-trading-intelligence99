# Radar TEL/USD et confirmation

Le radar réutilise les bougies Kraken clôturées, les pivots confirmés et les zones Smart View du terminal. Les quatre unités doivent être disponibles et les clôtures alignées, avec un segment final continu. Les garde-fous de fraîcheur restent ceux du terminal. La cotation instantanée sert à évaluer un plan et ses coûts, indépendamment du radar technique.

Sur la dernière clôture 15 min, une **alerte précoce non confirmée** demande deux familles de facteurs.

- Une réaction de prix. Cassure haussière d’un pivot confirmé, rebond avec clôture au-dessus du support pivot préexistant ou réaction au bord supérieur d’une zone haussière préexistante (FVG ou OB estimé).
- Au moins un appui. Volume ≥ 1,5 fois la moyenne des 20 bougies précédentes, divergence RSI14, reprise de l’EMA20 ou du VWAP dans la même session UTC, ou clôtures 15 min et 1 h au-dessus de leur EMA20. Le 4 h est affiché comme troisième degré de convergence. Le radar retient les bougies 1 h et 4 h déjà clôturées à la clôture 15 min analysée. La divergence compare les minima de clôture de deux fenêtres de cinq bougies et les RSI horodatés correspondants.

Cette règle de surveillance ne dépend pas du RR et ne mesure ni probabilité ni rentabilité. Elle ne modifie pas les seuils de scénario. Les zones et pivots testés existaient avant la bougie de réaction. Un RSI seul ne déclenche rien.

La confirmation réutilise le statut `PRÊT À ÉVALUER` d’un scénario de confirmation, ses conditions techniques et son RR net ≥ 1,5. Des frais personnels, la profondeur du carnet et les autres contrôles du scénario peuvent bloquer cette validation. Le terminal public ne dispose pas des frais personnels ni de la profondeur pour la taille envisagée. Un scénario conditionnel garde son RR théorique, ses hypothèses de coûts et ses motifs de blocage.

Une invalidation est possible sur la clôture 4 h sous le support du moteur ou sur la clôture 15 min suivant immédiatement une alerte 15 min, sous son niveau d’invalidation. L’évaluation de cette alerte précédente exclut les clôtures 1 h et 4 h postérieures. L’invalidation structurelle 4 h a priorité.

Les événements structurés `EARLY_ALERT`, `CONFIRMATION` et `INVALIDATION` portent un identifiant stable par marché, type et clôture. Le journal d’évaluation existant enregistre les changements et peut les exposer aux consommateurs. Les observations du journal restent ponctuelles et leur rendement mesure uniquement des variations de prix. Aucune réception push ni performance de stratégie ne découle de ces événements.
