# LightGBM Model

Config-driven LightGBM implementation supporting regression, binary
classification, and multiclass classification, with leaf-wise growth,
categorical feature support, GPU option, and early stopping, built on
`models/common/`.

## Files

| File | Purpose |
|---|---|
| `config.py` | `LightGBMConfig` dataclass (extends `BaseModelConfig`) |
| `model.py` | `LightGBMModel` (extends `BaseModel`); early stopping via `lightgbm.early_stopping` callback |
| `train.py` | CLI: train + save + register a model |
| `evaluate.py` | CLI: evaluate on test split, feature/permutation importance, SHAP |
| `predict.py` | CLI: batch inference on a CSV |
| `hyperparameter.py` | `LightGBMTuner` (extends `BaseHyperparameterTuner`); Optuna / grid / random |
| `utils.py` | argparse helpers shared across the CLIs above |

## Train

```bash
python -m models.machine_learning.lightgbm.train \
    --task-type regression --data-dir ml_ready --target-column imd_rainfall_mm \
    --experiment-name lgbm_rainfall_v1 --early-stopping-rounds 30
```

## Evaluate

```bash
python -m models.machine_learning.lightgbm.evaluate \
    --data-dir ml_ready --target-column imd_rainfall_mm --task-type regression \
    --experiment-name lgbm_rainfall_v1 \
    --model-path artifacts/lightgbm/lgbm_rainfall_v1/model.joblib \
    --with-permutation-importance --with-shap
```

## Predict

```bash
python -m models.machine_learning.lightgbm.predict \
    --model-path artifacts/lightgbm/lgbm_rainfall_v1/model.joblib \
    --input-csv ml_ready/X_test.csv \
    --output-csv predictions/lgbm_predictions.csv \
    --task-type regression
```

## Tune

```bash
python -m models.machine_learning.lightgbm.hyperparameter \
    --data-dir ml_ready --target-column imd_rainfall_mm \
    --task-type regression --experiment-name lgbm_rainfall_v1 \
    --method optuna --n-trials 50
```

## Notes

- Categorical features: pass `--categorical-features colA,colB`; these are
  forwarded to `LGBMRegressor/Classifier.fit(categorical_feature=...)`
  without one-hot encoding, using LightGBM's native handling.
- GPU: set `--device gpu`; requires a GPU-enabled LightGBM build.
- For imbalanced binary classification, use either `--is-unbalance` or let
  `scale_pos_weight` be derived automatically from `class_weights.json`
  (mutually exclusive, enforced in `config.validate()`).
- Early stopping uses `bundle.X_val`/`y_val` as the eval set via the
  `lightgbm.early_stopping` callback, and is preserved during tuning
  (see `LightGBMTuner._extra_fit_kwargs`).
