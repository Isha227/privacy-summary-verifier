from __future__ import annotations

import csv
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from .common import ROOT, read_csv


CLAIMS = ROOT / "data/opp115/experiment/faithfulness/prepared/claim_candidates.csv"
KEY = ROOT / "data/opp115/experiment/anonymised/BLINDING_KEY_RESTRICTED.csv"
CLEAN = ROOT / "data/opp115/frozen/clean"
BUNDLE_DIR = ROOT / "data/opp115/experiment/minicheck_colab_input"
BUNDLE_ZIP = ROOT / "notebooks/MiniCheck_OPP115_inputs.zip"
NOTEBOOK = ROOT / "notebooks/MiniCheck_OPP115_Colab.ipynb"


def _cell(cell_type: str, source: str) -> dict:
    cell = {"cell_type": cell_type, "metadata": {}, "source": source.splitlines(keepends=True)}
    if cell_type == "code":
        cell.update({"execution_count": None, "outputs": []})
    return cell


def build_bundle() -> tuple[int, int, int]:
    claims = [row for row in read_csv(CLAIMS) if row.get("include", "yes").strip().lower() == "yes"]
    key_rows = read_csv(KEY)
    claim_keys = {(row["blind_id"], row["claim_id"]) for row in claims}
    if len(claims) != 11873 or len(claim_keys) != 11873:
        raise RuntimeError("Expected 11,873 unique included OPP-115 claims")
    if len(key_rows) != 486 or len({row["blind_id"] for row in key_rows}) != 486:
        raise RuntimeError("Expected 486 unique blind-ID mappings")

    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    sources_dir = BUNDLE_DIR / "sources"
    sources_dir.mkdir(parents=True)

    policies = sorted({row["policy_id"] for row in key_rows})
    source_id = {policy_id: f"P{index:03d}" for index, policy_id in enumerate(policies, 1)}
    for policy_id, safe_id in source_id.items():
        source = CLEAN / f"{policy_id}.txt"
        if not source.is_file():
            raise FileNotFoundError(f"Missing frozen source: {source}")
        shutil.copyfile(source, sources_dir / f"{safe_id}.txt")

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
            relative = str(path.relative_to(BUNDLE_DIR)).replace("\\", "/")
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    (BUNDLE_DIR / "SHA256_MANIFEST.json").write_text(
        json.dumps(hashes, indent=2) + "\n", encoding="utf-8"
    )

    BUNDLE_ZIP.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BUNDLE_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(BUNDLE_DIR.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(BUNDLE_DIR))
    return len(claims), len({row["blind_id"] for row in key_rows}), len(policies)


def build_notebook() -> None:
    cells = [
        _cell("markdown", """# MiniCheck source-alignment evaluation — OPP-115 extension

Runs the frozen `flan-t5-large` MiniCheck evaluator on all **11,873 sentences from 486 blinded summaries**. Each sentence is paired with its correct frozen source policy through an evaluator-safe manifest.

MiniCheck is binary: `1 = predicted supported` and `0 = predicted unsupported`. It assesses sentence-to-source alignment; it does **not** assess omission or source coverage.

Before running, select **Runtime → Change runtime type → T4 GPU**. Run the cells in order and upload only `MiniCheck_OPP115_inputs.zip`. Results are checkpointed to Google Drive after every batch, so another free Colab session can safely resume the work.
"""),
        _cell("code", """# Confirm that Colab supplied a GPU.
import subprocess
gpu = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
if gpu.returncode != 0:
    raise RuntimeError('No GPU detected. Choose Runtime > Change runtime type > T4 GPU, then reconnect.')
print(gpu.stdout.splitlines()[0])
print('GPU detected.')
"""),
        _cell("code", """# Install the official MiniCheck implementation and required NLTK resources.
%pip install -q "minicheck @ git+https://github.com/Liyan06/MiniCheck.git@main"
import nltk
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)
"""),
        _cell("code", """# Mount Google Drive for resumable checkpoints, then upload the prepared ZIP.
from google.colab import drive, files
from pathlib import Path
import zipfile

drive.mount('/content/drive')
uploaded = files.upload()
name = 'MiniCheck_OPP115_inputs.zip'
if name not in uploaded:
    raise FileNotFoundError(f'Upload exactly {name}. Do not upload API keys or the restricted blinding key.')
INPUT_DIR = Path('/content/minicheck_opp115_inputs')
INPUT_DIR.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(name) as archive:
    archive.extractall(INPUT_DIR)
print('Inputs extracted to', INPUT_DIR)
"""),
        _cell("code", """# Verify the frozen inputs before loading the model.
import hashlib
import json
import pandas as pd

claims_path = INPUT_DIR / 'claim_candidates.csv'
manifest_path = INPUT_DIR / 'source_manifest.csv'
claims = pd.read_csv(claims_path, dtype=str).fillna('')
manifest = pd.read_csv(manifest_path, dtype=str).fillna('')
approved = claims[claims['include'].str.strip().str.lower().eq('yes')].copy()

required = {'blind_id', 'claim_id', 'claim_text', 'include', 'review_notes'}
if not required.issubset(claims.columns):
    raise ValueError(f'Missing claim columns: {sorted(required - set(claims.columns))}')
if len(approved) != 11873 or approved[['blind_id', 'claim_id']].duplicated().any():
    raise ValueError('Expected 11,873 unique included claims.')
if len(manifest) != 486 or manifest['blind_id'].duplicated().any():
    raise ValueError('Expected 486 unique blind-ID source mappings.')
if set(approved['blind_id']) != set(manifest['blind_id']):
    raise ValueError('Claim and source-manifest blind IDs do not match.')
missing = [path for path in manifest['source_file'] if not (INPUT_DIR / path).is_file()]
if missing:
    raise FileNotFoundError(f'Missing source files: {missing[:5]}')

print('Approved claims:', len(approved))
print('Blinded summaries:', approved['blind_id'].nunique())
print('Distinct policy sources:', manifest['source_file'].nunique())
print('Claims SHA-256:', hashlib.sha256(claims_path.read_bytes()).hexdigest())
"""),
        _cell("code", """# Load the same frozen MiniCheck model used in the contemporary-policy study.
import torch
from minicheck.minicheck import MiniCheck

if not torch.cuda.is_available():
    raise RuntimeError('PyTorch cannot access the GPU. Reconnect to a GPU runtime.')
MODEL_ID = 'flan-t5-large'
scorer = MiniCheck(model_name=MODEL_ID, cache_dir='/content/minicheck_ckpts')
print('Loaded', MODEL_ID, 'on', torch.cuda.get_device_name(0))
"""),
        _cell("code", """# Score and save after every batch. This cell is safe to rerun after disconnection.
from datetime import datetime, timezone

DRIVE_DIR = Path('/content/drive/MyDrive/MSc_AI_MiniCheck_OPP115')
DRIVE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT = DRIVE_DIR / 'minicheck_opp115_claim_scores.csv'
FIELDS = ['blind_id', 'claim_id', 'model_id', 'predicted_supported', 'support_probability', 'timestamp_utc', 'status', 'error']

if OUTPUT.exists():
    existing = pd.read_csv(OUTPUT, dtype=str).fillna('')
    existing = existing.drop_duplicates(['blind_id', 'claim_id'], keep='last')
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

# Batch 32 worked in the earlier study. If GPU memory is exhausted, change only this to 16.
BATCH_SIZE = 32
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
        pd.DataFrame(result_rows, columns=FIELDS).drop_duplicates(
            ['blind_id', 'claim_id'], keep='last'
        ).to_csv(OUTPUT, index=False)
        raise

    pd.DataFrame(result_rows, columns=FIELDS).drop_duplicates(
        ['blind_id', 'claim_id'], keep='last'
    ).to_csv(OUTPUT, index=False)
    processed = min(start + len(batch), len(pending))
    if processed % 320 == 0 or processed == len(pending):
        print(f'Checkpoint: {processed}/{len(pending)} pending; total complete: {len(completed) + processed}/11873')
print('Scoring pass complete. Checkpoint:', OUTPUT)
"""),
        _cell("code", """# Final validation, canonical deduplication and download.
results = pd.read_csv(OUTPUT, dtype=str).fillna('')
latest = results.drop_duplicates(['blind_id', 'claim_id'], keep='last')
successful = latest[latest['status'].eq('success')].copy()

print('Successful:', len(successful), '/ 11873')
print('Summaries represented:', successful['blind_id'].nunique(), '/ 486')
print(successful['predicted_supported'].value_counts())

if len(successful) != 11873:
    print('Not complete yet. Reconnect later and rerun the notebook; Google Drive will resume it.')
else:
    if successful[['blind_id', 'claim_id']].duplicated().any():
        raise ValueError('Duplicate successful claim keys remain.')
    if set(successful['model_id']) != {'flan-t5-large'}:
        raise ValueError('Unexpected MiniCheck model ID.')
    successful['support_probability'] = pd.to_numeric(successful['support_probability'], errors='raise')
    if not successful['support_probability'].between(0, 1).all():
        raise ValueError('Support probabilities must be between 0 and 1.')
    final_path = DRIVE_DIR / 'minicheck_opp115_claim_scores_FINAL.csv'
    successful.sort_values(['blind_id', 'claim_id']).to_csv(final_path, index=False)
    print('Validated: 11873/11873 successful unique claims across 486 summaries.')
    files.download(str(final_path))
"""),
        _cell("markdown", """## Return the final result

Only after the notebook reports **11,873 / 11,873 successful** and **486 / 486 summaries**, place the downloaded file here:

`pilot_study/data/opp115/experiment/evaluations/faithfulness/minicheck_opp115_claim_scores_FINAL.csv`

MiniCheck remains a binary evaluator. Do not translate its output into Gemini's four source-alignment labels.
"""),
    ]
    notebook = {
        "cells": cells,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"name": "MiniCheck_OPP115_Colab.ipynb", "provenance": []},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    NOTEBOOK.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    claim_count, summary_count, policy_count = build_bundle()
    build_notebook()
    print(
        "Built OPP-115 MiniCheck Colab package: "
        f"{claim_count} claims, {summary_count} summaries, {policy_count} policy sources"
    )
