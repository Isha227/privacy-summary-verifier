"""Automated, non-destructive QA checks for the 30-policy main corpus."""

from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "main" / "metadata" / "collection_log.csv"
RAW = ROOT / "data" / "main" / "raw"
CLEAN = ROOT / "data" / "main" / "clean"
OUT = ROOT / "outputs" / "main_corpus_qa" / "qa_results.csv"

TOPIC_TERMS = {
    "collection": ["collect", "information we receive", "information you provide"],
    "use": ["how we use", "use your", "purposes"],
    "sharing": ["share", "disclose", "third parties"],
    "rights": ["your rights", "access", "delete", "opt out"],
    "retention": ["retain", "retention", "keep your"],
    "security": ["security", "protect", "safeguard"],
    "contact": ["contact us", "privacy@", "data protection officer"],
}
INTERFACE_TERMS = [
    "skip to main content", "sign in", "main menu", "accept all cookies",
    "cookie preferences", "subscribe to our newsletter", "back to top",
]
ERROR_TERMS = ["access denied", "enable javascript", "page not found", "captcha", "403 forbidden"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(value: str, limit: int = 240) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit] + ("…" if len(value) > limit else "")


def main() -> None:
    with LOG.open(encoding="utf-8", newline="") as handle:
        metadata = list(csv.DictReader(handle))
    results = []
    for row in metadata:
        candidate = row["candidate_id"]
        clean_path = CLEAN / f"{candidate}.txt"
        raw_files = list(RAW.glob(f"{candidate}_2026-08-14_source.*"))
        text = clean_path.read_text(encoding="utf-8-sig", errors="replace") if clean_path.exists() else ""
        lower = text.casefold()
        words = re.findall(r"\b[\w’'-]+\b", text)
        substantive_lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        substantive_lines = [line for line in substantive_lines if len(line) >= 35]
        counts = Counter(line.casefold() for line in substantive_lines)
        duplicate_instances = sum(count - 1 for count in counts.values() if count > 1)
        duplicate_rate = duplicate_instances / max(1, len(substantive_lines))
        topic_hits = {name: int(any(term in lower for term in terms)) for name, terms in TOPIC_TERMS.items()}
        interface_hits = sum(lower.count(term) for term in INTERFACE_TERMS)
        error_hits = sum(lower.count(term) for term in ERROR_TERMS)
        issues = []
        if len(raw_files) != 1:
            issues.append(f"raw_file_count={len(raw_files)}")
        if not clean_path.exists():
            issues.append("clean_missing")
        if len(words) < 1000:
            issues.append("unusually_short")
        if len(words) > 20000:
            issues.append("unusually_long")
        if sum(topic_hits.values()) < 6:
            issues.append("privacy_topic_check")
        if duplicate_rate > 0.12:
            issues.append("repeated_content")
        if interface_hits > 12:
            issues.append("interface_text")
        if error_hits:
            issues.append("error_text")
        raw_match = bool(raw_files) and any(digest(path) == row["raw_sha256"] for path in raw_files)
        clean_match = clean_path.exists() and digest(clean_path) == row["clean_sha256"]
        if not raw_match:
            issues.append("raw_hash_mismatch")
        if not clean_match:
            issues.append("clean_hash_mismatch")
        results.append({
            "candidate_id": candidate,
            "organisation": row["organisation"],
            "sector": row["sector"],
            "source_url": row["url"],
            "effective_date": row["effective_date"],
            "word_count": len(words),
            "paragraph_like_lines": len(substantive_lines),
            "duplicate_line_rate": round(duplicate_rate, 4),
            "interface_phrase_hits": interface_hits,
            "privacy_topics_present": sum(topic_hits.values()),
            **{f"has_{name}": value for name, value in topic_hits.items()},
            "raw_hash_match": raw_match,
            "clean_hash_match": clean_match,
            "automated_status": "review" if issues else "pass",
            "issues": "; ".join(issues),
            "start_preview": compact(text[:900]),
            "end_preview": compact(text[-900:]),
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(f"WROTE {OUT}")
    print(Counter(row["automated_status"] for row in results))
    for row in results:
        if row["automated_status"] == "review":
            print(row["candidate_id"], row["organisation"], row["issues"])


if __name__ == "__main__":
    main()
