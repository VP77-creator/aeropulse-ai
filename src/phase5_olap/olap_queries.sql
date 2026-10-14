-- ==============================================================================
-- FLIGHT DELAY ANALYTICS AND PREDICTION SYSTEM
-- Phase 5: SQL & OLAP Multidimensional Analytical Queries
-- ==============================================================================

-- 1. Airline On-Time Performance & Seasonal Rollup
SELECT 
    d.quarter,
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
GROUP BY d.quarter, d.month, d.month_name, c.carrier_code, c.carrier_name
ORDER BY d.month, total_flights DESC;

-- 2. State & Airport Hierarchical Drill-Down
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

-- 3. Route Pareto Analysis (Cumulative Delay Concentration)
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
LIMIT 25;

-- 4. Temporal Interaction Matrix (Day of Week x Time Block Cube)
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

-- 5. Delay Causation Breakdown by Carrier
SELECT 
    c.carrier_code,
    c.carrier_name,
    count(*) as delayed_flights_with_breakdown,
    round(sum(f.carrier_delay), 0) as total_carrier_delay,
    round(sum(f.weather_delay), 0) as total_weather_delay,
    round(sum(f.nas_delay), 0) as total_nas_delay,
    round(sum(f.security_delay), 0) as total_security_delay,
    round(sum(f.late_aircraft_delay), 0) as total_late_aircraft_delay,
    round(sum(f.carrier_delay + f.weather_delay + f.nas_delay + f.security_delay + f.late_aircraft_delay), 0) as total_all_delay,
    round(sum(f.carrier_delay) * 100.0 / nullif(sum(f.carrier_delay + f.weather_delay + f.nas_delay + f.security_delay + f.late_aircraft_delay), 0), 2) as carrier_pct,
    round(sum(f.weather_delay) * 100.0 / nullif(sum(f.carrier_delay + f.weather_delay + f.nas_delay + f.security_delay + f.late_aircraft_delay), 0), 2) as weather_pct,
    round(sum(f.nas_delay) * 100.0 / nullif(sum(f.carrier_delay + f.weather_delay + f.nas_delay + f.security_delay + f.late_aircraft_delay), 0), 2) as nas_pct,
    round(sum(f.late_aircraft_delay) * 100.0 / nullif(sum(f.carrier_delay + f.weather_delay + f.nas_delay + f.security_delay + f.late_aircraft_delay), 0), 2) as late_aircraft_pct
FROM fact_flights f
JOIN dim_carrier c ON f.carrier_key = c.carrier_key
WHERE f.arr_del15 = 1
GROUP BY c.carrier_code, c.carrier_name
ORDER BY total_all_delay DESC;

-- 6. Airport Surface Congestion & NAS Impact Index
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
