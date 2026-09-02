from pathlib import Path
import re
import sys

from docx import Document

sys.stdout.reconfigure(encoding="utf-8")


root = Path(__file__).resolve().parents[1] / "outputs" / "final_report"
files = [
    "INTRODUCTION_80_PLUS_DRAFT.docx",
    "RELEVANT_WORK_80_PLUS_DRAFT.docx",
    "METHODS_AND_MATERIALS_80_PLUS_DRAFT.docx",
    "EXPERIMENTAL_RESULTS_AND_DISCUSSION_80_PLUS_DRAFT.docx",
    "CONCLUSIONS_80_PLUS_DRAFT.docx",
    "LNCS_MSc_AI_Report_with_Prompt_Appendix.docx",
    "LNCS_MSc_AI_Report_with_Methods_and_Appendix_B_Diagrams.docx",
]

selected = files if len(sys.argv) == 1 else sys.argv[1:]
for filename in selected:
    document = Document(root / filename)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    citations = sorted(set(re.findall(r"\[(\d+)\]", text)), key=int)
    print(f"{filename}: citations={citations}")
    print(text)
    print("\n---\n")
