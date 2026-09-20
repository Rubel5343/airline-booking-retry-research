using BookingStrategyService;
using Npgsql;

var builder = WebApplication.CreateBuilder(args);

var connectionString = builder.Configuration.GetConnectionString("Postgres")
    ?? throw new InvalidOperationException("ConnectionStrings:Postgres is required.");
var supplierBaseUrl = builder.Configuration["Supplier:BaseUrl"]
    ?? throw new InvalidOperationException("Supplier:BaseUrl is required.");

builder.Services.AddSingleton(NpgsqlDataSource.Create(connectionString));
builder.Services.AddSingleton<ExperimentRepository>();
builder.Services.AddHttpClient<ISupplierClient, SupplierClient>(client =>
{
    client.BaseAddress = new Uri(supplierBaseUrl);
    client.Timeout = Timeout.InfiniteTimeSpan;
});
builder.Services.AddSingleton<IBookingRecoveryStrategy, ImmediateBlindRetryStrategy>();
builder.Services.AddSingleton<IBookingRecoveryStrategy, DelayedBlindRetryStrategy>();
builder.Services.AddSingleton<IBookingRecoveryStrategy, RetrieveBeforeRetryStrategy>();
builder.Services.AddSingleton<StrategyResolver>();

var app = builder.Build();

app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.MapPost("/experiment-runs", async (
    CreateExperimentRunRequest request,
    ExperimentRepository repository,
    CancellationToken ct) =>
{
    var runId = await repository.CreateRunAsync(request, ct);
    return Results.Created($"/experiment-runs/{runId}", new { runId });
});

app.MapPost("/experiment-runs/{runId:guid}/complete", async (
    Guid runId,
    ExperimentRepository repository,
    CancellationToken ct) =>
{
    await repository.CompleteRunAsync(runId, ct);
    return Results.Ok(new { runId, completed = true });
});

app.MapGet("/experiment-runs/{runId:guid}/summary", async (
    Guid runId,
    ExperimentRepository repository,
    CancellationToken ct) =>
{
    var summary = await repository.GetSummaryAsync(runId, ct);
    return Results.Ok(new { runId, summary });
});

app.MapPost("/bookings", async (
    BookingExperimentRequest request,
    StrategyResolver resolver,
    ISupplierClient supplier,
    ExperimentRepository repository,
    CancellationToken ct) =>
{
    if (string.IsNullOrWhiteSpace(request.ClientReference) ||
        string.IsNullOrWhiteSpace(request.LogicalBookingId))
        return Results.BadRequest(new { error = "logicalBookingId and clientReference are required" });

    IBookingRecoveryStrategy strategy;
    try
    {
        strategy = resolver.Resolve(request.Strategy);
    }
    catch (ArgumentException ex)
    {
        return Results.BadRequest(new { error = ex.Message });
    }

    Guid attemptId;
    try
    {
        attemptId = await repository.CreateAttemptAsync(request, ct);
    }
    catch (PostgresException ex) when (ex.SqlState == PostgresErrorCodes.UniqueViolation)
    {
        return Results.Conflict(new { error = "logical booking already exists in this experiment run" });
    }

    await repository.LogEventAsync(request, attemptId, "BOOKING_ATTEMPT_STARTED",
        metadata: new
        {
            strategy = strategy.Name,
            request.BookingTimeoutMs,
            request.RetrieveAttempts,
            request.RetrieveDelayMs,
            request.DelayedRetryMs
        }, ct: ct);

    var context = new StrategyContext(request, attemptId, supplier, repository);
    BookingExecutionResult result;
    try
    {
        result = await strategy.ExecuteAsync(context, ct);
    }
    catch (OperationCanceledException) when (ct.IsCancellationRequested)
    {
        result = context.Result("SYSTEM_ERROR", errorCode: "REQUEST_CANCELLED");
    }
    catch (Exception ex)
    {
        result = context.Result("SYSTEM_ERROR", errorCode: ex.GetType().Name);
    }

    await repository.LogEventAsync(request, attemptId, $"FINAL_{result.State}",
        result.SupplierOrderId, new { result.ErrorCode, result.ResolutionMs }, CancellationToken.None);
    await repository.CompleteAttemptAsync(attemptId, result, CancellationToken.None);

    if (result.State == "SYSTEM_ERROR")
        return Results.Json(new { attemptId, result }, statusCode: StatusCodes.Status500InternalServerError);

    return result.State == "UNKNOWN"
        ? Results.Accepted(value: new { attemptId, result })
        : Results.Ok(new { attemptId, result });
});

app.Run();
