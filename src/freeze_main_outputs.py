from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .common import ROOT, load_config, read_csv


EXPECTED_OUTPUTS = 270


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze() -> tuple[int, Path]:
    cfg = load_config()
    log_path = ROOT / cfg["paths"]["logs"]
    blind_dir = ROOT / cfg["paths"]["anonymised"]
    key_path = blind_dir / "BLINDING_KEY_RESTRICTED.csv"

    successful = [row for row in read_csv(log_path) if row.get("status") == "success"]
    latest: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in successful:
        key = (
            row["policy_id"],
            row["model_family"],
            row["prompt_strategy"],
            row.get("replicate", "1"),
        )
        if key not in latest or row.get("timestamp_utc", "") > latest[key].get("timestamp_utc", ""):
            latest[key] = row

    blind_rows = read_csv(key_path)
    if len(latest) != EXPECTED_OUTPUTS:
        raise RuntimeError(f"Expected {EXPECTED_OUTPUTS} unique successful outputs, found {len(latest)}")
    if len(blind_rows) != EXPECTED_OUTPUTS:
        raise RuntimeError(f"Expected {EXPECTED_OUTPUTS} blinded outputs, found {len(blind_rows)}")

    blind_by_run = {row["run_id"]: row for row in blind_rows}
    manifest: list[dict[str, str]] = []
    for condition, row in sorted(latest.items()):
        blind = blind_by_run.get(row["run_id"])
        if blind is None:
            raise RuntimeError(f"No blind mapping for run {row['run_id']}")
        original = ROOT / row["text_path"]
        anonymised = blind_dir / f"{blind['blind_id']}.txt"
        if not original.is_file() or not anonymised.is_file():
            raise FileNotFoundError(f"Missing output pair for {row['run_id']}")
        original_hash = sha256(original)
        anonymised_hash = sha256(anonymised)
        if original_hash != anonymised_hash:
            raise RuntimeError(f"Anonymised copy differs from original for {row['run_id']}")
        manifest.append({
            "blind_id": blind["blind_id"],
            "run_id": row["run_id"],
            "policy_id": condition[0],
            "model_family": condition[1],
            "prompt_strategy": condition[2],
            "replicate": condition[3],
            "original_path": str(original.relative_to(ROOT)),
            "anonymised_path": str(anonymised.relative_to(ROOT)),
            "sha256": original_hash,
            "bytes": str(original.stat().st_size),
        })

    manifest.sort(key=lambda row: row["blind_id"])
    manifest_path = blind_dir / "OUTPUT_MANIFEST_RESTRICTED.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=manifest[0].keys())
        writer.writeheader()
        writer.writerows(manifest)

    study_files = [
        ROOT / "config/main_experiment.yaml",
        ROOT / "prompts/zero_v1.0.txt",
        ROOT / "prompts/role_v1.0.txt",
        ROOT / "prompts/structured_v1.0.txt",
        log_path,
        key_path,
        manifest_path,
    ]
    freeze_record = {
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected_outputs": EXPECTED_OUTPUTS,
        "verified_outputs": len(manifest),
        "all_anonymised_copies_match_originals": True,
        "files": {
            str(path.relative_to(ROOT)): sha256(path)
            for path in study_files
        },
    }
    record_path = blind_dir / "FREEZE_RECORD.json"
    record_path.write_text(json.dumps(freeze_record, indent=2) + "\n", encoding="utf-8")
    return len(manifest), record_path


if __name__ == "__main__":
    count, path = freeze()
    print(f"Frozen and verified {count} outputs: {path}")
