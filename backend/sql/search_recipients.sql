-- Parameterized search read path through v_all_recipients
-- VECTOR_SEARCH over recipient_embeddings joined to v_all_recipients.
-- Returns only verified pantries present in v_all_recipients (excluding PENDING app recipients).
-- Parameterized inputs: @query_text (STRING), @top_k (INT64)
WITH search_candidates AS (
  SELECT 
    base.recipient_id,
    distance AS semantic_distance,
    ROW_NUMBER() OVER (ORDER BY distance ASC) AS semantic_rank
  FROM VECTOR_SEARCH(
    TABLE `{project}.rescueguard_app.recipient_embeddings`,
    'embedding',
    (SELECT AI.EMBED(@query_text, endpoint => 'gemini-embedding-2').result AS embedding),
    top_k => @top_k,
    distance_type => 'COSINE'
  )
)
SELECT 
  s.semantic_rank,
  s.semantic_distance,
  v.recipient_id,
  v.ein,
  v.name,
  v.street,
  v.city,
  v.state,
  v.zip_code,
  v.ntee_code,
  v.archetype,
  v.archetype_label,
  v.cold_storage,
  v.frozen_storage,
  v.loading_dock,
  v.refrigerated_transport,
  v.max_pallets,
  v.pickup_window_hours,
  v.weekly_households,
  v.reported_income,
  v.populations_served,
  v.service_days,
  v.profile_text,
  v.profile_source,
  v.latitude,
  v.longitude,
  v.verification_status,
  v.dietary_flags
FROM search_candidates s
INNER JOIN `{project}.rescueguard_app.v_all_recipients` v
  ON s.recipient_id = v.recipient_id
ORDER BY s.semantic_rank ASC;
