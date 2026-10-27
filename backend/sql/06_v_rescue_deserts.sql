-- View rescueguard_app.v_rescue_deserts
-- Identifies census tracts where poverty_rate > 0.30 AND no_vehicle_rate > 0.40
-- AND cold_recipients_within_5km = 0, using the verified cold storage domain.
-- Cold domain includes verified pantries in v_all_recipients where cold_storage IN ('walk-in', 'commercial', 'domestic') OR frozen_storage = TRUE.
CREATE OR REPLACE VIEW `{project}.rescueguard_app.v_rescue_deserts` AS
WITH cold_capable_recipients AS (
  SELECT 
    recipient_id,
    name,
    latitude,
    longitude,
    cold_storage,
    frozen_storage
  FROM `{project}.rescueguard_app.v_all_recipients`
  WHERE (cold_storage IN ('walk-in', 'commercial', 'domestic') OR frozen_storage = TRUE)
    AND latitude IS NOT NULL AND longitude IS NOT NULL
),
tract_eval AS (
  SELECT 
    t.geo_id,
    t.tract_lat,
    t.tract_lon,
    t.total_pop,
    t.median_income,
    t.poverty_rate,
    t.no_vehicle_rate,
    t.assistance_rate,
    COUNT(c.recipient_id) AS cold_recipients_within_5km
  FROM `{project}.a4i_food.tract_demographics` t
  LEFT JOIN cold_capable_recipients c
    ON ST_DISTANCE(
      ST_GEOGPOINT(c.longitude, c.latitude), 
      ST_GEOGPOINT(t.tract_lon, t.tract_lat)
    ) <= 5000.0 -- 5km radius
  WHERE t.poverty_rate > 0.30 
    AND t.no_vehicle_rate > 0.40
  GROUP BY 
    t.geo_id, t.tract_lat, t.tract_lon, t.total_pop, 
    t.median_income, t.poverty_rate, t.no_vehicle_rate, t.assistance_rate
)
SELECT *
FROM tract_eval
WHERE cold_recipients_within_5km = 0;
