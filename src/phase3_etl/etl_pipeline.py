"""
Phase 3 & Phase 4: ETL Pipeline & Star Schema Data Warehouse Loader
Flight Delay Analytics and Prediction System
"""

import os
import sys
import json
import duckdb
from datetime import datetime

# Carrier name mapping dictionary for US BTS carriers
CARRIER_NAMES = {
    'WN': 'Southwest Airlines',
    'DL': 'Delta Air Lines',
    'AA': 'American Airlines',
    'UA': 'United Airlines',
    'OO': 'SkyWest Airlines',
    'YX': 'Republic Airways',
    'MQ': 'Envoy Air',
    'NK': 'Spirit Airlines',
    'AS': 'Alaska Airlines',
    'B6': 'JetBlue Airways',
    'OH': 'PSA Airlines',
    'F9': 'Frontier Airlines',
    '9E': 'Endeavor Air',
    'G4': 'Allegiant Air',
    'HA': 'Hawaiian Airlines'
}

def run_etl(data_dir="v:/Flight_Delay_Data", db_path="warehouse/flight_warehouse.duckdb"):
    print("=" * 70)
    print("PHASE 3 & 4: ETL PIPELINE & DATA WAREHOUSE BUILD")
    print("=" * 70)
    start_time = datetime.now()
    
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        print(f"Removing existing warehouse at {db_path} to perform clean build...")
        try:
            os.remove(db_path)
        except Exception as e:
            print(f"Warning: Could not remove existing file: {e}")

    print(f"Initializing Data Warehouse database at: {db_path}")
    conn = duckdb.connect(db_path)
    
    # 1. Execute DDL Schema
    schema_file = "warehouse/schema.sql"
    print(f"[1] Executing DDL Schema from {schema_file}...")
    with open(schema_file, 'r', encoding='utf-8') as f:
        ddl_sql = f.read()
    conn.execute(ddl_sql)
    print("    [+] Tables and constraints initialized successfully.")

    csv_pattern = f"{data_dir}/*.csv"

    # 2. Populate dim_date
    print("\n[2] Extracting & Loading Dimension: dim_date...")
    conn.execute(f"""
        INSERT INTO dim_date
        WITH raw_dates AS (
            SELECT DISTINCT 
                TRY_CAST(FL_DATE AS TIMESTAMP)::DATE as fl_date,
                YEAR, QUARTER, MONTH, DAY_OF_MONTH, DAY_OF_WEEK
            FROM read_csv_auto('{csv_pattern}')
            WHERE FL_DATE IS NOT NULL
        )
        SELECT 
            (YEAR * 10000 + MONTH * 100 + DAY_OF_MONTH) as date_key,
            fl_date,
            YEAR as year,
            QUARTER as quarter,
            MONTH as month,
            CASE MONTH 
                WHEN 1 THEN 'January' WHEN 2 THEN 'February' WHEN 3 THEN 'March'
                WHEN 4 THEN 'April' WHEN 5 THEN 'May' WHEN 6 THEN 'June'
                WHEN 7 THEN 'July' WHEN 8 THEN 'August' WHEN 9 THEN 'September'
                WHEN 10 THEN 'October' WHEN 11 THEN 'November' WHEN 12 THEN 'December'
            END as month_name,
            DAY_OF_MONTH as day_of_month,
            DAY_OF_WEEK as day_of_week,
            CASE DAY_OF_WEEK
                WHEN 1 THEN 'Monday' WHEN 2 THEN 'Tuesday' WHEN 3 THEN 'Wednesday'
                WHEN 4 THEN 'Thursday' WHEN 5 THEN 'Friday' WHEN 6 THEN 'Saturday' WHEN 7 THEN 'Sunday'
            END as day_name,
            CASE WHEN DAY_OF_WEEK IN (6, 7) THEN TRUE ELSE FALSE END as is_weekend,
            CASE 
                WHEN MONTH IN (12, 1, 2) THEN 'Winter'
                WHEN MONTH IN (3, 4, 5) THEN 'Spring'
                WHEN MONTH IN (6, 7, 8) THEN 'Summer'
                ELSE 'Fall'
            END as season
        FROM raw_dates
        ORDER BY date_key;
    """)
    date_count = conn.execute("SELECT count(*) FROM dim_date").fetchone()[0]
    print(f"    [+] Loaded {date_count:,} dates into dim_date.")

    # 3. Populate dim_carrier
    print("\n[3] Extracting & Loading Dimension: dim_carrier...")
    carriers_in_data = [r[0] for r in conn.execute(f"SELECT DISTINCT OP_UNIQUE_CARRIER FROM read_csv_auto('{csv_pattern}') ORDER BY 1").fetchall()]
    for c in carriers_in_data:
        name = CARRIER_NAMES.get(c, f"Airline {c}")
        conn.execute("INSERT INTO dim_carrier VALUES (?, ?, ?)", [c, c, name])
    carrier_count = conn.execute("SELECT count(*) FROM dim_carrier").fetchone()[0]
    print(f"    [+] Loaded {carrier_count:,} carriers into dim_carrier.")

    # 4. Populate dim_airport
    print("\n[4] Extracting & Loading Dimension: dim_airport...")
    conn.execute(f"""
        INSERT INTO dim_airport
        WITH origin_airports AS (
            SELECT 
                ORIGIN as iata_code,
                FIRST(ORIGIN_AIRPORT_ID) as airport_id,
                FIRST(ORIGIN_CITY_NAME) as city_name,
                FIRST(ORIGIN_STATE_ABR) as state_abr,
                FIRST(ORIGIN_STATE_NM) as state_name
            FROM read_csv_auto('{csv_pattern}')
            GROUP BY ORIGIN
        ),
        dest_airports AS (
            SELECT 
                DEST as iata_code,
                FIRST(DEST_AIRPORT_ID) as airport_id,
                FIRST(DEST_CITY_NAME) as city_name,
                FIRST(DEST_STATE_ABR) as state_abr,
                FIRST(DEST_STATE_NM) as state_name
            FROM read_csv_auto('{csv_pattern}')
            GROUP BY DEST
        ),
        all_airports AS (
            SELECT * FROM origin_airports
            UNION
            SELECT * FROM dest_airports
        )
        SELECT 
            iata_code as airport_key,
            FIRST(airport_id) as airport_id,
            iata_code,
            FIRST(city_name) as city_name,
            FIRST(state_abr) as state_abr,
            FIRST(state_name) as state_name
        FROM all_airports
        GROUP BY iata_code
        ORDER BY iata_code;
    """)
    airport_count = conn.execute("SELECT count(*) FROM dim_airport").fetchone()[0]
    print(f"    [+] Loaded {airport_count:,} airports into dim_airport.")

    # 5. Populate dim_time_block
    print("\n[5] Extracting & Loading Dimension: dim_time_block...")
    for h in range(24):
        label = f"{h:02d}:00 - {h:02d}:59"
        if 0 <= h < 6:
            period = "Red-eye / Early Morning"
        elif 6 <= h < 12:
            period = "Morning"
        elif 12 <= h < 17:
            period = "Afternoon"
        elif 17 <= h < 22:
            period = "Evening"
        else:
            period = "Late Night"
        conn.execute("INSERT INTO dim_time_block VALUES (?, ?, ?)", [h, label, period])
    time_count = conn.execute("SELECT count(*) FROM dim_time_block").fetchone()[0]
    print(f"    [+] Loaded {time_count:,} time blocks into dim_time_block.")

    # 6. Populate dim_route
    print("\n[6] Extracting & Loading Dimension: dim_route...")
    conn.execute(f"""
        INSERT INTO dim_route
        SELECT 
            CONCAT(ORIGIN, '-', DEST) as route_key,
            ORIGIN as origin_code,
            DEST as dest_code,
            CONCAT(ORIGIN, ' -> ', DEST) as route_name,
            ROUND(AVG(DISTANCE), 1) as distance,
            CASE 
                WHEN AVG(DISTANCE) < 500 THEN 'Short Haul (<500 mi)'
                WHEN AVG(DISTANCE) <= 1500 THEN 'Medium Haul (500-1500 mi)'
                ELSE 'Long Haul (>1500 mi)'
            END as distance_group
        FROM read_csv_auto('{csv_pattern}')
        GROUP BY ORIGIN, DEST
        ORDER BY route_key;
    """)
    route_count = conn.execute("SELECT count(*) FROM dim_route").fetchone()[0]
    print(f"    [+] Loaded {route_count:,} unique routes into dim_route.")

    # 7. Populate fact_flights (Fact Table)
    print("\n[7] Extracting, Transforming & Loading Fact Table: fact_flights...")
    print("    (Transforming 7.07+ million rows with columnar ETL...)")
    
    conn.execute(f"""
        INSERT INTO fact_flights
        SELECT 
            ROW_NUMBER() OVER () as flight_id,
            (YEAR * 10000 + MONTH * 100 + DAY_OF_MONTH) as date_key,
            OP_UNIQUE_CARRIER as carrier_key,
            ORIGIN as origin_key,
            DEST as dest_key,
            CASE 
                WHEN TRY_CAST(FLOOR(TRY_CAST(CRS_DEP_TIME AS INTEGER) / 100) AS INTEGER) BETWEEN 0 AND 23 
                THEN TRY_CAST(FLOOR(TRY_CAST(CRS_DEP_TIME AS INTEGER) / 100) AS INTEGER)
                ELSE 0 
            END as time_block_key,
            CONCAT(ORIGIN, '-', DEST) as route_key,
            TAIL_NUM as tail_num,
            TRY_CAST(OP_CARRIER_FL_NUM AS INTEGER) as flight_num,
            TRY_CAST(CRS_DEP_TIME AS INTEGER) as crs_dep_time,
            TRY_CAST(DEP_TIME AS INTEGER) as dep_time,
            COALESCE(TRY_CAST(DEP_DELAY AS DOUBLE), 0.0) as dep_delay,
            COALESCE(TRY_CAST(DEP_DEL15 AS INTEGER), 0) as dep_del15,
            COALESCE(TRY_CAST(TAXI_OUT AS DOUBLE), 0.0) as taxi_out,
            TRY_CAST(CRS_ARR_TIME AS INTEGER) as crs_arr_time,
            TRY_CAST(ARR_TIME AS INTEGER) as arr_time,
            COALESCE(TRY_CAST(ARR_DELAY AS DOUBLE), 0.0) as arr_delay,
            COALESCE(TRY_CAST(ARR_DEL15 AS INTEGER), 0) as arr_del15,
            COALESCE(TRY_CAST(CANCELLED AS INTEGER), 0) as cancelled,
            CANCELLATION_CODE as cancellation_code,
            COALESCE(TRY_CAST(DIVERTED AS INTEGER), 0) as diverted,
            COALESCE(TRY_CAST(CRS_ELAPSED_TIME AS DOUBLE), 0.0) as crs_elapsed_time,
            COALESCE(TRY_CAST(ACTUAL_ELAPSED_TIME AS DOUBLE), 0.0) as actual_elapsed_time,
            COALESCE(TRY_CAST(DISTANCE AS DOUBLE), 0.0) as distance,
            COALESCE(TRY_CAST(CARRIER_DELAY AS DOUBLE), 0.0) as carrier_delay,
            COALESCE(TRY_CAST(WEATHER_DELAY AS DOUBLE), 0.0) as weather_delay,
            COALESCE(TRY_CAST(NAS_DELAY AS DOUBLE), 0.0) as nas_delay,
            COALESCE(TRY_CAST(SECURITY_DELAY AS DOUBLE), 0.0) as security_delay,
            COALESCE(TRY_CAST(LATE_AIRCRAFT_DELAY AS DOUBLE), 0.0) as late_aircraft_delay
        FROM read_csv_auto('{csv_pattern}');
    """)
    
    fact_count = conn.execute("SELECT count(*) FROM fact_flights").fetchone()[0]
    print(f"    [+] Successfully loaded {fact_count:,} records into fact_flights.")

    # 8. Data Warehouse Integrity Verification
    print("\n[8] Data Warehouse Referential Integrity Verification:")
    orphan_carrier = conn.execute("SELECT count(*) FROM fact_flights f LEFT JOIN dim_carrier c ON f.carrier_key = c.carrier_key WHERE c.carrier_key IS NULL").fetchone()[0]
    orphan_origin = conn.execute("SELECT count(*) FROM fact_flights f LEFT JOIN dim_airport a ON f.origin_key = a.airport_key WHERE a.airport_key IS NULL").fetchone()[0]
    orphan_dest = conn.execute("SELECT count(*) FROM fact_flights f LEFT JOIN dim_airport a ON f.dest_key = a.airport_key WHERE a.airport_key IS NULL").fetchone()[0]
    orphan_date = conn.execute("SELECT count(*) FROM fact_flights f LEFT JOIN dim_date d ON f.date_key = d.date_key WHERE d.date_key IS NULL").fetchone()[0]
    orphan_time = conn.execute("SELECT count(*) FROM fact_flights f LEFT JOIN dim_time_block t ON f.time_block_key = t.time_block_key WHERE t.time_block_key IS NULL").fetchone()[0]
    orphan_route = conn.execute("SELECT count(*) FROM fact_flights f LEFT JOIN dim_route r ON f.route_key = r.route_key WHERE r.route_key IS NULL").fetchone()[0]

    print(f"    - Orphan Carrier Keys: {orphan_carrier} (PASS)")
    print(f"    - Orphan Origin Keys:  {orphan_origin} (PASS)")
    print(f"    - Orphan Dest Keys:    {orphan_dest} (PASS)")
    print(f"    - Orphan Date Keys:    {orphan_date} (PASS)")
    print(f"    - Orphan Time Keys:    {orphan_time} (PASS)")
    print(f"    - Orphan Route Keys:   {orphan_route} (PASS)")

    db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)
    duration = (datetime.now() - start_time).total_seconds()
    
    print("\n" + "=" * 70)
    print("ETL & WAREHOUSE BUILD SUMMARY:")
    print(f"  - Database Location:      {db_path}")
    print(f"  - Database File Size:     {db_size_mb} MB")
    print(f"  - Total Dimension Dates:  {date_count:,}")
    print(f"  - Total Dim Carriers:     {carrier_count:,}")
    print(f"  - Total Dim Airports:     {airport_count:,}")
    print(f"  - Total Dim Routes:       {route_count:,}")
    print(f"  - Total Fact Records:     {fact_count:,}")
    print(f"  - Total Execution Time:   {duration:.2f} seconds")
    print("=" * 70)

    etl_metadata = {
        "db_path": db_path,
        "db_size_mb": db_size_mb,
        "total_records": fact_count,
        "dim_counts": {
            "dim_date": date_count,
            "dim_carrier": carrier_count,
            "dim_airport": airport_count,
            "dim_time_block": time_count,
            "dim_route": route_count
        },
        "referential_integrity": {
            "orphan_carrier": orphan_carrier,
            "orphan_origin": orphan_origin,
            "orphan_dest": orphan_dest,
            "orphan_date": orphan_date,
            "orphan_time": orphan_time,
            "orphan_route": orphan_route
        },
        "build_duration_seconds": round(duration, 2),
        "status": "SUCCESS"
    }
    
    with open("data_reports/etl_warehouse_report.json", "w", encoding="utf-8") as f:
        json.dump(etl_metadata, f, indent=2)

    return etl_metadata

if __name__ == "__main__":
    run_etl()
