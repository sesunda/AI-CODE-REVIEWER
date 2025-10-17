import os
from typing import Dict, List, Any

def load_markdown_file(filepath: str) -> str:
    """Load markdown file content, return empty string if not found"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

def build_agent_prompt(agent: str, diff: str, meta: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build agent-specific prompt with system and user messages"""
    
    # Load base prompts
    system_prompt = load_markdown_file("server/prompts/reviewer_system.md")
    style_guide = load_markdown_file("server/prompts/style_guide.md")
    
    # Role-specific focus areas
    role_deltas = {
        "linter": """
Focus on:
- Code style and formatting consistency
- Variable and function naming conventions
- Dead code detection and removal
- Cyclomatic complexity (flag if > 20)
- Unused imports and variables
- Code organization and structure
""",
        "security": """
Focus on:
- SQL injection vulnerabilities
- Authorization and authentication flaws
- Hardcoded secrets and credentials
- SSRF (Server-Side Request Forgery) risks
- Path traversal vulnerabilities
- Unsafe deserialization
- Input validation and sanitization
- XSS and injection attacks
""",
        "complexity": """
Focus on:
- Functions longer than 60 lines
- Nesting depth greater than 3 levels
- Code duplication and DRY violations
- Testability concerns
- Maintainability issues
- Performance bottlenecks
- Cognitive complexity
- Separation of concerns
"""
    }
    
    # Get role-specific guidance
    role_guidance = role_deltas.get(agent, "Review the code for general issues.")
    
    # Build system message
    system_content = f"{system_prompt}\n\n{role_guidance}"
    if style_guide:
        system_content += f"\n\nStyle Guide:\n{style_guide}"
    
    # Build user message with context
    meta_info = ""
    if meta:
        meta_items = [f"- {k}: {v}" for k, v in meta.items()]
        meta_info = f"\n\nRepository Context:\n" + "\n".join(meta_items)
    
    user_content = f"""Please review the following code diff for {agent}-related issues:

{diff}{meta_info}

Provide your analysis in JSON format with:
- "decision": "approve", "block", or "needs_changes"
- "summary": Brief explanation of your findings
- "issues": Array of specific issues found with type, severity, message, and line number"""
    
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content}
    ]
