-- Schema for rescueguard_app.audit_history
-- Post-run sink of live Firestore audit_log. Live = Firestore; history = this table.
CREATE TABLE IF NOT EXISTS `{project}.rescueguard_app.audit_history` (
  audit_id STRING NOT NULL,
  ticket_id STRING,
  plan_version INT64,
  event_type STRING,
  actor_role STRING,
  action STRING,
  timestamp TIMESTAMP,
  request_id STRING,
  tenant_id STRING,
  sunk_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);
