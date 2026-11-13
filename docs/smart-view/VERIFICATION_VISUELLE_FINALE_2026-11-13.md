# TEL99 — Vérification visuelle finale Smart View — 13/11/2026

> **Source :** inspection navigateur TinyFish en lecture seule du board officiel, run `b79d0549-b3df-4083-b951-87538d137f3f`. https://agent.tinyfish.ai/runs/b79d0549-b3df-4083-b951-87538d137f3f. Les constatations ci-dessous proviennent du compte rendu de l'agent navigateur ; **elles ne sont pas des calculs indépendants ni un export brut du moteur**. Ne pas modifier les règles, widgets, observateurs, branches ou journaux ; ne pas passer d'ordre.

## Découverte centrale : Rule Scan a un rendu booléen VISUEL
- 21 widgets visibles, emplacement « Add widget » vide.
- Rule Scan : des cercles verts/rouges par condition et symbole sont visibles dans le tableau, contrairement aux deux précédentes extractions textuelles qui ne remontaient que des prix.
- Alerte précoce (6 conditions) : **0 matches complets** affichés.
- Invalidation (5 conditions) : **2 matches complets**, rapportés pour BTCUSD et ETHUSD.
- **Anomalie du relevé :** l'agent navigateur a écrit « TELUSD 1/6 » mais aussi « 2 verts / 4 rouges » pour l'alerte précoce. Ces chiffres sont contradictoires. **Ne pas enregistrer de compte fiable par condition TEL sans nouvelle capture horodatée.** Pour TEL invalidation « 4/5 » était inféré et non lu explicitement ; ne pas traiter comme preuve.
- Aucun export CSV/PDF, valeur numérique par condition, log d'erreur ou horodatage exact par condition trouvé.
- **Conclusion corrigée :** absence de booléens dans les données rendues à Copilot ≠ absence de booléens dans l'interface graphique ; le Rule Scan peut afficher des correspondances. Cela ne démontre pas à lui seul la justesse de son calcul ni la cause de l'ancien manque.

## Autres constatations
- Technical Gauge RSI visuel 48.63 et MACD Neutral, sans horodatage absolu par condition. Dashboard « Updated 5 min ago » ; ne pas assimiler ce délai relatif à un timestamp fiable de barre clôturée.
- SMC : FVG baissier 0.001453–0.001468 ; OB haussier 0.001310–0.001329, **niveaux historiques de ce rendu uniquement**.
- Volume Profile : POC 0.001608, VAH 0.001725, VAL 0.001438 ; ne pas en déduire l'algorithme propriétaire.
- Pattern Scanner : « 0 of 1 », « No pattern near its trigger » ; ce rendu diffère du précédent `degraded:no_rows`, donc ne pas considérer l'état antérieur comme permanent.
- Setup Stats : « Too few signals », cinq signaux fermés en 1D ; pas de liste individuelle/export visible.
- Market Snapshot : toujours vide (« No market breadth data / Market data unavailable »).
- Watchlist 18 symboles ; My Alerts affiche **7 alertes actives**. **Attention :** ces alertes TradingView ne sont pas nécessairement les deux observateurs `w15`/`w1h` signalés `skipped_plan` ; ne pas confondre ni affirmer que les observateurs fonctionnent. Le rapport navigateur ne vérifie pas leurs exécutions effectives.
- News sentiment visuel : 92 % négatif / 1 % neutre / 7 % positif, source et période à vérifier avant exploitation.
- Seasonality indique « 5 ans » comme paramètre de fenêtre, **pas cinq années complètes de données**.

## Contrôles à effectuer dans TEL99
1. Rejouer les 11 expressions exactes documentées dans `PASSATION_SMART_VIEW_2026-11-13_FINAL.md` sur bougies Kraken horodatées et clôturées ; enregistrer les 11 booléens, les valeurs intermédiaires et les timestamps.
2. Comparer aux observations visuelles **uniquement sur le même instant/barre** ; les comptes historiques ne sont pas un jeu de vérité terrain.
3. Ne pas convertir les correspondances Rule Scan en « achat confirmé » : vérifications indépendantes de frais, spread, profondeur, risque et RR net.
4. Continuer la collecte et la mesure prospective des alertes précoces, faux négatifs et rebonds non détectés.
5. Préserver les trois passations antérieures et cette quatrième note. Lire issue #60 et issue #61 avant modification.

## Verdict
Le contrôle visuel a permis de récupérer **une information utile nouvelle** (les booléens existent dans le rendu visuel du Rule Scan). **Aucun accès à l'algorithme propriétaire, aux historiques détaillés ou aux exports individuels n'a été trouvé.** Le développement TEL99 ne dépend plus de Smart View ; conserver l'abonnement n'est pas nécessaire pour reproduire les formules publiques. La décision de résilier dépend aussi des autres usages TradingView et des 7 alertes affichées.
