-- Schema for rescueguard_app.app_recipients
-- App-owned onboarded recipients only. Never insert into starter a4i_food.recipients.
CREATE TABLE IF NOT EXISTS `{project}.rescueguard_app.app_recipients` (
  recipient_id INT64 NOT NULL,
  ein STRING,
  name STRING NOT NULL,
  street STRING,
  city STRING,
  state STRING,
  zip_code STRING,
  ntee_code STRING,
  archetype STRING,
  archetype_label STRING,
  cold_storage STRING,
  frozen_storage BOOL,
  loading_dock BOOL,
  refrigerated_transport BOOL,
  max_pallets INT64,
  pickup_window_hours INT64,
  weekly_households INT64,
  reported_income FLOAT64,
  populations_served STRING,
  service_days STRING,
  profile_text STRING,
  profile_source STRING DEFAULT 'app_onboarded',
  latitude FLOAT64,
  longitude FLOAT64,
  verification_status STRING NOT NULL, -- PENDING | VERIFIED | DEMO_SIMULATED
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);
