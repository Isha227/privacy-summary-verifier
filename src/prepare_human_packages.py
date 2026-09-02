from __future__ import annotations

import csv
import hashlib
import shutil
from pathlib import Path

from .common import ROOT, read_csv


BASE = ROOT / "data/main/faithfulness_sample"
CLAIMS = BASE / "claim_candidates.csv"
KEY = ROOT / "data/main/anonymised/BLINDING_KEY_RESTRICTED.csv"
SOURCES = BASE / "blinded_sources"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare() -> tuple[int, Path]:
    claims = read_csv(CLAIMS)
    required = sorted({row["blind_id"] for row in claims})
    mapping = {row["blind_id"]: row["policy_id"] for row in read_csv(KEY)}
    if len(required) != 270:
        raise RuntimeError(f"Expected claims from 270 summaries, found {len(required)}")

    SOURCES.mkdir(parents=True, exist_ok=True)
    manifest = []
    for blind_id in required:
        if blind_id not in mapping:
            raise KeyError(f"No source-policy mapping for {blind_id}")
        source = ROOT / "data/main/clean" / f"{mapping[blind_id]}.txt"
        destination = SOURCES / f"{blind_id}_source.txt"
        shutil.copyfile(source, destination)
        manifest.append({
            "blind_id": blind_id,
            "source_file": f"blinded_sources/{destination.name}",
            "source_sha256": sha256(destination),
        })

    manifest_path = BASE / "EVALUATOR_SOURCE_INDEX.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=manifest[0].keys())
        writer.writeheader()
        writer.writerows(manifest)
    return len(manifest), manifest_path


if __name__ == "__main__":
    count, path = prepare()
    print(f"Prepared {count} evaluator-safe blinded source files: {path}")
