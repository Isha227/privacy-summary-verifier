"""Resume-safe collector for the frozen 30-policy main-study candidate list."""

from __future__ import annotations

import hashlib
import re
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "main" / "metadata" / "collection_log.csv"
RAW = ROOT / "data" / "main" / "raw"
CLEAN = ROOT / "data" / "main" / "clean"
ACCESS_DATE = "2026-08-14"
USER_AGENT = "Mozilla/5.0 (compatible; MSc-AI-privacy-policy-research/1.0)"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def html_text(content: bytes) -> tuple[str, str]:
    soup = BeautifulSoup(content, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for tag in soup(["script", "style", "nav", "footer", "noscript", "svg"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return normalize(main.get_text("\n")), title


def pdf_text(path: Path) -> str:
    return normalize("\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages))


def displayed_date(text: str) -> str:
    patterns = [
        r"(?:Effective|Last updated|Updated|Last Updated|Effective Date)\s*:?[ \t]*(?:on\s+)?"
        r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2})",
        r"(?:Effective|Last updated|Updated|Last Updated|Effective Date)\s*:?[ \t]*(\d{1,2}[-/]\d{1,2}[-/]20\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text[:12000], flags=re.IGNORECASE)
        if match:
            value = match.group(1)
            for fmt in ("%B %d, %Y", "%m-%d-%Y", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    return date.strftime(__import__("datetime").datetime.strptime(value, fmt), "%Y-%m-%d")
                except ValueError:
                    pass
            return value
    return ""


def save_log(frame: pd.DataFrame) -> None:
    frame.to_csv(LOG, index=False, encoding="utf-8", lineterminator="\n")


def collect() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    CLEAN.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(LOG, dtype=str).fillna("")

    # The researcher visually approved C01 in the dashboard workflow.
    c01 = frame["candidate_id"].eq("C01")
    frame.loc[c01, "qa_status"] = "passed"
    frame.loc[c01, "qa_date"] = ACCESS_DATE
    frame.loc[c01, "qa_reviewer"] = "researcher"
    save_log(frame)

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        "Referer": "https://www.google.com/",
    })

    for index, row in frame.iterrows():
        candidate = row["candidate_id"]
        if candidate == "C01":
            continue
        existing = list(RAW.glob(f"{candidate}_{ACCESS_DATE}_source.*"))
        clean_path = CLEAN / f"{candidate}.txt"
        if existing and clean_path.exists() and row["qa_status"] in {"awaiting_visual_qa", "passed"}:
            print(f"SKIP {candidate}: already collected", flush=True)
            continue
        try:
            response = session.get(row["url"], timeout=45, allow_redirects=True)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            is_pdf = "application/pdf" in content_type or response.url.lower().endswith(".pdf")
            suffix = ".pdf" if is_pdf else ".html"
            raw_path = RAW / f"{candidate}_{ACCESS_DATE}_source{suffix}"
            raw_path.write_bytes(response.content)
            if is_pdf:
                text = pdf_text(raw_path)
                title = row["organisation"] + " privacy policy"
            else:
                text, title = html_text(response.content)
            clean_path.write_text(text, encoding="utf-8", newline="\n")
            words = len(text.split())
            status = "awaiting_visual_qa" if words >= 300 else "flagged_short"
            frame.loc[index, "effective_date"] = displayed_date(text)
            frame.loc[index, "accessed_date"] = ACCESS_DATE
            frame.loc[index, "eligible"] = "pending_review"
            frame.loc[index, "raw_sha256"] = file_hash(raw_path)
            frame.loc[index, "clean_sha256"] = file_hash(clean_path)
            frame.loc[index, "raw_words"] = str(words)
            frame.loc[index, "clean_words"] = str(words)
            frame.loc[index, "qa_reviewer"] = ""
            frame.loc[index, "qa_status"] = status
            frame.loc[index, "qa_date"] = ""
            note = f"Downloaded from official page; final URL {response.url}; page title {title!r}; preliminary automatic clean"
            frame.loc[index, "notes"] = note
            print(f"OK {candidate}: words={words} status={status}", flush=True)
        except Exception as exc:
            frame.loc[index, "eligible"] = "pending"
            frame.loc[index, "qa_status"] = "download_failed"
            frame.loc[index, "notes"] = f"Collection error: {type(exc).__name__}: {exc}"
            print(f"FAILED {candidate}: {type(exc).__name__}: {exc}", flush=True)
        save_log(frame)
        time.sleep(0.75)


if __name__ == "__main__":
    collect()
