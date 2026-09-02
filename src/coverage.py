"""Gemini coverage scoring for frozen source units and blinded summaries."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests

from .common import ROOT, append_csv, load_config, read_csv


COVERAGE_FIELDS = [
    "blind_id", "policy_id", "unit_id", "category", "model_id",
    "coverage_score", "summary_evidence", "scoring_rationale",
    "evidence_is_verbatim", "response_id", "timestamp_utc", "status", "error",
]
COVERAGE_BATCH_FIELDS = [
    "batch_id", "blind_id", "model_id", "requested_units", "returned_units",
    "response_id", "timestamp_utc", "status", "error",
]


def _coverage_config() -> tuple[dict, dict]:
    cfg = load_config()
    if "coverage" not in cfg:
        raise RuntimeError("The selected configuration has no coverage section")
    return cfg, cfg["coverage"]


def _paths(cc: dict) -> tuple[Path, Path, Path]:
    units = ROOT / cc["frozen_units"]
    summaries = ROOT / cc["blinded_summaries_dir"]
    results = ROOT / cc["results_dir"]
    return units, summaries, results


def validate_coverage_setup() -> tuple[int, int, int]:
    _, cc = _coverage_config()
    unit_path, summary_dir, _ = _paths(cc)
    units = read_csv(unit_path)
    if not units:
        raise RuntimeError(f"No frozen units found: {unit_path}")
    unit_ids = [row["unit_id"].strip() for row in units]
    if len(unit_ids) != len(set(unit_ids)):
        raise RuntimeError("Frozen coverage unit IDs are not unique")
    if any(row.get("status", "").strip() != "frozen" for row in units):
        raise RuntimeError("Every source unit must have status=frozen")
    summary_glob = cc.get("summary_glob", "CV*.txt")
    summaries = sorted(summary_dir.glob(summary_glob))
    expected_units = int(cc.get("expected_units", 126))
    expected_summaries = int(cc.get("expected_summaries", 9))
    if len(units) != expected_units:
        raise RuntimeError(f"Expected {expected_units} frozen units, found {len(units)}")
    if len(summaries) != expected_summaries:
        raise RuntimeError(f"Expected {expected_summaries} blinded summaries, found {len(summaries)}")
    if any(not path.read_text(encoding="utf-8").strip() for path in summaries):
        raise RuntimeError("At least one blinded summary is empty")
    return len(units), len(summaries), len(units) * len(summaries)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _parse_json_object(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
        raise


def run_gemini_coverage(max_batches: int | None = None) -> tuple[int, int, Path]:
    cfg, cc = _coverage_config()
    validate_coverage_setup()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")
    unit_path, summary_dir, result_dir = _paths(cc)
    units = read_csv(unit_path)
    model = cc["gemini_model"]
    safe_model = re.sub(r"[^A-Za-z0-9._-]+", "_", model)
    output = result_dir / f"gemini_coverage_scores__{safe_model}.csv"
    batch_log = result_dir / f"gemini_coverage_batch_log__{safe_model}.csv"
    completed = {
        (row["blind_id"], row["unit_id"])
        for row in read_csv(output) if row.get("status") == "success"
    }
    max_units = max(1, int(cc.get("gemini_max_units_per_batch", 15)))
    work: list[tuple[str, Path, list[dict]]] = []
    summary_glob = cc.get("summary_glob", "CV*.txt")
    policy_id = cc["policy_id"]
    for summary_path in sorted(summary_dir.glob(summary_glob)):
        blind_id = summary_path.stem
        pending = [row for row in units if (blind_id, row["unit_id"]) not in completed]
        work.extend(
            (blind_id, summary_path, pending[start:start + max_units])
            for start in range(0, len(pending), max_units)
        )

    successful = 0
    attempted = 0
    quota_reached = False
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    for blind_id, summary_path, batch_units in work:
        if max_batches is not None and attempted >= max_batches:
            break
        summary = summary_path.read_text(encoding="utf-8")
        unit_block = "\n".join(
            json.dumps({
                "unit_id": row["unit_id"],
                "information_unit": row["information_unit"],
                "material_qualifiers": row.get("material_qualifiers", ""),
            }, ensure_ascii=False)
            for row in batch_units
        )
        instruction = f"""You are evaluating INFORMATION COVERAGE in a privacy-policy summary.

Each supplied SOURCE UNIT is a proposition already verified as present and important in the original privacy policy. Judge only whether the BLINDED SUMMARY preserves that unit. Do not use outside knowledge and do not judge whether the source unit itself is true.

Scores:
- 2: The essential meaning and all material qualifiers are accurately preserved.
- 1: The core meaning is present, but a meaningful qualifier, scope, condition, duration, recipient, purpose, exception, or detail is missing or weakened.
- 0: The unit is absent, materially distorted, or contradicted.

For every unit return its unit_id, score, summary_evidence, and rationale. summary_evidence must be a short verbatim quote copied from the summary; use an empty string when score is 0 and no relevant wording exists. Keep rationales concise. Preserve every unit_id exactly. Return exactly one judgment per supplied unit.

BLINDED SUMMARY:
{summary}

SOURCE UNITS (one JSON object per line):
{unit_block}"""
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        batch_id = f"{blind_id}-{batch_units[0]['unit_id']}-{timestamp}"
        batch_result = {
            "batch_id": batch_id, "blind_id": blind_id, "model_id": model,
            "requested_units": len(batch_units), "returned_units": 0,
            "response_id": "", "timestamp_utc": timestamp, "status": "failed", "error": "",
        }
        attempted += 1
        response = None
        seen: set[str] = set()
        last_error: Exception | None = None
        attempts = 1 + int(cc.get("json_retries", 1))
        for parse_attempt in range(attempts):
            try:
                payload = {
                    "contents": [{"parts": [{"text": instruction}]}],
                    "generationConfig": {
                        "temperature": cc.get("gemini_temperature", 0.0),
                        "responseMimeType": "application/json",
                        "responseSchema": {
                            "type": "object",
                            "properties": {
                                "judgments": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "unit_id": {"type": "string"},
                                            "score": {"type": "string", "enum": ["0", "1", "2"]},
                                            "summary_evidence": {"type": "string"},
                                            "rationale": {"type": "string"},
                                        },
                                        "required": ["unit_id", "score", "summary_evidence", "rationale"],
                                    },
                                },
                            },
                            "required": ["judgments"],
                        },
                        "maxOutputTokens": int(cc.get("max_output_tokens", 8192)),
                    },
                }
                response = requests.post(
                    url, headers={"x-goog-api-key": api_key}, json=payload,
                    timeout=max(int(cc.get("timeout_seconds", cfg.get("timeout_seconds", 120))), 120),
                )
                if not response.ok:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1000]}")
                raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                parsed = _parse_json_object(raw)
                judgments = parsed.get("judgments", [])
                if not isinstance(judgments, list):
                    raise ValueError("Gemini response 'judgments' is not an array")
                expected = {row["unit_id"] for row in batch_units}
                valid: list[dict] = []
                local_seen: set[str] = set()
                for judged in judgments:
                    unit_id = str(judged.get("unit_id", "")).strip()
                    score = str(judged.get("score", "")).strip()
                    if unit_id not in expected or unit_id in local_seen or score not in {"0", "1", "2"}:
                        continue
                    local_seen.add(unit_id)
                    valid.append(judged)
                if local_seen != expected:
                    missing = sorted(expected - local_seen)
                    raise ValueError(f"Missing or invalid judgments for {len(missing)} units: {missing[:5]}")
                for judged in valid:
                    evidence = str(judged.get("summary_evidence", "")).strip()
                    append_csv(output, {
                        "blind_id": blind_id, "policy_id": policy_id,
                        "unit_id": judged["unit_id"],
                        "category": next(row["category"] for row in batch_units if row["unit_id"] == judged["unit_id"]),
                        "model_id": model, "coverage_score": judged["score"],
                        "summary_evidence": evidence,
                        "scoring_rationale": str(judged.get("rationale", "")).strip(),
                        "evidence_is_verbatim": str(bool(evidence) and _normalise(evidence) in _normalise(summary)).lower(),
                        "response_id": response.headers.get("x-request-id", ""),
                        "timestamp_utc": timestamp, "status": "success", "error": "",
                    }, COVERAGE_FIELDS)
                seen = local_seen
                successful += len(valid)
                batch_result.update({
                    "returned_units": len(valid),
                    "response_id": response.headers.get("x-request-id", ""),
                    "status": "success", "error": "",
                })
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if response is not None and response.status_code == 429:
                    quota_reached = True
                    break
                if parse_attempt + 1 < attempts:
                    time.sleep(2)
        if last_error is not None:
            batch_result["returned_units"] = len(seen)
            batch_result["error"] = f"{type(last_error).__name__}: {str(last_error).replace(api_key, '[REDACTED]')}"
        append_csv(batch_log, batch_result, COVERAGE_BATCH_FIELDS)
        print(
            f"Coverage batch {attempted}: {blind_id} "
            f"status={batch_result['status']} units={batch_result['returned_units']}/{len(batch_units)}",
            flush=True,
        )
        if quota_reached and cc.get("gemini_free_tier", True):
            print("Gemini free-tier quota reached; rerun later to resume.", flush=True)
            break
        time.sleep(float(cc.get("gemini_batch_delay_seconds", 10)))
    return successful, attempted, output
