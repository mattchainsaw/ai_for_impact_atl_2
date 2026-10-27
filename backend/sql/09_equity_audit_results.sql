-- Schema for rescueguard_app.equity_audit_results
-- One row per equity audit, sunk from plans.equity_checker_result. Live Checker never reads this table.
CREATE TABLE IF NOT EXISTS `{project}.rescueguard_app.equity_audit_results` (
  audit_id STRING NOT NULL,
  plan_id STRING NOT NULL,
  ticket_id STRING NOT NULL,
  plan_version INT64 NOT NULL,
  verdict STRING NOT NULL,
  reasons ARRAY<STRING>,
  comparative_summary STRING,
  audited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  tenant_id STRING
);
