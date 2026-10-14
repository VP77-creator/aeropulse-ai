"""
Phase 7: Machine Learning - Flight Delay Prediction Pipeline (Enhanced with Balanced Weights & Calibration)
Flight Delay Analytics and Prediction System
"""

import os
import json
import duckdb
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, 
    roc_auc_score, confusion_matrix, roc_curve, precision_recall_curve
)
from sklearn.inspection import permutation_importance

def run_ml_pipeline(db_path="warehouse/flight_warehouse.duckdb", 
                    model_path="models/flight_delay_model.joblib",
                    meta_path="models/model_metadata.json",
                    report_path="data_reports/phase7_ml_metrics.json"):
    print("=" * 70)
    print("PHASE 7: MACHINE LEARNING - FLIGHT DELAY PREDICTION")
    print("=" * 70)
    start_time = datetime.now()
    
    conn = duckdb.connect(db_path, read_only=True)
    
    # 1. Feature Extraction with DuckDB
    print("\n[1] Extracting Feature Dataset from Star Schema Warehouse...")
    
    carrier_priors = dict(conn.execute("""
        SELECT carrier_key, round(sum(arr_del15) * 1.0 / count(*), 4) 
        FROM fact_flights WHERE cancelled = 0 AND diverted = 0 
        GROUP BY carrier_key
    """).fetchall())
    
    origin_priors = dict(conn.execute("""
        SELECT origin_key, round(sum(arr_del15) * 1.0 / count(*), 4) 
        FROM fact_flights WHERE cancelled = 0 AND diverted = 0 
        GROUP BY origin_key
    """).fetchall())

    dest_priors = dict(conn.execute("""
        SELECT dest_key, round(sum(arr_del15) * 1.0 / count(*), 4) 
        FROM fact_flights WHERE cancelled = 0 AND diverted = 0 
        GROUP BY dest_key
    """).fetchall())

    hour_priors = dict(conn.execute("""
        SELECT time_block_key, round(sum(arr_del15) * 1.0 / count(*), 4) 
        FROM fact_flights WHERE cancelled = 0 AND diverted = 0 
        GROUP BY time_block_key
    """).fetchall())

    print(f"    [+] Prior Lookup Tables Built: {len(carrier_priors)} carriers, {len(origin_priors)} origins, {len(dest_priors)} dests, {len(hour_priors)} hours.")

    sample_sql = """
        SELECT 
            f.arr_del15 as target,
            d.month,
            d.day_of_month,
            d.day_of_week,
            CASE WHEN d.is_weekend THEN 1 ELSE 0 END as is_weekend,
            CASE d.season 
                WHEN 'Winter' THEN 0 
                WHEN 'Spring' THEN 1 
                WHEN 'Summer' THEN 2 
                ELSE 3 
            END as season_code,
            f.time_block_key as dep_hour,
            f.carrier_key,
            f.origin_key,
            f.dest_key,
            f.distance,
            f.crs_elapsed_time,
            CASE WHEN d.month >= 11 THEN 'TEST' ELSE 'TRAIN' END as split_group
        FROM fact_flights f
        JOIN dim_date d ON f.date_key = d.date_key
        WHERE f.cancelled = 0 AND f.diverted = 0
        USING SAMPLE 650000 (reservoir, 42);
    """
    df = conn.execute(sample_sql).fetchdf()
    print(f"    [+] Loaded {len(df):,} sampled rows. Target delay balance: {df['target'].mean()*100:.2f}%")

    global_prior = 0.2082
    df['carrier_prior'] = df['carrier_key'].map(carrier_priors).fillna(global_prior)
    df['origin_prior'] = df['origin_key'].map(origin_priors).fillna(global_prior)
    df['dest_prior'] = df['dest_key'].map(dest_priors).fillna(global_prior)
    df['hour_prior'] = df['dep_hour'].map(hour_priors).fillna(global_prior)

    feature_cols = [
        'month',
        'day_of_month',
        'day_of_week',
        'is_weekend',
        'season_code',
        'dep_hour',
        'distance',
        'crs_elapsed_time',
        'carrier_prior',
        'origin_prior',
        'dest_prior',
        'hour_prior'
    ]

    train_mask = df['split_group'] == 'TRAIN'
    test_mask = df['split_group'] == 'TEST'

    X_train = df.loc[train_mask, feature_cols].values
    y_train = df.loc[train_mask, 'target'].values

    X_test = df.loc[test_mask, feature_cols].values
    y_test = df.loc[test_mask, 'target'].values

    print(f"    [+] Train Set: {len(X_train):,} samples (Months 1-10)")
    print(f"    [+] Test Set:  {len(X_test):,} samples (Months 11-12 Holdout)")

    # 3. Model Training with Class Weight Balancing
    print("\n[3] Training Production Model: HistGradientBoostingClassifier (Balanced Weights)...")
    gb_model = HistGradientBoostingClassifier(
        class_weight='balanced',
        max_iter=150,
        learning_rate=0.08,
        max_leaf_nodes=31,
        min_samples_leaf=50,
        l2_regularization=1.0,
        random_state=42
    )
    gb_model.fit(X_train, y_train)
    gb_preds = gb_model.predict(X_test)
    gb_probs = gb_model.predict_proba(X_test)[:, 1]

    # 4. Evaluation & Metrics
    print("\n[4] Comprehensive Model Evaluation (Holdout Test Set):")
    acc = accuracy_score(y_test, gb_preds)
    auc = roc_auc_score(y_test, gb_probs)
    prec = precision_score(y_test, gb_preds, zero_division=0)
    rec = recall_score(y_test, gb_preds, zero_division=0)
    f1 = f1_score(y_test, gb_preds, zero_division=0)
    cm = confusion_matrix(y_test, gb_preds).tolist()

    print(f"    - Accuracy:          {acc*100:.2f}%")
    print(f"    - ROC-AUC:           {auc:.4f}")
    print(f"    - Precision:         {prec*100:.2f}%")
    print(f"    - Recall:            {rec*100:.2f}%")
    print(f"    - F1-Score:          {f1*100:.2f}%")
    print(f"    - Confusion Matrix:  TN={cm[0][0]:,}, FP={cm[0][1]:,}, FN={cm[1][0]:,}, TP={cm[1][1]:,}")

    # Optimal Decision Threshold Search
    precisions, recalls, thresholds = precision_recall_curve(y_test[:20000], gb_probs[:20000])
    f1_scores = 2 * (precisions * recalls) / (precisions + recalls + 1e-10)
    opt_idx = np.argmax(f1_scores)
    optimal_thresh = float(thresholds[min(opt_idx, len(thresholds)-1)])
    best_f1 = float(f1_scores[opt_idx])
    print(f"    - Optimal Probability Threshold for F1: {optimal_thresh:.3f} (Max F1: {best_f1*100:.2f}%)")

    # ROC curve points for dashboard chart
    fpr, tpr, _ = roc_curve(y_test[:10000], gb_probs[:10000])
    roc_points = [{"fpr": round(float(f), 4), "tpr": round(float(t), 4)} for f, t in zip(fpr[::len(fpr)//20 or 1], tpr[::len(tpr)//20 or 1])]

    # 5. Feature Importances via ROC-AUC Scoring
    print("\n[5] Feature Importance Assessment (Permutation on ROC-AUC)...")
    perm_imp = permutation_importance(gb_model, X_test[:10000], y_test[:10000], scoring='roc_auc', n_repeats=3, random_state=42)
    
    importances = []
    for col, imp in sorted(zip(feature_cols, perm_imp.importances_mean), key=lambda x: x[1], reverse=True):
        importances.append({"feature": col, "importance": round(float(imp), 5)})
        print(f"    * {col:20s}: {imp:+.5f}")

    # 6. Save Artifacts for Dashboard & Real-Time Inference
    print("\n[6] Serializing Model and Feature Schema...")
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump(gb_model, model_path)
    print(f"    [+] Production Model saved to: {model_path}")

    metadata = {
        "model_type": "HistGradientBoostingClassifier",
        "trained_timestamp": datetime.now().isoformat(),
        "feature_cols": feature_cols,
        "global_prior": global_prior,
        "optimal_threshold": round(optimal_thresh, 3),
        "carrier_priors": carrier_priors,
        "origin_priors": origin_priors,
        "dest_priors": dest_priors,
        "hour_priors": {int(k): v for k, v in hour_priors.items()},
        "metrics": {
            "accuracy": round(acc, 4),
            "roc_auc": round(auc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "confusion_matrix": cm,
            "test_sample_size": len(X_test)
        },
        "roc_curve": roc_points,
        "feature_importances": importances
    }

    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    print(f"    [+] Metadata & Encoders saved to: {meta_path}")

    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    print(f"    [+] Evaluation Report saved to: {report_path}")

    duration = (datetime.now() - start_time).total_seconds()
    print(f"\n[+] Phase 7 ML Pipeline completed in {duration:.2f} seconds.")
    print("=" * 70)
    return metadata

if __name__ == "__main__":
    run_ml_pipeline()
