# server/providers.py
import os
import json
import requests

PROVIDER = os.getenv("PROVIDER", "mock").lower()

# --- Groq config ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
PREFERRED = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
FALLBACKS = ["llama3-70b-8192", "llama-3.1-8b-instant"]



def _groq_chat(model: str, messages: list[dict]) -> dict:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    body = {"model": model, "messages": messages, "temperature": 0.1}
    r = requests.post(url, headers=headers, json=body, timeout=20)
    if r.status_code == 400 and "model_decommissioned" in r.text:
        raise RuntimeError("MODEL_DECOMMISSIONED")
    r.raise_for_status()
    return r.json()

def groq_llm_call(prompt: str, role: str = "agent") -> dict:
    sys_msg = {"role":"system","content":"You are a code reviewer. Return strict JSON with keys: verdict, summary, issues[]."}
    user_msg = {"role":"user","content": prompt}
    models = [PREFERRED] + [m for m in FALLBACKS if m != PREFERRED]
    last_err = None
    for m in models:
        try:
            data = _groq_chat(m, [sys_msg, user_msg])
            content = data["choices"][0]["message"]["content"]
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                nudged = _groq_chat(m, [sys_msg, user_msg, {"role":"user","content":"Return strict JSON only."}])
                return json.loads(nudged["choices"][0]["message"]["content"])
        except Exception as e:
            last_err = e
            if isinstance(e, RuntimeError) and str(e) == "MODEL_DECOMMISSIONED":
                continue  # try next model in FALLBACKS
            break
    return {
        "verdict": "needs_changes",
        "summary": f"LLM call failed: {last_err}",
        "issues": [
          {"type":"tool","severity":"medium","title":"LLM response handling issue",
           "line": None, "fix": "Set GROQ_MODEL to a supported ID or enable MOCK_MODE=1."}
        ]
    }


def llm_call(prompt: str, role: str = "agent", schema_hint: dict | None = None) -> dict:
    if PROVIDER == "groq" and GROQ_API_KEY:
        return groq_llm_call(prompt, role)
    # TODO: add manus/openai providers here if needed
    return {
        "verdict": "needs_changes",
        "summary": "Mock/provider not configured",
        "issues": []
    }
