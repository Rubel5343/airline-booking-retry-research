using Npgsql;

namespace SupplierSimulator;

public sealed class SimulatorStore(NpgsqlDataSource dataSource)
{
    public Task<int> NextCreateAttemptAsync(
        Guid experimentRunId,
        string clientReference,
        CancellationToken ct) =>
        NextOperationAttemptAsync(experimentRunId, clientReference, "CREATE", ct);

    public Task<int> NextRetrieveAttemptAsync(
        Guid experimentRunId,
        string clientReference,
        CancellationToken ct) =>
        NextOperationAttemptAsync(experimentRunId, clientReference, "RETRIEVE", ct);

    private async Task<int> NextOperationAttemptAsync(
        Guid experimentRunId,
        string clientReference,
        string operation,
        CancellationToken ct)
    {
        await using var cmd = dataSource.CreateCommand("""
            INSERT INTO simulator.operation_counters
                (experiment_run_id, client_reference, operation, last_attempt_no)
            VALUES ($1, $2, $3, 1)
            ON CONFLICT (experiment_run_id, client_reference, operation)
            DO UPDATE SET last_attempt_no = simulator.operation_counters.last_attempt_no + 1
            RETURNING last_attempt_no
            """);
        cmd.Parameters.AddWithValue(experimentRunId);
        cmd.Parameters.AddWithValue(clientReference);
        cmd.Parameters.AddWithValue(operation);
        var result = await cmd.ExecuteScalarAsync(ct);
        return Convert.ToInt32(result);
    }

    public async Task InsertOrderAsync(
        CreateOrderRequest request,
        int attemptNo,
        string supplierOrderId,
        DateTimeOffset createdAt,
        DateTimeOffset visibleAt,
        bool responseLost,
        CancellationToken ct)
    {
        await using var cmd = dataSource.CreateCommand("""
            INSERT INTO simulator.supplier_orders
            (supplier_order_id, experiment_run_id, logical_booking_id, client_reference,
             create_attempt_no, origin, destination, created_at, visible_at, response_lost)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            """);
        cmd.Parameters.AddWithValue(supplierOrderId);
        cmd.Parameters.AddWithValue(request.ExperimentRunId);
        cmd.Parameters.AddWithValue(request.LogicalBookingId);
        cmd.Parameters.AddWithValue(request.ClientReference);
        cmd.Parameters.AddWithValue(attemptNo);
        cmd.Parameters.AddWithValue(request.Origin);
        cmd.Parameters.AddWithValue(request.Destination);
        cmd.Parameters.AddWithValue(createdAt);
        cmd.Parameters.AddWithValue(visibleAt);
        cmd.Parameters.AddWithValue(responseLost);
        await cmd.ExecuteNonQueryAsync(ct);
    }

    public async Task LogCallAsync(
        Guid? experimentRunId,
        string? logicalBookingId,
        string clientReference,
        string operation,
        int? operationAttemptNo,
        string outcome,
        string? supplierOrderId,
        int configuredDelayMs,
        CancellationToken ct)
    {
        await using var cmd = dataSource.CreateCommand("""
            INSERT INTO simulator.supplier_calls
            (experiment_run_id, logical_booking_id, client_reference, operation,
             operation_attempt_no, outcome, supplier_order_id, configured_delay_ms)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            """);
        cmd.Parameters.AddWithValue((object?)experimentRunId ?? DBNull.Value);
        cmd.Parameters.AddWithValue((object?)logicalBookingId ?? DBNull.Value);
        cmd.Parameters.AddWithValue(clientReference);
        cmd.Parameters.AddWithValue(operation);
        cmd.Parameters.AddWithValue((object?)operationAttemptNo ?? DBNull.Value);
        cmd.Parameters.AddWithValue(outcome);
        cmd.Parameters.AddWithValue((object?)supplierOrderId ?? DBNull.Value);
        cmd.Parameters.AddWithValue(configuredDelayMs);
        await cmd.ExecuteNonQueryAsync(ct);
    }

    public async Task<RetrieveOrderResponse?> RetrieveVisibleAsync(
        Guid experimentRunId,
        string clientReference,
        CancellationToken ct)
    {
        await using var cmd = dataSource.CreateCommand("""
            SELECT supplier_order_id, client_reference, created_at
            FROM simulator.supplier_orders
            WHERE experiment_run_id = $1
              AND client_reference = $2
              AND visible_at <= now()
            ORDER BY created_at ASC
            LIMIT 1
            """);
        cmd.Parameters.AddWithValue(experimentRunId);
        cmd.Parameters.AddWithValue(clientReference);
        await using var reader = await cmd.ExecuteReaderAsync(ct);
        if (!await reader.ReadAsync(ct))
            return null;

        return new RetrieveOrderResponse(
            reader.GetString(0),
            reader.GetString(1),
            "CONFIRMED",
            reader.GetFieldValue<DateTimeOffset>(2));
    }

    public async Task<object> GroundTruthAsync(
        Guid experimentRunId,
        string clientReference,
        CancellationToken ct)
    {
        await using var cmd = dataSource.CreateCommand("""
            SELECT supplier_order_id, create_attempt_no, created_at, visible_at, response_lost
            FROM simulator.supplier_orders
            WHERE experiment_run_id = $1
              AND client_reference = $2
            ORDER BY created_at
            """);
        cmd.Parameters.AddWithValue(experimentRunId);
        cmd.Parameters.AddWithValue(clientReference);
        await using var reader = await cmd.ExecuteReaderAsync(ct);
        var orders = new List<object>();
        while (await reader.ReadAsync(ct))
        {
            orders.Add(new
            {
                supplierOrderId = reader.GetString(0),
                createAttemptNo = reader.GetInt32(1),
                createdAt = reader.GetFieldValue<DateTimeOffset>(2),
                visibleAt = reader.GetFieldValue<DateTimeOffset>(3),
                responseLost = reader.GetBoolean(4)
            });
        }

        return new { experimentRunId, clientReference, orderCount = orders.Count, orders };
    }

    public async Task ResetAllAsync(CancellationToken ct)
    {
        await using var cmd = dataSource.CreateCommand("""
            TRUNCATE TABLE simulator.supplier_calls RESTART IDENTITY;
            TRUNCATE TABLE simulator.operation_counters;
            TRUNCATE TABLE simulator.supplier_orders;
            """);
        await cmd.ExecuteNonQueryAsync(ct);
    }
}
