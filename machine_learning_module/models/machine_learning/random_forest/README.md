# Random Forest Model

Config-driven Random Forest implementation supporting regression, binary
classification, and multiclass classification, built on `sklearn.ensemble`
and the shared `models/common/` framework.

## Files

| File | Purpose |
|---|---|
| `config.py` | `RandomForestConfig` dataclass (extends `BaseModelConfig`) |
| `model.py` | `RandomForestModel` (extends `BaseModel`) |
| `train.py` | CLI: train + save + register a model |
| `evaluate.py` | CLI: evaluate on test split, feature/permutation importance, SHAP |
| `predict.py` | CLI: batch inference on a CSV |
| `hyperparameter.py` | `RandomForestTuner` (extends `BaseHyperparameterTuner`); Optuna / grid / random |
| `utils.py` | argparse helpers shared across the CLIs above |

## Train

```bash
python -m models.machine_learning.random_forest.train \
    --task-type regression \
    --data-dir ml_ready \
    --target-column imd_rainfall_mm \
    --experiment-name rf_rainfall_v1 \
    --n-estimators 400 --max-depth 20
```

## Evaluate

```bash
python -m models.machine_learning.random_forest.evaluate \
    --data-dir ml_ready --target-column imd_rainfall_mm \
    --task-type regression --experiment-name rf_rainfall_v1 \
    --model-path artifacts/random_forest/rf_rainfall_v1/model.joblib \
    --with-permutation-importance --with-shap
```

## Predict

```bash
python -m models.machine_learning.random_forest.predict \
    --model-path artifacts/random_forest/rf_rainfall_v1/model.joblib \
    --input-csv ml_ready/X_test.csv \
    --output-csv predictions/rf_predictions.csv \
    --task-type regression
```

## Tune

```bash
python -m models.machine_learning.random_forest.hyperparameter \
    --data-dir ml_ready --target-column imd_rainfall_mm \
    --task-type regression --experiment-name rf_rainfall_v1 \
    --method optuna --n-trials 50
```

## Notes

- `oob_score=True` requires `bootstrap=True` (enforced in `config.validate()`).
- `class_weight_mode` (`balanced` / `balanced_subsample` / `none`) is only
  applied for classification tasks; `use_class_weights` from
  `BaseModelConfig` is separate and governs whether `class_weights.json` is
  loaded at all from `ml_ready/`.
- `eval_set` / early stopping are not supported by `RandomForestRegressor`/
  `RandomForestClassifier`; `RandomForestModel.fit()` silently ignores
  `eval_set` so `train.py` stays identical across all three algorithms.
