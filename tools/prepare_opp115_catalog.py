"""Prepare a reproducible text and metadata catalogue for OPP-115.

This script preserves the downloaded corpus unchanged. It writes cleaned policy text
and a derived CSV catalogue to ``data/opp115/processed``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import re
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from pypdf import PdfReader


WORD_RE = re.compile(r"\b[\w][\w'’.-]*\b", flags=re.UNICODE)


def normalize_space(value: str) -> str:
    value = html.unescape(value).replace("\xa0", " ")
    value = re.sub(r"[ \t\f\v]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def extract_text(path: Path) -> str:
    raw = path.read_bytes()
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript", "svg"]):
        tag.decompose()
    return normalize_space(soup.get_text("\n"))


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return normalize_space("\n\n".join(page.extract_text() or "" for page in reader.pages))


def domain_from_url(value: str) -> str:
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return parsed.netloc.lower().removeprefix("www.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    metadata_path = args.corpus_root / "documentation" / "policies_opp115.csv"
    originals = args.corpus_root / "original_policies"
    text_dir = args.output_dir / "cleaned_policies"
    text_dir.mkdir(parents=True, exist_ok=True)

    metadata: dict[str, dict[str, str]] = {}
    with metadata_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            metadata[row["Policy UID"].strip()] = row

    rows: list[dict[str, object]] = []
    for source_path in sorted(path for path in originals.iterdir() if path.suffix.lower() in {".html", ".pdf"}):
        print(f"Processing {source_path.name}", flush=True)
        uid = source_path.name.split("_", 1)[0]
        meta = metadata.get(uid, {})
        policy_url = meta.get("Policy URL", "")
        domain = domain_from_url(policy_url) if policy_url else source_path.stem.split("_", 1)[-1]
        text = extract_pdf_text(source_path) if source_path.suffix.lower() == ".pdf" else extract_text(source_path)
        words = WORD_RE.findall(text)
        output_name = f"OPP{int(uid):04d}_{domain.replace('.', '_')}.txt"
        output_path = text_dir / output_name
        output_path.write_text(text + "\n", encoding="utf-8")
        rows.append(
            {
                "policy_uid": uid,
                "domain": domain,
                "policy_url": policy_url,
                "collection_date": meta.get("Policy collection date", ""),
                "last_updated_date": meta.get("Policy last updated date", ""),
                "source_html_file": source_path.name,
                "cleaned_text_file": output_name,
                "word_count": len(words),
                "character_count": len(text),
                "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                "cleaned_sha256": hashlib.sha256((text + "\n").encode("utf-8")).hexdigest(),
            }
        )

    rows.sort(key=lambda row: int(str(row["policy_uid"])))
    catalogue_path = args.output_dir / "opp115_policy_catalogue.csv"
    with catalogue_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    counts = sorted(int(row["word_count"]) for row in rows)
    print(f"Policies processed: {len(rows)}")
    print(f"Word count min/median/max: {counts[0]}/{counts[len(counts)//2]}/{counts[-1]}")
    print(f"Catalogue: {catalogue_path}")


if __name__ == "__main__":
    main()
