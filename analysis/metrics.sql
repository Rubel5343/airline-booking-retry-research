-- Per-strategy summary for one experiment run.
-- Usage in psql:
--   \set run_id '00000000-0000-0000-0000-000000000000'

WITH ground_truth AS (
    SELECT
        experiment_run_id,
        logical_booking_id,
        COUNT(*) AS supplier_order_count,
        MIN(created_at) AS first_supplier_order_at
    FROM simulator.supplier_orders
    WHERE experiment_run_id = :'run_id'::uuid
    GROUP BY experiment_run_id, logical_booking_id
),
base AS (
    SELECT
        a.experiment_run_id,
        a.logical_booking_id,
        a.strategy,
        a.state,
        a.create_call_count,
        a.retrieve_call_count,
        a.resolution_ms,
        COALESCE(g.supplier_order_count, 0) AS supplier_order_count
    FROM research.booking_attempts a
    LEFT JOIN ground_truth g
      ON g.experiment_run_id = a.experiment_run_id
     AND g.logical_booking_id = a.logical_booking_id
    WHERE a.experiment_run_id = :'run_id'::uuid
      AND a.state <> 'SYSTEM_ERROR'
)
SELECT
    strategy,
    COUNT(*) AS logical_bookings,
    COUNT(*) FILTER (WHERE supplier_order_count > 1) AS duplicate_logical_bookings,
    ROUND(100.0 * COUNT(*) FILTER (WHERE supplier_order_count > 1) / NULLIF(COUNT(*), 0), 4) AS duplicate_rate_pct,
    COUNT(*) FILTER (WHERE state = 'UNKNOWN') AS unresolved_bookings,
    ROUND(AVG(resolution_ms)::numeric, 2) AS avg_resolution_ms,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY resolution_ms) AS p50_resolution_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY resolution_ms) AS p95_resolution_ms,
    percentile_cont(0.99) WITHIN GROUP (ORDER BY resolution_ms) AS p99_resolution_ms,
    ROUND(AVG(create_call_count + retrieve_call_count)::numeric, 4) AS avg_supplier_calls_per_booking,
    ROUND(AVG(create_call_count)::numeric, 4) AS avg_create_calls,
    ROUND(AVG(retrieve_call_count)::numeric, 4) AS avg_retrieve_calls
FROM base
GROUP BY strategy
ORDER BY strategy;
