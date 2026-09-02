from __future__ import annotations

import csv
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from .common import ROOT, read_csv


CLAIMS = ROOT / "data/main/faithfulness/claim_candidates.csv"
KEY = ROOT / "data/main/anonymised/BLINDING_KEY_RESTRICTED.csv"
BUNDLE_DIR = ROOT / "data/main/minicheck_colab_input"
BUNDLE_ZIP = ROOT / "notebooks/MiniCheck_MAIN_inputs.zip"
NOTEBOOK = ROOT / "notebooks/MiniCheck_MAIN_Colab.ipynb"


def _cell(cell_type: str, source: str) -> dict:
    cell = {"cell_type": cell_type, "metadata": {}, "source": source.splitlines(keepends=True)}
    if cell_type == "code":
        cell.update({"execution_count": None, "outputs": []})
    return cell


def build_bundle() -> tuple[int, int]:
    claims = read_csv(CLAIMS)
    key_rows = read_csv(KEY)
    if len(claims) != 10485 or len({(r["blind_id"], r["claim_id"]) for r in claims}) != 10485:
        raise RuntimeError("Expected 10,485 unique main-study claims")
    if len(key_rows) != 270 or len({r["blind_id"] for r in key_rows}) != 270:
        raise RuntimeError("Expected 270 unique blind-ID mappings")

    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    sources_dir = BUNDLE_DIR / "sources"
    sources_dir.mkdir(parents=True)
    policies = sorted({row["policy_id"] for row in key_rows})
    source_id = {policy_id: f"P{index:03d}" for index, policy_id in enumerate(policies, 1)}
    for policy_id, safe_id in source_id.items():
        shutil.copyfile(ROOT / "data/main/clean" / f"{policy_id}.txt", sources_dir / f"{safe_id}.txt")

    shutil.copyfile(CLAIMS, BUNDLE_DIR / "claim_candidates.csv")
    manifest = [
        {"blind_id": row["blind_id"], "source_file": f"sources/{source_id[row['policy_id']]}.txt"}
        for row in sorted(key_rows, key=lambda item: item["blind_id"])
    ]
    with (BUNDLE_DIR / "source_manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["blind_id", "source_file"])
        writer.writeheader()
        writer.writerows(manifest)

    hashes = {}
    for path in sorted(BUNDLE_DIR.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(BUNDLE_DIR)).replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
    (BUNDLE_DIR / "SHA256_MANIFEST.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")

    with zipfile.ZipFile(BUNDLE_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(BUNDLE_DIR.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(BUNDLE_DIR))
    return len(claims), len(policies)


def build_notebook() -> None:
    cells = [
        _cell("markdown", """# MiniCheck faithfulness evaluation — main study

Runs frozen `flan-t5-large` MiniCheck on all 10,485 claims from 270 blinded summaries and selects the correct source policy through an evaluator-safe manifest.

Before running, choose **Runtime → Change runtime type → T4 GPU**. Run cells in order. Upload only `MiniCheck_MAIN_inputs.zip`. Progress is saved to Google Drive after every batch, so a disconnected free Colab session can resume.
"""),
        _cell("code", """# Confirm that Colab supplied a GPU.
import subprocess
gpu = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
if gpu.returncode != 0:
    raise RuntimeError('No GPU detected. Choose Runtime > Change runtime type > T4 GPU, then reconnect.')
print(gpu.stdout.splitlines()[0])
print('GPU detected.')
"""),
        _cell("code", """# Install the official MiniCheck implementation.
%pip install -q "minicheck @ git+https://github.com/Liyan06/MiniCheck.git@main"
"""),
        _cell("code", """# Mount Google Drive for resumable checkpoints, then upload the prepared input ZIP.
from google.colab import drive, files
from pathlib import Path
import zipfile

drive.mount('/content/drive')
uploaded = files.upload()
name = 'MiniCheck_MAIN_inputs.zip'
if name not in uploaded:
    raise FileNotFoundError(f'Upload {name}, not the restricted blinding key or API keys.')
INPUT_DIR = Path('/content/minicheck_main_inputs')
INPUT_DIR.mkdir(exist_ok=True)
with zipfile.ZipFile(name) as archive:
    archive.extractall(INPUT_DIR)
print('Inputs extracted to', INPUT_DIR)
"""),
        _cell("code", """# Validate all frozen inputs before loading the model.
import hashlib
import json
import pandas as pd

claims_path = INPUT_DIR / 'claim_candidates.csv'
manifest_path = INPUT_DIR / 'source_manifest.csv'
claims = pd.read_csv(claims_path, dtype=str).fillna('')
manifest = pd.read_csv(manifest_path, dtype=str).fillna('')
required_claim_columns = {'blind_id', 'claim_id', 'claim_text', 'include', 'review_notes'}
if not required_claim_columns.issubset(claims.columns):
    raise ValueError(f'Missing claim columns: {sorted(required_claim_columns - set(claims.columns))}')
approved = claims[claims['include'].str.strip().str.lower().eq('yes')].copy()
if len(approved) != 10485 or approved[['blind_id', 'claim_id']].duplicated().any():
    raise ValueError('Expected 10,485 unique included claims.')
if len(manifest) != 270 or manifest['blind_id'].duplicated().any():
    raise ValueError('Expected 270 unique blind-ID source mappings.')
if set(approved['blind_id']) != set(manifest['blind_id']):
    raise ValueError('Claim and source-manifest blind IDs do not match.')
missing_sources = [p for p in manifest['source_file'] if not (INPUT_DIR / p).is_file()]
if missing_sources:
    raise FileNotFoundError(f'Missing source files: {missing_sources[:5]}')
print('Approved claims:', len(approved))
print('Blind summaries:', approved['blind_id'].nunique())
print('Distinct policy sources:', manifest['source_file'].nunique())
print('Claims SHA-256:', hashlib.sha256(claims_path.read_bytes()).hexdigest())
"""),
        _cell("code", """# Load the frozen MiniCheck model. The first run downloads its weights.
import torch
import nltk
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)
from minicheck.minicheck import MiniCheck

if not torch.cuda.is_available():
    raise RuntimeError('PyTorch cannot access the GPU. Reconnect to a GPU runtime.')
MODEL_ID = 'flan-t5-large'
scorer = MiniCheck(model_name=MODEL_ID, cache_dir='/content/minicheck_ckpts')
print('Loaded', MODEL_ID, 'on', torch.cuda.get_device_name(0))
"""),
        _cell("code", """# Score in small batches and checkpoint to Google Drive after every batch. Safe to rerun.
from datetime import datetime, timezone

DRIVE_DIR = Path('/content/drive/MyDrive/MSc_AI_MiniCheck_MAIN')
DRIVE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT = DRIVE_DIR / 'minicheck_claim_scores.csv'
FIELDS = ['blind_id', 'claim_id', 'model_id', 'predicted_supported', 'support_probability', 'timestamp_utc', 'status', 'error']

if OUTPUT.exists():
    existing = pd.read_csv(OUTPUT, dtype=str).fillna('')
    completed = set(existing.loc[existing['status'].eq('success'), 'claim_id'])
    result_rows = existing.to_dict('records')
else:
    completed, result_rows = set(), []

source_for_blind = dict(zip(manifest['blind_id'], manifest['source_file']))
source_cache = {
    path: (INPUT_DIR / path).read_text(encoding='utf-8')
    for path in sorted(set(source_for_blind.values()))
}
pending = approved[~approved['claim_id'].isin(completed)].copy()
BATCH_SIZE = 4
print(f'Already complete: {len(completed)}; pending: {len(pending)}')

for start in range(0, len(pending), BATCH_SIZE):
    batch = pending.iloc[start:start + BATCH_SIZE]
    docs = [source_cache[source_for_blind[blind_id]] for blind_id in batch['blind_id']]
    try:
        labels, probabilities, _, _ = scorer.score(docs=docs, claims=batch['claim_text'].tolist())
        for (_, row), label, probability in zip(batch.iterrows(), labels, probabilities):
            result_rows.append({
                'blind_id': row['blind_id'], 'claim_id': row['claim_id'], 'model_id': MODEL_ID,
                'predicted_supported': int(label), 'support_probability': float(probability),
                'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'status': 'success', 'error': '',
            })
    except Exception as exc:
        for _, row in batch.iterrows():
            result_rows.append({
                'blind_id': row['blind_id'], 'claim_id': row['claim_id'], 'model_id': MODEL_ID,
                'predicted_supported': '', 'support_probability': '',
                'timestamp_utc': datetime.now(timezone.utc).isoformat(),
                'status': 'failed', 'error': f'{type(exc).__name__}: {exc}',
            })
        pd.DataFrame(result_rows, columns=FIELDS).to_csv(OUTPUT, index=False)
        raise
    pd.DataFrame(result_rows, columns=FIELDS).to_csv(OUTPUT, index=False)
    processed = min(start + len(batch), len(pending))
    if processed % 100 == 0 or processed == len(pending):
        print(f'Checkpoint: {processed}/{len(pending)} pending claims; total complete: {len(completed) + processed}/10485')
print('Scoring complete. Checkpoint:', OUTPUT)
"""),
        _cell("code", """# Final validation, deduplication and download. Run only after scoring completes.
results = pd.read_csv(OUTPUT, dtype=str).fillna('')
latest = results.drop_duplicates(subset=['blind_id', 'claim_id'], keep='last')
successful = latest[latest['status'].eq('success')].copy()
if len(latest) != 10485 or len(successful) != 10485:
    raise ValueError(f'Incomplete result: {len(successful)}/10485 successful unique claims.')
if set(successful['model_id']) != {'flan-t5-large'}:
    raise ValueError('Unexpected MiniCheck model ID.')
successful['support_probability'] = pd.to_numeric(successful['support_probability'], errors='raise')
if not successful['support_probability'].between(0, 1).all():
    raise ValueError('Support probabilities must be between 0 and 1.')
successful = successful.sort_values(['blind_id', 'claim_id'])
successful.to_csv(OUTPUT, index=False)
print(successful.groupby(['predicted_supported']).size())
print('Validated: 10485/10485 successful unique claims across', successful['blind_id'].nunique(), 'summaries.')
files.download(str(OUTPUT))
"""),
        _cell("markdown", """## Save locally

After validation, place the downloaded `minicheck_claim_scores.csv` in:

`pilot_study/data/main/evaluations/faithfulness/`

MiniCheck is binary: `1` means predicted supported and `0` means predicted unsupported. Do not convert these into Gemini's or the human evaluators' four-category labels.
"""),
    ]
    notebook = {
        "cells": cells,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"name": "MiniCheck_MAIN_Colab.ipynb", "provenance": []},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    NOTEBOOK.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    claim_count, policy_count = build_bundle()
    build_notebook()
    print(f"Built main MiniCheck Colab notebook and input ZIP: {claim_count} claims, {policy_count} policy sources")
