from __future__ import annotations

import csv
import json
import os
import time

import requests

from .common import ROOT, load_config, read_csv, sha256_text, write_json
from .v2_statement_verifier import _normalise_whitespace


FIELDS = [
    "blind_id", "policy_id", "proposed_unit_id", "important_information",
    "model_id", "coverage_label", "summary_evidence", "explanation",
    "evidence_verified", "response_id", "timestamp_utc", "status", "error",
]
LABELS = {"Covered", "Partially covered", "Not covered"}


def verify_summary(blind_id: str) -> tuple[int, object]:
    cfg = load_config()
    settings = cfg["v2_coverage_verifier"]
    key = read_csv(ROOT / cfg["paths"]["anonymised"] / "BLINDING_KEY_RESTRICTED.csv")
    match = [row for row in key if row["blind_id"] == blind_id]
    if len(match) != 1:
        raise RuntimeError(f"Expected one blinding-key row for {blind_id}")
    policy_id = match[0]["policy_id"]
    summary = (ROOT / cfg["paths"]["anonymised"] / f"{blind_id}.txt").read_text(encoding="utf-8").strip()
    unit_path = ROOT / cfg["v2_source_unit_identification"]["output_dir"] / policy_id / f"{policy_id}_gemini_source_units_v{cfg['v2_source_unit_identification']['version']}.csv"
    units = [row for row in read_csv(unit_path) if row.get("status") == "success"]
    if not units:
        raise RuntimeError(f"No evidence-valid source units found for {policy_id}")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY")
    model = settings["model"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    schema = {
        "type": "object", "properties": {"judgments": {"type": "array", "items": {
            "type": "object", "properties": {
                "proposed_unit_id": {"type": "string"},
                "coverage_label": {"type": "string", "enum": sorted(LABELS)},
                "summary_evidence": {"type": "string"},
                "explanation": {"type": "string"},
            }, "required": ["proposed_unit_id", "coverage_label", "summary_evidence", "explanation"],
        }}}, "required": ["judgments"],
    }
    all_rows, audits = [], []
    batch_size = int(settings.get("max_units_per_batch", 15))
    for start in range(0, len(units), batch_size):
        batch = units[start:start + batch_size]
        unit_block = "\n".join(json.dumps({
            "proposed_unit_id": row["proposed_unit_id"],
            "important_information": row["important_information"],
            "material_qualifiers": row["qualifiers"],
        }, ensure_ascii=False) for row in batch)
        instruction = f"""Assess whether each independently identified important source-policy unit is retained in the supplied plain-English summary. Use only the unit text and summary.

Labels:
- Covered: all material meaning and qualifications are retained.
- Partially covered: the topic is present but some material meaning, scope, condition, exception or qualification is missing or weakened.
- Not covered: the important information is absent from the summary.

For Covered or Partially covered, copy an exact quotation from the summary as evidence. For Not covered, return an empty evidence string. Give a concise reason. Preserve every proposed_unit_id exactly and return every unit once in the supplied order.

SUMMARY:
{summary}

IMPORTANT SOURCE UNITS (one JSON object per line):
{unit_block}"""
        payload = {"contents": [{"parts": [{"text": instruction}]}], "generationConfig": {
            "temperature": settings.get("temperature", 0.0),
            "maxOutputTokens": int(settings.get("max_output_tokens", 8192)),
            "responseMimeType": "application/json", "responseSchema": schema,
        }}
        response = requests.post(url, headers={"x-goog-api-key": api_key}, json=payload,
                                 timeout=int(settings.get("timeout_seconds", 300)))
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1500]}")
        data = response.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        judgments = json.loads(raw).get("judgments", [])
        expected = [row["proposed_unit_id"] for row in batch]
        if [row.get("proposed_unit_id") for row in judgments] != expected:
            raise ValueError("Coverage verifier did not return every unit exactly once in order")
        response_id = response.headers.get("x-request-id", "") or data.get("responseId", "")
        lookup = {row["proposed_unit_id"]: row for row in batch}
        for judgment in judgments:
            unit_id = judgment["proposed_unit_id"]
            label = judgment.get("coverage_label")
            evidence = judgment.get("summary_evidence", "").strip()
            valid = label in LABELS and ((label == "Not covered" and not evidence) or
                    (label != "Not covered" and bool(evidence) and _normalise_whitespace(evidence) in _normalise_whitespace(summary)))
            all_rows.append({
                "blind_id": blind_id, "policy_id": policy_id, "proposed_unit_id": unit_id,
                "important_information": lookup[unit_id]["important_information"], "model_id": model,
                "coverage_label": label, "summary_evidence": evidence,
                "explanation": judgment.get("explanation", ""), "evidence_verified": str(valid).lower(),
                "response_id": response_id, "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "status": "success" if valid else "evidence_validation_failed",
                "error": "" if valid else "Coverage label/evidence did not match the frozen summary",
            })
        audits.append({"batch": len(audits)+1, "prompt_sha256": sha256_text(instruction), "response_id": response_id})
        if start + batch_size < len(units):
            time.sleep(float(settings.get("batch_delay_seconds", 3)))
    output_dir = ROOT / settings["output_dir"] / blind_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{blind_id}_gemini_coverage_v{settings['version']}.csv"
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(all_rows)
    write_json(output_dir / f"{blind_id}_gemini_coverage_v{settings['version']}_audit.json", {
        "blind_id": blind_id, "policy_id": policy_id, "model_id": model,
        "summary_sha256": sha256_text(summary), "unit_file": unit_path.relative_to(ROOT).as_posix(),
        "batches": audits,
    })
    return len(all_rows), output_path
