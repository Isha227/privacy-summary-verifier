from __future__ import annotations

import csv
import json
import os
import re
import time
from pathlib import Path

import requests

from .common import ROOT, load_config, sha256_text, write_json
from .v2_statement_verifier import _normalise_whitespace, _policy_units, _quote_matches


FIELDS = [
    "policy_id", "proposer", "proposed_unit_id", "source_unit_ids",
    "exact_source_quotes", "important_information", "importance_reason",
    "qualifiers", "model_id", "evidence_verified", "status", "error",
]


def identify(policy_id: str) -> tuple[int, Path]:
    cfg = load_config()
    settings = cfg["v2_source_unit_identification"]
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")
    policy_path = ROOT / cfg["paths"]["clean"] / f"{policy_id}.txt"
    if not policy_path.exists():
        raise FileNotFoundError(f"Missing frozen policy: {policy_path}")
    policy = policy_path.read_text(encoding="utf-8").strip()
    units = _policy_units(policy)
    source_lookup = dict(units)
    source_block = "\n\n".join(f"[{unit_id}] {text}" for unit_id, text in units)
    policy_tag = f"P{int(re.search(r'(\d+)$', policy_id).group(1)):02d}"

    instruction = f"""Identify the information in this privacy policy that is important for a general adult reader with no specialist legal or privacy knowledge.

Use only the supplied policy. Do not use outside knowledge, a fixed privacy-category checklist, generated summaries, or assumptions about information that is absent.

Each proposed source unit must:
1. represent one independently assessable policy proposition;
2. be explicitly stated in the policy;
3. matter to a reader's understanding of how personal information is handled, possible effects, rights or choices;
4. preserve material entities, scope, purposes, recipients, conditions, exceptions, quantities, time periods and certainty;
5. include exact source quotation(s), their SRC identifier(s), a neutral plain-language statement, and a concise reason the information matters.

Split unrelated propositions. A unit may use multiple source sentences only when they are necessary to express one qualified proposition. Do not include decorative headings or administrative wording merely because it appears in the policy. There is no required number of units.

Return the proposed units in source order. Use sequential IDs beginning G-{policy_tag}-U001.

SOURCE POLICY:
{source_block}"""

    model = settings["model"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    schema = {
        "type": "object",
        "properties": {
            "units": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "proposed_unit_id": {"type": "string"},
                        "source_unit_ids": {"type": "array", "items": {"type": "string"}},
                        "exact_source_quotes": {"type": "array", "items": {"type": "string"}},
                        "important_information": {"type": "string"},
                        "importance_reason": {"type": "string"},
                        "qualifiers": {"type": "string"},
                    },
                    "required": [
                        "proposed_unit_id", "source_unit_ids", "exact_source_quotes",
                        "important_information", "importance_reason", "qualifiers",
                    ],
                },
            },
        },
        "required": ["units"],
    }
    payload = {
        "contents": [{"parts": [{"text": instruction}]}],
        "generationConfig": {
            "temperature": settings.get("temperature", 0.0),
            "maxOutputTokens": int(settings.get("max_output_tokens", 8192)),
            "responseMimeType": "application/json",
            "responseSchema": schema,
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
        raise RuntimeError(f"Gemini returned no candidate: {json.dumps(data, ensure_ascii=False)[:2000]}")
    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(raw_text)
    proposed = parsed.get("units", [])
    if not proposed:
        raise ValueError("Gemini returned no important source units")

    rows: list[dict] = []
    for index, unit in enumerate(proposed, 1):
        expected_id = f"G-{policy_tag}-U{index:03d}"
        if unit.get("proposed_unit_id") != expected_id:
            raise ValueError(f"Expected {expected_id}, received {unit.get('proposed_unit_id')}")
        ids = unit.get("source_unit_ids", [])
        quotes = unit.get("exact_source_quotes", [])
        verified = len(ids) == len(quotes) and bool(ids) and all(
            source_id in source_lookup and _quote_matches(source_lookup[source_id], quote)
            for source_id, quote in zip(ids, quotes)
        )
        rows.append({
            "policy_id": policy_id,
            "proposer": "Gemini",
            "proposed_unit_id": expected_id,
            "source_unit_ids": ";".join(ids),
            "exact_source_quotes": json.dumps(quotes, ensure_ascii=False),
            "important_information": unit.get("important_information", ""),
            "importance_reason": unit.get("importance_reason", ""),
            "qualifiers": unit.get("qualifiers", ""),
            "model_id": model,
            "evidence_verified": str(verified).lower(),
            "status": "success" if verified else "evidence_validation_failed",
            "error": "" if verified else "At least one source ID or exact quotation did not match the frozen policy",
        })

    output_dir = ROOT / settings["output_dir"] / policy_id
    output_dir.mkdir(parents=True, exist_ok=True)
    version = str(settings["version"])
    output_path = output_dir / f"{policy_id}_gemini_source_units_v{version}.csv"
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    response_id = response.headers.get("x-request-id", "") or data.get("responseId", "")
    write_json(output_dir / f"{policy_id}_gemini_source_units_v{version}_raw.json", {
        "policy_id": policy_id,
        "model_id": model,
        "response_id": response_id,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "policy_sha256": sha256_text(policy),
        "source_unit_scheme": "whitespace-normalised complete source sentences",
        "prompt_sha256": sha256_text(instruction),
        "units": proposed,
    })
    return len(rows), output_path
