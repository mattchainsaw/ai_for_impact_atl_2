-- Schema for rescueguard_app.recipient_overrides
-- App-owned profile changes and overrides. Never update starter rows in place.
CREATE TABLE IF NOT EXISTS `{project}.rescueguard_app.recipient_overrides` (
  override_id STRING NOT NULL,
  recipient_id INT64 NOT NULL,
  cold_storage STRING,
  frozen_storage BOOL,
  loading_dock BOOL,
  refrigerated_transport BOOL,
  max_pallets INT64,
  pickup_window_hours INT64,
  weekly_households INT64,
  populations_served STRING,
  service_days STRING,
  profile_text STRING,
  parsed_dietary_flags ARRAY<STRING>,
  status STRING NOT NULL, -- PENDING | VERIFIED | APPROVED
  effective_date TIMESTAMP,
  approver_role STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);
