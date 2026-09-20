using Npgsql;
using SupplierSimulator;

var builder = WebApplication.CreateBuilder(args);

var connectionString = builder.Configuration.GetConnectionString("Postgres")
    ?? throw new InvalidOperationException("ConnectionStrings:Postgres is required.");

builder.Services.AddSingleton(NpgsqlDataSource.Create(connectionString));
builder.Services.AddSingleton<SimulatorStore>();
builder.Services.AddSingleton<DeterministicDecider>();
builder.Services.AddSingleton<ConfigHolder>();

var app = builder.Build();

app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.MapPut("/admin/config", (SimulatorConfig config, ConfigHolder holder) =>
{
    var errors = config.Validate();
    if (errors.Count > 0)
        return Results.BadRequest(new { errors });

    holder.Value = config;
    return Results.Ok(config);
});

app.MapGet("/admin/config", (ConfigHolder holder) => Results.Ok(holder.Value));

app.MapPost("/admin/reset", async (SimulatorStore store, CancellationToken ct) =>
{
    await store.ResetAllAsync(ct);
    return Results.Ok(new { reset = true });
});

app.MapGet("/admin/ground-truth/{clientReference}", async (
    string clientReference,
    Guid experimentRunId,
    SimulatorStore store,
    CancellationToken ct) =>
{
    return Results.Ok(await store.GroundTruthAsync(experimentRunId, clientReference, ct));
});

app.MapPost("/orders", async (
    CreateOrderRequest request,
    SimulatorStore store,
    DeterministicDecider decider,
    ConfigHolder configHolder) =>
{
    var config = configHolder.Value;
    var faultKey = string.IsNullOrWhiteSpace(request.FaultCohort)
        ? request.ExperimentRunId.ToString("N")
        : request.FaultCohort;
    var attemptNo = await store.NextCreateAttemptAsync(
        request.ExperimentRunId,
        request.ClientReference,
        CancellationToken.None);

    var jitter = config.ProcessingJitterMs <= 0
        ? 0
        : decider.Range(
            config.RandomSeed,
            0,
            config.ProcessingJitterMs,
            faultKey,
            request.ClientReference,
            attemptNo.ToString(),
            "processing-jitter");

    var processingDelayMs = config.ProcessingDelayMs + jitter;

    var decision = decider.UnitInterval(
        config.RandomSeed,
        faultKey,
        request.ClientReference,
        attemptNo.ToString(),
        "pre-create-outcome");

    var definiteFailure = decision < config.DefiniteFailureProbability;
    var transientFailure = !definiteFailure &&
        decision < config.DefiniteFailureProbability + config.TransientFailureProbability;

    if (processingDelayMs > 0)
        await Task.Delay(processingDelayMs);

    if (definiteFailure)
    {
        await store.LogCallAsync(
            request.ExperimentRunId,
            request.LogicalBookingId,
            request.ClientReference,
            "CREATE",
            attemptNo,
            "DEFINITE_REJECTION",
            null,
            processingDelayMs,
            CancellationToken.None);

        return Results.Json(
            new
            {
                code = "BOOKING_REJECTED",
                message = "Simulator definite pre-create rejection"
            },
            statusCode: StatusCodes.Status422UnprocessableEntity);
    }

    if (transientFailure)
    {
        await store.LogCallAsync(
            request.ExperimentRunId,
            request.LogicalBookingId,
            request.ClientReference,
            "CREATE",
            attemptNo,
            "TRANSIENT_503_NO_CREATE",
            null,
            processingDelayMs,
            CancellationToken.None);

        return Results.StatusCode(StatusCodes.Status503ServiceUnavailable);
    }

    var responseLost = decider.UnitInterval(
        config.RandomSeed,
        faultKey,
        request.ClientReference,
        attemptNo.ToString(),
        "response-loss") < config.ResponseLossProbability;

    var hiddenSuccess = !responseLost ||
        decider.UnitInterval(
            config.RandomSeed,
            faultKey,
            request.ClientReference,
            attemptNo.ToString(),
            "hidden-success") < config.HiddenSuccessProbabilityOnResponseLoss;

    if (!hiddenSuccess)
    {
        await store.LogCallAsync(
            request.ExperimentRunId,
            request.LogicalBookingId,
            request.ClientReference,
            "CREATE",
            attemptNo,
            "RESPONSE_LOST_WITHOUT_CREATE",
            null,
            processingDelayMs,
            CancellationToken.None);

        if (config.ResponseLossHoldMs > 0)
            await Task.Delay(config.ResponseLossHoldMs);

        return Results.StatusCode(StatusCodes.Status504GatewayTimeout);
    }

    var createdAt = DateTimeOffset.UtcNow;
    var supplierOrderId = $"ORD-{Guid.NewGuid():N}";
    var visibleAt = createdAt.AddMilliseconds(config.VisibilityDelayMs);

    await store.InsertOrderAsync(
        request,
        attemptNo,
        supplierOrderId,
        createdAt,
        visibleAt,
        responseLost,
        CancellationToken.None);

    await store.LogCallAsync(
        request.ExperimentRunId,
        request.LogicalBookingId,
        request.ClientReference,
        "CREATE",
        attemptNo,
        responseLost ? "CREATED_RESPONSE_LOST" : "CREATED_RESPONSE_RETURNED",
        supplierOrderId,
        processingDelayMs,
        CancellationToken.None);

    if (responseLost && config.ResponseLossHoldMs > 0)
        await Task.Delay(config.ResponseLossHoldMs);

    return Results.Ok(new CreateOrderResponse(
        supplierOrderId,
        request.ClientReference,
        "CONFIRMED"));
});

app.MapGet("/orders/by-client-reference/{clientReference}", async (
    string clientReference,
    Guid experimentRunId,
    string? faultCohort,
    SimulatorStore store,
    DeterministicDecider decider,
    ConfigHolder configHolder) =>
{
    var config = configHolder.Value;
    var faultKey = string.IsNullOrWhiteSpace(faultCohort)
        ? experimentRunId.ToString("N")
        : faultCohort;
    var retrieveAttemptNo = await store.NextRetrieveAttemptAsync(
        experimentRunId,
        clientReference,
        CancellationToken.None);

    var fail = decider.UnitInterval(
        config.RandomSeed,
        faultKey,
        clientReference,
        retrieveAttemptNo.ToString(),
        "retrieve-failure") < config.RetrieveFailureProbability;

    if (config.RetrieveDelayMs > 0)
        await Task.Delay(config.RetrieveDelayMs);

    if (fail)
    {
        await store.LogCallAsync(
            experimentRunId,
            null,
            clientReference,
            "RETRIEVE",
            retrieveAttemptNo,
            "TRANSIENT_FAILURE",
            null,
            config.RetrieveDelayMs,
            CancellationToken.None);

        return Results.StatusCode(StatusCodes.Status503ServiceUnavailable);
    }

    var order = await store.RetrieveVisibleAsync(
        experimentRunId,
        clientReference,
        CancellationToken.None);

    await store.LogCallAsync(
        experimentRunId,
        null,
        clientReference,
        "RETRIEVE",
        retrieveAttemptNo,
        order is null ? "NOT_FOUND" : "FOUND",
        order?.SupplierOrderId,
        config.RetrieveDelayMs,
        CancellationToken.None);

    return order is null ? Results.NotFound() : Results.Ok(order);
});

app.Run();

public sealed class ConfigHolder
{
    private SimulatorConfig _value = new();

    public SimulatorConfig Value
    {
        get => Volatile.Read(ref _value);
        set => Volatile.Write(ref _value, value);
    }
}
