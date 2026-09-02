from __future__ import annotations
import csv, math, re
from .common import ROOT, load_config, read_csv

def sentences(text): return [x for x in re.split(r"(?<=[.!?])\s+|\n+",text) if x.strip()]
def words(text): return re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?",text)
def syllables(word):
    w=word.lower(); n=len(re.findall(r"[aeiouy]+",w)); n-=int(w.endswith("e") and n>1); return max(1,n)
def metrics(text):
    ws=words(text); ss=sentences(text); wc=max(1,len(ws)); sc=max(1,len(ss)); syl=sum(syllables(w) for w in ws); complex_n=sum(syllables(w)>=3 for w in ws)
    return {"words":len(ws),"sentences":len(ss),"characters":len(text),"flesch_reading_ease":round(206.835-1.015*wc/sc-84.6*syl/wc,2),"flesch_kincaid_grade":round(.39*wc/sc+11.8*syl/wc-15.59,2),"smog_grade":round(1.043*math.sqrt(complex_n*(30/sc))+3.1291,2) if len(ss)>=3 else ""}
def evaluate_all():
    cfg=load_config(); log=read_csv(ROOT/cfg["paths"]["logs"]); rows=[]
    target_range=cfg.get("target_word_range")
    latest={}
    for item in log:
        if item.get("status") == "success":
            key=(item["policy_id"],item["model_family"],item["prompt_strategy"],item.get("replicate","1"))
            if key not in latest or item.get("timestamp_utc","") > latest[key].get("timestamp_utc",""):
                latest[key]=item
    for item in latest.values():
        if item["status"]!="success": continue
        source=(ROOT/cfg["paths"]["clean"]/f'{item["policy_id"]}.txt').read_text(encoding="utf-8"); summary=(ROOT/item["text_path"]).read_text(encoding="utf-8"); sm=metrics(summary); src=metrics(source)
        leaked=bool(re.search(
            r"(?im)^\s*(?:analysis:|step 1\b|first,? i (?:will|need to)\b|let me analyze\b)|"
            r"(?i:\binternal checklist\b|\bmy reasoning\b)",
            summary,
        ))
        format_violation=bool(re.search(r"(?m)^\s*(?:#{1,6}\s|[-*•]\s|\d+[.)]\s)",summary))
        within_target=(target_range[0] <= sm["words"] <= target_range[1]) if target_range else ""
        rows.append({"run_id":item["run_id"],"policy_id":item["policy_id"],"model_family":item["model_family"],"prompt_strategy":item["prompt_strategy"],"replicate":item.get("replicate","1"),**sm,"within_target_words":within_target,"continuous_prose_format_compliant":not format_violation,"reasoning_leak_detected":leaked,"output_tokens":item.get("output_tokens",""),"max_output_tokens":item.get("max_output_tokens",""),"at_token_ceiling":bool(item.get("output_tokens") and item.get("max_output_tokens") and int(item["output_tokens"])>=int(item["max_output_tokens"])),"source_words":src["words"],"word_compression_ratio":round(sm["words"]/max(1,src["words"]),4),"character_compression_ratio":round(sm["characters"]/max(1,src["characters"]),4)})
    path=ROOT/cfg["paths"]["evaluations"]; path.parent.mkdir(parents=True,exist_ok=True)
    if rows:
        with path.open("w",encoding="utf-8",newline="") as f: w=csv.DictWriter(f,fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
    return len(rows)
