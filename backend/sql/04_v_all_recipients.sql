-- View rescueguard_app.v_all_recipients
-- Joins starter recipients + verified app_recipients, applying latest approved overrides and deriving dietary_flags.
CREATE OR REPLACE VIEW `{project}.rescueguard_app.v_all_recipients` AS
WITH combined_base AS (
  SELECT 
    recipient_id,
    ein,
    name,
    street,
    city,
    state,
    zip_code,
    ntee_code,
    archetype,
    archetype_label,
    cold_storage,
    frozen_storage,
    loading_dock,
    refrigerated_transport,
    max_pallets,
    pickup_window_hours,
    weekly_households,
    reported_income,
    populations_served,
    service_days,
    profile_text,
    profile_source,
    latitude,
    longitude,
    'VERIFIED' AS verification_status
  FROM `{project}.a4i_food.recipients`

  UNION ALL

  SELECT 
    recipient_id,
    ein,
    name,
    street,
    city,
    state,
    zip_code,
    ntee_code,
    archetype,
    archetype_label,
    cold_storage,
    frozen_storage,
    loading_dock,
    refrigerated_transport,
    max_pallets,
    pickup_window_hours,
    weekly_households,
    reported_income,
    populations_served,
    service_days,
    profile_text,
    profile_source,
    latitude,
    longitude,
    verification_status
  FROM `{project}.rescueguard_app.app_recipients`
  WHERE verification_status = 'VERIFIED'
),
latest_overrides AS (
  SELECT * EXCEPT(row_num)
  FROM (
    SELECT 
      *,
      ROW_NUMBER() OVER (
        PARTITION BY recipient_id 
        ORDER BY COALESCE(effective_date, created_at) DESC
      ) AS row_num
    FROM `{project}.rescueguard_app.recipient_overrides`
    WHERE status = 'APPROVED'
  )
  WHERE row_num = 1
),
with_overrides AS (
  SELECT 
    b.recipient_id,
    b.ein,
    b.name,
    b.street,
    b.city,
    b.state,
    b.zip_code,
    b.ntee_code,
    b.archetype,
    b.archetype_label,
    COALESCE(o.cold_storage, b.cold_storage) AS cold_storage,
    COALESCE(o.frozen_storage, b.frozen_storage) AS frozen_storage,
    COALESCE(o.loading_dock, b.loading_dock) AS loading_dock,
    COALESCE(o.refrigerated_transport, b.refrigerated_transport) AS refrigerated_transport,
    COALESCE(o.max_pallets, b.max_pallets) AS max_pallets,
    COALESCE(o.pickup_window_hours, b.pickup_window_hours) AS pickup_window_hours,
    COALESCE(o.weekly_households, b.weekly_households) AS weekly_households,
    b.reported_income,
    COALESCE(o.populations_served, b.populations_served) AS populations_served,
    COALESCE(o.service_days, b.service_days) AS service_days,
    COALESCE(o.profile_text, b.profile_text) AS profile_text,
    b.profile_source,
    b.latitude,
    b.longitude,
    b.verification_status,
    o.parsed_dietary_flags AS override_dietary_flags
  FROM combined_base b
  LEFT JOIN latest_overrides o
    ON b.recipient_id = o.recipient_id
),
with_dietary AS (
  SELECT 
    w.* EXCEPT(override_dietary_flags),
    CASE 
      WHEN override_dietary_flags IS NOT NULL AND ARRAY_LENGTH(override_dietary_flags) > 0 
        THEN override_dietary_flags
      ELSE (
        SELECT 
          IF(ARRAY_LENGTH(flags) = 0, ['UNRECORDED'], flags)
        FROM (
          SELECT ARRAY(
            SELECT DISTINCT flag FROM UNNEST([
              IF(REGEXP_CONTAINS(LOWER(COALESCE(w.populations_served, '')), r'infant|child|baby'), 'infant', NULL),
              IF(REGEXP_CONTAINS(LOWER(COALESCE(w.populations_served, '')), r'patient|medical'), 'medically_restricted', NULL),
              IF(REGEXP_CONTAINS(LOWER(COALESCE(w.populations_served, '')), r'older adult|senior|60\+'), 'seniors', NULL),
              IF(REGEXP_CONTAINS(LOWER(COALESCE(w.populations_served, '')), r'unhoused|homeless'), 'unhoused', NULL),
              IF(REGEXP_CONTAINS(LOWER(COALESCE(w.populations_served, '')), r'student|school'), 'students', NULL),
              IF(REGEXP_CONTAINS(LOWER(COALESCE(w.populations_served, '')), r'halal'), 'halal', NULL),
              IF(REGEXP_CONTAINS(LOWER(COALESCE(w.populations_served, '')), r'kosher'), 'kosher', NULL),
              IF(REGEXP_CONTAINS(LOWER(COALESCE(w.populations_served, '')), r'pork-free|no pork'), 'pork_free', NULL),
              IF(REGEXP_CONTAINS(LOWER(COALESCE(w.populations_served, '')), r'vegetarian|vegan'), 'vegetarian', NULL)
            ]) flag WHERE flag IS NOT NULL
          ) AS flags
        )
      )
    END AS dietary_flags
  FROM with_overrides w
)
SELECT * FROM with_dietary;
