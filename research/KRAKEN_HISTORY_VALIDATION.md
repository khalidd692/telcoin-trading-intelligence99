# Historiques Kraken TEL/USD validés — 10 novembre 2026

Les CSV bruts sont repris **sans modification** de la branche
`research/tel-discovery-unrestricted`, commit
`399982eebe753a557978af18ab2d826b7faca14a`. Les exports 5591/6798/1748 lignes
remplacent, pour ce chantier, les exports 5000 lignes plus courts : aucun
assemblage ni téléchargement de marché. Le manifeste conserve chemin Git,
commit, marché déclaré, fournisseur et SHA-256 de chaque fichier. Il enregistre
aussi le CSV 4h historique utilisé par le runner existant.

La source est **TradingView MCP, instrument KRAKEN:TELUSD**. Le hash garantit
l'intégrité par rapport au dépôt ; il ne constitue pas une confirmation des
prix par une seconde source Kraken officielle. La mèche suspecte reste à
vérifier à la source, et n'est pas corrigée arbitrairement.

## Reproduction hors réseau

```sh
python -m scripts.strategy_backtest.history_quality --as-of 2026-11-10T00:00:00Z
python -m unittest tests.test_kraken_history_quality tests.test_strategy_engine tests.test_strategy_phase_continuity tests.test_strategy_phase_risk
python -m unittest discover -s tests
```

Sorties dans `results/kraken_history/` : CSV valides, provenance de chaque CSV,
quarantaine avec valeurs brutes/numéro de ligne/motifs, rapport JSON détaillant
**toutes** les ruptures et périodes continues. Les fins sont exclusives et
correspondent à la clôture de la dernière bougie utilisable.

| TF | Lignes brutes | Valides | Anomalies de prix | Dernière bougie exclue | Ruptures internes | Bougies absentes | Segments |
|---|---:|---:|---:|---:|---:|---:|---:|
| 15m | 5591 | 5590 | 0 | 1 | 801 | 1116 | 802 |
| 1h | 6798 | 6796 | 1 | 1 | 166 | 193 | 167 |
| 4h | 1748 | 1746 | 1 | 1 | 1 | 1 | 2 |

Aucun doublon, OHLC incohérent, volume négatif, timestamp invalide ou prix
non fini dans ces trois snapshots. Les ruptures internes sont comptées entre
bougies retenues ; les exclusions au début ou à la fin ne créent pas de trou
interne. Ici les ruptures existaient déjà dans les sources. Un intervalle sans
bougie peut correspondre à une absence de transactions ; il reste une rupture,
sans interpolation ni invention d'une bougie plate.

## Périodes continues effectivement disponibles (UTC)

| TF | Étendue des données retenues (fragmentée) | Plus longue période continue | Bougies de cette période |
|---|---|---|---:|
| 15m | 2026-09-01 00:00 → 2026-11-09 20:30 | 2026-09-28 11:00 → 2026-09-29 23:30 | 146 |
| 1h | 2026-01-22 15:00 → 2026-11-09 20:00 | 2026-09-22 04:00 → 2026-10-11 05:00 | 457 |
| 4h | 2026-01-22 16:00 → 2026-11-09 20:00 | 2026-01-23 00:00 → 2026-11-09 20:00 | 1745 |

Le premier segment 4h ne contient qu'une bougie et ne permet pas de signal.
Un segment valide ne garantit pas assez de barres pour l'amorçage des
indicateurs et l'horizon complet : le moteur conserve ses exclusions existantes.

## Politique de validation

- Marché/provenance déclarés et hash obligatoires pour charger un historique
  dans le simulateur. Un fichier modifié ou inconnu est refusé.
- Timestamps explicitement UTC, alignés sur la grille du timeframe, ordonnés ;
  toutes les copies d'un doublon et les deux côtés d'une inversion sont exclus.
- Prix finis et strictement positifs, volume fini non négatif, low ≤ open/close
  ≤ high. Volume nul autorisé.
- Ratio mèche/corps supérieur à 3 ou saut entre clôtures adjacentes supérieur
  à 3 : quarantaine conservatrice, sans correction. Ce seuil de qualité ne
  modifie aucune règle de signal, d'admission ou de risque.
- La mèche 1h à 0,020000 du 22 janvier 14:00 et son agrégat 4h à 12:00 sont
  mis en quarantaine. Leurs valeurs originales restent dans les CSV bruts.
- Dernière bougie de chaque export exclue : la clôture au moment de la capture
  n'est pas attestée. Attendre aujourd'hui ne transforme pas un snapshot
  potentiellement partiel en bougie finale. Le cutoff source reste figé ;
  `--as-of` peut uniquement le réduire.

## Entrée du moteur existant

```python
from scripts.strategy_backtest import engine as E
bars = E.load_csv('results/kraken_history/4h_valid.csv')
segments = E.build_segments(bars, E.Params())
```

Le chemin brut enregistré fonctionne aussi : `load_csv` applique automatiquement
la même quarantaine. Les exports valides ont un sidecar de provenance/hash et
sont recontrôlés lors du chargement. `history_quality.load_history` fournit les
observations UTC et segments pour les trois timeframes. Le simulateur de
stratégie existant reste explicitement **4h** ; il refuse un CSV 1h/15m au lieu
de changer silencieusement le sens des paramètres.

`build_segments` réamorce les indicateurs à chaque rupture. Construire un
`Segment` discontinu ou non UTC est refusé. Les fenêtres de signal, pivots et
sortie restent locales au segment ; un horizon incomplet est exclu, même si un
candidat préfabriqué a été transmis directement au runner. Aucune position ne
traverse une rupture. La continuité du capital et des limites de risque entre
IS/VAL/OOS reste conservée ; les frontières de phase ne sont pas des trous.

Le runner historique continue d'utiliser son fichier 4h enregistré, désormais
validé au chargement. Ses anciens résultats n'ont pas été régénérés et doivent
être recalculés avant toute comparaison après quarantaine. Aucun nouveau
résultat de performance n'est revendiqué ici. La découverte précoce, le filtre
R d'admission paper, Smart View, les stratégies et les risques sont inchangés.

Prochaine priorité : confirmer la mèche et la clôture finale auprès d'une source
Kraken attestée, puis réexécuter le protocole figé sur le long segment 4h validé.
