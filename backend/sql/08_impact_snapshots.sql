-- Schema for rescueguard_app.impact_snapshots
-- One row per approved plan, sunk from plans.impact_breakdown.
CREATE TABLE IF NOT EXISTS `{project}.rescueguard_app.impact_snapshots` (
  snapshot_id STRING NOT NULL,
  ticket_id STRING NOT NULL,
  plan_id STRING NOT NULL,
  plan_version INT64 NOT NULL,
  need_score FLOAT64,
  food_rescued_score FLOAT64,
  equity_score FLOAT64,
  reliability_score FLOAT64,
  total_impact_score INT64,
  breakdown_json STRING,
  snapshotted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  tenant_id STRING
);
