from __future__ import annotations
import re
from pathlib import Path
from bs4 import BeautifulSoup
from pypdf import PdfReader
from .common import ROOT, load_config, read_csv, sha256_text

def extract(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}: return path.read_text(encoding="utf-8-sig", errors="replace")
    if suffix in {".html", ".htm"}:
        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "noscript"]): tag.decompose()
        return soup.get_text("\n")
    if suffix == ".pdf": return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    raise ValueError(f"Unsupported source type: {path.name}")

def clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"

def apply_boundaries(text: str, policy_id: str, cfg: dict) -> str:
    boundaries = cfg.get("preprocess_boundaries", {}).get(policy_id, {})
    start = boundaries.get("start")
    end = boundaries.get("end")
    if start:
        position = text.find(start)
        if position < 0:
            raise ValueError(f"Start boundary not found for {policy_id}: {start}")
        text = text[position:]
    if end:
        position = text.find(end)
        if position < 0:
            raise ValueError(f"End boundary not found for {policy_id}: {end}")
        text = text[:position]
    return text

def preprocess_all() -> int:
    cfg = load_config(); raw = ROOT / cfg["paths"]["raw"]; out = ROOT / cfg["paths"]["clean"]
    rows = read_csv(ROOT / cfg["paths"]["metadata"]); count = 0
    for row in rows:
        if row.get("include", "yes").lower() != "yes": continue
        source = raw / row["source_filename"]
        if not source.exists(): print(f"SKIP missing {source}"); continue
        value = clean(apply_boundaries(extract(source), row["policy_id"], cfg)); target = out / f'{row["policy_id"]}.txt'
        target.parent.mkdir(parents=True, exist_ok=True); target.write_text(value, encoding="utf-8")
        print(f"WROTE {target.relative_to(ROOT)} words={len(value.split())} sha256={sha256_text(value)[:12]}"); count += 1
    return count
