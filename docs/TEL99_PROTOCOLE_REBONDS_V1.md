# TEL99 — protocole prospectif des rebonds v1

Le critère principal validé par l'utilisateur est une hausse d'au moins 5 % en 24 heures après une clôture Kraken TEL/USD 15 minutes. Les seuils de 2 %, 3 % et 10 % sont descriptifs. Les calculs n'agissent jamais sur les alertes, les achats ou le risque.

## Préenregistrement et données

Au premier passage valide, le journal enregistre un protocole immuable `tel99-rebounds-v1` et fixe son début à une clôture 15 minutes future, au minimum une bougie après le passage. Aucune période antérieure ne sert à mesurer ce protocole. Les prix proviennent des clôtures 15 minutes Kraken TEL/USD validées par le collecteur ; le journal conserve la première valeur observée sans modifier les observations originales. Une fenêtre avec bougie manquante n'est pas évaluée.

## Épisodes

Pour chaque seuil séparément, parcourir les clôtures possibles par ordre chronologique. Une fenêtre est évaluée uniquement lorsque les 96 clôtures suivantes sont disponibles. Si au moins une clôture atteint le seuil avant ou à 24 h, retenir cette fenêtre comme un épisode ; écarter les nouveaux départs jusqu'à sa fin de 24 h incluse. C'est une règle déterministe de regroupement, pas une recherche du meilleur creux. On ne classe ni un épisode ni une absence avant maturité.

## Attribution et limites

Une alerte précoce est pertinente si elle a été effectivement enregistrée entre 60 minutes avant le départ et le départ inclus, temps d'observation faisant foi. Une alerte enregistrée après le départ n'est pas attribuée en avance, mais son retard est mesuré séparément si elle arrive avant la première clôture au seuil. L'avance médiane des alertes attribuées est aussi publiée.

Si aucune alerte pertinente n'existe, classer l'épisode « manqué » seulement si les quatre clôtures précédant le départ ont chacune une observation radar valide, reçue au plus tard une bougie après leur clôture et avant le départ. Sinon, classer « indéterminé » ; ne jamais déduire une absence d'alerte d'un trou de surveillance. La proportion détectée ne prend pour dénominateur que les épisodes détectés ou manqués dont l'attribution est connue.

Une alerte précoce est un faux positif descriptif si, après son heure d'observation, aucune clôture n'atteint +5 % du prix de clôture connu à l'alerte pendant les 24 heures suivantes, toutes les clôtures étant présentes. Une alerte non mûre ou à historique incomplet n'est pas comptée comme fausse. Cette convention ne prouve ni une erreur de trading ni un résultat financier.

Le protocole est fixé avant les observations évaluées. Les champs publiés sont des variations de marché, non des opérations. Les données insuffisantes et la faible taille de l'échantillon interdisent toute validation de stratégie.
