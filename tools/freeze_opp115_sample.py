"""Freeze the supervisor-approved 27-policy OPP-115 extension sample."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


PROMPTS = [
    "prompts/v2/basic_direct_v1.2.txt",
    "prompts/v2/basic_role_guided_v1.2.txt",
    "prompts/v2/basic_structured_v1.2.txt",
    "prompts/v2/safety_focused_direct_v1.2.txt",
    "prompts/v2/safety_focused_role_guided_v1.2.txt",
    "prompts/v2/safety_focused_structured_v1.2.txt",
]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_text_file(path: Path) -> str:
    return sha256_bytes(path.read_text(encoding="utf-8-sig").encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--approval-date", default="2026-08-27")
    args = parser.parse_args()

    root = args.project_root.resolve()
    qa_path = root / "data/opp115/qa_approved/opp115_proposed_27_boundary_qa.json"
    qa_rows = json.loads(qa_path.read_text(encoding="utf-8"))
    if len(qa_rows) != 27:
        raise ValueError(f"Expected 27 QA-approved policies; found {len(qa_rows)}")
    if any(row["boundary_qa_decision"] != "Pass" for row in qa_rows):
        raise ValueError("Every policy must pass boundary QA before freezing")
    bands = {name: sum(row["final_length_band"] == name for row in qa_rows) for name in ("Short", "Medium", "Long")}
    if bands != {"Short": 9, "Medium": 9, "Long": 9}:
        raise ValueError(f"Expected 9/9/9 final length balance; found {bands}")

    frozen_root = root / "data/opp115/frozen"
    clean_dir = frozen_root / "clean"
    metadata_dir = frozen_root / "metadata"
    clean_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    metadata_rows: list[dict[str, object]] = []
    policy_manifest: list[dict[str, object]] = []
    for row in qa_rows:
        source = root / "data/opp115/qa_approved/cleaned_policies" / row["final_cleaned_text_file"]
        actual_hash = sha256_text_file(source)
        if actual_hash != row["final_sha256"]:
            raise ValueError(f"Hash mismatch before freeze: {row['sample_id']}")
        destination = clean_dir / f"{row['sample_id']}.txt"
        shutil.copyfile(source, destination)
        if sha256_text_file(destination) != actual_hash:
            raise ValueError(f"Hash mismatch after copy: {row['sample_id']}")

        metadata_rows.append(
            {
                "policy_id": row["sample_id"],
                "opp_policy_uid": row["opp_policy_uid"],
                "organisation": row["organisation"],
                "sector": row["sector"],
                "domain": row["domain"],
                "collection_date": row["collection_date"],
                "last_updated_date": row["last_updated_date"],
                "final_word_count": row["final_policy_words"],
                "length_band": row["final_length_band"],
                "source_path": f"data/opp115/frozen/clean/{row['sample_id']}.txt",
                "source_sha256": actual_hash,
                "opp_annotation_rows": row["consolidated_annotation_rows"],
                "include": "yes",
                "freeze_status": "frozen",
            }
        )
        policy_manifest.append(
            {
                "policy_id": row["sample_id"],
                "opp_policy_uid": int(row["opp_policy_uid"]),
                "organisation": row["organisation"],
                "sector": row["sector"],
                "final_word_count": int(row["final_policy_words"]),
                "length_band": row["final_length_band"],
                "source_sha256": actual_hash,
            }
        )

    metadata_path = metadata_dir / "policies.csv"
    with metadata_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metadata_rows[0]))
        writer.writeheader()
        writer.writerows(metadata_rows)

    prompt_hashes = {name: sha256_file(root / name) for name in PROMPTS}
    selection_csv = root / "data/opp115/qa_approved/opp115_proposed_27_boundary_qa.csv"
    record = {
        "study": "OPP-115 historical extension",
        "freeze_status": "frozen_after_supervisor_approval_before_generation",
        "approval_record": "Supervisor approval reported by the student in the project conversation.",
        "approval_date": args.approval_date,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "policy_count": 27,
        "sector_count": 9,
        "length_balance": bands,
        "models": {
            "gpt": {"provider": "openai", "model_id": "gpt-5.6-luna"},
            "llama": {"provider": "together", "model_id": "meta-llama/Llama-3.3-70B-Instruct-Turbo"},
            "mistral": {"provider": "mistral", "model_id": "mistral-large-2512"},
        },
        "prompt_version": "1.2",
        "prompt_hashes": prompt_hashes,
        "generation_config_sha256": sha256_file(root / "config/opp115_extension_v1.0.yaml"),
        "planned_conditions": 27 * 3 * 6,
        "qa_selection_csv_sha256": sha256_file(selection_csv),
        "metadata_csv_sha256": sha256_file(metadata_path),
        "policies": policy_manifest,
    }
    record_path = frozen_root / "OPP115_FROZEN_SAMPLE_MANIFEST.json"
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Frozen policies: {len(policy_manifest)}")
    print(f"Length balance: {bands}")
    print(f"Planned generation conditions: {record['planned_conditions']}")
    print(f"Manifest: {record_path}")


if __name__ == "__main__":
    main()
