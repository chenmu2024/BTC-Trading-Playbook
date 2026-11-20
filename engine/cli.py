"""Command: python -m engine.cli [--snapshot-file saved.json] [--output-dir output]."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml
from .market import analyze, fetch_snapshot, markdown_report


def main() -> int:
    parser = argparse.ArgumentParser(description="BTC public data analysis; NO trading")
    parser.add_argument("--config", default="config/strategy.yaml")
    parser.add_argument("--snapshot-file", help="Offline snapshot JSON; no network call")
    parser.add_argument("--output-dir", default="output", help="Generated files; not automatically committed")
    args = parser.parse_args()
    with open(args.config, encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if (config.get("status") != "research_only"
            or config["analysis"]["symbol"] != "BTCUSDT"
            or config["analysis"]["preferred_market"] != "USD-M_PERPETUAL"
            or config["risk"]["auto_trading_enabled"]):
        raise ValueError("Unsafe/unrecognized config. This program supports research BTCUSDT USD-M only.")
    if args.snapshot_file:
        with open(args.snapshot_file, encoding="utf-8") as handle:
            snap = json.load(handle)
    else:
        snap = fetch_snapshot(symbol=config["analysis"]["symbol"])
    if snap.get("symbol") != "BTCUSDT" or snap.get("market") != "USD-M_PERPETUAL":
        raise ValueError("Snapshot market mismatch; refusing cross-market analysis")
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    report = analyze(snap, config, repo_commit=commit)
    directory = Path(args.output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = directory / f"BTCUSDT_{stamp}.json"
    md_path = directory / f"BTCUSDT_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown_report(report), encoding="utf-8")
    snapshot_path = directory / f"BTCUSDT_{stamp}.snapshot.json"
    snapshot_path.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(markdown_report(report))
    print(f"Saved: {json_path}, {md_path} and {snapshot_path}")
    return 0 if report["decision"] != "DATA_INSUFFICIENT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
