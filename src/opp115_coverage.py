from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

from .common import ROOT, append_csv, load_config, read_csv, sha256_text, write_json
from .v2_statement_verifier import _policy_units


UNIT_FIELDS = [
    "policy_id", "unit_id", "important_information", "importance_reason",
    "material_qualifiers", "source_passage_ids", "exact_source_evidence",
    "model_id", "prompt_sha256", "policy_sha256", "status", "error",
]
COVERAGE_FIELDS = [
    "comparison_id", "blind_id", "policy_id", "unit_id", "important_information",
    "model_id", "coverage_label", "coverage_score", "summary_evidence_ids",
    "summary_evidence", "explanation", "response_id", "timestamp_utc", "status", "error",
]
LOG_FIELDS = [
    "stage", "item_id", "requested", "returned", "model_id", "response_id",
    "timestamp_utc", "status", "error",
]
LABEL_TO_SCORE = {"Not covered": 0, "Partially covered": 1, "Covered": 2}


def _settings() -> tuple[dict, dict]:
    cfg = load_config()
    profile = os.getenv("OPP115_COVERAGE_PROFILE", "opp115_coverage").strip()
    if profile not in {"opp115_coverage", "opp115_coverage_v3"}:
        raise RuntimeError(f"Unsupported OPP coverage profile: {profile}")
    if profile not in cfg:
        raise RuntimeError(f"The selected configuration has no {profile} section")
    settings = dict(cfg[profile])
    settings["profile"] = profile
    return cfg, settings


def _source_unit_instruction(policy_id: str, source_block: str, settings: dict) -> str:
    if str(settings.get("source_unit_prompt_version", "v2")) == "v3":
        return f"""Independently identify the important source-information units in this privacy policy for an ordinary adult reader with no specialist legal, technical or privacy knowledge.

Your objective is coverage-oriented completeness, not a short overview. Read the complete policy from the first supplied passage to the last. For every passage, decide whether it contains an explicit proposition whose omission or distortion would remove meaningful information about how personal information is handled, its possible effects, or the reader's rights and choices.

Use only the supplied policy. Do not use outside knowledge, generated summaries, human-created source units, the OPP-115 taxonomy, or any fixed privacy-category checklist. Do not infer or invent absent topics.

Create one source unit for each independently assessable proposition that meets the importance rule. In particular:
1. Split propositions whenever a later summary could reasonably preserve one while omitting another, even when they occur in the same sentence, paragraph or topic.
2. Do not replace several separately assessable facts with one broad umbrella statement.
3. Do not combine distinct data types, collection sources, purposes, recipients, disclosures, rights, choices, consequences, conditions or exceptions merely because they are related.
4. Include conditional or product-specific information when it materially affects readers who use that product, feature or process. State the condition within the unit.
5. Include scope information when it determines who or what the policy covers, which separate notice applies, or when a stated practice applies.
6. Preserve material actors, data types, purposes, recipients, conditions, exceptions, quantities, time periods and levels of certainty.
7. Cite the smallest sufficient set of supplied source-passage IDs and provide a neutral plain-English statement, a concise importance reason and all material qualifiers.

Exclude decorative headings, navigation text, repetition, purely promotional language and administrative wording that does not materially help the reader. Do not create a separate unit for an example when it adds no distinct information beyond the general proposition.

After drafting the units, perform a completeness pass over every supplied passage. Add any important proposition not yet represented, remove duplicates, and check that no broad unit hides separately omittable facts. There is no required minimum or maximum number of units. Return only the final units in source order; do not return your working or passage-by-passage decisions.

SOURCE POLICY {policy_id}:
{source_block}"""

    return f"""Identify the information in this privacy policy that is important for an ordinary adult reader with no specialist legal, technical or privacy knowledge.

Use only the supplied policy. Do not use outside knowledge, generated summaries, the OPP-115 taxonomy, or any other fixed privacy-category checklist. Do not invent topics that the policy does not contain.

Each unit must:
1. express one independently assessable proposition explicitly present in the policy;
2. help the reader understand how personal information is handled, possible effects, rights or choices;
3. preserve material actors, data types, purposes, recipients, conditions, exceptions, quantities, time periods and levels of certainty;
4. cite the smallest sufficient set of supplied source passage IDs;
5. include a neutral plain-English statement, a concise importance reason and any material qualifiers.

Split unrelated propositions. Combine passages only when needed to express one qualified proposition. Exclude navigation text, decorative headings and administrative wording that does not materially help the reader. There is no required number of units. Return units in source order.

SOURCE POLICY {policy_id}:
{source_block}"""


def _paths(settings: dict) -> dict[str, Path]:
    base = ROOT / settings["output_dir"]
    return {
        "base": base,
        "by_policy": base / "source_units/by_policy",
        "units": base / "source_units/frozen_source_units.csv",
        "unit_manifest": base / "source_units/frozen_source_units_manifest.json",
        "scores": base / "evaluations/gemini_coverage_scores.csv",
        "log": base / "logs/gemini_coverage_log.csv",
        "audit": base / "audits/gemini_coverage_audit.json",
    }


def _api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")
    return key


def _request(model: str, instruction: str, schema: dict, settings: dict) -> tuple[dict, str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": instruction}]}],
        "generationConfig": {
            "temperature": float(settings.get("temperature", 0.0)),
            "maxOutputTokens": int(settings.get("max_output_tokens", 32768)),
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    response = requests.post(
        url, headers={"x-goog-api-key": _api_key()}, json=payload,
        timeout=int(settings.get("timeout_seconds", 600)),
    )
    if not response.ok:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1500]}")
    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidate: {json.dumps(data)[:1500]}")
    raw = candidates[0]["content"]["parts"][0]["text"].strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S)
    request_id = response.headers.get("x-request-id", "") or data.get("responseId", "")
    return json.loads(raw), request_id


def _policies(cfg: dict) -> list[str]:
    metadata = read_csv(ROOT / cfg["paths"]["metadata"])
    policies = sorted({row["policy_id"] for row in metadata})
    if len(policies) != 27:
        raise ValueError(f"Expected 27 OPP policies, found {len(policies)}")
    return policies


def identify_units(max_policies: int | None = None) -> dict:
    cfg, settings = _settings()
    paths = _paths(settings)
    model = settings["model"]
    completed = {
        policy_id for policy_id in _policies(cfg)
        if (paths["by_policy"] / f"{policy_id}_source_units.csv").is_file()
        and all(row.get("status") == "success" for row in read_csv(paths["by_policy"] / f"{policy_id}_source_units.csv"))
        and bool(read_csv(paths["by_policy"] / f"{policy_id}_source_units.csv"))
    }
    pending = [policy_id for policy_id in _policies(cfg) if policy_id not in completed]
    if max_policies is not None:
        pending = pending[:max_policies]
    added = 0
    attempted = 0

    for policy_id in pending:
        attempted += 1
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        log_row = {
            "stage": "identify_units", "item_id": policy_id, "requested": 1,
            "returned": 0, "model_id": model, "response_id": "",
            "timestamp_utc": timestamp, "status": "failed", "error": "",
        }
        try:
            policy_path = ROOT / cfg["paths"]["clean"] / f"{policy_id}.txt"
            policy = policy_path.read_text(encoding="utf-8").strip()
            passages = _policy_units(policy)
            lookup = dict(passages)
            source_block = "\n\n".join(f"[{source_id}] {text}" for source_id, text in passages)
            instruction = _source_unit_instruction(policy_id, source_block, settings)
            schema = {
                "type": "object", "properties": {"units": {"type": "array", "items": {
                    "type": "object", "properties": {
                        "source_passage_ids": {"type": "array", "items": {
                            "type": "string", "enum": list(lookup),
                        }},
                        "important_information": {"type": "string"},
                        "importance_reason": {"type": "string"},
                        "material_qualifiers": {"type": "string"},
                    }, "required": [
                        "source_passage_ids", "important_information",
                        "importance_reason", "material_qualifiers",
                    ],
                }}}, "required": ["units"],
            }
            parsed, response_id = _request(model, instruction, schema, settings)
            proposed = parsed.get("units", [])
            if not isinstance(proposed, list) or not proposed:
                raise ValueError("Gemini returned no source units")
            rows = []
            seen_information = set()
            for index, unit in enumerate(proposed, 1):
                ids = list(dict.fromkeys(str(item).strip() for item in unit.get("source_passage_ids", []) if str(item).strip()))
                information = str(unit.get("important_information", "")).strip()
                reason = str(unit.get("importance_reason", "")).strip()
                if not ids or any(item not in lookup for item in ids):
                    raise ValueError(f"Unit {index} contains missing or invalid source passage IDs")
                if not information or not reason:
                    raise ValueError(f"Unit {index} has blank required text")
                normalised = re.sub(r"\s+", " ", information).casefold()
                if normalised in seen_information:
                    raise ValueError(f"Duplicate important-information unit at position {index}")
                seen_information.add(normalised)
                rows.append({
                    "policy_id": policy_id, "unit_id": f"{policy_id}-U{index:03d}",
                    "important_information": information, "importance_reason": reason,
                    "material_qualifiers": str(unit.get("material_qualifiers", "")).strip(),
                    "source_passage_ids": ";".join(ids),
                    "exact_source_evidence": "\n---\n".join(lookup[item] for item in ids),
                    "model_id": model, "prompt_sha256": sha256_text(instruction),
                    "policy_sha256": sha256_text(policy), "status": "success", "error": "",
                })
            destination = paths["by_policy"] / f"{policy_id}_source_units.csv"
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=UNIT_FIELDS)
                writer.writeheader(); writer.writerows(rows)
            write_json(destination.with_suffix(".audit.json"), {
                "policy_id": policy_id, "model_id": model, "response_id": response_id,
                "timestamp_utc": timestamp, "policy_sha256": sha256_text(policy),
                "prompt_sha256": sha256_text(instruction), "units": len(rows),
                "source_unit_prompt_version": settings.get("source_unit_prompt_version", "v2"),
                "coverage_profile": settings.get("profile", "opp115_coverage"),
                "taxonomy_visible_to_model": False, "summaries_visible_to_model": False,
            })
            added += len(rows)
            log_row.update({"returned": len(rows), "response_id": response_id, "status": "success"})
        except Exception as exc:
            log_row["error"] = f"{type(exc).__name__}: {exc}"
        append_csv(paths["log"], log_row, LOG_FIELDS)
        print(f"Source units {policy_id}: {log_row['status']} units={log_row['returned']}", flush=True)
        if "HTTP 429" in log_row["error"] and settings.get("free_tier", True):
            print("Gemini free-tier quota reached; rerun later to resume.", flush=True)
            break
        time.sleep(float(settings.get("request_delay_seconds", 10)))
    return {"attempted_policies": attempted, "new_units": added, **unit_status()}


def unit_status() -> dict:
    cfg, settings = _settings()
    paths = _paths(settings)
    policies = _policies(cfg)
    completed, units = 0, 0
    for policy_id in policies:
        rows = read_csv(paths["by_policy"] / f"{policy_id}_source_units.csv")
        if rows and all(row.get("status") == "success" for row in rows):
            completed += 1; units += len(rows)
    return {"completed_policies": completed, "expected_policies": 27, "units": units}


def freeze_units() -> dict:
    cfg, settings = _settings()
    paths = _paths(settings)
    rows = []
    counts = {}
    for policy_id in _policies(cfg):
        policy_rows = read_csv(paths["by_policy"] / f"{policy_id}_source_units.csv")
        if not policy_rows or any(row.get("status") != "success" for row in policy_rows):
            raise RuntimeError(f"Source units are not complete and valid for {policy_id}")
        expected = [f"{policy_id}-U{i:03d}" for i in range(1, len(policy_rows) + 1)]
        if [row["unit_id"] for row in policy_rows] != expected:
            raise ValueError(f"Non-contiguous source-unit IDs for {policy_id}")
        counts[policy_id] = len(policy_rows)
        rows.extend(policy_rows)
    if len({row["unit_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate unit IDs across policies")
    paths["units"].parent.mkdir(parents=True, exist_ok=True)
    with paths["units"].open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=UNIT_FIELDS)
        writer.writeheader(); writer.writerows(rows)
    digest = hashlib.sha256(paths["units"].read_bytes()).hexdigest()
    manifest = {
        "status": "frozen", "policies": 27, "units": len(rows),
        "units_per_policy": counts, "sha256": digest,
        "source_unit_prompt_version": settings.get("source_unit_prompt_version", "v2"),
        "coverage_profile": settings.get("profile", "opp115_coverage"),
        "taxonomy_used_during_identification": False,
        "summaries_used_during_identification": False,
    }
    write_json(paths["unit_manifest"], manifest)
    return manifest


def _summary_passages(summary: str) -> tuple[str, dict[str, str]]:
    passages = _policy_units(summary)
    lookup = {f"SUM{index:03d}": text for index, (_, text) in enumerate(passages, 1)}
    block = "\n".join(f"[{item}] {text}" for item, text in lookup.items())
    return block, lookup


def score_coverage(max_summaries: int | None = None) -> dict:
    cfg, settings = _settings()
    paths = _paths(settings)
    units = read_csv(paths["units"])
    if not units or not paths["unit_manifest"].is_file():
        raise RuntimeError("Freeze all 27 source-unit sets before coverage scoring")
    units_by_policy = defaultdict(list)
    for row in units:
        units_by_policy[row["policy_id"]].append(row)
    key = read_csv(ROOT / cfg["faithfulness"]["blinding_key"])
    if len(key) != 486:
        raise ValueError(f"Expected 486 blinded summaries, found {len(key)}")
    expected = {
        f"{row['blind_id']}--{unit['unit_id']}"
        for row in key for unit in units_by_policy[row["policy_id"]]
    }
    existing = read_csv(paths["scores"])
    completed = {
        row["comparison_id"] for row in existing
        if row.get("status") == "success" and row.get("comparison_id") in expected
    }
    pending_summaries = [
        row for row in sorted(key, key=lambda item: item["blind_id"])
        if any(f"{row['blind_id']}--{unit['unit_id']}" not in completed for unit in units_by_policy[row["policy_id"]])
    ]
    if max_summaries is not None:
        pending_summaries = pending_summaries[:max_summaries]
    model = settings["model"]
    new_rows = 0
    attempted = 0
    max_units = int(settings.get("max_units_per_request", 100))

    for key_row in pending_summaries:
        blind_id, policy_id = key_row["blind_id"], key_row["policy_id"]
        pending_units = [
            unit for unit in units_by_policy[policy_id]
            if f"{blind_id}--{unit['unit_id']}" not in completed
        ]
        summary = (ROOT / cfg["paths"]["anonymised"] / f"{blind_id}.txt").read_text(encoding="utf-8").strip()
        summary_block, summary_lookup = _summary_passages(summary)
        for start in range(0, len(pending_units), max_units):
            batch = pending_units[start:start + max_units]
            attempted += 1
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            item_id = f"{blind_id}-B{1 + start // max_units:03d}"
            log_row = {
                "stage": "score_coverage", "item_id": item_id, "requested": len(batch),
                "returned": 0, "model_id": model, "response_id": "",
                "timestamp_utc": timestamp, "status": "failed", "error": "",
            }
            seen: set[str] = set()
            try:
                unit_block = "\n".join(json.dumps({
                    "unit_id": row["unit_id"],
                    "important_information": row["important_information"],
                    "material_qualifiers": row["material_qualifiers"],
                }, ensure_ascii=False) for row in batch)
                instruction = f"""Assess whether every independently identified important source-policy unit is retained in the supplied plain-English summary. Use only the unit text and the summary. Do not use outside knowledge.

Labels:
- Covered: all material meaning and qualifications are retained.
- Partially covered: the topic is present, but material meaning, scope, condition, exception or qualification is missing or weakened.
- Not covered: the important information is absent.

For Covered or Partially covered, cite the smallest sufficient set of supplied summary passage IDs. For Not covered, return an empty evidence ID array. Give a concise reason. Return every requested unit exactly once.

BLINDED SUMMARY {blind_id}:
{summary_block}

IMPORTANT SOURCE UNITS:
{unit_block}"""
                expected_ids = [row["unit_id"] for row in batch]
                schema = {
                    "type": "object", "properties": {"judgments": {"type": "array", "items": {
                        "type": "object", "properties": {
                            "unit_id": {"type": "string", "enum": expected_ids},
                            "coverage_label": {"type": "string", "enum": list(LABEL_TO_SCORE)},
                            "summary_evidence_ids": {"type": "array", "items": {
                                "type": "string", "enum": list(summary_lookup),
                            }},
                            "explanation": {"type": "string"},
                        }, "required": ["unit_id", "coverage_label", "summary_evidence_ids", "explanation"],
                    }}}, "required": ["judgments"],
                }
                parsed, response_id = _request(model, instruction, schema, settings)
                judgments = parsed.get("judgments", [])
                if not isinstance(judgments, list):
                    raise ValueError("Gemini response judgments is not an array")
                lookup = {row["unit_id"]: row for row in batch}
                for judgment in judgments:
                    unit_id = str(judgment.get("unit_id", ""))
                    label = judgment.get("coverage_label")
                    evidence_ids = list(dict.fromkeys(
                        str(item).strip() for item in judgment.get("summary_evidence_ids", []) if str(item).strip()
                    ))
                    explanation = str(judgment.get("explanation", "")).strip()
                    if unit_id not in lookup or unit_id in seen or label not in LABEL_TO_SCORE:
                        continue
                    if any(item not in summary_lookup for item in evidence_ids) or not explanation:
                        continue
                    if (label == "Not covered" and evidence_ids) or (label != "Not covered" and not evidence_ids):
                        continue
                    comparison_id = f"{blind_id}--{unit_id}"
                    append_csv(paths["scores"], {
                        "comparison_id": comparison_id, "blind_id": blind_id, "policy_id": policy_id,
                        "unit_id": unit_id, "important_information": lookup[unit_id]["important_information"],
                        "model_id": model, "coverage_label": label,
                        "coverage_score": LABEL_TO_SCORE[label],
                        "summary_evidence_ids": ";".join(evidence_ids),
                        "summary_evidence": "\n---\n".join(summary_lookup[item] for item in evidence_ids),
                        "explanation": explanation, "response_id": response_id,
                        "timestamp_utc": timestamp, "status": "success", "error": "",
                    }, COVERAGE_FIELDS)
                    seen.add(unit_id); completed.add(comparison_id); new_rows += 1
                if seen != set(expected_ids):
                    missing = sorted(set(expected_ids) - seen)
                    raise ValueError(f"Missing or invalid judgments for {len(missing)} units: {missing[:5]}")
                log_row.update({"returned": len(seen), "response_id": response_id, "status": "success"})
            except Exception as exc:
                log_row["returned"] = len(seen)
                log_row["error"] = f"{type(exc).__name__}: {exc}"
            append_csv(paths["log"], log_row, LOG_FIELDS)
            print(f"Coverage {item_id}: {log_row['status']} units={log_row['returned']}/{len(batch)}", flush=True)
            if "HTTP 429" in log_row["error"] and settings.get("free_tier", True):
                print("Gemini free-tier quota reached; rerun later to resume.", flush=True)
                return {"new_rows": new_rows, "attempted_requests": attempted, **coverage_status()}
            time.sleep(float(settings.get("request_delay_seconds", 10)))
    return {"new_rows": new_rows, "attempted_requests": attempted, **coverage_status()}


def coverage_status() -> dict:
    cfg, settings = _settings()
    paths = _paths(settings)
    units = read_csv(paths["units"])
    if not units:
        return {"expected_comparisons": 0, "successful_unique": 0, "remaining": 0, "summaries_represented": 0}
    by_policy = Counter(row["policy_id"] for row in units)
    key = read_csv(ROOT / cfg["faithfulness"]["blinding_key"])
    expected = sum(by_policy[row["policy_id"]] for row in key)
    valid_ids = {
        f"{row['blind_id']}--{unit['unit_id']}"
        for row in key for unit in units if unit["policy_id"] == row["policy_id"]
    }
    successful_rows = [
        row for row in read_csv(paths["scores"])
        if row.get("status") == "success" and row.get("comparison_id") in valid_ids
    ]
    successful = {row["comparison_id"] for row in successful_rows}
    return {
        "expected_comparisons": expected, "successful_unique": len(successful),
        "remaining": expected - len(successful),
        "summaries_represented": len({row["blind_id"] for row in successful_rows}),
    }


def audit_coverage() -> dict:
    cfg, settings = _settings()
    paths = _paths(settings)
    units = read_csv(paths["units"])
    key = read_csv(ROOT / cfg["faithfulness"]["blinding_key"])
    expected = {
        f"{row['blind_id']}--{unit['unit_id']}"
        for row in key for unit in units if unit["policy_id"] == row["policy_id"]
    }
    rows = [row for row in read_csv(paths["scores"]) if row.get("status") == "success"]
    counts = Counter(row["comparison_id"] for row in rows)
    audit = {
        "expected_comparisons": len(expected), "successful_rows": len(rows),
        "unique_successful": len(counts), "remaining": len(expected - set(counts)),
        "duplicates": sum(count - 1 for count in counts.values() if count > 1),
        "unexpected": len(set(counts) - expected),
        "invalid_labels": sum(row.get("coverage_label") not in LABEL_TO_SCORE for row in rows),
        "blank_explanations": sum(not row.get("explanation", "").strip() for row in rows),
        "invalid_evidence": sum(
            (row.get("coverage_label") == "Not covered" and row.get("summary_evidence", "").strip())
            or (row.get("coverage_label") != "Not covered" and not row.get("summary_evidence", "").strip())
            for row in rows
        ),
        "summaries_represented": len({row["blind_id"] for row in rows}),
        "label_distribution": dict(Counter(row["coverage_label"] for row in rows)),
    }
    audit["valid_complete"] = (
        audit["remaining"] == audit["duplicates"] == audit["unexpected"] == 0
        and audit["invalid_labels"] == audit["blank_explanations"] == audit["invalid_evidence"] == 0
        and audit["summaries_represented"] == 486
    )
    write_json(paths["audit"], audit)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="OPP-115 independent source-unit and coverage workflow")
    sub = parser.add_subparsers(dest="command", required=True)
    identify = sub.add_parser("identify-units"); identify.add_argument("--max-policies", type=int)
    sub.add_parser("unit-status")
    sub.add_parser("freeze-units")
    score = sub.add_parser("score"); score.add_argument("--max-summaries", type=int)
    sub.add_parser("status")
    sub.add_parser("audit")
    args = parser.parse_args()
    if args.command == "identify-units": result = identify_units(args.max_policies)
    elif args.command == "unit-status": result = unit_status()
    elif args.command == "freeze-units": result = freeze_units()
    elif args.command == "score": result = score_coverage(args.max_summaries)
    elif args.command == "status": result = coverage_status()
    else: result = audit_coverage()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
