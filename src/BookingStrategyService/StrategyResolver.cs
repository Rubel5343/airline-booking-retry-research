namespace BookingStrategyService;

public sealed class StrategyResolver(IEnumerable<IBookingRecoveryStrategy> strategies)
{
    private readonly Dictionary<string, IBookingRecoveryStrategy> _strategies =
        strategies.ToDictionary(x => x.Name, StringComparer.OrdinalIgnoreCase);

    public IBookingRecoveryStrategy Resolve(string name)
    {
        if (_strategies.TryGetValue(name, out var strategy))
            return strategy;

        throw new ArgumentException(
            $"Unknown strategy '{name}'. Supported: {string.Join(", ", _strategies.Keys)}");
    }
}
