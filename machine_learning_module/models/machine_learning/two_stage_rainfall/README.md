# Two-Stage Rainfall Pipeline

Rainfall (`imd_rainfall_mm`) is zero-inflated: most rows are 0, and the rest
are right-skewed with rare large spikes. A single regressor tends to be
mediocre everywhere instead of good anywhere (this is exactly what the
plain `random_forest`/`xgboost`/`lightgbm` regressors were doing: R²≈0.24,
RMSE≈18.5mm against a std of 9.6mm).

This pipeline splits the problem in two, reusing the existing algorithm
modules rather than duplicating them:

- **Stage 1 (classifier)**: "did it rain at all?" — binary classification
  on `target > rain_threshold`.
- **Stage 2 (regressor)**: "how much, given that it rained?" — trained
  **only** on the rainy subset of the training data, optionally on
  `log1p(target)` to tame the right-skew.
- **Final prediction** = 0 where stage 1 says "no rain", else stage 2's
  (inverse-transformed) prediction.

You can mix algorithms per stage, e.g. RandomForest for the classifier and
XGBoost for the regressor.

## Files

| File | Purpose |
|---|---|
| `config.py` | `TwoStageRainfallConfig` |
| `pipeline.py` | `TwoStageRainfallModel` — composes two `BaseModel`s from `random_forest`/`xgboost`/`lightgbm` |
| `train.py` | CLI: fits both stages, saves one combined artifact |
| `evaluate.py` | CLI: stage-1 classification metrics + stage-2-on-true-rain metrics + combined end-to-end regression metrics |
| `predict.py` | CLI: batch inference, outputs both `rain_probability` and `predicted_rainfall_mm` |
| `utils.py` | argparse helpers |

## Train

```bash
python -m models.machine_learning.two_stage_rainfall.train \
    --data-dir ml_ready --target-column imd_rainfall_mm \
    --classifier-algorithm random_forest --regressor-algorithm xgboost \
    --experiment-name two_stage_v1
```

## Evaluate

```bash
python -m models.machine_learning.two_stage_rainfall.evaluate \
    --data-dir ml_ready --target-column imd_rainfall_mm \
    --experiment-name two_stage_v1 \
    --model-path artifacts/two_stage_rainfall/two_stage_v1/model.joblib
```

Output has three sections:
- `stage1_classification`: accuracy/precision/recall/f1/roc_auc for "did it rain".
- `stage2_on_rainy_subset`: RMSE/MAE/R2 of the amount prediction, evaluated
  only on rows that actually rained (tells you how good stage 2 is in
  isolation).
- `combined`: RMSE/MAE/R2 of the full pipeline against every row — **this
  is the number to compare against the plain regressor's R²=0.245.**

## Predict

```bash
python -m models.machine_learning.two_stage_rainfall.predict \
    --model-path artifacts/two_stage_rainfall/two_stage_v1/model.joblib \
    --input-csv ml_ready/X_test.csv \
    --output-csv predictions/two_stage_predictions.csv
```

## Key knobs

- `--rain-threshold` (default 0.1mm): rows above this count as "it rained"
  for stage 1. Raise it if trace/measurement noise near 0 is polluting the
  classifier.
- `--classification-threshold` (default 0.5): probability cutoff for stage
  1's rain/no-rain decision. Lower it to bias toward predicting *some*
  rain more often (higher recall) — often desirable for an early-warning
  system where missing a rain event is worse than a false alarm.
- `--log-transform` / `--no-log-transform` (default on): whether stage 2
  fits `log1p(target)` instead of the raw mm value.
- `--classifier-algorithm` / `--regressor-algorithm`: any of
  `random_forest`, `xgboost`, `lightgbm`, independently per stage.

## Notes

- `sample_weights_train.csv` is applied to both stages (subset to the rainy
  rows for stage 2) if `--use-sample-weights` (default on).
- The saved artifact bundles both sub-estimators in one `.joblib` file —
  `evaluate.py`/`predict.py` only need `--model-path`, not two paths.
- This module does not use `class_weights.json` for stage 1; if your
  rain/no-rain split is heavily imbalanced, prefer adjusting
  `--classification-threshold` first, since that directly controls the
  recall/precision trade-off you actually care about for a hazard-warning
  use case.
