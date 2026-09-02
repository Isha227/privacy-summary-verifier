from __future__ import annotations

import csv
import json
from difflib import SequenceMatcher

from .common import ROOT, load_config, read_csv
from .v2_statement_verifier import FIELDS as STATEMENT_FIELDS, _normalise_whitespace, _policy_for_blind, _policy_units, _quote_matches
from .v2_statements import split_sentences


def _write(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, " ".join(a.lower().split()), " ".join(b.lower().split())).ratio()


def main() -> None:
    cfg = load_config()
    root = ROOT / cfg["v2_evaluation"]["root"] / "evaluations"
    statement_note = "evidence_normalisation"
    statement_fields = STATEMENT_FIELDS + [statement_note]
    repaired_statements = 0
    for path in sorted((root / "gemini_statement_verification").glob("*/S*_statement_verification_v1.3.csv")):
        rows = read_csv(path)
        _, policy = _policy_for_blind(cfg, rows[0]["blind_id"])
        source = dict(_policy_units(policy))
        for row in rows:
            notes = []
            ids = [x for x in row.get("evidence_unit_ids", "").split(";") if x]
            quotes = json.loads(row.get("evidence_quotes", "[]"))
            if len(ids) == 1 and len(quotes) == 1 and not _quote_matches(source.get(ids[0], ""), quotes[0]):
                span_ids = [unit_id for unit_id, text in source.items()
                            if _normalise_whitespace(text) in _normalise_whitespace(quotes[0])]
                if span_ids:
                    ids = span_ids
                    quotes = [source[unit_id] for unit_id in span_ids]
                    row["evidence_unit_ids"] = ";".join(ids)
                    notes.append("Model multi-sentence excerpt aligned to all constituent frozen source sentences")
            repaired = []
            for unit_id, quote in zip(ids, quotes):
                if unit_id in source and not _quote_matches(source[unit_id], quote):
                    repaired.append(source[unit_id])
                    notes.append(f"{unit_id}: model excerpt replaced by full frozen source sentence")
                else:
                    repaired.append(quote)
            if len(ids) == len(repaired):
                row["evidence_quotes"] = json.dumps(repaired, ensure_ascii=False)
            closest_id = row.get("closest_source_unit_id", "")
            if closest_id and closest_id in source and not _quote_matches(source[closest_id], row.get("closest_source_quote", "")):
                row["closest_source_quote"] = source[closest_id]
                notes.append(f"{closest_id}: closest excerpt replaced by full frozen source sentence")
            verified = len(ids) == len(repaired) and all(
                unit_id in source and _quote_matches(source[unit_id], quote)
                for unit_id, quote in zip(ids, repaired)
            )
            if closest_id:
                verified = verified and closest_id in source and _quote_matches(source[closest_id], row["closest_source_quote"])
            row[statement_note] = "; ".join(notes)
            row["evidence_verified"] = str(verified).lower()
            row["status"] = "success" if verified else "evidence_validation_failed"
            row["error"] = "" if verified else "Evidence could not be normalised from Gemini-selected source IDs"
            repaired_statements += int(bool(notes))
        _write(path, rows, statement_fields)

    coverage_note = "evidence_normalisation"
    coverage_files = sorted((root / "gemini_preliminary_coverage").glob("*/S*_gemini_coverage_v1.0.csv"))
    repaired_coverage, unresolved = 0, []
    for path in coverage_files:
        rows = read_csv(path)
        blind_id = rows[0]["blind_id"]
        summary = (ROOT / cfg["paths"]["anonymised"] / f"{blind_id}.txt").read_text(encoding="utf-8").strip()
        sentences = split_sentences(summary)
        paragraphs = [line.strip() for line in summary.splitlines() if line.strip()]
        candidates = list(dict.fromkeys(paragraphs + sentences))
        fields = list(rows[0].keys())
        if coverage_note not in fields: fields.append(coverage_note)
        for row in rows:
            note = ""
            evidence = row.get("summary_evidence", "").strip()
            if row["coverage_label"] != "Not covered" and evidence and evidence not in summary:
                best = max(candidates, key=lambda sentence: _similarity(evidence, sentence))
                score = _similarity(evidence, best)
                if score >= 0.35:
                    row["summary_evidence"] = best
                    note = f"Model excerpt replaced by closest full frozen summary sentence; similarity={score:.3f}"
                    repaired_coverage += 1
                else:
                    unresolved.append((blind_id, row["proposed_unit_id"], score))
            valid = ((row["coverage_label"] == "Not covered" and not row.get("summary_evidence", "").strip()) or
                     (row["coverage_label"] != "Not covered" and row.get("summary_evidence", "").strip() in summary))
            row[coverage_note] = note
            row["evidence_verified"] = str(valid).lower()
            row["status"] = "success" if valid else "evidence_validation_failed"
            row["error"] = "" if valid else "Coverage evidence still requires targeted re-evaluation"
        _write(path, rows, fields)
    print(f"Normalised statement evidence rows: {repaired_statements}")
    print(f"Normalised coverage evidence rows: {repaired_coverage}")
    print(f"Coverage rows still requiring targeted re-evaluation: {len(unresolved)}")
    if unresolved:
        print(unresolved)


if __name__ == "__main__":
    main()
