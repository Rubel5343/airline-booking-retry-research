namespace SupplierSimulator;

public sealed record CreateOrderRequest(
    Guid ExperimentRunId,
    string LogicalBookingId,
    string ClientReference,
    string Origin,
    string Destination);

public sealed record CreateOrderResponse(
    string SupplierOrderId,
    string ClientReference,
    string Status);

public sealed record RetrieveOrderResponse(
    string SupplierOrderId,
    string ClientReference,
    string Status,
    DateTimeOffset CreatedAt);

public sealed record SimulatorConfig(
    int RandomSeed = 12345,
    int ProcessingDelayMs = 500,
    int ProcessingJitterMs = 0,
    double ResponseLossProbability = 0.10,
    double DefiniteFailureProbability = 0.0,
    double TransientFailureProbability = 0.0,
    double HiddenSuccessProbabilityOnResponseLoss = 1.0,
    int VisibilityDelayMs = 0,
    double RetrieveFailureProbability = 0.0,
    int RetrieveDelayMs = 50,
    int ResponseLossHoldMs = 15000)
{
    public IReadOnlyList<string> Validate()
    {
        var errors = new List<string>();

        if (ProcessingDelayMs < 0) errors.Add("processingDelayMs must be >= 0");
        if (ProcessingJitterMs < 0) errors.Add("processingJitterMs must be >= 0");
        if (VisibilityDelayMs < 0) errors.Add("visibilityDelayMs must be >= 0");
        if (RetrieveDelayMs < 0) errors.Add("retrieveDelayMs must be >= 0");
        if (ResponseLossHoldMs < 0) errors.Add("responseLossHoldMs must be >= 0");

        ValidateProbability(ResponseLossProbability, "responseLossProbability", errors);
        ValidateProbability(DefiniteFailureProbability, "definiteFailureProbability", errors);
        ValidateProbability(TransientFailureProbability, "transientFailureProbability", errors);
        ValidateProbability(HiddenSuccessProbabilityOnResponseLoss, "hiddenSuccessProbabilityOnResponseLoss", errors);
        ValidateProbability(RetrieveFailureProbability, "retrieveFailureProbability", errors);

        if (DefiniteFailureProbability + TransientFailureProbability > 1.0)
            errors.Add("definiteFailureProbability + transientFailureProbability must be <= 1.0");

        return errors;
    }

    private static void ValidateProbability(double value, string name, ICollection<string> errors)
    {
        if (value is < 0.0 or > 1.0)
            errors.Add($"{name} must be between 0.0 and 1.0");
    }
}
