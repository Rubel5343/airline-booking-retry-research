namespace BookingStrategyService;

public sealed record CreateExperimentRunRequest(
    string Name,
    int RandomSeed,
    Dictionary<string, object>? Config = null,
    string? GitCommit = null);

public sealed record BookingExperimentRequest(
    Guid ExperimentRunId,
    string LogicalBookingId,
    string ClientReference,
    string Origin,
    string Destination,
    string Strategy,
    int BookingTimeoutMs = 3000,
    int DelayedRetryMs = 1000,
    int RetrieveAttempts = 3,
    int RetrieveDelayMs = 1000);

public sealed record BookingExecutionResult(
    string State,
    string? SupplierOrderId,
    int CreateCallCount,
    int RetrieveCallCount,
    long ResolutionMs,
    string? ErrorCode = null);

public sealed record ExperimentSummary(
    string Strategy,
    long LogicalBookings,
    long DuplicateLogicalBookings,
    double DuplicateRatePct,
    long UnresolvedBookings,
    double AvgResolutionMs,
    double P50ResolutionMs,
    double P95ResolutionMs,
    double P99ResolutionMs,
    double AvgSupplierCallsPerBooking,
    double AvgCreateCalls,
    double AvgRetrieveCalls);

public enum SupplierCreateOutcome
{
    Success,
    DefiniteFailure,
    Ambiguous
}

public sealed record SupplierCreateResult(
    SupplierCreateOutcome Outcome,
    string? SupplierOrderId = null,
    string? ErrorCode = null);

public enum SupplierRetrieveOutcome
{
    Found,
    NotFound,
    Unknown
}

public sealed record SupplierRetrieveResult(
    SupplierRetrieveOutcome Outcome,
    string? SupplierOrderId = null,
    string? ErrorCode = null);

public sealed record SupplierCreateRequest(
    Guid ExperimentRunId,
    string LogicalBookingId,
    string ClientReference,
    string Origin,
    string Destination);
