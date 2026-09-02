from __future__ import annotations

import argparse
import csv
import time

from .common import ROOT, load_config, read_csv
from .v2_source_units import identify
from .v2_statement_verifier import verify_one


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-summaries", type=int)
    parser.add_argument("--skip-source-units", action="store_true")
    args = parser.parse_args()
    cfg = load_config()
    root = ROOT / cfg["v2_evaluation"]["root"]
    log_path = root / "logs" / "gemini_v12_run_log.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_csv(log_path)
    complete = {r["item_id"] for r in existing if r.get("status") == "success"}
    fields = ["task", "item_id", "status", "records", "output_path", "attempt", "error", "timestamp_utc"]

    def log(row: dict) -> None:
        exists = log_path.exists()
        with log_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            if not exists:
                writer.writeheader()
            writer.writerow(row)

    if not args.skip_source_units:
        for policy_id in ("PILOT01", "PILOT02", "PILOT03"):
            item = f"source_units:{policy_id}"
            if item in complete:
                continue
            for attempt in range(1, 4):
                try:
                    count, path = identify(policy_id)
                    log({"task": "source_units", "item_id": item, "status": "success", "records": count,
                         "output_path": path.relative_to(ROOT).as_posix(), "attempt": attempt, "error": "",
                         "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                    print(f"OK Gemini source units {policy_id}: {count}", flush=True)
                    break
                except Exception as exc:
                    log({"task": "source_units", "item_id": item, "status": "failed", "records": 0,
                         "output_path": "", "attempt": attempt, "error": f"{type(exc).__name__}: {exc}",
                         "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                    print(f"FAILED Gemini source units {policy_id} attempt {attempt}: {exc}", flush=True)
                    time.sleep(20 * attempt)

    key = sorted(read_csv(ROOT / cfg["paths"]["anonymised"] / "BLINDING_KEY_RESTRICTED.csv"), key=lambda r: r["blind_id"])
    pending = [r["blind_id"] for r in key if f"statements:{r['blind_id']}" not in complete]
    if args.max_summaries is not None:
        pending = pending[:args.max_summaries]
    for blind_id in pending:
        item = f"statements:{blind_id}"
        for attempt in range(1, 4):
            try:
                count, path = verify_one(blind_id)
                log({"task": "statements", "item_id": item, "status": "success", "records": count,
                     "output_path": path.relative_to(ROOT).as_posix(), "attempt": attempt, "error": "",
                     "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                print(f"OK Gemini statements {blind_id}: {count}", flush=True)
                break
            except Exception as exc:
                log({"task": "statements", "item_id": item, "status": "failed", "records": 0,
                     "output_path": "", "attempt": attempt, "error": f"{type(exc).__name__}: {exc}",
                     "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                print(f"FAILED Gemini statements {blind_id} attempt {attempt}: {exc}", flush=True)
                time.sleep(20 * attempt)


if __name__ == "__main__":
    main()
