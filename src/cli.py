from __future__ import annotations
import argparse, csv
from .common import ROOT, load_config, read_csv
from .preprocess import preprocess_all
from .runner import run, conditions
from .evaluate import evaluate_all
from .anonymise import anonymise
from .providers import generate
from .faithfulness import prepare as prepare_faithfulness, freeze_human_templates, run_gemini, run_gemini_batched, run_minicheck, validate_human, analyse_human_agreement, finalise_human
from .coverage import run_gemini_coverage, validate_coverage_setup
from .analyse_human_coverage import analyse as analyse_human_coverage
from .v2_claims import decompose_one as decompose_v2_claims
from .v2_statements import prepare_one as prepare_v2_statements
from .v2_statement_verifier import verify_one as verify_v2_statements, revalidate_one as revalidate_v2_statements
from .v2_source_units import identify as identify_v2_source_units
from .v12_final_coverage import (
    analyse as analyse_v12_final_coverage,
    run as run_v12_final_gemini_coverage,
    status as v12_final_coverage_status,
    validate_setup as validate_v12_final_coverage_setup,
)

META_FIELDS=["policy_id","organisation","sector","country_or_region","policy_title","canonical_url","effective_date","accessed_date","source_filename","source_format","language","word_count_raw","license_or_terms_note","collection_method","include","notes"]
def init_metadata():
    cfg=load_config(); p=ROOT/cfg["paths"]["metadata"]; p.parent.mkdir(parents=True,exist_ok=True)
    if not p.exists():
        with p.open("w",encoding="utf-8",newline="") as f: csv.DictWriter(f,fieldnames=META_FIELDS).writeheader()
    print(p)
def validate(expected):
    cfg=load_config(); errors=[]; rows=[r for r in read_csv(ROOT/cfg["paths"]["metadata"]) if r.get("include","yes").lower()=="yes"]
    if len(rows)!=expected: errors.append(f"expected {expected} included policies, found {len(rows)}")
    ids=[r["policy_id"] for r in rows]
    if len(ids)!=len(set(ids)): errors.append("duplicate policy IDs")
    for family,m in cfg["models"].items():
        if m["model_id"].startswith("REPLACE_"): errors.append(f"set exact model ID for {family}")
    found=sum(1 for _ in conditions()); expected_conditions=len(rows)*len(cfg["models"])*len(cfg["prompts"])+max(0,cfg.get("reproducibility_check",{}).get("total_runs",1)-1)
    if found!=expected_conditions: errors.append(f"only {found}/{expected_conditions} conditions have cleaned inputs")
    for e in errors: print("ERROR",e)
    if errors: raise SystemExit(1)
    print(f"VALID: {len(rows)} policies, {found} conditions")

def test_providers():
    cfg = load_config()
    prompt = "Reply with exactly: API connection successful"
    failed = False
    for family, model in cfg["models"].items():
        try:
            result = generate(
                model["provider"], model["model_id"], prompt,
                model.get("temperature", cfg["temperature"]),
                30, cfg["timeout_seconds"]
            )
            print(
                f'OK {family}: model={model["model_id"]} '
                f'input_tokens={result.get("input_tokens")} '
                f'output_tokens={result.get("output_tokens")} '
                f'response_id={result.get("response_id")}'
            )
        except Exception as exc:
            failed = True
            print(f'FAILED {family}: {type(exc).__name__}: {exc}')
    if failed:
        raise SystemExit(1)
def main():
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest="cmd",required=True)
    s.add_parser("init-metadata"); s.add_parser("preprocess"); v=s.add_parser("validate"); v.add_argument("--expected-policies",type=int,default=3); r=s.add_parser("run"); r.add_argument("--dry-run",action="store_true"); r.add_argument("--retry-truncated",action="store_true"); s.add_parser("evaluate"); s.add_parser("anonymise"); s.add_parser("test-providers"); dc=s.add_parser("decompose-v2-claims"); dc.add_argument("--blind-id",default="S015"); st=s.add_parser("prepare-v2-statements"); st.add_argument("--blind-id",default="S015"); sv=s.add_parser("verify-v2-statements"); sv.add_argument("--blind-id",default="S015"); rv=s.add_parser("revalidate-v2-statements"); rv.add_argument("--blind-id",default="S015"); su=s.add_parser("identify-v2-source-units"); su.add_argument("--policy-id",default="PILOT01"); s.add_parser("prepare-faithfulness"); s.add_parser("freeze-faithfulness"); s.add_parser("validate-human-faithfulness"); s.add_parser("analyse-human-faithfulness"); s.add_parser("finalise-human-faithfulness"); s.add_parser("run-gemini-faithfulness"); gb=s.add_parser("run-gemini-batched-faithfulness"); gb.add_argument("--max-batches",type=int); s.add_parser("run-minicheck-faithfulness"); s.add_parser("validate-coverage"); gc=s.add_parser("run-gemini-coverage"); gc.add_argument("--max-batches",type=int); s.add_parser("analyse-human-coverage"); s.add_parser("validate-v12-final-coverage"); s.add_parser("status-v12-final-coverage"); fgc=s.add_parser("run-v12-final-gemini-coverage"); fgc.add_argument("--max-batches",type=int); s.add_parser("analyse-v12-final-coverage"); a=p.parse_args()
    if a.cmd=="init-metadata": init_metadata()
    elif a.cmd=="preprocess": print(f"Processed {preprocess_all()} policies")
    elif a.cmd=="validate": validate(a.expected_policies)
    elif a.cmd=="run": print(f"Conditions: {run(a.dry_run, a.retry_truncated)}")
    elif a.cmd=="evaluate": print(f"Evaluated {evaluate_all()} outputs")
    elif a.cmd=="anonymise": print(f"Anonymised {anonymise()} outputs")
    elif a.cmd=="test-providers": test_providers()
    elif a.cmd=="decompose-v2-claims":
        count, path = decompose_v2_claims(a.blind_id); print(f"Prepared {count} atomic claims for {a.blind_id}: {path}")
    elif a.cmd=="prepare-v2-statements":
        count, path = prepare_v2_statements(a.blind_id); print(f"Prepared {count} summary statements for {a.blind_id}: {path}")
    elif a.cmd=="verify-v2-statements":
        count, path = verify_v2_statements(a.blind_id); print(f"Verified {count} summary statements for {a.blind_id}: {path}")
    elif a.cmd=="revalidate-v2-statements":
        count, path = revalidate_v2_statements(a.blind_id); print(f"Evidence-valid statements for {a.blind_id}: {count}; {path}")
    elif a.cmd=="identify-v2-source-units":
        count, path = identify_v2_source_units(a.policy_id); print(f"Gemini proposed {count} important source units for {a.policy_id}: {path}")
    elif a.cmd=="prepare-faithfulness":
        count, path = prepare_faithfulness(); print(f"Prepared {count} sentence-level claim candidates: {path}")
    elif a.cmd=="freeze-faithfulness": print(f"Frozen {freeze_human_templates()} claims into each A1/A2/A3 file")
    elif a.cmd=="validate-human-faithfulness": print(f"Validated {validate_human()} human ratings")
    elif a.cmd=="analyse-human-faithfulness":
        unanimous, disagreements, path = analyse_human_agreement(); print(f"Unanimous: {unanimous}; disagreements: {disagreements}; adjudication file: {path}")
    elif a.cmd=="finalise-human-faithfulness":
        count, final_path, summary_path = finalise_human(); print(f"Finalised {count} human claim ratings: {final_path}; summary: {summary_path}")
    elif a.cmd=="run-gemini-faithfulness": print(f"Gemini evaluated {run_gemini()} new claims")
    elif a.cmd=="run-gemini-batched-faithfulness":
        claims, batches, path = run_gemini_batched(a.max_batches); print(f"Gemini batch run evaluated {claims} claims in {batches} batches: {path}")
    elif a.cmd=="run-minicheck-faithfulness": print(f"MiniCheck evaluated {run_minicheck()} claims")
    elif a.cmd=="validate-coverage":
        units, summaries, comparisons = validate_coverage_setup(); print(f"Coverage ready: units={units} summaries={summaries} comparisons={comparisons}")
    elif a.cmd=="run-gemini-coverage":
        units, batches, path = run_gemini_coverage(a.max_batches); print(f"Gemini coverage evaluated {units} units in {batches} batches: {path}")
    elif a.cmd=="analyse-human-coverage":
        comparisons, path = analyse_human_coverage(); print(f"Analysed {comparisons} human coverage comparisons: {path}")
    elif a.cmd=="validate-v12-final-coverage":
        units, summaries, comparisons = validate_v12_final_coverage_setup(); print(f"Final coverage ready: units={units} summaries={summaries} comparisons={comparisons}")
    elif a.cmd=="status-v12-final-coverage":
        current = v12_final_coverage_status(); print(
            f"Final Gemini coverage: {current['successful_unique']}/2970 complete; "
            f"remaining={current['remaining']}; summaries={current['summaries_represented']}/54; "
            f"successful_batches={current['successful_batches']}; failed_batches={current['failed_batches']}"
        )
    elif a.cmd=="run-v12-final-gemini-coverage":
        rows, batches, path = run_v12_final_gemini_coverage(a.max_batches); print(f"Gemini final coverage added {rows} rows in {batches} batches: {path}")
    elif a.cmd=="analyse-v12-final-coverage":
        comparisons, path = analyse_v12_final_coverage(); print(f"Analysed {comparisons} final coverage comparisons: {path}")
if __name__=="__main__": main()
