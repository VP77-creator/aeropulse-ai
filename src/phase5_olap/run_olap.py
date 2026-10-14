"""
Phase 5: SQL & OLAP Execution Engine
Flight Delay Analytics and Prediction System
"""

import os
import json
import duckdb
from datetime import datetime

def run_olap_suite(db_path="warehouse/flight_warehouse.duckdb", output_report="data_reports/phase5_olap_results.json"):
    print("=" * 70)
    print("PHASE 5: SQL & OLAP MULTIDIMENSIONAL ANALYSIS")
    print("=" * 70)
    start_time = datetime.now()
    
    conn = duckdb.connect(db_path, read_only=True)
    print(f"Connected to Warehouse at: {db_path}")

    # 1. Carrier by Month Performance
    print("\n[1] Executing OLAP Query 1: Carrier & Seasonality Matrix...")
    q1 = """
        SELECT 
            d.month,
            d.month_name,
            c.carrier_code,
            c.carrier_name,
            count(*) as total_flights,
            sum(f.arr_del15) as delayed_flights,
            round(sum(f.arr_del15) * 100.0 / nullif(count(*), 0), 2) as delay_rate_pct,
            round(avg(f.arr_delay), 2) as avg_arr_delay_min,
            round(avg(f.dep_delay), 2) as avg_dep_delay_min,
            round(sum(f.cancelled) * 100.0 / nullif(count(*), 0), 2) as cancel_rate_pct
        FROM fact_flights f
        JOIN dim_carrier c ON f.carrier_key = c.carrier_key
        JOIN dim_date d ON f.date_key = d.date_key
        WHERE f.cancelled = 0 AND f.diverted = 0
        GROUP BY d.month, d.month_name, c.carrier_code, c.carrier_name
        ORDER BY d.month, total_flights DESC;
    """
    df1 = conn.execute(q1).fetchdf()
    print(f"    [+] Computed {len(df1)} airline-month dimensional cells.")

    # 2. State & Airport Hierarchical Drill-Down
    print("\n[2] Executing OLAP Query 2: State & Airport Hub Drill-Down...")
    q2 = """
        SELECT 
            a.state_abr,
            a.state_name,
            a.iata_code,
            a.city_name,
            count(*) as total_departures,
            sum(f.arr_del15) as delayed_flights,
            round(sum(f.arr_del15) * 100.0 / nullif(count(*), 0), 2) as delay_rate_pct,
            round(avg(f.dep_delay), 2) as avg_dep_delay_min,
            round(avg(f.taxi_out), 2) as avg_taxi_out_min
        FROM fact_flights f
        JOIN dim_airport a ON f.origin_key = a.airport_key
        WHERE f.cancelled = 0 AND f.diverted = 0
        GROUP BY a.state_abr, a.state_name, a.iata_code, a.city_name
        HAVING count(*) >= 10000
        ORDER BY total_departures DESC;
    """
    df2 = conn.execute(q2).fetchdf()
    print(f"    [+] Computed {len(df2)} major airport hubs.")

    # 3. Route Pareto Analysis
    print("\n[3] Executing OLAP Query 3: Route Delay Pareto Analysis...")
    q3 = """
        WITH route_delays AS (
            SELECT 
                r.route_name,
                r.origin_code,
                r.dest_code,
                r.distance_group,
                count(*) as total_flights,
                sum(f.arr_del15) as delayed_flights,
                round(sum(f.arr_del15) * 100.0 / nullif(count(*), 0), 2) as delay_rate_pct,
                round(sum(CASE WHEN f.arr_delay > 0 THEN f.arr_delay ELSE 0 END), 0) as total_delay_mins,
                round(avg(f.arr_delay), 2) as avg_arr_delay_min
            FROM fact_flights f
            JOIN dim_route r ON f.route_key = r.route_key
            WHERE f.cancelled = 0 AND f.diverted = 0
            GROUP BY r.route_name, r.origin_code, r.dest_code, r.distance_group
        )
        SELECT 
            route_name,
            origin_code,
            dest_code,
            distance_group,
            total_flights,
            delayed_flights,
            delay_rate_pct,
            total_delay_mins,
            avg_arr_delay_min,
            round(sum(total_delay_mins) OVER (ORDER BY total_delay_mins DESC) * 100.0 / 
                  nullif(sum(total_delay_mins) OVER (), 0), 2) as cumulative_delay_pct,
            DENSE_RANK() OVER (ORDER BY total_delay_mins DESC) as delay_rank
        FROM route_delays
        ORDER BY total_delay_mins DESC
        LIMIT 30;
    """
    df3 = conn.execute(q3).fetchdf()
    print(f"    [+] Top route with highest cumulative delay: {df3.iloc[0]['route_name']} ({df3.iloc[0]['total_delay_mins']:,.0f} min)")

    # 4. Day of Week x Hour Heatmap Cube
    print("\n[4] Executing OLAP Query 4: Day x Time Block Cube...")
    q4 = """
        SELECT 
            d.day_name,
            d.day_of_week,
            t.time_block_key as hour,
            t.hour_label,
            t.period_name,
            count(*) as total_flights,
            sum(f.arr_del15) as delayed_flights,
            round(sum(f.arr_del15) * 100.0 / nullif(count(*), 0), 2) as delay_rate_pct,
            round(avg(f.arr_delay), 2) as avg_arr_delay_min
        FROM fact_flights f
        JOIN dim_date d ON f.date_key = d.date_key
        JOIN dim_time_block t ON f.time_block_key = t.time_block_key
        WHERE f.cancelled = 0 AND f.diverted = 0
        GROUP BY d.day_name, d.day_of_week, t.time_block_key, t.hour_label, t.period_name
        ORDER BY d.day_of_week, t.time_block_key;
    """
    df4 = conn.execute(q4).fetchdf()
    print(f"    [+] Computed {len(df4)} temporal cells across the week.")

    # 5. Delay Causes by Carrier
    print("\n[5] Executing OLAP Query 5: Delay Causation Decomposition by Carrier...")
    q5 = """
        SELECT 
            c.carrier_code,
            c.carrier_name,
            count(*) as delayed_flights,
            round(sum(f.carrier_delay), 0) as carrier_mins,
            round(sum(f.weather_delay), 0) as weather_mins,
            round(sum(f.nas_delay), 0) as nas_mins,
            round(sum(f.security_delay), 0) as security_mins,
            round(sum(f.late_aircraft_delay), 0) as late_aircraft_mins,
            round(sum(f.carrier_delay + f.weather_delay + f.nas_delay + f.security_delay + f.late_aircraft_delay), 0) as total_mins,
            round(sum(f.carrier_delay) * 100.0 / nullif(sum(f.carrier_delay + f.weather_delay + f.nas_delay + f.security_delay + f.late_aircraft_delay), 0), 2) as carrier_pct,
            round(sum(f.weather_delay) * 100.0 / nullif(sum(f.carrier_delay + f.weather_delay + f.nas_delay + f.security_delay + f.late_aircraft_delay), 0), 2) as weather_pct,
            round(sum(f.nas_delay) * 100.0 / nullif(sum(f.carrier_delay + f.weather_delay + f.nas_delay + f.security_delay + f.late_aircraft_delay), 0), 2) as nas_pct,
            round(sum(f.late_aircraft_delay) * 100.0 / nullif(sum(f.carrier_delay + f.weather_delay + f.nas_delay + f.security_delay + f.late_aircraft_delay), 0), 2) as late_aircraft_pct
        FROM fact_flights f
        JOIN dim_carrier c ON f.carrier_key = c.carrier_key
        WHERE f.arr_del15 = 1
        GROUP BY c.carrier_code, c.carrier_name
        ORDER BY total_mins DESC;
    """
    df5 = conn.execute(q5).fetchdf()
    print(f"    [+] Decomposed delay causes across all {len(df5)} airlines.")

    # 6. Airport Congestion & Taxi-out Index
    print("\n[6] Executing OLAP Query 6: Surface Congestion & NAS Friction Index...")
    q6 = """
        SELECT 
            a.iata_code,
            a.city_name,
            a.state_abr,
            count(*) as total_departures,
            round(avg(f.taxi_out), 2) as avg_taxi_out_min,
            round(avg(f.dep_delay), 2) as avg_dep_delay_min,
            round(sum(f.nas_delay) * 1.0 / count(*), 2) as avg_nas_delay_per_dep,
            round(sum(f.arr_del15) * 100.0 / count(*), 2) as delay_rate_pct
        FROM fact_flights f
        JOIN dim_airport a ON f.origin_key = a.airport_key
        WHERE f.cancelled = 0 AND f.diverted = 0
        GROUP BY a.iata_code, a.city_name, a.state_abr
        HAVING count(*) >= 25000
        ORDER BY avg_taxi_out_min DESC
        LIMIT 20;
    """
    df6 = conn.execute(q6).fetchdf()
    print(f"    [+] Airport with highest departure taxi: {df6.iloc[0]['iata_code']} ({df6.iloc[0]['avg_taxi_out_min']} min)")

    duration = (datetime.now() - start_time).total_seconds()
    results = {
        "execution_timestamp": datetime.now().isoformat(),
        "duration_seconds": round(duration, 2),
        "carrier_month_cube": df1.to_dict(orient='records'),
        "state_airport_drilldown": df2.to_dict(orient='records'),
        "route_pareto": df3.to_dict(orient='records'),
        "day_hour_cube": df4.to_dict(orient='records'),
        "carrier_cause_decomposition": df5.to_dict(orient='records'),
        "airport_congestion_index": df6.to_dict(orient='records')
    }

    os.makedirs(os.path.dirname(output_report), exist_ok=True)
    with open(output_report, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    print(f"\n[+] OLAP execution complete in {duration:.2f} seconds.")
    print(f"[+] Results saved to: {output_report}")
    print("=" * 70)
    return results

if __name__ == "__main__":
    run_olap_suite()
