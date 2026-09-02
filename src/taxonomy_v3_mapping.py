from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import requests

from .common import ROOT, append_csv, read_csv, write_json


OPP_UNITS = ROOT / "data/opp115/experiment/coverage_v3/source_units/frozen_source_units.csv"
HUMAN_UNITS = ROOT / "data/v2_prompt_intervention_v1_2/source_unit_method_validation/final_comparison/final_reference_completeness.csv"
GEMINI_UNITS = ROOT / "data/v2_prompt_intervention_v1_2/source_unit_method_validation/gemini_v3/frozen_gemini_source_units.csv"
BLINDING = ROOT / "data/v2_prompt_intervention_v1_2/source_unit_method_validation/v3_researcher_comparison/restricted/BLINDING_KEY_RESTRICTED.csv"
FINAL_DECISIONS = ROOT / "data/v2_prompt_intervention_v1_2/source_unit_method_validation/v3_researcher_comparison/adjudication/final_v3_source_unit_decisions.csv"
CATEGORY_XML = ROOT / "data/opp115/raw/OPP-115_v1_0/OPP-115/documentation/categories-july30.xml"
OPP_CANDIDATES = ROOT / "data/opp115/experiment/coverage_v3/taxonomy/opp115_unit_taxonomy_candidates.csv"
BASE = ROOT / "data/opp115/experiment/taxonomy_v3"
PREPARED = BASE / "prepared/frozen_unified_units.csv"
MAPPINGS = BASE / "evaluations/gemini_taxonomy_mappings.csv"
LOG = BASE / "logs/gemini_taxonomy_log.csv"
AUDIT = BASE / "audits/taxonomy_mapping_audit.json"
MANIFEST = BASE / "prepared/frozen_unified_units_manifest.json"

MODEL = "gemini-3.5-flash-lite"
PROMPT_VERSION = "opp-taxonomy-v3.1"
CATEGORY_ORDER = [
    "First Party Collection/Use",
    "Third Party Sharing/Collection",
    "User Choice/Control",
    "User Access, Edit and Deletion",
    "Data Retention",
    "Data Security",
    "Policy Change",
    "Do Not Track",
    "International and Specific Audiences",
    "Other",
]
UNIT_FIELDS = [
    "mapping_id", "dataset", "policy_id", "unit_id", "important_information",
    "material_qualifiers", "exact_source_evidence",
]
MAPPING_FIELDS = UNIT_FIELDS + [
    "primary_category", "secondary_categories", "explanation", "confidence",
    "model_id", "prompt_version", "response_id", "timestamp_utc", "status", "error",
]
LOG_FIELDS = [
    "batch_id", "requested", "returned", "model_id", "response_id",
    "timestamp_utc", "status", "error",
]


def _api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Missing GEMINI_API_KEY")
    return key


def _category_definitions() -> dict[str, str]:
    root = ET.parse(CATEGORY_XML).getroot()
    namespace = {"x": "http://www.w3schools.com"}
    found = {}
    for category in root.findall("x:category", namespace):
        name = (category.findtext("x:name", default="", namespaces=namespace) or "").strip()
        description = (category.findtext("x:description", default="", namespaces=namespace) or "").strip()
        if name:
            found[name] = re.sub(r"\s+", " ", description)
    if list(found) != CATEGORY_ORDER:
        raise ValueError(f"Unexpected OPP category order: {list(found)}")
    return found


def prepare() -> dict:
    rows: list[dict] = []
    for row in read_csv(OPP_UNITS):
        rows.append({
            "mapping_id": f"HIST-{row['unit_id']}",
            "dataset": "OPP historical",
            "policy_id": row["policy_id"],
            "unit_id": row["unit_id"],
            "important_information": row["important_information"],
            "material_qualifiers": row.get("material_qualifiers", ""),
            "exact_source_evidence": row["exact_source_evidence"],
        })

    for row in read_csv(HUMAN_UNITS):
        rows.append({
            "mapping_id": f"CUR-H-{row['policy_code']}-{row['unit_id']}",
            "dataset": "Contemporary human reference",
            "policy_id": row["policy_code"],
            "unit_id": row["unit_id"],
            "important_information": row["important_information"],
            "material_qualifiers": row.get("material_qualifiers", ""),
            "exact_source_evidence": row["exact_source_evidence"],
        })

    additions = {
        row["unit_id"] for row in read_csv(FINAL_DECISIONS)
        if row["direction"] == "candidate_to_reference"
        and row["final_label"] == "Valid additional unit"
    }
    blind_to_original = {
        row["safe_id"]: row["original_id"] for row in read_csv(BLINDING)
        if row["set"] == "A"
    }
    gemini_lookup = {row["candidate_unit_id"]: row for row in read_csv(GEMINI_UNITS)}
    if len(additions) != 4:
        raise ValueError(f"Expected four validated additions, found {len(additions)}")
    for blind_id in sorted(additions):
        original_id = blind_to_original.get(blind_id, "")
        if original_id not in gemini_lookup:
            raise ValueError(f"Cannot resolve validated addition {blind_id}")
        row = gemini_lookup[original_id]
        rows.append({
            "mapping_id": f"CUR-G-{blind_id}",
            "dataset": "Contemporary Gemini validated addition",
            "policy_id": row["policy_id"],
            "unit_id": blind_id,
            "important_information": row["important_information"],
            "material_qualifiers": row.get("material_qualifiers", ""),
            "exact_source_evidence": row["exact_source_evidence"],
        })

    if len(rows) != 1177 or len({row["mapping_id"] for row in rows}) != 1177:
        raise ValueError("Unified taxonomy input must contain 1,177 unique units")
    PREPARED.parent.mkdir(parents=True, exist_ok=True)
    with PREPARED.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=UNIT_FIELDS)
        writer.writeheader(); writer.writerows(rows)
    import hashlib
    manifest = {
        "status": "frozen",
        "units": len(rows),
        "dataset_counts": dict(Counter(row["dataset"] for row in rows)),
        "category_definitions": _category_definitions(),
        "prompt_version": PROMPT_VERSION,
        "sha256": hashlib.sha256(PREPARED.read_bytes()).hexdigest(),
    }
    write_json(MANIFEST, manifest)
    return manifest


def _instruction(batch: list[dict]) -> str:
    definitions = _category_definitions()
    category_block = "\n".join(f"- {name}: {definitions[name]}" for name in CATEGORY_ORDER)
    unit_block = "\n".join(json.dumps({
        "mapping_id": row["mapping_id"],
        "important_information": row["important_information"],
        "material_qualifiers": row["material_qualifiers"],
        "source_evidence": row["exact_source_evidence"],
    }, ensure_ascii=False) for row in batch)
    return f"""Classify each already-frozen important privacy-policy source unit using the official OPP-115 high-level taxonomy definitions below.

This is a classification task only. Do not judge whether the unit is important, covered by a summary, historically common, or well written. Use only the supplied unit and source evidence. You are not told whether a unit is historical, contemporary, human-created or machine-created, and you must not infer that origin.

Assign exactly one primary category to every unit. Choose the category describing the unit's principal privacy practice, not merely a word appearing in it. Add a secondary category only when the unit independently expresses another privacy practice that genuinely satisfies that category definition. Do not add secondary categories for weak topical associations. Use Other when none of the nine specific categories adequately describes the principal proposition. Do not force a contemporary practice into an unsuitable specific category.

OFFICIAL OPP-115 CATEGORIES:
{category_block}

For each unit, return its mapping_id, primary_category, zero or more secondary_categories, a concise evidence-based explanation, and confidence (High, Medium or Low). Return every requested unit exactly once.

UNITS:
{unit_block}"""


def _request(batch: list[dict]) -> tuple[list[dict], str]:
    expected_ids = [row["mapping_id"] for row in batch]
    schema = {
        "type": "object", "properties": {"mappings": {"type": "array", "items": {
            "type": "object", "properties": {
                "mapping_id": {"type": "string", "enum": expected_ids},
                "primary_category": {"type": "string", "enum": CATEGORY_ORDER},
                "secondary_categories": {"type": "array", "items": {"type": "string", "enum": CATEGORY_ORDER}},
                "explanation": {"type": "string"},
                "confidence": {"type": "string", "enum": ["High", "Medium", "Low"]},
            }, "required": ["mapping_id", "primary_category", "secondary_categories", "explanation", "confidence"],
        }}}, "required": ["mappings"],
    }
    request_kwargs = {
        "headers": {"x-goog-api-key": _api_key()},
        "json": {
            "contents": [{"parts": [{"text": _instruction(batch)}]}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 32768,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        },
        "timeout": 600,
    }
    response = None
    for attempt, delay in enumerate((0, 5, 15), start=1):
        if delay:
            time.sleep(delay)
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
            **request_kwargs,
        )
        if response.status_code not in {500, 502, 503, 504} or attempt == 3:
            break
    assert response is not None
    if not response.ok:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1500]}")
    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidate: {json.dumps(data)[:1000]}")
    raw = candidates[0]["content"]["parts"][0]["text"].strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S)
    response_id = response.headers.get("x-request-id", "") or data.get("responseId", "")
    return json.loads(raw).get("mappings", []), response_id


def run(max_batches: int | None = None, batch_size: int = 40) -> dict:
    if not PREPARED.is_file() or not MANIFEST.is_file():
        prepare()
    units = read_csv(PREPARED)
    lookup = {row["mapping_id"]: row for row in units}
    completed = {
        row["mapping_id"] for row in read_csv(MAPPINGS)
        if row.get("status") == "success" and row.get("mapping_id") in lookup
    }
    pending = [row for row in units if row["mapping_id"] not in completed]
    batches = [pending[i:i + batch_size] for i in range(0, len(pending), batch_size)]
    if max_batches is not None:
        batches = batches[:max_batches]
    added = 0
    starting_batch_number = 1 + len(completed) // batch_size
    for index, batch in enumerate(batches, 1):
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        batch_id = f"TV3-B{starting_batch_number + index - 1:03d}"
        log = {"batch_id": batch_id, "requested": len(batch), "returned": 0, "model_id": MODEL,
               "response_id": "", "timestamp_utc": timestamp, "status": "failed", "error": ""}
        try:
            mappings, response_id = _request(batch)
            expected = {row["mapping_id"] for row in batch}
            seen = set()
            rows = []
            for item in mappings:
                mapping_id = str(item.get("mapping_id", "")).strip()
                primary = str(item.get("primary_category", "")).strip()
                secondary = list(dict.fromkeys(str(x).strip() for x in item.get("secondary_categories", []) if str(x).strip()))
                explanation = str(item.get("explanation", "")).strip()
                confidence = str(item.get("confidence", "")).strip()
                if mapping_id not in expected or mapping_id in seen or primary not in CATEGORY_ORDER:
                    continue
                if any(x not in CATEGORY_ORDER or x == primary for x in secondary):
                    continue
                if not explanation or confidence not in {"High", "Medium", "Low"}:
                    continue
                base = lookup[mapping_id]
                rows.append({**base, "primary_category": primary,
                             "secondary_categories": "; ".join(secondary), "explanation": explanation,
                             "confidence": confidence, "model_id": MODEL, "prompt_version": PROMPT_VERSION,
                             "response_id": response_id, "timestamp_utc": timestamp, "status": "success", "error": ""})
                seen.add(mapping_id)
            if seen != expected:
                raise ValueError(f"Missing or invalid mappings for {len(expected - seen)} units")
            for row in rows:
                append_csv(MAPPINGS, row, MAPPING_FIELDS)
            added += len(rows); completed.update(seen)
            log.update({"returned": len(rows), "response_id": response_id, "status": "success"})
        except Exception as exc:
            log["error"] = f"{type(exc).__name__}: {exc}"
        append_csv(LOG, log, LOG_FIELDS)
        print(f"Taxonomy {batch_id}: {log['status']} units={log['returned']}/{len(batch)}", flush=True)
        if "HTTP 429" in log["error"]:
            break
        time.sleep(10)
    return {"new_rows": added, **status()}


def status() -> dict:
    expected = len(read_csv(PREPARED)) if PREPARED.is_file() else 0
    rows = [row for row in read_csv(MAPPINGS) if row.get("status") == "success"]
    unique = {row["mapping_id"] for row in rows}
    return {"expected": expected, "successful_unique": len(unique), "remaining": expected - len(unique)}


def audit() -> dict:
    units = read_csv(PREPARED)
    expected = {row["mapping_id"] for row in units}
    rows = [row for row in read_csv(MAPPINGS) if row.get("status") == "success"]
    counts = Counter(row["mapping_id"] for row in rows)
    invalid_secondary = 0
    for row in rows:
        secondary = [x.strip() for x in row.get("secondary_categories", "").split(";") if x.strip()]
        invalid_secondary += int(any(x not in CATEGORY_ORDER or x == row.get("primary_category") for x in secondary))
    result = {
        "expected": len(expected), "successful_rows": len(rows), "unique_successful": len(counts),
        "remaining": len(expected - set(counts)),
        "duplicates": sum(n - 1 for n in counts.values() if n > 1),
        "unexpected": len(set(counts) - expected),
        "invalid_primary": sum(row.get("primary_category") not in CATEGORY_ORDER for row in rows),
        "invalid_secondary": invalid_secondary,
        "blank_explanations": sum(not row.get("explanation", "").strip() for row in rows),
        "invalid_confidence": sum(row.get("confidence") not in {"High", "Medium", "Low"} for row in rows),
        "dataset_counts": dict(Counter(row["dataset"] for row in rows)),
        "primary_distribution": dict(Counter(row["primary_category"] for row in rows)),
    }
    result["valid_complete"] = all(result[key] == 0 for key in [
        "remaining", "duplicates", "unexpected", "invalid_primary", "invalid_secondary",
        "blank_explanations", "invalid_confidence",
    ]) and result["unique_successful"] == 1177
    write_json(AUDIT, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--max-batches", type=int)
    run_parser.add_argument("--batch-size", type=int, default=40)
    sub.add_parser("status"); sub.add_parser("audit")
    args = parser.parse_args()
    if args.command == "prepare": result = prepare()
    elif args.command == "run": result = run(args.max_batches, args.batch_size)
    elif args.command == "status": result = status()
    else: result = audit()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
