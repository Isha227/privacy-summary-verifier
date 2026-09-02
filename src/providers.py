from __future__ import annotations
import os, time, requests

def _raise_api_error(response: requests.Response) -> None:
    if response.ok:
        return
    try:
        payload = response.json()
        detail = payload.get("error", payload)
        if isinstance(detail, dict):
            message = detail.get("message", str(detail))
            code = detail.get("code") or detail.get("type")
            suffix = f" [{code}]" if code else ""
            raise RuntimeError(f"HTTP {response.status_code}: {message}{suffix}")
    except ValueError:
        pass
    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")

def generate(provider: str, model: str, prompt: str, temperature: float | None, max_tokens: int, timeout: int) -> dict:
    if provider == "openai":
        url = "https://api.openai.com/v1/responses"; key = os.getenv("OPENAI_API_KEY")
        payload = {"model": model, "input": prompt, "max_output_tokens": max_tokens}
        if temperature is not None:
            payload["temperature"] = temperature
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        started = time.perf_counter(); r = requests.post(url, headers=headers, json=payload, timeout=timeout); _raise_api_error(r); data = r.json()
        text = data.get("output_text") or "".join(c.get("text", "") for o in data.get("output", []) for c in o.get("content", []))
        usage = data.get("usage", {}); return {"text": text, "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"), "latency_ms": round((time.perf_counter()-started)*1000), "response_id": data.get("id")}
    if provider in {"together", "mistral", "openrouter", "local"}:
        if provider == "together":
            base = "https://api.together.xyz/v1"
            key = os.getenv("TOGETHER_API_KEY")
        elif provider == "mistral":
            base = "https://api.mistral.ai/v1"
            key = os.getenv("MISTRAL_API_KEY")
        elif provider == "openrouter":
            base = "https://openrouter.ai/api/v1"
            key = os.getenv("OPENROUTER_API_KEY")
        else:
            base = os.getenv("LOCAL_BASE_URL", "").rstrip("/")
            key = os.getenv("LOCAL_API_KEY")
        if not key:
            raise RuntimeError(f"Missing API key for provider: {provider}")
        payload = {"model": model, "messages": [{"role":"user","content":prompt}], "max_tokens":max_tokens}
        if temperature is not None:
            payload["temperature"] = temperature
        started = time.perf_counter(); r = requests.post(f"{base}/chat/completions", headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"}, json=payload, timeout=timeout); _raise_api_error(r); data=r.json(); usage=data.get("usage", {})
        return {"text":data["choices"][0]["message"]["content"], "input_tokens":usage.get("prompt_tokens"), "output_tokens":usage.get("completion_tokens"), "latency_ms":round((time.perf_counter()-started)*1000), "response_id":data.get("id")}
    raise ValueError(f"Unknown provider: {provider}")
