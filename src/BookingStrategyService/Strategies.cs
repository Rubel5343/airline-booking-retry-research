using System.Diagnostics;

namespace BookingStrategyService;

public sealed class StrategyContext(
    BookingExperimentRequest request,
    Guid attemptId,
    ISupplierClient supplier,
    ExperimentRepository repository)
{
    public BookingExperimentRequest Request { get; } = request;
    public Guid AttemptId { get; } = attemptId;
    public ISupplierClient Supplier { get; } = supplier;
    public ExperimentRepository Repository { get; } = repository;
    public int CreateCalls { get; set; }
    public int RetrieveCalls { get; set; }
    public Stopwatch Stopwatch { get; } = Stopwatch.StartNew();

    public SupplierCreateRequest ToSupplierRequest() => new(
        Request.ExperimentRunId,
        Request.LogicalBookingId,
        Request.ClientReference,
        Request.Origin,
        Request.Destination);

    public BookingExecutionResult Result(
        string state,
        string? supplierOrderId = null,
        string? errorCode = null) =>
        new(state, supplierOrderId, CreateCalls, RetrieveCalls, Stopwatch.ElapsedMilliseconds, errorCode);
}

public interface IBookingRecoveryStrategy
{
    string Name { get; }
    Task<BookingExecutionResult> ExecuteAsync(StrategyContext context, CancellationToken ct);
}

public abstract class BookingRecoveryStrategyBase
{
    protected static TimeSpan BookingTimeout(StrategyContext context) =>
        TimeSpan.FromMilliseconds(Math.Max(1, context.Request.BookingTimeoutMs));

    protected static TimeSpan RetrieveTimeout(StrategyContext context) =>
        TimeSpan.FromMilliseconds(Math.Max(250, Math.Min(context.Request.BookingTimeoutMs, 5000)));

    protected static async Task<SupplierCreateResult> CreateAsync(StrategyContext context, CancellationToken ct)
    {
        context.CreateCalls++;
        await context.Repository.LogEventAsync(context.Request, context.AttemptId,
            "ORDER_CREATE_SENT", metadata: new { createCall = context.CreateCalls }, ct: ct);

        var result = await context.Supplier.CreateAsync(
            context.ToSupplierRequest(), BookingTimeout(context), ct);

        var eventType = result.Outcome switch
        {
            SupplierCreateOutcome.Success => "ORDER_CREATE_SUCCESS",
            SupplierCreateOutcome.DefiniteFailure => "ORDER_CREATE_DEFINITE_FAILURE",
            _ => "ORDER_CREATE_AMBIGUOUS"
        };
        await context.Repository.LogEventAsync(context.Request, context.AttemptId,
            eventType, result.SupplierOrderId,
            new { createCall = context.CreateCalls, result.ErrorCode }, ct);
        return result;
    }

    protected static async Task<SupplierRetrieveResult> RetrieveAsync(StrategyContext context, CancellationToken ct)
    {
        context.RetrieveCalls++;
        await context.Repository.LogEventAsync(context.Request, context.AttemptId,
            "RETRIEVE_SENT", metadata: new { retrieveCall = context.RetrieveCalls }, ct: ct);

        var result = await context.Supplier.RetrieveAsync(
            context.Request.ExperimentRunId,
            context.Request.ClientReference,
            RetrieveTimeout(context),
            ct);

        var eventType = result.Outcome switch
        {
            SupplierRetrieveOutcome.Found => "RETRIEVE_FOUND",
            SupplierRetrieveOutcome.NotFound => "RETRIEVE_NOT_FOUND",
            _ => "RETRIEVE_UNKNOWN"
        };
        await context.Repository.LogEventAsync(context.Request, context.AttemptId,
            eventType, result.SupplierOrderId,
            new { retrieveCall = context.RetrieveCalls, result.ErrorCode }, ct);
        return result;
    }
}

public sealed class ImmediateBlindRetryStrategy : BookingRecoveryStrategyBase, IBookingRecoveryStrategy
{
    public string Name => "ImmediateBlindRetry";

    public async Task<BookingExecutionResult> ExecuteAsync(StrategyContext context, CancellationToken ct)
    {
        var first = await CreateAsync(context, ct);
        if (first.Outcome == SupplierCreateOutcome.Success)
            return context.Result("SUCCESS", first.SupplierOrderId);
        if (first.Outcome == SupplierCreateOutcome.DefiniteFailure)
            return context.Result("FAILED", errorCode: first.ErrorCode);

        await context.Repository.LogEventAsync(context.Request, context.AttemptId,
            "BLIND_RETRY_TRIGGERED", metadata: new { delayMs = 0 }, ct: ct);
        var retry = await CreateAsync(context, ct);
        return retry.Outcome switch
        {
            SupplierCreateOutcome.Success => context.Result("SUCCESS", retry.SupplierOrderId),
            SupplierCreateOutcome.DefiniteFailure => context.Result("FAILED", errorCode: retry.ErrorCode),
            _ => context.Result("UNKNOWN", errorCode: retry.ErrorCode)
        };
    }
}

public sealed class DelayedBlindRetryStrategy : BookingRecoveryStrategyBase, IBookingRecoveryStrategy
{
    public string Name => "DelayedBlindRetry";

    public async Task<BookingExecutionResult> ExecuteAsync(StrategyContext context, CancellationToken ct)
    {
        var first = await CreateAsync(context, ct);
        if (first.Outcome == SupplierCreateOutcome.Success)
            return context.Result("SUCCESS", first.SupplierOrderId);
        if (first.Outcome == SupplierCreateOutcome.DefiniteFailure)
            return context.Result("FAILED", errorCode: first.ErrorCode);

        var delay = Math.Max(0, context.Request.DelayedRetryMs);
        await context.Repository.LogEventAsync(context.Request, context.AttemptId,
            "DELAYED_RETRY_WAIT", metadata: new { delayMs = delay }, ct: ct);
        if (delay > 0)
            await Task.Delay(delay, ct);

        var retry = await CreateAsync(context, ct);
        return retry.Outcome switch
        {
            SupplierCreateOutcome.Success => context.Result("SUCCESS", retry.SupplierOrderId),
            SupplierCreateOutcome.DefiniteFailure => context.Result("FAILED", errorCode: retry.ErrorCode),
            _ => context.Result("UNKNOWN", errorCode: retry.ErrorCode)
        };
    }
}

public sealed class RetrieveBeforeRetryStrategy : BookingRecoveryStrategyBase, IBookingRecoveryStrategy
{
    public string Name => "RetrieveBeforeRetry";

    public async Task<BookingExecutionResult> ExecuteAsync(StrategyContext context, CancellationToken ct)
    {
        var first = await CreateAsync(context, ct);
        if (first.Outcome == SupplierCreateOutcome.Success)
            return context.Result("SUCCESS", first.SupplierOrderId);
        if (first.Outcome == SupplierCreateOutcome.DefiniteFailure)
            return context.Result("FAILED", errorCode: first.ErrorCode);

        await context.Repository.LogEventAsync(context.Request, context.AttemptId,
            "BOOKING_ATTEMPT_UNKNOWN", metadata: new { reason = first.ErrorCode }, ct: ct);

        var attempts = Math.Max(1, context.Request.RetrieveAttempts);
        var sawUnknownRetrieve = false;

        for (var i = 1; i <= attempts; i++)
        {
            var retrieve = await RetrieveAsync(context, ct);
            if (retrieve.Outcome == SupplierRetrieveOutcome.Found)
                return context.Result("SUCCESS", retrieve.SupplierOrderId);

            if (retrieve.Outcome == SupplierRetrieveOutcome.Unknown)
                sawUnknownRetrieve = true;

            if (i < attempts && context.Request.RetrieveDelayMs > 0)
                await Task.Delay(context.Request.RetrieveDelayMs, ct);
        }

        if (sawUnknownRetrieve)
        {
            await context.Repository.LogEventAsync(context.Request, context.AttemptId,
                "RECONCILIATION_INCONCLUSIVE", ct: ct);
            return context.Result("UNKNOWN", errorCode: "RETRIEVE_INCONCLUSIVE");
        }

        await context.Repository.LogEventAsync(context.Request, context.AttemptId,
            "CONTROLLED_RETRY_AFTER_NOT_FOUND", ct: ct);
        var retry = await CreateAsync(context, ct);
        return retry.Outcome switch
        {
            SupplierCreateOutcome.Success => context.Result("SUCCESS", retry.SupplierOrderId),
            SupplierCreateOutcome.DefiniteFailure => context.Result("FAILED", errorCode: retry.ErrorCode),
            _ => context.Result("UNKNOWN", errorCode: retry.ErrorCode)
        };
    }
}
