"""Documented targeted corrections identified during main-corpus QA."""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "main" / "clean"
LOG = ROOT / "data" / "main" / "metadata" / "collection_log.csv"


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def start_at(text: str, marker: str) -> str:
    position = text.find(marker)
    if position < 0:
        raise ValueError(f"Missing start marker: {marker}")
    return text[position:]


def end_at(text: str, marker: str, after: int = 0) -> str:
    position = text.find(marker, after)
    if position < 0:
        raise ValueError(f"Missing end marker: {marker}")
    return text[:position]


def remove_interface_lines(text: str) -> str:
    unwanted = {
        "back to top", "print", "expand all", "collapse all", "skip to main content",
        "skip to footer", "main menu", "sign in",
    }
    return "\n".join(line for line in text.splitlines() if line.strip().casefold() not in unwanted)


def clean_disney_markup(text: str) -> str:
    output = []
    seen_injected = set()
    for line in text.splitlines():
        if "<p>" in line or "</a>" in line or "href=" in line:
            line = re.sub(r"<[^>]+>", " ", line)
            line = re.sub(r"\s+", " ", line).strip()
            key = re.sub(r"\s+", " ", line).casefold()
            if len(key) > 80 and key in seen_injected:
                continue
            if len(key) > 80:
                seen_injected.add(key)
        output.append(line)
    return "\n".join(output)


def transform(candidate: str, text: str) -> tuple[str, str]:
    note = "QA checked; no additional boundary correction required"
    if candidate == "C02":
        text = start_at(text, "Microsoft Privacy Statement")
        text = remove_interface_lines(text)
        note = "QA corrected: removed page controls; retained full product-specific Microsoft statement"
    elif candidate == "C07":
        text = start_at(text, "User Privacy Notice")
        positions = [m.start() for m in re.finditer("Previous User Privacy Notice", text)]
        boundaries = [position for position in positions if position > 10000]
        if boundaries:
            text = text[:boundaries[0]]
        note = "QA corrected: removed search interface and archived previous policy appended to current notice"
    elif candidate == "C09":
        text = start_at(text, "Walmart Customer Privacy Notice (Online and In-Store)")
        text = remove_interface_lines(text)
        note = "QA corrected: removed corporate navigation before policy"
    elif candidate == "C11":
        text = start_at(text, "PayPal Privacy Statement")
        text = remove_interface_lines(text)
        note = "QA corrected: removed page controls; repeated address rows retained as regional policy content"
    elif candidate == "C17":
        text = start_at(text, "MyChart/MyClevelandClinic Privacy Policy")
        if "Telemedicine Privacy Policy" in text:
            text = end_at(text, "Telemedicine Privacy Policy")
        note = "QA corrected: isolated the intended MyChart/MyClevelandClinic policy from adjacent website and telemedicine notices"
    elif candidate == "C21":
        text = start_at(text, "Privacy Notice for Travelers")
        if "How does it work?" in text:
            text = end_at(text, "How does it work?")
        text = remove_interface_lines(text)
        note = "QA corrected: removed site navigation and traveler-review widget after policy"
    elif candidate == "C23":
        text = start_at(text, "Privacy and Cookies Statement")
        footer = text.find("\nUnited States\n\nCanada", 50000)
        if footer > 0:
            text = text[:footer]
        note = "QA corrected: removed media-centre navigation and country/footer selector after policy"
    elif candidate == "C24":
        text = start_at(text, "HILTON GLOBAL PRIVACY STATEMENT")
        text = remove_interface_lines(text)
        note = "QA corrected: removed page controls; regional appendices retained"
    elif candidate == "C28":
        text = start_at(text, "Privacy Policy")
        text = clean_disney_markup(text)
        note = "QA corrected: converted embedded tooltip HTML to text and removed exact injected duplicates"
    return normalize(text), note


def main() -> None:
    with LOG.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])
    notes = {}
    for candidate in ["C02", "C07", "C09", "C11", "C17", "C21", "C23", "C24", "C28"]:
        path = CLEAN / f"{candidate}.txt"
        text, note = transform(candidate, path.read_text(encoding="utf-8-sig"))
        path.write_text(text, encoding="utf-8", newline="\n")
        notes[candidate] = note
        print(candidate, len(text.split()), note)
    for row in rows:
        path = CLEAN / f"{row['candidate_id']}.txt"
        row["clean_words"] = str(len(path.read_text(encoding="utf-8-sig").split()))
        row["clean_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        if row["candidate_id"] in notes:
            row["notes"] = notes[row["candidate_id"]]
    with LOG.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
