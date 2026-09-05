# ensemble

Combines `random_forest` + `xgboost` + `lightgbm` (optionally + `deep_learning`)
behind a single `BaseModel`, via stacking / voting / weighted averaging. This
is usually the most reliable way to squeeze out extra accuracy once your
individual models have plateaued -- exactly your situation after step2/step3/
step4 (log1p LightGBM was your best single model at test R²=0.216).

## The three methods

- **`stacking`** (recommended, usually most accurate): out-of-fold
  predictions from each base model become features for a meta-learner
  (Ridge for regression, Logistic Regression for classification), which
  learns how to best combine them. Base models are refit on the full train
  split afterward for inference. Out-of-fold (not in-sample) predictions are
  what stop the meta-learner from just trusting whichever base model
  overfit train the hardest.
- **`voting`**: plain unweighted average / majority vote. Fastest, hardest
  to overfit, but leaves some accuracy on the table vs. stacking.
- **`weighted_average`**: like voting, but weighted. If you don't pass
  `--weights` explicitly, weights are auto-derived from each base model's
  validation performance (inverse RMSE for regression, accuracy for
  classification) -- a base model that validates poorly counts for less.

## Quickstart

```powershell
python -m models.machine_learning.ensemble.train `
  --task-type regression --data-dir ml_ready --target-column imd_rainfall_mm `
  --base-algorithms random_forest,xgboost,lightgbm --ensemble-method stacking `
  --cv-folds 5 --target-transform log1p --experiment-name ensemble_stack_v1

python -m models.machine_learning.ensemble.evaluate `
  --task-type regression --data-dir ml_ready --target-column imd_rainfall_mm `
  --base-algorithms random_forest,xgboost,lightgbm --ensemble-method stacking `
  --target-transform log1p --experiment-name ensemble_stack_v1 `
  --model-path artifacts\ensemble\ensemble_stack_v1\model.joblib

python -m models.machine_learning.ensemble.predict `
  --task-type regression --base-algorithms random_forest,xgboost,lightgbm --ensemble-method stacking `
  --target-transform log1p `
  --model-path artifacts\ensemble\ensemble_stack_v1\model.joblib `
  --input-csv ml_ready\X_test.csv --output-csv predictions\ensemble_predictions.csv
```

Given your earlier results, this is worth trying first:
```powershell
--base-algorithms random_forest,xgboost,lightgbm --ensemble-method stacking --target-transform log1p
```
since log1p was the one transform that actually generalized to your test set.

**Important:** `evaluate.py` and `predict.py` need the same
`--base-algorithms` / `--ensemble-method` flags you trained with, so the
saved sub-models and meta-learner match what gets reconstructed.

## Adding deep_learning as a 4th base model

```powershell
--base-algorithms random_forest,xgboost,lightgbm,deep_learning
```

Note the ensemble builds each base model with its own *default*
hyperparameters (via a minimal sub-config inheriting only task_type,
data_dir, target_column, seed, etc. from the ensemble config) -- it does
not re-tune them. Tune each algorithm individually first with its own
`hyperparameter.py`, and if you want the ensemble to use tuned settings
rather than defaults, that's a natural next extension of
`_build_sub_config` in `model.py` (accept an optional params dict per
algorithm).

## Hyperparameter tuning

```powershell
python -m models.machine_learning.ensemble.hyperparameter `
  --data-dir ml_ready --target-column imd_rainfall_mm --task-type regression `
  --method optuna --n-trials 10
```

This searches ensemble-level knobs only (method, meta-learner
regularization, CV folds) -- not the base models' own hyperparameters. Each
trial retrains every base model, so it's the slowest tuner in the
framework; keep `--n-trials` small.

## Notes

- `--target-transform log1p` on the ensemble CLI transforms `y` once, at the
  top level, before any base model sees it -- every base model and the
  meta-learner train in the same log-space, and only the final combined
  prediction gets inverse-transformed. Don't try to also set a transform
  on individual base models; there's no CLI flag for that by design, to
  avoid double-transforming.
- `model.get_feature_importance()` averages `feature_importances_` across
  whichever base models expose it (the tree-based ones); it raises a clear
  error if none do (e.g. an all-deep_learning ensemble).
- `train.py` writes `ensemble_weights.json` (final blend weights) alongside
  the usual `model.joblib` / `val_metrics.json`.
