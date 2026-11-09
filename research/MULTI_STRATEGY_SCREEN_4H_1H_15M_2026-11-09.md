# Criblage multi-stratégies KRAKEN:TELUSD — 09/11/2026

## Données
- 4h: 1748 bougies, 2026-01-22T12:00:00.000Z → 2026-11-09T20:00:00.000Z
- 1h: 5000 bougies, 2026-04-12T17:00:00.000Z → 2026-11-09T20:00:00.000Z
- 15m: 3000 bougies, 2026-10-03T14:45:00.000Z → 2026-11-09T20:45:00.000Z

## Moteur
Signal à la clôture, entrée à l'ouverture suivante, une position à la fois par stratégie. Stop sous le plus bas des cinq bougies précédentes et du signal, marge 0,05 ATR, risque borné 0,8–2 ATR; cible 2R; stop prioritaire; gap de données clôture le trade. Durée max 20 bougies 4h, 48 bougies 1h, 96 bougies 15m. Frais stress: 1,9% aller-retour (0,80% taker + 0,15% slippage par côté). Slippage hypothétique. Split chronologique 60/40. Pas d'optimisation.

## Résultats
| TF | Stratégie | Signaux | Trades | Win % | Moyenne nette % | PF | OOS n | OOS moyenne % |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 4h | BB_reentry | 42 | 37 | 37.8 | -0.954 | 0.66 | 23 | -1.407 |
| 4h | RSI30_recovery | 68 | 54 | 35.2 | -1.576 | 0.54 | 29 | -0.898 |
| 4h | EMA20_pullback_trend | 26 | 17 | 29.4 | -2.08 | 0.49 | 4 | 2.284 |
| 4h | Donchian20_volume_breakout | 24 | 17 | 35.3 | -2.292 | 0.6 | 10 | -1.016 |
| 4h | Sweep10_reclaim | 125 | 74 | 33.8 | -1.393 | 0.57 | 35 | -0.657 |
| 4h | MACD_bull_cross | 63 | 53 | 50.9 | 0.868 | 1.3 | 26 | 0.86 |
| 1h | BB_reentry | 147 | 137 | 32.1 | -1.492 | 0.32 | 57 | -0.73 |
| 1h | RSI30_recovery | 202 | 164 | 29.3 | -1.696 | 0.28 | 72 | -1.095 |
| 1h | EMA20_pullback_trend | 98 | 61 | 34.4 | -1.119 | 0.56 | 27 | -1.152 |
| 1h | Donchian20_volume_breakout | 86 | 54 | 35.2 | -1.4 | 0.54 | 28 | -0.805 |
| 1h | Sweep10_reclaim | 341 | 222 | 26.1 | -1.752 | 0.21 | 88 | -1.825 |
| 1h | MACD_bull_cross | 194 | 154 | 33.8 | -1.35 | 0.44 | 63 | -1.018 |
| 15m | BB_reentry | 86 | 81 | 12.3 | -1.676 | 0.06 | 30 | -1.761 |
| 15m | RSI30_recovery | 99 | 90 | 12.2 | -1.705 | 0.06 | 38 | -1.791 |
| 15m | EMA20_pullback_trend | 62 | 48 | 14.6 | -1.725 | 0.14 | 19 | -1.891 |
| 15m | Donchian20_volume_breakout | 43 | 28 | 32.1 | -1.448 | 0.27 | 15 | -1.955 |
| 15m | Sweep10_reclaim | 131 | 107 | 10.3 | -1.785 | 0.03 | 45 | -1.903 |
| 15m | MACD_bull_cross | 92 | 90 | 14.4 | -1.727 | 0.09 | 37 | -2.119 |

## Détail JSON
```json
{
  "4h": {
    "bars": 1748,
    "from": "2026-01-22T12:00:00.000Z",
    "to": "2026-11-09T20:00:00.000Z",
    "strategies": {
      "BB_reentry": {
        "signals": 42,
        "all": {
          "n": 37,
          "win_pct": 37.8,
          "mean_net_pct": -0.954,
          "pf": 0.66,
          "targets": 14,
          "stops": 21
        },
        "is": {
          "n": 14,
          "win_pct": 42.9,
          "mean_net_pct": -0.21,
          "pf": 0.92,
          "targets": 6,
          "stops": 7
        },
        "oos": {
          "n": 23,
          "win_pct": 34.8,
          "mean_net_pct": -1.407,
          "pf": 0.52,
          "targets": 8,
          "stops": 14
        }
      },
      "RSI30_recovery": {
        "signals": 68,
        "all": {
          "n": 54,
          "win_pct": 35.2,
          "mean_net_pct": -1.576,
          "pf": 0.54,
          "targets": 19,
          "stops": 33
        },
        "is": {
          "n": 25,
          "win_pct": 32,
          "mean_net_pct": -2.362,
          "pf": 0.37,
          "targets": 8,
          "stops": 16
        },
        "oos": {
          "n": 29,
          "win_pct": 37.9,
          "mean_net_pct": -0.898,
          "pf": 0.71,
          "targets": 11,
          "stops": 17
        }
      },
      "EMA20_pullback_trend": {
        "signals": 26,
        "all": {
          "n": 17,
          "win_pct": 29.4,
          "mean_net_pct": -2.08,
          "pf": 0.49,
          "targets": 4,
          "stops": 10
        },
        "is": {
          "n": 13,
          "win_pct": 23.1,
          "mean_net_pct": -3.422,
          "pf": 0.22,
          "targets": 2,
          "stops": 8
        },
        "oos": {
          "n": 4,
          "win_pct": 50,
          "mean_net_pct": 2.284,
          "pf": 1.72,
          "targets": 2,
          "stops": 2
        }
      },
      "Donchian20_volume_breakout": {
        "signals": 24,
        "all": {
          "n": 17,
          "win_pct": 35.3,
          "mean_net_pct": -2.292,
          "pf": 0.6,
          "targets": 6,
          "stops": 10
        },
        "is": {
          "n": 7,
          "win_pct": 28.6,
          "mean_net_pct": -4.114,
          "pf": 0.35,
          "targets": 2,
          "stops": 5
        },
        "oos": {
          "n": 10,
          "win_pct": 40,
          "mean_net_pct": -1.016,
          "pf": 0.81,
          "targets": 4,
          "stops": 5
        }
      },
      "Sweep10_reclaim": {
        "signals": 125,
        "all": {
          "n": 74,
          "win_pct": 33.8,
          "mean_net_pct": -1.393,
          "pf": 0.57,
          "targets": 25,
          "stops": 46
        },
        "is": {
          "n": 39,
          "win_pct": 28.2,
          "mean_net_pct": -2.054,
          "pf": 0.42,
          "targets": 11,
          "stops": 27
        },
        "oos": {
          "n": 35,
          "win_pct": 40,
          "mean_net_pct": -0.657,
          "pf": 0.78,
          "targets": 14,
          "stops": 19
        }
      },
      "MACD_bull_cross": {
        "signals": 63,
        "all": {
          "n": 53,
          "win_pct": 50.9,
          "mean_net_pct": 0.868,
          "pf": 1.3,
          "targets": 26,
          "stops": 23
        },
        "is": {
          "n": 27,
          "win_pct": 48.1,
          "mean_net_pct": 0.877,
          "pf": 1.3,
          "targets": 13,
          "stops": 11
        },
        "oos": {
          "n": 26,
          "win_pct": 53.8,
          "mean_net_pct": 0.86,
          "pf": 1.29,
          "targets": 13,
          "stops": 12
        }
      }
    }
  },
  "1h": {
    "bars": 5000,
    "from": "2026-04-12T17:00:00.000Z",
    "to": "2026-11-09T20:00:00.000Z",
    "strategies": {
      "BB_reentry": {
        "signals": 147,
        "all": {
          "n": 137,
          "win_pct": 32.1,
          "mean_net_pct": -1.492,
          "pf": 0.32,
          "targets": 45,
          "stops": 82
        },
        "is": {
          "n": 80,
          "win_pct": 20,
          "mean_net_pct": -2.036,
          "pf": 0.19,
          "targets": 16,
          "stops": 54
        },
        "oos": {
          "n": 57,
          "win_pct": 49.1,
          "mean_net_pct": -0.73,
          "pf": 0.58,
          "targets": 29,
          "stops": 28
        }
      },
      "RSI30_recovery": {
        "signals": 202,
        "all": {
          "n": 164,
          "win_pct": 29.3,
          "mean_net_pct": -1.696,
          "pf": 0.28,
          "targets": 50,
          "stops": 102
        },
        "is": {
          "n": 92,
          "win_pct": 19.6,
          "mean_net_pct": -2.167,
          "pf": 0.17,
          "targets": 18,
          "stops": 64
        },
        "oos": {
          "n": 72,
          "win_pct": 41.7,
          "mean_net_pct": -1.095,
          "pf": 0.47,
          "targets": 32,
          "stops": 38
        }
      },
      "EMA20_pullback_trend": {
        "signals": 98,
        "all": {
          "n": 61,
          "win_pct": 34.4,
          "mean_net_pct": -1.119,
          "pf": 0.56,
          "targets": 20,
          "stops": 35
        },
        "is": {
          "n": 34,
          "win_pct": 35.3,
          "mean_net_pct": -1.093,
          "pf": 0.53,
          "targets": 12,
          "stops": 17
        },
        "oos": {
          "n": 27,
          "win_pct": 33.3,
          "mean_net_pct": -1.152,
          "pf": 0.59,
          "targets": 8,
          "stops": 18
        }
      },
      "Donchian20_volume_breakout": {
        "signals": 86,
        "all": {
          "n": 54,
          "win_pct": 35.2,
          "mean_net_pct": -1.4,
          "pf": 0.54,
          "targets": 19,
          "stops": 27
        },
        "is": {
          "n": 26,
          "win_pct": 30.8,
          "mean_net_pct": -2.04,
          "pf": 0.38,
          "targets": 8,
          "stops": 14
        },
        "oos": {
          "n": 28,
          "win_pct": 39.3,
          "mean_net_pct": -0.805,
          "pf": 0.71,
          "targets": 11,
          "stops": 13
        }
      },
      "Sweep10_reclaim": {
        "signals": 341,
        "all": {
          "n": 222,
          "win_pct": 26.1,
          "mean_net_pct": -1.752,
          "pf": 0.21,
          "targets": 73,
          "stops": 132
        },
        "is": {
          "n": 134,
          "win_pct": 24.6,
          "mean_net_pct": -1.703,
          "pf": 0.22,
          "targets": 43,
          "stops": 76
        },
        "oos": {
          "n": 88,
          "win_pct": 28.4,
          "mean_net_pct": -1.825,
          "pf": 0.19,
          "targets": 30,
          "stops": 56
        }
      },
      "MACD_bull_cross": {
        "signals": 194,
        "all": {
          "n": 154,
          "win_pct": 33.8,
          "mean_net_pct": -1.35,
          "pf": 0.44,
          "targets": 53,
          "stops": 79
        },
        "is": {
          "n": 91,
          "win_pct": 26.4,
          "mean_net_pct": -1.579,
          "pf": 0.38,
          "targets": 25,
          "stops": 48
        },
        "oos": {
          "n": 63,
          "win_pct": 44.4,
          "mean_net_pct": -1.018,
          "pf": 0.55,
          "targets": 28,
          "stops": 31
        }
      }
    }
  },
  "15m": {
    "bars": 3000,
    "from": "2026-10-03T14:45:00.000Z",
    "to": "2026-11-09T20:45:00.000Z",
    "strategies": {
      "BB_reentry": {
        "signals": 86,
        "all": {
          "n": 81,
          "win_pct": 12.3,
          "mean_net_pct": -1.676,
          "pf": 0.06,
          "targets": 22,
          "stops": 33
        },
        "is": {
          "n": 51,
          "win_pct": 15.7,
          "mean_net_pct": -1.626,
          "pf": 0.07,
          "targets": 15,
          "stops": 22
        },
        "oos": {
          "n": 30,
          "win_pct": 6.7,
          "mean_net_pct": -1.761,
          "pf": 0.05,
          "targets": 7,
          "stops": 11
        }
      },
      "RSI30_recovery": {
        "signals": 99,
        "all": {
          "n": 90,
          "win_pct": 12.2,
          "mean_net_pct": -1.705,
          "pf": 0.06,
          "targets": 20,
          "stops": 38
        },
        "is": {
          "n": 52,
          "win_pct": 15.4,
          "mean_net_pct": -1.642,
          "pf": 0.06,
          "targets": 11,
          "stops": 19
        },
        "oos": {
          "n": 38,
          "win_pct": 7.9,
          "mean_net_pct": -1.791,
          "pf": 0.06,
          "targets": 9,
          "stops": 19
        }
      },
      "EMA20_pullback_trend": {
        "signals": 62,
        "all": {
          "n": 48,
          "win_pct": 14.6,
          "mean_net_pct": -1.725,
          "pf": 0.14,
          "targets": 9,
          "stops": 19
        },
        "is": {
          "n": 29,
          "win_pct": 13.8,
          "mean_net_pct": -1.617,
          "pf": 0.16,
          "targets": 6,
          "stops": 9
        },
        "oos": {
          "n": 19,
          "win_pct": 15.8,
          "mean_net_pct": -1.891,
          "pf": 0.12,
          "targets": 3,
          "stops": 10
        }
      },
      "Donchian20_volume_breakout": {
        "signals": 43,
        "all": {
          "n": 28,
          "win_pct": 32.1,
          "mean_net_pct": -1.448,
          "pf": 0.27,
          "targets": 8,
          "stops": 9
        },
        "is": {
          "n": 13,
          "win_pct": 38.5,
          "mean_net_pct": -0.862,
          "pf": 0.44,
          "targets": 5,
          "stops": 3
        },
        "oos": {
          "n": 15,
          "win_pct": 26.7,
          "mean_net_pct": -1.955,
          "pf": 0.17,
          "targets": 3,
          "stops": 6
        }
      },
      "Sweep10_reclaim": {
        "signals": 131,
        "all": {
          "n": 107,
          "win_pct": 10.3,
          "mean_net_pct": -1.785,
          "pf": 0.03,
          "targets": 24,
          "stops": 39
        },
        "is": {
          "n": 62,
          "win_pct": 9.7,
          "mean_net_pct": -1.7,
          "pf": 0.03,
          "targets": 15,
          "stops": 19
        },
        "oos": {
          "n": 45,
          "win_pct": 11.1,
          "mean_net_pct": -1.903,
          "pf": 0.04,
          "targets": 9,
          "stops": 20
        }
      },
      "MACD_bull_cross": {
        "signals": 92,
        "all": {
          "n": 90,
          "win_pct": 14.4,
          "mean_net_pct": -1.727,
          "pf": 0.09,
          "targets": 17,
          "stops": 26
        },
        "is": {
          "n": 53,
          "win_pct": 17,
          "mean_net_pct": -1.453,
          "pf": 0.14,
          "targets": 11,
          "stops": 12
        },
        "oos": {
          "n": 37,
          "win_pct": 10.8,
          "mean_net_pct": -2.119,
          "pf": 0.04,
          "targets": 6,
          "stops": 14
        }
      }
    }
  }
}
```

## Limites
Criblage exploratoire, aucune stratégie validée. La fenêtre 15m est courte. Les historiques ne sont pas une réplication exacte des résultats Claude. Le slippage est une hypothèse faute de carnet historique. Aucun ordre ni modification de board/stratégie.
