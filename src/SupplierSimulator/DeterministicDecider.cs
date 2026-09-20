using System.Security.Cryptography;
using System.Text;

namespace SupplierSimulator;

public sealed class DeterministicDecider
{
    public double UnitInterval(int seed, params string[] parts)
    {
        var input = seed + "|" + string.Join("|", parts);
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(input));
        var value = BitConverter.ToUInt64(hash, 0);
        return value / ((double)ulong.MaxValue + 1d);
    }

    public int Range(int seed, int minInclusive, int maxInclusive, params string[] parts)
    {
        if (maxInclusive <= minInclusive)
            return minInclusive;

        var u = UnitInterval(seed, parts);
        return minInclusive + (int)Math.Floor(u * (maxInclusive - minInclusive + 1));
    }
}
