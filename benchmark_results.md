# SOTA Prediction Model Benchmark — LPL

This report compares machine learning and deep learning models for predicting League of Legends match outcomes. All models are trained on the chronological train split (first 80%) and evaluated on the chronological test split (last 20%) to prevent look-ahead bias.

## Benchmark Results

| Model                                         | Tuned   | Accuracy   |   ROC-AUC |   F1-Score | Train Time   |
|:----------------------------------------------|:--------|:-----------|----------:|-----------:|:-------------|
| LogisticRegression                            | No      | 59.52%     |    0.6457 |     0.5952 | 0.02s        |
| LogisticRegression (Tuned)                    | Yes     | 63.10%     |    0.6391 |     0.6643 | 18.79s       |
| RandomForestClassifier                        | No      | 52.78%     |    0.5537 |     0.5441 | 0.64s        |
| RandomForestClassifier (Tuned)                | Yes     | 59.92%     |    0.6116 |     0.638  | 34.80s       |
| XGBClassifier                                 | No      | 55.95%     |    0.5668 |     0.5613 | 0.21s        |
| XGBClassifier (Tuned)                         | Yes     | 58.33%     |    0.5817 |     0.6125 | 5.35s        |
| LGBMClassifier                                | No      | 53.57%     |    0.5382 |     0.5483 | 0.26s        |
| LGBMClassifier (Tuned)                        | Yes     | 56.35%     |    0.5601 |     0.5736 | 5.28s        |
| TabAttention (PyTorch Self-Attention)         | No      | 55.95%     |    0.5887 |     0.5934 | 17.82s       |
| TabAttention (PyTorch Self-Attention) (Tuned) | Yes     | 57.14%     |    0.5775 |     0.5221 | 280.13s      |

## Insights
- **TabAttention (PyTorch Self-Attention)** leverages a Multi-Head Self-Attention layer to model feature interactions, capturing how team stats and drafting variables impact each other.
- **LightGBM and XGBoost** represent state-of-the-art tree boosting models frequently cited in MOBA predictive literature.
- **Tuning** uses `GridSearchCV` combined with a `TimeSeriesSplit` cross-validation scheme to optimize parameters without temporal data leakage.
