"""Evidence-linked explorer for the privacy-summary study."""

from __future__ import annotations

import html
import json
import re
from collections import Counter
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "v2_prompt_intervention_v1_2"
SOURCE_DIR = ROOT / "data" / "pilot" / "clean"
OUTPUT_DIR = DATA / "outputs"
METRICS_PATH = DATA / "evaluations" / "readability_compression.csv"
BLINDING_KEY_PATH = DATA / "anonymised" / "BLINDING_KEY_RESTRICTED.csv"
GEMINI_PATH = DATA / "evaluations" / "gemini_statement_verification_all.csv"
MINICHECK_PATH = DATA / "evaluations" / "minicheck" / "minicheck_v12_statement_scores_FINAL.csv"
GEMINI_COVERAGE_PATH = DATA / "evaluations" / "gemini_final_coverage" / "gemini_final_coverage_all.csv"
HUMAN_PATH = DATA / "human_evaluation" / "adjudication" / "human_phase1_all_faithfulness_ratings.csv"
HUMAN_ADJUDICATION_PATH = DATA / "human_evaluation" / "adjudication" / "faithfulness_disagreements_ADJUDICATED.csv"
SOURCE_UNITS_PATH = DATA / "human_evaluation" / "adjudication" / "frozen_source_units_FINAL.csv"
HUMAN_COVERAGE_PATH = DATA / "evaluations" / "final_coverage_results" / "final_human_and_gemini_coverage.csv"
COVERAGE_PACKAGES = DATA / "human_evaluation" / "coverage_phase2"
HUMAN_COVERAGE_RATINGS_PATH = DATA / "evaluations" / "final_coverage_results" / "human_coverage_ratings_all.csv"
OPP_ROOT = ROOT / "data" / "opp115"
OPP_EXPERIMENT = OPP_ROOT / "experiment"
OPP_OUTPUT_DIR = OPP_EXPERIMENT / "outputs"
OPP_SOURCE_DIR = OPP_ROOT / "frozen" / "clean"
OPP_METADATA_PATH = OPP_ROOT / "frozen" / "metadata" / "policies.csv"
OPP_KEY_PATH = OPP_EXPERIMENT / "anonymised" / "BLINDING_KEY_RESTRICTED.csv"
OPP_CLAIMS_PATH = OPP_EXPERIMENT / "faithfulness" / "prepared" / "claim_candidates.csv"
OPP_GEMINI_PATH = OPP_EXPERIMENT / "evaluations" / "faithfulness" / "gemini_claim_scores_batched__gemini-3.5-flash-lite__source-passage-ids-v2.csv"
OPP_MINICHECK_PATH = OPP_EXPERIMENT / "evaluations" / "faithfulness" / "minicheck_opp115_claim_scores_FINAL.csv"
OPP_COVERAGE_PATH = OPP_EXPERIMENT / "coverage_v3" / "evaluations" / "gemini_coverage_scores.csv"
OPP_UNITS_PATH = OPP_EXPERIMENT / "coverage_v3" / "source_units" / "frozen_source_units.csv"
TAXONOMY_MAPPING_PATH = OPP_EXPERIMENT / "taxonomy_v3" / "evaluations" / "gemini_taxonomy_mappings.csv"
TAXONOMY_VALIDATION_PATH = OPP_EXPERIMENT / "taxonomy_v3" / "analysis" / "historical_annotation_validation.csv"
TAXONOMY_DIFFERENCE_PATH = OPP_EXPERIMENT / "taxonomy_v3" / "analysis" / "historical_contemporary_difference.csv"

POLICIES = {
    "PILOT01": "Mozilla · short",
    "PILOT02": "DuckDuckGo · medium",
    "PILOT03": "Automattic · long",
}
MODELS = {"gpt": "GPT", "llama": "Llama", "mistral": "Mistral"}
SETS = {"basic": "Basic", "safety_focused": "Safety-focused"}
STRATEGIES = {"direct": "Zero-shot baseline", "role_guided": "Role-based", "structured": "Structured-reasoning"}
VIEW_TITLES = {
    "Summary verification": "Summary claim verification",
    "Source coverage": "Policy-specific coverage",
    "Evaluator agreement": "Evaluator agreement",
    "Study overview": "Study overview",
    "OPP-115 explorer": "OPP-115 evidence explorer",
    "Taxonomy mapping": "OPP taxonomy mapping",
}
FILE_PATTERN = re.compile(
    r"(PILOT\d+)__(gpt|llama|mistral)__(basic|safety_focused)_(direct|role_guided|structured)__r(\d+)\.txt$"
)


@st.cache_data(show_spinner=False)
def load_summaries() -> pd.DataFrame:
    rows = []
    if not OUTPUT_DIR.exists():
        return pd.DataFrame(columns=["policy_id", "model_family", "prompt_set", "strategy", "replicate", "text", "path"])
    for path in sorted(OUTPUT_DIR.glob("PILOT*/*.txt")):
        match = FILE_PATTERN.match(path.name)
        if not match:
            continue
        policy, model, prompt_set, strategy, replicate = match.groups()
        rows.append({
            "policy_id": policy,
            "model_family": model,
            "prompt_set": prompt_set,
            "strategy": strategy,
            "replicate": int(replicate),
            "text": path.read_text(encoding="utf-8"),
            "path": str(path),
        })
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def load_metrics() -> pd.DataFrame:
    if not METRICS_PATH.exists():
        return pd.DataFrame()
    frame = pd.read_csv(METRICS_PATH)
    parts = frame["prompt_strategy"].str.extract(r"^(basic|safety_focused)_(direct|role_guided|structured)$")
    frame["prompt_set"] = parts[0]
    frame["strategy"] = parts[1]
    frame["words"] = pd.to_numeric(frame["words"], errors="coerce")
    frame["flesch_reading_ease"] = pd.to_numeric(frame["flesch_reading_ease"], errors="coerce")
    return frame


@st.cache_data(show_spinner=False)
def load_evaluations() -> tuple[pd.DataFrame, ...]:
    def read(path: Path) -> pd.DataFrame:
        return pd.read_csv(path, keep_default_na=False) if path.exists() else pd.DataFrame()

    return (
        read(BLINDING_KEY_PATH), read(GEMINI_PATH), read(MINICHECK_PATH),
        read(GEMINI_COVERAGE_PATH), read(SOURCE_UNITS_PATH), read(HUMAN_PATH),
        read(HUMAN_ADJUDICATION_PATH), read(HUMAN_COVERAGE_PATH),
    )


@st.cache_data(show_spinner=False)
def load_source(policy_id: str) -> str:
    path = SOURCE_DIR / f"{policy_id}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


@st.cache_data(show_spinner=False)
def load_human_coverage_ratings() -> pd.DataFrame:
    if HUMAN_COVERAGE_RATINGS_PATH.exists():
        return pd.read_csv(HUMAN_COVERAGE_RATINGS_PATH, keep_default_na=False)
    frames = []
    for evaluator in ("A1", "A2", "A3"):
        path = COVERAGE_PACKAGES / f"Researcher_{evaluator}_Package" / f"human_v12_{evaluator}_COVERAGE_PHASE2_COMPLETED.xlsx"
        if path.exists():
            frame = pd.read_excel(path, sheet_name="Coverage", keep_default_na=False)
            frame["evaluator"] = evaluator
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


@st.cache_data(show_spinner=False)
def load_opp_summaries() -> pd.DataFrame:
    rows = []
    pattern = re.compile(r"(OPP\d+)__(gpt|llama|mistral)__(basic|safety_focused)_(direct|role_guided|structured)__r(\d+)\.txt$")
    for path in sorted(OPP_OUTPUT_DIR.glob("OPP*/*.txt")):
        match = pattern.match(path.name)
        if not match:
            continue
        policy, model, prompt_set, strategy, replicate = match.groups()
        rows.append({"policy_id": policy, "model_family": model, "prompt_set": prompt_set,
                     "strategy": strategy, "replicate": int(replicate),
                     "text": path.read_text(encoding="utf-8"), "path": str(path)})
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def load_opp_data() -> tuple[pd.DataFrame, ...]:
    def read(path: Path) -> pd.DataFrame:
        return pd.read_csv(path, keep_default_na=False) if path.exists() else pd.DataFrame()
    return (read(OPP_METADATA_PATH), read(OPP_KEY_PATH), read(OPP_CLAIMS_PATH),
            read(OPP_GEMINI_PATH), read(OPP_MINICHECK_PATH), read(OPP_COVERAGE_PATH),
            read(OPP_UNITS_PATH), read(TAXONOMY_MAPPING_PATH),
            read(TAXONOMY_VALIDATION_PATH), read(TAXONOMY_DIFFERENCE_PATH))


@st.cache_data(show_spinner=False)
def load_opp_source(policy_id: str) -> str:
    path = OPP_SOURCE_DIR / f"{policy_id}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse_json_list(value: object) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def blind_id_for(row: pd.Series, key: pd.DataFrame) -> str:
    if key.empty:
        return ""
    prompt_strategy = f"{row['prompt_set']}_{row['strategy']}"
    match = key[
        (key["policy_id"] == row["policy_id"])
        & (key["model_family"] == row["model_family"])
        & (key["prompt_strategy"] == prompt_strategy)
        & (key["replicate"].astype(str) == str(row["replicate"]))
    ]
    return str(match.iloc[0]["blind_id"]) if len(match) == 1 else ""


def verdict_style(label: str) -> tuple[str, str, str, str]:
    key = str(label).casefold()
    if "partial" in key or "distortion" in key:
        return "partial", "#fff4dc", "#9b6200", "◐"
    if any(term in key for term in ("not covered", "unsupported", "hallucination", "contradicted", "omitted")):
        return "unsupported", "#ffebe9", "#b42318", "×"
    if "supported" in key or "covered" in key:
        return "supported", "#e8f6ef", "#16794a", "✓"
    return "pending", "#eef2f6", "#667085", "…"


def badge_html(label: str, item_id: str = "") -> str:
    _, background, colour, icon = verdict_style(label)
    identifier = f'<span class="pv-item-id">{html.escape(item_id)}</span>' if item_id else ""
    return (
        '<div class="pv-status-row">'
        f'<span class="pv-badge" style="background:{background};color:{colour}">{icon}&nbsp; {html.escape(str(label))}</span>'
        f"{identifier}</div>"
    )


def source_context(source: str, quote: str, margin: int = 360) -> str:
    if not quote:
        return "No supporting source quotation was identified."
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", source) if part.strip()]
    for index, paragraph in enumerate(paragraphs):
        if quote not in paragraph:
            continue
        selected = []
        if index > 0:
            previous = paragraphs[index - 1]
            looks_like_heading = len(previous) <= 160 and len(previous.splitlines()) <= 2
            if looks_like_heading:
                selected.append(previous)
        selected.append(paragraph)
        return "\n\n".join(selected)

    position = source.find(quote)
    if position < 0:
        return quote
    start = source.rfind("\n\n", 0, position)
    end = source.find("\n\n", position + len(quote))
    start = 0 if start < 0 else start + 2
    end = len(source) if end < 0 else end
    return source[start:end].strip()


def source_reader_html(source: str, quote: str, full: bool = False) -> str:
    display = source if full else source_context(source, quote)
    escaped = html.escape(display)
    escaped_quote = html.escape(quote)
    if quote and escaped_quote in escaped:
        escaped = escaped.replace(escaped_quote, f"<mark>{escaped_quote}</mark>", 1)
    mode = " full" if full else ""
    return f'<div class="pv-source-reader{mode}">{escaped}</div>'


def researcher_summary(
    human: pd.DataFrame, adjudicated: pd.DataFrame, statement_id: str
) -> tuple[str, str]:
    if not adjudicated.empty:
        final = adjudicated[adjudicated["statement_id"] == statement_id]
        if not final.empty:
            return str(final.iloc[0]["final_label"]), "Adjudicated"
    if human.empty:
        return "Pending", "Not yet available"
    rows = human[human["statement_id"] == statement_id]
    labels = [str(label) for label in rows.get("label", pd.Series(dtype=str)).tolist() if str(label)]
    if not labels:
        return "Pending", "Not yet available"
    counts = Counter(labels)
    label, count = counts.most_common(1)[0]
    if count > len(labels) / 2 or count == len(labels):
        return label, f"{count}/{len(labels)} agree"
    return "Disagreement", "Adjudication required"


def human_statement_detail(
    human: pd.DataFrame, adjudicated: pd.DataFrame, statement_id: str
) -> tuple[str, str, str, str, pd.DataFrame]:
    rows = human[human["statement_id"] == statement_id].copy() if not human.empty else pd.DataFrame()
    final = adjudicated[adjudicated["statement_id"] == statement_id] if not adjudicated.empty else pd.DataFrame()
    if not final.empty:
        item = final.iloc[0]
        return (
            str(item.get("final_label", "Pending")),
            "Final adjudicated decision",
            str(item.get("final_evidence", "")),
            str(item.get("adjudication_reason", "")),
            rows,
        )
    label, note = researcher_summary(human, adjudicated, statement_id)
    evidence = ""
    reason = ""
    if not rows.empty:
        evidence_values = [str(v) for v in rows.get("exact_source_evidence", pd.Series(dtype=str)) if str(v)]
        reason_values = [str(v) for v in rows.get("reason", pd.Series(dtype=str)) if str(v)]
        evidence = Counter(evidence_values).most_common(1)[0][0] if evidence_values else ""
        reason = reason_values[0] if reason_values else ""
    return label, note, evidence, reason, rows


def cohen_kappa(left: pd.Series, right: pd.Series) -> float:
    pairs = pd.DataFrame({"left": left.astype(str), "right": right.astype(str)}).dropna()
    if pairs.empty:
        return float("nan")
    observed = (pairs["left"] == pairs["right"]).mean()
    labels = sorted(set(pairs["left"]) | set(pairs["right"]))
    expected = sum((pairs["left"] == label).mean() * (pairs["right"] == label).mean() for label in labels)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def final_human_statement_frame(human: pd.DataFrame, adjudicated: pd.DataFrame) -> pd.DataFrame:
    if human.empty:
        return pd.DataFrame(columns=["statement_id", "final_human_label"])
    rows = []
    final_lookup = adjudicated.set_index("statement_id")["final_label"].to_dict() if not adjudicated.empty else {}
    for statement_id, group in human.groupby("statement_id"):
        label = str(final_lookup.get(statement_id, Counter(group["label"].astype(str)).most_common(1)[0][0]))
        rows.append({"statement_id": statement_id, "final_human_label": label})
    return pd.DataFrame(rows)


def evaluator_rows_html(mini_label: str, mini_note: str, gemini_label: str, human_label: str, human_note: str) -> str:
    rows = [
        ("MiniCheck", mini_label, mini_note),
        ("Gemini", gemini_label, "Evidence cited"),
        ("Researchers", human_label, human_note),
    ]
    content = "".join(
        '<div class="pv-eval-row">'
        f'<span class="pv-eval-name">{html.escape(name)}</span>'
        f'<span>{html.escape(str(label))}</span>'
        f'<span class="pv-eval-note">{html.escape(str(note))}</span>'
        "</div>"
        for name, label, note in rows
    )
    return f'<div class="pv-evaluator-list">{content}</div>'


def agreement_cards_html(cards: list[tuple[str, str, str]]) -> str:
    """Render agreement measures with the value and its interpretation kept together."""
    content = "".join(
        '<div class="pv-agreement-card">'
        f'<div class="pv-agreement-title">{html.escape(title)}</div>'
        f'<div class="pv-agreement-value">{html.escape(value)}</div>'
        f'<div class="pv-agreement-note">{html.escape(note)}</div>'
        '</div>'
        for title, value, note in cards
    )
    return f'<div class="pv-agreement-grid">{content}</div>'


st.set_page_config(page_title="Privacy Summary Verifier", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
st.markdown(
    """
    <style>
    :root { --pv-bg:#f4f6f8; --pv-surface:#fff; --pv-surface-2:#f7f9fb; --pv-text:#172033; --pv-muted:#667085; --pv-line:#dce2e8; --pv-navy:#173d67; --pv-blue-soft:#eaf3fc; --pv-green:#16794a; --pv-amber:#9b6200; --pv-red:#b42318; }
    html, body, .stApp, .stApp button, .stApp input, .stApp textarea, .stApp select {
      font-family:Inter,"Segoe UI",ui-sans-serif,system-ui,-apple-system,sans-serif!important;
    }
    .stApp { background:var(--pv-bg); color:var(--pv-text); }
    [data-testid="stSidebar"], [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"], #MainMenu, footer { display:none!important; }
    .block-container { max-width:none!important; padding:7px 8px 12px!important; }
    div[data-testid="stVerticalBlock"] { gap:.62rem; }
    div[data-testid="stHorizontalBlock"] { gap:14px; }
    .st-key-pv_topbar { background:var(--pv-surface); border:1px solid var(--pv-line); border-radius:14px 14px 0 0; padding:7px 14px; }
    .st-key-pv_topbar div[data-testid="stVerticalBlock"] { gap:.2rem; }
    .pv-brand { display:flex; align-items:center; gap:10px; min-height:40px; }
    .pv-mark { width:34px; height:34px; display:grid; place-items:center; border-radius:8px; background:var(--pv-navy); color:#fff; font-size:17px; }
    .pv-brand strong { display:block; font-size:15px; font-weight:650; line-height:1.2; }
    .pv-brand span { display:block; color:var(--pv-muted); font-size:12px; margin-top:2px; }
    .pv-top-label { color:var(--pv-text); font-size:12px; text-align:right; white-space:nowrap; }
    .st-key-pv_topbar [data-baseweb="select"] > div { background:var(--pv-surface-2); border-color:var(--pv-line); min-height:38px; }
    .st-key-pv_nav { min-height:calc(100vh - 69px); background:var(--pv-surface); border:1px solid var(--pv-line); border-top:0; border-radius:0 0 0 12px; padding:15px 10px; }
    .pv-kicker { color:var(--pv-muted); text-transform:uppercase; letter-spacing:.08em; font-size:11px; margin:2px 8px 7px; }
    .st-key-pv_nav .stButton button { justify-content:flex-start; border:0; box-shadow:none; background:transparent; color:var(--pv-text); min-height:39px; padding:8px 10px; font-size:14px; }
    .st-key-pv_nav .stButton button:hover { background:var(--pv-surface-2); color:var(--pv-navy); }
    .st-key-pv_nav .stButton button[kind="primary"] { background:var(--pv-blue-soft); color:var(--pv-navy); font-weight:600; }
    .pv-side-note { margin:20px 7px 0; padding-top:15px; border-top:1px solid var(--pv-line); color:var(--pv-muted); font-size:12px; line-height:1.55; }
    .pv-context { display:flex; flex-wrap:wrap; align-items:baseline; gap:7px 17px; margin:7px 0 7px; }
    .pv-context h1 { margin:0; font-size:20px; font-weight:650; }
    .pv-meta { color:var(--pv-muted); font-size:12px; }
    .st-key-pv_left, .st-key-pv_right, .st-key-pv_single_panel { background:var(--pv-surface); border:1px solid var(--pv-line); border-radius:12px; overflow:hidden; padding:0; }
    .st-key-pv_right { padding-bottom:16px; gap:.75rem!important; }
    .st-key-pv_right > [data-testid="stElementContainer"]:not(:first-child),
    .st-key-pv_right > [data-testid="stLayoutWrapper"] { margin-left:16px; margin-right:16px; width:auto!important; }
    .pv-panel-head { display:flex; align-items:center; gap:10px; min-height:52px; padding:13px 16px; border-bottom:1px solid var(--pv-line); }
    .pv-panel-head h2 { margin:0; font-size:15px; font-weight:650; }
    .pv-legend { margin-left:auto; display:flex; flex-wrap:wrap; gap:10px; color:var(--pv-muted); font-size:11px; }
    .pv-dot { width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:4px; }
    .st-key-pv_claim_list { padding:8px 12px 12px; max-height:calc(100vh - 235px); overflow-y:auto; }
    .st-key-pv_claim_list div[data-testid="stVerticalBlock"] { gap:.28rem; }
    [class*="st-key-pv_claim_"] .stButton button { width:100%; justify-content:flex-start; text-align:left; white-space:normal; line-height:1.46; font-size:13.5px; min-height:unset; padding:9px 10px; border:0; border-left:4px solid transparent; border-radius:7px; background:transparent; box-shadow:none; color:var(--pv-text); }
    [class*="st-key-pv_claim_"] .stButton button:hover { background:#f0f4f8; color:var(--pv-text); }
    [class*="st-key-pv_claim_"] .stButton button[kind="primary"] { background:#e2eaf3; color:var(--pv-text); box-shadow:inset 0 0 0 1px #c9d6e4; }
    [class*="st-key-pv_claim_supported_"] .stButton button { border-left-color:var(--pv-green); }
    [class*="st-key-pv_claim_partial_"] .stButton button { border-left-color:var(--pv-amber); }
    [class*="st-key-pv_claim_unsupported_"] .stButton button { border-left-color:var(--pv-red); }
    [class*="st-key-pv_claim_pending_"] .stButton button { border-left-color:#98a2b3; }
    .pv-inspector { padding:17px 18px 18px; }
    .pv-status-row { display:flex; align-items:center; gap:8px; margin:0 0 12px; }
    .pv-badge { display:inline-flex; align-items:center; border-radius:999px; padding:5px 9px; font-size:12px; font-weight:650; }
    .pv-item-id { color:var(--pv-muted); font-size:11px; }
    .pv-label { color:var(--pv-muted); text-transform:uppercase; letter-spacing:.06em; font-size:10.5px; font-weight:650; margin:10px 0 6px; }
    .pv-why-label { margin-top:18px; }
    .pv-evaluator-label { margin-top:18px; }
    .pv-selected, .pv-explanation { margin:0 0 5px; font-size:13.5px!important; line-height:1.52!important; font-weight:400; }
    .pv-quote { margin:0; padding:10px 11px; background:var(--pv-surface-2); border-left:3px solid var(--pv-navy); border-radius:6px; font-size:12.5px; line-height:1.5; }
    [class*="st-key-pv_source_toggle"] [data-testid="stSegmentedControl"] { margin:2px 0 10px; }
    [class*="st-key-pv_source_toggle"] button { min-height:34px; padding:6px 10px; font-size:12px; border-color:var(--pv-line)!important; color:var(--pv-navy)!important; }
    [class*="st-key-pv_source_toggle"] button p { color:inherit!important; }
    [class*="st-key-pv_source_toggle"] button[kind="segmented_controlActive"], [class*="st-key-pv_source_toggle"] button[data-testid="stBaseButton-segmented_controlActive"] { background:var(--pv-navy)!important; background-color:var(--pv-navy)!important; color:#fff!important; border-color:var(--pv-navy)!important; box-shadow:none!important; }
    .pv-source-reader { max-height:170px; overflow-y:auto; white-space:pre-wrap; background:var(--pv-surface-2); border:1px solid var(--pv-line); border-radius:8px; padding:13px; color:var(--pv-text); font-family:Inter,"Segoe UI",ui-sans-serif,system-ui,-apple-system,sans-serif!important; font-size:13.5px; font-weight:400; line-height:1.55; }
    .pv-source-reader.full { max-height:300px; }
    .pv-source-reader mark { background:#fff0c2; color:var(--pv-text); padding:1px 2px; }
    .pv-reason-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:11px; }
    .pv-reason-part { background:var(--pv-surface-2); border-radius:7px; padding:12px; font-size:13.5px; font-weight:400; line-height:1.5; }
    .pv-reason-part strong { display:block; margin-bottom:6px; font-size:13px; font-weight:650; }
    .pv-evaluator-list { margin-top:5px; }
    .pv-eval-row { display:grid; grid-template-columns:90px minmax(0,1fr) auto; align-items:center; gap:10px; padding:10px 0; border-bottom:1px solid var(--pv-line); font-size:13.5px; font-weight:400; line-height:1.45; }
    .pv-eval-row:last-child { border-bottom:0; }
    .pv-eval-name, .pv-eval-note { color:var(--pv-muted); }
    [class*="st-key-pv_eval_card_"] { background:#fbfcfd; border:1px solid var(--pv-line); border-radius:10px; padding:15px 15px 16px; margin-top:4px; }
    [class*="st-key-pv_eval_card_"] div[data-testid="stVerticalBlock"] { gap:.45rem; }
    .pv-evaluator-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:3px; }
    .pv-evaluator-name { font-size:15px; font-weight:680; }
    .pv-evaluator-desc { color:var(--pv-muted); font-size:11.5px; line-height:1.45; margin-top:2px; }
    .pv-score { text-align:right; font-size:20px; font-weight:700; color:var(--pv-navy); white-space:nowrap; }
    .pv-score span { display:block; color:var(--pv-muted); font-size:10.5px; font-weight:500; margin-top:1px; }
    .pv-section-intro { color:var(--pv-muted); font-size:13.5px; line-height:1.55; margin:0 0 14px; max-width:980px; }
    .pv-callout { background:#eef5fb; border-left:4px solid var(--pv-navy); border-radius:7px; padding:12px 14px; font-size:13px; line-height:1.5; margin:8px 0 16px; }
    .st-key-pv_single_panel { padding-bottom:18px; }
    .st-key-pv_single_panel > [data-testid="stElementContainer"]:not(:first-child),
    .st-key-pv_single_panel > [data-testid="stLayoutWrapper"] { margin-left:18px; margin-right:18px; width:auto!important; }
    .st-key-pv_single_panel > [data-testid="stElementContainer"]:nth-child(2) { margin-top:7px; }
    .pv-agreement-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:5px 0 14px; }
    .pv-agreement-card { min-height:112px; background:var(--pv-surface-2); border:1px solid var(--pv-line); border-radius:9px; padding:14px 15px; display:flex; flex-direction:column; }
    .pv-agreement-title { font-size:12.5px; line-height:1.4; color:var(--pv-text); }
    .pv-agreement-value { font-size:22px; line-height:1.2; font-weight:650; color:var(--pv-navy); margin:7px 0 5px; }
    .pv-agreement-note { color:var(--pv-muted); font-size:11.5px; line-height:1.4; margin-top:auto; }
    .pv-study-flow { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin:12px 0 18px; }
    .pv-flow-card { background:var(--pv-surface-2); border:1px solid var(--pv-line); border-radius:9px; padding:13px; font-size:12.5px; line-height:1.5; }
    .pv-flow-card strong { display:block; color:var(--pv-navy); margin-bottom:5px; }
    .st-key-pv_unit_list { padding:2px 0; max-height:calc(100vh - 215px); overflow-y:auto; }
    .st-key-pv_unit_list div[data-testid="stVerticalBlock"] { gap:0; }
    [class*="st-key-pv_unit_"] { border-bottom:1px solid var(--pv-line); }
    [class*="st-key-pv_unit_"] div[data-testid="stHorizontalBlock"] { gap:5px; align-items:center; }
    [class*="st-key-pv_unit_"] .stButton button { width:100%; justify-content:flex-start; text-align:left; white-space:pre-line; line-height:1.38; min-height:unset; padding:10px 15px; border:0; border-left:4px solid transparent; border-radius:0; background:transparent; box-shadow:none; color:var(--pv-text); font-size:12px; }
    [class*="st-key-pv_unit_"] .stButton button:hover { background:#f0f4f8; color:var(--pv-navy); }
    [class*="st-key-pv_unit_"] .stButton button[kind="primary"] { background:#e2eaf3; color:var(--pv-navy); box-shadow:inset 0 0 0 1px #c9d6e4; }
    [class*="st-key-pv_unit_supported_"] .stButton button { border-left-color:var(--pv-green); }
    [class*="st-key-pv_unit_partial_"] .stButton button { border-left-color:var(--pv-amber); }
    [class*="st-key-pv_unit_unsupported_"] .stButton button { border-left-color:var(--pv-red); }
    .pv-unit-status { padding:0 12px 0 2px; text-align:right; font-size:10.5px; font-style:italic; white-space:nowrap; }
    .pv-unit-status.supported { color:var(--pv-green); } .pv-unit-status.partial { color:var(--pv-amber); } .pv-unit-status.unsupported { color:var(--pv-red); }
    .pv-metric-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:9px; margin:10px 0 4px; }
    .pv-metric { background:var(--pv-surface-2); border:1px solid var(--pv-line); border-radius:9px; padding:11px; }
    .pv-metric strong { display:block; font-size:20px; margin-top:3px; }
    .pv-metric span { color:var(--pv-muted); font-size:11px; }
    [data-testid="stMetric"] { background:var(--pv-surface-2); border:1px solid var(--pv-line); border-radius:9px; padding:10px 12px; }
    [data-testid="stMetricValue"] { font-size:1.35rem; }
    .stDownloadButton button { border:1px solid var(--pv-line); background:var(--pv-surface); color:var(--pv-navy); font-size:11px; min-height:34px; }
    .pv-footer { color:var(--pv-muted); font-size:10.5px; text-align:right; padding:3px 2px 0; }
    @media (max-width:1000px) {
      .block-container { padding:8px!important; }
      .st-key-pv_nav { min-height:calc(100vh - 69px); padding:12px 5px; }
      .st-key-pv_nav .pv-kicker, .pv-side-note { display:none; }
      .st-key-pv_nav .stButton button { justify-content:center; padding:7px 2px; }
      .st-key-pv_nav .stButton button p { width:1.25em; overflow:hidden; white-space:nowrap; font-size:0; }
      div[class*="st-key-pv_nav_Summary-"] .stButton button p::before { content:"✓"; font-size:15px; }
      div[class*="st-key-pv_nav_Source-"] .stButton button p::before { content:"≡"; font-size:15px; }
      div[class*="st-key-pv_nav_Evaluator-"] .stButton button p::before { content:"≋"; font-size:15px; }
      div[class*="st-key-pv_nav_Study-"] .stButton button p::before { content:"○"; font-size:15px; }
      .pv-top-label { font-size:10px; }
      .pv-brand span { display:none; }
      .pv-reason-grid { grid-template-columns:1fr; }
      .pv-eval-row { grid-template-columns:76px minmax(0,1fr); }
      .pv-eval-note { grid-column:2; }
      .pv-study-flow { grid-template-columns:1fr 1fr; }
      .pv-agreement-grid { grid-template-columns:1fr; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

summaries = load_summaries()
metrics = load_metrics()
(
    blinding_key, gemini_scores, minicheck_scores, coverage_scores, source_units,
    human_scores, human_adjudication, human_coverage,
) = load_evaluations()
human_coverage_ratings = load_human_coverage_ratings()
final_human_statements = final_human_statement_frame(human_scores, human_adjudication)
opp_summaries = load_opp_summaries()
(
    opp_metadata, opp_key, opp_claims, opp_gemini, opp_minicheck, opp_coverage,
    opp_units, taxonomy_mapping, taxonomy_validation, taxonomy_difference,
) = load_opp_data()

if summaries.empty:
    st.error("No V1.2 summaries were found.")
    st.stop()

if "pv_view" not in st.session_state:
    st.session_state.pv_view = "Summary verification"
view = st.session_state.pv_view
opp_view = view in {"OPP-115 explorer", "Taxonomy mapping"}

with st.container(key="pv_topbar"):
    brand_col, prompt_label_col, prompt_col, summary_label_col, summary_col = st.columns([1.18, .28, .82, .28, 1.38], vertical_alignment="center", gap="small")
    with brand_col:
        st.markdown('<div class="pv-brand"><div class="pv-mark">⌕</div><div><strong>Privacy Summary Verifier</strong><span>Evidence-linked research prototype</span></div></div>', unsafe_allow_html=True)
    with prompt_label_col:
        st.markdown('<div class="pv-top-label">Prompt version</div>', unsafe_allow_html=True)
    with prompt_col:
        prompt_key = "pv_opp_prompt_set" if opp_view else "pv_prompt_set"
        prompt_set = st.selectbox("Prompt version", list(SETS), format_func=SETS.get, key=prompt_key, label_visibility="collapsed")
    active_summaries = opp_summaries if opp_view else summaries
    available = active_summaries[active_summaries["prompt_set"] == prompt_set].copy().sort_values(["policy_id", "model_family", "strategy", "replicate"])
    summary_options = available.index.tolist()
    summary_key = "pv_opp_summary_option" if opp_view else "pv_summary_option"
    if st.session_state.get(summary_key) not in summary_options:
        st.session_state.pop(summary_key, None)

    def summary_label(index: int) -> str:
        item = active_summaries.loc[index]
        active_key = opp_key if opp_view else blinding_key
        blind = blind_id_for(item, active_key) or "Summary"
        if opp_view:
            meta = opp_metadata[opp_metadata["policy_id"] == item["policy_id"]]
            organisation = str(meta.iloc[0]["organisation"]) if not meta.empty else str(item["policy_id"])
        else:
            organisation = POLICIES[item["policy_id"]].split(" · ")[0]
        return f"{blind} · {organisation} · {MODELS[item['model_family']]} · {STRATEGIES[item['strategy']]}"

    with summary_label_col:
        st.markdown('<div class="pv-top-label">Summary</div>', unsafe_allow_html=True)
    with summary_col:
        summary_index = st.selectbox("Select summary", summary_options, format_func=summary_label, key=summary_key, label_visibility="collapsed")

row = active_summaries.loc[summary_index]
policy_id, model, strategy = str(row["policy_id"]), str(row["model_family"]), str(row["strategy"])
summary_text, stem = str(row["text"]), Path(str(row["path"])).stem
blind_id = blind_id_for(row, opp_key if opp_view else blinding_key)
if opp_view:
    selected_meta = opp_metadata[opp_metadata["policy_id"] == policy_id]
    organisation = str(selected_meta.iloc[0]["organisation"]) if not selected_meta.empty else policy_id
    length_band = str(selected_meta.iloc[0]["length_band"]).lower() if not selected_meta.empty else ""
    policy_display = f"{organisation} · {length_band} · historical OPP-115"
else:
    policy_display = POLICIES[policy_id]

nav_col, main_col = st.columns([.14, .86], gap="small")
with nav_col:
    with st.container(key="pv_nav"):
        st.markdown('<div class="pv-kicker">Review</div>', unsafe_allow_html=True)
        for label, icon in (("Summary verification", "✓"), ("Source coverage", "≡"), ("Evaluator agreement", "≋"), ("Study overview", "○"), ("OPP-115 explorer", "▦"), ("Taxonomy mapping", "↔")):
            if st.button(f"{icon}  {label}", key=f"pv_nav_{label}", type="primary" if view == label else "secondary", use_container_width=True):
                st.session_state.pv_view = label
                st.rerun()
        st.markdown(
            f'<div class="pv-side-note">Policy: {html.escape(policy_display)}<br>Blind ID: {html.escape(blind_id)}</div>',
            unsafe_allow_html=True,
        )

with main_col:
    st.markdown(
        f'<div class="pv-context"><h1>{VIEW_TITLES[view]}</h1><span class="pv-meta">{html.escape(policy_display)} · {html.escape(SETS[prompt_set])} · {html.escape(MODELS[model])} · {html.escape(STRATEGIES[strategy])}</span></div>',
        unsafe_allow_html=True,
    )

    if view == "Summary verification":
        current_statements = gemini_scores[gemini_scores["blind_id"] == blind_id].copy() if not gemini_scores.empty else pd.DataFrame()
        if not current_statements.empty:
            current_statements["statement_number"] = current_statements["statement_id"].str.extract(r"ST(\d+)$")[0].astype(int)
            current_statements = current_statements.sort_values("statement_number").reset_index(drop=True)
        if current_statements.empty:
            st.info("The evaluated statements for this summary are unavailable.")
        else:
            if st.session_state.get("pv_claim_blind") != blind_id:
                st.session_state.pv_claim_blind, st.session_state.pv_claim_index = blind_id, 0
            chosen = min(int(st.session_state.get("pv_claim_index", 0)), len(current_statements) - 1)
            left, right = st.columns([1.28, .82], gap="medium")
            with left:
                with st.container(key="pv_left"):
                    st.markdown('<div class="pv-panel-head"><h2>Plain-English summary</h2><div class="pv-legend">Final researcher decision&nbsp; <span><span class="pv-dot" style="background:#16794a"></span>Supported</span><span><span class="pv-dot" style="background:#9b6200"></span>Partial</span><span><span class="pv-dot" style="background:#b42318"></span>Unsupported</span></div></div>', unsafe_allow_html=True)
                    with st.container(key="pv_claim_list"):
                        for index, statement in current_statements.iterrows():
                            display_label, _ = researcher_summary(human_scores, human_adjudication, str(statement["statement_id"]))
                            state, _, _, _ = verdict_style(display_label)
                            with st.container(key=f"pv_claim_{state}_{index}"):
                                if st.button(str(statement["statement_text"]), key=f"pv_statement_{blind_id}_{index}", type="primary" if index == chosen else "secondary", use_container_width=True):
                                    st.session_state.pv_claim_index = index
                                    st.rerun()
                    st.download_button("Download summary", summary_text, file_name=f"{stem}.txt", mime="text/plain", key="pv_download_summary")
            with right:
                statement = current_statements.iloc[chosen]
                statement_id = str(statement["statement_id"])
                mmatch = minicheck_scores[minicheck_scores["statement_id"] == statement_id] if not minicheck_scores.empty else pd.DataFrame()
                minicheck = mmatch.iloc[0] if not mmatch.empty else pd.Series(dtype=object)
                label = str(statement.get("label", "Pending evaluation"))
                evidence_quotes = parse_json_list(statement.get("evidence_quotes", "[]"))
                closest_quote = str(statement.get("closest_source_quote", ""))
                anchor_quote = evidence_quotes[0] if evidence_quotes else closest_quote
                supported = str(statement.get("supported_components", "")) or "No supported component was recorded."
                problematic = str(statement.get("problematic_components", "")) or "None detected."
                source = load_source(policy_id)
                human_label, human_note, human_evidence, human_reason, human_rows = human_statement_detail(
                    human_scores, human_adjudication, statement_id
                )
                mini_label = "Supported" if str(minicheck.get("predicted_supported", "")) == "1" else ("Unsupported" if str(minicheck.get("predicted_supported", "")) == "0" else "Pending")
                probability = str(minicheck.get("probability", ""))
                mini_note = f"p={float(probability):.3f}" if probability else "—"
                with st.container(key="pv_right"):
                    st.markdown('<div class="pv-panel-head"><h2>Evidence and judgement</h2></div>', unsafe_allow_html=True)
                    st.markdown('<div class="pv-inspector"><p class="pv-section-intro">Each evaluator keeps its own decision. The app does not combine them into an artificial overall label; the sentence colour on the left shows the final researcher decision.</p></div>', unsafe_allow_html=True)
                    with st.container(key="pv_eval_card_minicheck"):
                        score_display = f"{float(probability):.3f}" if probability else "—"
                        st.markdown(
                            f'<div class="pv-evaluator-head"><div><div class="pv-evaluator-name">1. MiniCheck</div><div class="pv-evaluator-desc">Binary source-support model</div></div><div class="pv-score">{score_display}<span>support probability</span></div></div>',
                            unsafe_allow_html=True,
                        )
                        st.markdown(badge_html(mini_label), unsafe_allow_html=True)
                        st.caption("MiniCheck returns a support decision and probability. It does not provide a quotation or written explanation.")
                    with st.container(key="pv_eval_card_gemini"):
                        st.markdown('<div class="pv-evaluator-head"><div><div class="pv-evaluator-name">2. Gemini</div><div class="pv-evaluator-desc">Evidence-citing LLM verifier</div></div></div>', unsafe_allow_html=True)
                        st.markdown(badge_html(label, statement_id), unsafe_allow_html=True)
                        with st.container(key="pv_source_toggle_gemini"):
                            source_mode = st.segmented_control(
                                "Gemini evidence view", ["Supporting evidence", "Full policy"],
                                default="Supporting evidence", label_visibility="collapsed",
                                key=f"pv_source_mode_gemini_{statement_id}",
                            )
                        st.markdown(source_reader_html(source, anchor_quote, source_mode == "Full policy"), unsafe_allow_html=True)
                        st.markdown('<div class="pv-label pv-why-label">Why Gemini assigned this label</div>', unsafe_allow_html=True)
                        st.markdown(f'<p class="pv-explanation">{html.escape(str(statement.get("explanation", "No explanation available.")))}</p>', unsafe_allow_html=True)
                        st.markdown(f'<div class="pv-reason-grid"><div class="pv-reason-part"><strong>Supported elements</strong>{html.escape(supported)}</div><div class="pv-reason-part"><strong>Problem detected</strong>{html.escape(problematic)}</div></div>', unsafe_allow_html=True)
                    with st.container(key="pv_eval_card_human"):
                        st.markdown('<div class="pv-evaluator-head"><div><div class="pv-evaluator-name">3. Researchers</div><div class="pv-evaluator-desc">Final decision from three blinded independent ratings</div></div></div>', unsafe_allow_html=True)
                        st.markdown(badge_html(human_label, human_note), unsafe_allow_html=True)
                        with st.container(key="pv_source_toggle_human"):
                            human_mode = st.segmented_control(
                                "Researcher evidence view", ["Supporting evidence", "Full policy"],
                                default="Supporting evidence", label_visibility="collapsed",
                                key=f"pv_source_mode_human_{statement_id}",
                            )
                        st.markdown(source_reader_html(source, human_evidence, human_mode == "Full policy"), unsafe_allow_html=True)
                        st.markdown('<div class="pv-label pv-why-label">Why researchers assigned this label</div>', unsafe_allow_html=True)
                        st.markdown(f'<p class="pv-explanation">{html.escape(human_reason or "No written reason was available.")}</p>', unsafe_allow_html=True)
                        if not human_rows.empty:
                            with st.expander("View A1–A3 judgements"):
                                for _, rating in human_rows.sort_values("evaluator").iterrows():
                                    st.markdown(f"**{rating.get('evaluator', 'Researcher')} · {rating.get('label', '')}**  \n{rating.get('reason', '')}")

    elif view == "Source coverage":
        current_coverage = coverage_scores[coverage_scores["blind_id"] == blind_id].copy() if not coverage_scores.empty else pd.DataFrame()
        current_units = source_units[source_units["policy_id"] == policy_id] if not source_units.empty else pd.DataFrame()
        if current_coverage.empty:
            st.info("Final Gemini coverage is unavailable for this summary.")
        else:
            current_coverage = current_coverage.reset_index(drop=True)
            if st.session_state.get("pv_unit_blind") != blind_id:
                st.session_state.pv_unit_blind, st.session_state.pv_unit_index = blind_id, 0
            unit_index = min(int(st.session_state.get("pv_unit_index", 0)), len(current_coverage) - 1)
            left, right = st.columns([1.15, .85], gap="medium")
            with left:
                with st.container(key="pv_left"):
                    st.markdown('<div class="pv-panel-head"><h2>Important source information</h2><div class="pv-legend">Final researcher decision&nbsp; <span><span class="pv-dot" style="background:#16794a"></span>Covered</span><span><span class="pv-dot" style="background:#9b6200"></span>Partial</span><span><span class="pv-dot" style="background:#b42318"></span>Not covered</span></div></div>', unsafe_allow_html=True)
                    with st.container(key="pv_unit_list"):
                        for index, unit_row in current_coverage.iterrows():
                            final_match = human_coverage[human_coverage["comparison_id"] == str(unit_row["comparison_id"])] if not human_coverage.empty else pd.DataFrame()
                            display_label = str(final_match.iloc[0]["final_human_label"]) if not final_match.empty else "Pending"
                            state, _, _, _ = verdict_style(display_label)
                            with st.container(key=f"pv_unit_{state}_{index}"):
                                unit_button, unit_status = st.columns([.84, .16], gap="small", vertical_alignment="center")
                                with unit_button:
                                    if st.button(f"{unit_row['important_information']}\nSource unit {unit_row['final_unit_id']}", key=f"pv_coverage_{blind_id}_{index}", type="primary" if index == unit_index else "secondary", use_container_width=True):
                                        st.session_state.pv_unit_index = index
                                        st.rerun()
                                with unit_status:
                                    st.markdown(f'<div class="pv-unit-status {state}">{html.escape(display_label)}</div>', unsafe_allow_html=True)
            with right:
                coverage_row = current_coverage.iloc[unit_index]
                selected_unit_id = str(coverage_row["final_unit_id"])
                unit_match = current_units[current_units["final_unit_id"] == selected_unit_id]
                unit = unit_match.iloc[0] if not unit_match.empty else pd.Series(dtype=object)
                source_quote = str(unit.get("exact_source_quote", ""))
                source = load_source(policy_id)
                human_match = human_coverage[
                    human_coverage["comparison_id"] == str(coverage_row["comparison_id"])
                ] if not human_coverage.empty else pd.DataFrame()
                human_coverage_label = (
                    str(human_match.iloc[0]["final_human_label"])
                    if not human_match.empty else "Pending"
                )
                human_coverage_note = (
                    "3/3 agree" if not human_match.empty and str(human_match.iloc[0]["resolution"]) == "unanimous"
                    else ("Adjudicated" if not human_match.empty else "Not available")
                )
                coverage_rating_rows = human_coverage_ratings[
                    human_coverage_ratings["comparison_id"] == str(coverage_row["comparison_id"])
                ].copy() if not human_coverage_ratings.empty else pd.DataFrame()
                human_summary_evidence = ""
                human_coverage_reason = ""
                if not coverage_rating_rows.empty:
                    evidence_values = [str(v) for v in coverage_rating_rows["summary_evidence"] if str(v)]
                    reason_values = [str(v) for v in coverage_rating_rows["reason"] if str(v)]
                    human_summary_evidence = Counter(evidence_values).most_common(1)[0][0] if evidence_values else ""
                    human_coverage_reason = reason_values[0] if reason_values else ""
                with st.container(key="pv_right"):
                    st.markdown('<div class="pv-panel-head"><h2>Evidence and judgement</h2></div>', unsafe_allow_html=True)
                    st.markdown('<div class="pv-inspector"><p class="pv-section-intro">Coverage asks whether each important source item appears in the summary. Gemini and the researchers keep separate labels; the item colour on the left shows the final researcher decision.</p></div>', unsafe_allow_html=True)
                    with st.container(key="pv_eval_card_coverage_minicheck"):
                        st.markdown('<div class="pv-evaluator-head"><div><div class="pv-evaluator-name">1. MiniCheck</div><div class="pv-evaluator-desc">Sentence-level source-support model</div></div></div>', unsafe_allow_html=True)
                        st.markdown(badge_html("Not evaluated"), unsafe_allow_html=True)
                        st.caption("MiniCheck checked generated sentences for source support. It was not used for source-to-summary omission assessment.")
                    summary_evidence = str(coverage_row.get("summary_evidence", "")) or "No corresponding summary evidence was found."
                    coverage_label = str(coverage_row["coverage_label"])
                    if coverage_label == "Covered":
                        coverage_gap = "None detected."
                    elif coverage_label == "Partially covered":
                        coverage_gap = "The source information is retained only partly or without all of its original detail."
                    else:
                        coverage_gap = "The important source information was not found in the summary."
                    with st.container(key="pv_eval_card_coverage_gemini"):
                        st.markdown('<div class="pv-evaluator-head"><div><div class="pv-evaluator-name">2. Gemini</div><div class="pv-evaluator-desc">Evidence-citing LLM coverage verifier</div></div></div>', unsafe_allow_html=True)
                        st.markdown(badge_html(coverage_label, selected_unit_id), unsafe_allow_html=True)
                        with st.container(key="pv_source_toggle_coverage_gemini"):
                            coverage_source_mode = st.segmented_control(
                                "Gemini coverage evidence view", ["Supporting evidence", "Full policy"],
                                default="Supporting evidence", label_visibility="collapsed",
                                key=f"pv_coverage_source_mode_gemini_{selected_unit_id}",
                            )
                        st.markdown(source_reader_html(source, source_quote, coverage_source_mode == "Full policy"), unsafe_allow_html=True)
                        st.markdown('<div class="pv-label pv-why-label">Why Gemini assigned this label</div>', unsafe_allow_html=True)
                        st.markdown(f'<p class="pv-explanation">{html.escape(str(coverage_row.get("explanation", "No explanation available.")))}</p>', unsafe_allow_html=True)
                        st.markdown(f'<div class="pv-reason-grid"><div class="pv-reason-part"><strong>Evidence in summary</strong>{html.escape(summary_evidence)}</div><div class="pv-reason-part"><strong>Coverage gap</strong>{html.escape(coverage_gap)}</div></div>', unsafe_allow_html=True)
                    with st.container(key="pv_eval_card_coverage_human"):
                        st.markdown('<div class="pv-evaluator-head"><div><div class="pv-evaluator-name">3. Researchers</div><div class="pv-evaluator-desc">Final decision from three blinded independent ratings</div></div></div>', unsafe_allow_html=True)
                        st.markdown(badge_html(human_coverage_label, human_coverage_note), unsafe_allow_html=True)
                        with st.container(key="pv_source_toggle_coverage_human"):
                            human_coverage_mode = st.segmented_control(
                                "Researcher coverage evidence view", ["Supporting evidence", "Full policy"],
                                default="Supporting evidence", label_visibility="collapsed",
                                key=f"pv_coverage_source_mode_human_{selected_unit_id}",
                            )
                        st.markdown(source_reader_html(source, source_quote, human_coverage_mode == "Full policy"), unsafe_allow_html=True)
                        st.markdown('<div class="pv-label pv-why-label">Why researchers assigned this label</div>', unsafe_allow_html=True)
                        st.markdown(f'<p class="pv-explanation">{html.escape(human_coverage_reason or "Final label after researcher agreement or adjudication.")}</p>', unsafe_allow_html=True)
                        st.markdown(f'<div class="pv-reason-grid"><div class="pv-reason-part"><strong>Evidence in summary</strong>{html.escape(human_summary_evidence or "No corresponding summary evidence was recorded.")}</div><div class="pv-reason-part"><strong>Resolution</strong>{html.escape(human_coverage_note)}</div></div>', unsafe_allow_html=True)
                        if not coverage_rating_rows.empty:
                            with st.expander("View A1–A3 judgements"):
                                for _, rating in coverage_rating_rows.sort_values("evaluator").iterrows():
                                    st.markdown(f"**{rating.get('evaluator', 'Researcher')} · {rating.get('coverage_label', '')}**  \n{rating.get('reason', '')}")

    elif view == "OPP-115 explorer":
        st.markdown('<div class="pv-callout"><strong>Historical benchmark:</strong> this page shows the same automated, evidence-linked checks used across 27 OPP-115 policies. Human ratings were reserved for the three contemporary policies.</div>', unsafe_allow_html=True)
        inspection = st.segmented_control("Inspection direction", ["Sentence source alignment", "Information coverage"], default="Sentence source alignment")
        opp_source = load_opp_source(policy_id)
        if inspection == "Sentence source alignment":
            claims = opp_claims[opp_claims["blind_id"] == blind_id].copy()
            claims = claims.merge(opp_gemini[["claim_id", "label", "evidence_quote", "explanation"]], on="claim_id", how="left")
            claims = claims.merge(opp_minicheck[["claim_id", "predicted_supported", "support_probability"]], on="claim_id", how="left")
            if claims.empty:
                st.info("No completed OPP sentence assessments are available for this summary.")
            else:
                if st.session_state.get("pv_opp_claim_blind") != blind_id:
                    st.session_state.pv_opp_claim_blind, st.session_state.pv_opp_claim_index = blind_id, 0
                chosen = min(int(st.session_state.get("pv_opp_claim_index", 0)), len(claims) - 1)
                left, right = st.columns([1.2, .8], gap="medium")
                with left:
                    with st.container(key="pv_left"):
                        st.markdown('<div class="pv-panel-head"><h2>Generated summary statements</h2><div class="pv-legend">Gemini decision&nbsp; <span><span class="pv-dot" style="background:#16794a"></span>Supported</span><span><span class="pv-dot" style="background:#9b6200"></span>Partial</span><span><span class="pv-dot" style="background:#b42318"></span>Unsupported</span></div></div>', unsafe_allow_html=True)
                        for index, claim in claims.reset_index(drop=True).iterrows():
                            state, _, _, _ = verdict_style(str(claim.get("label", "")))
                            with st.container(key=f"pv_claim_{state}_opp_{index}"):
                                if st.button(str(claim["claim_text"]), key=f"pv_opp_claim_{blind_id}_{index}", type="primary" if index == chosen else "secondary", use_container_width=True):
                                    st.session_state.pv_opp_claim_index = index
                                    st.rerun()
                with right:
                    claim = claims.reset_index(drop=True).iloc[chosen]
                    gemini_label = str(claim.get("label", "Pending"))
                    mini_label = "Supported" if str(claim.get("predicted_supported", "")) == "1" else "Unsupported"
                    probability = pd.to_numeric(pd.Series([claim.get("support_probability", "")]), errors="coerce").iloc[0]
                    quote = str(claim.get("evidence_quote", ""))
                    with st.container(key="pv_right"):
                        st.markdown('<div class="pv-panel-head"><h2>Evidence and judgement</h2></div>', unsafe_allow_html=True)
                        with st.container(key="pv_eval_card_minicheck_opp"):
                            score = f"{probability:.3f}" if pd.notna(probability) else "—"
                            st.markdown(f'<div class="pv-evaluator-head"><div><div class="pv-evaluator-name">1. MiniCheck</div><div class="pv-evaluator-desc">Binary source-support model</div></div><div class="pv-score">{score}<span>support probability</span></div></div>', unsafe_allow_html=True)
                            st.markdown(badge_html(mini_label), unsafe_allow_html=True)
                        with st.container(key="pv_eval_card_gemini_opp"):
                            st.markdown('<div class="pv-evaluator-head"><div><div class="pv-evaluator-name">2. Gemini</div><div class="pv-evaluator-desc">Evidence-citing LLM verifier</div></div></div>', unsafe_allow_html=True)
                            st.markdown(badge_html(gemini_label, str(claim["claim_id"])), unsafe_allow_html=True)
                            with st.container(key="pv_source_toggle_opp_gemini"):
                                mode = st.segmented_control("OPP evidence view", ["Supporting evidence", "Full policy"], default="Supporting evidence", label_visibility="collapsed", key=f"pv_opp_source_{claim['claim_id']}")
                            st.markdown(source_reader_html(opp_source, quote, mode == "Full policy"), unsafe_allow_html=True)
                            st.markdown('<div class="pv-label pv-why-label">Why Gemini assigned this label</div>', unsafe_allow_html=True)
                            st.markdown(f'<p class="pv-explanation">{html.escape(str(claim.get("explanation", "No explanation available.")))}</p>', unsafe_allow_html=True)
        else:
            cov = opp_coverage[opp_coverage["blind_id"] == blind_id].copy().reset_index(drop=True)
            if cov.empty:
                st.info("No completed OPP coverage assessments are available for this summary.")
            else:
                selected = st.selectbox("Choose important source information", cov.index.tolist(), format_func=lambda i: f"{cov.loc[i, 'unit_id']} · {cov.loc[i, 'important_information']}")
                item = cov.loc[selected]
                unit = opp_units[(opp_units["policy_id"] == policy_id) & (opp_units["unit_id"] == item["unit_id"])]
                source_quote = str(unit.iloc[0]["exact_source_evidence"]) if not unit.empty else ""
                left, right = st.columns([1.05, .95], gap="medium")
                with left:
                    with st.container(key="pv_left"):
                        st.markdown('<div class="pv-panel-head"><h2>Important source information</h2></div>', unsafe_allow_html=True)
                        st.markdown(f'<div class="pv-inspector"><p class="pv-explanation">{html.escape(str(item["important_information"]))}</p>{badge_html(str(item["coverage_label"]), str(item["unit_id"]))}<div class="pv-label pv-why-label">Evidence found in the summary</div><p class="pv-explanation">{html.escape(str(item.get("summary_evidence", "No corresponding evidence found.")))}</p></div>', unsafe_allow_html=True)
                with right:
                    with st.container(key="pv_right"):
                        st.markdown('<div class="pv-panel-head"><h2>Source evidence and reason</h2></div>', unsafe_allow_html=True)
                        with st.container(key="pv_source_toggle_opp_coverage"):
                            mode = st.segmented_control("OPP coverage evidence view", ["Supporting evidence", "Full policy"], default="Supporting evidence", label_visibility="collapsed", key=f"pv_opp_cov_source_{item['comparison_id']}")
                        st.markdown(source_reader_html(opp_source, source_quote, mode == "Full policy"), unsafe_allow_html=True)
                        st.markdown('<div class="pv-label pv-why-label">Why Gemini assigned this label</div>', unsafe_allow_html=True)
                        st.markdown(f'<p class="pv-explanation">{html.escape(str(item.get("explanation", "No explanation available.")))}</p>', unsafe_allow_html=True)

    elif view == "Taxonomy mapping":
        with st.container(key="pv_single_panel"):
            st.markdown('<div class="pv-panel-head"><h2>How independently extracted information maps to OPP-115</h2></div><div class="pv-inspector">', unsafe_allow_html=True)
            st.markdown('<p class="pv-section-intro">Gemini first identified important source information without seeing the OPP taxonomy. The frozen units were then mapped to the ten OPP-115 categories. For historical policies, overlapping official annotations provide a consistency check; the mapping was compatible for 90.2% of units.</p>', unsafe_allow_html=True)
            a, b, c = st.columns(3)
            a.metric("OPP source units", f"{len(taxonomy_mapping[taxonomy_mapping['dataset'] == 'OPP historical']):,}")
            b.metric("Contemporary reference units", f"{len(taxonomy_mapping[taxonomy_mapping['dataset'] == 'Contemporary human reference']):,}")
            b.caption("Kept separate from four validated Gemini additions")
            c.metric("Historical category compatibility", "90.2%")
            if not taxonomy_difference.empty:
                comparison = taxonomy_difference[["category", "opp_historical_unit_percent", "contemporary_human_unit_percent"]].copy()
                comparison = comparison.rename(columns={"opp_historical_unit_percent": "OPP historical", "contemporary_human_unit_percent": "Contemporary"})
                comparison = comparison.melt("category", var_name="Corpus", value_name="Percent")
                comparison["Percent"] = pd.to_numeric(comparison["Percent"], errors="coerce")
                chart = alt.Chart(comparison).mark_bar().encode(
                    x=alt.X("Percent:Q", title="Share of source units (%)"),
                    y=alt.Y("category:N", title=None, sort="-x"),
                    color=alt.Color("Corpus:N", scale=alt.Scale(range=["#173d67", "#79b9e8"])),
                    yOffset="Corpus:N", tooltip=["category", "Corpus", alt.Tooltip("Percent:Q", format=".2f")]
                ).properties(height=330)
                st.altair_chart(chart, use_container_width=True)
                st.caption("Descriptive unit proportions: the contemporary sample contains only three policies, so this is not evidence of a population-wide historical trend.")
            st.markdown('<div class="pv-label">Inspect one mapping for the selected OPP policy</div>', unsafe_allow_html=True)
            policy_maps = taxonomy_mapping[(taxonomy_mapping["dataset"] == "OPP historical") & (taxonomy_mapping["policy_id"] == policy_id)].copy().reset_index(drop=True)
            if policy_maps.empty:
                st.info("No taxonomy mapping is available for this policy.")
            else:
                map_index = st.selectbox("Choose a mapped source unit", policy_maps.index.tolist(), format_func=lambda i: f"{policy_maps.loc[i, 'unit_id']} · {policy_maps.loc[i, 'primary_category']} · {policy_maps.loc[i, 'important_information']}")
                mapped = policy_maps.loc[map_index]
                official = taxonomy_validation[(taxonomy_validation["policy_id"] == policy_id) & (taxonomy_validation["unit_id"] == mapped["unit_id"])]
                official_categories = str(official.iloc[0]["overlapping_opp_categories"]) if not official.empty else "No overlapping annotation located"
                compatible = str(official.iloc[0]["compatible_with_overlapping_opp_annotation"]) if not official.empty else "Not available"
                st.markdown(f'<div class="pv-reason-grid"><div class="pv-reason-part"><strong>Important information</strong>{html.escape(str(mapped["important_information"]))}</div><div class="pv-reason-part"><strong>Mapped category</strong>{html.escape(str(mapped["primary_category"]))}<br><span class="pv-muted">Confidence: {html.escape(str(mapped["confidence"]))}</span></div><div class="pv-reason-part"><strong>Gemini reason</strong>{html.escape(str(mapped["explanation"]))}</div><div class="pv-reason-part"><strong>Official OPP overlap check</strong>{html.escape(official_categories)}<br>Compatible: {html.escape(compatible)}</div></div>', unsafe_allow_html=True)
                st.markdown('<div class="pv-label pv-why-label">Original-policy evidence</div>', unsafe_allow_html=True)
                st.markdown(source_reader_html(load_opp_source(policy_id), str(mapped["exact_source_evidence"]), False), unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    elif view == "Evaluator agreement":
        with st.container(key="pv_single_panel"):
            st.markdown('<div class="pv-panel-head"><h2>Can automated evaluators reproduce researcher decisions?</h2></div><div class="pv-inspector">', unsafe_allow_html=True)
            st.markdown('<p class="pv-section-intro">Agreement is reported separately for sentence source alignment and information coverage. Exact agreement shows how often two labels are identical; Cohen’s kappa also allows for agreement expected by chance. High raw agreement with a low kappa can occur when most items belong to one category.</p>', unsafe_allow_html=True)
            sentence_comparison = gemini_scores[["statement_id", "blind_id", "label", "statement_text"]].merge(
                minicheck_scores[["statement_id", "predicted_supported", "probability"]], on="statement_id", how="inner"
            ).merge(final_human_statements, on="statement_id", how="inner") if not gemini_scores.empty and not minicheck_scores.empty else pd.DataFrame()
            if not sentence_comparison.empty:
                sentence_comparison["minicheck_label"] = sentence_comparison["predicted_supported"].astype(str).map({"1": "Supported", "0": "Not supported"})
                sentence_comparison["human_binary"] = sentence_comparison["final_human_label"].map(lambda value: "Supported" if value == "Supported" else "Not supported")
                sentence_comparison["gemini_exact_human"] = sentence_comparison["label"] == sentence_comparison["final_human_label"]
                sentence_comparison["mini_exact_human"] = sentence_comparison["minicheck_label"] == sentence_comparison["human_binary"]
                gemini_human_exact = 100 * sentence_comparison["gemini_exact_human"].mean()
                gemini_human_kappa = cohen_kappa(sentence_comparison["label"], sentence_comparison["final_human_label"])
                mini_human_exact = 100 * sentence_comparison["mini_exact_human"].mean()
                mini_human_kappa = cohen_kappa(sentence_comparison["minicheck_label"], sentence_comparison["human_binary"])
            else:
                gemini_human_exact = gemini_human_kappa = mini_human_exact = mini_human_kappa = float("nan")
            pair_path = DATA / "human_evaluation" / "adjudication" / "human_phase1_pairwise_agreement.csv"
            human_pairs = pd.read_csv(pair_path) if pair_path.exists() else pd.DataFrame()
            coverage_pair_path = DATA / "evaluations" / "final_coverage_results" / "human_pairwise_coverage_agreement.csv"
            coverage_pairs = pd.read_csv(coverage_pair_path) if coverage_pair_path.exists() else pd.DataFrame()
            gemini_human_coverage = 100 * pd.to_numeric(human_coverage.get("exact_match", pd.Series(dtype=float)), errors="coerce").mean() if not human_coverage.empty else float("nan")
            coverage_kappa = cohen_kappa(human_coverage["gemini_label"], human_coverage["final_human_label"]) if not human_coverage.empty else float("nan")
            st.markdown('<div class="pv-label">Sentence source alignment</div>', unsafe_allow_html=True)
            researcher_exact = f"{100*human_pairs['label_exact_agreement'].min():.1f}–{100*human_pairs['label_exact_agreement'].max():.1f}%" if not human_pairs.empty else "Pending"
            researcher_kappa = f"Cohen’s κ = {human_pairs['label_cohen_kappa'].min():.3f}–{human_pairs['label_cohen_kappa'].max():.3f}" if not human_pairs.empty else "Kappa pending"
            st.markdown(agreement_cards_html([
                ("Researchers: pairwise exact agreement", researcher_exact, researcher_kappa),
                ("Gemini vs final researchers", f"{gemini_human_exact:.1f}%", f"Cohen’s κ = {gemini_human_kappa:.3f}"),
                ("MiniCheck vs binary researchers", f"{mini_human_exact:.1f}%", f"Cohen’s κ = {mini_human_kappa:.3f}"),
            ]), unsafe_allow_html=True)
            st.markdown('<div class="pv-callout"><strong>Meaning:</strong> the automated tools often match the final researcher label, but agreement must be interpreted with kappa because supported sentences are much more common than failures.</div>', unsafe_allow_html=True)
            st.markdown('<div class="pv-label">Information coverage</div>', unsafe_allow_html=True)
            coverage_exact = f"{100*coverage_pairs['exact_agreement'].min():.1f}–{100*coverage_pairs['exact_agreement'].max():.1f}%" if not coverage_pairs.empty else "Pending"
            st.markdown(agreement_cards_html([
                ("Researchers: pairwise exact agreement", coverage_exact, "Across the three researcher pairs"),
                ("Researchers: pairwise kappa", f"{coverage_pairs['cohen_kappa'].min():.3f}–{coverage_pairs['cohen_kappa'].max():.3f}" if not coverage_pairs.empty else "Pending", "Chance-corrected agreement"),
                ("Gemini vs final researchers", f"{gemini_human_coverage:.1f}%", f"Cohen’s κ = {coverage_kappa:.3f}"),
            ]), unsafe_allow_html=True)
            st.markdown('<div class="pv-callout"><strong>Meaning:</strong> researcher coverage judgements are strongly consistent. Gemini is useful for screening, but its lower agreement means it should not replace human review in this study.</div>', unsafe_allow_html=True)
            if not sentence_comparison.empty:
                disagreements = sentence_comparison[(sentence_comparison["blind_id"] == blind_id) & (~sentence_comparison["gemini_exact_human"])].reset_index(drop=True)
                st.markdown('<div class="pv-label">Inspect a Gemini–researcher disagreement in the selected summary</div>', unsafe_allow_html=True)
                if disagreements.empty:
                    st.success("Gemini and the final researcher decision agree on every sentence in this summary.")
                else:
                    disagreement_index = st.selectbox("Choose a sentence", disagreements.index.tolist(), format_func=lambda index: f"{disagreements.loc[index, 'statement_id']} · {disagreements.loc[index, 'statement_text']}")
                    disagreement = disagreements.loc[disagreement_index]
                    st.markdown(evaluator_rows_html(str(disagreement["minicheck_label"]), f"p={float(disagreement['probability']):.3f}", str(disagreement["label"]), str(disagreement["final_human_label"]), "Final researcher decision"), unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    elif view == "Study overview":
        with st.container(key="pv_single_panel"):
            st.markdown('<div class="pv-panel-head"><h2>What the prototype demonstrates</h2></div><div class="pv-inspector">', unsafe_allow_html=True)
            st.markdown('<p class="pv-section-intro">The prototype makes the dissertation’s evaluation process inspectable. It links every generated sentence and every important source item to separate automated and researcher judgements.</p>', unsafe_allow_html=True)
            st.markdown('<div class="pv-callout"><strong>Study design:</strong> 3 privacy policies × 3 model families × 3 prompting strategies × 2 prompt versions = 54 summaries.</div>', unsafe_allow_html=True)
            st.markdown('<div class="pv-study-flow"><div class="pv-flow-card"><strong>1 · Generate</strong>GPT, Llama and Mistral summarise short, medium and long policies.</div><div class="pv-flow-card"><strong>2 · Measure accessibility</strong>Readability, word count and compression describe how easy and concise outputs are.</div><div class="pv-flow-card"><strong>3 · Verify in two directions</strong>Summary-to-source checks alignment; source-to-summary checks omission.</div><div class="pv-flow-card"><strong>4 · Compare evaluators</strong>MiniCheck and Gemini are compared with final researcher decisions.</div></div>', unsafe_allow_html=True)
            a, b, c, d = st.columns(4)
            a.metric("Summaries", f"{len(summaries):,}")
            b.metric("Evaluated sentences", f"{len(gemini_scores):,}")
            c.metric("Important source items", f"{len(source_units):,}")
            d.metric("Coverage comparisons", f"{len(human_coverage):,}")
            if not metrics.empty:
                plot = metrics.dropna(subset=["words", "flesch_reading_ease"]).copy(); plot["Prompt version"] = plot["prompt_set"].map(SETS); plot["Model"] = plot["model_family"].map(MODELS)
                chart = alt.Chart(plot).mark_point(size=85, opacity=.75, filled=True).encode(x=alt.X("words:Q", title="Summary words"), y=alt.Y("flesch_reading_ease:Q", title="Flesch Reading Ease"), color=alt.Color("Prompt version:N"), shape=alt.Shape("Model:N"), tooltip=["policy_id", "Model", "Prompt version", "prompt_strategy", "words", "flesch_reading_ease"]).properties(height=330)
                st.markdown('<div class="pv-label">Accessibility and conciseness</div>', unsafe_allow_html=True)
                st.caption("Each point is one summary. Moving right means a longer summary; moving upward means a higher Flesch Reading Ease score.")
                st.altair_chart(chart, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="pv-footer">Privacy Summary Verifier · MSc AI research prototype · summaries are not legal advice</div>', unsafe_allow_html=True)
