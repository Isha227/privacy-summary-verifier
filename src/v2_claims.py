from __future__ import annotations

import csv
import json
import os
import re
import time
from pathlib import Path

import requests

from .common import ROOT, load_config, sha256_text, write_json


REVIEW_FIELDS = [
    "blind_id", "claim_id", "source_sentence_id", "claim_text",
    "review_decision", "review_notes",
]


def _number_sentences(text: str) -> list[tuple[str, str]]:
    parts = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+|\n+", text)
        if part.strip()
    ]
    return [(f"SENT{number:03d}", sentence) for number, sentence in enumerate(parts, 1)]


def decompose_one(blind_id: str) -> tuple[int, Path]:
    cfg = load_config()
    settings = cfg["v2_atomic_claims"]
    version = str(settings.get("decomposition_version", "1.0"))
    summary_path = ROOT / cfg["paths"]["anonymised"] / f"{blind_id}.txt"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing blinded summary: {summary_path}")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")

    summary = summary_path.read_text(encoding="utf-8").strip()
    numbered = _number_sentences(summary)
    numbered_text = "\n".join(f"{sid}: {sentence}" for sid, sentence in numbered)
    template_path = ROOT / settings["prompt_template"]
    template = template_path.read_text(encoding="utf-8")
    prompt = template.replace("{{SUMMARY_ID}}", blind_id).replace("{{SUMMARY_TEXT}}", numbered_text)

    model = settings["model"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": settings.get("temperature", 0.0),
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "object",
                "properties": {
                    "summary_id": {"type": "string"},
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "claim_id": {"type": "string"},
                                "source_sentence_id": {"type": "string"},
                                "claim_text": {"type": "string"},
                            },
                            "required": ["claim_id", "source_sentence_id", "claim_text"],
                        },
                    },
                },
                "required": ["summary_id", "claims"],
            },
        },
    }
    response = requests.post(
        url,
        headers={"x-goog-api-key": api_key},
        json=payload,
        timeout=int(settings.get("timeout_seconds", cfg["timeout_seconds"])),
    )
    response.raise_for_status()
    data = response.json()
    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    result = json.loads(raw_text)

    if result.get("summary_id") != blind_id:
        raise ValueError(f"Returned summary_id does not match {blind_id}")
    claims = result.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError("No atomic claims returned")

    valid_sentence_ids = {sid for sid, _ in numbered}
    for index, claim in enumerate(claims, 1):
        expected = f"{blind_id}-C{index:03d}"
        if claim.get("claim_id") != expected:
            raise ValueError(f"Expected claim_id {expected}, received {claim.get('claim_id')}")
        if claim.get("source_sentence_id") not in valid_sentence_ids:
            raise ValueError(f"Invalid source sentence ID: {claim.get('source_sentence_id')}")
        if not str(claim.get("claim_text", "")).strip():
            raise ValueError(f"Empty claim text: {expected}")

    output_dir = ROOT / settings["output_dir"] / blind_id
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / f"{blind_id}_atomic_claims_v{version}_raw.json"
    review_path = output_dir / f"{blind_id}_atomic_claims_v{version}_review.csv"
    audit = {
        "blind_id": blind_id,
        "decomposition_version": version,
        "model": model,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary_sha256": sha256_text(summary),
        "prompt_sha256": sha256_text(template),
        "source_sentences": [{"sentence_id": sid, "text": text} for sid, text in numbered],
        "claims": claims,
        "response_id": response.headers.get("x-request-id", ""),
    }
    write_json(raw_path, audit)
    with review_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        for claim in claims:
            writer.writerow({
                "blind_id": blind_id,
                "claim_id": claim["claim_id"],
                "source_sentence_id": claim["source_sentence_id"],
                "claim_text": claim["claim_text"],
                "review_decision": "",
                "review_notes": "",
            })
    return len(claims), review_path
