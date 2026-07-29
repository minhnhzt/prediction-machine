"""
model.py — Classification models for LPL match prediction.

Provides:
  - 5 Model options: lr, rf, xgboost, lightgbm, tabattention (PyTorch Self-Attention)
  - TimeSeriesSplit GridSearchCV hyperparameter tuning
  - Standard training and evaluation pipeline
"""

import os
import warnings
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.base import BaseEstimator, ClassifierMixin

# Import features list
from feature_engineering import (
    build_feature_dataframe,
    FEATURE_COLS,
    TARGET_COL,
    DB_PATH,
)

# Optional dependencies
try:
    from xgboost import XGBClassifier
except (ImportError, OSError):
    XGBClassifier = None

try:
    from lightgbm import LGBMClassifier
except (ImportError, OSError):
    LGBMClassifier = None

# PyTorch support
import torch
import torch.nn as nn
import torch.optim as optim

# AutoGluon support
try:
    from autogluon_model import AutoGluonClassifier
except ImportError:
    AutoGluonClassifier = None

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ── PyTorch Tabular Self-Attention Architecture ──────────────────────────────
class TabAttention(nn.Module):
    def __init__(self, input_dim=16, d_model=32, nhead=2, dropout=0.2):
        super().__init__()
        self.input_dim = input_dim
        self.d_model = d_model
        
        # Project each of the input features to a d_model embedding space
        self.feature_projections = nn.ModuleList([
            nn.Linear(1, d_model) for _ in range(input_dim)
        ])
        
        self.attention = nn.MultiheadAttention(
            embed_dim=d_model, num_heads=nhead, dropout=dropout, batch_first=True
        )
        self.norm1 = nn.LayerNorm(d_model)
        
        self.ffn = nn.Sequential(
            nn.Linear(input_dim * d_model, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 1)
        )
        
    def forward(self, x):
        batch_size = x.size(0)
        
        # Project each column feature
        projected = []
        for i in range(self.input_dim):
            feat = x[:, i:i+1]  # shape: (batch, 1)
            proj = self.feature_projections[i](feat)  # shape: (batch, d_model)
            projected.append(proj.unsqueeze(1))  # shape: (batch, 1, d_model)
            
        # Concatenate tokens
        tokens = torch.cat(projected, dim=1)  # shape: (batch, input_dim, d_model)
        
        # Self-attention over feature sequence
        attn_out, _ = self.attention(tokens, tokens, tokens)
        x_attn = self.norm1(tokens + attn_out)
        
        # Flatten and predict
        x_flat = x_attn.view(batch_size, -1)
        out = self.ffn(x_flat)
        return torch.sigmoid(out)


class PyTorchTabAttentionClassifier(BaseEstimator, ClassifierMixin):
    """Scikit-learn compatible wrapper for the PyTorch TabAttention model."""
    def __init__(self, d_model=16, nhead=2, lr=0.005, epochs=60, batch_size=32, dropout=0.1):
        self.d_model = d_model
        self.nhead = nhead
        self.lr = lr
        self.epochs = epochs
        self.batch_size = batch_size
        self.dropout = dropout
        self.model = None
        self.classes_ = np.array([0, 1])
        
    def fit(self, X, y):
        # Convert inputs to torch tensors
        X_t = torch.tensor(X, dtype=torch.float32)
        y_t = torch.tensor(y, dtype=torch.float32).unsqueeze(1)
        
        self.model = TabAttention(
            input_dim=X.shape[1], d_model=self.d_model, nhead=self.nhead, dropout=self.dropout
        )
        optimizer = optim.Adam(self.model.parameters(), lr=self.lr, weight_decay=1e-4)
        criterion = nn.BCELoss()
        
        self.model.train()
        dataset = torch.utils.data.TensorDataset(X_t, y_t)
        loader = torch.utils.data.DataLoader(dataset, batch_size=self.batch_size, shuffle=True)
        
        for epoch in range(self.epochs):
            for batch_X, batch_y in loader:
                optimizer.zero_grad()
                pred = self.model(batch_X)
                loss = criterion(pred, batch_y)
                loss.backward()
                optimizer.step()
        return self
        
    def predict_proba(self, X):
        self.model.eval()
        with torch.no_grad():
            X_t = torch.tensor(X, dtype=torch.float32)
            pred = self.model(X_t).numpy()
        return np.hstack([1 - pred, pred])
        
    def predict(self, X):
        proba = self.predict_proba(X)[:, 1]
        return (proba >= 0.5).astype(int)


# ── Configuration ────────────────────────────────────────────────────────────
TRAIN_RATIO = 0.80  # chronological split
RANDOM_STATE = 42


def get_hyperparameter_grid(model_key: str) -> dict:
    """Return GridSearchCV parameters for a given model."""
    if model_key == "lr":
        return {
            "C": [0.01, 0.1, 1.0, 10.0],
            "solver": ["liblinear", "lbfgs"]
        }
    elif model_key == "rf":
        return {
            "n_estimators": [100, 200, 300],
            "max_depth": [5, 8, 12, None],
            "min_samples_leaf": [2, 5, 10]
        }
    elif model_key == "xgboost":
        return {
            "n_estimators": [100, 200],
            "max_depth": [3, 5, 7],
            "learning_rate": [0.05, 0.1]
        }
    elif model_key == "lightgbm":
        return {
            "n_estimators": [100, 200],
            "max_depth": [3, 5, -1],
            "learning_rate": [0.05, 0.1],
            "verbose": [-1]
        }
    elif model_key == "tabattention":
        return {
            "d_model": [16, 32],
            "nhead": [2],
            "lr": [0.005, 0.01],
            "epochs": [40, 60]
        }
    return {}


def train_and_evaluate(
    df: pd.DataFrame | None = None,
    model_type: str = "rf",
    tune: bool = False,
) -> tuple:
    """
    Train a classifier and return (model, scaler, metrics_dict).

    Parameters
    ----------
    df : pd.DataFrame, optional
        Pre-built feature DataFrame. If None, builds from DB.
    model_type : str
        Model key: 'lr', 'rf', 'xgboost', 'lightgbm', 'tabattention'
    tune : bool
        If True, runs GridSearchCV using TimeSeriesSplit(5) for hyperparameter tuning.

    Returns
    -------
    model : fitted classifier
    scaler : fitted StandardScaler
    metrics : dict with accuracy, roc_auc, report (str), model_name (str)
    """
    if df is None:
        df = build_feature_dataframe()

    # ── Chronological train / test split ──────────────────────────────────
    split_idx = int(len(df) * TRAIN_RATIO)
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    X_train = train_df[FEATURE_COLS].values
    y_train = train_df[TARGET_COL].values
    X_test = test_df[FEATURE_COLS].values
    y_test = test_df[TARGET_COL].values

    # ── Feature scaling ───────────────────────────────────────────────────
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)

    # ── Model selection ───────────────────────────────────────────────────
    model_name = "Unknown"
    base_model = None

    if model_type == "lr":
        base_model = LogisticRegression(random_state=RANDOM_STATE, max_iter=1000)
        model_name = "LogisticRegression"
    elif model_type == "rf":
        base_model = RandomForestClassifier(random_state=RANDOM_STATE, n_jobs=-1)
        model_name = "RandomForestClassifier"
    elif model_type == "xgboost":
        if XGBClassifier is None:
            print("⚠️  xgboost not installed, falling back to GradientBoosting")
            base_model = GradientBoostingClassifier(random_state=RANDOM_STATE)
            model_name = "GradientBoostingClassifier (fallback)"
        else:
            base_model = XGBClassifier(random_state=RANDOM_STATE, eval_metric="logloss", n_jobs=-1)
            model_name = "XGBClassifier"
    elif model_type == "lightgbm":
        if LGBMClassifier is None:
            print("⚠️  lightgbm not installed, falling back to GradientBoosting")
            base_model = GradientBoostingClassifier(random_state=RANDOM_STATE)
            model_name = "GradientBoostingClassifier (fallback)"
        else:
            base_model = LGBMClassifier(random_state=RANDOM_STATE, verbose=-1, n_jobs=-1)
            model_name = "LGBMClassifier"
    elif model_type == "tabattention":
        base_model = PyTorchTabAttentionClassifier()
        model_name = "TabAttention (PyTorch Self-Attention)"
    elif model_type == "autogluon":
        if AutoGluonClassifier is None:
            raise ImportError(
                "AutoGluonClassifier is not available. Ensure AutoGluon is installed: pip install autogluon"
            )
        presets = 'best_quality' if tune else 'medium_quality_faster_train'
        base_model = AutoGluonClassifier(time_limit=300, presets=presets)
        model_name = "AutoGluonClassifier"
    else:
        raise ValueError(f"Invalid model_type: {model_type}")

    # ── Model fitting (Tuned or Default) ──────────────────────────────────
    if tune:
        param_grid = get_hyperparameter_grid(model_type)
        if param_grid:
            print(f"⚙️  Tuning {model_name} with GridSearchCV (TimeSeriesSplit)...")
            cv = TimeSeriesSplit(n_splits=5)
            # Custom scoring for classifier
            grid_search = GridSearchCV(
                estimator=base_model,
                param_grid=param_grid,
                cv=cv,
                scoring="accuracy",
                n_jobs=-1 if model_type != "tabattention" else 1, # PyTorch grid search in parallel can crash
            )
            grid_search.fit(X_train, y_train)
            model = grid_search.best_estimator_
            print(f"   Best Params: {grid_search.best_params_}")
            model_name += f" (Tuned)"
        else:
            model = base_model
            model.fit(X_train, y_train)
    else:
        model = base_model
        model.fit(X_train, y_train)

    # ── Evaluate ──────────────────────────────────────────────────────────
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    try:
        auc = roc_auc_score(y_test, y_proba)
    except ValueError:
        auc = float("nan")
    report = classification_report(y_test, y_pred, target_names=["Red Win", "Blue Win"])

    metrics = {
        "accuracy": acc,
        "roc_auc": auc,
        "report": report,
        "model_name": model_name
    }

    print(f"\n{'='*60}")
    print(f"  Model        : {model_name}")
    print(f"  Train size   : {len(train_df)}")
    print(f"  Test size    : {len(test_df)}")
    print(f"  Accuracy     : {acc:.4%}")
    print(f"  ROC-AUC      : {auc:.4f}")
    print(f"{'='*60}")
    print(report)

    # ── Feature importance (only for tree-based models) ──────────────────
    if hasattr(model, "feature_importances_"):
        imp = pd.Series(model.feature_importances_, index=FEATURE_COLS)
        imp = imp.sort_values(ascending=False)
        print("\n📊  Feature Importance:")
        for feat, val in imp.items():
            bar = "█" * int(val * 50)
            print(f"   {feat:<22s}  {val:.4f}  {bar}")

    return model, scaler, metrics


# ── Hypothetical match prediction ────────────────────────────────────────────
def predict_hypothetical(
    model,
    scaler,
    blue_elo: float = 1550.0,
    red_elo: float = 1480.0,
    blue_obj: float = 0.60,
    red_obj: float = 0.45,
    blue_avg_kills: float = 16.0,
    red_avg_kills: float = 13.5,
    blue_avg_dur: float = 1900.0,
    red_avg_dur: float = 2100.0,
    blue_avg_dragons: float = 3.0,
    red_avg_dragons: float = 2.0,
    blue_avg_towers: float = 7.0,
    red_avg_towers: float = 5.0,
    blue_avg_gold: float = 58000.0,
    red_avg_gold: float = 52000.0,
    blue_draft_wr: float = 0.52,
    red_draft_wr: float = 0.48,
) -> dict:
    """
    Predict outcome of a hypothetical match given pre-computed features.

    Features (16 total):
        Elo, ObjCtrl, AvgKills, AvgDuration, AvgDragons, AvgTowers, AvgGold, DraftWinRate
        — each for Blue and Red side.

    Returns dict with predicted class and probability.
    """
    features = np.array(
        [[blue_elo, red_elo,
          blue_obj, red_obj,
          blue_avg_kills, red_avg_kills,
          blue_avg_dur, red_avg_dur,
          blue_avg_dragons, red_avg_dragons,
          blue_avg_towers, red_avg_towers,
          blue_avg_gold, red_avg_gold,
          blue_draft_wr, red_draft_wr]]
    )
    features_scaled = scaler.transform(features)
    proba = model.predict_proba(features_scaled)[0]
    pred_class = model.predict(features_scaled)[0]

    result = {
        "predicted_winner": "Blue" if pred_class == 1 else "Red",
        "blue_win_prob": round(proba[1], 4),
        "red_win_prob": round(proba[0], 4),
    }

    print(f"\n🔮  Hypothetical Match Prediction:")
    print(f"   Blue Elo={blue_elo}  vs  Red Elo={red_elo}")
    print(f"   Blue ObjCtrl={blue_obj:.2f}  Red ObjCtrl={red_obj:.2f}")
    print(f"   Blue DraftWR={blue_draft_wr:.2f}  Red DraftWR={red_draft_wr:.2f}")
    print(f"   → Predicted Winner : {result['predicted_winner']} side")
    print(f"   → P(Blue Win)      : {result['blue_win_prob']:.2%}")
    print(f"   → P(Red Win)       : {result['red_win_prob']:.2%}")

    return result


if __name__ == "__main__":
    df = build_feature_dataframe()
    # Test RF
    model, scaler, metrics = train_and_evaluate(df, model_type="rf", tune=False)
    # Test PyTorch
    model_pt, scaler_pt, metrics_pt = train_and_evaluate(df, model_type="tabattention", tune=False)
    predict_hypothetical(model_pt, scaler_pt)
