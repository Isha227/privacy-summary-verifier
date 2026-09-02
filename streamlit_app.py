"""Read-only dashboard for the completed privacy-policy summarisation pilot."""

from __future__ import annotations

import re
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "pilot"
REPORT = ROOT / "outputs" / "reports" / "Final_Pilot_Study_Report.docx"

MODEL_NAMES = {"gpt": "GPT", "llama": "Llama", "mistral": "Mistral"}
PROMPT_NAMES = {"zero": "Zero-shot", "role": "Role", "structured": "Structured reasoning"}
POLICY_NAMES = {
    "PILOT01": "Mozilla (short)",
    "PILOT02": "DuckDuckGo (medium)",
    "PILOT03": "Automattic (long/complex)",
}

COVERAGE = pd.DataFrame(
    [
        ("PILOT01", "gpt", "zero", 1, 74.00), ("PILOT01", "gpt", "role", 1, 64.00),
        ("PILOT01", "gpt", "structured", 1, 90.00), ("PILOT01", "llama", "zero", 1, 88.00),
        ("PILOT01", "llama", "role", 1, 68.00), ("PILOT01", "llama", "structured", 1, 74.00),
        ("PILOT01", "mistral", "zero", 1, 80.00), ("PILOT01", "mistral", "role", 1, 84.00),
        ("PILOT01", "mistral", "structured", 1, 54.00),
        ("PILOT02", "gpt", "zero", 1, 69.44), ("PILOT02", "gpt", "zero", 2, 75.00),
        ("PILOT02", "gpt", "zero", 3, 63.89), ("PILOT02", "gpt", "role", 1, 65.28),
        ("PILOT02", "gpt", "structured", 1, 69.44), ("PILOT02", "llama", "zero", 1, 40.28),
        ("PILOT02", "llama", "role", 1, 47.22), ("PILOT02", "llama", "structured", 1, 34.72),
        ("PILOT02", "mistral", "zero", 1, 68.06), ("PILOT02", "mistral", "role", 1, 70.83),
        ("PILOT02", "mistral", "structured", 1, 77.78),
        ("PILOT03", "gpt", "zero", 1, 56.90), ("PILOT03", "gpt", "role", 1, 61.50),
        ("PILOT03", "gpt", "structured", 1, 50.00), ("PILOT03", "llama", "zero", 1, 30.00),
        ("PILOT03", "llama", "role", 1, 28.50), ("PILOT03", "llama", "structured", 1, 28.50),
        ("PILOT03", "mistral", "zero", 1, 30.00), ("PILOT03", "mistral", "role", 1, 30.80),
        ("PILOT03", "mistral", "structured", 1, 44.60),
    ],
    columns=["policy_id", "model_family", "prompt_strategy", "replicate", "coverage_percent"],
)


@st.cache_data
def load_metrics() -> pd.DataFrame:
    frame = pd.read_csv(DATA / "evaluations" / "metrics.csv")
    frame["model"] = frame["model_family"].map(MODEL_NAMES)
    frame["prompt"] = frame["prompt_strategy"].map(PROMPT_NAMES)
    frame["policy"] = frame["policy_id"].map(POLICY_NAMES)
    return frame


@st.cache_data
def load_policies() -> pd.DataFrame:
    return pd.read_csv(DATA / "metadata" / "policies.csv")


@st.cache_data
def load_summaries() -> pd.DataFrame:
    pattern = re.compile(r"(PILOT\d+)__(gpt|llama|mistral)__(zero|role|structured)__r(\d+)\.txt$")
    rows = []
    for path in sorted((DATA / "outputs").glob("PILOT*/*.txt")):
        match = pattern.match(path.name)
        if not match:
            continue
        policy, model, prompt, replicate = match.groups()
        rows.append({
            "policy_id": policy,
            "model_family": model,
            "prompt_strategy": prompt,
            "replicate": int(replicate),
            "text": path.read_text(encoding="utf-8"),
            "filename": path.name,
        })
    return pd.DataFrame(rows)


def label_data(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["Model"] = result["model_family"].map(MODEL_NAMES)
    result["Prompt"] = result["prompt_strategy"].map(PROMPT_NAMES)
    result["Policy"] = result["policy_id"].map(POLICY_NAMES)
    return result


def download(path: Path, label: str, mime: str) -> None:
    if path.exists():
        st.download_button(label, path.read_bytes(), file_name=path.name, mime=mime, use_container_width=True)


def source_context(source: str, evidence: str, radius: int = 240) -> str:
    """Return a short source passage around an evidence quote when it can be matched."""
    if not evidence or pd.isna(evidence):
        return ""
    start = source.casefold().find(str(evidence).strip().casefold())
    if start < 0:
        return ""
    left = max(0, start - radius)
    right = min(len(source), start + len(str(evidence)) + radius)
    passage = source[left:right].strip()
    if left:
        passage = "…" + passage
    if right < len(source):
        passage += "…"
    return passage


st.set_page_config(page_title="Pilot Study Dashboard", page_icon="🔎", layout="wide")
st.markdown(
    """
    <style>
    .stApp {background: #f6f8fb;}
    [data-testid="stMetric"] {background: white; border: 1px solid #e3e8ef; border-radius: 14px; padding: 16px;}
    div[data-testid="stExpander"] {background: white; border-radius: 12px;}
    .block-container {padding-top: 2rem; padding-bottom: 3rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

metrics = load_metrics()
summaries = load_summaries()
policies = load_policies()

with st.sidebar:
    st.title("Pilot study")
    page = st.radio(
        "View",
        ["Overview", "Summary explorer", "Coverage", "Readability & compression", "Faithfulness", "Files"],
    )
    st.divider()
    st.caption("Read-only dashboard · saved results only")

st.title("Privacy-policy summarisation pilot")
st.caption("GPT vs Llama vs Mistral · zero-shot, role and structured-reasoning prompts")

if page == "Overview":
    st.subheader("What happened")
    st.write(
        "Three privacy policies—short, medium and long—were summarised with three models and three prompt "
        "strategies. The normal matrix produced 27 summaries, plus two GPT repeats for a reproducibility check."
    )
    a, b, c, d = st.columns(4)
    a.metric("Policies", len(policies))
    b.metric("Retained summaries", len(summaries))
    c.metric("Experimental conditions", 29)
    d.metric("Within 350–550 words", f"{int(metrics['within_350_550_words'].sum())}/29")

    st.subheader("Pilot corpus")
    shown = policies[["policy_id", "organisation", "sector", "word_count_raw", "accessed_date"]].copy()
    shown.columns = ["ID", "Organisation", "Sector", "Words", "Accessed"]
    st.dataframe(shown, hide_index=True, use_container_width=True)

    st.subheader("Main conclusions")
    st.info(
        "The pipeline worked end to end. Researcher agreement was high, faithfulness was generally high, "
        "and longer policies were harder to cover fully. One generation per main-study condition was retained."
    )
    st.write("• No reasoning leakage was detected.\n\n• The output ceiling is frozen at 1,500 tokens.\n\n• Only technical failures should be retried.\n\n• Word-limit compliance is evaluated, not corrected by regeneration.")

elif page == "Summary explorer":
    st.subheader("Read and compare summaries")
    left, middle, right, fourth = st.columns(4)
    policy = left.selectbox("Policy", list(POLICY_NAMES), format_func=POLICY_NAMES.get)
    model = middle.selectbox("Model", list(MODEL_NAMES), format_func=MODEL_NAMES.get)
    prompt = right.selectbox("Prompt", list(PROMPT_NAMES), format_func=PROMPT_NAMES.get)
    available = summaries.query("policy_id == @policy and model_family == @model and prompt_strategy == @prompt")
    reps = sorted(available["replicate"].unique()) if not available.empty else [1]
    replicate = fourth.selectbox("Run", reps, format_func=lambda value: f"r{value}")
    selected = available[available["replicate"] == replicate]
    if selected.empty:
        st.warning("No saved summary matches these filters.")
    else:
        row = selected.iloc[0]
        metric_row = metrics.query(
            "policy_id == @policy and model_family == @model and prompt_strategy == @prompt and replicate == @replicate"
        )
        if not metric_row.empty:
            m = metric_row.iloc[0]
            x, y, z, q = st.columns(4)
            x.metric("Words", int(m["words"]))
            y.metric("Reading ease", f"{m['flesch_reading_ease']:.1f}")
            z.metric("Grade level", f"{m['flesch_kincaid_grade']:.1f}")
            q.metric("Compression", f"{m['word_compression_ratio']:.1%}")
        st.text_area("Summary text", row["text"], height=520)
        st.download_button("Download this summary", row["text"], file_name=row["filename"], mime="text/plain")

elif page == "Coverage":
    st.subheader("Human coverage evaluation")
    st.caption("Percentage of weighted privacy-policy content covered by each summary after adjudication.")
    selected_policy = st.selectbox("Policy", list(POLICY_NAMES), format_func=POLICY_NAMES.get)
    chart_data = label_data(COVERAGE.query("policy_id == @selected_policy"))
    chart_data["Run label"] = chart_data.apply(
        lambda row: f"{row['Prompt']} r{row['replicate']}" if row["replicate"] > 1 else row["Prompt"], axis=1
    )
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("Run label:N", title=None, sort=None),
            y=alt.Y("coverage_percent:Q", title="Coverage (%)", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("Model:N", scale=alt.Scale(range=["#2563eb", "#16a34a", "#f59e0b"])),
            tooltip=["Policy", "Model", "Prompt", "replicate", alt.Tooltip("coverage_percent:Q", format=".2f")],
        )
        .properties(height=420)
    )
    st.altair_chart(chart, use_container_width=True)
    st.dataframe(
        chart_data[["Policy", "Model", "Prompt", "replicate", "coverage_percent"]].rename(
            columns={"replicate": "Run", "coverage_percent": "Coverage (%)"}
        ),
        hide_index=True,
        use_container_width=True,
    )
    st.caption("Researcher unanimous agreement: PILOT01 89.3% · PILOT02 92.4% · PILOT03 90.4%")

elif page == "Readability & compression":
    st.subheader("Readability, length and compression")
    colour_by = st.radio("Compare by", ["Model", "Prompt"], horizontal=True)
    dimension = "model" if colour_by == "Model" else "prompt"
    x_metric = st.selectbox(
        "Horizontal measure",
        ["words", "flesch_reading_ease", "flesch_kincaid_grade", "word_compression_ratio"],
        format_func=lambda value: {
            "words": "Summary words", "flesch_reading_ease": "Flesch reading ease",
            "flesch_kincaid_grade": "Flesch–Kincaid grade", "word_compression_ratio": "Compression ratio",
        }[value],
    )
    plot = alt.Chart(metrics).mark_circle(size=110, opacity=.78).encode(
        x=alt.X(f"{x_metric}:Q", title=x_metric.replace("_", " ").title()),
        y=alt.Y("policy:N", title=None),
        color=alt.Color(f"{dimension}:N", title=colour_by),
        tooltip=["policy", "model", "prompt", "replicate", "words", "flesch_reading_ease", "flesch_kincaid_grade", "word_compression_ratio"],
    ).properties(height=380)
    st.altair_chart(plot, use_container_width=True)
    group = metrics.groupby(dimension, as_index=False).agg(
        outputs=("run_id", "count"), mean_words=("words", "mean"),
        mean_reading_ease=("flesch_reading_ease", "mean"), mean_grade=("flesch_kincaid_grade", "mean"),
        mean_compression=("word_compression_ratio", "mean"),
    ).round(3)
    st.dataframe(group, hide_index=True, use_container_width=True)
    st.caption("Higher reading-ease scores indicate easier text; lower grade levels indicate simpler text.")

elif page == "Faithfulness":
    st.subheader("Faithfulness reproducibility check")
    st.write("Faithfulness was checked on 118 sentence-level claims from the three repeated GPT zero-shot summaries of PILOT02.")
    human = pd.read_csv(DATA / "evaluations" / "faithfulness" / "human_final_blinded_summary.csv")
    gemini = pd.read_csv(DATA / "evaluations" / "faithfulness" / "gemini_claim_scores__gemini-3.5-flash-lite.csv")
    mini = pd.read_csv(DATA / "evaluations" / "faithfulness" / "minicheck_claim_scores.csv")
    a, b, c, d = st.columns(4)
    a.metric("Claims checked", len(gemini))
    b.metric("Human unanimous ratings", "90.7%")
    c.metric("Gemini–human agreement", "89.0%")
    d.metric("MiniCheck–human agreement", "89.0%")
    long = human.melt(
        id_vars=["blind_id"], value_vars=["strict_supported_percent", "supported_or_partial_percent"],
        var_name="Measure", value_name="Percent",
    )
    long["Measure"] = long["Measure"].map({
        "strict_supported_percent": "Strictly supported", "supported_or_partial_percent": "Supported or partial"
    })
    chart = alt.Chart(long).mark_bar().encode(
        x=alt.X("blind_id:N", title="Blinded summary"), y=alt.Y("Percent:Q", scale=alt.Scale(domain=[0, 100])),
        xOffset="Measure:N", color=alt.Color("Measure:N"), tooltip=["blind_id", "Measure", "Percent"],
    ).properties(height=380)
    st.altair_chart(chart, use_container_width=True)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Gemini labels**")
        st.dataframe(gemini["label"].value_counts().rename_axis("Label").reset_index(name="Claims"), hide_index=True, use_container_width=True)
    with col2:
        st.markdown("**MiniCheck predictions**")
        mini_counts = mini["predicted_supported"].map({1: "Supported", 0: "Not supported"}).value_counts()
        st.dataframe(mini_counts.rename_axis("Prediction").reset_index(name="Claims"), hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("Sentence-level evidence viewer")
    st.write(
        "Choose one repeated summary and one claim to see whether it was supported, partially supported, "
        "unsupported or contradicted—and why."
    )
    human_detail = pd.read_csv(DATA / "evaluations" / "faithfulness" / "human_final_blinded.csv")
    claim_names = {
        "S027": "S027 — GPT zero-shot, run 1",
        "S014": "S014 — GPT zero-shot, run 2",
        "S015": "S015 — GPT zero-shot, run 3",
    }
    selected_blind = st.selectbox(
        "Summary",
        [item for item in ["S027", "S014", "S015"] if item in set(human_detail["blind_id"])],
        format_func=lambda item: claim_names[item],
    )
    claim_rows = human_detail[human_detail["blind_id"] == selected_blind].reset_index(drop=True)
    selected_claim = st.selectbox(
        "Summary sentence or claim",
        claim_rows["claim_id"].tolist(),
        format_func=lambda claim_id: (
            f"{claim_id}: "
            + claim_rows.loc[claim_rows["claim_id"] == claim_id, "claim_text"].iloc[0][:105]
            + ("…" if len(claim_rows.loc[claim_rows["claim_id"] == claim_id, "claim_text"].iloc[0]) > 105 else "")
        ),
    )
    detail = claim_rows[claim_rows["claim_id"] == selected_claim].iloc[0]
    gemini_match = gemini[gemini["claim_id"] == selected_claim]
    mini_match = mini[mini["claim_id"] == selected_claim]

    label = str(detail["final_label"])
    label_colours = {
        "Supported": ("#dcfce7", "#166534"),
        "Partially supported": ("#fef3c7", "#92400e"),
        "Unsupported": ("#fee2e2", "#991b1b"),
        "Contradicted": ("#fecaca", "#7f1d1d"),
    }
    background, foreground = label_colours.get(label, ("#e5e7eb", "#1f2937"))
    st.markdown(
        f'<span style="background:{background};color:{foreground};padding:7px 12px;border-radius:999px;'
        f'font-weight:700">Human verdict: {label}</span>',
        unsafe_allow_html=True,
    )
    st.markdown("**Claim from the summary**")
    st.info(str(detail["claim_text"]))

    with st.expander("Show original-policy evidence and explanation", expanded=True):
        st.markdown("**Evidence quoted by the human reviewers**")
        st.success(str(detail["final_evidence"]) if pd.notna(detail["final_evidence"]) else "No supporting quotation recorded.")
        st.caption(f"Recorded location: {detail['final_evidence_location']}")
        st.markdown("**Why the reviewers gave this verdict**")
        explanation = detail["resolution_notes"] if pd.notna(detail["resolution_notes"]) else "No additional adjudication note was needed."
        st.write(str(explanation))

        policy_text = (DATA / "clean" / "PILOT02.txt").read_text(encoding="utf-8")
        context = source_context(policy_text, str(detail["final_evidence"]))
        if not context and not gemini_match.empty:
            context = source_context(policy_text, str(gemini_match.iloc[0]["evidence_quote"]))
        st.markdown("**Nearby wording in the original cleaned policy**")
        if context:
            st.text_area("Source passage", context, height=145, disabled=True, label_visibility="collapsed")
        else:
            st.caption("The saved evidence is a shortened quotation, so an exact automatic context match was not available.")

    g_col, m_col = st.columns(2)
    with g_col:
        st.markdown("**Gemini assessment**")
        if not gemini_match.empty:
            g = gemini_match.iloc[0]
            st.write(f"Verdict: **{g['label']}**")
            st.write(str(g["explanation"]))
            with st.expander("Gemini evidence quotation"):
                st.write(str(g["evidence_quote"]))
        else:
            st.caption("No Gemini result found.")
    with m_col:
        st.markdown("**MiniCheck assessment**")
        if not mini_match.empty:
            m = mini_match.iloc[0]
            prediction = "Supported" if int(m["predicted_supported"]) == 1 else "Not supported"
            st.write(f"Verdict: **{prediction}**")
            st.write(f"Support probability: **{float(m['support_probability']):.1%}**")
            st.caption("MiniCheck provides a score, not a written explanation or evidence quotation.")
        else:
            st.caption("No MiniCheck result found.")

else:
    st.subheader("Files and exports")
    st.write("Download the final report or the tables used by this dashboard.")
    c1, c2 = st.columns(2)
    with c1:
        download(REPORT, "Download final pilot report", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        download(DATA / "evaluations" / "metrics.csv", "Download readability/compression metrics", "text/csv")
    with c2:
        download(DATA / "evaluations" / "faithfulness" / "human_final_blinded_summary.csv", "Download human faithfulness summary", "text/csv")
        download(DATA / "evaluations" / "faithfulness" / "minicheck_claim_scores.csv", "Download MiniCheck results", "text/csv")
    st.warning("The restricted blinding key and API configuration are deliberately not available through the dashboard.")

st.divider()
st.caption("MSc AI dissertation pilot · local read-only research dashboard")
