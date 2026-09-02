"""Freeze and verify all 486 OPP-115 generation outputs before evaluation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config/opp115_extension_v1.0.yaml"
FREEZE_DIR = ROOT / "data/opp115/experiment/frozen"
MANIFEST_PATH = FREEZE_DIR / "OUTPUT_MANIFEST.csv"
RECORD_PATH = FREEZE_DIR / "GENERATION_FREEZE_RECORD.json"
EXPECTED = 486


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def latest_successful(log_path: Path) -> dict[tuple[str, str, str, str], dict[str, str]]:
    rows = read_csv(log_path)
    if len(rows) != EXPECTED:
        raise RuntimeError(f"Expected exactly {EXPECTED} log rows before freezing; found {len(rows)}")
    latest: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["policy_id"], row["model_family"], row["prompt_strategy"], row.get("replicate", "1"))
        if key not in latest or row["timestamp_utc"] > latest[key]["timestamp_utc"]:
            latest[key] = row
    if len(latest) != EXPECTED:
        raise RuntimeError(f"Expected {EXPECTED} unique conditions; found {len(latest)}")
    failed = [row for row in latest.values() if row["status"] != "success"]
    if failed:
        raise RuntimeError(f"Cannot freeze with {len(failed)} unsuccessful conditions")
    return latest


def freeze() -> tuple[int, Path]:
    if RECORD_PATH.exists() or MANIFEST_PATH.exists():
        raise RuntimeError("A generation freeze already exists. Use --verify-only; do not silently refreeze outputs.")
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    log_path = ROOT / config["paths"]["logs"]
    latest = latest_successful(log_path)
    output_root = ROOT / config["paths"]["outputs"]
    if len(list(output_root.rglob("*.txt"))) != EXPECTED or len(list(output_root.rglob("*.json"))) != EXPECTED:
        raise RuntimeError("Output directory must contain exactly 486 text files and 486 JSON files")

    manifest: list[dict[str, str]] = []
    for condition, row in sorted(latest.items()):
        text_path = ROOT / row["text_path"]
        json_path = ROOT / row["json_path"]
        if not text_path.is_file() or not json_path.is_file():
            raise FileNotFoundError(f"Missing output for {condition}")
        text = text_path.read_text(encoding="utf-8").strip()
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if not text or text != str(payload.get("text", "")).strip():
            raise RuntimeError(f"Text/JSON mismatch for {condition}")
        manifest.append(
            {
                "policy_id": condition[0],
                "model_family": condition[1],
                "prompt_strategy": condition[2],
                "replicate": condition[3],
                "run_id": row["run_id"],
                "model_id": row["model_id"],
                "provider": row["provider"],
                "source_sha256": row["source_sha256"],
                "prompt_sha256": row["prompt_sha256"],
                "response_id": row["response_id"],
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "text_path": str(text_path.relative_to(ROOT)),
                "text_sha256": sha256(text_path),
                "text_bytes": str(text_path.stat().st_size),
                "json_path": str(json_path.relative_to(ROOT)),
                "json_sha256": sha256(json_path),
                "json_bytes": str(json_path.stat().st_size),
            }
        )

    FREEZE_DIR.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)

    study_files = [
        CONFIG_PATH,
        ROOT / "data/opp115/frozen/OPP115_FROZEN_SAMPLE_MANIFEST.json",
        log_path,
        ROOT / "data/opp115/experiment/audits/generation_completion_audit.json",
        ROOT / "data/opp115/experiment/audits/format_deviations.csv",
        MANIFEST_PATH,
    ]
    record = {
        "study": "OPP-115 historical extension",
        "freeze_status": "generation_outputs_frozen_before_evaluation",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected_conditions": EXPECTED,
        "verified_conditions": len(manifest),
        "text_files": EXPECTED,
        "json_files": EXPECTED,
        "failed_conditions": 0,
        "token_ceiling_cases": sum(int(row["output_tokens"]) >= 6000 for row in manifest),
        "study_file_hashes": {str(path.relative_to(ROOT)): sha256(path) for path in study_files},
    }
    RECORD_PATH.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return len(manifest), RECORD_PATH


def verify() -> tuple[int, Path]:
    record = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
    manifest = read_csv(MANIFEST_PATH)
    if len(manifest) != EXPECTED or record["verified_conditions"] != EXPECTED:
        raise RuntimeError("Frozen manifest does not contain 486 conditions")
    for row in manifest:
        text_path = ROOT / row["text_path"]
        json_path = ROOT / row["json_path"]
        if sha256(text_path) != row["text_sha256"] or sha256(json_path) != row["json_sha256"]:
            raise RuntimeError(f"Frozen output changed: {row['policy_id']} / {row['model_family']} / {row['prompt_strategy']}")
    for relative, expected_hash in record["study_file_hashes"].items():
        if sha256(ROOT / relative) != expected_hash:
            raise RuntimeError(f"Frozen study file changed: {relative}")
    return len(manifest), RECORD_PATH


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    count, path = verify() if args.verify_only else freeze()
    action = "Verified" if args.verify_only else "Frozen and verified"
    print(f"{action} {count} OPP generation outputs: {path}")


if __name__ == "__main__":
    main()
