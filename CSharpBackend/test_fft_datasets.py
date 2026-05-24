"""
FFT Multi-Dataset Backtest
==========================
Trains FFT on DIFFERENT training windows and compares out-of-sample accuracy.

Why different datasets matter for FFT:
- FFT phase accuracy depends on how many COMPLETE cycles are in the training window
- If the window captures 3.7 cycles vs 4.0 cycles, the reconstructed frequency
  will be slightly off → phase drift accumulates over the 30-step forecast horizon
- This test shows which window length gives the most accurate FFT extrapolation

Test Matrix:
  Training window lengths: 30 min, 60 min, 90 min, 120 min, 180 min
  Forecast target: fixed 30 steps = 30 minutes ahead
  Cutoff offsets: 35 min ago (so we have ground truth to compare against)
"""
import psycopg2
import numpy as np
from datetime import datetime, timezone, timedelta

DB  = dict(host="localhost", dbname="Automation_DB", user="cereveate", password="cereveate@222")
TAG = "Triangle Waves.Int1"
STEPS       = 30
TOP_K_FFT   = 10
CUTOFF_OFFSET_MIN = 35   # forecast origin = 35 min ago (30 steps have elapsed → ground truth exists)

# Training window sizes to test (minutes of history before cutoff)
TRAIN_WINDOWS_MIN = [20, 30, 60, 90, 120, 180, 240]

# ─────────────────────────────────────────────────────────────────────────────
def fetch_raw(conn, start: datetime, end: datetime) -> list[tuple]:
    """Fetch per-second values in window, return (ts, value) list."""
    cur = conn.cursor()
    cur.execute("""
        SELECT time AT TIME ZONE 'UTC', value_num
        FROM   historian_raw.historian_timeseries
        WHERE  tag_id = %s
          AND  time BETWEEN %s AND %s
          AND  value_num IS NOT NULL
        ORDER  BY time ASC
    """, (TAG, start, end))
    rows = cur.fetchall()
    cur.close()
    return rows


def resample_to_1min(rows: list[tuple]) -> np.ndarray:
    """Average values into 1-minute bins, return array."""
    if not rows:
        return np.array([])
    # Build dict: minute_key → list of values
    bins: dict[datetime, list] = {}
    for ts, val in rows:
        key = ts.replace(second=0, microsecond=0, tzinfo=timezone.utc)
        bins.setdefault(key, []).append(float(val))
    # Sort and average
    sorted_keys = sorted(bins.keys())
    return np.array([float(np.mean(bins[k])) for k in sorted_keys])


def fft_project(signal: np.ndarray, n_out: int, top_k: int = 10):
    """
    Fit FFT to `signal`, extrapolate n_out steps beyond its end.
    Returns (future_values, res_std, dominant_period_samples, phase_reliable).
    """
    n_sig   = len(signal)
    coeffs  = np.fft.rfft(signal)
    mags    = np.abs(coeffs)
    k_use   = min(top_k, len(mags))
    thresh  = np.sort(mags)[-k_use]
    filtered = np.where(mags >= thresh, coeffs, 0)
    freqs   = np.fft.rfftfreq(n_sig)

    # Dominant frequency (skip DC bin 0)
    dom_k       = int(np.argmax(mags[1:]) + 1)
    period_smp  = n_sig / dom_k if dom_k > 0 else n_sig
    frac_part   = abs(period_smp - round(period_smp)) / period_smp
    phase_reliable = frac_part < 0.05

    # Extrapolate
    t_fut = np.arange(n_sig, n_sig + n_out)
    fut   = np.full(n_out, float(np.real(filtered[0]) / n_sig))
    for ki, co in enumerate(filtered):
        if ki == 0 or co == 0:
            continue
        is_nyq = (n_sig % 2 == 0 and ki == len(filtered) - 1)
        amp    = np.abs(co) * (1.0 if is_nyq else 2.0) / n_sig
        fut   += amp * np.cos(2 * np.pi * freqs[ki] * t_fut + np.angle(co))

    reconstructed = np.fft.irfft(filtered, n=n_sig)
    res_std = float(np.std(signal - reconstructed))
    return fut, res_std, round(period_smp, 2), phase_reliable


def score(preds: np.ndarray, actuals: np.ndarray):
    n = min(len(preds), len(actuals))
    if n == 0:
        return None, None
    e = np.abs(preds[:n] - actuals[:n])
    return float(np.mean(e)), float(np.sqrt(np.mean((preds[:n] - actuals[:n])**2)))


# ─────────────────────────────────────────────────────────────────────────────
def main():
    conn = psycopg2.connect(**DB)

    now    = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=CUTOFF_OFFSET_MIN)

    print(f"\n{'='*75}")
    print(f"  FFT MULTI-DATASET BACKTEST  —  {TAG}")
    print(f"  Forecast origin (cutoff): {cutoff.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Forecast window: +1..+{STEPS} min  (ground truth available)")
    print(f"{'='*75}\n")

    # ── Fetch actuals for the 30-step future window ────────────────────────
    actual_rows = fetch_raw(conn, cutoff + timedelta(seconds=1),
                            cutoff + timedelta(minutes=STEPS + 2))
    actual_arr  = resample_to_1min(actual_rows)
    if len(actual_arr) == 0:
        print("❌ No actual data in forecast window — cutoff too recent?")
        conn.close()
        return

    print(f"  Actual ground-truth points available: {len(actual_arr)}/{STEPS}")
    print(f"  Signal amplitude range in future: [{actual_arr.min():.1f}, {actual_arr.max():.1f}]\n")
    n_compare = min(len(actual_arr), STEPS)

    # ── Print header ──────────────────────────────────────────────────────
    print(f"{'Win(min)':>8}  {'N_train':>7}  {'Period(s)':>9}  {'PhaseOK?':>8}  "
          f"{'res_std':>7}  {'MAE':>7}  {'RMSE':>7}  {'%range':>7}  {'Verdict'}")
    print("-" * 90)

    results = []
    for win_min in TRAIN_WINDOWS_MIN:
        train_start = cutoff - timedelta(minutes=win_min)
        train_rows  = fetch_raw(conn, train_start, cutoff)
        train_arr   = resample_to_1min(train_rows)

        if len(train_arr) < 8:
            print(f"{win_min:>8}  {'too short':>7}")
            continue

        try:
            fft_fut, res_std, period_smp, phase_ok = fft_project(
                train_arr, n_compare, top_k=TOP_K_FFT
            )
            mae, rmse = score(fft_fut, actual_arr[:n_compare])
            pct_range = mae / 182 * 100 if mae is not None else None

            phase_str = "✅ YES" if phase_ok else "❌ NO"
            verdict   = ""
            if mae is not None:
                if mae < 10:
                    verdict = "✅ EXCELLENT"
                elif mae < 25:
                    verdict = "⚠️  ACCEPTABLE"
                elif mae < 50:
                    verdict = "❌ POOR"
                else:
                    verdict = "💀 CATASTROPHIC"

            print(f"{win_min:>8}  {len(train_arr):>7}  {period_smp:>9.2f}  "
                  f"{phase_str:>8}  {res_std:>7.2f}  "
                  f"{mae:>7.2f}  {rmse:>7.2f}  {pct_range:>6.1f}%  {verdict}")

            results.append({
                "win_min": win_min,
                "n_train": len(train_arr),
                "period_smp": period_smp,
                "phase_ok": phase_ok,
                "res_std": res_std,
                "mae": mae,
                "rmse": rmse,
            })
        except Exception as e:
            print(f"{win_min:>8}  ERROR: {e}")

    conn.close()

    if not results:
        print("\n❌ No results.")
        return

    # ── Summary ────────────────────────────────────────────────────────────
    best = min(results, key=lambda r: r["mae"] if r["mae"] is not None else 999)
    worst = max(results, key=lambda r: r["mae"] if r["mae"] is not None else 0)

    print(f"\n{'='*75}")
    print(f"  BEST  training window: {best['win_min']} min  → MAE = {best['mae']:.2f}  "
          f"({best['mae']/182*100:.1f}% range)  period={best['period_smp']}s  phase_ok={best['phase_ok']}")
    print(f"  WORST training window: {worst['win_min']} min  → MAE = {worst['mae']:.2f}  "
          f"({worst['mae']/182*100:.1f}% range)")

    phase_ok_results  = [r for r in results if r["phase_ok"]]
    phase_bad_results = [r for r in results if not r["phase_ok"]]
    if phase_ok_results and phase_bad_results:
        avg_ok  = float(np.mean([r["mae"] for r in phase_ok_results]))
        avg_bad = float(np.mean([r["mae"] for r in phase_bad_results]))
        print(f"\n  Phase-aligned windows    avg MAE: {avg_ok:.2f}")
        print(f"  Phase-misaligned windows avg MAE: {avg_bad:.2f}")
        delta = avg_bad - avg_ok
        if delta > 5:
            print(f"  → Phase alignment improves MAE by {delta:.1f} points ✅")
        else:
            print(f"  → Phase alignment has minimal effect on this dataset")

    print(f"\n  CONCLUSION:")
    if best["mae"] < 15:
        print(f"  FFT CAN be accurate on this signal — use {best['win_min']}-min training window")
        print(f"  Recommendation: align window to whole multiples of period ({best['period_smp']:.1f} samples ≈ {best['period_smp']:.0f} min)")
    elif best["mae"] < 35:
        print(f"  FFT is MARGINAL — phase error dominates at >10 step horizon")
        print(f"  Best window: {best['win_min']} min, but ARIMA likely more reliable")
    else:
        print(f"  FFT is UNRELIABLE on this signal regardless of window size")
        print(f"  Use ARIMA or HW instead")
    print(f"{'='*75}\n")


if __name__ == "__main__":
    main()
