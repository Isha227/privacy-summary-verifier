"""Validate the frozen OPP-115 sample without making API calls."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "data/opp115/frozen"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_hash(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest()


def main() -> None:
    manifest = json.loads((FROZEN / "OPP115_FROZEN_SAMPLE_MANIFEST.json").read_text(encoding="utf-8"))
    config_path = ROOT / "config/opp115_extension_v1.0.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    metadata_path = FROZEN / "metadata/policies.csv"
    with metadata_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert manifest["freeze_status"] == "frozen_after_supervisor_approval_before_generation"
    assert manifest["policy_count"] == 27 and len(rows) == 27
    assert len({row["policy_id"] for row in rows}) == 27
    assert len({row["sector"] for row in rows}) == 9
    bands = {name: sum(row["length_band"] == name for row in rows) for name in ("Short", "Medium", "Long")}
    assert bands == {"Short": 9, "Medium": 9, "Long": 9}
    assert file_hash(config_path) == manifest["generation_config_sha256"]
    assert file_hash(metadata_path) == manifest["metadata_csv_sha256"]

    manifest_policies = {row["policy_id"]: row for row in manifest["policies"]}
    for row in rows:
        source = ROOT / row["source_path"]
        actual = text_hash(source)
        assert actual == row["source_sha256"] == manifest_policies[row["policy_id"]]["source_sha256"]

    for prompt_path, expected in manifest["prompt_hashes"].items():
        assert file_hash(ROOT / prompt_path) == expected
    for family, model in manifest["models"].items():
        assert config["models"][family]["provider"] == model["provider"]
        assert config["models"][family]["model_id"] == model["model_id"]

    condition_count = len(rows) * len(config["models"]) * len(config["prompts"])
    assert condition_count == manifest["planned_conditions"] == 486
    clean_files = list((FROZEN / "clean").glob("OPP*.txt"))
    assert len(clean_files) == 27

    print("VALID FROZEN OPP-115 EXTENSION")
    print(f"Policies: {len(rows)}; sectors: 9; bands: {bands}")
    print(f"Models: {len(config['models'])}; prompts: {len(config['prompts'])}; conditions: {condition_count}")
    print("All source, prompt, metadata and configuration hashes match.")


if __name__ == "__main__":
    main()
