# Validation de « TEL Kraken – repli 4h dans tendance »

Verdict : **DONNÉES INSUFFISANTES** (0 trade ; 53 candidats rejetés par RR brut < 1,51 ; maximum 0,8011).

## Dépendances
Python ≥ 3.10 ; bibliothèque standard uniquement.

## Tests
`python3 -m unittest tests.test_strategy_engine -v`

## Reproduire
`sha256sum data/KRAKEN_TELUSD_4h_2026-01-22_2026-11-08.csv` (attendu : `96b50ad431ff3c78cefc2a18b37d6cc3224ec82e9a67d7812a0e172535674aa4`)
`python3 scripts/strategy_backtest/run_validation.py`

Fichiers : protocole `PROTOCOLE_STRATEGIE_FIGE.md`, audit `AUDIT_STRATEGIE_TEL.md`, rapport `RAPPORT_FINAL_VALIDATION_TEL.md`, traçabilité `research/TRACABILITE_VALIDATION_TEL.md`, résultats `results/strategy_validation/`.
