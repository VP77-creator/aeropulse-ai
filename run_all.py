"""
AeroPulse AI: Master Pipeline Runner
Flight Delay Analytics and Prediction System
Executes all 8 phases sequentially or individually.
"""

import os
import sys
import argparse
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description="AeroPulse Flight Delay Analytics & Prediction System")
    parser.add_argument("--phase", type=str, default="all", 
                        choices=["1", "2", "3", "4", "5", "6", "7", "8", "all"],
                        help="Specify which phase to execute (1-8 or 'all')")
    parser.add_argument("--port", type=int, default=8050, help="Port for Phase 8 Dashboard Server")
    args = parser.parse_args()

    start_total = datetime.now()
    print("=" * 80)
    print("      AEROPULSE AI — FLIGHT DELAY ANALYTICS & PREDICTION SYSTEM")
    print("      Data Warehousing, Multidimensional OLAP, Mining & ML Platform")
    print("=" * 80)

    # Phase 1
    if args.phase in ["1", "all"]:
        from src.phase1_validation.validate_clean import run_phase1_validation
        run_phase1_validation()

    # Phase 2
    if args.phase in ["2", "all"]:
        from src.phase2_eda.eda_analysis import run_phase2_eda
        run_phase2_eda()

    # Phase 3 & 4
    if args.phase in ["3", "4", "all"]:
        from src.phase3_etl.etl_pipeline import run_etl
        run_etl()

    # Phase 5
    if args.phase in ["5", "all"]:
        from src.phase5_olap.run_olap import run_olap_suite
        run_olap_suite()

    # Phase 6
    if args.phase in ["6", "all"]:
        from src.phase6_mining.run_data_mining import run_phase6_mining
        run_phase6_mining()

    # Phase 7
    if args.phase in ["7", "all"]:
        from src.phase7_ml.train_predict import run_ml_pipeline
        run_ml_pipeline()

    # Phase 8
    if args.phase in ["8", "all"]:
        print("\n" + "=" * 80)
        print("PHASE 8: STARTING INTERACTIVE WEB DASHBOARD")
        print("=" * 80)
        from src.phase8_dashboard.server import start_server
        start_server()

    total_duration = (datetime.now() - start_total).total_seconds()
    print(f"\n[+] Total Pipeline execution finished in {total_duration:.2f} seconds.")

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
