using System.Text.Json;
using Npgsql;

namespace BookingStrategyService;

public sealed class ExperimentRepository(NpgsqlDataSource dataSource)
{
    public async Task<Guid> CreateRunAsync(CreateExperimentRunRequest request, CancellationToken ct)
    {
        var configJson = JsonSerializer.Serialize(request.Config ?? new Dictionary<string, object>());
        await using var cmd = dataSource.CreateCommand("""
            INSERT INTO research.experiment_runs(name, random_seed, config, git_commit)
            VALUES ($1,$2,$3::jsonb,$4)
            RETURNING run_id
            """);
        cmd.Parameters.AddWithValue(request.Name);
        cmd.Parameters.AddWithValue(request.RandomSeed);
        cmd.Parameters.AddWithValue(configJson);
        cmd.Parameters.AddWithValue((object?)request.GitCommit ?? DBNull.Value);
        var result = await cmd.ExecuteScalarAsync(ct);
        return (Guid)(result ?? throw new InvalidOperationException("Experiment run ID was not returned."));
    }

    public async Task CompleteRunAsync(Guid runId, CancellationToken ct)
    {
        await using var cmd = dataSource.CreateCommand("""
            UPDATE research.experiment_runs
            SET completed_at = COALESCE(completed_at, now())
            WHERE run_id = $1
            """);
        cmd.Parameters.AddWithValue(runId);
        await cmd.ExecuteNonQueryAsync(ct);
    }

    public async Task<Guid> CreateAttemptAsync(BookingExperimentRequest request, CancellationToken ct)
    {
        await using var cmd = dataSource.CreateCommand("""
            INSERT INTO research.booking_attempts
            (experiment_run_id, logical_booking_id, client_reference, strategy, state)
            VALUES ($1,$2,$3,$4,'PROCESSING')
            RETURNING attempt_id
            """);
        cmd.Parameters.AddWithValue(request.ExperimentRunId);
        cmd.Parameters.AddWithValue(request.LogicalBookingId);
        cmd.Parameters.AddWithValue(request.ClientReference);
        cmd.Parameters.AddWithValue(request.Strategy);
        var result = await cmd.ExecuteScalarAsync(ct);
        return (Guid)(result ?? throw new InvalidOperationException("Attempt ID was not returned."));
    }

    public async Task LogEventAsync(
        BookingExperimentRequest request,
        Guid attemptId,
        string eventType,
        string? supplierOrderId = null,
        object? metadata = null,
        CancellationToken ct = default)
    {
        var metadataJson = JsonSerializer.Serialize(metadata ?? new { });
        await using var cmd = dataSource.CreateCommand("""
            INSERT INTO research.booking_events
            (experiment_run_id, attempt_id, logical_booking_id, client_reference,
             event_type, supplier_order_id, metadata)
            VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb)
            """);
        cmd.Parameters.AddWithValue(request.ExperimentRunId);
        cmd.Parameters.AddWithValue(attemptId);
        cmd.Parameters.AddWithValue(request.LogicalBookingId);
        cmd.Parameters.AddWithValue(request.ClientReference);
        cmd.Parameters.AddWithValue(eventType);
        cmd.Parameters.AddWithValue((object?)supplierOrderId ?? DBNull.Value);
        cmd.Parameters.AddWithValue(metadataJson);
        await cmd.ExecuteNonQueryAsync(ct);
    }

    public async Task CompleteAttemptAsync(
        Guid attemptId,
        BookingExecutionResult result,
        CancellationToken ct)
    {
        await using var cmd = dataSource.CreateCommand("""
            UPDATE research.booking_attempts
            SET state = $2,
                supplier_order_id = $3,
                create_call_count = $4,
                retrieve_call_count = $5,
                resolved_at = now(),
                resolution_ms = $6,
                error_code = $7
            WHERE attempt_id = $1
            """);
        cmd.Parameters.AddWithValue(attemptId);
        cmd.Parameters.AddWithValue(result.State);
        cmd.Parameters.AddWithValue((object?)result.SupplierOrderId ?? DBNull.Value);
        cmd.Parameters.AddWithValue(result.CreateCallCount);
        cmd.Parameters.AddWithValue(result.RetrieveCallCount);
        cmd.Parameters.AddWithValue(result.ResolutionMs);
        cmd.Parameters.AddWithValue((object?)result.ErrorCode ?? DBNull.Value);
        await cmd.ExecuteNonQueryAsync(ct);
    }

    public async Task<IReadOnlyList<ClientExperimentSummary>> GetSummaryAsync(Guid runId, CancellationToken ct)
    {
        await using var cmd = dataSource.CreateCommand("""
            SELECT
                strategy,
                COUNT(*)::bigint AS logical_bookings,
                COUNT(*) FILTER (WHERE state = 'UNKNOWN')::bigint AS unresolved_bookings,
                COALESCE(AVG(resolution_ms), 0)::double precision AS avg_resolution_ms,
                COALESCE(percentile_cont(0.50) WITHIN GROUP (ORDER BY resolution_ms), 0)::double precision AS p50_resolution_ms,
                COALESCE(percentile_cont(0.95) WITHIN GROUP (ORDER BY resolution_ms), 0)::double precision AS p95_resolution_ms,
                COALESCE(percentile_cont(0.99) WITHIN GROUP (ORDER BY resolution_ms), 0)::double precision AS p99_resolution_ms,
                COALESCE(AVG(create_call_count + retrieve_call_count), 0)::double precision AS avg_supplier_calls_per_booking,
                COALESCE(AVG(create_call_count), 0)::double precision AS avg_create_calls,
                COALESCE(AVG(retrieve_call_count), 0)::double precision AS avg_retrieve_calls
            FROM research.booking_attempts
            WHERE experiment_run_id = $1
              AND state <> 'SYSTEM_ERROR'
            GROUP BY strategy
            ORDER BY strategy
            """);
        cmd.Parameters.AddWithValue(runId);

        var result = new List<ClientExperimentSummary>();
        await using var reader = await cmd.ExecuteReaderAsync(ct);
        while (await reader.ReadAsync(ct))
        {
            result.Add(new ClientExperimentSummary(
                Strategy: reader.GetString(0),
                LogicalBookings: reader.GetInt64(1),
                UnresolvedBookings: reader.GetInt64(2),
                AvgResolutionMs: reader.GetDouble(3),
                P50ResolutionMs: reader.GetDouble(4),
                P95ResolutionMs: reader.GetDouble(5),
                P99ResolutionMs: reader.GetDouble(6),
                AvgSupplierCallsPerBooking: reader.GetDouble(7),
                AvgCreateCalls: reader.GetDouble(8),
                AvgRetrieveCalls: reader.GetDouble(9)));
        }

        return result;
    }
}
