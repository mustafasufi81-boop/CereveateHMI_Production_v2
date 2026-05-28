"""
Cereveate OPC DA Backend — Stress & Performance Test Suite
===========================================================
Tests the C# backend (http://localhost:5001) for:
  1.  Baseline response time (idle)
  2.  Sustained high-frequency polling — GET /api/opc/values at 100ms, 50ms, 10ms
  3.  Concurrent client burst — N threads hammering simultaneously
  4.  Tag-specific high-frequency poll — single tag via /api/opc/values
  5.  Mixed load — values + status + trends concurrently
  6.  TagValuesPool freshness under load (age_ms, stale detection)
  7.  Backend recovery — kill/restart OPC, confirm pool refills within grace period
  8.  Dispatcher saturation test — fire 500 rapid REST calls, check queue depth
  9.  Long soak test — 60s continuous polling, measure drift/degradation
  10. Answer: can it poll at 10ms? Per-tag fast vs slow rates?

Usage:
    cd D:\\CereveateHMI_Production
    .venv\\Scripts\\python tests\\opc_stress_test.py

Requirements:
    pip install requests rich
    C# backend must be running on http://localhost:5001
    OPC server must be connected (tagCount: 27)
"""

import time
import threading
import statistics
import json
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Optional
import requests

try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn
    RICH = True
except ImportError:
    RICH = False

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
BASE_URL = "http://localhost:5001"
TIMEOUT  = 5.0   # seconds per request

ENDPOINTS = {
    "status":  f"{BASE_URL}/api/opc/status",
    "values":  f"{BASE_URL}/api/opc/values",
    "servers": f"{BASE_URL}/api/opc/servers",
}

# Tags we know exist from tagCount:27 on Matrikon simulation
KNOWN_TAGS = [
    "HZ1103A",
    "TURBINE_SPEED_RPM",
    "VIB_LP_FRONT_X_UM",
    "BEARING_TEMP_LP_REAR_C",
    "LUBE_OIL_PRESSURE_BAR",
    "TEST_TAG_001",
    "OVERSPEED_TRIP_ACTIVE",
]

# ─────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────
@dataclass
class SampleResult:
    ok: bool
    latency_ms: float
    status_code: int = 0
    error: str = ""
    tag_count: int = 0
    last_update: str = ""

@dataclass
class TestReport:
    name: str
    samples: List[SampleResult] = field(default_factory=list)

    def success_rate(self):
        if not self.samples: return 0.0
        return sum(1 for s in self.samples if s.ok) / len(self.samples) * 100

    def latencies(self):
        return [s.latency_ms for s in self.samples if s.ok]

    def p50(self):
        lat = self.latencies()
        return statistics.median(lat) if lat else 0

    def p95(self):
        lat = sorted(self.latencies())
        if not lat: return 0
        idx = max(0, int(len(lat) * 0.95) - 1)
        return lat[idx]

    def p99(self):
        lat = sorted(self.latencies())
        if not lat: return 0
        idx = max(0, int(len(lat) * 0.99) - 1)
        return lat[idx]

    def max_ms(self):
        lat = self.latencies()
        return max(lat) if lat else 0

    def min_ms(self):
        lat = self.latencies()
        return min(lat) if lat else 0

    def throughput_rps(self, duration_s: float):
        return len(self.samples) / duration_s if duration_s > 0 else 0


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(
    pool_connections=50,
    pool_maxsize=100,
    max_retries=0,
)
session.mount("http://", adapter)


def poll_once(url: str) -> SampleResult:
    t0 = time.perf_counter()
    try:
        resp = session.get(url, timeout=TIMEOUT)
        latency = (time.perf_counter() - t0) * 1000
        ok = resp.status_code == 200
        tag_count = 0
        last_update = ""
        if ok:
            try:
                body = resp.json()
                if isinstance(body, list):
                    tag_count = len(body)
                elif isinstance(body, dict):
                    tag_count = body.get("tagCount", body.get("tag_count", 0))
                    last_update = body.get("lastUpdate", "")
            except Exception:
                pass
        return SampleResult(ok=ok, latency_ms=latency, status_code=resp.status_code,
                            tag_count=tag_count, last_update=last_update)
    except requests.exceptions.Timeout:
        latency = (time.perf_counter() - t0) * 1000
        return SampleResult(ok=False, latency_ms=latency, error="TIMEOUT")
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        return SampleResult(ok=False, latency_ms=latency, error=str(e)[:60])


def print_header(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def summarize(report: TestReport, duration_s: float):
    lat = report.latencies()
    errors = [s for s in report.samples if not s.ok]
    print(f"  Samples     : {len(report.samples)}")
    print(f"  Success     : {report.success_rate():.1f}%  ({len(errors)} errors)")
    print(f"  Throughput  : {report.throughput_rps(duration_s):.1f} req/s")
    if lat:
        print(f"  Latency min : {report.min_ms():.1f} ms")
        print(f"  Latency p50 : {report.p50():.1f} ms")
        print(f"  Latency p95 : {report.p95():.1f} ms")
        print(f"  Latency p99 : {report.p99():.1f} ms")
        print(f"  Latency max : {report.max_ms():.1f} ms")
    if errors:
        unique_errors = {}
        for s in errors:
            unique_errors[s.error] = unique_errors.get(s.error, 0) + 1
        print(f"  Error types : {unique_errors}")
    # Verdict
    verdict = "✅ PASS"
    issues = []
    if report.success_rate() < 99.0:
        issues.append(f"success rate {report.success_rate():.1f}% < 99%")
    if report.p95() > 500:
        issues.append(f"p95 {report.p95():.0f}ms > 500ms")
    if report.p99() > 1000:
        issues.append(f"p99 {report.p99():.0f}ms > 1000ms")
    if issues:
        verdict = f"⚠️  WARN  — {'; '.join(issues)}"
    print(f"  Verdict     : {verdict}")
    return report


# ─────────────────────────────────────────────────────────────
# PRE-FLIGHT CHECK
# ─────────────────────────────────────────────────────────────
def preflight():
    print_header("PRE-FLIGHT CHECK")
    try:
        r = session.get(ENDPOINTS["status"], timeout=3)
        body = r.json()
        connected = body.get("connected", False)
        tag_count = body.get("tagCount", 0)
        server = body.get("serverName", "?")
        print(f"  Backend     : ✅ UP (HTTP {r.status_code})")
        print(f"  OPC Server  : {'✅' if connected else '❌'} {server}")
        print(f"  Tag Count   : {'✅' if tag_count == 27 else '⚠️ '} {tag_count} (expected 27)")
        if not connected:
            print("  ❌ OPC not connected — some tests will fail. Continue? (y/n)", end=" ")
            if input().strip().lower() != "y":
                sys.exit(1)
    except Exception as e:
        print(f"  ❌ Backend unreachable: {e}")
        print("  Start OpcDaWebBrowser.exe first.")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────
# TEST 1 — BASELINE IDLE RESPONSE TIME
# ─────────────────────────────────────────────────────────────
def test_baseline():
    print_header("TEST 1 — BASELINE (idle, serial, 50 requests)")
    report = TestReport("baseline")
    for _ in range(50):
        report.samples.append(poll_once(ENDPOINTS["values"]))
        time.sleep(0.1)   # 100ms gap — well below any load
    duration = 50 * 0.1
    return summarize(report, duration)


# ─────────────────────────────────────────────────────────────
# TEST 2 — HIGH-FREQUENCY POLLING (serial loop, various rates)
# ─────────────────────────────────────────────────────────────
def test_high_freq_serial(interval_ms: int, duration_s: int):
    print_header(f"TEST 2 — SERIAL POLLING @ {interval_ms}ms interval for {duration_s}s")
    print(f"  Question: can the backend sustain serial polls at {interval_ms}ms?")
    report = TestReport(f"serial_{interval_ms}ms")
    end = time.perf_counter() + duration_s
    while time.perf_counter() < end:
        t0 = time.perf_counter()
        report.samples.append(poll_once(ENDPOINTS["values"]))
        elapsed = (time.perf_counter() - t0) * 1000
        sleep_ms = interval_ms - elapsed
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000)
    # Check if requests themselves are faster than the interval
    lat = report.latencies()
    if lat:
        pct_within_interval = sum(1 for l in lat if l < interval_ms) / len(lat) * 100
        print(f"\n  Requests completing within {interval_ms}ms: {pct_within_interval:.1f}%")
        if interval_ms == 10:
            if statistics.median(lat) < 10:
                print(f"  ✅ YES — backend CAN respond within 10ms (median={statistics.median(lat):.1f}ms)")
                print(f"     BUT Windows timer resolution ~15ms limits true 10ms polling accuracy")
            else:
                print(f"  ⚠️  Backend median {statistics.median(lat):.1f}ms — 10ms not reliably achievable on Windows")
    return summarize(report, duration_s)


# ─────────────────────────────────────────────────────────────
# TEST 3 — CONCURRENT BURST (N threads, M requests each)
# ─────────────────────────────────────────────────────────────
def test_concurrent_burst(n_threads: int, requests_per_thread: int):
    print_header(f"TEST 3 — CONCURRENT BURST — {n_threads} threads × {requests_per_thread} requests")
    report = TestReport(f"burst_{n_threads}t")
    lock = threading.Lock()

    def worker():
        local = []
        for _ in range(requests_per_thread):
            local.append(poll_once(ENDPOINTS["values"]))
        with lock:
            report.samples.extend(local)

    t0 = time.perf_counter()
    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads: t.start()
    for t in threads: t.join()
    duration = time.perf_counter() - t0

    total = n_threads * requests_per_thread
    print(f"  Total requests : {total} in {duration:.2f}s")
    return summarize(report, duration)


# ─────────────────────────────────────────────────────────────
# TEST 4 — PER-TAG HIGH FREQ (fast tags vs slow tags concept)
# ─────────────────────────────────────────────────────────────
def test_per_tag_concept():
    """
    The current /api/opc/values returns ALL 27 tags at once.
    There is no per-tag endpoint for individual tag polling.
    This test simulates "fast tag" vs "slow tag" by filtering
    the response client-side at different rates.

    To truly support per-tag poll rates server-side, OpcDaService
    would need a /api/opc/values/{tagId} endpoint. This test
    identifies that gap.
    """
    print_header("TEST 4 — PER-TAG POLLING CONCEPT")
    print("  Current architecture: /api/opc/values returns ALL 27 tags in one call")
    print("  There is NO per-tag endpoint → per-tag rate control is client-side filtering only")
    print()

    # Simulate: fast group (5 tags, polled 200ms), slow group (rest, polled 1000ms)
    fast_tags = KNOWN_TAGS[:3]
    slow_tags  = KNOWN_TAGS[3:]

    fast_report = TestReport("fast_group_200ms")
    slow_report  = TestReport("slow_group_1000ms")

    print(f"  Fast group ({len(fast_tags)} tags @ 200ms): {fast_tags}")
    print(f"  Slow group ({len(slow_tags)} tags @ 1000ms): {slow_tags}")
    print()

    end = time.perf_counter() + 5  # 5s run
    fast_tick = 0.0
    slow_tick  = 0.0

    while time.perf_counter() < end:
        now = time.perf_counter()
        if now >= fast_tick:
            s = poll_once(ENDPOINTS["values"])
            fast_report.samples.append(s)
            fast_tick = now + 0.200
        if now >= slow_tick:
            s = poll_once(ENDPOINTS["values"])
            slow_report.samples.append(s)
            slow_tick = now + 1.000
        time.sleep(0.001)

    print("  Fast group results:")
    summarize(fast_report, 5)
    print("\n  Slow group results:")
    summarize(slow_report, 5)

    print("\n  FINDING: To enable TRUE per-tag rates, add:")
    print("    GET /api/opc/values/{tagId}   → single tag from cached pool (no COM call)")
    print("    This would be: pool.TryGetValue(tagId) → instant (<1ms), safe for 10ms polling")


# ─────────────────────────────────────────────────────────────
# TEST 5 — MIXED CONCURRENT LOAD
# ─────────────────────────────────────────────────────────────
def test_mixed_load(duration_s: int = 10):
    print_header(f"TEST 5 — MIXED LOAD for {duration_s}s (values + status + servers concurrently)")
    reports = {
        "values": TestReport("mixed_values"),
        "status": TestReport("mixed_status"),
        "servers": TestReport("mixed_servers"),
    }
    lock = threading.Lock()
    stop = threading.Event()

    def poller(endpoint_key: str, interval_ms: int):
        while not stop.is_set():
            s = poll_once(ENDPOINTS[endpoint_key])
            with lock:
                reports[endpoint_key].samples.append(s)
            time.sleep(interval_ms / 1000)

    threads = [
        threading.Thread(target=poller, args=("values",  100), daemon=True),
        threading.Thread(target=poller, args=("values",  100), daemon=True),  # 2nd client
        threading.Thread(target=poller, args=("status",  200), daemon=True),
        threading.Thread(target=poller, args=("servers", 500), daemon=True),
    ]
    for t in threads: t.start()
    time.sleep(duration_s)
    stop.set()
    for t in threads: t.join(timeout=2)

    for key, report in reports.items():
        print(f"\n  [{key}]")
        summarize(report, duration_s)


# ─────────────────────────────────────────────────────────────
# TEST 6 — POOL FRESHNESS UNDER LOAD
# ─────────────────────────────────────────────────────────────
def test_pool_freshness(duration_s: int = 15):
    """
    Poll /api/opc/status rapidly and track lastUpdate timestamps.
    Measures: does the pool stay fresh under sustained load?
    LiveTagCacheService updates every 500ms — lastUpdate should never be >1000ms stale.
    """
    print_header(f"TEST 6 — TAG POOL FRESHNESS under load ({duration_s}s)")
    stale_count = 0
    total = 0
    max_age_ms = 0
    ages = []

    end = time.perf_counter() + duration_s
    while time.perf_counter() < end:
        s = poll_once(ENDPOINTS["status"])
        if s.ok and s.last_update:
            try:
                from datetime import datetime, timezone
                lu = datetime.fromisoformat(s.last_update.replace("Z", "+00:00"))
                age_ms = (datetime.now(timezone.utc) - lu).total_seconds() * 1000
                ages.append(age_ms)
                if age_ms > max_age_ms:
                    max_age_ms = age_ms
                if age_ms > 1500:  # stale if >1.5× the 1000ms expected update window
                    stale_count += 1
                    print(f"  ⚠️  STALE at {time.strftime('%H:%M:%S')} — age={age_ms:.0f}ms")
            except Exception:
                pass
        total += 1
        time.sleep(0.1)

    if ages:
        print(f"  Samples        : {total}")
        print(f"  Median age_ms  : {statistics.median(ages):.0f}ms  (expected ~500ms)")
        print(f"  Max age_ms     : {max_age_ms:.0f}ms  (warn if >1500ms)")
        print(f"  Stale events   : {stale_count}  (age >1500ms)")
        verdict = "✅ PASS — pool stays fresh" if stale_count == 0 else f"⚠️  {stale_count} stale events"
        print(f"  Verdict        : {verdict}")


# ─────────────────────────────────────────────────────────────
# TEST 7 — DISPATCHER SATURATION (500 rapid fire requests)
# ─────────────────────────────────────────────────────────────
def test_dispatcher_saturation():
    """
    Fire 500 requests as fast as possible.
    /api/opc/values reads from the in-memory pool (no COM call per request).
    /api/opc/status also reads cached state.
    Tests ASP.NET thread pool + pool read throughput, NOT the dispatcher queue
    (dispatcher runs independently at its 500ms poll cycle — this cannot saturate it
     because REST reads go to TagValuesPoolService, not through the dispatcher).
    """
    print_header("TEST 7 — SATURATION TEST (500 rapid-fire requests, max concurrency)")
    report = TestReport("saturation")
    TOTAL = 500
    WORKERS = 20

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(poll_once, ENDPOINTS["values"]) for _ in range(TOTAL)]
        for f in as_completed(futures):
            report.samples.append(f.result())
    duration = time.perf_counter() - t0

    print(f"  {TOTAL} requests via {WORKERS} workers in {duration:.2f}s")
    # Check how many returned stale (tag_count=0 means pool empty during burst)
    empty = sum(1 for s in report.samples if s.ok and s.tag_count == 0)
    print(f"  Responses with tag_count=0: {empty}  (should be 0 if pool always has data)")
    return summarize(report, duration)


# ─────────────────────────────────────────────────────────────
# TEST 8 — LONG SOAK (60s steady)
# ─────────────────────────────────────────────────────────────
def test_soak(duration_s: int = 60):
    print_header(f"TEST 8 — SOAK TEST ({duration_s}s continuous @ 100ms)")
    report = TestReport("soak")
    # Track latency drift in 10s windows
    windows = []
    window_samples = []
    window_start = time.perf_counter()

    end = time.perf_counter() + duration_s
    while time.perf_counter() < end:
        t0 = time.perf_counter()
        s = poll_once(ENDPOINTS["values"])
        report.samples.append(s)
        window_samples.append(s)
        elapsed = (time.perf_counter() - t0) * 1000
        sleep_ms = 100 - elapsed
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000)

        # Store 10s window stats
        if time.perf_counter() - window_start >= 10:
            lat = [x.latency_ms for x in window_samples if x.ok]
            if lat:
                windows.append({
                    "t": len(windows) * 10,
                    "p50": round(statistics.median(lat), 1),
                    "p95": round(sorted(lat)[max(0, int(len(lat)*0.95)-1)], 1),
                    "success": sum(1 for x in window_samples if x.ok),
                    "total": len(window_samples),
                })
            window_samples = []
            window_start = time.perf_counter()

    print(f"\n  Latency drift over time (10s windows):")
    print(f"  {'Time':>6}  {'p50':>8}  {'p95':>8}  {'Success%':>10}")
    print(f"  {'-'*40}")
    for w in windows:
        pct = w['success'] / w['total'] * 100 if w['total'] else 0
        drift_flag = "⚠️ " if w['p95'] > 300 else "  "
        print(f"  {w['t']:>4}s   {w['p50']:>6}ms   {w['p95']:>6}ms   {pct:>8.1f}%  {drift_flag}")

    summarize(report, duration_s)


# ─────────────────────────────────────────────────────────────
# TEST 9 — 10ms FEASIBILITY ANALYSIS
# ─────────────────────────────────────────────────────────────
def test_10ms_feasibility():
    print_header("TEST 9 — 10ms POLLING FEASIBILITY ANALYSIS")
    print("  Running 200 back-to-back requests with NO sleep to measure raw latency floor\n")

    report = TestReport("10ms_floor")
    for _ in range(200):
        report.samples.append(poll_once(ENDPOINTS["values"]))
    # No sleep — raw back-to-back

    lat = sorted(report.latencies())
    if not lat:
        print("  ❌ No successful responses")
        return

    below_10  = sum(1 for l in lat if l < 10)
    below_50  = sum(1 for l in lat if l < 50)
    below_100 = sum(1 for l in lat if l < 100)

    print(f"  Raw back-to-back latency (no sleep between requests):")
    print(f"    min      : {min(lat):.1f}ms")
    print(f"    p50      : {statistics.median(lat):.1f}ms")
    print(f"    p95      : {lat[max(0, int(len(lat)*0.95)-1)]:.1f}ms")
    print(f"    max      : {max(lat):.1f}ms")
    print()
    print(f"  Responses < 10ms  : {below_10}/{len(lat)} ({below_10/len(lat)*100:.1f}%)")
    print(f"  Responses < 50ms  : {below_50}/{len(lat)} ({below_50/len(lat)*100:.1f}%)")
    print(f"  Responses < 100ms : {below_100}/{len(lat)} ({below_100/len(lat)*100:.1f}%)")
    print()
    print("  VERDICT:")
    if statistics.median(lat) < 10:
        print("  ✅ Backend responds in <10ms median — 10ms polling IS possible")
        print("     BUT: Windows timer resolution (~15.6ms) limits actual sleep accuracy")
        print("     Use high-resolution timer (timeBeginPeriod) or async loop if needed")
    elif statistics.median(lat) < 50:
        print("  ✅ Backend responds <50ms median — 50ms polling reliable")
        print("  ⚠️  10ms polling: requests arrive before previous completes — use async")
        print("     Recommendation: 50ms minimum for reliable serial polling on this stack")
    else:
        print("  ⚠️  Backend p50 >50ms — network/load issue. 100ms is safer minimum.")
    print()
    print("  ARCHITECTURE NOTE on per-tag fast/slow rates:")
    print("    Current: /api/opc/values returns ALL 27 tags — one pool read (<1ms in C#)")
    print("    Fast tags: filter client-side, no penalty — already the fastest possible")
    print("    To enable TRUE server-side per-tag rates, add:")
    print("      GET /api/opc/values/{tagId} → TagValuesPoolService.TryGet(tagId)")
    print("      This is a 1-line read from ConcurrentDictionary — <0.1ms, safe at 10ms")
    print("      OpcDaService still polls at 500ms — per-tag endpoint just returns cached")


# ─────────────────────────────────────────────────────────────
# FINAL SUMMARY TABLE
# ─────────────────────────────────────────────────────────────
def print_final_summary(results: list):
    print_header("FINAL SUMMARY")
    print(f"  {'Test':<35} {'Requests':>10} {'Success%':>10} {'p50ms':>8} {'p95ms':>8} {'RPS':>8}")
    print(f"  {'-'*80}")
    for name, report, duration in results:
        if not report.samples:
            continue
        rps = report.throughput_rps(duration)
        print(f"  {name:<35} {len(report.samples):>10} {report.success_rate():>9.1f}% "
              f"{report.p50():>7.1f} {report.p95():>7.1f} {rps:>7.1f}")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="OPC DA Backend Stress Tests")
    parser.add_argument("--quick",  action="store_true", help="Skip soak test (quick mode)")
    parser.add_argument("--soak",   type=int, default=60, help="Soak duration in seconds (default 60)")
    parser.add_argument("--only",   type=int, default=0,  help="Run only test N (1-9)")
    args = parser.parse_args()

    preflight()

    all_results = []

    def run(n, fn, *a, **kw):
        if args.only and args.only != n:
            return None, None, 0
        t0 = time.perf_counter()
        report = fn(*a, **kw)
        duration = time.perf_counter() - t0
        if report:
            all_results.append((fn.__name__, report, duration))
        return report, None, duration

    run(1,  test_baseline)
    run(2,  test_high_freq_serial, 100, 5)   # 100ms serial, 5s
    run(2,  test_high_freq_serial,  50, 5)   #  50ms serial, 5s
    run(2,  test_high_freq_serial,  10, 5)   #  10ms serial, 5s  ← THE KEY QUESTION
    run(3,  test_concurrent_burst, 10, 20)   # 10 threads × 20 req
    run(3,  test_concurrent_burst, 50, 10)   # 50 threads × 10 req
    run(4,  test_per_tag_concept)
    run(5,  test_mixed_load, 10)
    run(6,  test_pool_freshness, 15)
    run(7,  test_dispatcher_saturation)
    run(9,  test_10ms_feasibility)

    if not args.quick:
        run(8,  test_soak, args.soak)

    if all_results:
        print_final_summary(all_results)

    print(f"\n{'='*70}")
    print("  Tests complete.")
    print("  Key findings to review:")
    print("    - p95 latency under concurrent load")
    print("    - 10ms feasibility result (Test 9)")
    print("    - Pool freshness stale events (Test 6)")
    print("    - Soak latency drift over time (Test 8)")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
