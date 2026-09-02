from __future__ import annotations
import os, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from .common import ROOT, append_csv, load_config, read_csv, sha256_text, write_json
from .providers import generate

FIELDS = ["run_id","policy_id","model_family","model_id","provider","prompt_strategy","prompt_version","replicate","temperature","max_output_tokens","input_tokens","output_tokens","latency_ms","timestamp_utc","status","error","source_sha256","prompt_sha256","response_id","text_path","json_path"]

def conditions():
    cfg=load_config(); rows=read_csv(ROOT/cfg["paths"]["metadata"])
    for row in rows:
        if row.get("include","yes").lower() != "yes": continue
        source=ROOT/cfg["paths"]["clean"]/f'{row["policy_id"]}.txt'
        if not source.exists(): continue
        for family, model in cfg["models"].items():
            for strategy, prompt_path in cfg["prompts"].items():
                check = cfg.get("reproducibility_check", {})
                repetitions = check.get("total_runs", 1) if (
                    row["policy_id"] == check.get("policy_id")
                    and family == check.get("model_family")
                    and strategy == check.get("prompt_strategy")
                ) else 1
                for replicate in range(1, repetitions + 1):
                    yield cfg,row,source,family,model,strategy,ROOT/prompt_path,replicate

def run(dry_run=False, retry_truncated=False):
    cfg_for_log = load_config()
    prior = read_csv(ROOT / cfg_for_log["paths"]["logs"])
    completed = {
        (r["policy_id"], r["model_family"], r["prompt_strategy"], r.get("replicate", "1"))
        for r in prior if r.get("status") == "success"
    }
    latest = {}
    for r in prior:
        key = (r.get("policy_id"), r.get("model_family"), r.get("prompt_strategy"), r.get("replicate", "1"))
        if key not in latest or r.get("timestamp_utc", "") > latest[key].get("timestamp_utc", ""):
            latest[key] = r
    total=0
    for cfg,row,source,family,model,strategy,prompt_path,replicate in conditions():
        total+=1; label=f'{row["policy_id"]}__{family}__{strategy}__r{replicate}'
        if dry_run: print(label); continue
        condition_key = (row["policy_id"], family, strategy, str(replicate))
        previous = latest.get(condition_key)
        exhausted_previous_limit = bool(
            previous
            and previous.get("status") == "success"
            and previous.get("output_tokens")
            and previous.get("max_output_tokens")
            and int(previous["output_tokens"]) >= int(previous["max_output_tokens"])
            and int(previous["max_output_tokens"]) < int(cfg["max_output_tokens"])
        )
        if retry_truncated and not exhausted_previous_limit:
            print(f"SKIP not truncated {label}")
            continue
        if condition_key in completed and not (retry_truncated and exhausted_previous_limit):
            print(f"SKIP successful {label}")
            continue
        policy=source.read_text(encoding="utf-8"); template=prompt_path.read_text(encoding="utf-8"); prompt=template.replace("{{POLICY_TEXT}}",policy)
        outdir=ROOT/cfg["paths"]["outputs"]/row["policy_id"]; text_path=outdir/f"{label}.txt"; json_path=outdir/f"{label}.json"
        temperature=model.get("temperature",cfg["temperature"])
        log={"run_id":str(uuid.uuid4()),"policy_id":row["policy_id"],"model_family":family,"model_id":model["model_id"],"provider":model["provider"],"prompt_strategy":strategy,"prompt_version":str(cfg.get("prompt_version", "1.0")),"replicate":replicate,"temperature":temperature,"max_output_tokens":cfg["max_output_tokens"],"timestamp_utc":datetime.now(timezone.utc).isoformat(),"source_sha256":sha256_text(policy),"prompt_sha256":sha256_text(template),"text_path":str(text_path.relative_to(ROOT)),"json_path":str(json_path.relative_to(ROOT))}
        try:
            result=None
            for attempt in range(cfg["retries_on_technical_failure"]+1):
                try: result=generate(model["provider"],model["model_id"],prompt,temperature,cfg["max_output_tokens"],cfg["timeout_seconds"]); break
                except Exception:
                    if attempt == cfg["retries_on_technical_failure"]: raise
                    time.sleep(2**attempt)
            text_path.parent.mkdir(parents=True,exist_ok=True); text_path.write_text(result["text"],encoding="utf-8"); write_json(json_path,{**log,**result}); log.update(result); log.update(status="success",error="")
        except Exception as e: log.update(status="error",error=f"{type(e).__name__}: {e}")
        append_csv(ROOT/cfg["paths"]["logs"],log,FIELDS)
        if log.get("status") == "success":
            completed.add(condition_key)
            latest[condition_key] = log
    return total
