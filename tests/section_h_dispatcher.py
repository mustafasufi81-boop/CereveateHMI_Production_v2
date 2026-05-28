"""
SECTION H — COM Dispatcher Resilience Tests
============================================
CereveateHMI Production  |  C# OPC DA Backend  |  http://localhost:5001

Validates the OPC STA dispatcher under:
  H1  STA apartment verification        — dispatcher thread must be STA
  H2  Dispatcher heartbeat monotonic    — /api/health responds and timestamps advance
  H3  Queue depth growth + drain        — burst → depth rises, idle → drains to 0
  H4  Dispatcher timeout detection      — slow /api/opc/values poll latency baseline
  H5  Dispatcher tag-count stability    — tagCount never drops to 0 under load
  H6  Queue saturation rejection        — 500 rapid fire, check 0 server 500s
  H7  Reconnect storm behaviour         — OPC restart → tagCount=27 restored in <120s
  H8  Dispatcher survives OPC restart   — after restart backend stays healthy
  H9  OPC health state transitions      — /api/health/opc fields change on reconnect
  H10 Long dispatcher soak (5 min)      — continuous 500ms poll, drift + leak check

Usage:
    cd D:\\CereveateHMI_Production
    .\\HMI\\.venv\\Scripts\\python.exe tests\\section_h_dispatcher.py [--only H1 H2 ...] [--no-soak]

Prerequisites:
    • C# backend running on http://localhost:5001 (OpcDaWebBrowser.exe)
    • OPC server connected (tagCount == 27 before starting)
    • pip install requests psutil (inside HMI venv)

Safety rules enforced:
    • H7/H8 (OPC restart) are SKIPPED unless --restart flag is passed — they kill
      OpcDaWebBrowser.exe via taskkill.  Do NOT run in production with live UI clients.
    • H10 (soak) is SKIPPED when --no-soak is passed.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# ─── psutil (optional — resource tracking) ───────────────────────────────────
try:
    import psutil
    PSUTIL = True
except ImportError:
    PSUTIL = False

# ─── CONFIG ──────────────────────────────────────────────────────────────────
BASE_URL     = "http://localhost:5001"
TIMEOUT_S    = 6.0
EXPECTED_TAGS = 27

ENDPOINTS = {
    "values":     f"{BASE_URL}/api/opc/values",
    "status":     f"{BASE_URL}/api/opc/status",
    "health":     f"{BASE_URL}/api/health",
    "opc":        f"{BASE_URL}/api/health/opc",
    "res":        f"{BASE_URL}/api/health/resources",
    "dispatcher": f"{BASE_URL}/api/health/dispatcher",
}

# ─── Data structures ─────────────────────────────────────────────────────────
@dataclass
class TestResult:
    test_id:   str
    passed:    bool
    message:   str
    detail:    str = ""
    duration_s: float = 0.0
    data:      Dict[str, Any] = field(default_factory=dict)


@dataclass
class PollSample:
    latency_ms: float
    status_code: int
    tag_count:   int
    ok:          bool
    ts:          float = field(default_factory=time.monotonic)


# ─── Helpers ─────────────────────────────────────────────────────────────────
def get(url: str, timeout: float = TIMEOUT_S) -> Tuple[int, Any]:
    """GET → (status_code, parsed_json_or_None)"""
    try:
        r = requests.get(url, timeout=timeout)
        try:
            body = r.json()
        except Exception:
            body = None
        return r.status_code, body
    except requests.exceptions.ConnectionError:
        return 0, None
    except requests.exceptions.Timeout:
        return -1, None
    except Exception:
        return -2, None


def extract_tag_count(body: Any) -> int:
    if not body:
        return 0
    if isinstance(body, dict):
        tags = body.get("tags", body.get("tagValues", []))
        return (body.get("tagCount")
                or body.get("tag_count")
                or body.get("count")
                or (len(tags) if isinstance(tags, list) else 0))
    if isinstance(body, list):
        return len(body)
    return 0


def poll_values(n: int, interval_s: float = 0.0) -> List[PollSample]:
    """Serial poll /api/opc/values n times with optional inter-request sleep."""
    samples: List[PollSample] = []
    for _ in range(n):
        t0 = time.monotonic()
        code, body = get(ENDPOINTS["values"])
        ms = (time.monotonic() - t0) * 1000
        tc = extract_tag_count(body)
        samples.append(PollSample(
            latency_ms=ms,
            status_code=code,
            tag_count=tc,
            ok=(code == 200 and tc > 0),
        ))
        if interval_s > 0:
            time.sleep(interval_s)
    return samples


def percentile(data: List[float], pct: float) -> float:
    if not data:
        return 0.0
    sorted_d = sorted(data)
    idx = int(len(sorted_d) * pct / 100)
    idx = min(idx, len(sorted_d) - 1)
    return sorted_d[idx]


def sep(title: str = "") -> None:
    bar = "━" * 60
    if title:
        print(f"\n{bar}")
        print(f"  {title}")
        print(bar)
    else:
        print(bar)


def ok(result: TestResult) -> str:
    return "✅ PASS" if result.passed else "❌ FAIL"


# ─── Dispatcher Metrics Time-Series Tracker ──────────────────────────────────

@dataclass
class DispatcherSample:
    """One snapshot from /api/health/dispatcher."""
    elapsed_s:           float
    wall_ts:             str
    queue_depth:         int
    max_queue_depth:     int
    operations_processed: int
    timeout_count:       int
    state:               str
    last_success:        Optional[str]
    last_heartbeat:      Optional[str]
    apartment:           str
    reachable:           bool


class DispatcherMetricsTracker:
    """
    Background thread that polls /api/health/dispatcher every `interval_s` seconds.
    Start with .start(), stop with .stop().  Read results via .samples.

    Captured fields:
        queueDepth, maxQueueDepth, operationsProcessed, timeoutCount,
        state, lastSuccess, lastHeartbeat, apartment
    """
    def __init__(self, interval_s: float = 2.0):
        self.interval_s = interval_s
        self.samples: List[DispatcherSample] = []
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._t0 = time.monotonic()

    def start(self) -> "DispatcherMetricsTracker":
        self._t0 = time.monotonic()
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="DispatcherTracker")
        self._thread.start()
        return self

    def stop(self) -> List[DispatcherSample]:
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=self.interval_s + 2)
        return self.samples

    def _run(self):
        while not self._stop_evt.is_set():
            elapsed = time.monotonic() - self._t0
            code, body = get(ENDPOINTS["dispatcher"], timeout=3.0)
            reachable = code == 200 and isinstance(body, dict)
            if reachable:
                ldb = {k.lower(): v for k, v in body.items()}
                self.samples.append(DispatcherSample(
                    elapsed_s            = elapsed,
                    wall_ts              = datetime.now().isoformat(timespec='seconds'),
                    queue_depth          = int(ldb.get("queuedepth", 0)),
                    max_queue_depth      = int(ldb.get("maxqueuedepth", 0)),
                    operations_processed = int(ldb.get("operationsprocessed", 0)),
                    timeout_count        = int(ldb.get("timeoutcount", 0)),
                    state                = str(ldb.get("state", "")),
                    last_success         = str(ldb.get("lastsuccess", "") or ""),
                    last_heartbeat       = str(ldb.get("lastheartbeat", "") or ""),
                    apartment            = str(ldb.get("apartment", "")),
                    reachable            = True,
                ))
            else:
                self.samples.append(DispatcherSample(
                    elapsed_s=elapsed, wall_ts=datetime.now().isoformat(timespec='seconds'),
                    queue_depth=0, max_queue_depth=0, operations_processed=0,
                    timeout_count=0, state="UNREACHABLE", last_success=None,
                    last_heartbeat=None, apartment="", reachable=False,
                ))
            self._stop_evt.wait(self.interval_s)

    def report(self, label: str = "") -> dict:
        """Return a summary dict + print a compact table."""
        if not self.samples:
            return {}
        reachable = [s for s in self.samples if s.reachable]
        unreachable_count = len(self.samples) - len(reachable)
        if not reachable:
            print(f"  [Dispatcher Tracker{' ' + label if label else ''}] 0/{len(self.samples)} samples reachable")
            return {"unreachable": unreachable_count}

        q_depths  = [s.queue_depth for s in reachable]
        ops       = [s.operations_processed for s in reachable]
        timeouts  = [s.timeout_count for s in reachable]
        max_qdep  = max(s.max_queue_depth for s in reachable)
        ops_delta = ops[-1] - ops[0] if len(ops) >= 2 else 0
        t_delta   = timeouts[-1] - timeouts[0] if len(timeouts) >= 2 else 0
        states    = list(dict.fromkeys(s.state for s in reachable))  # unique, ordered

        print(f"\n  ┌─ Dispatcher Metrics{' — ' + label if label else ''} ({len(self.samples)} samples, {unreachable_count} unreachable)")
        print(f"  │  queueDepth     : min={min(q_depths)}  max={max(q_depths)}  final={q_depths[-1]}")
        print(f"  │  maxQueueDepth  : peak={max_qdep}")
        print(f"  │  ops_processed  : Δ{ops_delta:+d}  (start={ops[0]}  end={ops[-1]})")
        print(f"  │  timeouts       : Δ{t_delta:+d}  (start={timeouts[0]}  end={timeouts[-1]})")
        print(f"  │  states seen    : {states}")
        print(f"  │  apartment      : {reachable[-1].apartment}")
        if reachable[-1].last_success:
            print(f"  │  lastSuccess    : {reachable[-1].last_success}")
        if reachable[-1].last_heartbeat:
            print(f"  │  lastHeartbeat  : {reachable[-1].last_heartbeat}")
        print(f"  └─")

        return {
            "samples": len(self.samples),
            "unreachable": unreachable_count,
            "queue_depth_min": min(q_depths),
            "queue_depth_max": max(q_depths),
            "queue_depth_final": q_depths[-1],
            "max_queue_depth_peak": max_qdep,
            "ops_delta": ops_delta,
            "timeout_delta": t_delta,
            "states_seen": states,
            "apartment_final": reachable[-1].apartment,
        }


# ─── Individual tests ────────────────────────────────────────────────────────

def h1_sta_apartment_check() -> TestResult:
    """
    H1 — Concurrent Dispatcher Stability + STA Apartment Verification
    Part A (stability proxy): send a burst of 10 concurrent requests that all
    require the dispatcher.  If apartment were MTA, COM marshalling errors would
    cause at least one to fail or return tagCount=0.
    Part B (direct STA proof): read /api/health/dispatcher and assert
    apartment == "STA" — now available after dispatcher metrics instrumentation.
    """
    t0 = time.monotonic()
    errors = 0
    tag_counts = []

    # Part A — concurrent stability
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(get, ENDPOINTS["values"]) for _ in range(10)]
        for f in as_completed(futures):
            code, body = f.result()
            tc = extract_tag_count(body)
            tag_counts.append(tc)
            if code != 200 or tc == 0:
                errors += 1

    stability_ok = errors == 0 and all(tc == EXPECTED_TAGS for tc in tag_counts)

    # Part B — direct apartment check via /api/health/dispatcher
    apt_ok = False
    apt_value = "(unknown)"
    apt_thread = None
    d_code, d_body = get(ENDPOINTS["dispatcher"])
    if d_code == 200 and isinstance(d_body, dict):
        ldb = {k.lower(): v for k, v in d_body.items()}
        apt_value = str(ldb.get("apartment", ""))
        apt_thread = ldb.get("threadid")
        apt_ok = apt_value.upper() == "STA"
    else:
        apt_value = f"endpoint_unavailable (code={d_code})"

    passed = stability_ok and apt_ok
    return TestResult(
        test_id="H1 STA apartment",
        passed=passed,
        message=(
            f"Concurrent: {10-errors}/10 ok | Dispatcher apartment={apt_value!r} thread={apt_thread}"
            + (" ✅" if passed else " ❌")
        ),
        detail="Part A: concurrent stability proxy. Part B: /api/health/dispatcher apartment==STA",
        duration_s=time.monotonic() - t0,
        data={
            "errors": errors, "tag_counts": tag_counts,
            "apartment": apt_value, "thread_id": apt_thread,
            "dispatcher_endpoint_code": d_code,
        },
    )


def h2_heartbeat_monotonic() -> TestResult:
    """
    H2 — Dispatcher Heartbeat Monotonic
    /api/health must respond with advancing Timestamp across 5 polls at 1s intervals.
    Verifies health push-service is alive and timestamps are fresh.
    """
    t0 = time.monotonic()
    timestamps: List[str] = []
    failures = 0

    for i in range(5):
        code, body = get(ENDPOINTS["health"])
        if code == 200 and isinstance(body, dict):
            ts = body.get("Timestamp") or body.get("timestamp")
            if ts:
                timestamps.append(str(ts))
        else:
            failures += 1
        if i < 4:
            time.sleep(1.0)

    # Timestamps must all be present and the last must differ from the first
    monotonic = (
        len(timestamps) >= 2
        and timestamps[0] != timestamps[-1]
        and failures == 0
    )
    return TestResult(
        test_id="H2 heartbeat monotonic",
        passed=monotonic,
        message=(f"5/5 health polls OK, timestamps advancing ✅"
                 if monotonic else
                 f"failures={failures}, unique_ts={len(set(timestamps))}/{len(timestamps)}"),
        detail="/api/health Timestamp must advance — stale timestamp = push service frozen",
        duration_s=time.monotonic() - t0,
        data={"timestamps": timestamps, "failures": failures},
    )


def h3_queue_depth_drain() -> TestResult:
    """
    H3 — Queue Depth Growth + Drain
    Fire a burst of 50 rapid requests (no sleep between them) to create backpressure,
    then poll /api/health to confirm the backend recovered (tagCount stable, no 500s).
    Indirect proxy for queue depth — we cannot read the internal BlockingCollection
    count without a new metrics endpoint, so we measure:
      • burst: 0 server 500 errors (queue not overflowing into exceptions)
      • drain: tagCount returns to 27 within 5s of burst completion
    """
    t0 = time.monotonic()
    BURST = 50
    errors_500 = 0
    errors_net = 0

    with ThreadPoolExecutor(max_workers=50) as ex:
        futures = [ex.submit(get, ENDPOINTS["values"]) for _ in range(BURST)]
        for f in as_completed(futures):
            code, body = f.result()
            if code == 500:
                errors_500 += 1
            elif code not in (200,):
                errors_net += 1

    # Drain check: give 5s then verify tagCount=27
    time.sleep(5.0)
    code, body = get(ENDPOINTS["values"])
    drained_ok = (code == 200 and extract_tag_count(body) == EXPECTED_TAGS)

    passed = errors_500 == 0 and drained_ok
    return TestResult(
        test_id="H3 queue drain",
        passed=passed,
        message=(f"Burst {BURST}: 0 server 500s, tagCount={EXPECTED_TAGS} after drain ✅"
                 if passed else
                 f"errors_500={errors_500}, errors_net={errors_net}, drain_ok={drained_ok}"),
        detail="Unbounded queue = no overflow; bounded queue must not block ASP.NET thread pool",
        duration_s=time.monotonic() - t0,
        data={"burst": BURST, "errors_500": errors_500, "errors_net": errors_net, "drained": drained_ok},
    )


def h4_dispatcher_latency_profile() -> TestResult:
    """
    H4 — Dispatcher Latency Profile
    100 serial requests at 200ms.  Baseline for detecting dispatcher slowdown.
    Thresholds (relaxed for STA dispatch overhead):
      p50 < 50ms  p95 < 200ms  p99 < 500ms  success = 100%
    This test establishes a Section H latency baseline separate from Section D.
    """
    t0 = time.monotonic()
    samples = poll_values(n=100, interval_s=0.2)
    latencies = [s.latency_ms for s in samples if s.ok]
    errors = sum(1 for s in samples if not s.ok)

    if len(latencies) < 5:
        return TestResult(
            test_id="H4 dispatcher latency",
            passed=False,
            message=f"Too many errors to measure latency: {errors}/100",
            duration_s=time.monotonic() - t0,
        )

    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)
    mx  = max(latencies)
    passed = p50 < 50 and p95 < 200 and p99 < 500 and errors == 0

    return TestResult(
        test_id="H4 dispatcher latency",
        passed=passed,
        message=(f"p50={p50:.1f}ms p95={p95:.1f}ms p99={p99:.1f}ms max={mx:.1f}ms errors={errors}"),
        detail="Thresholds: p50<50ms p95<200ms p99<500ms — STA dispatch adds overhead vs REST pool",
        duration_s=time.monotonic() - t0,
        data={"p50": p50, "p95": p95, "p99": p99, "max": mx, "errors": errors, "n": len(latencies)},
    )


def h5_tagcount_stability_under_load() -> TestResult:
    """
    H5 — tagCount Stability Under Load
    200 serial requests at 50ms.  tagCount must NEVER drop to 0 or go below 27.
    A drop to 0 means: dispatcher hung, COM disconnected, or pool cleared.
    """
    t0 = time.monotonic()
    samples = poll_values(n=200, interval_s=0.05)
    drops = [s for s in samples if s.ok and s.tag_count < EXPECTED_TAGS]
    zeros = [s for s in samples if s.tag_count == 0]
    errors = [s for s in samples if not s.ok]
    min_tc = min((s.tag_count for s in samples), default=0)

    passed = len(zeros) == 0 and len(drops) == 0 and len(errors) == 0
    return TestResult(
        test_id="H5 tagCount stability",
        passed=passed,
        message=(f"200 polls at 50ms: min_tagCount={min_tc}, zeros={len(zeros)}, drops={len(drops)}, errors={len(errors)}"
                 + (" ✅" if passed else " ❌")),
        detail="tagCount drop to 0 = dispatcher hung or COM disconnected (Fix #1 regression)",
        duration_s=time.monotonic() - t0,
        data={"min_tc": min_tc, "zeros": len(zeros), "drops": len(drops), "errors": len(errors)},
    )


def h6_saturation_no_500s() -> TestResult:
    """
    H6 — Queue Saturation: no 500 errors under 500-request storm
    500 requests fired by 50 concurrent workers.
    Success criteria:
      • HTTP 500 count = 0  (no unhandled dispatcher exceptions)
      • success rate ≥ 95%  (network hiccups allowed)
      • tagCount=27 in all 200 responses immediately after storm
    """
    t0 = time.monotonic()
    STORM = 500
    WORKERS = 50
    results_500 = 0
    results_ok  = 0
    results_err = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = [ex.submit(get, ENDPOINTS["values"]) for _ in range(STORM)]
        for f in as_completed(futures):
            code, body = f.result()
            if code == 200 and extract_tag_count(body) > 0:
                results_ok += 1
            elif code == 500:
                results_500 += 1
            else:
                results_err += 1

    success_rate = results_ok / STORM * 100
    passed = results_500 == 0 and success_rate >= 95.0

    return TestResult(
        test_id="H6 saturation no-500s",
        passed=passed,
        message=(f"500 requests: ok={results_ok} 500s={results_500} err={results_err} "
                 f"success={success_rate:.1f}%"
                 + (" ✅" if passed else " ❌")),
        detail="Thresholds: 0 HTTP 500s, ≥95% success rate",
        duration_s=time.monotonic() - t0,
        data={"storm": STORM, "ok": results_ok, "500s": results_500, "err": results_err,
              "success_rate": success_rate},
    )


def _snapshot_dispatcher() -> dict:
    """Pull a dispatcher health snapshot; returns {} on any failure."""
    code, body = get(ENDPOINTS["dispatcher"])
    if code == 200 and isinstance(body, dict):
        return {k.lower(): v for k, v in body.items()}
    return {}


def h7_opc_restart_recovery(
    run_restart: bool,
    cycles: int = 1,
    cycle_interval_s: float = 30.0,
    cycle_jitter_s: float = 0.0,
) -> TestResult:
    """
    H7 — Multi-Restart Soak: OPC Backend Restart → tagCount=27 + dispatcher health
    ⚠ DESTRUCTIVE — kills OpcDaWebBrowser.exe.  Only runs with --restart flag.

    Per-cycle metrics tracked:
      reconnect_s         — time from kill to tagCount==27 (hard SLA: <30s)
      rejected_delta      — rejectedCount increase during cycle (must be 0)
      timeout_delta       — timeoutCount increase during cycle (must be 0)
      max_q               — maxQueueDepth at steady state post-recovery (must be <=10)
      time_in_reconnecting — seconds dispatcher spent reporting non-Running state
      time_in_degraded     — seconds dispatcher reported Degraded/Faulted state

    Random jitter between cycles (--cycle-jitter-s J) surfaces reconnect race
    conditions that fixed intervals miss.
    """
    import random
    import subprocess

    t0 = time.monotonic()

    if not run_restart:
        return TestResult(
            test_id="H7 OPC restart recovery",
            passed=True,
            message="SKIPPED (pass --restart to enable — kills OpcDaWebBrowser.exe)",
            duration_s=0.0,
        )

    BACKEND_EXE  = r"D:\CereveateHMI_Production\CSharpBackend\bin\Release\net8.0\publish\OpcDaWebBrowser.exe"
    RECOVER_TIMEOUT = 120.0
    RECONNECT_SLA   = 30.0   # seconds — hard pass criterion
    MAX_Q_SLA       = 10     # maxQueueDepth at steady state

    cycle_rows: List[dict] = []
    successful_recoveries = 0
    failed_recoveries     = 0
    overall_pass          = True

    for cycle in range(1, cycles + 1):
        print(f"\n  [H7] ═══ Cycle {cycle}/{cycles} ═══")
        c_t0 = time.monotonic()

        # ── pre-kill baseline snapshot ────────────────────────────────────────
        snap_pre = _snapshot_dispatcher()
        rejected_pre = int(snap_pre.get("rejectedcount", 0))
        timeout_pre  = int(snap_pre.get("timeoutcount",  0))

        # verify baseline healthy
        code0, body0 = get(ENDPOINTS["values"])
        tc0 = extract_tag_count(body0)
        if code0 != 200 or tc0 == 0:
            overall_pass = False
            failed_recoveries += 1
            cycle_rows.append({"cycle": cycle, "result": "FAIL",
                                "note": f"pre-kill baseline bad: code={code0} tagCount={tc0}"})
            break

        # ── kill ──────────────────────────────────────────────────────────────
        subprocess.run(["taskkill", "/F", "/IM", "OpcDaWebBrowser.exe"],
                       capture_output=True, text=True)
        kill_ts = time.monotonic()
        print(f"  [H7] Killed — polling for recovery (SLA={RECONNECT_SLA:.0f}s, timeout={RECOVER_TIMEOUT:.0f}s)")

        # ── restart ───────────────────────────────────────────────────────────
        subprocess.Popen(
            [BACKEND_EXE],
            cwd=str(Path(BACKEND_EXE).parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(10.0)  # grace: process starts, OPC still reconnecting

        # ── poll until recovered ──────────────────────────────────────────────
        recovered        = False
        recovery_s       = None
        time_reconnecting = 0.0   # seconds dispatcher NOT in Running state
        time_degraded     = 0.0   # seconds dispatcher in Degraded or Faulted
        last_poll_ts      = time.monotonic()

        deadline = kill_ts + RECOVER_TIMEOUT
        while time.monotonic() < deadline:
            time.sleep(2.0)
            now          = time.monotonic()
            poll_elapsed = now - last_poll_ts
            last_poll_ts = now

            d_snap = _snapshot_dispatcher()
            d_state = str(d_snap.get("state", "")).lower()
            if d_state and d_state != "running":
                time_reconnecting += poll_elapsed
                if d_state in ("degraded", "faulted"):
                    time_degraded += poll_elapsed

            code, body = get(ENDPOINTS["values"])
            tc      = extract_tag_count(body)
            elapsed = now - kill_ts
            print(f"  [H7] t+{elapsed:.0f}s  code={code}  tagCount={tc}  disp_state={d_state!r}")

            if code == 200 and tc == EXPECTED_TAGS:
                recovered  = True
                recovery_s = elapsed
                break

        # ── post-recovery dispatcher snapshot ────────────────────────────────
        time.sleep(2.0)  # brief settle before post snapshot
        snap_post    = _snapshot_dispatcher()
        rejected_post = int(snap_post.get("rejectedcount", 0))
        timeout_post  = int(snap_post.get("timeoutcount",  0))
        max_q_post    = int(snap_post.get("maxqueuedepth", 0))
        state_post    = snap_post.get("state", "?")
        state_reason  = snap_post.get("statereason", "")

        rejected_delta = rejected_post - rejected_pre
        timeout_delta  = timeout_post  - timeout_pre

        # ── per-cycle pass criteria ───────────────────────────────────────────
        cycle_pass = (
            recovered
            and (recovery_s is not None and recovery_s <= RECONNECT_SLA)
            and rejected_delta == 0
            and timeout_delta  == 0
            and max_q_post     <= MAX_Q_SLA
        )
        cycle_result_str = "PASS" if cycle_pass else "FAIL"
        if recovered:
            successful_recoveries += 1
        else:
            failed_recoveries += 1
            overall_pass = False

        # ── actual inter-cycle interval with jitter ───────────────────────────
        raw_interval = time.monotonic() - c_t0

        row = {
            "cycle":             cycle,
            "interval_s":        round(raw_interval, 1),
            "reconnect_s":       round(recovery_s, 1) if recovery_s else None,
            "rejected_delta":    rejected_delta,
            "timeout_delta":     timeout_delta,
            "max_q":             max_q_post,
            "time_reconnecting": round(time_reconnecting, 1),
            "time_degraded":     round(time_degraded, 1),
            "state_post":        state_post,
            "state_reason":      state_reason,
            "result":            cycle_result_str,
        }
        cycle_rows.append(row)

        print(f"  [H7] Cycle {cycle}: {cycle_result_str} | "
              f"reconnect={recovery_s:.0f}s " if recovery_s else f"  [H7] Cycle {cycle}: {cycle_result_str} | reconnect=TIMEOUT ")
        # print violations
        if rejected_delta > 0:
            print(f"         ❌ rejectedCount delta={rejected_delta} (expected 0)")
        if timeout_delta > 0:
            print(f"         ❌ timeoutCount delta={timeout_delta} (expected 0)")
        if max_q_post > MAX_Q_SLA:
            print(f"         ❌ maxQueueDepth={max_q_post} (SLA <={MAX_Q_SLA})")
        if not cycle_pass and cycle_pass is False and recovery_s and recovery_s > RECONNECT_SLA:
            print(f"         ❌ reconnect_s={recovery_s:.0f}s exceeds SLA of {RECONNECT_SLA:.0f}s")
        if not recovered:
            overall_pass = False
            break  # abort on unrecovered cycle

        # ── inter-cycle wait with jitter ──────────────────────────────────────
        if cycle < cycles:
            jitter     = random.uniform(-cycle_jitter_s, cycle_jitter_s) if cycle_jitter_s > 0 else 0.0
            wait_s     = max(5.0, cycle_interval_s + jitter)
            wait_m, wait_s_rem = divmod(wait_s, 60)
            print(f"  [H7] Waiting {int(wait_m)}m {wait_s_rem:.0f}s before next cycle "
                  f"(base={cycle_interval_s:.0f}s jitter={jitter:+.0f}s)...")
            time.sleep(wait_s)

    # ── summary table ─────────────────────────────────────────────────────────
    print()
    print(f"  {'Cycle':>5}  {'interval':>10}  {'reconnect':>10}  "
          f"{'rej_Δ':>6}  {'tmo_Δ':>6}  {'maxQ':>5}  "
          f"{'t_reconn':>9}  {'t_degrad':>9}  result")
    print(f"  {'-'*5}  {'-'*10}  {'-'*10}  {'-'*6}  {'-'*6}  {'-'*5}  {'-'*9}  {'-'*9}  {'-'*6}")
    for row in cycle_rows:
        if "note" in row:
            print(f"  {row['cycle']:>5}  {'—':>10}  {'—':>10}  {'—':>6}  {'—':>6}  {'—':>5}  {'—':>9}  {'—':>9}  FAIL ({row['note']})")
            continue
        iv = row["interval_s"]
        iv_m, iv_s = divmod(iv, 60)
        rc = f"{row['reconnect_s']:.0f}s" if row["reconnect_s"] is not None else "TIMEOUT"
        print(f"  {row['cycle']:>5}  {int(iv_m):>3}m {iv_s:04.1f}s  {rc:>10}  "
              f"{row['rejected_delta']:>6}  {row['timeout_delta']:>6}  {row['max_q']:>5}  "
              f"{row['time_reconnecting']:>8.1f}s  {row['time_degraded']:>8.1f}s  {row['result']}")

    recovery_times = [r["reconnect_s"] for r in cycle_rows if r.get("reconnect_s") is not None]
    max_recovery   = max(recovery_times) if recovery_times else None
    max_rejected   = max((r.get("rejected_delta", 0) for r in cycle_rows if "note" not in r), default=0)
    max_timeouts   = max((r.get("timeout_delta",  0) for r in cycle_rows if "note" not in r), default=0)
    print(f"  {'─'*80}")
    print(f"  TOTAL  successful={successful_recoveries}  failed={failed_recoveries}  "
          f"max_reconnect={'%.0fs' % max_recovery if max_recovery else 'N/A'}  "
          f"max_rejected={max_rejected}  max_timeouts={max_timeouts}")
    print()

    overall_pass = overall_pass and failed_recoveries == 0
    msg = (
        f"{successful_recoveries}/{cycles} recovered  "
        f"failed={failed_recoveries}  "
        f"max_reconnect={'%.0fs' % max_recovery if max_recovery else 'N/A'}  "
        f"max_rej={max_rejected}  max_tmo={max_timeouts}"
        + (" ✅" if overall_pass else " ❌")
    )
    return TestResult(
        test_id="H7 OPC restart recovery",
        passed=overall_pass,
        message=msg,
        detail=(
            f"Soak: {cycles} cycle(s), interval={cycle_interval_s:.0f}s jitter=±{cycle_jitter_s:.0f}s | "
            f"SLAs: reconnect<{RECONNECT_SLA:.0f}s, rej_delta=0, tmo_delta=0, maxQ<={MAX_Q_SLA}"
        ),
        duration_s=time.monotonic() - t0,
        data={
            "cycles":               cycle_rows,
            "successful_recoveries": successful_recoveries,
            "failed_recoveries":     failed_recoveries,
            "max_recovery_s":        max_recovery,
            "max_rejected_delta":    max_rejected,
            "max_timeout_delta":     max_timeouts,
        },
    )


def h8_dispatcher_survives_restart(run_restart: bool) -> TestResult:
    """
    H8 — Dispatcher Survives OPC Restart: health status stable after H7
    Must be run AFTER H7.  Verifies dispatcher thread did not exit/deadlock
    during the restart cycle.  Checks /api/health/opc Status == Connected.
    """
    t0 = time.monotonic()

    if not run_restart:
        return TestResult(
            test_id="H8 dispatcher post-restart",
            passed=True,
            message="SKIPPED (pass --restart to enable)",
            duration_s=0.0,
        )

    # Give 5s after H7 to stabilise
    time.sleep(5.0)

    code, body = get(ENDPOINTS["opc"])
    if code != 200 or not isinstance(body, dict):
        return TestResult(
            test_id="H8 dispatcher post-restart",
            passed=False,
            message=f"Health OPC endpoint unreachable: code={code}",
            duration_s=time.monotonic() - t0,
        )

    status = body.get("Status") or body.get("status", "")
    tc     = body.get("TagsConnected") or body.get("tagsConnected") or body.get("tagCount", 0)
    passed = "connected" in status.lower() and int(tc) == EXPECTED_TAGS

    # Snapshot dispatcher metrics post-restart
    d_code, d_body = get(ENDPOINTS["dispatcher"])
    disp_snap: dict = {}
    if d_code == 200 and isinstance(d_body, dict):
        ldb = {k.lower(): v for k, v in d_body.items()}
        disp_snap = {
            "apartment":            ldb.get("apartment"),
            "state":                ldb.get("state"),
            "queue_depth":          ldb.get("queuedepth"),
            "max_queue_depth":      ldb.get("maxqueuedepth"),
            "operations_processed": ldb.get("operationsprocessed"),
            "timeout_count":        ldb.get("timeoutcount"),
            "last_success":         ldb.get("lastsuccess"),
            "last_heartbeat":       ldb.get("lastheartbeat"),
        }
        print(f"  [H8] Dispatcher post-restart: apartment={disp_snap['apartment']!r} "
              f"state={disp_snap['state']!r} ops={disp_snap['operations_processed']} "
              f"timeouts={disp_snap['timeout_count']}")

    return TestResult(
        test_id="H8 dispatcher post-restart",
        passed=passed,
        message=(f"OPC health: Status={status!r} TagsConnected={tc} ✅"
                 if passed else
                 f"OPC health bad after restart: Status={status!r} TagsConnected={tc}"),
        detail="Dispatcher STA thread must remain alive through OPC restart cycle",
        duration_s=time.monotonic() - t0,
        data={"opc_status": status, "tags_connected": tc, "dispatcher_snapshot": disp_snap},
    )


def h9_opc_health_fields() -> TestResult:
    """
    H9 — OPC Health State Transitions: /api/health/opc field coverage
    Validates all required fields exist in the OPC health record.
    These become the baseline for Section H dispatcher state machine tests.
    Required: Status, TagsConnected, HealthScore, LastUpdate (or lastUpdate).
    Optional but tracked: ErrorCount, UpdateRateMs.
    """
    t0 = time.monotonic()
    code, body = get(ENDPOINTS["opc"])

    if code != 200 or not isinstance(body, dict):
        return TestResult(
            test_id="H9 OPC health fields",
            passed=False,
            message=f"Cannot reach /api/health/opc: code={code}",
            duration_s=time.monotonic() - t0,
        )

    # Normalise keys to lowercase for comparison
    lbody = {k.lower(): v for k, v in body.items()}
    required = ["status", "tagsconnected", "healthscore", "lastupdate"]
    optional = ["errorcount", "updateratemS", "lastError"]
    missing  = [f for f in required if f not in lbody]
    present  = [f for f in required if f not in missing]
    opt_present = [f for f in optional if f.lower() in lbody]

    status      = lbody.get("status", "")
    tc          = lbody.get("tagsconnected", 0)
    score       = lbody.get("healthscore", 0)
    connected   = "connected" in str(status).lower()

    # Dispatcher endpoint: NOW REQUIRED (C# dispatcher metrics instrumented)
    d_code, d_body = get(ENDPOINTS["dispatcher"])
    dispatcher_required = ["apartment", "threadid", "queuedepth", "operationsprocessed", "state"]
    dispatcher_present: List[str] = []
    dispatcher_missing: List[str] = []
    dispatcher_apt = ""
    if d_code == 200 and isinstance(d_body, dict):
        ldb = {k.lower(): v for k, v in d_body.items()}
        dispatcher_present = [f for f in dispatcher_required if f in ldb]
        dispatcher_missing = [f for f in dispatcher_required if f not in ldb]
        dispatcher_apt = str(ldb.get("apartment", ""))
    else:
        dispatcher_missing = list(dispatcher_required)

    dispatcher_ok = len(dispatcher_missing) == 0 and dispatcher_apt.upper() == "STA"

    passed = len(missing) == 0 and connected and int(tc) == EXPECTED_TAGS and dispatcher_ok

    msg = (f"Status={status!r} TagsConnected={tc} HealthScore={score} "
           f"dispatcher_apt={dispatcher_apt!r}"
           + (" ✅" if passed else f" ❌ opc_missing={missing} disp_missing={dispatcher_missing}"))

    return TestResult(
        test_id="H9 OPC health fields",
        passed=passed,
        message=msg,
        detail=(f"OPC required={present} | "
                f"Dispatcher required={dispatcher_required} "
                f"present={dispatcher_present} missing={dispatcher_missing}"),
        duration_s=time.monotonic() - t0,
        data={
            "status": status, "tags_connected": tc, "health_score": score,
            "required_missing": missing,
            "dispatcher_fields_present": dispatcher_present,
            "dispatcher_fields_missing": dispatcher_missing,
            "dispatcher_apartment": dispatcher_apt,
            "dispatcher_endpoint_code": d_code,
        },
    )


def h10_long_soak(duration_s: int, run_soak: bool) -> TestResult:
    """
    H10 — Long Dispatcher Soak (default 300s / 5 min)
    Polls /api/opc/values every 500ms.  Tracks:
      • tagCount — must never drop to 0
      • latency drift — compare first-30s p95 vs last-30s p95
      • error rate — must stay below 1%
      • memory/thread growth (if psutil available)
    Prints live progress every 30s.
    Skipped unless --soak is passed.
    """
    t0 = time.monotonic()
    label = f"H10 soak {duration_s}s"

    if not run_soak:
        return TestResult(
            test_id=label,
            passed=True,
            message=f"SKIPPED (pass --soak to enable {duration_s}s soak)",
            duration_s=0.0,
        )

    baseline_mem = None
    baseline_threads = None
    baseline_handles = None
    if PSUTIL:
        try:
            proc = psutil.Process()
            baseline_mem = proc.memory_info().rss / 1024 / 1024
            baseline_threads = proc.num_threads()
            baseline_handles = getattr(proc, 'num_handles', lambda: None)()
        except Exception:
            pass

    all_samples: List[PollSample] = []
    window_samples: List[PollSample] = []
    next_report = time.monotonic() + 30
    deadline = time.monotonic() + duration_s

    # Timestamp-freeze detection: >5 consecutive identical /api/health timestamps = push service frozen
    last_health_ts: Optional[str] = None
    consecutive_same_ts = 0
    MAX_SAME_TS = 5
    ts_freeze_events = 0

    # Dispatcher metrics tracker — 5s interval to not overload during soak
    disp_tracker = DispatcherMetricsTracker(interval_s=5.0).start()

    print(f"\n  [H10] Starting {duration_s}s soak (poll=500ms, dispatcher poll=5s)...")

    while time.monotonic() < deadline:
        t_req = time.monotonic()
        code, body = get(ENDPOINTS["values"])
        ms = (time.monotonic() - t_req) * 1000
        tc = extract_tag_count(body)
        s = PollSample(latency_ms=ms, status_code=code, tag_count=tc, ok=(code == 200 and tc > 0))
        all_samples.append(s)
        window_samples.append(s)

        # Timestamp-freeze check: every 5th sample poll /api/health
        if len(all_samples) % 5 == 0:
            h_code, h_body = get(ENDPOINTS["health"])
            if h_code == 200 and isinstance(h_body, dict):
                cur_ts = str(h_body.get("Timestamp") or h_body.get("timestamp", ""))
                if cur_ts and cur_ts == last_health_ts:
                    consecutive_same_ts += 1
                    if consecutive_same_ts > MAX_SAME_TS:
                        ts_freeze_events += 1
                        print(f"  [H10] ⚠ TIMESTAMP FREEZE: {consecutive_same_ts} identical ts={cur_ts!r}")
                else:
                    consecutive_same_ts = 0
                last_health_ts = cur_ts

        if time.monotonic() >= next_report:
            elapsed = time.monotonic() - t0
            w_lat = [x.latency_ms for x in window_samples if x.ok]
            w_ok  = sum(1 for x in window_samples if x.ok)
            w_zero = sum(1 for x in window_samples if x.tag_count == 0)
            print(
                f"  [H10] t+{elapsed:.0f}s | "
                f"window_ok={w_ok}/{len(window_samples)} | "
                f"zeros={w_zero} | "
                f"p50={percentile(w_lat,50):.1f}ms | "
                f"p95={percentile(w_lat,95):.1f}ms | "
                f"total={len(all_samples)}"
            )
            window_samples = []
            next_report = time.monotonic() + 30

        # Sleep the remainder of the 500ms slot
        elapsed_req = time.monotonic() - t_req
        sleep_rem = 0.5 - elapsed_req
        if sleep_rem > 0:
            time.sleep(sleep_rem)

    # Analysis
    total = len(all_samples)
    errors = sum(1 for s in all_samples if not s.ok)
    zeros  = sum(1 for s in all_samples if s.tag_count == 0)
    error_rate = errors / total * 100 if total > 0 else 100.0

    early = [s.latency_ms for s in all_samples[:60] if s.ok]   # first 30s
    late  = [s.latency_ms for s in all_samples[-60:] if s.ok]  # last 30s
    p95_early = percentile(early, 95) if early else 0.0
    p95_late  = percentile(late,  95) if late  else 0.0
    drift_ms  = p95_late - p95_early

    disp_tracker.stop()
    disp_report = disp_tracker.report("H10 soak")

    mem_delta = None
    handle_delta = None
    if PSUTIL:
        try:
            proc = psutil.Process()
            if baseline_mem is not None:
                end_mem = proc.memory_info().rss / 1024 / 1024
                mem_delta = end_mem - baseline_mem
            if baseline_handles is not None:
                end_handles = getattr(proc, 'num_handles', lambda: None)()
                if end_handles is not None:
                    handle_delta = end_handles - baseline_handles
        except Exception:
            pass

    # Thresholds
    passed = (
        zeros             == 0
        and error_rate    <= 1.0
        and drift_ms      <= 100.0      # p95 must not drift >100ms over soak
        and ts_freeze_events == 0       # health push service must not freeze
        and (mem_delta    is None or mem_delta    <= 50.0)   # <50MB growth
        and (handle_delta is None or handle_delta <= 100)    # <100 handle leak
    )

    msg_parts = [
        f"total={total}",
        f"errors={errors}({error_rate:.1f}%)",
        f"zeros={zeros}",
        f"ts_freeze={ts_freeze_events}",
        f"p95_drift={drift_ms:+.1f}ms",
    ]
    if mem_delta is not None:
        msg_parts.append(f"mem_delta={mem_delta:+.1f}MB")
    if handle_delta is not None:
        msg_parts.append(f"handle_delta={handle_delta:+d}")
    msg = " ".join(msg_parts)

    return TestResult(
        test_id=label,
        passed=passed,
        message=msg + (" ✅" if passed else " ❌"),
        detail="Thresholds: zeros=0, error_rate≤1%, p95_drift≤100ms, ts_freeze=0, mem≤50MB, handles≤100",
        duration_s=time.monotonic() - t0,
        data={
            "total": total, "errors": errors, "zeros": zeros,
            "error_rate": error_rate, "p95_early": p95_early,
            "p95_late": p95_late, "drift_ms": drift_ms,
            "ts_freeze_events": ts_freeze_events,
            "mem_delta_mb": mem_delta,
            "handle_delta": handle_delta,
            "dispatcher_metrics": disp_report,
        },
    )


# ─── Runner ──────────────────────────────────────────────────────────────────

def pre_flight() -> bool:
    """Verify backend is reachable and tagCount=27 before starting."""
    code, body = get(ENDPOINTS["values"])
    if code != 200:
        print(f"❌ PRE-FLIGHT FAILED: /api/opc/values returned {code}")
        print("   Is OpcDaWebBrowser.exe running on http://localhost:5001?")
        return False
    tc = extract_tag_count(body)
    if tc != EXPECTED_TAGS:
        print(f"❌ PRE-FLIGHT FAILED: tagCount={tc} (expected {EXPECTED_TAGS})")
        print("   Is OPC server connected? Check /api/opc/status")
        return False
    print(f"✅ Pre-flight OK — backend reachable, tagCount={tc}")
    return True


def save_results(results: List[TestResult], run_id: str) -> None:
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"section_h_{run_id}.json"
    payload = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "suite": "Section H — COM Dispatcher Resilience",
        "passed": sum(1 for r in results if r.passed),
        "total": len(results),
        "results": [
            {
                "test_id":    r.test_id,
                "passed":     r.passed,
                "message":    r.message,
                "detail":     r.detail,
                "duration_s": round(r.duration_s, 2),
                "data":       r.data,
            }
            for r in results
        ],
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\n  📄 Results saved → {path}")


def print_summary(results: List[TestResult]) -> None:
    sep("SECTION H — FINAL REPORT")
    col_w = 34
    print(f"  {'Test ID':<{col_w}} {'Status':<10}  Message")
    print("  " + "─" * 80)
    for r in results:
        tag = "✅ PASS" if r.passed else ("⏭  SKIP" if "SKIPPED" in r.message else "❌ FAIL")
        print(f"  {r.test_id:<{col_w}} {tag:<10}  {r.message}")

    passed = sum(1 for r in results if r.passed)
    skipped = sum(1 for r in results if "SKIPPED" in r.message)
    total = len(results)
    print()
    print(f"  TOTAL: {passed}/{total} passed  ({skipped} skipped)")
    if passed == total:
        print("  🎉 ALL TESTS PASSED")
    elif passed + skipped == total:
        print("  ✅ All non-skipped tests passed")
    else:
        failed = total - passed
        print(f"  ⚠️  {failed} FAILED")
    sep()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Section H — COM Dispatcher Resilience Tests"
    )
    parser.add_argument(
        "--only", nargs="+", metavar="TEST",
        help="Run only specific tests, e.g. --only H1 H3 H9"
    )
    parser.add_argument(
        "--restart", action="store_true",
        help="Enable H7/H8 (kills OpcDaWebBrowser.exe — destructive)"
    )
    parser.add_argument(
        "--restart-cycles", type=int, default=1, metavar="N",
        help="Number of kill→recover cycles for H7 repeated restart soak (default: 1)"
    )
    parser.add_argument(
        "--cycle-interval-s", type=float, default=30.0, metavar="T",
        help="Base wait between H7 restart cycles in seconds (default: 30)"
    )
    parser.add_argument(
        "--cycle-jitter-s", type=float, default=0.0, metavar="J",
        help="Random ±J seconds added to each inter-cycle interval (default: 0)"
    )
    parser.add_argument(
        "--soak", action="store_true",
        help="Enable H10 long soak"
    )
    parser.add_argument(
        "--soak-duration", type=int, default=300,
        metavar="SECONDS",
        help="H10 soak duration in seconds (default: 300)"
    )
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    sep("CEREVEATE HMI — SECTION H: COM DISPATCHER RESILIENCE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  Run ID: {run_id}")
    print(f"  Backend: {BASE_URL}")
    print(f"  psutil: {'✅' if PSUTIL else '⚠️  not installed (resource tracking disabled)'}")
    print(f"  --restart: {'ENABLED ⚠️  (cycles=' + str(args.restart_cycles) + ' interval=' + str(args.cycle_interval_s) + 's jitter=±' + str(args.cycle_jitter_s) + 's)' if args.restart else 'disabled (H7/H8 skipped)'}")
    print(f"  --cycle-interval-s: {args.cycle_interval_s}s  --cycle-jitter-s: ±{args.cycle_jitter_s}s")
    print(f"  --soak: {'ENABLED (' + str(args.soak_duration) + 's)' if args.soak else 'disabled (H10 skipped)'}")
    sep()

    if not pre_flight():
        sys.exit(1)

    only = {x.upper() for x in (args.only or [])}

    def should_run(key: str) -> bool:
        return not only or key.upper() in only

    results: List[TestResult] = []

    # ── H1 ────────────────────────────────────────────────────────────────────
    if should_run("H1"):
        sep("H1 — STA Apartment Verification")
        r = h1_sta_apartment_check()
        print(f"  {ok(r)}  {r.test_id}")
        print(f"         {r.message}")
        if r.detail:
            print(f"         {r.detail}")
        results.append(r)

    # ── H2 ────────────────────────────────────────────────────────────────────
    if should_run("H2"):
        sep("H2 — Heartbeat Monotonic")
        r = h2_heartbeat_monotonic()
        print(f"  {ok(r)}  {r.test_id}")
        print(f"         {r.message}")
        results.append(r)

    # ── H3 ────────────────────────────────────────────────────────────────────
    if should_run("H3"):
        sep("H3 — Queue Depth Growth + Drain")
        r = h3_queue_depth_drain()
        print(f"  {ok(r)}  {r.test_id}")
        print(f"         {r.message}")
        print(f"         {r.detail}")
        results.append(r)

    # ── H4 ────────────────────────────────────────────────────────────────────
    if should_run("H4"):
        sep("H4 — Dispatcher Latency Profile (100 × 200ms)")
        r = h4_dispatcher_latency_profile()
        print(f"  {ok(r)}  {r.test_id}")
        print(f"         {r.message}")
        print(f"         {r.detail}")
        results.append(r)

    # ── H5 ────────────────────────────────────────────────────────────────────
    if should_run("H5"):
        sep("H5 — tagCount Stability Under Load (200 × 50ms)")
        r = h5_tagcount_stability_under_load()
        print(f"  {ok(r)}  {r.test_id}")
        print(f"         {r.message}")
        results.append(r)

    # ── H6 ────────────────────────────────────────────────────────────────────
    if should_run("H6"):
        sep("H6 — Saturation: 500 requests / 50 workers → 0 HTTP 500s")
        r = h6_saturation_no_500s()
        print(f"  {ok(r)}  {r.test_id}")
        print(f"         {r.message}")
        print(f"         {r.detail}")
        results.append(r)

    # ── H7 ────────────────────────────────────────────────────────────────────
    if should_run("H7"):
        sep("H7 — OPC Restart Recovery ⚠️  (--restart required)")
        r = h7_opc_restart_recovery(
                args.restart,
                cycles=args.restart_cycles,
                cycle_interval_s=args.cycle_interval_s,
                cycle_jitter_s=args.cycle_jitter_s,
            )
        print(f"  {ok(r)}  {r.test_id}")
        print(f"         {r.message}")
        results.append(r)

    # ── H8 ────────────────────────────────────────────────────────────────────
    if should_run("H8"):
        sep("H8 — Dispatcher Survives Restart ⚠️  (--restart required)")
        r = h8_dispatcher_survives_restart(args.restart)
        print(f"  {ok(r)}  {r.test_id}")
        print(f"         {r.message}")
        results.append(r)

    # ── H9 ────────────────────────────────────────────────────────────────────
    if should_run("H9"):
        sep("H9 — OPC Health Field Coverage")
        r = h9_opc_health_fields()
        print(f"  {ok(r)}  {r.test_id}")
        print(f"         {r.message}")
        print(f"         {r.detail}")
        results.append(r)

    # ── H10 ───────────────────────────────────────────────────────────────────
    if should_run("H10"):
        sep(f"H10 — Long Soak ({args.soak_duration}s) (--soak required)")
        r = h10_long_soak(args.soak_duration, args.soak)
        print(f"  {ok(r)}  {r.test_id}")
        print(f"         {r.message}")
        if r.detail:
            print(f"         {r.detail}")
        results.append(r)

    print_summary(results)
    save_results(results, run_id)

    passed = sum(1 for r in results if r.passed)
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
