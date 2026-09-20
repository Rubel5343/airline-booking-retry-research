-- A retry is classified as premature if a second CREATE was sent after the first
-- supplier order already existed in ground truth.

WITH second_create AS (
    SELECT
        e.experiment_run_id,
        e.logical_booking_id,
        MIN(e.occurred_at) FILTER (
            WHERE e.event_type = 'ORDER_CREATE_SENT'
              AND (e.metadata->>'createCall')::int = 2
        ) AS second_create_at
    FROM research.booking_events e
    WHERE e.experiment_run_id = :'run_id'::uuid
    GROUP BY e.experiment_run_id, e.logical_booking_id
),
first_order AS (
    SELECT
        experiment_run_id,
        logical_booking_id,
        MIN(created_at) AS first_order_created_at
    FROM simulator.supplier_orders
    WHERE experiment_run_id = :'run_id'::uuid
    GROUP BY experiment_run_id, logical_booking_id
)
SELECT
    a.strategy,
    COUNT(*) FILTER (WHERE s.second_create_at IS NOT NULL) AS retries,
    COUNT(*) FILTER (
        WHERE s.second_create_at IS NOT NULL
          AND f.first_order_created_at IS NOT NULL
          AND f.first_order_created_at <= s.second_create_at
    ) AS premature_retries,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE s.second_create_at IS NOT NULL
              AND f.first_order_created_at IS NOT NULL
              AND f.first_order_created_at <= s.second_create_at
        ) / NULLIF(COUNT(*) FILTER (WHERE s.second_create_at IS NOT NULL), 0),
        4
    ) AS premature_retry_rate_pct
FROM research.booking_attempts a
LEFT JOIN second_create s
  ON s.experiment_run_id = a.experiment_run_id
 AND s.logical_booking_id = a.logical_booking_id
LEFT JOIN first_order f
  ON f.experiment_run_id = a.experiment_run_id
 AND f.logical_booking_id = a.logical_booking_id
WHERE a.experiment_run_id = :'run_id'::uuid
GROUP BY a.strategy
ORDER BY a.strategy;
