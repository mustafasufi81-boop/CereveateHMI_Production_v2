import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover
    pq = None


def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_data_dir(config: dict, default_dir: Path) -> Path:
    paths = config.get("LoggingPaths") or {}
    raw = paths.get("DataLogDirectory") or paths.get("BaseDirectory")
    if raw:
        candidate = Path(raw)
        return candidate if candidate.is_absolute() else (config_path.parent / candidate).resolve()
    return default_dir


def list_parquet_files(data_dir: Path):
    return sorted(data_dir.glob("*.parquet"), key=lambda p: p.stat().st_mtime, reverse=True)


def is_bad_or_null(value: str, quality: str) -> bool:
    v = (value or "").strip().lower()
    q = (quality or "").strip().lower()
    if v == "" or v == "null" or "error" in v:
        return True
    return q == "bad"


def scan_files(files, max_files: int, stale_minutes: int):
    summary = {
        "files_scanned": 0,
        "rows_total": 0,
        "distinct_tags": set(),
        "tags": {},  # tag -> {rows, bad_null, last_seen}
        "stale_cutoff": (datetime.utcnow() - timedelta(minutes=stale_minutes)),
    }

    if pq is None:
        raise RuntimeError("pyarrow is required: pip install pyarrow")

    for file_path in files[:max_files]:
        pf = pq.ParquetFile(file_path)
        for rg_index in range(pf.num_row_groups):
            table = pf.read_row_group(rg_index, columns=["TagId", "Timestamp", "Value", "Quality"])
            tags = table.column("TagId").to_pylist()
            timestamps = table.column("Timestamp").to_pylist()
            values = table.column("Value").to_pylist()
            qualities = table.column("Quality").to_pylist()

            summary["rows_total"] += len(tags)
            for tag, ts, val, qual in zip(tags, timestamps, values, qualities):
                tag = tag or ""
                if tag not in summary["tags"]:
                    summary["tags"][tag] = {"rows": 0, "bad_null": 0, "last_seen": None}
                tinfo = summary["tags"][tag]
                tinfo["rows"] += 1
                if is_bad_or_null(val, qual):
                    tinfo["bad_null"] += 1
                # Parquet timestamp may already be datetime; if not, try parse
                if ts is not None:
                    if not isinstance(ts, datetime):
                        try:
                            ts = datetime.fromisoformat(str(ts))
                        except Exception:
                            ts = None
                    if ts:
                        if tinfo["last_seen"] is None or ts > tinfo["last_seen"]:
                            tinfo["last_seen"] = ts
                summary["distinct_tags"].add(tag)
        summary["files_scanned"] += 1

    return summary


def build_report(config: dict, summary: dict, stale_minutes: int):
    selected_tags = [t.strip() for t in (config.get("SelectedTags") or []) if t and t.strip()]
    selected_set = set(selected_tags)
    observed_set = summary["distinct_tags"]
    stale_cutoff = summary["stale_cutoff"]

    report_tags = {}
    stale_tags = []
    bad_ratio_tags = []

    for tag, info in summary["tags"].items():
        rows = info["rows"]
        bad = info["bad_null"]
        last_seen = info["last_seen"].isoformat() if info["last_seen"] else None
        ratio = (bad / rows) if rows else 0
        report_tags[tag] = {
            "rows": rows,
            "bad_null": bad,
            "bad_null_ratio": round(ratio, 4),
            "last_seen": last_seen,
        }
        if info["last_seen"] is None or info["last_seen"] < stale_cutoff:
            stale_tags.append(tag)
        if ratio > 0.1:  # 10% or more bad/null
            bad_ratio_tags.append(tag)

    missing_tags = sorted(selected_set - observed_set)

    return {
        "selected_count": len(selected_tags),
        "selected_tags": selected_tags,
        "files_scanned": summary["files_scanned"],
        "rows_total": summary["rows_total"],
        "distinct_tags": len(observed_set),
        "missing_tags": missing_tags,
        "stale_tags": stale_tags,
        "bad_ratio_tags": bad_ratio_tags,
        "tags": report_tags,
        "generated_utc": datetime.utcnow().isoformat(),
        "stale_cutoff_utc": stale_cutoff.isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="Monitor Parquet logging vs selected tags (no app changes)")
    parser.add_argument("--config", default="logging-config.json", help="Path to logging-config.json")
    parser.add_argument("--data-dir", default=None, help="Override data directory (defaults to config LoggingPaths.DataLogDirectory)")
    parser.add_argument("--max-files", type=int, default=3, help="How many latest parquet files to scan")
    parser.add_argument("--stale-minutes", type=int, default=10, help="Consider tag stale if unseen for this many minutes")
    parser.add_argument("--output", default="Logs/monitor_report.json", help="Where to write the report JSON")
    args = parser.parse_args()

    global config_path
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        sys.stderr.write(f"Config not found: {config_path}\n")
        sys.exit(1)

    try:
        config = load_config(config_path)
    except Exception as exc:  # pragma: no cover
        sys.stderr.write(f"Failed to load config: {exc}\n")
        sys.exit(1)

    default_dir = Path("Logs").resolve()
    data_dir = Path(args.data_dir).resolve() if args.data_dir else resolve_data_dir(config, default_dir)
    if not data_dir.exists():
        sys.stderr.write(f"Data directory not found: {data_dir}\n")
        sys.exit(1)

    parquet_files = list_parquet_files(data_dir)
    if not parquet_files:
        sys.stderr.write(f"No parquet files found in {data_dir}\n")
        sys.exit(1)

    summary = scan_files(parquet_files, args.max_files, args.stale_minutes)
    report = build_report(config, summary, args.stale_minutes)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
