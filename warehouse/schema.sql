-- ==============================================================================
-- FLIGHT DELAY ANALYTICS AND PREDICTION SYSTEM
-- Phase 4: Kimball Star Schema DDL for Data Warehouse
-- Engine: DuckDB / Relational OLAP
-- ==============================================================================

-- 1. Date Dimension (dim_date)
CREATE TABLE IF NOT EXISTS dim_date (
    date_key INTEGER PRIMARY KEY,
    fl_date DATE NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    month INTEGER NOT NULL,
    month_name VARCHAR NOT NULL,
    day_of_month INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    day_name VARCHAR NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    season VARCHAR NOT NULL
);

-- 2. Carrier Dimension (dim_carrier)
CREATE TABLE IF NOT EXISTS dim_carrier (
    carrier_key VARCHAR PRIMARY KEY,
    carrier_code VARCHAR NOT NULL,
    carrier_name VARCHAR NOT NULL
);

-- 3. Airport Dimension (dim_airport)
CREATE TABLE IF NOT EXISTS dim_airport (
    airport_key VARCHAR PRIMARY KEY,
    airport_id INTEGER,
    iata_code VARCHAR NOT NULL,
    city_name VARCHAR,
    state_abr VARCHAR,
    state_name VARCHAR
);

-- 4. Scheduled Time Block Dimension (dim_time_block)
CREATE TABLE IF NOT EXISTS dim_time_block (
    time_block_key INTEGER PRIMARY KEY,
    hour_label VARCHAR NOT NULL,
    period_name VARCHAR NOT NULL
);

-- 5. Route Dimension (dim_route)
CREATE TABLE IF NOT EXISTS dim_route (
    route_key VARCHAR PRIMARY KEY,
    origin_code VARCHAR NOT NULL,
    dest_code VARCHAR NOT NULL,
    route_name VARCHAR NOT NULL,
    distance DOUBLE,
    distance_group VARCHAR
);

-- 6. Fact Flights Table (fact_flights)
CREATE TABLE IF NOT EXISTS fact_flights (
    flight_id BIGINT PRIMARY KEY,
    date_key INTEGER REFERENCES dim_date(date_key),
    carrier_key VARCHAR REFERENCES dim_carrier(carrier_key),
    origin_key VARCHAR REFERENCES dim_airport(airport_key),
    dest_key VARCHAR REFERENCES dim_airport(airport_key),
    time_block_key INTEGER REFERENCES dim_time_block(time_block_key),
    route_key VARCHAR REFERENCES dim_route(route_key),
    tail_num VARCHAR,
    flight_num INTEGER,
    crs_dep_time INTEGER,
    dep_time INTEGER,
    dep_delay DOUBLE,
    dep_del15 INTEGER,
    taxi_out DOUBLE,
    crs_arr_time INTEGER,
    arr_time INTEGER,
    arr_delay DOUBLE,
    arr_del15 INTEGER,
    cancelled INTEGER,
    cancellation_code VARCHAR,
    diverted INTEGER,
    crs_elapsed_time DOUBLE,
    actual_elapsed_time DOUBLE,
    distance DOUBLE,
    carrier_delay DOUBLE,
    weather_delay DOUBLE,
    nas_delay DOUBLE,
    security_delay DOUBLE,
    late_aircraft_delay DOUBLE
);

-- Create Analytical Indexes for High-Speed OLAP Slicing
CREATE INDEX IF NOT EXISTS idx_fact_date ON fact_flights(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_carrier ON fact_flights(carrier_key);
CREATE INDEX IF NOT EXISTS idx_fact_origin ON fact_flights(origin_key);
CREATE INDEX IF NOT EXISTS idx_fact_dest ON fact_flights(dest_key);
CREATE INDEX IF NOT EXISTS idx_fact_time_block ON fact_flights(time_block_key);
CREATE INDEX IF NOT EXISTS idx_fact_del15 ON fact_flights(arr_del15);
