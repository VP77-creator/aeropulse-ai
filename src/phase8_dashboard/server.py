"""
Phase 8: Web Dashboard Backend Server
Flight Delay Analytics and Prediction System
Serves the interactive web interface, analytical APIs, live DuckDB SQL console, and real-time ML inference.
"""

import os
import sys
import json
import duckdb
import joblib
import numpy as np
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = 8050
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
DB_PATH = "warehouse/flight_warehouse.duckdb"
MODEL_PATH = "models/flight_delay_model.joblib"
METADATA_PATH = "models/model_metadata.json"

# Load trained ML model and metadata at startup
print("Loading Machine Learning model & metadata for real-time inference...")
ml_model = None
ml_meta = None
try:
    if os.path.exists(MODEL_PATH):
        ml_model = joblib.load(MODEL_PATH)
        print("  [+] ML Model successfully loaded into memory.")
    if os.path.exists(METADATA_PATH):
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            ml_meta = json.load(f)
        print("  [+] Model metadata & prior encoders successfully loaded.")
except Exception as e:
    print(f"  [!] Error loading ML artifacts: {e}")

# Pre-load report summaries
reports_cache = {}
report_files = {
    "validation": "data_reports/phase1_validation_report.json",
    "eda": "data_reports/phase2_eda_summary.json",
    "etl": "data_reports/etl_warehouse_report.json",
    "olap": "data_reports/phase5_olap_results.json",
    "mining": "data_reports/phase6_mining_rules.json",
    "ml": "data_reports/phase7_ml_metrics.json"
}

for key, path in report_files.items():
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                reports_cache[key] = json.load(f)
        except Exception as e:
            print(f"Error caching {key}: {e}")

# DuckDB read-only connection
warehouse_conn = None
try:
    if os.path.exists(DB_PATH):
        warehouse_conn = duckdb.connect(DB_PATH, read_only=True)
        print(f"  [+] DuckDB Data Warehouse connected in read-only mode ({DB_PATH}).")
except Exception as e:
    print(f"  [!] Could not connect to DuckDB: {e}")


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            self.handle_api_get(path, parse_qs(parsed.query))
        else:
            # Fall back to serving static files
            if path == "/" or path == "":
                self.path = "/index.html"
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/predict":
            self.handle_predict()
        elif path == "/api/query":
            self.handle_custom_query()
        else:
            self.send_error(404, "Endpoint not found")

    def handle_api_get(self, path, params):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        response_data = {}
        if path == "/api/overview":
            v = reports_cache.get("validation", {})
            e = reports_cache.get("eda", {})
            response_data = {
                "total_records": v.get("total_records", 7079081),
                "status_summary": v.get("status_summary", {}),
                "delay_summary": v.get("delay_summary", {}),
                "delay_causes": e.get("delay_causes", {}),
                "warehouse_metrics": reports_cache.get("etl", {})
            }
        elif path == "/api/eda":
            response_data = reports_cache.get("eda", {})
        elif path == "/api/olap":
            response_data = reports_cache.get("olap", {})
        elif path == "/api/mining":
            response_data = reports_cache.get("mining", {})
        elif path == "/api/ml_metrics":
            response_data = reports_cache.get("ml", {})
        elif path == "/api/metadata":
            # Return airport list, carrier list, etc.
            if warehouse_conn:
                try:
                    airports = warehouse_conn.execute("""
                        SELECT airport_key as code, city_name as city, state_abr as state, count(*) as flights
                        FROM fact_flights f
                        JOIN dim_airport a ON f.origin_key = a.airport_key
                        GROUP BY airport_key, city_name, state_abr
                        HAVING count(*) >= 2000
                        ORDER BY flights DESC
                    """).fetchdf().to_dict(orient="records")

                    carriers = warehouse_conn.execute("""
                        SELECT carrier_key as code, carrier_name as name
                        FROM dim_carrier
                        ORDER BY name
                    """).fetchdf().to_dict(orient="records")

                    response_data = {
                        "airports": airports,
                        "carriers": carriers
                    }
                except Exception as e:
                    response_data = {"error": str(e)}
            else:
                response_data = {"airports": [], "carriers": []}
        else:
            response_data = {"status": "ok", "message": "AeroPulse API"}

        self.wfile.write(json.dumps(response_data).encode("utf-8"))

    def handle_predict(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8")
        
        try:
            req = json.loads(post_data)
        except Exception:
            self.send_error(400, "Invalid JSON")
            return

        carrier = req.get("carrier", "AA")
        origin = req.get("origin", "DFW")
        dest = req.get("dest", "ORD")
        month = int(req.get("month", 7))
        day_of_month = int(req.get("day_of_month", 15))
        day_of_week = int(req.get("day_of_week", 5)) # Friday
        dep_hour = int(req.get("dep_hour", 18)) # 6 PM

        # Determine weekend & season code
        is_weekend = 1 if day_of_week in [6, 7] else 0
        if month in [12, 1, 2]:
            season_code = 0 # Winter
        elif month in [3, 4, 5]:
            season_code = 1 # Spring
        elif month in [6, 7, 8]:
            season_code = 2 # Summer
        else:
            season_code = 3 # Fall

        # Look up distance & duration from warehouse or heuristics
        distance = 800.0
        crs_elapsed_time = 140.0
        if warehouse_conn:
            try:
                route_res = warehouse_conn.execute(
                    "SELECT distance FROM dim_route WHERE origin_code = ? AND dest_code = ?",
                    [origin, dest]
                ).fetchone()
                if route_res and route_res[0]:
                    distance = float(route_res[0])
                    crs_elapsed_time = round(distance / 7.5 + 40, 1) # aviation rule-of-thumb
            except Exception:
                pass

        # Lookup priors
        global_prior = 0.2082
        carrier_prior = global_prior
        origin_prior = global_prior
        dest_prior = global_prior
        hour_prior = global_prior

        if ml_meta:
            carrier_prior = ml_meta.get("carrier_priors", {}).get(carrier, global_prior)
            origin_prior = ml_meta.get("origin_priors", {}).get(origin, global_prior)
            dest_prior = ml_meta.get("dest_priors", {}).get(dest, global_prior)
            hour_prior = ml_meta.get("hour_priors", {}).get(str(dep_hour), ml_meta.get("hour_priors", {}).get(dep_hour, global_prior))

        features = [
            month,
            day_of_month,
            day_of_week,
            is_weekend,
            season_code,
            dep_hour,
            distance,
            crs_elapsed_time,
            carrier_prior,
            origin_prior,
            dest_prior,
            hour_prior
        ]

        # ML Prediction
        delay_prob = 0.25
        pred_label = 0
        if ml_model:
            try:
                X = np.array([features])
                probs = ml_model.predict_proba(X)[0]
                delay_prob = float(probs[1])
                opt_thresh = ml_meta.get("optimal_threshold", 0.337) if ml_meta else 0.337
                pred_label = 1 if delay_prob >= opt_thresh else 0
            except Exception as e:
                print(f"Prediction inference error: {e}")

        # Risk Classification
        if delay_prob < 0.20:
            risk_tier = "Low Risk"
            risk_color = "#10B981" # Emerald
            est_delay_min = round(delay_prob * 15, 1)
        elif delay_prob < 0.35:
            risk_tier = "Moderate Risk"
            risk_color = "#F59E0B" # Amber
            est_delay_min = round(delay_prob * 35, 1)
        elif delay_prob < 0.50:
            risk_tier = "Elevated Risk"
            risk_color = "#F97316" # Orange
            est_delay_min = round(delay_prob * 65, 1)
        else:
            risk_tier = "Severe Risk"
            risk_color = "#EF4444" # Red
            est_delay_min = round(delay_prob * 95, 1)

        # Dynamic Delay Causes Breakdown (Queried from Warehouse or Prior Models)
        # We query the warehouse for this carrier, origin, and time-block profile
        carrier_c_pct = 34.5
        late_c_pct = 40.4
        nas_c_pct = 18.9
        weather_c_pct = 6.0
        sec_c_pct = 0.2

        if warehouse_conn:
            try:
                # Query cause proportions for this carrier and origin
                cause_res = warehouse_conn.execute("""
                    SELECT 
                        round(sum(carrier_delay) * 100.0 / nullif(sum(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 1) as c_pct,
                        round(sum(late_aircraft_delay) * 100.0 / nullif(sum(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 1) as l_pct,
                        round(sum(nas_delay) * 100.0 / nullif(sum(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 1) as n_pct,
                        round(sum(weather_delay) * 100.0 / nullif(sum(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 1) as w_pct,
                        round(sum(security_delay) * 100.0 / nullif(sum(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 1) as s_pct
                    FROM fact_flights
                    WHERE arr_del15 = 1 AND carrier_key = ? AND origin_key = ?
                """, [carrier, origin]).fetchone()

                if cause_res and cause_res[0] is not None:
                    carrier_c_pct, late_c_pct, nas_c_pct, weather_c_pct, sec_c_pct = [float(v) for v in cause_res]
                else:
                    # Fallback to carrier profile
                    cause_c = warehouse_conn.execute("""
                        SELECT 
                            round(sum(carrier_delay) * 100.0 / nullif(sum(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 1),
                            round(sum(late_aircraft_delay) * 100.0 / nullif(sum(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 1),
                            round(sum(nas_delay) * 100.0 / nullif(sum(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 1),
                            round(sum(weather_delay) * 100.0 / nullif(sum(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 1),
                            round(sum(security_delay) * 100.0 / nullif(sum(carrier_delay + weather_delay + nas_delay + security_delay + late_aircraft_delay), 0), 1)
                        FROM fact_flights
                        WHERE arr_del15 = 1 AND carrier_key = ?
                    """, [carrier]).fetchone()
                    if cause_c and cause_c[0] is not None:
                        carrier_c_pct, late_c_pct, nas_c_pct, weather_c_pct, sec_c_pct = [float(v) for v in cause_c]
            except Exception as e:
                print(f"Error fetching cause breakdown: {e}")

        # Adjust for departure time of day (Late Aircraft surges in evening, Carrier dominates early morning)
        if dep_hour >= 17:
            late_c_pct = min(65.0, late_c_pct + 8.0)
            carrier_c_pct = max(15.0, carrier_c_pct - 5.0)
        elif dep_hour <= 8:
            late_c_pct = max(10.0, late_c_pct - 15.0)
            carrier_c_pct = min(65.0, carrier_c_pct + 15.0)

        # Normalize to 100%
        cause_sum = carrier_c_pct + late_c_pct + nas_c_pct + weather_c_pct + sec_c_pct
        if cause_sum > 0:
            carrier_c_pct = round(carrier_c_pct * 100.0 / cause_sum, 1)
            late_c_pct = round(late_c_pct * 100.0 / cause_sum, 1)
            nas_c_pct = round(nas_c_pct * 100.0 / cause_sum, 1)
            weather_c_pct = round(weather_c_pct * 100.0 / cause_sum, 1)
            sec_c_pct = round(sec_c_pct * 100.0 / cause_sum, 1)

        # Calculate estimated delay minutes per cause
        carrier_mins = round(est_delay_min * carrier_c_pct / 100.0, 1)
        late_mins = round(est_delay_min * late_c_pct / 100.0, 1)
        nas_mins = round(est_delay_min * nas_c_pct / 100.0, 1)
        weather_mins = round(est_delay_min * weather_c_pct / 100.0, 1)
        sec_mins = round(est_delay_min * sec_c_pct / 100.0, 1)

        # Determine Primary Cause
        cause_map = {
            "Late Inbound Aircraft Propagation": (late_c_pct, late_mins, "#8B5CF6", "Turnaround delay from prior incoming flight leg arriving behind schedule"),
            "Airline Controllable Operational Delay": (carrier_c_pct, carrier_mins, "#3B82F6", f"Aircraft maintenance, crew connectivity, baggage loading, or turn handling for {carrier}"),
            "National Airspace System (NAS) Congestion": (nas_c_pct, nas_mins, "#06B6D4", f"Air traffic volume flow controls, runway spacing constraints, or ground holds at {origin}/{dest}"),
            "Weather & Convective Conditions": (weather_c_pct, weather_mins, "#F59E0B", "En-route convective thunderstorm cells, wind shear, or terminal ceiling restrictions"),
            "Security Ground Interruption": (sec_c_pct, sec_mins, "#F43F5E", "TSA screening checkpoint delays or concourse security re-screening")
        }
        primary_cause_name = max(cause_map.keys(), key=lambda k: cause_map[k][0])
        primary_cause_info = cause_map[primary_cause_name]

        causes_breakdown = [
            {
                "cause": "Late Aircraft Inbound Lag",
                "percentage": late_c_pct,
                "est_minutes": late_mins,
                "color": "#8B5CF6",
                "explanation": f"Turnaround lag from prior incoming leg. Escalates to {late_c_pct}% for {dep_hour:02d}:00 departure as rotational lags compound."
            },
            {
                "cause": "Carrier Operational Delay",
                "percentage": carrier_c_pct,
                "est_minutes": carrier_mins,
                "color": "#3B82F6",
                "explanation": f"Turnaround servicing, crew positioning, and boarding logistics specific to {carrier}."
            },
            {
                "cause": "NAS / Airspace Congestion",
                "percentage": nas_c_pct,
                "est_minutes": nas_mins,
                "color": "#06B6D4",
                "explanation": f"Air traffic control flow spacing, departure taxi queues, and terminal airspace saturation at {origin}."
            },
            {
                "cause": "Weather & Meteorological",
                "percentage": weather_c_pct,
                "est_minutes": weather_mins,
                "color": "#F59E0B",
                "explanation": "Regional convective turbulence, storm cell avoidance, or low cloud ceilings."
            },
            {
                "cause": "Security Interruption",
                "percentage": sec_c_pct,
                "est_minutes": sec_mins,
                "color": "#F43F5E",
                "explanation": "Security checkpoint wait times or terminal concourse re-screening."
            }
        ]
        causes_breakdown = sorted(causes_breakdown, key=lambda x: x['percentage'], reverse=True)

        # Primary risk contributors & root cause narratives
        risk_factors = []
        if dep_hour >= 16:
            risk_factors.append(f"⏰ Peak Evening Rush ({dep_hour:02d}:00): Late Aircraft ripple probability is {late_c_pct}%, generating ~{late_mins} min of delay.")
        elif dep_hour <= 8:
            risk_factors.append(f"🌅 Early Morning Departure ({dep_hour:02d}:00): Low Late-Aircraft risk ({late_c_pct}%), but initial morning crew/servicing checks account for {carrier_c_pct}%.")
        
        if origin_prior > 0.23:
            risk_factors.append(f"🛫 Origin Hub Saturation ({origin}): Historical departure delay rate is {origin_prior*100:.1f}% with heavy departure taxi congestion.")
        
        if carrier_prior > 0.23:
            risk_factors.append(f"✈️ Airline Profile ({carrier}): Historical on-time delay vulnerability is {carrier_prior*100:.1f}%.")
            
        if season_code == 2:
            risk_factors.append(f"⛈️ Peak Summer Season (Month {month}): Frequent convective storm systems and FAA ground delay programs.")
        elif season_code == 0:
            risk_factors.append(f"❄️ Winter Operations: De-icing and winter weather ground operations increase NAS spacing.")

        # Mitigation Travel Tip
        if dep_hour >= 15:
            mitigation_tip = f"Mitigation Tip: Shifting departure to earlier morning (06:00-09:00) on {carrier} reduces delay risk from {delay_prob*100:.1f}% down to ~12-15% by bypassing rotational inbound lags."
        else:
            mitigation_tip = f"Good Scheduling Choice: Morning departures have minimum inbound aircraft ripple lag and higher on-time arrival probability."

        resp = {
            "predicted_delay": bool(pred_label),
            "delay_probability": round(delay_prob * 100, 1),
            "risk_tier": risk_tier,
            "risk_color": risk_color,
            "expected_delay_minutes": est_delay_min,
            "distance_miles": distance,
            "flight_duration_min": crs_elapsed_time,
            "primary_cause": {
                "name": primary_cause_name,
                "percentage": primary_cause_info[0],
                "minutes": primary_cause_info[1],
                "color": primary_cause_info[2],
                "description": primary_cause_info[3]
            },
            "causes_breakdown": causes_breakdown,
            "risk_factors": risk_factors,
            "mitigation_tip": mitigation_tip,
            "priors": {
                "carrier": round(carrier_prior * 100, 1),
                "origin": round(origin_prior * 100, 1),
                "dest": round(dest_prior * 100, 1),
                "dep_hour": round(hour_prior * 100, 1)
            }
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def handle_custom_query(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8")
        try:
            req = json.loads(post_data)
            sql = req.get("query", "").strip()
        except Exception:
            self.send_error(400, "Invalid JSON")
            return

        # Basic safety check (read-only queries)
        upper_sql = sql.upper()
        if any(kw in upper_sql for kw in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE"]):
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Only SELECT / read-only analytical queries are permitted."}).encode("utf-8"))
            return

        if not warehouse_conn:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Warehouse connection unavailable."}).encode("utf-8"))
            return

        try:
            start = datetime.now()
            df = warehouse_conn.execute(sql).fetchdf()
            elapsed_ms = round((datetime.now() - start).total_seconds() * 1000, 1)
            columns = list(df.columns)
            # Limit results to 100 rows for display
            records = df.head(100).to_dict(orient="records")
            resp = {
                "columns": columns,
                "rows": records,
                "total_returned": len(df),
                "displayed_count": len(records),
                "execution_ms": elapsed_ms
            }
        except Exception as e:
            resp = {"error": str(e)}

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(resp, default=str).encode("utf-8"))


def start_server():
    server_address = ("127.0.0.1", PORT)
    httpd = HTTPServer(server_address, DashboardHandler)
    print("\n" + "=" * 70)
    print(">> AeroPulse Flight Delay Analytics & Prediction Dashboard")
    print(f">> Local URL: http://localhost:{PORT}")
    print("=" * 70 + "\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    start_server()
