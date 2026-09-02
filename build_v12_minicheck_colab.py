from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "data/v2_prompt_intervention_v1_2"
STATEMENTS = BASE / "evaluations/statements"
KEY = BASE / "anonymised/BLINDING_KEY_RESTRICTED.csv"
OUT = BASE / "minicheck_colab"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": [line + "\n" for line in text.splitlines()]}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
            "source": [line + "\n" for line in text.splitlines()]}


OUT.mkdir(parents=True, exist_ok=True)
with KEY.open(encoding="utf-8-sig", newline="") as handle:
    key = list(csv.DictReader(handle))

claim_rows = []
safe_manifest = []
for row in sorted(key, key=lambda r: r["blind_id"]):
    blind_id, policy_id = row["blind_id"], row["policy_id"]
    safe_manifest.append({"blind_id": blind_id, "policy_id": policy_id})
    path = STATEMENTS / blind_id / f"{blind_id}_summary_statements_v1.0.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for claim in csv.DictReader(handle):
            if claim["include"].lower() == "yes":
                claim_rows.append({"blind_id": blind_id, "policy_id": policy_id,
                                   "statement_id": claim["statement_id"], "statement_text": claim["statement_text"]})

claims_path = OUT / "v12_minicheck_statements.csv"
with claims_path.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=claim_rows[0].keys()); writer.writeheader(); writer.writerows(claim_rows)
manifest_path = OUT / "v12_evaluator_safe_manifest.csv"
with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=safe_manifest[0].keys()); writer.writeheader(); writer.writerows(safe_manifest)

zip_path = OUT / "MiniCheck_V12_inputs.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
    archive.write(claims_path, claims_path.name)
    archive.write(manifest_path, manifest_path.name)
    for policy_id in ("PILOT01", "PILOT02", "PILOT03"):
        archive.write(ROOT / f"data/pilot/clean/{policy_id}.txt", f"sources/{policy_id}.txt")

cells = [
    md("""# MiniCheck — v1.2 prompt-intervention study

Evaluates all 1,393 frozen summary sentences from 54 blinded summaries against their complete source privacy policy. MiniCheck is a **binary faithfulness evaluator**: `1 = predicted supported`, `0 = predicted unsupported`. It does not measure omission/coverage.

Use **Runtime → Change runtime type → T4 GPU**. Upload only `MiniCheck_V12_inputs.zip`. Progress is saved in Google Drive after every batch, so the run can resume after disconnection."""),
    code("""%pip install -q \"minicheck @ git+https://github.com/Liyan06/MiniCheck.git@main\"
import nltk
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)"""),
    code("""from google.colab import files, drive
from pathlib import Path
import io, zipfile, pandas as pd

uploaded = files.upload()
name = 'MiniCheck_V12_inputs.zip'
if name not in uploaded:
    raise FileNotFoundError(f'Upload exactly {name}')
INPUT_DIR = Path('/content/minicheck_v12_inputs')
INPUT_DIR.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(io.BytesIO(uploaded[name])) as z:
    z.extractall(INPUT_DIR)
claims = pd.read_csv(INPUT_DIR / 'v12_minicheck_statements.csv', dtype=str).fillna('')
assert len(claims) == 1393
assert claims.statement_id.is_unique
print('Validated statements:', len(claims), 'Summaries:', claims.blind_id.nunique())"""),
    code("""import torch
from minicheck.minicheck import MiniCheck

MODEL_ID = 'flan-t5-large'
device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
print('Device:', device)
scorer = MiniCheck(model_name=MODEL_ID, cache_dir='/content/minicheck_ckpts')"""),
    code("""drive.mount('/content/drive')
DRIVE_DIR = Path('/content/drive/MyDrive/MSc_AI_MiniCheck_V12')
DRIVE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT = DRIVE_DIR / 'minicheck_v12_statement_scores.csv'

sources = {p.stem: p.read_text(encoding='utf-8').strip() for p in (INPUT_DIR / 'sources').glob('*.txt')}
if OUTPUT.exists():
    done = pd.read_csv(OUTPUT, dtype=str).fillna('')
else:
    done = pd.DataFrame(columns=['blind_id','policy_id','statement_id','statement_text','minicheck_model','predicted_supported','probability','status','error'])
done_ids = set(done.loc[done.status.eq('success'), 'statement_id'])
pending = claims.loc[~claims.statement_id.isin(done_ids)].copy()
print('Already complete:', len(done_ids), 'Pending:', len(pending))"""),
    code("""from tqdm.auto import tqdm

BATCH_SIZE = 16  # Reduce to 8 if Colab runs out of GPU memory; do not exceed 32 without testing.
rows = done.to_dict('records')
for start in range(0, len(pending), BATCH_SIZE):
    batch = pending.iloc[start:start+BATCH_SIZE]
    try:
        labels, probabilities, _, _ = scorer.score(
            docs=[sources[p] for p in batch.policy_id],
            claims=batch.statement_text.tolist(),
        )
        for (_, item), label, probability in zip(batch.iterrows(), labels, probabilities):
            rows.append({**item.to_dict(), 'minicheck_model': MODEL_ID,
                         'predicted_supported': int(label), 'probability': float(probability),
                         'status': 'success', 'error': ''})
    except Exception as exc:
        for _, item in batch.iterrows():
            rows.append({**item.to_dict(), 'minicheck_model': MODEL_ID,
                         'predicted_supported': '', 'probability': '', 'status': 'failed',
                         'error': f'{type(exc).__name__}: {exc}'})
    current = pd.DataFrame(rows).drop_duplicates('statement_id', keep='last')
    current.to_csv(OUTPUT, index=False)
    print(f'Saved {min(start+BATCH_SIZE, len(pending))}/{len(pending)} pending statements')
print('Run finished:', OUTPUT)"""),
    code("""results = pd.read_csv(OUTPUT, dtype=str).fillna('')
success = results[results.status.eq('success')].copy()
assert success.statement_id.is_unique
print('Successful:', len(success), '/ 1393')
print('Summaries represented:', success.blind_id.nunique(), '/ 54')
print(success.predicted_supported.value_counts())
if len(success) == 1393:
    final_path = DRIVE_DIR / 'minicheck_v12_statement_scores_FINAL.csv'
    success.sort_values(['blind_id','statement_id']).to_csv(final_path, index=False)
    files.download(str(final_path))
else:
    print('Not complete yet. Re-run the notebook later; it will resume from Google Drive.')"""),
    md("""## Return the result

When the final validation reports **1,393 / 1,393 successful** and **54 / 54 summaries**, place the downloaded `minicheck_v12_statement_scores_FINAL.csv` in:

`pilot_study/data/v2_prompt_intervention_v1_2/evaluations/minicheck/`

Do not translate MiniCheck's binary output into the four-category Gemini/human labels."""),
]
notebook = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"name": "MiniCheck_V12_Colab.ipynb", "provenance": []},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
(ROOT / "notebooks/MiniCheck_V12_Colab.ipynb").write_text(json.dumps(notebook, indent=1), encoding="utf-8")
print(f"Created notebook and inputs for {len(claim_rows)} statements: {zip_path}")
