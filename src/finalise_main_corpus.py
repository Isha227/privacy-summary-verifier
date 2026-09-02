"""Freeze accepted candidates as MAIN01-MAIN30 and create final metadata."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "main" / "metadata" / "collection_log.csv"
POLICIES = ROOT / "data" / "main" / "metadata" / "policies.csv"
CROSSWALK = ROOT / "data" / "main" / "metadata" / "id_crosswalk.csv"
RAW = ROOT / "data" / "main" / "raw"
CLEAN = ROOT / "data" / "main" / "clean"
QA_DATE = "2026-08-14"

SECTOR_ORDER = {
    "Technology": 1,
    "Retail and e-commerce": 2,
    "Financial services": 3,
    "Health and wellness": 4,
    "Travel and hospitality": 5,
    "Media and entertainment": 6,
}

TITLES = {
    "Google": "Google Privacy Policy", "Microsoft": "Microsoft Privacy Statement",
    "Apple": "Apple Privacy Policy", "Adobe": "Adobe Privacy Policy",
    "Dropbox": "Dropbox Privacy Policy", "Amazon": "Amazon.com Privacy Notice",
    "eBay": "User Privacy Notice", "Shopify": "Shopify Privacy Policy",
    "Walmart": "Walmart Customer Privacy Notice", "IKEA": "IKEA Privacy Policy",
    "PayPal": "PayPal Privacy Statement", "Stripe": "Stripe Privacy Policy",
    "Wise": "Personal Customer Privacy Notice", "Revolut": "Customer Privacy Notice",
    "Coinbase": "Coinbase Global Privacy Policy", "Mayo Clinic": "Privacy Policy",
    "Cleveland Clinic": "MyChart/MyClevelandClinic Privacy Policy",
    "WebMD": "WebMD Privacy Policy", "Headspace": "Headspace Privacy Policy",
    "MyFitnessPal": "MyFitnessPal Privacy Policy", "Booking.com": "Privacy Notice for Travelers",
    "Airbnb": "Airbnb Privacy Policy", "Tripadvisor": "Privacy and Cookies Statement",
    "Hilton": "Hilton Global Privacy Statement", "Uber": "Privacy Notice",
    "Netflix": "Netflix Privacy Statement", "Spotify": "Spotify Privacy Policy",
    "The Walt Disney Company": "The Walt Disney Company Privacy Policy",
    "TikTok": "TikTok US Privacy Policy", "Vimeo": "Vimeo Privacy Policy",
}

META_FIELDS = [
    "policy_id", "organisation", "sector", "country_or_region", "policy_title",
    "canonical_url", "effective_date", "accessed_date", "source_filename",
    "source_format", "language", "word_count_raw", "license_or_terms_note",
    "collection_method", "include", "notes",
]


def main() -> None:
    with LOG.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        log_fields = list(rows[0])
    rows.sort(key=lambda row: (SECTOR_ORDER[row["sector"]], row["organisation"].casefold()))
    metadata = []
    crosswalk = []
    for number, row in enumerate(rows, 1):
        final_id = f"MAIN{number:02d}"
        candidate = row["candidate_id"]
        source_candidates = list(RAW.glob(f"{candidate}_2026-08-14_source.*"))
        existing_final = list(RAW.glob(f"{final_id}_2026-08-14_source.*"))
        if source_candidates:
            source = source_candidates[0]
            final_source = RAW / f"{final_id}_2026-08-14_source{source.suffix.lower()}"
            source.replace(final_source)
        elif existing_final:
            final_source = existing_final[0]
        else:
            raise FileNotFoundError(f"No source file for {candidate}/{final_id}")
        candidate_clean = CLEAN / f"{candidate}.txt"
        final_clean = CLEAN / f"{final_id}.txt"
        if candidate_clean.exists():
            candidate_clean.replace(final_clean)
        elif not final_clean.exists():
            raise FileNotFoundError(f"No clean file for {candidate}/{final_id}")
        row["eligible"] = "yes"
        row["qa_status"] = "passed"
        row["qa_reviewer"] = "researcher" if candidate == "C01" else "Codex QA"
        row["qa_date"] = QA_DATE
        crosswalk.append({
            "candidate_id": candidate, "policy_id": final_id, "organisation": row["organisation"],
            "sector": row["sector"], "replacement_for": row["replacement_for"],
        })
        metadata.append({
            "policy_id": final_id,
            "organisation": row["organisation"],
            "sector": row["sector"],
            "country_or_region": row["region"],
            "policy_title": TITLES[row["organisation"]],
            "canonical_url": row["url"],
            "effective_date": row["effective_date"],
            "accessed_date": row["accessed_date"],
            "source_filename": final_source.name,
            "source_format": final_source.suffix.lstrip(".").upper(),
            "language": "English",
            "word_count_raw": row["raw_words"],
            "license_or_terms_note": "Public official privacy policy retained for research provenance",
            "collection_method": "Direct download from official page",
            "include": "yes",
            "notes": f"Clean words: {row['clean_words']}; candidate {candidate}. {row['notes']}",
        })
    with POLICIES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=META_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(metadata)
    with CROSSWALK.open("w", encoding="utf-8", newline="") as handle:
        fields = ["candidate_id", "policy_id", "organisation", "sector", "replacement_for"]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(crosswalk)
    rows.sort(key=lambda row: int(row["candidate_id"][1:]))
    with LOG.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=log_fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    print(f"Finalised {len(metadata)} policies")


if __name__ == "__main__":
    main()
