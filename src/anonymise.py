from __future__ import annotations
import csv, random, shutil
from .common import ROOT, load_config, read_csv
def anonymise():
    cfg=load_config(); successful=[r for r in read_csv(ROOT/cfg["paths"]["logs"]) if r["status"]=="success"]
    latest={}
    for row in successful:
        key=(row["policy_id"],row["model_family"],row["prompt_strategy"],row.get("replicate","1"))
        if key not in latest or row.get("timestamp_utc","") > latest[key].get("timestamp_utc",""):
            latest[key]=row
    logs=list(latest.values())
    rng=random.Random(cfg["random_seed"]); rng.shuffle(logs); out=ROOT/cfg["paths"]["anonymised"]; out.mkdir(parents=True,exist_ok=True); key=[]
    for i,row in enumerate(logs,1):
        blind=f"S{i:03d}"; shutil.copyfile(ROOT/row["text_path"],out/f"{blind}.txt"); key.append({"blind_id":blind,"run_id":row["run_id"],"policy_id":row["policy_id"],"model_family":row["model_family"],"prompt_strategy":row["prompt_strategy"],"replicate":row.get("replicate","1")})
    if key:
        with (out/"BLINDING_KEY_RESTRICTED.csv").open("w",encoding="utf-8",newline="") as f: w=csv.DictWriter(f,fieldnames=key[0]); w.writeheader(); w.writerows(key)
    return len(key)
