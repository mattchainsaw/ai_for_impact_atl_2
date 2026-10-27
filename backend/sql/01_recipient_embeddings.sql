-- Schema for rescueguard_app.recipient_embeddings
-- 3,072d vector embeddings generated via AI.EMBED (gemini-embedding-2)
CREATE TABLE IF NOT EXISTS `{project}.rescueguard_app.recipient_embeddings` (
  recipient_id INT64 NOT NULL,
  profile_text STRING,
  embedding ARRAY<FLOAT64>,
  embedded_status STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);
