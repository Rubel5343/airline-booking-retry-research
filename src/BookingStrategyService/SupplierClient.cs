using System.Net;
using System.Net.Http.Json;

namespace BookingStrategyService;

public interface ISupplierClient
{
    Task<SupplierCreateResult> CreateAsync(
        SupplierCreateRequest request,
        TimeSpan timeout,
        CancellationToken ct);

    Task<SupplierRetrieveResult> RetrieveAsync(
        Guid experimentRunId,
        string clientReference,
        TimeSpan timeout,
        CancellationToken ct);
}

public sealed class SupplierClient(HttpClient httpClient) : ISupplierClient
{
    public async Task<SupplierCreateResult> CreateAsync(
        SupplierCreateRequest request,
        TimeSpan timeout,
        CancellationToken ct)
    {
        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeoutCts.CancelAfter(timeout);

        try
        {
            using var response = await httpClient.PostAsJsonAsync("/orders", request, timeoutCts.Token);
            if (response.IsSuccessStatusCode)
            {
                var body = await response.Content.ReadFromJsonAsync<CreateOrderResponse>(
                    cancellationToken: timeoutCts.Token);

                return body is null
                    ? new SupplierCreateResult(SupplierCreateOutcome.Ambiguous, ErrorCode: "EMPTY_SUCCESS_RESPONSE")
                    : new SupplierCreateResult(SupplierCreateOutcome.Success, body.SupplierOrderId);
            }

            if (response.StatusCode == HttpStatusCode.UnprocessableEntity)
                return new SupplierCreateResult(SupplierCreateOutcome.DefiniteFailure, ErrorCode: "BOOKING_REJECTED");

            return new SupplierCreateResult(
                SupplierCreateOutcome.Ambiguous,
                ErrorCode: $"HTTP_{(int)response.StatusCode}");
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            return new SupplierCreateResult(SupplierCreateOutcome.Ambiguous, ErrorCode: "CLIENT_TIMEOUT");
        }
        catch (HttpRequestException ex)
        {
            return new SupplierCreateResult(SupplierCreateOutcome.Ambiguous, ErrorCode: $"NETWORK_{ex.HttpRequestError}");
        }
    }

    public async Task<SupplierRetrieveResult> RetrieveAsync(
        Guid experimentRunId,
        string clientReference,
        TimeSpan timeout,
        CancellationToken ct)
    {
        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeoutCts.CancelAfter(timeout);

        try
        {
            var path = $"/orders/by-client-reference/{Uri.EscapeDataString(clientReference)}" +
                       $"?experimentRunId={Uri.EscapeDataString(experimentRunId.ToString())}";

            using var response = await httpClient.GetAsync(path, timeoutCts.Token);

            if (response.IsSuccessStatusCode)
            {
                var body = await response.Content.ReadFromJsonAsync<RetrieveOrderResponse>(
                    cancellationToken: timeoutCts.Token);

                return body is null
                    ? new SupplierRetrieveResult(SupplierRetrieveOutcome.Unknown, ErrorCode: "EMPTY_RETRIEVE_RESPONSE")
                    : new SupplierRetrieveResult(SupplierRetrieveOutcome.Found, body.SupplierOrderId);
            }

            if (response.StatusCode == HttpStatusCode.NotFound)
                return new SupplierRetrieveResult(SupplierRetrieveOutcome.NotFound);

            return new SupplierRetrieveResult(
                SupplierRetrieveOutcome.Unknown,
                ErrorCode: $"HTTP_{(int)response.StatusCode}");
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            return new SupplierRetrieveResult(SupplierRetrieveOutcome.Unknown, ErrorCode: "RETRIEVE_TIMEOUT");
        }
        catch (HttpRequestException ex)
        {
            return new SupplierRetrieveResult(SupplierRetrieveOutcome.Unknown, ErrorCode: $"NETWORK_{ex.HttpRequestError}");
        }
    }

    private sealed record CreateOrderResponse(
        string SupplierOrderId,
        string ClientReference,
        string Status);

    private sealed record RetrieveOrderResponse(
        string SupplierOrderId,
        string ClientReference,
        string Status,
        DateTimeOffset CreatedAt);
}
