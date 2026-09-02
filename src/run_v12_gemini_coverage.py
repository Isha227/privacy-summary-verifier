from __future__ import annotations

import csv
import time

from .common import ROOT, load_config, read_csv
from .v2_coverage_verifier import verify_summary


def main() -> None:
    cfg = load_config()
    root = ROOT / cfg["v2_evaluation"]["root"]
    log_path = root / "logs" / "gemini_v12_coverage_log.csv"
    existing = read_csv(log_path)
    complete = {row["blind_id"] for row in existing if row.get("status") == "success"}
    fields = ["blind_id", "status", "records", "output_path", "attempt", "error", "timestamp_utc"]
    key = sorted(read_csv(ROOT / cfg["paths"]["anonymised"] / "BLINDING_KEY_RESTRICTED.csv"), key=lambda r:r["blind_id"])
    for item in key:
        blind_id = item["blind_id"]
        if blind_id in complete:
            continue
        for attempt in range(1, 4):
            try:
                count, path = verify_summary(blind_id)
                row = {"blind_id": blind_id, "status": "success", "records": count,
                       "output_path": path.relative_to(ROOT).as_posix(), "attempt": attempt, "error": "",
                       "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                print(f"OK Gemini coverage {blind_id}: {count}", flush=True)
            except Exception as exc:
                row = {"blind_id": blind_id, "status": "failed", "records": 0, "output_path": "",
                       "attempt": attempt, "error": f"{type(exc).__name__}: {exc}",
                       "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                print(f"FAILED Gemini coverage {blind_id} attempt {attempt}: {exc}", flush=True)
            exists = log_path.exists()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                if not exists: writer.writeheader()
                writer.writerow(row)
            if row["status"] == "success": break
            time.sleep(20 * attempt)


if __name__ == "__main__":
    main()
