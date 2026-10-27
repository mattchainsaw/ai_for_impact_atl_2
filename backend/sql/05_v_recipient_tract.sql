-- View rescueguard_app.v_recipient_tract
-- Maps recipient to nearest census tract by distance to ZIP/location centroid.
-- Left join guarantees that a missing tract produces UNKNOWN with weekly_households fallback, never dropping a pantry.
-- tract_distance_km is strictly recipient-to-tract distance, never donor-to-recipient distance.
CREATE OR REPLACE VIEW `{project}.rescueguard_app.v_recipient_tract` AS
WITH valid_recipients AS (
  SELECT 
    recipient_id,
    name,
    latitude,
    longitude,
    weekly_households,
    CASE 
      WHEN latitude IS NULL OR longitude IS NULL 
        OR (latitude = 0.0 AND longitude = 0.0)
        OR latitude < 24.0 OR latitude > 50.0 
        OR longitude < -125.0 OR longitude > -65.0 
      THEN FALSE
      ELSE TRUE
    END AS has_valid_coords
  FROM `{project}.rescueguard_app.v_all_recipients`
),
tract_distances AS (
  SELECT 
    r.recipient_id,
    t.geo_id AS tract_geo_id,
    t.poverty_rate,
    t.no_vehicle_rate,
    t.assistance_rate,
    t.median_income,
    ST_DISTANCE(
      ST_GEOGPOINT(r.longitude, r.latitude), 
      ST_GEOGPOINT(t.tract_lon, t.tract_lat)
    ) / 1000.0 AS tract_distance_km,
    ROW_NUMBER() OVER (
      PARTITION BY r.recipient_id 
      ORDER BY ST_DISTANCE(
        ST_GEOGPOINT(r.longitude, r.latitude), 
        ST_GEOGPOINT(t.tract_lon, t.tract_lat)
      ) ASC
    ) AS rank_order
  FROM valid_recipients r
  CROSS JOIN `{project}.a4i_food.tract_demographics` t
  WHERE r.has_valid_coords = TRUE
),
nearest_tract AS (
  SELECT * EXCEPT(rank_order)
  FROM tract_distances
  WHERE rank_order = 1 AND tract_distance_km <= 50.0 -- 50km metro cutoff
)
SELECT 
  r.recipient_id,
  r.name,
  n.tract_geo_id,
  n.poverty_rate,
  n.no_vehicle_rate,
  n.assistance_rate,
  n.median_income,
  n.tract_distance_km,
  r.weekly_households AS fallback_weekly_households,
  CASE 
    WHEN n.tract_geo_id IS NOT NULL THEN 'FOUND'
    ELSE 'UNKNOWN'
  END AS tract_status
FROM valid_recipients r
LEFT JOIN nearest_tract n
  ON r.recipient_id = n.recipient_id;
