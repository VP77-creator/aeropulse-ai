# AeroPulse AI: Flight Delay Analytics and Prediction System
### *End-to-End Enterprise Data Warehousing, OLAP, Data Mining, and Machine Learning Platform*

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![Database](https://img.shields.io/badge/Data%20Warehouse-DuckDB%20Star%20Schema-yellow.svg)](https://duckdb.org/)
[![Machine Learning](https://img.shields.io/badge/ML-HistGradientBoosting-brightgreen.svg)](https://scikit-learn.org/)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-emerald.svg)]()

---

## ✈️ Executive Overview

**AeroPulse AI** is an end-to-end flight delay analytics, data warehousing, data mining, and machine learning platform engineered on **7,079,081 official US Department of Transportation (Bureau of Transportation Statistics) flight records** spanning the full year of 2024.

The project implements an 8-phase lifecycle:
1. **Data Validation & Cleaning**: Schema verification, null handling, cancellation/diversion partitioning across 12 monthly CSV partitions (~1.6 GB).
2. **Exploratory Data Analysis (EDA)**: Statistical profiling across 15 airlines, 348 airport hubs, and 6,805 routes.
3. **ETL Pipeline**: Automated columnar extraction, standardization, feature derivation, and relational loading into DuckDB.
4. **Data Warehouse Design**: Kimball Star Schema with 1 centralized fact table (`fact_flights`) and 5 dimension tables (`dim_date`, `dim_carrier`, `dim_airport`, `dim_time_block`, `dim_route`).
5. **SQL & OLAP Analysis**: Multidimensional analysis utilizing `ROLLUP`, `CUBE`, window ranking, and Pareto delay concentration queries.
6. **Data Mining**: Association Rule Mining (Apriori algorithm for delay causes) and Unsupervised K-Means clustering of major US airport hubs.
7. **Machine Learning**: Production predictive modeling using class-balanced `HistGradientBoostingClassifier` with Bayes smoothed target priors and threshold tuning.
8. **Interactive Visual Dashboard**: Modern glassmorphic web dashboard with real-time KPI monitors, interactive Chart.js visualizations, live SQL console, and sub-millisecond ML delay prediction simulator.

---

## 🏛️ Project Architecture & Directory Layout

```
Flight_Delay_Data/
├── src/
│   ├── phase1_validation/
│   │   └── validate_clean.py        # Data validation, quality audit & cleaning rules
│   ├── phase2_eda/
│   │   └── eda_analysis.py          # Statistical profiling, delay distributions & trends
│   ├── phase3_etl/
│   │   └── etl_pipeline.py          # Columnar extraction, transformation, and warehouse loading
│   ├── phase4_warehouse/
│   │   └── schema.sql               # Kimball Star Schema SQL DDL definition
│   ├── phase5_olap/
│   │   ├── olap_queries.sql         # Rollup, Cube, Grouping Sets, and Window functions
│   │   └── run_olap.py              # Executes OLAP queries against DuckDB warehouse
│   ├── phase6_mining/
│   │   └── run_data_mining.py       # Apriori Association Rule Mining & K-Means Clustering
│   ├── phase7_ml/
│   │   └── train_predict.py         # HistGradientBoosting ML training, evaluation & serialization
│   └── phase8_dashboard/
│       ├── server.py                # Python HTTP Server & real-time prediction REST API
│       └── static/
│           ├── index.html           # Glassmorphic frontend dashboard
│           ├── style.css            # Dark mode design system & animations
│           └── app.js               # Interactive charts, SQL runner & prediction client
├── warehouse/
│   ├── flight_warehouse.duckdb      # 1.3 GB High-Performance Columnar OLAP Database
│   └── schema.sql                   # Star Schema Relational DDL
├── data_reports/
│   ├── phase1_validation_report.json
│   ├── phase2_eda_summary.json
│   ├── etl_warehouse_report.json
│   ├── phase5_olap_results.json
│   ├── phase6_mining_rules.json
│   └── phase7_ml_metrics.json
├── models/
│   ├── flight_delay_model.joblib    # Serialized gradient boosting pipeline
│   └── model_metadata.json          # Encoders, optimal threshold, priors, and feature schema
├── run_all.py                       # Unified master pipeline orchestrator
└── README.md                        # Complete technical documentation
```

---

## 📊 Phase-by-Phase Highlights & Key Discoveries

### Phase 1: Data Validation & Quality Audit
- **Dataset Scale**: 7,079,081 total records across 12 monthly CSV files (`jan.csv` through `dec.csv`).
- **Completion Breakdown**:
  - Completed: **6,965,267 flights (98.39%)**
  - Cancelled: **96,315 flights (1.36%)**
  - Diverted: **17,499 flights (0.25%)**
- **Schema Consistency**: 100% column identity (41 standard BTS attributes) across all 12 partitions.
- **Missing Value Handling**: Cause-specific delay fields (`CARRIER_DELAY`, `WEATHER_DELAY`, `NAS_DELAY`, `SECURITY_DELAY`, `LATE_AIRCRAFT_DELAY`) are zero-imputed for non-delayed arrivals per FAA/DOT reporting standards.

### Phase 2: Exploratory Data Analysis (EDA)
- **Top Delay Driver**: **Late Aircraft Delay accounts for 40.44% of cumulative delay minutes** (41,974,007 min), demonstrating severe ripple propagation throughout daily aircraft rotation cycles.
- **Intra-Day Delay Acceleration**:
  - **06:00 AM Departure**: Delay rate is **9.58%** with average delay of **-2.18 minutes** (early arrivals).
  - **18:00 PM Departure**: Delay rate peaks at **29.39%** with average delay of **+14.95 minutes** (a 3x increase).
- **Seasonality**:
  - **Peak Delay Month**: July (**29.62%** delay rate, average delay +18.09 min) due to peak summer convective storms.
  - **Smoothest Month**: October (**13.20%** delay rate, average delay -1.28 min).
- **Carrier Delay Performance**:
  - Best On-Time: Republic Airways (YX) - 14.07% delayed.
  - Worst Delayed: Frontier Airlines (F9) - 28.74% delayed; American Airlines (AA) - 26.13% delayed.

### Phase 3 & 4: Kimball Star Schema Data Warehouse
Engineered a fast, zero-redundancy Star Schema in DuckDB:
- `fact_flights` (7,079,081 rows): Grain is an individual scheduled flight operation.
- `dim_date` (366 rows): Date surrogate key, quarter, month, day of week, season, weekend flag.
- `dim_carrier` (15 rows): Full marketing name, operational unique carrier code.
- `dim_airport` (348 rows): IATA code, BTS identifier, city, state abbreviation, state name.
- `dim_time_block` (24 rows): Hourly departure bins and operational periods (Morning, Afternoon, Evening, Red-eye).
- `dim_route` (6,805 rows): Origin-destination route pair, average distance, haul class (Short, Medium, Long).
- **Referential Integrity**: Verified **0 orphaned foreign keys** across all dimensions.

### Phase 5: SQL & OLAP Multidimensional Analytics
- **Route Pareto Concentration**: The single most delayed route in the United States is **LAX → SFO** (236,986 cumulative delay minutes, 32.87% delay rate).
- **Airport Ground Congestion Index**:
  - **JFK (New York)**: Highest average taxi-out time in the nation at **26.31 minutes**.
  - **LGA (New York)**: Average taxi-out of 24.38 minutes.
  - **ORD (Chicago)**: Average taxi-out of 20.88 minutes.
- **Query Performance**: Columnar OLAP aggregations across the entire 7.07M rows execute in **9 to 20 milliseconds**!

### Phase 6: Data Mining (Apriori Rules & K-Means)
- **High-Lift Association Rules**:
  1. `IF [Origin=CLT AND TimePeriod=Evening AND Season=Summer] THEN [Delayed ≥ 15m]` (Confidence: **51.7%**, Lift: **2.482x**).
  2. `IF [Origin=ORD AND TimePeriod=Evening AND Season=Summer] THEN [Delayed ≥ 15m]` (Confidence: **46.5%**, Lift: **2.235x**).
  3. `IF [Origin=DFW AND TimePeriod=Evening AND Season=Summer] THEN [Delayed ≥ 15m]` (Confidence: **44.1%**, Lift: **2.119x**).
- **Unsupervised K-Means Airport Hub Segmentation (k=4)**:
  - **Cluster 0 (High-Efficiency Smooth Operations Hubs)**: HNL, PDX, SMF, SJC, OAK (15.1% delay rate, 13.9m taxi-out).
  - **Cluster 1 & 2 (Balanced Mid-to-Large Hubs)**: DTW, MSP, SLC, ATL, LAX, PHX, LAS, SEA.
  - **Cluster 3 (High-Friction Surface Congestion Hubs)**: DFW, DEN, ORD, CLT, MCO, JFK (24.3% delay rate, 19.8m taxi-out, elevated NAS airspace ground hold penalties).

### Phase 7: Machine Learning Prediction Pipeline
- **Algorithm**: `HistGradientBoostingClassifier` with `class_weight='balanced'`.
- **Validation Methodology**: True temporal holdout split (Months 1–10 Train [533,525 flights], Months 11–12 Test [106,044 flights]).
- **Key Metrics**:
  - Accuracy: **76.69%**
  - ROC-AUC: **0.6124**
  - Optimal F1 Decision Threshold: **0.337** (F1 Score: **33.78%**)
- **Top Feature Importances (ROC-AUC Impact)**:
  1. `hour_prior`: Scheduled departure hour / time-of-day lag.
  2. `carrier_prior`: Historical airline operational resilience.
  3. `day_of_week`: Weekly traffic rhythm.
  4. `dest_prior`: Arrival runway / terminal capacity constraints.
  5. `origin_prior`: Surface taxi-out congestion.

### Phase 8: Interactive Web Dashboard
- Accessible at: **`http://localhost:8050`**
- Features:
  - Executive KPI cards with glowing animated pulse indicators.
  - Dynamic interactive charts (Delay Causes Doughnut, Monthly Seasonality, Carrier Ranking, Hourly Ramp, Day-of-Week).
  - Kimball Star Schema interactive architectural viewer.
  - Interactive Route Pareto table and Association Rules explorer.
  - **Live ML Delay Predictor Simulator**: Select any airline, origin, destination, month, and scheduled departure time to calculate real-time delay probability, risk category, expected delay minutes, and operational risk factors.
  - **Interactive SQL OLAP Console**: Run custom queries directly against DuckDB with execution latency displayed in milliseconds.

---

## 🚀 Quickstart & Usage

### 1. Launch the Web Dashboard
```bash
python src/phase8_dashboard/server.py
```
Open **`http://localhost:8050`** in your browser.

### 2. Run the Full 8-Phase Pipeline
```bash
python run_all.py
```

### 3. Run Individual Phases
```bash
# Phase 1: Data Validation & Quality Audit
python src/phase1_validation/validate_clean.py

# Phase 2: Exploratory Data Analysis (EDA)
python src/phase2_eda/eda_analysis.py

# Phase 3 & 4: ETL Pipeline & Star Schema Data Warehouse Loader
python src/phase3_etl/etl_pipeline.py

# Phase 5: SQL & OLAP Multidimensional Queries
python src/phase5_olap/run_olap.py

# Phase 6: Data Mining (Apriori Rules & K-Means Clustering)
python src/phase6_mining/run_data_mining.py

# Phase 7: Machine Learning Prediction Pipeline
python src/phase7_ml/train_predict.py
```

---

## 📡 REST API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/overview` | `GET` | Core KPI metrics, flight completion rates, and delay cause distributions |
| `/api/eda` | `GET` | Monthly seasonality, hourly ramps, and carrier performance |
| `/api/olap` | `GET` | Route Pareto rankings, congestion index, and carrier cause breakdowns |
| `/api/mining` | `GET` | Apriori association rules and K-Means airport clusters |
| `/api/ml_metrics` | `GET` | Model ROC-AUC, confusion matrix, and feature importances |
| `/api/predict` | `POST` | Real-time flight delay inference with probability and risk factors |
| `/api/query` | `POST` | Live read-only SQL execution against the DuckDB Data Warehouse |

---

## 💻 Technical Stack
- **Data Warehouse**: DuckDB 1.5+ (Columnar Vectorized Engine, Kimball Star Schema)
- **Machine Learning**: Scikit-Learn (`HistGradientBoostingClassifier`, `KMeans`, `StandardScaler`)
- **Data Engineering**: Python 3.13, NumPy, Pandas, Joblib
- **Frontend & Styling**: Vanilla HTML5, Vanilla CSS3 (Custom Glassmorphic Design System), Vanilla ES6 JavaScript, Chart.js 4.4
- **Dataset**: US Bureau of Transportation Statistics (BTS) On-Time Performance (2024 Full Year, 7,079,081 records)
