from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class Issue(BaseModel):
    type: str = Field(..., examples=["security", "style", "complexity"])
    severity: str = Field(..., examples=["low", "medium", "high"])
    title: Optional[str] = None
    message: Optional[str] = None
    line: Optional[int] = None
    fix: Optional[str] = None
    agent: Optional[str] = None

class AgentFindingOut(BaseModel):
    agent: str
    verdict: str  # approve | needs_changes | block
    summary: str
    issues: List[Dict[str, Any]] = []

class ReviewIn(BaseModel):
    diff: str
    repo_meta: Optional[Dict[str, Any]] = None
    files_changed: Optional[List[str]] = None
    store_review: Optional[bool] = True
    generate_audio: Optional[bool] = False

class ReviewOut(BaseModel):
    verdict: str
    summary: str
    findings: List[AgentFindingOut]
    review_id: Optional[str] = None

class DemoIn(BaseModel):
    old_code: str
    new_code: str

class DemoOut(BaseModel):
    generated_diff: str
    review_result: ReviewOut