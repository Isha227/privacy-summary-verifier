"""Audit the completed frozen OPP-115 generation without regenerating outputs."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config/opp115_extension_v1.0.yaml"
MANIFEST_PATH = ROOT / "data/opp115/frozen/OPP115_FROZEN_SAMPLE_MANIFEST.json"
AUDIT_DIR = ROOT / "data/opp115/experiment/audits"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    log_path = ROOT / config["paths"]["logs"]
    rows = read_csv(log_path)

    latest: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["policy_id"], row["model_family"], row["prompt_strategy"], row.get("replicate", "1"))
        if key not in latest or row["timestamp_utc"] > latest[key]["timestamp_utc"]:
            latest[key] = row

    expected = manifest["planned_conditions"]
    errors: list[str] = []
    deviations: list[dict[str, object]] = []
    word_counts: dict[str, list[int]] = {}
    source_hashes = {row["policy_id"]: row["source_sha256"] for row in manifest["policies"]}

    if len(rows) != expected:
        errors.append(f"generation log has {len(rows)} rows; expected {expected}")
    if len(latest) != expected:
        errors.append(f"latest-condition set has {len(latest)} rows; expected {expected}")

    for key, row in sorted(latest.items()):
        label = " / ".join(key)
        if row["status"] != "success":
            errors.append(f"unsuccessful condition: {label}: {row.get('error', '')}")
            continue
        if row["model_id"] != config["models"][row["model_family"]]["model_id"]:
            errors.append(f"model mismatch: {label}")
        if row["source_sha256"] != source_hashes[row["policy_id"]]:
            errors.append(f"source hash mismatch: {label}")
        prompt_rel = config["prompts"][row["prompt_strategy"]]
        from hashlib import sha256
        prompt_hash = sha256((ROOT / prompt_rel).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        if row["prompt_sha256"] != prompt_hash:
            errors.append(f"prompt hash mismatch: {label}")

        text_path = ROOT / row["text_path"]
        json_path = ROOT / row["json_path"]
        if not text_path.exists() or not json_path.exists():
            errors.append(f"missing output file: {label}")
            continue
        text = text_path.read_text(encoding="utf-8").strip()
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if not text:
            errors.append(f"empty output: {label}")
            continue
        if text != str(payload.get("text", "")).strip():
            errors.append(f"text/JSON content mismatch: {label}")
        if int(row["output_tokens"]) >= int(row["max_output_tokens"]):
            deviations.append({"condition": label, "type": "token_ceiling", "detail": row["output_tokens"]})

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        checks = {
            "bullet": any(re.match(r"^[-*•]\s+", line) for line in lines),
            "numbered_list": any(re.match(r"^\d+[.)]\s+", line) for line in lines),
            "markdown_heading": any(re.match(r"^#{1,6}\s+", line) for line in lines),
            "bold_heading": any(re.match(r"^\*\*.+\*\*$", line) for line in lines),
            "intro_label": any(line.endswith(":") and len(line.split()) <= 25 for line in lines),
            "table": any(re.match(r"^\|.*\|$", line) for line in lines),
            "summary_label": any(re.match(r"^(summary|plain[- ]english summary)\s*:?​?$", line, re.I) for line in lines),
            "reasoning_leak": bool(re.search(r"chain of thought|my reasoning|step-by-step reasoning|^analysis:", text, re.I | re.M)),
            "unfinished_paragraph": any(
                not re.search(r"[.!?\"'”’)]$", line)
                and not line.endswith(":")
                and not re.match(r"^\*\*.+\*\*$", line)
                for line in lines
            ),
        }
        for deviation_type, present in checks.items():
            if present:
                deviations.append({"condition": label, "type": deviation_type, "detail": "Detected by frozen-format audit"})
        words = len(re.findall(r"\b[\w’'-]+\b", text))
        word_counts.setdefault(f"{row['model_family']} / {row['prompt_strategy']}", []).append(words)

    deviating_conditions = {str(row["condition"]) for row in deviations}
    deviation_conditions_by_model = Counter(condition.split(" / ")[1] for condition in deviating_conditions)
    summary = {
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "log_rows": len(rows),
        "unique_conditions": len(latest),
        "successful_conditions": sum(row["status"] == "success" for row in latest.values()),
        "failed_conditions": sum(row["status"] != "success" for row in latest.values()),
        "text_files": len(list((ROOT / config["paths"]["outputs"]).rglob("*.txt"))),
        "json_files": len(list((ROOT / config["paths"]["outputs"]).rglob("*.json"))),
        "format_deviation_records": len(deviations),
        "summaries_with_format_deviation": len(deviating_conditions),
        "fully_format_compliant_summaries": len(latest) - len(deviating_conditions),
        "deviation_types": dict(Counter(str(row["type"]) for row in deviations)),
        "deviating_summaries_by_model": dict(deviation_conditions_by_model),
        "integrity_errors": errors,
        "word_count_ranges": {
            name: {"minimum": min(values), "maximum": max(values), "mean": round(sum(values) / len(values), 1), "n": len(values)}
            for name, values in sorted(word_counts.items())
        },
    }
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "generation_completion_audit.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    deviation_path = AUDIT_DIR / "format_deviations.csv"
    with deviation_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["condition", "type", "detail"])
        writer.writeheader()
        writer.writerows(deviations)

    if errors:
        print(f"FAILED: {len(errors)} integrity errors")
        for error in errors[:20]:
            print(error)
        raise SystemExit(1)
    print(f"VALID: {summary['successful_conditions']}/{expected} successful unique conditions")
    print(f"Files: text={summary['text_files']} json={summary['json_files']}")
    print(
        f"Format: {summary['fully_format_compliant_summaries']}/{expected} fully compliant; "
        f"{summary['summaries_with_format_deviation']} summaries have at least one deviation"
    )
    print(f"Deviation records: {summary['format_deviation_records']} {summary['deviation_types']}")
    print(f"Audit: {AUDIT_DIR / 'generation_completion_audit.json'}")


if __name__ == "__main__":
    main()
