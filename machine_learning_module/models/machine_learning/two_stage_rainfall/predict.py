"""
CLI entrypoint for batch prediction with the two-stage rainfall pipeline.

Example
-------
python -m models.machine_learning.two_stage_rainfall.predict \
    --model-path artifacts/two_stage_rainfall/two_stage_v1/model.joblib \
    --input-csv ml_ready/X_test.csv \
    --output-csv predictions/two_stage_predictions.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from models.common.logging_config import get_logger

from .config import TwoStageRainfallConfig
from .pipeline import TwoStageRainfallModel
from .utils import add_common_cli_args, add_two_stage_cli_args, build_config_from_args

logger = get_logger(__name__, log_file="logs/two_stage_rainfall_predict.log")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch prediction with the two-stage rainfall pipeline.")
    parser = add_common_cli_args(parser)
    parser = add_two_stage_cli_args(parser)
    parser.add_argument("--model-path", dest="model_path", required=True)
    parser.add_argument("--input-csv", dest="input_csv", required=True)
    parser.add_argument("--output-csv", dest="output_csv", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config: TwoStageRainfallConfig = build_config_from_args(args)

    X = pd.read_csv(args.input_csv)
    model = TwoStageRainfallModel(config)
    model.load(args.model_path)

    result = X.copy()
    result["rain_probability"] = model.predict_rain_probability(X)
    result["predicted_rainfall_mm"] = model.predict(X)

    Path(args.output_csv).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output_csv, index=False)
    logger.info("Wrote %d predictions to %s", len(result), args.output_csv)


if __name__ == "__main__":
    main()
