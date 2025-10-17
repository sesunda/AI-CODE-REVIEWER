# server/agents.py
import asyncio
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from server.providers import llm_call  # <— use real provider

AGENTS = ["linter", "security", "complexity"]


@dataclass
class AgentFinding:
    agent: str
    verdict: str  # "approve", "block", "needs_changes"
    summary: str
    issues: List[Dict[str, Any]]


# --- Agent runner ---
async def run_agent(agent: str, diff: str, meta: Dict[str, Any]) -> AgentFinding:
    """Run a specific agent on the diff using role-tailored prompts."""
    role_prompts = {
        "linter": (
            "You are the Linter Agent. Focus on style, naming, dead code, "
            "docstrings, and cyclomatic complexity ≤ 20.\n"
        ),
        "security": (
            "You are the Security Agent. Prioritize injection, authZ, secrets "
            "exposure, SSRF, path traversal, and unsafe deserialization.\n"
        ),
        "complexity": (
            "You are the Complexity Agent. Flag long functions (>60 lines), "
            "deep nesting (>3), duplication, and low testability. Propose refactors.\n"
        ),
    }

    prompt = (
        role_prompts.get(agent, "You are a code reviewer.\n")
        + "Repository meta:\n"
        + f"{meta}\n\n"
        + "Review the following unified diff and return STRICT JSON with keys: "
          "verdict, summary, issues, patches. "
          'issues entries must have {type, severity, title, line, fix}.\n\n'
        + "DIFF START\n"
        + diff
        + "\nDIFF END"
    )

    result = await llm_call(prompt)
    return AgentFinding(
        agent=agent,
        verdict=str(result.get("verdict", "needs_changes")),
        summary=str(result.get("summary", f"{agent} analysis")),
        issues=list(result.get("issues", [])) or [],
    )


# --- Majority vote ---
def majority_vote(findings: List[AgentFinding]) -> str:
    """Determine verdict based on majority vote with blocking rules."""
    verdicts = [f.verdict for f in findings]
    if "block" in verdicts:
        return "block"
    if verdicts.count("approve") >= 2:
        return "approve"
    return "needs_changes"


# --- Rules loading & enforcement ---
def _load_rules() -> Dict[str, Any]:
    """
    Load approval rules from server/rules/approval_rules.yaml.

    Supports either:
      auto_approve_if:
        - only_docs: true
    or:
      auto_approve_if:
        only_docs: true
    """
    rules_path = Path("server/rules/approval_rules.yaml")
    if not rules_path.exists():
        return {}

    try:
        data = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

    # Normalize structures
    block_on = data.get("block_on", [])
    if isinstance(block_on, dict):
        # {"security":"high"} -> ["security:high"]
        block_on = [f"{k}:{v}" for k, v in block_on.items()]
    elif not isinstance(block_on, list):
        block_on = []

    auto = data.get("auto_approve_if", [])
    only_docs = False
    if isinstance(auto, dict):
        only_docs = bool(auto.get("only_docs"))
    elif isinstance(auto, list):
        for item in auto:
            if isinstance(item, dict) and item.get("only_docs") is True:
                only_docs = True
                break

    return {
        "block_on": set(map(str, block_on)),
        "auto_approve_only_docs": only_docs,
    }


def enforce_rules(
    findings: List[AgentFinding],
    majority_verdict: str,
    meta: Dict[str, Any],
) -> str:
    """Apply approval rules on top of majority vote."""
    rules = _load_rules()

    # Auto-approve on docs-only if enabled
    if meta.get("only_docs") and rules.get("auto_approve_only_docs"):
        return "approve"

    # Block on security:high if configured
    if "security:high" in rules.get("block_on", set()):
        for f in findings:
            for issue in f.issues:
                if (
                    str(issue.get("type", "")).lower() == "security"
                    and str(issue.get("severity", "")).lower() == "high"
                ):
                    return "block"

    return majority_verdict


# --- Public API: async + sync wrappers ---
async def review_async(
    diff: str,
    meta: Optional[Dict[str, Any]] = None,
    files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run all agents concurrently, compute majority, apply rules."""
    meta = meta or {}
    files = files or []  # reserved for future use

    tasks = [run_agent(agent, diff, meta) for agent in AGENTS]
    findings_objs = await asyncio.gather(*tasks)

    majority = majority_vote(findings_objs)
    verdict = enforce_rules(findings_objs, majority, meta)

    # Build a short summary and ensure JSON-serializable findings
    summary = " | ".join(f"{f.agent}: {f.summary}" for f in findings_objs)
    findings = [asdict(f) for f in findings_objs]

    return {"verdict": verdict, "summary": summary, "findings": findings}


def review_diff(
    diff: str,
    meta: Optional[Dict[str, Any]] = None,
    files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Synchronous wrapper (good for tests/CLI).
    FastAPI endpoints should call review_async().
    """
    return asyncio.run(review_async(diff, meta, files))
