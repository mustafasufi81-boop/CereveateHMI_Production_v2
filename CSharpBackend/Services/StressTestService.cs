using System.Collections.Generic;
using System.Diagnostics;
using System.Threading.Channels;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// Generates synthetic tag batches and pushes them into the data logging pipeline for stress validation.
/// </summary>
public class StressTestService
{
    private readonly ChannelWriter<List<LogRecord>> _writer;
    private readonly ILogger<StressTestService> _logger;
    private long _rowCounter;

    public StressTestService(ChannelWriter<List<LogRecord>> writer, ILogger<StressTestService> logger)
    {
        _writer = writer;
        _logger = logger;
    }

    public async Task RunAsync(
        int tagCount = 10000,
        int durationSeconds = 120,
        int intervalMs = 1000,
        CancellationToken token = default)
    {
        _logger.LogWarning("=== STRESS TEST STARTED ===");
        _logger.LogWarning("Tags: {TagCount}, Interval: {Interval}ms, Duration: {Duration}s", tagCount, intervalMs, durationSeconds);

        long totalBatches = 0;
        long totalRecords = 0;
        long maxLatency = 0;

        var swTotal = Stopwatch.StartNew();

        while (swTotal.Elapsed.TotalSeconds < durationSeconds && !token.IsCancellationRequested)
        {
            var sw = Stopwatch.StartNew();
            var batch = GenerateBatch(tagCount);

            totalRecords += batch.Count;
            totalBatches++;

            bool written = false;
            while (!written && !token.IsCancellationRequested)
            {
                if (await _writer.WaitToWriteAsync(token))
                {
                    written = _writer.TryWrite(batch);
                }
            }

            sw.Stop();
            maxLatency = Math.Max(maxLatency, sw.ElapsedMilliseconds);

            if (sw.ElapsedMilliseconds > intervalMs)
            {
                _logger.LogError("Pipeline lag detected: {Elapsed}ms > {Interval}ms", sw.ElapsedMilliseconds, intervalMs);
            }

            var remaining = intervalMs - (int)sw.ElapsedMilliseconds;
            if (remaining > 0)
            {
                await Task.Delay(remaining, token);
            }
        }

        swTotal.Stop();

        _logger.LogWarning("=== STRESS TEST COMPLETED ===");
        _logger.LogWarning("Total Batches: {Batches}", totalBatches);
        _logger.LogWarning("Total Records: {Records}", totalRecords);
        _logger.LogWarning("Max Write Latency: {Latency}ms", maxLatency);
        _logger.LogWarning("====================================");
    }

    private List<LogRecord> GenerateBatch(int count)
    {
        var now = DateTime.UtcNow;
        var list = new List<LogRecord>(count);

        for (int i = 0; i < count; i++)
        {
            list.Add(new LogRecord
            {
                RowId = Interlocked.Increment(ref _rowCounter),
                TagId = $"Stress.Tag.{i:D5}",
                Timestamp = now,
                Value = "123.456",
                Quality = "GOOD"
            });
        }

        return list;
    }
}
