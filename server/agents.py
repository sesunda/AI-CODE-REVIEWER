# server/agents.py
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from . import providers  # ensure this import exists (your llm_call lives here)

AGENTS = ["linter", "security", "complexity"]

@dataclass
class AgentFinding:
    agent: str
    verdict: str   # "approve" | "needs_changes" | "block"
    summary: str
    issues: List[Dict[str, Any]]

async def run_agent(agent: str, diff: str, meta: Dict[str, Any]) -> AgentFinding:
    prompts = {
        "linter":    f"Analyze this code diff for linting/style issues:\n{diff}",
        "security":  f"Review this code diff for security vulnerabilities:\n{diff}",
        "complexity":f"Assess code complexity and maintainability:\n{diff}",
    }
    prompt = prompts.get(agent, f"Review code diff:\n{diff}")

    # If providers.llm_call is async, await directly; if sync, wrap with to_thread:
    if asyncio.iscoroutinefunction(providers.llm_call):
        result = await providers.llm_call(prompt, role=agent)
    else:
        result = await asyncio.to_thread(providers.llm_call, prompt, agent)

    return AgentFinding(
        agent=agent,
        verdict=result.get("verdict", "needs_changes"),
        summary=result.get("summary", f"{agent} analysis"),
        issues=list(result.get("issues", [])) or [],
    )


def majority_vote(findings: List[AgentFinding]) -> str:
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


# Optional: simple rules hook; keep your existing enforce_rules if you have it
def enforce_rules(findings: List[AgentFinding], majority_verdict: str, meta: Dict[str, Any]) -> str:
    # Keep your yaml-based rules here if already implemented.
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


async def review_diff(diff: str, meta: Optional[Dict[str, Any]] = None, files: Optional[List[str]] = None) -> Dict[str, Any]:
    if meta is None: meta = {}
    if files is None: files = []

    tasks = [run_agent(a, diff, meta) for a in AGENTS]
    findings = await asyncio.gather(*tasks)

    majority = majority_vote(findings)
    final_verdict = enforce_rules(findings, majority, meta)

    summary = " | ".join(f"{f.agent}: {f.summary}" for f in findings)
    return {
        "verdict": final_verdict,
        "summary": summary,
        "findings": [f.__dict__ for f in findings],
    }
