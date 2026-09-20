CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS research;
CREATE SCHEMA IF NOT EXISTS simulator;

CREATE TABLE IF NOT EXISTS research.experiment_runs (
    run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    random_seed integer NOT NULL,
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    git_commit text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS research.booking_attempts (
    attempt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_run_id uuid NOT NULL REFERENCES research.experiment_runs(run_id),
    logical_booking_id text NOT NULL,
    client_reference text NOT NULL,
    strategy text NOT NULL,
    state text NOT NULL,
    supplier_order_id text,
    create_call_count integer NOT NULL DEFAULT 0,
    retrieve_call_count integer NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    resolution_ms bigint,
    error_code text,
    UNIQUE (experiment_run_id, logical_booking_id)
);

CREATE INDEX IF NOT EXISTS ix_booking_attempts_run_strategy
    ON research.booking_attempts(experiment_run_id, strategy);

CREATE INDEX IF NOT EXISTS ix_booking_attempts_client_reference
    ON research.booking_attempts(experiment_run_id, client_reference);

CREATE TABLE IF NOT EXISTS research.booking_events (
    event_id bigserial PRIMARY KEY,
    experiment_run_id uuid NOT NULL REFERENCES research.experiment_runs(run_id),
    attempt_id uuid NOT NULL REFERENCES research.booking_attempts(attempt_id),
    logical_booking_id text NOT NULL,
    client_reference text NOT NULL,
    event_type text NOT NULL,
    supplier_order_id text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_booking_events_attempt_time
    ON research.booking_events(attempt_id, occurred_at);

CREATE INDEX IF NOT EXISTS ix_booking_events_run_type
    ON research.booking_events(experiment_run_id, event_type);

CREATE TABLE IF NOT EXISTS simulator.supplier_orders (
    supplier_order_id text PRIMARY KEY,
    experiment_run_id uuid NOT NULL REFERENCES research.experiment_runs(run_id),
    logical_booking_id text NOT NULL,
    client_reference text NOT NULL,
    create_attempt_no integer NOT NULL,
    origin text NOT NULL,
    destination text NOT NULL,
    created_at timestamptz NOT NULL,
    visible_at timestamptz NOT NULL,
    response_lost boolean NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS ix_supplier_orders_run_reference
    ON simulator.supplier_orders(experiment_run_id, client_reference, created_at);

CREATE INDEX IF NOT EXISTS ix_supplier_orders_run_logical
    ON simulator.supplier_orders(experiment_run_id, logical_booking_id, created_at);

CREATE TABLE IF NOT EXISTS simulator.operation_counters (
    experiment_run_id uuid NOT NULL REFERENCES research.experiment_runs(run_id),
    client_reference text NOT NULL,
    operation text NOT NULL,
    last_attempt_no integer NOT NULL,
    PRIMARY KEY (experiment_run_id, client_reference, operation)
);

CREATE TABLE IF NOT EXISTS simulator.supplier_calls (
    supplier_call_id bigserial PRIMARY KEY,
    experiment_run_id uuid REFERENCES research.experiment_runs(run_id),
    logical_booking_id text,
    client_reference text NOT NULL,
    operation text NOT NULL,
    operation_attempt_no integer,
    outcome text NOT NULL,
    supplier_order_id text,
    configured_delay_ms integer NOT NULL DEFAULT 0,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_supplier_calls_run_reference_time
    ON simulator.supplier_calls(experiment_run_id, client_reference, occurred_at);

CREATE INDEX IF NOT EXISTS ix_supplier_calls_run_operation
    ON simulator.supplier_calls(experiment_run_id, operation, operation_attempt_no);
