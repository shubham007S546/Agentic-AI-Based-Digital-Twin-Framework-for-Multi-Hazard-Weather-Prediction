# deep_learning

LSTM / GRU / TCN sequence models, following the same 7-file structure as
`random_forest` / `xgboost` / `lightgbm`, so they're drop-in-compatible with
the rest of the framework (same `BaseModel` / `BaseTrainer` / `BaseEvaluator`
/ `ModelRegistry` contract).

## Requirements

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

(Use the regular `pip install torch` if you have a CUDA GPU and want to pass
`--device cuda`.)

## How it turns tabular rows into sequences

Your `X_train.csv` / `X_val.csv` / `X_test.csv` are still one row per
timestamp, exactly like for RandomForest/XGBoost/LightGBM. Internally,
`build_padded_sequences` (in `models/common/torch_utils.py`) builds a sliding
window of the last `--sequence-length` rows ending at each row. Rows near the
start of a series that don't have enough history yet are **zero-padded**,
which is what guarantees `predict(X)` always returns exactly `len(X)`
predictions -- same row-alignment contract every other algorithm in this
framework follows.

If your data has multiple independent series (e.g. one per district/station),
pass `--group-column district_id` so windows never bleed across two unrelated
locations. Just make sure that column is present in your `X_*.csv` files --
you do **not** need to (and should not) also list it in `--drop-columns`; it's
excluded from the numeric input automatically.

## Quickstart

```powershell
python -m models.machine_learning.deep_learning.train `
  --task-type regression --data-dir ml_ready --target-column imd_rainfall_mm `
  --architecture lstm --sequence-length 24 --hidden-size 64 --num-layers 2 `
  --epochs 100 --early-stopping-patience 10 --experiment-name dl_lstm_v1

python -m models.machine_learning.deep_learning.evaluate `
  --task-type regression --data-dir ml_ready --target-column imd_rainfall_mm `
  --architecture lstm --sequence-length 24 --hidden-size 64 --num-layers 2 `
  --experiment-name dl_lstm_v1 `
  --model-path artifacts\deep_learning\dl_lstm_v1\model.joblib

python -m models.machine_learning.deep_learning.predict `
  --task-type regression --architecture lstm --sequence-length 24 --hidden-size 64 --num-layers 2 `
  --model-path artifacts\deep_learning\dl_lstm_v1\model.joblib `
  --input-csv ml_ready\X_test.csv --output-csv predictions\dl_predictions.csv
```

Switch architecture with `--architecture gru` or `--architecture tcn`
(TCN also takes `--tcn-channels 64,64,64` and `--tcn-kernel-size 3`).

**Important:** `evaluate.py` and `predict.py` need the *same* architecture
flags you trained with (`--architecture`, `--sequence-length`,
`--hidden-size`, `--num-layers`, `--tcn-channels`, etc.) so the network
shape matches the saved weights. If you forget, you'll get a
size-mismatch error when loading `state_dict` -- if that happens, double
check these flags against your train.py command.

## Hyperparameter tuning

```powershell
python -m models.machine_learning.deep_learning.hyperparameter `
  --task-type regression --data-dir ml_ready --target-column imd_rainfall_mm `
  --architecture lstm --method optuna --n-trials 15
```

Each trial fully retrains the network, so this is much slower than tuning a
tree model -- start with a small `--n-trials` and a small `--epochs` budget.

## Notes

- Feature importance (`--with-permutation-importance` in `evaluate.py`) uses
  model-agnostic permutation importance rather than a native
  `feature_importances_` attribute (deep nets don't have one).
- `model.get_training_history()` returns the per-epoch train/val loss curve,
  saved to `training_history.json` by `train.py` -- useful for spotting
  overfitting (the same generalization-gap issue you found with the Tweedie
  LightGBM run) early, before wasting a full test-set evaluation on it.
