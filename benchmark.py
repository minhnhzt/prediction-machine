"""
benchmark.py — Run comparative benchmarks on all LPL match prediction models.

Iterates over Logistic Regression, Random Forest, XGBoost, LightGBM, and PyTorch TabAttention,
evaluating them both default and tuned with chronological TimeSeriesSplit cross-validation.
"""

import argparse
import os
import sys
import time
import pandas as pd
from sklearn.metrics import f1_score

# Add root directory to python path
sys.path.insert(0, os.path.dirname(__file__))

from feature_engineering import build_feature_dataframe, DB_PATH
from model import train_and_evaluate, FEATURE_COLS, TARGET_COL


def run_benchmark(league: str = "LPL") -> None:
    print("=" * 60)
    print(f"  STARTING MODEL BENCHMARK FOR LEAGUE: {league}")
    print("=" * 60)

    # 1. Load data
    if not os.path.isfile(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}. Run real_data_pipeline.py first.")
        sys.exit(1)

    df = build_feature_dataframe(DB_PATH, league_filter=league)
    if len(df) < 50:
        print(f"Warning: Not enough matches for league {league} (got {len(df)}). Benchmarking on whole dataset...")
        df = build_feature_dataframe(DB_PATH, league_filter=None)

    # We will run both default and tuned versions for each model type
    model_configs = [
        # (model_key, tune)
        ("lr", False),
        ("lr", True),
        ("rf", False),
        ("rf", True),
        ("xgboost", False),
        ("xgboost", True),
        ("lightgbm", False),
        ("lightgbm", True),
        ("tabattention", False),
        ("tabattention", True),
    ]

    results = []

    # Chronological train-test split for evaluation metrics
    split_idx = int(len(df) * 0.80)
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]
    y_test = test_df[TARGET_COL].values

    try:
        from tqdm import tqdm
        config_iter = tqdm(model_configs, desc="Benchmarking Models")
    except ImportError:
        config_iter = model_configs

    for model_key, tune in config_iter:
        tune_str = "Tuned" if tune else "Default"
        print(f"\n🚀 Running: Model={model_key.upper()} ({tune_str})...")
        
        start_time = time.time()
        try:
            model, scaler, metrics = train_and_evaluate(df, model_type=model_key, tune=tune)
            elapsed = time.time() - start_time
            
            # Predict to get F1 score
            # We scale test features using the fitted scaler
            X_test_scaled = scaler.transform(test_df[FEATURE_COLS].values)
            y_pred = model.predict(X_test_scaled)
            
            f1 = f1_score(y_test, y_pred, average="binary")
            
            results.append({
                "Model": metrics["model_name"],
                "Tuned": "Yes" if tune else "No",
                "Accuracy": f"{metrics['accuracy']:.2%}",
                "ROC-AUC": f"{metrics['roc_auc']:.4f}",
                "F1-Score": f"{f1:.4f}",
                "Train Time": f"{elapsed:.2f}s"
            })
        except Exception as e:
            print(f"⚠️ Error running {model_key} ({tune_str}): {e}")
            # Fall back / skip
            results.append({
                "Model": f"{model_key} ({tune_str})",
                "Tuned": "Yes" if tune else "No",
                "Accuracy": "FAILED",
                "ROC-AUC": "N/A",
                "F1-Score": "N/A",
                "Train Time": "N/A"
            })

    # Compile Markdown table
    res_df = pd.DataFrame(results)
    markdown_table = res_df.to_markdown(index=False)

    report_content = f"""# SOTA Prediction Model Benchmark — {league}

This report compares machine learning and deep learning models for predicting League of Legends match outcomes. All models are trained on the chronological train split (first 80%) and evaluated on the chronological test split (last 20%) to prevent look-ahead bias.

## Benchmark Results

{markdown_table}

## Insights
- **TabAttention (PyTorch Self-Attention)** leverages a Multi-Head Self-Attention layer to model feature interactions, capturing how team stats and drafting variables impact each other.
- **LightGBM and XGBoost** represent state-of-the-art tree boosting models frequently cited in MOBA predictive literature.
- **Tuning** uses `GridSearchCV` combined with a `TimeSeriesSplit` cross-validation scheme to optimize parameters without temporal data leakage.
"""

    # Print table to console
    print("\n" + "=" * 60)
    print("  BENCHMARK PIPELINE COMPLETE")
    print("=" * 60)
    print(markdown_table)
    print("=" * 60)

    # Save to file
    out_path = os.path.join(os.path.dirname(__file__), "benchmark_results.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"Report saved to: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", type=str, default="LPL", help="League filter (LPL or LCK)")
    args = parser.parse_args()
    run_benchmark(args.league)
