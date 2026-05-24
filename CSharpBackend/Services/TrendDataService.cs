using System.Collections.Concurrent;

namespace OpcDaWebBrowser.Services;

public class TrendDataService
{
    private readonly ConcurrentDictionary<string, List<TrendDataPoint>> _trendData = new();
    private readonly int _maxDataPointsPerTag = 10000; // Keep last 10k points per tag
    private readonly object _lock = new();

    public void AddDataPoint(string itemID, string value, string quality, DateTime timestamp)
    {
        lock (_lock)
        {
            if (!_trendData.ContainsKey(itemID))
            {
                _trendData[itemID] = new List<TrendDataPoint>();
            }

            var dataPoint = new TrendDataPoint
            {
                Timestamp = timestamp,
                Value = value,
                Quality = quality,
                NumericValue = TryParseNumeric(value)
            };

            _trendData[itemID].Add(dataPoint);

            // Keep only the most recent data points
            if (_trendData[itemID].Count > _maxDataPointsPerTag)
            {
                _trendData[itemID].RemoveRange(0, _trendData[itemID].Count - _maxDataPointsPerTag);
            }
        }
    }

    public List<TrendDataPoint> GetTrendData(string itemID, DateTime startTime, DateTime endTime)
    {
        lock (_lock)
        {
            if (!_trendData.ContainsKey(itemID))
                return new List<TrendDataPoint>();

            return _trendData[itemID]
                .Where(dp => dp.Timestamp >= startTime && dp.Timestamp <= endTime)
                .OrderBy(dp => dp.Timestamp)
                .ToList();
        }
    }

    public TrendStats GetTrendStats(string itemID, DateTime startTime, DateTime endTime)
    {
        var data = GetTrendData(itemID, startTime, endTime);
        var numericData = data.Where(dp => dp.NumericValue.HasValue).Select(dp => dp.NumericValue!.Value).ToList();

        if (!numericData.Any())
        {
            return new TrendStats
            {
                Count = data.Count,
                Min = null,
                Max = null,
                Average = null,
                LastValue = data.LastOrDefault()?.Value,
                FirstValue = data.FirstOrDefault()?.Value
            };
        }

        return new TrendStats
        {
            Count = data.Count,
            Min = numericData.Min(),
            Max = numericData.Max(),
            Average = numericData.Average(),
            LastValue = data.LastOrDefault()?.Value,
            FirstValue = data.FirstOrDefault()?.Value
        };
    }

    public void ClearTrendData(string itemID)
    {
        lock (_lock)
        {
            _trendData.TryRemove(itemID, out _);
        }
    }

    public void ClearAllTrendData()
    {
        lock (_lock)
        {
            _trendData.Clear();
        }
    }

    public List<string> GetMonitoredTags()
    {
        lock (_lock)
        {
            return _trendData.Keys.ToList();
        }
    }

    private double? TryParseNumeric(string value)
    {
        if (double.TryParse(value, out double result))
            return result;
        
        if (bool.TryParse(value, out bool boolResult))
            return boolResult ? 1.0 : 0.0;

        return null;
    }
}

public class TrendDataPoint
{
    public DateTime Timestamp { get; set; }
    public string Value { get; set; } = "";
    public string Quality { get; set; } = "";
    public double? NumericValue { get; set; }
}

public class TrendStats
{
    public int Count { get; set; }
    public double? Min { get; set; }
    public double? Max { get; set; }
    public double? Average { get; set; }
    public string? FirstValue { get; set; }
    public string? LastValue { get; set; }
}
