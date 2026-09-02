from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests

from .common import ROOT, append_csv, load_config, read_csv, sha256_text, write_json
from .v2_statement_verifier import _policy_units


POLICIES = ["PILOT01", "PILOT02", "PILOT03"]
FIELDS = [
    "policy_id", "candidate_unit_id", "important_information", "importance_reason",
    "material_qualifiers", "source_passage_ids", "exact_source_evidence", "model_id",
    "prompt_sha256", "policy_sha256", "status", "error",
]
LOG_FIELDS = [
    "policy_id", "model_id", "requested", "returned", "response_id",
    "timestamp_utc", "status", "error",
]


def _settings() -> tuple[dict, dict]:
    cfg = load_config()
    settings = cfg.get("contemporary_source_unit_validation")
    if not settings:
        raise RuntimeError("The selected configuration has no contemporary_source_unit_validation section")
    return cfg, settings


def _paths(settings: dict, prompt_version: str = "v2") -> dict[str, Path]:
    base = ROOT / settings["output_dir"]
    version_dir = f"gemini_{prompt_version}"
    return {
        "base": base,
        "by_policy": base / version_dir / "by_policy",
        "log": base / version_dir / "source_unit_generation_log.csv",
        "frozen": base / version_dir / "frozen_gemini_source_units.csv",
        "manifest": base / version_dir / "frozen_gemini_source_units_manifest.json",
    }


def _api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")
    return key


def _instruction(policy_id: str, source_block: str, prompt_version: str = "v2") -> str:
    if prompt_version == "v2":
        return f"""Identify the information in this privacy policy that is important for an ordinary adult reader with no specialist legal, technical or privacy knowledge.

Use only the supplied policy. Do not use outside knowledge, generated summaries, human-created source units, the OPP-115 taxonomy, or any other fixed privacy-category checklist. Do not invent topics that the policy does not contain.

Each proposed source unit must:
1. express one independently assessable proposition explicitly present in the policy;
2. help the reader understand how personal information is handled, possible effects, rights or choices;
3. preserve material actors, data types, purposes, recipients, conditions, exceptions, quantities, time periods and levels of certainty;
4. cite the smallest sufficient set of supplied source passage IDs;
5. include a neutral plain-English statement, a concise importance reason and any material qualifiers.

Split unrelated propositions. Combine passages only when necessary to express one qualified proposition. Exclude navigation text, decorative headings and administrative wording that does not materially help the reader. There is no required number of units. Return units in source order.

SOURCE POLICY {policy_id}:
{source_block}"""

    if prompt_version != "v3":
        raise ValueError(f"Unsupported prompt version: {prompt_version}")

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


def identify(policy_id: str, prompt_version: str = "v2") -> tuple[int, Path]:
    if policy_id not in POLICIES:
        raise ValueError(f"Choose one of {POLICIES}")
    cfg, settings = _settings()
    paths = _paths(settings, prompt_version)
    destination = paths["by_policy"] / f"{policy_id}_gemini_source_units_{prompt_version}.csv"
    existing = read_csv(destination)
    if existing and all(row.get("status") == "success" for row in existing):
        return len(existing), destination

    policy_path = ROOT / cfg["paths"]["clean"] / f"{policy_id}.txt"
    policy = policy_path.read_text(encoding="utf-8").strip()
    passages = _policy_units(policy)
    source_lookup = dict(passages)
    source_block = "\n\n".join(f"[{source_id}] {text}" for source_id, text in passages)
    instruction = _instruction(policy_id, source_block, prompt_version)
    model = settings["model"]
    schema = {
        "type": "object", "properties": {"units": {"type": "array", "items": {
            "type": "object", "properties": {
                "source_passage_ids": {"type": "array", "items": {
                    "type": "string", "enum": list(source_lookup),
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
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    log_row = {
        "policy_id": policy_id, "model_id": model, "requested": 1, "returned": 0,
        "response_id": "", "timestamp_utc": timestamp, "status": "failed", "error": "",
    }
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        response = requests.post(
            url, headers={"x-goog-api-key": _api_key()},
            json={
                "contents": [{"parts": [{"text": instruction}]}],
                "generationConfig": {
                    "temperature": float(settings.get("temperature", 0.0)),
                    "maxOutputTokens": int(settings.get("max_output_tokens", 32768)),
                    "responseMimeType": "application/json", "responseSchema": schema,
                },
            }, timeout=int(settings.get("timeout_seconds", 600)),
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
        proposed = json.loads(raw).get("units", [])
        if not isinstance(proposed, list) or not proposed:
            raise ValueError("Gemini returned no source units")

        rows = []
        seen_information = set()
        short_id = policy_id.replace("PILOT", "P")
        id_version = "GV2" if prompt_version == "v2" else "GV3"
        for index, unit in enumerate(proposed, 1):
            evidence_ids = list(dict.fromkeys(
                str(item).strip() for item in unit.get("source_passage_ids", []) if str(item).strip()
            ))
            information = str(unit.get("important_information", "")).strip()
            reason = str(unit.get("importance_reason", "")).strip()
            if not evidence_ids or any(item not in source_lookup for item in evidence_ids):
                raise ValueError(f"Unit {index} has missing or invalid source passage IDs")
            if not information or not reason:
                raise ValueError(f"Unit {index} has blank required text")
            normalised = re.sub(r"\s+", " ", information).casefold()
            if normalised in seen_information:
                raise ValueError(f"Duplicate important-information unit at position {index}")
            seen_information.add(normalised)
            rows.append({
                "policy_id": policy_id, "candidate_unit_id": f"{id_version}-{short_id}-U{index:03d}",
                "important_information": information, "importance_reason": reason,
                "material_qualifiers": str(unit.get("material_qualifiers", "")).strip(),
                "source_passage_ids": ";".join(evidence_ids),
                "exact_source_evidence": "\n---\n".join(source_lookup[item] for item in evidence_ids),
                "model_id": model, "prompt_sha256": sha256_text(instruction),
                "policy_sha256": sha256_text(policy), "status": "success", "error": "",
            })
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader(); writer.writerows(rows)
        response_id = response.headers.get("x-request-id", "") or data.get("responseId", "")
        write_json(destination.with_suffix(".audit.json"), {
            "policy_id": policy_id, "model_id": model, "response_id": response_id,
            "timestamp_utc": timestamp, "units": len(rows),
            "policy_sha256": sha256_text(policy), "prompt_sha256": sha256_text(instruction),
            "summaries_visible": False, "human_units_visible": False, "taxonomy_visible": False,
            "prompt_version": prompt_version,
            "source_evidence_retrieved_by_program": True,
        })
        log_row.update({"returned": len(rows), "response_id": response_id, "status": "success"})
    except Exception as exc:
        log_row["error"] = f"{type(exc).__name__}: {exc}"
    append_csv(paths["log"], log_row, LOG_FIELDS)
    if log_row["status"] != "success":
        raise RuntimeError(log_row["error"])
    return log_row["returned"], destination


def status(prompt_version: str = "v2") -> dict:
    _, settings = _settings()
    paths = _paths(settings, prompt_version)
    counts = {}
    for policy_id in POLICIES:
        rows = read_csv(paths["by_policy"] / f"{policy_id}_gemini_source_units_{prompt_version}.csv")
        counts[policy_id] = len(rows) if rows and all(row.get("status") == "success" for row in rows) else 0
    return {
        "completed_policies": sum(count > 0 for count in counts.values()),
        "expected_policies": 3, "prompt_version": prompt_version,
        "units_by_policy": counts, "total_units": sum(counts.values()),
    }


def freeze(prompt_version: str = "v2") -> dict:
    _, settings = _settings()
    paths = _paths(settings, prompt_version)
    all_rows = []
    for policy_id in POLICIES:
        rows = read_csv(paths["by_policy"] / f"{policy_id}_gemini_source_units_{prompt_version}.csv")
        if not rows or any(row.get("status") != "success" for row in rows):
            raise RuntimeError(f"Valid Gemini {prompt_version} units are incomplete for {policy_id}")
        id_version = "GV2" if prompt_version == "v2" else "GV3"
        expected = [f"{id_version}-{policy_id.replace('PILOT', 'P')}-U{i:03d}" for i in range(1, len(rows) + 1)]
        if [row["candidate_unit_id"] for row in rows] != expected:
            raise ValueError(f"Non-contiguous candidate IDs for {policy_id}")
        all_rows.extend(rows)
    if len({row["candidate_unit_id"] for row in all_rows}) != len(all_rows):
        raise ValueError("Duplicate Gemini candidate unit IDs")
    paths["frozen"].parent.mkdir(parents=True, exist_ok=True)
    with paths["frozen"].open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(all_rows)
    manifest = {
        "status": "frozen_before_researcher_comparison", "policies": 3,
        "prompt_version": prompt_version,
        "units": len(all_rows), "units_by_policy": {
            policy_id: sum(row["policy_id"] == policy_id for row in all_rows) for policy_id in POLICIES
        },
        "sha256": hashlib.sha256(paths["frozen"].read_bytes()).hexdigest(),
        "summaries_used": False, "human_units_used": False, "taxonomy_used": False,
    }
    write_json(paths["manifest"], manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Contemporary independent Gemini source-unit validation")
    parser.add_argument("--prompt-version", choices=["v2", "v3"], default="v2")
    sub = parser.add_subparsers(dest="command", required=True)
    identify_parser = sub.add_parser("identify"); identify_parser.add_argument("--policy-id", choices=POLICIES)
    sub.add_parser("status"); sub.add_parser("freeze")
    args = parser.parse_args()
    if args.command == "identify":
        targets = [args.policy_id] if args.policy_id else POLICIES
        result = {}
        for policy_id in targets:
            count, path = identify(policy_id, args.prompt_version)
            result[policy_id] = {"units": count, "path": str(path)}
            time.sleep(10)
    elif args.command == "status": result = status(args.prompt_version)
    else: result = freeze(args.prompt_version)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
