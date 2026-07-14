# XGBoost Model

Config-driven XGBoost implementation supporting regression, binary
classification, and multiclass classification, with early stopping,
GPU support, and native missing-value handling, built on `models/common/`.

## Files

| File | Purpose |
|---|---|
| `config.py` | `XGBoostConfig` dataclass (extends `BaseModelConfig`) |
| `model.py` | `XGBoostModel` (extends `BaseModel`); early stopping via `eval_set` |
| `train.py` | CLI: train + save + register a model |
| `evaluate.py` | CLI: evaluate on test split, feature/permutation importance, SHAP |
| `predict.py` | CLI: batch inference on a CSV |
| `hyperparameter.py` | `XGBoostTuner` (extends `BaseHyperparameterTuner`); Optuna / grid / random |
| `utils.py` | argparse helpers shared across the CLIs above |

## Train

```bash
python -m models.machine_learning.xgboost.train \
    --task-type regression --data-dir ml_ready --target-column imd_rainfall_mm \
    --experiment-name xgb_rainfall_v1 --early-stopping-rounds 30
```

## Evaluate

```bash
python -m models.machine_learning.xgboost.evaluate \
    --data-dir ml_ready --target-column imd_rainfall_mm --task-type regression \
    --experiment-name xgb_rainfall_v1 \
    --model-path artifacts/xgboost/xgb_rainfall_v1/model.joblib \
    --with-permutation-importance --with-shap
```

## Predict

```bash
python -m models.machine_learning.xgboost.predict \
    --model-path artifacts/xgboost/xgb_rainfall_v1/model.joblib \
    --input-csv ml_ready/X_test.csv \
    --output-csv predictions/xgb_predictions.csv \
    --task-type regression
```

## Tune

```bash
python -m models.machine_learning.xgboost.hyperparameter \
    --data-dir ml_ready --target-column imd_rainfall_mm \
    --task-type regression --experiment-name xgb_rainfall_v1 \
    --method optuna --n-trials 50
```

## Notes

- GPU: set `--use-gpu` (maps to `device="cuda"` on the underlying estimator);
  falls back silently to CPU if no GPU/CUDA build is present.
- Missing values: XGBoost's native `missing=nan` handling means `NaN`s in
  `ml_ready/X_*.csv` are handled without imputation.
- `scale_pos_weight` for binary classification is derived automatically from
  `class_weights.json` (weight[1] / weight[0]) unless explicitly overridden
  in `XGBoostConfig.scale_pos_weight`.
- Early stopping uses `bundle.X_val`/`y_val` as the eval set; this is also
  preserved during hyperparameter tuning (see `XGBoostTuner._extra_fit_kwargs`).
