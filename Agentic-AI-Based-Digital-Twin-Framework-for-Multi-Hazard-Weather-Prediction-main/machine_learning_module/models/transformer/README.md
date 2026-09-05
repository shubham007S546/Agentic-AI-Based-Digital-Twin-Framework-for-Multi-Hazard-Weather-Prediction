# transformer (TFT-Lite)

A compact Temporal Fusion Transformer, simplified from Lim et al. 2019
("Temporal Fusion Transformers for Interpretable Multi-horizon Time Series
Forecasting") down to single-horizon output with no separate static/
known-future covariate branches -- but keeping the parts that made TFT
distinctive:

1. **Variable Selection Network** -- learns a per-timestep softmax weight
   over input features via per-feature Gated Residual Networks, so the
   model can learn to down-weight noisy/uninformative inputs (relevant
   given the flat-fill artifacts you found in `imd_rainfall_mm`).
2. **LSTM encoder** for local sequential processing.
3. **Causal multi-head self-attention** on top of the LSTM output, for
   longer-range temporal dependencies the LSTM alone might miss.
4. **Gated residual connections** (GLU + LayerNorm) throughout, so each
   block can learn to skip itself rather than being forced to use every
   layer -- this is what makes TFT trainable at depth without the usual
   vanishing-gradient/overfitting issues on small tabular-style datasets.

Same 7-file structure and `BaseModel` contract as every other algorithm here.

## Requirements

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

## Quickstart

```powershell
python -m models.machine_learning.transformer.train `
  --task-type regression --data-dir ml_ready --target-column imd_rainfall_mm `
  --sequence-length 24 --hidden-size 64 --num-attention-heads 4 --num-lstm-layers 1 `
  --epochs 100 --early-stopping-patience 10 --experiment-name tft_lite_v1

python -m models.machine_learning.transformer.evaluate `
  --task-type regression --data-dir ml_ready --target-column imd_rainfall_mm `
  --sequence-length 24 --hidden-size 64 --num-attention-heads 4 --num-lstm-layers 1 `
  --experiment-name tft_lite_v1 `
  --model-path artifacts\transformer\tft_lite_v1\model.joblib

python -m models.machine_learning.transformer.predict `
  --task-type regression --sequence-length 24 --hidden-size 64 --num-attention-heads 4 --num-lstm-layers 1 `
  --model-path artifacts\transformer\tft_lite_v1\model.joblib `
  --input-csv ml_ready\X_test.csv --output-csv predictions\tft_predictions.csv
```

**Important:** `--hidden-size` must be evenly divisible by
`--num-attention-heads` (e.g. 64/4=16 head-dim -- fine; 64/3 is not
allowed and will fail config validation with a clear error). `evaluate.py`
and `predict.py` need the same architecture flags you trained with, same
as `deep_learning`.

Same row-alignment / `--group-column` behavior as `deep_learning` --
see that package's README for how `--sequence-length` windowing works if
you haven't read it yet; it's identical here.

## Hyperparameter tuning

```powershell
python -m models.machine_learning.transformer.hyperparameter `
  --data-dir ml_ready --target-column imd_rainfall_mm --task-type regression `
  --method optuna --n-trials 15
```

The search space only offers `(hidden_size, num_attention_heads)` pairs
that are compatible (32/2, 32/4, 64/2, 64/4, 64/8, 128/4, 128/8), so you
won't hit the divisibility error mid-search.

## Interpreting attention

```python
weights = model.get_attention_weights(X)  # (batch, heads, seq_len, seq_len)
```

This exposes the raw causal self-attention map after loading a fitted
`TFTLiteModel` -- useful for seeing which past timesteps the model leaned
on most for a given prediction, one of TFT's signature interpretability
features (not exposed as a CLI flag; call it directly in a notebook/script).

## Notes on this being your "best architecture" candidate

TFT-style attention is well suited to exactly the kind of problem you're
working on (multi-source rainfall/hazard signals with irregular temporal
structure) -- but it's also the most parameter-hungry model in this
framework relative to how much genuine hourly signal your dataset has
(recall: your `imd_rainfall_mm` values are flat-fill artifacts, not real
sub-daily readings). Watch train vs. val loss in `training_history.json`
closely; if val loss plateaus or rises while train loss keeps dropping,
that's the same generalization-gap pattern you already caught with
Tweedie LightGBM, and it means TFT-Lite is overfitting the flat-fill
pattern rather than learning real structure -- in which case a smaller
`--hidden-size`/`--sequence-length` or the ensemble/log1p LightGBM
approach is likely to generalize better on this particular dataset.
