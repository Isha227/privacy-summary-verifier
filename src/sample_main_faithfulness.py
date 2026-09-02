from __future__ import annotations

import csv
import hashlib
import random
from collections import Counter

from .common import ROOT, read_csv
from .faithfulness import CLAIM_FIELDS, HUMAN_FIELDS, _write_csv


SEED = 20260814
SOURCE = ROOT / "data/main/faithfulness/claim_candidates.csv"
DESTINATION = ROOT / "data/main/faithfulness_sample"
BLINDING_KEY = ROOT / "data/main/anonymised/BLINDING_KEY_RESTRICTED.csv"
METADATA = ROOT / "data/main/metadata/policies.csv"
METRICS = ROOT / "data/main/evaluations/metrics.csv"
CELLS = [(m, p) for m in ("gpt", "llama", "mistral") for p in ("zero", "role", "structured")]


def _stable_seed(label: str) -> int:
    digest = hashlib.sha256(f"{SEED}:{label}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _check_templates_are_blank() -> None:
    for annotator in ("A1", "A2", "A3"):
        path = DESTINATION / f"human_faithfulness_{annotator}.csv"
        if path.exists() and any(row.get("label", "").strip() for row in read_csv(path)):
            raise RuntimeError(f"Refusing to overwrite scored evaluator file: {path}")


def _choose_full_policies() -> tuple[list[str], dict[str, str]]:
    metadata = {row["policy_id"]: row for row in read_csv(METADATA)}
    source_words: dict[str, int] = {}
    for row in read_csv(METRICS):
        source_words.setdefault(row["policy_id"], int(row["source_words"]))
    ranked = sorted(source_words, key=lambda policy_id: (source_words[policy_id], policy_id))
    length_group = {
        policy_id: ("short" if index < 10 else "medium" if index < 20 else "long")
        for index, policy_id in enumerate(ranked)
    }
    rng = random.Random(SEED)
    policies = sorted(metadata)
    for _ in range(100000):
        selected = rng.sample(policies, 9)
        sector_counts = Counter(metadata[p]["sector"] for p in selected)
        length_counts = Counter(length_group[p] for p in selected)
        if sorted(sector_counts.values()) == [1, 1, 1, 2, 2, 2] and length_counts == {"short": 3, "medium": 3, "long": 3}:
            rng.shuffle(selected)
            return selected, length_group
    raise RuntimeError("Could not construct the required balanced full-summary sample")


def create_sample() -> tuple[int, str]:
    _check_templates_are_blank()
    candidates = read_csv(SOURCE)
    by_blind: dict[str, list[dict[str, str]]] = {}
    for row in candidates:
        if row.get("include", "yes").strip().lower() == "yes":
            by_blind.setdefault(row["blind_id"], []).append(row)

    key_rows = read_csv(BLINDING_KEY)
    key_by_blind = {row["blind_id"]: row for row in key_rows}
    expected_blind_ids = set(key_by_blind)
    if set(by_blind) != expected_blind_ids or len(expected_blind_ids) != 270:
        raise RuntimeError("Candidate blind IDs do not match the 270 frozen summaries")

    chosen_policies, length_group = _choose_full_policies()
    full_by_cell = dict(zip(CELLS, chosen_policies))
    full_blind_ids: set[str] = set()
    for cell, policy_id in full_by_cell.items():
        matches = [
            row["blind_id"] for row in key_rows
            if row["policy_id"] == policy_id
            and row["model_family"] == cell[0]
            and row["prompt_strategy"] == cell[1]
        ]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one blinded summary for {policy_id} {cell}, found {len(matches)}")
        full_blind_ids.add(matches[0])

    selected_by_key: dict[tuple[str, str], dict[str, str]] = {}
    selection_role: dict[tuple[str, str], str] = {}
    for blind_id in sorted(by_blind):
        pool = by_blind[blind_id]
        if blind_id in full_blind_ids:
            for row in pool:
                key = (row["blind_id"], row["claim_id"])
                selected_by_key[key] = row
                selection_role[key] = "full_summary"
        else:
            chosen = random.Random(_stable_seed(blind_id)).choice(pool)
            key = (chosen["blind_id"], chosen["claim_id"])
            selected_by_key[key] = chosen
            selection_role[key] = "one_claim_broad_sample"

    selected = sorted(selected_by_key.values(), key=lambda row: (row["blind_id"], row["claim_id"]))
    DESTINATION.mkdir(parents=True, exist_ok=True)
    claims_path = DESTINATION / "claim_candidates.csv"
    _write_csv(claims_path, CLAIM_FIELDS, selected)

    human_rows = [{
        "blind_id": row["blind_id"], "claim_id": row["claim_id"], "claim_text": row["claim_text"],
        "label": "", "evidence_quote": "", "evidence_location": "", "annotator_notes": "",
    } for row in selected]
    for annotator in ("A1", "A2", "A3"):
        _write_csv(DESTINATION / f"human_faithfulness_{annotator}.csv", HUMAN_FIELDS, human_rows)

    metadata = {row["policy_id"]: row for row in read_csv(METADATA)}
    audit_rows = []
    for row in selected:
        mapped = key_by_blind[row["blind_id"]]
        key = (row["blind_id"], row["claim_id"])
        audit_rows.append({
            "blind_id": row["blind_id"], "claim_id": row["claim_id"],
            "selection_role": selection_role[key], "policy_id": mapped["policy_id"],
            "sector": metadata[mapped["policy_id"]]["sector"],
            "policy_length_group": length_group[mapped["policy_id"]],
            "model_family": mapped["model_family"], "prompt_strategy": mapped["prompt_strategy"],
            "selection_seed": str(SEED),
        })
    audit_path = DESTINATION / "HYBRID_SAMPLING_KEY_RESTRICTED.csv"
    with audit_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=audit_rows[0].keys())
        writer.writeheader()
        writer.writerows(audit_rows)

    if len({row["blind_id"] for row in selected}) != 270 or len(full_blind_ids) != 9:
        raise RuntimeError("Hybrid sample coverage check failed")
    return len(selected), str(audit_path)


if __name__ == "__main__":
    count, audit = create_sample()
    print(f"Created hybrid human-validation sample with {count} claims")
    print(f"Restricted audit key: {audit}")
