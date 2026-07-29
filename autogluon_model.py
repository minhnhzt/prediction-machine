"""
autogluon_model.py — Scikit-learn compatible wrapper for AutoGluon-Tabular.
"""

import os
import shutil
import pandas as pd
import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from feature_engineering import FEATURE_COLS, TARGET_COL

try:
    from autogluon.tabular import TabularPredictor
except (ImportError, OSError):
    TabularPredictor = None

class AutoGluonClassifier(BaseEstimator, ClassifierMixin):
    """Scikit-learn compatible wrapper for Amazon AutoGluon-Tabular."""
    
    def __init__(self, time_limit=180, presets='best_quality', path='autogluon_models'):
        self.time_limit = time_limit
        self.presets = presets
        self.path = path
        self.predictor_ = None

    def fit(self, X, y):
        if TabularPredictor is None:
            raise ImportError(
                "AutoGluon is not installed. Please install it using: "
                "pip install autogluon"
            )
            
        # Clean any existing model directory to avoid loading old models
        if os.path.exists(self.path):
            try:
                shutil.rmtree(self.path)
            except Exception:
                pass

        # Convert numpy features back to DataFrame for AutoGluon
        df_train = pd.DataFrame(X, columns=FEATURE_COLS)
        df_train[TARGET_COL] = y

        print(f"[AutoGluon] Starting fit with time_limit={self.time_limit}s, presets={self.presets}...")
        
        # Disable logging file handlers if needed, let autogluon log to stdout
        self.predictor_ = TabularPredictor(
            label=TARGET_COL,
            eval_metric='accuracy',
            path=self.path
        ).fit(
            train_data=df_train,
            time_limit=self.time_limit,
            presets=self.presets,
            hyperparameters='default',
            num_gpus=1 # Tận dụng H100 GPU!
        )
        return self

    def predict(self, X):
        if self.predictor_ is None:
            raise ValueError("Predictor is not fitted yet.")
        df_test = pd.DataFrame(X, columns=FEATURE_COLS)
        return self.predictor_.predict(df_test).values

    def predict_proba(self, X):
        if self.predictor_ is None:
            raise ValueError("Predictor is not fitted yet.")
        df_test = pd.DataFrame(X, columns=FEATURE_COLS)
        proba_df = self.predictor_.predict_proba(df_test)
        # AutoGluon returns pd.DataFrame with class labels.
        # We need to return a 2D numpy array with probabilities of [class_0, class_1]
        # Sort columns to ensure column 0 is Red Win (0) and column 1 is Blue Win (1)
        sorted_cols = sorted(proba_df.columns)
        return proba_df[sorted_cols].values
