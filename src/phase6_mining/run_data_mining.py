"""
Phase 6: Data Mining (Association Rule Mining & Clustering)
Flight Delay Analytics and Prediction System
"""

import os
import json
import duckdb
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

def run_association_rule_mining(conn, baseline_delay_rate, total_n):
    print("\n--- [1] Association Rule Mining for Flight Delays ---")
    print(f"Total Completed Flights (N): {total_n:,}")
    print(f"Baseline Flight Delay Rate: {baseline_delay_rate * 100:.2f}%")
    
    rules = []
    
    # Level 1 Rules: Single factor impacts
    print("Mining 1-item Antecedents -> {Delayed >= 15m}...")
    level1_query = f"""
        WITH flights AS (
            SELECT 
                c.carrier_code as carrier,
                f.origin_key as origin,
                t.period_name as time_period,
                d.season as season,
                CASE WHEN d.is_weekend THEN 'Weekend' ELSE 'Weekday' END as day_type,
                f.arr_del15 as is_delayed
            FROM fact_flights f
            JOIN dim_carrier c ON f.carrier_key = c.carrier_key
            JOIN dim_date d ON f.date_key = d.date_key
            JOIN dim_time_block t ON f.time_block_key = t.time_block_key
            WHERE f.cancelled = 0 AND f.diverted = 0
        )
        
        -- Carrier rules
        SELECT 
            'Carrier=' || carrier as antecedent,
            count(*) as total_matched,
            sum(is_delayed) as delay_matched,
            round(count(*) * 1.0 / {total_n}, 4) as support,
            round(sum(is_delayed) * 1.0 / count(*), 4) as confidence,
            round((sum(is_delayed) * 1.0 / count(*)) / {baseline_delay_rate}, 3) as lift
        FROM flights
        GROUP BY carrier
        HAVING count(*) >= 100000 AND (sum(is_delayed) * 1.0 / count(*)) > 0.22
        
        UNION ALL
        
        -- Time Period rules
        SELECT 
            'TimePeriod=' || time_period as antecedent,
            count(*) as total_matched,
            sum(is_delayed) as delay_matched,
            round(count(*) * 1.0 / {total_n}, 4) as support,
            round(sum(is_delayed) * 1.0 / count(*), 4) as confidence,
            round((sum(is_delayed) * 1.0 / count(*)) / {baseline_delay_rate}, 3) as lift
        FROM flights
        GROUP BY time_period
        HAVING (sum(is_delayed) * 1.0 / count(*)) > 0.22
        
        UNION ALL
        
        -- Season rules
        SELECT 
            'Season=' || season as antecedent,
            count(*) as total_matched,
            sum(is_delayed) as delay_matched,
            round(count(*) * 1.0 / {total_n}, 4) as support,
            round(sum(is_delayed) * 1.0 / count(*), 4) as confidence,
            round((sum(is_delayed) * 1.0 / count(*)) / {baseline_delay_rate}, 3) as lift
        FROM flights
        GROUP BY season
        HAVING (sum(is_delayed) * 1.0 / count(*)) > 0.22
        
        UNION ALL
        
        -- Origin airport rules (top hubs)
        SELECT 
            'Origin=' || origin as antecedent,
            count(*) as total_matched,
            sum(is_delayed) as delay_matched,
            round(count(*) * 1.0 / {total_n}, 4) as support,
            round(sum(is_delayed) * 1.0 / count(*), 4) as confidence,
            round((sum(is_delayed) * 1.0 / count(*)) / {baseline_delay_rate}, 3) as lift
        FROM flights
        GROUP BY origin
        HAVING count(*) >= 100000 AND (sum(is_delayed) * 1.0 / count(*)) > 0.22
        ORDER BY lift DESC;
    """
    df_l1 = conn.execute(level1_query).fetchdf()
    for _, r in df_l1.iterrows():
        rules.append({
            "antecedent": [r['antecedent']],
            "consequent": ["Delayed >= 15m"],
            "support": float(r['support']),
            "confidence": float(r['confidence']),
            "lift": float(r['lift']),
            "matched_flights": int(r['total_matched'])
        })
    print(f"    [+] Discovered {len(df_l1)} high-confidence 1-item pattern rules.")

    # Level 2 & 3 Rules: Multi-attribute combinations (Apriori candidate generation)
    print("Mining Multi-item Antecedents: {Origin, TimePeriod, Season, Carrier} -> {Delayed >= 15m}...")
    level2_query = f"""
        WITH flights AS (
            SELECT 
                c.carrier_code as carrier,
                f.origin_key as origin,
                t.period_name as time_period,
                d.season as season,
                f.arr_del15 as is_delayed
            FROM fact_flights f
            JOIN dim_carrier c ON f.carrier_key = c.carrier_key
            JOIN dim_date d ON f.date_key = d.date_key
            JOIN dim_time_block t ON f.time_block_key = t.time_block_key
            WHERE f.cancelled = 0 AND f.diverted = 0
        )

        -- Rule Type A: Origin + TimePeriod
        SELECT 
            origin,
            time_period,
            '' as carrier,
            '' as season,
            count(*) as total_matched,
            sum(is_delayed) as delay_matched,
            round(count(*) * 1.0 / {total_n}, 4) as support,
            round(sum(is_delayed) * 1.0 / count(*), 4) as confidence,
            round((sum(is_delayed) * 1.0 / count(*)) / {baseline_delay_rate}, 3) as lift
        FROM flights
        WHERE origin IN ('DFW', 'ORD', 'DEN', 'ATL', 'CLT', 'LAX', 'JFK', 'SFO', 'LAS', 'EWR', 'MCO', 'BOS')
        GROUP BY origin, time_period
        HAVING count(*) >= 15000 AND (sum(is_delayed) * 1.0 / count(*)) >= 0.28

        UNION ALL

        -- Rule Type B: Carrier + TimePeriod
        SELECT 
            '' as origin,
            time_period,
            carrier,
            '' as season,
            count(*) as total_matched,
            sum(is_delayed) as delay_matched,
            round(count(*) * 1.0 / {total_n}, 4) as support,
            round(sum(is_delayed) * 1.0 / count(*), 4) as confidence,
            round((sum(is_delayed) * 1.0 / count(*)) / {baseline_delay_rate}, 3) as lift
        FROM flights
        GROUP BY carrier, time_period
        HAVING count(*) >= 30000 AND (sum(is_delayed) * 1.0 / count(*)) >= 0.28

        UNION ALL

        -- Rule Type C: Season + TimePeriod + Origin
        SELECT 
            origin,
            time_period,
            '' as carrier,
            season,
            count(*) as total_matched,
            sum(is_delayed) as delay_matched,
            round(count(*) * 1.0 / {total_n}, 4) as support,
            round(sum(is_delayed) * 1.0 / count(*), 4) as confidence,
            round((sum(is_delayed) * 1.0 / count(*)) / {baseline_delay_rate}, 3) as lift
        FROM flights
        WHERE origin IN ('DFW', 'ORD', 'DEN', 'CLT', 'ATL', 'JFK', 'SFO')
        GROUP BY origin, time_period, season
        HAVING count(*) >= 10000 AND (sum(is_delayed) * 1.0 / count(*)) >= 0.32
        ORDER BY lift DESC
        LIMIT 30;
    """
    df_l2 = conn.execute(level2_query).fetchdf()
    for _, r in df_l2.iterrows():
        ant = []
        if r['carrier']: ant.append(f"Carrier={r['carrier']}")
        if r['origin']: ant.append(f"Origin={r['origin']}")
        if r['time_period']: ant.append(f"TimePeriod={r['time_period']}")
        if r['season']: ant.append(f"Season={r['season']}")
        rules.append({
            "antecedent": ant,
            "consequent": ["Delayed >= 15m"],
            "support": float(r['support']),
            "confidence": float(r['confidence']),
            "lift": float(r['lift']),
            "matched_flights": int(r['total_matched'])
        })
    print(f"    [+] Discovered {len(df_l2)} multi-item association rules.")
    
    # Sort all rules by lift descending
    rules = sorted(rules, key=lambda x: x['lift'], reverse=True)
    print("\nTop 5 Association Rules by Lift:")
    for rule in rules[:5]:
        ant_str = " AND ".join(rule['antecedent'])
        print(f"    - IF [{ant_str}] THEN [{rule['consequent'][0]}] | Conf={rule['confidence']*100:.1f}%, Lift={rule['lift']}x, Supp={rule['support']*100:.2f}%")
        
    return rules

def run_airport_clustering(conn):
    print("\n--- [2] Unsupervised K-Means Clustering on Airport Hubs ---")
    
    query = """
        SELECT 
            a.iata_code as airport,
            FIRST(a.city_name) as city,
            FIRST(a.state_abr) as state,
            count(*) as total_departures,
            round(sum(f.arr_del15) * 100.0 / count(*), 2) as arr_delay_rate,
            round(sum(f.dep_del15) * 100.0 / count(*), 2) as dep_delay_rate,
            round(avg(f.dep_delay), 2) as avg_dep_delay,
            round(avg(f.arr_delay), 2) as avg_arr_delay,
            round(avg(f.taxi_out), 2) as avg_taxi_out,
            round(sum(f.nas_delay) * 1.0 / count(*), 2) as avg_nas_delay,
            round(sum(f.weather_delay) * 1.0 / count(*), 2) as avg_weather_delay
        FROM fact_flights f
        JOIN dim_airport a ON f.origin_key = a.airport_key
        WHERE f.cancelled = 0 AND f.diverted = 0
        GROUP BY a.iata_code
        HAVING count(*) >= 10000
        ORDER BY total_departures DESC;
    """
    df = conn.execute(query).fetchdf()
    print(f"Clustering {len(df)} major airports...")

    features = ['arr_delay_rate', 'dep_delay_rate', 'avg_dep_delay', 'avg_taxi_out', 'avg_nas_delay', 'avg_weather_delay']
    X = df[features].values
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # 4 distinct operational clusters
    k = 4
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    df['cluster'] = kmeans.fit_predict(X_scaled)
    
    # Characterize clusters
    cluster_profiles = []
    cluster_labels = {}
    
    # Analyze centroids to assign human-interpretable names
    cluster_stats = df.groupby('cluster')[features].mean()
    
    for c in range(k):
        stats = cluster_stats.loc[c].to_dict()
        airports_in_c = df[df['cluster'] == c]['airport'].tolist()
        
        # Centroid profile evaluation
        if stats['avg_taxi_out'] > 18.0 or stats['avg_nas_delay'] > 3.0:
            name = "High-Friction Surface Congestion Hubs"
            desc = "Airports characterized by long taxi-out queues and severe National Airspace System (NAS) ground delays."
        elif stats['arr_delay_rate'] > 24.0 or stats['avg_dep_delay'] > 16.0:
            name = "Severe Delay & Rotational Chokepoints"
            desc = "Airports suffering from elevated arrival and departure delay rates due to high scheduling density and weather vulnerability."
        elif stats['arr_delay_rate'] < 18.0 and stats['avg_taxi_out'] < 16.0:
            name = "High-Efficiency Smooth Operations Hubs"
            desc = "Large and mid-size airports with superior on-time departure records, quick surface movements, and low delay propagation."
        else:
            name = "Moderate Volume Balanced Airfields"
            desc = "Stable airports with moderate delay variance and balanced ground/air traffic operations."
            
        cluster_labels[c] = name
        cluster_profiles.append({
            "cluster_id": c,
            "cluster_name": name,
            "description": desc,
            "airport_count": len(airports_in_c),
            "sample_airports": airports_in_c[:8],
            "centroid_metrics": {k: round(v, 2) for k, v in stats.items()}
        })
        print(f"    * Cluster {c} [{name}]: {len(airports_in_c)} airports (e.g., {', '.join(airports_in_c[:5])})")
        print(f"      - Arr Delay Rate: {stats['arr_delay_rate']:.1f}% | Taxi-out: {stats['avg_taxi_out']:.1f}m | NAS Delay: {stats['avg_nas_delay']:.2f}m")

    df['cluster_name'] = df['cluster'].map(cluster_labels)
    airport_clusters = df[['airport', 'city', 'state', 'total_departures', 'arr_delay_rate', 'avg_taxi_out', 'avg_dep_delay', 'cluster', 'cluster_name']].to_dict(orient='records')
    
    return {
        "cluster_profiles": cluster_profiles,
        "airport_assignments": airport_clusters
    }

def run_phase6_mining(db_path="warehouse/flight_warehouse.duckdb", output_report="data_reports/phase6_mining_rules.json"):
    print("=" * 70)
    print("PHASE 6: DATA MINING (ASSOCIATION RULES & CLUSTER ANALYSIS)")
    print("=" * 70)
    start_time = datetime.now()
    
    conn = duckdb.connect(db_path, read_only=True)
    baseline_stats = conn.execute("SELECT sum(arr_del15) * 1.0 / count(*), count(*) FROM fact_flights WHERE cancelled = 0 AND diverted = 0").fetchone()
    baseline_delay_rate = float(baseline_stats[0])
    total_n = int(baseline_stats[1])
    
    rules = run_association_rule_mining(conn, baseline_delay_rate, total_n)
    clusters = run_airport_clustering(conn)
    
    duration = (datetime.now() - start_time).total_seconds()
    
    result = {
        "execution_timestamp": datetime.now().isoformat(),
        "duration_seconds": round(duration, 2),
        "baseline_delay_rate": round(baseline_delay_rate, 4),
        "total_rules_discovered": len(rules),
        "association_rules": rules,
        "clustering_analysis": clusters
    }
    
    os.makedirs(os.path.dirname(output_report), exist_ok=True)
    with open(output_report, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)

    print(f"\n[+] Phase 6 Data Mining completed in {duration:.2f} seconds.")
    print(f"[+] Mining results saved to: {output_report}")
    print("=" * 70)
    return result

if __name__ == "__main__":
    run_phase6_mining()
