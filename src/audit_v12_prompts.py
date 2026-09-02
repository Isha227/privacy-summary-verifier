from pathlib import Path
from .common import ROOT, load_config, sha256_text

SHARED_TASK = "Summarise the privacy policy below in clear, concise plain English for a general adult reader with no specialist legal or privacy knowledge."
SHARED_FORMAT = "Write the summary as continuous prose using complete sentences and short paragraphs. Do not use headings, bullet points, tables or numbered lists."
ROLE = "You are a plain-language communication specialist who explains complex information to non-specialist readers."
STRUCTURE = "Before writing, internally identify the policy information most important to the intended reader, organise it logically, and plan the summary. Do not reveal this process."
SAFETY_1 = "Retain the important information the reader needs to understand how the organisation handles personal information, what consequences this may have, and what rights or choices are available."
SAFETY_2 = 'Use only information supported by the policy. Preserve the original meaning, including important conditions, exceptions, limitations, quantities, time periods and distinctions such as "may," "will" and "only." Do not add assumptions or present uncertain information as certain.'

def audit():
    cfg = load_config()
    expected = {
        "basic_direct", "basic_role_guided", "basic_structured",
        "safety_focused_direct", "safety_focused_role_guided", "safety_focused_structured",
    }
    assert set(cfg["prompts"]) == expected, "unexpected prompt-condition keys"
    report=[]
    for key, rel in cfg["prompts"].items():
        path=ROOT/rel; text=path.read_text(encoding="utf-8")
        assert text.count("{{POLICY_TEXT}}") == 1, f"{key}: policy placeholder count"
        assert SHARED_TASK in text, f"{key}: shared task differs"
        assert SHARED_FORMAT in text, f"{key}: shared format differs"
        assert "approximately" not in text.lower(), f"{key}: unexpected word target"
        assert (ROLE in text) == ("role_guided" in key), f"{key}: role block mismatch"
        assert (STRUCTURE in text) == ("structured" in key), f"{key}: structure block mismatch"
        safety=key.startswith("safety_focused_")
        assert (SAFETY_1 in text) == safety, f"{key}: retention safeguard mismatch"
        assert (SAFETY_2 in text) == safety, f"{key}: alignment safeguard mismatch"
        report.append((key,sha256_text(text)))
    return report

if __name__ == "__main__":
    for key,digest in audit(): print(f"PASS {key}: {digest}")
