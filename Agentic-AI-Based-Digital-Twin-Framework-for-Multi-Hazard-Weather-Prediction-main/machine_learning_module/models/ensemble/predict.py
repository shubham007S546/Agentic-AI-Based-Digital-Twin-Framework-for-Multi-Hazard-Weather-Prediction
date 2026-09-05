"""
CLI entrypoint for batch prediction with a trained ensemble.

Example
-------
python -m models.machine_learning.ensemble.predict \\
    --model-path artifacts/ensemble/ensemble_stack_v1/model.joblib \\
    --base-algorithms random_forest,xgboost,lightgbm --ensemble-method stacking \\
    --input-csv ml_ready/X_test.csv \\
    --output-csv predictions/ensemble_predictions.csv \\
    --task-type regression
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from models.common.base_model import BasePredictor
from models.common.logging_config import get_logger

from .config import EnsembleConfig
from .model import EnsembleModel
from .utils import add_common_cli_args, add_ensemble_cli_args, build_config_from_args

logger = get_logger(__name__, log_file="logs/ensemble_predict.log")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run batch prediction with a trained ensemble.")
    parser = add_common_cli_args(parser)
    parser = add_ensemble_cli_args(parser)
    parser.add_argument("--model-path", dest="model_path", required=True)
    parser.add_argument("--input-csv", dest="input_csv", required=True)
    parser.add_argument("--output-csv", dest="output_csv", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: EnsembleConfig = build_config_from_args(args)

    X = pd.read_csv(args.input_csv)
    predictor = BasePredictor.from_artifact(EnsembleModel, config, args.model_path)
    result_df = predictor.predict_dataframe(X)

    Path(args.output_csv).parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(args.output_csv, index=False)
    logger.info("Wrote %d predictions to %s", len(result_df), args.output_csv)


if __name__ == "__main__":
    main()
