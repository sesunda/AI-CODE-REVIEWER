# server/providers.py
import os
import json
import asyncio
from typing import Dict, Any, Optional

from server.schemas import ReviewOut

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore

try:
    from groq import Groq
except Exception:
    Groq = None  # type: ignore

# --- Env & client ---
MODEL = os.getenv("MODEL", "gpt-4o-mini")
PROVIDER = os.getenv("PROVIDER", "openai")  # "openai" or "groq"
MOCK_MODE = os.getenv("MOCK_MODE", "0") == "1"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

_openai_client = None
_groq_client = None

# Initialize OpenAI client
if OpenAI and OPENAI_API_KEY and not MOCK_MODE and PROVIDER == "openai":
    try:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        _openai_client = None  # fall back gracefully

# Initialize Groq client
if Groq and GROQ_API_KEY and not MOCK_MODE and PROVIDER == "groq":
    try:
        _groq_client = Groq(api_key=GROQ_API_KEY)
    except Exception:
        _groq_client = None  # fall back gracefully


# --- Helpers return the SAME schema used by agents.py ---
def _fallback(reason: Optional[str] = None) -> Dict[str, Any]:
    return {
        "verdict": "needs_changes",
        "summary": reason or "Fallback response (parse or API failure).",
        "issues": [
            {
                "type": "tool",
                "severity": "medium",
                "title": "LLM response handling issue",
                "line": None,
                "fix": "Retry or run locally in MOCK_MODE=1",
            }
        ],
        "patches": [],
    }


def _mock(prompt: str) -> Dict[str, Any]:
    """
    Deterministic, role-aware mock.
    - If ONLY_DOCS_TRUE in prompt -> approve (no issues)
    - If risky SQL pattern:
        * Security Agent -> block (security:high)
        * Linter Agent   -> approve (no issues)
        * Complexity     -> needs_changes (medium complexity issue)
    - Else -> needs_changes with a low style suggestion
    """
    # detect role from the agent prompt header added in agents.py
    role = "generic"
    if "You are the Security Agent" in prompt:
        role = "security"
    elif "You are the Linter Agent" in prompt:
        role = "linter"
    elif "You are the Complexity Agent" in prompt:
        role = "complexity"

    # docs-only shortcut (use your docs-only test body or include this token in the diff)
    if "ONLY_DOCS_TRUE" in prompt:
        return {
            "verdict": "approve",
            "summary": "Mocked review: docs-only change.",
            "issues": [],
            "patches": [],
        }

    # very simple SQL-injection heuristics for demo
    risky_patterns = [
        'SELECT * FROM users WHERE id = {',  # f-string
        'f"SELECT * FROM users',             # f-string
        "SELECT * FROM users WHERE id = "    # concatenation
    ]
    is_risky = any(p in prompt for p in risky_patterns)

    if is_risky:
        if role == "security":
            return {
                "verdict": "block",
                "summary": "Mocked review: high-severity security risk detected.",
                "issues": [
                    {
                        "type": "security",
                        "severity": "high",
                        "title": "Possible SQL injection vulnerability.",
                        "line": 4,
                        "fix": "Use parameterized queries or ORM bindings.",
                    }
                ],
                "patches": [],
            }
        elif role == "linter":
            return {
                "verdict": "approve",
                "summary": "Mocked review: linter is OK.",
                "issues": [],
                "patches": [],
            }
        elif role == "complexity":
            return {
                "verdict": "needs_changes",
                "summary": "Mocked review: simplify function for testability.",
                "issues": [
                    {
                        "type": "complexity",
                        "severity": "medium",
                        "title": "Function could be decomposed.",
                        "line": 1,
                        "fix": "Extract database access into a helper.",
                    }
                ],
                "patches": [],
            }

    # default non-risky path
    return {
        "verdict": "needs_changes",
        "summary": "Mocked review for demo/offline mode.",
        "issues": [
            {
                "type": "style",
                "severity": "low",
                "title": "Consider adding a docstring",
                "line": 1,
                "fix": "Add a short docstring to the function.",
            }
        ],
        "patches": [],
    }


# --- Public API used by agents.run_agent() ---
async def llm_call(prompt: str) -> Dict[str, Any]:
    """
    LLM chat wrapper with JSON response & one retry.
    Supports both OpenAI and Groq providers.
    Returns dict with keys: verdict, summary, issues, patches.
    """
    # Mock / no client available
    if MOCK_MODE or (_openai_client is None and _groq_client is None):
        return _mock(prompt)

    system_msg = (
        "You are a strict, helpful code reviewer. "
        "Return STRICT JSON with keys: verdict, summary, issues, patches. "
        "issues is an array of objects: {type, severity, title, line, fix}. "
        "No prose outside JSON."
    )
    user_msg = prompt

    def _create_openai(messages):
        # Run the blocking SDK call in a thread to avoid blocking the event loop
        return _openai_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
            timeout=20,  # seconds (SDK v1 supports this kwarg)
        )
    
    def _create_groq(messages):
        # Run the blocking SDK call in a thread to avoid blocking the event loop
        return _groq_client.chat.completions.create(
            model="llama-3.1-70b-versatile",  # Groq's recommended model
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
            timeout=20,
        )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    try:
        # Choose provider and create function
        if PROVIDER == "groq" and _groq_client is not None:
            _create = _create_groq
        elif PROVIDER == "openai" and _openai_client is not None:
            _create = _create_openai
        else:
            return _fallback("No valid LLM provider available")
        
        # First attempt
        resp = await asyncio.to_thread(_create, messages)
        content = resp.choices[0].message.content or ""
        try:
            data = json.loads(content)
            normalized_data = _normalize_schema(data)
            # Validate with Pydantic model
            try:
                safe = ReviewOut(**normalized_data).model_dump()
                return safe
            except Exception:
                return {
                    "verdict": "needs_changes",
                    "summary": "Validation failed; returning safe fallback.",
                    "issues": [],
                    "patches": []
                }
        except json.JSONDecodeError:
            # Retry with explicit schema nudge
            retry_messages = messages + [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "Return STRICT JSON only using keys {verdict, summary, issues, patches}. No prose."
                    ),
                },
            ]
            retry = await asyncio.to_thread(_create, retry_messages)
            retry_content = retry.choices[0].message.content or ""
            try:
                data = json.loads(retry_content)
                normalized_data = _normalize_schema(data)
                # Validate with Pydantic model
                try:
                    safe = ReviewOut(**normalized_data).model_dump()
                    return safe
                except Exception:
                    return {
                        "verdict": "needs_changes",
                        "summary": "Validation failed; returning safe fallback.",
                        "issues": [],
                        "patches": []
                    }
            except json.JSONDecodeError:
                return _fallback("JSON parse failed after retry.")
    except Exception as e:
        return _fallback(f"LLM call failed: {e}")


# --- Schema normalizer so callers always get verdict/summary/issues/patches ---
def _normalize_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    # Accept alternative key names like "decision" -> "verdict"
    verdict = data.get("verdict") or data.get("decision") or "needs_changes"
    summary = data.get("summary") or data.get("rationale") or ""
    issues = data.get("issues") or []
    patches = data.get("patches") or []

    # Ensure list types
    if not isinstance(issues, list):
        issues = []
    if not isinstance(patches, list):
        patches = []

    return {
        "verdict": str(verdict),
        "summary": str(summary),
        "issues": issues,
        "patches": patches,
    }
