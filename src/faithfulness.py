from __future__ import annotations

import csv
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

import requests

from .common import ROOT, append_csv, load_config, read_csv


CLAIM_FIELDS = ["blind_id", "claim_id", "claim_text", "include", "review_notes"]
HUMAN_FIELDS = [
    "blind_id", "claim_id", "claim_text", "label", "evidence_quote",
    "evidence_location", "annotator_notes",
]
GEMINI_FIELDS = [
    "blind_id", "claim_id", "model_id", "label", "evidence_quote",
    "explanation", "response_id", "timestamp_utc", "status", "error",
]
MINICHECK_FIELDS = [
    "blind_id", "claim_id", "model_id", "predicted_supported",
    "support_probability", "status", "error",
]
GEMINI_BATCH_FIELDS = [
    "batch_id", "blind_id", "model_id", "requested_claims", "returned_claims",
    "response_id", "timestamp_utc", "status", "error",
]


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _sentence_candidates(text: str) -> list[str]:
    """Create reproducible sentence-level candidates; humans still approve inclusion."""
    candidates: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*+] |\d+[.)]\s+)", "", raw_line).strip()
        line = re.sub(r"^#{1,6}\s+", "", line).strip()
        if not line or len(line.split()) < 3:
            continue
        # Heading-like fragments without terminal punctuation are not factual claims.
        if not re.search(r"[.!?]$", line) and len(line.split()) <= 8:
            continue
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", line)
        candidates.extend(part.strip() for part in parts if len(part.split()) >= 3)
    return candidates


def _blind_mapping(cfg: dict) -> dict[str, str]:
    """Map blind IDs to policy IDs, supporting both pilot and main-study layouts."""
    fc = cfg["faithfulness"]
    if fc.get("blinding_key"):
        rows = read_csv(ROOT / fc["blinding_key"])
        mapping = {row["blind_id"]: row["policy_id"] for row in rows}
        if not mapping:
            raise RuntimeError("The configured blinding key is empty")
        return mapping
    return {blind_id: fc["policy_id"] for blind_id in fc["blind_ids"]}


def _blind_ids(cfg: dict) -> list[str]:
    configured = cfg["faithfulness"].get("blind_ids", [])
    if configured == "all":
        return sorted(_blind_mapping(cfg))
    return list(configured)


def _source_for_blind(cfg: dict, blind_id: str) -> str:
    mapping = _blind_mapping(cfg)
    if blind_id not in mapping:
        raise KeyError(f"No policy mapping for blind ID {blind_id}")
    path = ROOT / cfg["paths"]["clean"] / f"{mapping[blind_id]}.txt"
    return path.read_text(encoding="utf-8")


def _numbered_source_passages(source: str) -> tuple[str, dict[str, str]]:
    """Give each non-empty source line a stable ID while retaining its exact text."""
    passages = [line.strip() for line in source.splitlines() if line.strip()]
    mapping = {f"SRC{number:04d}": passage for number, passage in enumerate(passages, 1)}
    numbered = "\n".join(f"[{source_id}] {passage}" for source_id, passage in mapping.items())
    return numbered, mapping


def prepare() -> tuple[int, Path]:
    cfg = load_config()
    fc = cfg["faithfulness"]
    destination = ROOT / fc["prepared_dir"]
    destination.mkdir(parents=True, exist_ok=True)
    claim_rows: list[dict] = []
    for blind_id in _blind_ids(cfg):
        summary_path = ROOT / cfg["paths"]["anonymised"] / f"{blind_id}.txt"
        if not summary_path.exists():
            raise FileNotFoundError(f"Missing blinded summary: {summary_path}")
        claims = _sentence_candidates(summary_path.read_text(encoding="utf-8"))
        for number, claim in enumerate(claims, 1):
            claim_rows.append({
                "blind_id": blind_id,
                "claim_id": f"{blind_id}-C{number:03d}",
                "claim_text": claim,
                "include": "yes",
                "review_notes": "",
            })
    claims_path = destination / "claim_candidates.csv"
    _write_csv(claims_path, CLAIM_FIELDS, claim_rows)
    if fc.get("create_human_templates", True):
        freeze_human_templates()
    return len(claim_rows), claims_path


def freeze_human_templates() -> int:
    """Create identical blank A1/A2/A3 files from the reviewed included claims."""
    cfg = load_config()
    destination = ROOT / cfg["faithfulness"]["prepared_dir"]
    approved = _approved_claims()
    rows = [{**row, "label": "", "evidence_quote": "", "evidence_location": "", "annotator_notes": ""}
            for row in approved]
    for annotator in ("A1", "A2", "A3"):
        path = destination / f"human_faithfulness_{annotator}.csv"
        if path.exists() and any(r.get("label", "").strip() for r in read_csv(path)):
            raise RuntimeError(f"Refusing to overwrite scored file: {path}")
        _write_csv(path, HUMAN_FIELDS, rows)
    return len(approved)


def _approved_claims() -> list[dict]:
    cfg = load_config()
    path = ROOT / cfg["faithfulness"]["prepared_dir"] / "claim_candidates.csv"
    rows = read_csv(path)
    return [row for row in rows if row.get("include", "yes").strip().lower() == "yes"]


def run_gemini() -> int:
    cfg = load_config()
    fc = cfg["faithfulness"]
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")
    model = fc["gemini_model"]
    safe_model = re.sub(r"[^A-Za-z0-9._-]+", "_", model)
    output = ROOT / fc["results_dir"] / f"gemini_claim_scores__{safe_model}.csv"
    completed = {(r["blind_id"], r["claim_id"]) for r in read_csv(output) if r.get("status") == "success"}
    count = 0
    for row in _approved_claims():
        key_pair = (row["blind_id"], row["claim_id"])
        if key_pair in completed:
            continue
        source = _source_for_blind(cfg, row["blind_id"])
        instruction = f"""You are a grounded faithfulness evaluator. Judge only whether the CLAIM is supported by the SOURCE. Do not use outside knowledge.

Labels:
- Supported: every material part is directly supported.
- Partially supported: some material content is supported, but part is missing, overstated, or imprecise.
- Unsupported: the source does not provide evidence for the claim.
- Contradicted: the source states the opposite or is materially incompatible.

Return only JSON with keys label, evidence_quote, explanation. The label must be one of the four labels. Keep evidence_quote short and copy it from the source; use an empty string if no evidence exists.

SOURCE:
{source}

CLAIM:
{row['claim_text']}"""
        result = {"blind_id": row["blind_id"], "claim_id": row["claim_id"], "model_id": model,
                  "label": "", "evidence_quote": "", "explanation": "", "response_id": "",
                  "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "status": "failed", "error": ""}
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            payload = {
                "contents": [{"parts": [{"text": instruction}]}],
                "generationConfig": {"temperature": fc.get("gemini_temperature", 0.0), "responseMimeType": "application/json"},
            }
            # Keep credentials out of URLs because requests includes URLs in exception text.
            response = None
            attempts = 1 if fc.get("gemini_free_tier", True) else 6
            for attempt in range(attempts):
                response = requests.post(url, headers={"x-goog-api-key": key}, json=payload, timeout=cfg["timeout_seconds"])
                if response.status_code not in (429, 503):
                    break
                if attempt == attempts - 1:
                    break
                retry_after = response.headers.get("retry-after")
                delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else min(60, 5 * (2 ** attempt))
                time.sleep(delay)
            response.raise_for_status()
            data = response.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            judged = json.loads(raw)
            if judged.get("label") not in fc["human_labels"]:
                raise ValueError(f"Invalid label: {judged.get('label')}")
            result.update({"label": judged["label"], "evidence_quote": judged.get("evidence_quote", ""),
                           "explanation": judged.get("explanation", ""), "response_id": response.headers.get("x-request-id", ""),
                           "status": "success"})
        except Exception as exc:
            safe_error = str(exc).replace(key, "[REDACTED]")
            result["error"] = f"{type(exc).__name__}: {safe_error}"
        append_csv(output, result, GEMINI_FIELDS)
        count += 1
        if response is not None and response.status_code == 429 and fc.get("gemini_free_tier", True):
            print("Gemini free-tier quota reached; stopping after the first HTTP 429.")
            break
        # Conservative pacing avoids exhausting request-per-minute quotas.
        time.sleep(3)
    return count


def run_gemini_batched(max_batches: int | None = None) -> tuple[int, int, Path]:
    """Evaluate all pending claims for each blinded summary in one Gemini request."""
    cfg = load_config()
    fc = cfg["faithfulness"]
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")
    model = fc["gemini_model"]
    safe_model = re.sub(r"[^A-Za-z0-9._-]+", "_", model)
    evaluator_version = re.sub(r"[^A-Za-z0-9._-]+", "_", str(fc.get("gemini_evaluator_version", "")))
    version_suffix = f"__{evaluator_version}" if evaluator_version else ""
    result_dir = ROOT / fc["results_dir"]
    output = result_dir / f"gemini_claim_scores_batched__{safe_model}{version_suffix}.csv"
    batch_log = result_dir / f"gemini_batch_log__{safe_model}{version_suffix}.csv"
    completed = {
        (row["blind_id"], row["claim_id"])
        for row in read_csv(output) if row.get("status") == "success"
    }

    grouped: dict[str, list[dict]] = {}
    for row in _approved_claims():
        if (row["blind_id"], row["claim_id"]) not in completed:
            grouped.setdefault(row["blind_id"], []).append(row)

    successful_claims = 0
    attempted_batches = 0
    labels = set(fc["human_labels"])
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    max_claims = max(1, int(fc.get("gemini_max_claims_per_batch", 1000000)))
    work: list[tuple[str, list[dict]]] = []
    for blind_id in sorted(grouped):
        pending = grouped[blind_id]
        work.extend(
            (blind_id, pending[start:start + max_claims])
            for start in range(0, len(pending), max_claims)
        )

    for blind_id, claims in work:
        if max_batches is not None and attempted_batches >= max_batches:
            break
        source = _source_for_blind(cfg, blind_id)
        evidence_mode = fc.get("evidence_reference_mode", "verbatim_quote")
        numbered_source, source_passages = _numbered_source_passages(source)
        source_for_prompt = numbered_source if evidence_mode == "source_passage_ids" else source
        claim_block = "\n".join(
            json.dumps({"claim_id": row["claim_id"], "claim_text": row["claim_text"]}, ensure_ascii=False)
            for row in claims
        )
        evidence_instruction = (
            f"""For evidence, return evidence_ids as an array containing zero to {int(fc.get('gemini_max_evidence_passages', 3))} SOURCE passage IDs. Use only IDs shown in the SOURCE, such as SRC0001. Select the smallest set of passages needed to justify the label. Use an empty array only for an Unsupported claim when no source evidence exists. Do not write or paraphrase evidence text; the program will retrieve the exact source passages from the IDs."""
            if evidence_mode == "source_passage_ids"
            else "The evidence_quote must be one short, continuous passage copied verbatim from the SOURCE."
        )
        evidence_field = "evidence_ids" if evidence_mode == "source_passage_ids" else "evidence_quote"
        instruction = f"""You are a grounded faithfulness evaluator. Judge every CLAIM independently using only the SOURCE. Do not use outside knowledge.

Labels:
- Supported: every material part is directly supported.
- Partially supported: some material content is supported, but part is missing, overstated, or imprecise.
- Unsupported: the source does not provide evidence for the claim.
- Contradicted: the source states the opposite or is materially incompatible.

Return only one JSON object with key \"judgments\". Its value must be an array containing exactly one object for every supplied claim. Each object must contain claim_id, label, {evidence_field}, and explanation.

{evidence_instruction} Keep each explanation concise. Preserve every claim_id exactly.

SOURCE:
{source_for_prompt}

CLAIMS (one JSON object per line):
{claim_block}"""
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        batch_id = f"{blind_id}-{timestamp}"
        response = None
        batch_result = {
            "batch_id": batch_id, "blind_id": blind_id, "model_id": model,
            "requested_claims": len(claims), "returned_claims": 0,
            "response_id": "", "timestamp_utc": timestamp, "status": "failed", "error": "",
        }
        attempted_batches += 1
        seen: set[str] = set()
        invalid_reasons: dict[str, str] = {}
        try:
            payload = {
                "contents": [{"parts": [{"text": instruction}]}],
                "generationConfig": {
                    "temperature": fc.get("gemini_temperature", 0.0),
                    "responseMimeType": "application/json",
                    "responseSchema": {
                        "type": "object",
                        "properties": {
                            "judgments": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "claim_id": {"type": "string"},
                                        "label": {
                                            "type": "string",
                                            "enum": [
                                                "Supported", "Partially supported",
                                                "Unsupported", "Contradicted",
                                            ],
                                        },
                                        **(
                                            {
                                                "evidence_ids": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "string",
                                                        "enum": list(source_passages),
                                                    },
                                                }
                                            }
                                            if evidence_mode == "source_passage_ids"
                                            else {"evidence_quote": {"type": "string"}}
                                        ),
                                        "explanation": {"type": "string"},
                                    },
                                    "required": [
                                        "claim_id", "label", evidence_field, "explanation",
                                    ],
                                },
                            },
                        },
                        "required": ["judgments"],
                    },
                    "maxOutputTokens": 16384,
                },
            }
            response = requests.post(
                url, headers={"x-goog-api-key": api_key}, json=payload,
                timeout=max(cfg["timeout_seconds"], 300),
            )
            if not response.ok:
                detail = response.text[:1000]
                raise RuntimeError(f"HTTP {response.status_code}: {detail}")
            data = response.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S)
            parsed = json.loads(raw)
            judgments = parsed.get("judgments", [])
            if not isinstance(judgments, list):
                raise ValueError("Gemini response 'judgments' is not an array")
            expected = {row["claim_id"] for row in claims}
            for judged in judgments:
                claim_id = str(judged.get("claim_id", ""))
                label = judged.get("label")
                if claim_id not in expected:
                    continue
                if claim_id in seen:
                    invalid_reasons[claim_id] = "duplicate judgment"
                    continue
                if label not in labels:
                    invalid_reasons[claim_id] = f"invalid label: {label}"
                    continue
                if evidence_mode == "source_passage_ids":
                    evidence_ids = judged.get("evidence_ids", [])
                    if not isinstance(evidence_ids, list):
                        invalid_reasons[claim_id] = "evidence_ids is not an array"
                        continue
                    evidence_ids = list(dict.fromkeys(str(item).strip() for item in evidence_ids if str(item).strip()))
                    if len(evidence_ids) > int(fc.get("gemini_max_evidence_passages", 3)):
                        invalid_reasons[claim_id] = f"too many evidence IDs: {len(evidence_ids)}"
                        continue
                    if any(item not in source_passages for item in evidence_ids):
                        invalid_reasons[claim_id] = "unknown evidence ID"
                        continue
                    if label != "Unsupported" and not evidence_ids:
                        invalid_reasons[claim_id] = "non-Unsupported label has no evidence ID"
                        continue
                    evidence_texts = list(dict.fromkeys(source_passages[item] for item in evidence_ids))
                    evidence_quote = "\n---\n".join(evidence_texts)
                else:
                    evidence_quote = str(judged.get("evidence_quote", "")).strip()
                    if fc.get("require_exact_evidence_quote", False):
                        if label != "Unsupported" and not evidence_quote:
                            continue
                        if evidence_quote and evidence_quote not in source:
                            continue
                append_csv(output, {
                    "blind_id": blind_id, "claim_id": claim_id, "model_id": model,
                    "label": label, "evidence_quote": evidence_quote,
                    "explanation": judged.get("explanation", ""),
                    "response_id": response.headers.get("x-request-id", ""),
                    "timestamp_utc": timestamp, "status": "success", "error": "",
                }, GEMINI_FIELDS)
                seen.add(claim_id)
                successful_claims += 1
            if seen != expected:
                missing = sorted(expected - seen)
                details = {claim_id: invalid_reasons.get(claim_id, "missing from response") for claim_id in missing[:5]}
                raise ValueError(f"Missing or invalid judgments for {len(missing)} claims: {details}")
            batch_result.update({
                "returned_claims": len(seen),
                "response_id": response.headers.get("x-request-id", ""),
                "status": "success",
            })
        except Exception as exc:
            batch_result["returned_claims"] = len(seen)
            batch_result["error"] = f"{type(exc).__name__}: {str(exc).replace(api_key, '[REDACTED]')}"
        append_csv(batch_log, batch_result, GEMINI_BATCH_FIELDS)
        print(
            f"Gemini batch {attempted_batches}: {blind_id} "
            f"status={batch_result['status']} claims={batch_result['returned_claims']}/{len(claims)}",
            flush=True,
        )
        if response is not None and response.status_code == 429 and fc.get("gemini_free_tier", True):
            print("Gemini free-tier quota reached; rerun later to resume.", flush=True)
            break
        time.sleep(fc.get("gemini_batch_delay_seconds", 10))
    return successful_claims, attempted_batches, output


def run_minicheck() -> int:
    cfg = load_config()
    fc = cfg["faithfulness"]
    try:
        from minicheck.minicheck import MiniCheck
    except ImportError as exc:
        raise RuntimeError("MiniCheck is not installed. Follow docs/faithfulness_protocol.md.") from exc
    claims = _approved_claims()
    model = fc["minicheck_model"]
    destination = ROOT / fc["results_dir"] / "minicheck_claim_scores.csv"
    scorer = MiniCheck(model_name=model, cache_dir=str(ROOT / ".model_cache" / "minicheck"))
    labels, probabilities, _, _ = scorer.score(
        docs=[_source_for_blind(cfg, row["blind_id"]) for row in claims],
        claims=[row["claim_text"] for row in claims],
    )
    rows = [{"blind_id": row["blind_id"], "claim_id": row["claim_id"], "model_id": model,
             "predicted_supported": int(label), "support_probability": float(probability), "status": "success", "error": ""}
            for row, label, probability in zip(claims, labels, probabilities)]
    _write_csv(destination, MINICHECK_FIELDS, rows)
    return len(rows)


def validate_human() -> int:
    cfg = load_config()
    fc = cfg["faithfulness"]
    expected = {(r["blind_id"], r["claim_id"]) for r in _approved_claims()}
    labels = set(fc["human_labels"])
    errors: list[str] = []
    for annotator in ("A1", "A2", "A3"):
        path = ROOT / fc["prepared_dir"] / f"human_faithfulness_{annotator}.csv"
        rows = read_csv(path)
        observed = {(r["blind_id"], r["claim_id"]) for r in rows}
        if observed != expected:
            errors.append(f"{annotator}: claim rows do not match approved claims")
        for row in rows:
            if row.get("label", "").strip() not in labels:
                errors.append(f"{annotator}: invalid/blank label at {row.get('claim_id')}")
            if not row.get("evidence_location", "").strip():
                errors.append(f"{annotator}: missing evidence location at {row.get('claim_id')}")
    if errors:
        raise ValueError("\n".join(errors[:30]))
    return len(expected) * 3


def _cohen_kappa(left: list[str], right: list[str], labels: list[str]) -> float:
    n = len(left)
    observed = sum(a == b for a, b in zip(left, right)) / n
    lc, rc = Counter(left), Counter(right)
    expected = sum((lc[label] / n) * (rc[label] / n) for label in labels)
    return 1.0 if expected == 1.0 else (observed - expected) / (1.0 - expected)


def analyse_human_agreement() -> tuple[int, int, Path]:
    validate_human()
    cfg = load_config()
    fc = cfg["faithfulness"]
    base = ROOT / fc["prepared_dir"]
    ratings = {a: {(r["blind_id"], r["claim_id"]): r for r in read_csv(base / f"human_faithfulness_{a}.csv")}
               for a in ("A1", "A2", "A3")}
    keys = sorted(ratings["A1"])
    disagreements: list[dict] = []
    unanimous = 0
    for key in keys:
        rows = [ratings[a][key] for a in ("A1", "A2", "A3")]
        labels = [r["label"] for r in rows]
        if len(set(labels)) == 1:
            unanimous += 1
            continue
        disagreements.append({
            "blind_id": key[0], "claim_id": key[1], "claim_text": rows[0]["claim_text"],
            "A1_label": labels[0], "A1_evidence": rows[0]["evidence_quote"], "A1_location": rows[0]["evidence_location"],
            "A2_label": labels[1], "A2_evidence": rows[1]["evidence_quote"], "A2_location": rows[1]["evidence_location"],
            "A3_label": labels[2], "A3_evidence": rows[2]["evidence_quote"], "A3_location": rows[2]["evidence_location"],
            "final_label": "", "adjudication_evidence": "", "adjudication_location": "", "adjudication_notes": "",
        })
    result_dir = ROOT / fc["results_dir"]
    disagreement_path = result_dir / "human_disagreements_blinded.csv"
    fields = list(disagreements[0]) if disagreements else ["blind_id", "claim_id", "claim_text", "final_label", "adjudication_notes"]
    _write_csv(disagreement_path, fields, disagreements)
    labels = fc["human_labels"]
    pairs = []
    for left, right in (("A1", "A2"), ("A1", "A3"), ("A2", "A3")):
        kappa = _cohen_kappa([ratings[left][k]["label"] for k in keys], [ratings[right][k]["label"] for k in keys], labels)
        pairs.append({"measure": f"Cohen kappa {left}-{right}", "value": round(kappa, 4), "numerator": "", "denominator": ""})
    summary = [
        {"measure": "claims", "value": len(keys), "numerator": "", "denominator": ""},
        {"measure": "unanimous claims", "value": unanimous, "numerator": unanimous, "denominator": len(keys)},
        {"measure": "unanimous agreement percent", "value": round(100 * unanimous / len(keys), 2), "numerator": unanimous, "denominator": len(keys)},
        {"measure": "claims requiring adjudication", "value": len(disagreements), "numerator": len(disagreements), "denominator": len(keys)},
        *pairs,
    ]
    _write_csv(result_dir / "human_agreement_summary.csv", ["measure", "value", "numerator", "denominator"], summary)
    return unanimous, len(disagreements), disagreement_path


def finalise_human() -> tuple[int, Path, Path]:
    validate_human()
    cfg = load_config()
    fc = cfg["faithfulness"]
    base = ROOT / fc["prepared_dir"]
    result_dir = ROOT / fc["results_dir"]
    ratings = {a: {(r["blind_id"], r["claim_id"]): r for r in read_csv(base / f"human_faithfulness_{a}.csv")}
               for a in ("A1", "A2", "A3")}
    adjudicated_rows = read_csv(result_dir / "human_disagreements_blinded.csv")
    adjudicated = {(r["blind_id"], r["claim_id"]): r for r in adjudicated_rows}
    valid_labels = set(fc["human_labels"])
    final_rows: list[dict] = []
    for key in sorted(ratings["A1"]):
        source_rows = [ratings[a][key] for a in ("A1", "A2", "A3")]
        source_labels = [r["label"] for r in source_rows]
        if len(set(source_labels)) == 1:
            final_label = source_labels[0]
            evidence = next((r["evidence_quote"] for r in source_rows if r["evidence_quote"].strip()), "")
            location = next((r["evidence_location"] for r in source_rows if r["evidence_location"].strip()), "")
            route, notes = "unanimous", "All three annotators assigned the same label."
        else:
            if key not in adjudicated:
                raise ValueError(f"Missing adjudication for {key[1]}")
            item = adjudicated[key]
            final_label = item.get("final_label", "").strip()
            evidence = item.get("adjudication_evidence", "").strip()
            location = item.get("adjudication_location", "").strip()
            notes = item.get("adjudication_notes", "").strip()
            if final_label not in valid_labels or not evidence or not location or not notes:
                raise ValueError(f"Incomplete/invalid adjudication for {key[1]}")
            route = "adjudicated"
        final_rows.append({
            "blind_id": key[0], "claim_id": key[1], "claim_text": source_rows[0]["claim_text"],
            "A1_label": source_labels[0], "A2_label": source_labels[1], "A3_label": source_labels[2],
            "final_label": final_label, "final_evidence": evidence, "final_evidence_location": location,
            "resolution": route, "resolution_notes": notes,
        })
    final_path = result_dir / "human_final_blinded.csv"
    _write_csv(final_path, list(final_rows[0]), final_rows)
    summary_rows: list[dict] = []
    for blind_id in _blind_ids(cfg):
        subset = [r for r in final_rows if r["blind_id"] == blind_id]
        counts = Counter(r["final_label"] for r in subset)
        total = len(subset)
        summary_rows.append({
            "blind_id": blind_id, "claims": total,
            "supported": counts["Supported"], "partially_supported": counts["Partially supported"],
            "unsupported": counts["Unsupported"], "contradicted": counts["Contradicted"],
            "strict_supported_percent": round(100 * counts["Supported"] / total, 2),
            "supported_or_partial_percent": round(100 * (counts["Supported"] + counts["Partially supported"]) / total, 2),
        })
    summary_path = result_dir / "human_final_blinded_summary.csv"
    _write_csv(summary_path, list(summary_rows[0]), summary_rows)
    return len(final_rows), final_path, summary_path
