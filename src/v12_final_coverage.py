from __future__ import annotations

import csv
import json
import os
import re
import time
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .common import ROOT, append_csv, load_config, read_csv, sha256_text
from .v2_statement_verifier import _normalise_whitespace


BASE = ROOT / "data/v2_prompt_intervention_v1_2"
ADJUDICATION_DIR = BASE / "human_evaluation/adjudication"
HUMAN_DIR = BASE / "human_evaluation/coverage_phase2"
OUTPUT_DIR = BASE / "evaluations/gemini_final_coverage"
OUTPUT_PATH = OUTPUT_DIR / "gemini_final_coverage_all.csv"
LOG_PATH = OUTPUT_DIR / "gemini_final_coverage_batch_log.csv"
RESULTS_DIR = BASE / "evaluations/final_coverage_results"

LABEL_TO_SCORE = {"Not covered": 0, "Partially covered": 1, "Covered": 2}
OUTPUT_FIELDS = [
    "comparison_id", "blind_id", "policy_id", "final_unit_id",
    "important_information", "coverage_label", "coverage_score",
    "summary_evidence", "explanation", "evidence_verified", "model_id",
    "response_id", "timestamp_utc", "status", "error",
]
LOG_FIELDS = [
    "blind_id", "batch_number", "requested_units", "returned_units",
    "new_rows", "status", "attempt", "response_id", "prompt_sha256",
    "timestamp_utc", "error",
]


def _load_design() -> tuple[list[dict], list[dict]]:
    units = read_csv(ADJUDICATION_DIR / "frozen_source_units_FINAL.csv")
    key = sorted(
        read_csv(BASE / "anonymised/BLINDING_KEY_RESTRICTED.csv"),
        key=lambda row: row["blind_id"],
    )
    if len(units) != 165 or len({row["final_unit_id"] for row in units}) != 165:
        raise ValueError("Expected 165 unique frozen human source units")
    if len(key) != 54 or len({row["blind_id"] for row in key}) != 54:
        raise ValueError("Expected 54 unique blinded summaries")
    for policy_id in ("PILOT01", "PILOT02", "PILOT03"):
        if sum(row["policy_id"] == policy_id for row in key) != 18:
            raise ValueError(f"Expected 18 summaries for {policy_id}")
    return units, key


def validate_setup() -> tuple[int, int, int]:
    units, key = _load_design()
    for row in key:
        path = BASE / "anonymised" / f"{row['blind_id']}.txt"
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            raise FileNotFoundError(f"Missing blinded summary: {path}")
    expected = sum(
        1 for summary in key for unit in units
        if summary["policy_id"] == unit["policy_id"]
    )
    if expected != 2970:
        raise ValueError(f"Expected 2,970 comparisons; found {expected}")
    return len(units), len(key), expected


def status() -> dict:
    rows = read_csv(OUTPUT_PATH)
    successful = [
        row for row in rows
        if row.get("status") == "success" and row.get("evidence_verified") == "true"
    ]
    unique_ids = {row["comparison_id"] for row in successful}
    logs = read_csv(LOG_PATH)
    return {
        "rows": len(rows),
        "successful_unique": len(unique_ids),
        "remaining": max(0, 2970 - len(unique_ids)),
        "summaries_represented": len({row["blind_id"] for row in successful}),
        "successful_batches": sum(row.get("status") == "success" for row in logs),
        "failed_batches": sum(row.get("status") == "failed" for row in logs),
        "complete": len(unique_ids) == 2970,
    }


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "judgments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "final_unit_id": {"type": "string"},
                        "coverage_label": {
                            "type": "string", "enum": sorted(LABEL_TO_SCORE)
                        },
                        "summary_evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "explanation": {"type": "string"},
                    },
                    "required": [
                        "final_unit_id", "coverage_label",
                        "summary_evidence_ids", "explanation",
                    ],
                },
            }
        },
        "required": ["judgments"],
    }


def _evidence_passages(summary: str) -> list[tuple[str, str]]:
    """Split a summary into stable, verbatim passages that Gemini cites by ID."""
    passages: list[str] = []
    for block in re.split(r"\n\s*\n", summary.strip()):
        block = block.strip()
        if not block:
            continue
        if block.startswith("**") and block.endswith("**"):
            passages.append(block)
            continue
        pieces = re.split(r"(?<=[.!?])\s+(?=(?:[-*]\s+|\*\*)?[A-Z])", block)
        passages.extend(piece.strip() for piece in pieces if piece.strip())
    return [(f"E{index:03d}", text) for index, text in enumerate(passages, start=1)]


def _instruction(summary: str, units: list[dict]) -> str:
    passage_block = "\n".join(
        json.dumps({"evidence_id": evidence_id, "text": text}, ensure_ascii=False)
        for evidence_id, text in _evidence_passages(summary)
    )
    unit_block = "\n".join(
        json.dumps(
            {
                "final_unit_id": row["final_unit_id"],
                "important_information": row["important_information"],
                "exact_source_quote": row["exact_source_quote"],
                "material_qualifiers": row["material_qualifiers"],
            },
            ensure_ascii=False,
        )
        for row in units
    )
    return f"""Assess whether each frozen important source-policy unit is retained in the supplied plain-English summary. Read the source unit first and then check the summary. Do not use outside knowledge.

Labels:
- Covered: the central meaning and all material qualifications are retained.
- Partially covered: some meaning is retained, but an important detail, scope, condition, exception or qualification is missing or weakened.
- Not covered: no adequate corresponding information appears in the summary.

For Covered or Partially covered, return the summary_evidence_ids needed to directly support the judgment. Use only IDs from the supplied evidence passages and avoid unnecessary passages. For Not covered, return an empty summary_evidence_ids array. Give one concise evidence-linked explanation. Preserve every final_unit_id exactly and return every unit once in the supplied order.

BLINDED SUMMARY, DIVIDED INTO VERBATIM EVIDENCE PASSAGES:
{passage_block}

FROZEN IMPORTANT SOURCE UNITS (one JSON object per line):
{unit_block}"""


def _call_gemini(
    *, model: str, api_key: str, instruction: str, settings: dict
) -> tuple[list[dict], str, int]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": instruction}]}],
        "generationConfig": {
            "temperature": settings.get("temperature", 0.0),
            "maxOutputTokens": int(settings.get("max_output_tokens", 8192)),
            "responseMimeType": "application/json",
            "responseSchema": _schema(),
        },
    }
    timeout = int(settings.get("timeout_seconds", 300))
    retries = int(settings.get("retries", 3))
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                url, headers={"x-goog-api-key": api_key}, json=payload, timeout=timeout
            )
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 0) or 0)
                raise RuntimeError(f"HTTP 429 rate limit; retry_after={retry_after}")
            if not response.ok:
                raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1200]}")
            data = response.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            judgments = json.loads(raw).get("judgments", [])
            response_id = response.headers.get("x-request-id", "") or data.get("responseId", "")
            return judgments, response_id, attempt
        except Exception:
            if attempt == retries:
                raise
            time.sleep(float(settings.get("retry_delay_seconds", 20)) * attempt)
    raise RuntimeError("Gemini retry loop terminated unexpectedly")


def run(max_batches: int | None = None) -> tuple[int, int, Path]:
    cfg = load_config()
    settings = cfg.get("v2_final_coverage_verifier", cfg["v2_coverage_verifier"])
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY")
    model = settings["model"]
    units, key = _load_design()
    unit_by_policy = {
        policy_id: [row for row in units if row["policy_id"] == policy_id]
        for policy_id in ("PILOT01", "PILOT02", "PILOT03")
    }
    existing = read_csv(OUTPUT_PATH)
    completed = {
        row["comparison_id"] for row in existing
        if row.get("status") == "success" and row.get("evidence_verified") == "true"
    }
    if len(completed) != len(set(completed)):
        raise ValueError("Duplicate completed comparison IDs in final Gemini coverage output")

    batch_size = int(settings.get("max_units_per_batch", 15))
    successful_batches = 0
    added = 0
    for summary_row in key:
        blind_id = summary_row["blind_id"]
        policy_id = summary_row["policy_id"]
        summary = (BASE / "anonymised" / f"{blind_id}.txt").read_text(
            encoding="utf-8"
        ).strip()
        pending = [
            row for row in unit_by_policy[policy_id]
            if f"{blind_id}--{row['final_unit_id']}" not in completed
        ]
        for start in range(0, len(pending), batch_size):
            if max_batches is not None and successful_batches >= max_batches:
                return added, successful_batches, OUTPUT_PATH
            batch = pending[start:start + batch_size]
            batch_number = start // batch_size + 1
            instruction = _instruction(summary, batch)
            passage_lookup = dict(_evidence_passages(summary))
            try:
                validation_retries = int(settings.get("validation_retries", 3))
                validation_delay = float(
                    settings.get("validation_retry_delay_seconds", 5)
                )
                for validation_attempt in range(1, validation_retries + 1):
                    submitted_instruction = instruction
                    if validation_attempt > 1:
                        submitted_instruction += (
                            "\n\nIMPORTANT RETRY: The preceding response failed strict "
                            "output validation. For Covered or Partially covered, return "
                            "valid summary_evidence_ids from the supplied "
                            "passages; do not write or paraphrase evidence text. Return every "
                            "requested final_unit_id exactly once and in order."
                        )
                    judgments, response_id, api_attempt = _call_gemini(
                        model=model,
                        api_key=api_key,
                        instruction=submitted_instruction,
                        settings=settings,
                    )
                    try:
                        expected_ids = [row["final_unit_id"] for row in batch]
                        returned_ids = [row.get("final_unit_id") for row in judgments]
                        if returned_ids != expected_ids:
                            raise ValueError(
                                "Gemini did not return every final unit exactly once in order"
                            )
                        lookup = {row["final_unit_id"]: row for row in batch}
                        new_rows = []
                        for judgment in judgments:
                            unit_id = judgment["final_unit_id"]
                            label = judgment.get("coverage_label", "")
                            evidence_ids = judgment.get("summary_evidence_ids", [])
                            explanation = judgment.get("explanation", "").strip()
                            evidence_valid = (
                                label in LABEL_TO_SCORE
                                and bool(explanation)
                                and isinstance(evidence_ids, list)
                                and len(evidence_ids) == len(set(evidence_ids))
                                and (
                                    (label == "Not covered" and not evidence_ids)
                                    or (
                                        label != "Not covered"
                                        and len(evidence_ids) >= 1
                                        and all(
                                            evidence_id in passage_lookup
                                            for evidence_id in evidence_ids
                                        )
                                    )
                                )
                            )
                            if not evidence_valid:
                                raise ValueError(
                                    "Invalid label, explanation or evidence for "
                                    f"{blind_id}--{unit_id}: label={label!r}; "
                                    f"evidence_ids={evidence_ids!r}; "
                                    f"explanation_present={bool(explanation)}"
                                )
                            unit = lookup[unit_id]
                            new_rows.append({
                                "comparison_id": f"{blind_id}--{unit_id}",
                                "blind_id": blind_id,
                                "policy_id": policy_id,
                                "final_unit_id": unit_id,
                                "important_information": unit["important_information"],
                                "coverage_label": label,
                                "coverage_score": LABEL_TO_SCORE[label],
                                "summary_evidence": (
                                    "No corresponding summary evidence."
                                    if label == "Not covered"
                                    else " […] ".join(
                                        passage_lookup[evidence_id]
                                        for evidence_id in evidence_ids
                                    )
                                ),
                                "explanation": explanation,
                                "evidence_verified": "true",
                                "model_id": model,
                                "response_id": response_id,
                                "timestamp_utc": time.strftime(
                                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                                ),
                                "status": "success",
                                "error": "",
                            })
                        break
                    except ValueError as exc:
                        if validation_attempt == validation_retries:
                            raise
                        print(
                            f"Gemini final coverage {blind_id} batch {batch_number}: "
                            f"validation retry {validation_attempt}/{validation_retries} "
                            f"after {exc}",
                            flush=True,
                        )
                        if validation_delay > 0:
                            time.sleep(validation_delay * validation_attempt)
                for row in new_rows:
                    append_csv(OUTPUT_PATH, row, OUTPUT_FIELDS)
                    completed.add(row["comparison_id"])
                added += len(new_rows)
                successful_batches += 1
                append_csv(LOG_PATH, {
                    "blind_id": blind_id, "batch_number": batch_number,
                    "requested_units": len(batch), "returned_units": len(judgments),
                    "new_rows": len(new_rows), "status": "success",
                    "attempt": f"validation={validation_attempt};api={api_attempt}",
                    "response_id": response_id,
                    "prompt_sha256": sha256_text(submitted_instruction),
                    "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "error": "",
                }, LOG_FIELDS)
                print(
                    f"Gemini final coverage {blind_id} batch {batch_number}: "
                    f"success {len(new_rows)}/{len(batch)}; total={len(completed)}/2970",
                    flush=True,
                )
                if float(settings.get("batch_delay_seconds", 3)) > 0:
                    time.sleep(float(settings.get("batch_delay_seconds", 3)))
            except Exception as exc:
                append_csv(LOG_PATH, {
                    "blind_id": blind_id, "batch_number": batch_number,
                    "requested_units": len(batch), "returned_units": 0,
                    "new_rows": 0, "status": "failed", "attempt": "",
                    "response_id": "", "prompt_sha256": sha256_text(instruction),
                    "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "error": f"{type(exc).__name__}: {exc}",
                }, LOG_FIELDS)
                raise
    return added, successful_batches, OUTPUT_PATH


def _confusion(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    matrix = np.zeros((3, 3), dtype=int)
    for a, b in zip(left, right):
        matrix[int(a), int(b)] += 1
    return matrix


def _agreement(left: np.ndarray, right: np.ndarray) -> dict:
    matrix = _confusion(left, right).astype(float)
    observed = matrix / matrix.sum()
    expected = np.outer(matrix.sum(axis=1), matrix.sum(axis=0)) / matrix.sum() ** 2
    exact = float(np.trace(observed))
    pe = float(np.trace(expected))
    kappa = 1.0 if pe == 1 else (exact - pe) / (1 - pe)
    weights = np.fromfunction(lambda i, j: ((i - j) / 2) ** 2, (3, 3))
    denominator = float((weights * expected).sum())
    weighted = 1.0 if denominator == 0 else 1.0 - float((weights * observed).sum()) / denominator
    return {
        "n": int(len(left)), "exact_agreement": exact, "cohen_kappa": float(kappa),
        "quadratic_weighted_kappa": float(weighted),
        "mean_absolute_difference": float(np.mean(np.abs(left - right))),
    }


def analyse() -> tuple[int, Path]:
    gemini = pd.read_csv(OUTPUT_PATH, dtype=str, keep_default_na=False)
    if len(gemini) != 2970 or gemini["comparison_id"].nunique() != 2970:
        raise ValueError(
            f"Final Gemini coverage is incomplete: rows={len(gemini)}, "
            f"unique={gemini['comparison_id'].nunique()}, expected=2970"
        )
    if not (gemini["status"] == "success").all() or not (
        gemini["evidence_verified"] == "true"
    ).all():
        raise ValueError("Final Gemini coverage contains unsuccessful or invalid rows")

    ratings = {}
    metadata = None
    for evaluator in ("A1", "A2", "A3"):
        path = (
            HUMAN_DIR / f"Researcher_{evaluator}_Package"
            / f"human_v12_{evaluator}_COVERAGE_PHASE2_COMPLETED.xlsx"
        )
        frame = pd.read_excel(path, sheet_name="Coverage", dtype=str).fillna("")
        ratings[evaluator] = frame.set_index("comparison_id")["coverage_label"]
        if metadata is None:
            metadata = frame[["comparison_id", "policy_id", "blind_id", "final_unit_id"]]
    labels = pd.DataFrame(ratings).sort_index()
    if labels.shape != (2970, 3) or labels.isna().any().any():
        raise ValueError(f"Expected a complete 2,970 x 3 human matrix; found {labels.shape}")

    adjudication = pd.read_excel(
        ROOT / "outputs/coverage_adjudication_v12/human_v12_COVERAGE_ADJUDICATION_COMPLETED.xlsx",
        sheet_name="Adjudication", dtype=str,
    ).fillna("").set_index("comparison_id")
    disagreement_ids = labels.index[labels.nunique(axis=1) > 1]
    if set(adjudication.index) != set(disagreement_ids):
        raise ValueError("Coverage adjudication rows do not match human disagreements")
    consensus = labels["A1"].copy()
    consensus.loc[disagreement_ids] = adjudication.loc[disagreement_ids, "final_label"]
    human_score = consensus.map(LABEL_TO_SCORE).astype(int)

    gemini = gemini.set_index("comparison_id").loc[labels.index]
    gemini_score = gemini["coverage_score"].astype(int)
    metrics = _agreement(human_score.to_numpy(), gemini_score.to_numpy())

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    final = metadata.set_index("comparison_id").loc[labels.index].copy()
    for evaluator in ("A1", "A2", "A3"):
        final[f"{evaluator}_label"] = labels[evaluator]
    final["final_human_label"] = consensus
    final["final_human_score"] = human_score
    final["resolution"] = np.where(labels.nunique(axis=1) == 1, "unanimous", "adjudicated")
    final["gemini_label"] = gemini["coverage_label"]
    final["gemini_score"] = gemini_score
    final["exact_match"] = (human_score == gemini_score).astype(int)
    final["absolute_difference"] = np.abs(human_score - gemini_score)
    final.reset_index().to_csv(
        RESULTS_DIR / "final_human_and_gemini_coverage.csv", index=False
    )

    pairwise = []
    score_frame = labels.apply(lambda column: column.map(LABEL_TO_SCORE)).astype(int)
    for left, right in combinations(("A1", "A2", "A3"), 2):
        pairwise.append({
            "comparison": f"{left} vs {right}",
            **_agreement(score_frame[left].to_numpy(), score_frame[right].to_numpy()),
        })
    pd.DataFrame(pairwise).to_csv(
        RESULTS_DIR / "human_pairwise_coverage_agreement.csv", index=False
    )
    pd.DataFrame([{"comparison": "Gemini vs final human consensus", **metrics}]).to_csv(
        RESULTS_DIR / "gemini_human_coverage_agreement.csv", index=False
    )

    key = pd.read_csv(BASE / "anonymised/BLINDING_KEY_RESTRICTED.csv", dtype=str)
    summary_level = final.reset_index().merge(
        key, on=["blind_id", "policy_id"], validate="many_to_one"
    )
    summary_level["prompt_set"] = np.where(
        summary_level["prompt_strategy"].str.startswith("safety_focused"),
        "Safety-focused", "Basic",
    )
    summary_level["strategy"] = (
        summary_level["prompt_strategy"].str.replace("safety_focused_", "", regex=False)
        .str.replace("basic_", "", regex=False)
    )
    summary_metrics = summary_level.groupby(
        ["blind_id", "policy_id", "model_family", "strategy", "prompt_set"]
    ).agg(
        strict_coverage=("final_human_score", lambda x: float((x == 2).mean())),
        weighted_coverage=("final_human_score", lambda x: float((x / 2).mean())),
    ).reset_index()
    summary_metrics.to_csv(RESULTS_DIR / "human_coverage_by_summary.csv", index=False)
    by_set = summary_metrics.groupby("prompt_set").agg(
        summaries=("blind_id", "count"),
        mean_strict_coverage=("strict_coverage", "mean"),
        mean_weighted_coverage=("weighted_coverage", "mean"),
    ).reset_index()
    by_set.to_csv(RESULTS_DIR / "human_coverage_by_prompt_set.csv", index=False)

    wide = summary_metrics.pivot(
        index=["policy_id", "model_family", "strategy"], columns="prompt_set",
        values=["strict_coverage", "weighted_coverage"],
    )
    delta_rows = []
    for index, row in wide.iterrows():
        delta_rows.append({
            "policy_id": index[0], "model_family": index[1], "strategy": index[2],
            "strict_delta_safety_minus_basic": (
                row[("strict_coverage", "Safety-focused")]
                - row[("strict_coverage", "Basic")]
            ),
            "weighted_delta_safety_minus_basic": (
                row[("weighted_coverage", "Safety-focused")]
                - row[("weighted_coverage", "Basic")]
            ),
        })
    deltas = pd.DataFrame(delta_rows)
    deltas.to_csv(RESULTS_DIR / "human_coverage_matched_pair_deltas.csv", index=False)

    confusion = _confusion(human_score.to_numpy(), gemini_score.to_numpy())
    pd.DataFrame(
        confusion,
        index=["Human Not covered", "Human Partially covered", "Human Covered"],
        columns=["Gemini Not covered", "Gemini Partially covered", "Gemini Covered"],
    ).to_csv(RESULTS_DIR / "gemini_human_coverage_confusion.csv")

    summary = {
        "comparisons": 2970,
        "summaries": 54,
        "frozen_units": 165,
        "human_distribution": dict(Counter(consensus)),
        "gemini_distribution": dict(Counter(gemini["coverage_label"])),
        "human_unanimous": int((labels.nunique(axis=1) == 1).sum()),
        "human_adjudicated": int(len(disagreement_ids)),
        "pairwise_human": pairwise,
        "gemini_vs_final_human": metrics,
        "human_prompt_set_means": by_set.to_dict("records"),
        "matched_pair_mean_deltas": {
            "strict": float(deltas["strict_delta_safety_minus_basic"].mean()),
            "weighted": float(deltas["weighted_delta_safety_minus_basic"].mean()),
        },
    }
    summary_path = RESULTS_DIR / "final_coverage_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    report = f"""# Final coverage results

The final coverage denominator comprised 165 human-adjudicated source units evaluated against all 54 blinded summaries, producing 2,970 unit-summary comparisons per evaluator. The three researchers agreed unanimously on {summary['human_unanimous']:,} comparisons and adjudicated the remaining {summary['human_adjudicated']:,} disagreements.

Gemini exactly matched the final human coverage label on {100 * metrics['exact_agreement']:.1f}% of comparisons. Cohen's kappa was {metrics['cohen_kappa']:.3f}, quadratic weighted kappa was {metrics['quadratic_weighted_kappa']:.3f}, and the mean absolute difference on the 0-2 scale was {metrics['mean_absolute_difference']:.3f}.

Across the 27 matched policy-model-strategy pairs, safety-focused prompting changed mean strict human coverage by {100 * summary['matched_pair_mean_deltas']['strict']:+.2f} percentage points and mean weighted coverage by {100 * summary['matched_pair_mean_deltas']['weighted']:+.2f} points relative to basic prompting.
"""
    report_path = RESULTS_DIR / "final_coverage_report_ready.md"
    report_path.write_text(report, encoding="utf-8")
    return len(final), report_path
