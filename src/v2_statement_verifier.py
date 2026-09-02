from __future__ import annotations

import csv
import json
import os
import re
import time
from pathlib import Path

import requests

from .common import ROOT, load_config, read_csv, sha256_text, write_json


FIELDS = [
    "blind_id", "statement_id", "statement_text", "model_id", "label",
    "failure_type", "evidence_unit_ids", "evidence_quotes",
    "closest_source_unit_id", "closest_source_quote", "supported_components",
    "problematic_components", "explanation", "evidence_verified",
    "response_id", "timestamp_utc", "status", "error",
]
LABELS = {"Supported", "Partially supported", "Contradicted", "Unsupported"}
FAILURES = {"None", "Hallucination", "Distortion", "Hallucination and distortion"}


def _normalise_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _quote_matches(unit_text: str, quote: str) -> bool:
    return bool(quote.strip()) and _normalise_whitespace(quote) in _normalise_whitespace(unit_text)


def _policy_units(text: str) -> list[tuple[str, str]]:
    normalised = _normalise_whitespace(text)
    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“‘])", normalised)
        if part.strip()
    ]
    return [(f"SRC{number:03d}", sentence) for number, sentence in enumerate(sentences, 1)]


def _policy_for_blind(cfg: dict, blind_id: str) -> tuple[str, str]:
    key_path = ROOT / cfg["paths"]["anonymised"] / "BLINDING_KEY_RESTRICTED.csv"
    matches = [row for row in read_csv(key_path) if row.get("blind_id") == blind_id]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one blinding-key row for {blind_id}, found {len(matches)}")
    policy_id = matches[0]["policy_id"]
    policy = (ROOT / cfg["paths"]["clean"] / f"{policy_id}.txt").read_text(encoding="utf-8").strip()
    return policy_id, policy


def verify_one(blind_id: str) -> tuple[int, Path]:
    cfg = load_config()
    settings = cfg["v2_statement_verifier"]
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")

    statement_path = (
        ROOT / cfg["v2_statements"]["output_dir"] / blind_id /
        f"{blind_id}_summary_statements_v{cfg['v2_statements']['version']}.csv"
    )
    statements = [row for row in read_csv(statement_path) if row.get("include", "yes").lower() == "yes"]
    if not statements:
        raise RuntimeError(f"No included statements found: {statement_path}")

    policy_id, policy = _policy_for_blind(cfg, blind_id)
    units = _policy_units(policy)
    valid_units = {unit_id for unit_id, _ in units}
    source_block = "\n\n".join(f"[{unit_id}]\n{text}" for unit_id, text in units)
    def build_instruction(batch: list[dict]) -> str:
        statement_block = "\n".join(json.dumps({
            "statement_id": row["statement_id"],
            "statement_text": row["statement_text"],
        }, ensure_ascii=False) for row in batch)
        return f"""You are assessing the faithfulness of plain-English privacy-policy summary statements. Use only the supplied SOURCE POLICY. Do not use outside knowledge and do not assess information omitted from the summary in this task.

Judge every statement independently.

Labels:
- Supported: every material component is supported by the source, including its conditions and level of certainty.
- Partially supported: at least one material component is supported, but another component is unsupported, overstated, imprecise or missing an important qualification.
- Contradicted: the source is materially incompatible with the statement or states the opposite.
- Unsupported: no adequate source support was located for the statement.

Failure types:
- None: use only for Supported.
- Hallucination: the statement adds a material assertion for which the source provides no adequate support.
- Distortion: the statement changes source meaning, scope, entity, action, purpose, recipient, quantity, duration, condition, exception or certainty.
- Hallucination and distortion: use only when both occur in the same statement.

Mechanical consistency requirement: if and only if the label is Supported,
failure_type must be None. Every Partially supported, Contradicted or Unsupported
judgment must use a non-None failure type. Check this pairing before returning JSON.

For evidence, copy exact quotations from one numbered source paragraph. Do not paraphrase quotations. A Supported, Partially supported or Contradicted judgment must include at least one evidence item. For Unsupported, use an empty evidence array and provide the closest relevant source passage if one exists. For every label other than Unsupported, closest_source_unit_id and closest_source_quote must be empty strings. Identify the specifically supported and problematic components. Use empty problematic_components for Supported. Keep explanations concise but sufficient to justify the label.

Return exactly one judgment for every supplied statement and preserve every statement_id.

SOURCE POLICY:
{source_block}

SUMMARY STATEMENTS (one JSON object per line):
{statement_block}"""

    model = settings["model"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    judgment_schema = {
        "type": "object",
        "properties": {
            "statement_id": {"type": "string"},
            "label": {"type": "string", "enum": sorted(LABELS)},
            "failure_type": {"type": "string", "enum": sorted(FAILURES)},
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "unit_id": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                    "required": ["unit_id", "quote"],
                },
            },
            "closest_source_unit_id": {"type": "string"},
            "closest_source_quote": {"type": "string"},
            "supported_components": {"type": "string"},
            "problematic_components": {"type": "string"},
            "explanation": {"type": "string"},
        },
        "required": [
            "statement_id", "label", "failure_type", "evidence",
            "closest_source_unit_id", "closest_source_quote", "supported_components",
            "problematic_components", "explanation",
        ],
    }
    judgments: list[dict] = []
    response_ids: dict[str, str] = {}
    prompt_hashes: list[str] = []
    batch_audit: list[dict] = []
    batch_size = max(1, int(settings.get("max_statements_per_batch", 5)))
    for start in range(0, len(statements), batch_size):
        batch = statements[start:start + batch_size]
        instruction = build_instruction(batch)
        prompt_hashes.append(sha256_text(instruction))
        payload = {
            "contents": [{"parts": [{"text": instruction}]}],
            "generationConfig": {
                "temperature": settings.get("temperature", 0.0),
                "maxOutputTokens": int(settings.get("max_output_tokens", 8192)),
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "object",
                    "properties": {
                        "judgments": {"type": "array", "items": judgment_schema},
                    },
                    "required": ["judgments"],
                },
            },
        }
        response = requests.post(
            url,
            headers={"x-goog-api-key": api_key},
            json=payload,
            timeout=int(settings.get("timeout_seconds", 300)),
        )
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1500]}")
        data = response.json()
        if not data.get("candidates"):
            diagnostic = json.dumps(data, ensure_ascii=False)[:2000]
            raise RuntimeError(f"Gemini returned no candidate: {diagnostic}")
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw_text)
        returned = parsed.get("judgments", [])
        expected_ids = [row["statement_id"] for row in batch]
        returned_ids = [row.get("statement_id") for row in returned]
        if returned_ids != expected_ids:
            raise ValueError("Verifier did not return every statement exactly once in the supplied order")
        response_id = response.headers.get("x-request-id", "") or data.get("responseId", "")
        for statement_id in expected_ids:
            response_ids[statement_id] = response_id
        judgments.extend(returned)
        batch_audit.append({
            "batch_number": len(batch_audit) + 1,
            "statement_ids": expected_ids,
            "response_id": response_id,
            "prompt_sha256": prompt_hashes[-1],
        })
        if start + batch_size < len(statements):
            time.sleep(float(settings.get("batch_delay_seconds", 3)))

    source_lookup = dict(units)
    output_rows: list[dict] = []
    for statement, judgment in zip(statements, judgments):
        label = judgment.get("label")
        failure = judgment.get("failure_type")
        if label not in LABELS or failure not in FAILURES:
            raise ValueError(f"Invalid label or failure type for {statement['statement_id']}")
        if (label == "Supported") != (failure == "None"):
            raise ValueError(f"Inconsistent label/failure type for {statement['statement_id']}")
        evidence = judgment.get("evidence", [])
        if label in {"Supported", "Partially supported", "Contradicted"} and not evidence:
            raise ValueError(f"Missing evidence for {statement['statement_id']}")
        evidence_verified = True
        for item in evidence:
            unit_id, quote = item.get("unit_id", ""), item.get("quote", "")
            if unit_id not in valid_units or not _quote_matches(source_lookup.get(unit_id, ""), quote):
                evidence_verified = False
        closest_id = judgment.get("closest_source_unit_id", "")
        closest_quote = judgment.get("closest_source_quote", "")
        if label != "Unsupported":
            closest_id, closest_quote = "", ""
        elif closest_id or closest_quote:
            if closest_id not in valid_units or not _quote_matches(source_lookup.get(closest_id, ""), closest_quote):
                evidence_verified = False
        output_rows.append({
            "blind_id": blind_id,
            "statement_id": statement["statement_id"],
            "statement_text": statement["statement_text"],
            "model_id": model,
            "label": label,
            "failure_type": failure,
            "evidence_unit_ids": ";".join(item["unit_id"] for item in evidence),
            "evidence_quotes": json.dumps([item["quote"] for item in evidence], ensure_ascii=False),
            "closest_source_unit_id": closest_id,
            "closest_source_quote": closest_quote,
            "supported_components": judgment.get("supported_components", ""),
            "problematic_components": judgment.get("problematic_components", ""),
            "explanation": judgment.get("explanation", ""),
            "evidence_verified": str(evidence_verified).lower(),
            "response_id": response_ids[statement["statement_id"]],
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "success" if evidence_verified else "evidence_validation_failed",
            "error": "" if evidence_verified else "At least one quoted span or unit ID did not match the frozen policy",
        })

    output_dir = ROOT / settings["output_dir"] / blind_id
    output_dir.mkdir(parents=True, exist_ok=True)
    version = str(settings["version"])
    output_path = output_dir / f"{blind_id}_statement_verification_v{version}.csv"
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output_rows)
    write_json(output_dir / f"{blind_id}_statement_verification_v{version}_raw.json", {
        "blind_id": blind_id,
        "policy_id": policy_id,
        "model_id": model,
        "policy_sha256": sha256_text(policy),
        "source_unit_scheme": "whitespace-normalised complete source sentences",
        "statements_sha256": sha256_text(statement_path.read_text(encoding="utf-8-sig")),
        "prompt_sha256_by_batch": prompt_hashes,
        "batches": batch_audit,
        "judgments": judgments,
    })
    return len(output_rows), output_path


def revalidate_one(blind_id: str) -> tuple[int, Path]:
    cfg = load_config()
    settings = cfg["v2_statement_verifier"]
    version = str(settings["version"])
    output_path = ROOT / settings["output_dir"] / blind_id / f"{blind_id}_statement_verification_v{version}.csv"
    rows = read_csv(output_path)
    if not rows:
        raise RuntimeError(f"No saved verification rows found: {output_path}")
    _, policy = _policy_for_blind(cfg, blind_id)
    source_lookup = dict(_policy_units(policy))
    accepted = 0
    for row in rows:
        unit_ids = [value for value in row.get("evidence_unit_ids", "").split(";") if value]
        quotes = json.loads(row.get("evidence_quotes", "[]"))
        verified = len(unit_ids) == len(quotes) and all(
            unit_id in source_lookup and _quote_matches(source_lookup[unit_id], quote)
            for unit_id, quote in zip(unit_ids, quotes)
        )
        if row.get("label") != "Unsupported":
            row["closest_source_unit_id"] = ""
            row["closest_source_quote"] = ""
        elif row.get("closest_source_unit_id") or row.get("closest_source_quote"):
            closest_id = row.get("closest_source_unit_id", "")
            verified = verified and closest_id in source_lookup and _quote_matches(
                source_lookup.get(closest_id, ""), row.get("closest_source_quote", "")
            )
        row["evidence_verified"] = str(verified).lower()
        row["status"] = "success" if verified else "evidence_validation_failed"
        row["error"] = "" if verified else "At least one quoted span or unit ID did not match the frozen policy"
        accepted += int(verified)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return accepted, output_path
