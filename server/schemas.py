"""
Pydantic models for validating LLM output and API responses.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class Issue(BaseModel):
    """Model for individual code review issues"""
    type: str = Field(..., description="Type of issue (security, style, complexity, etc.)")
    severity: str = Field(..., description="Severity level (low, medium, high)")
    title: str = Field(..., description="Brief title describing the issue")
    line: Optional[int] = Field(None, description="Line number where the issue occurs")
    fix: Optional[str] = Field(None, description="Suggested fix for the issue")


class ReviewOut(BaseModel):
    """Model for complete code review output"""
    verdict: str = Field(..., description="Overall review verdict (approve, needs_changes, block)")
    summary: str = Field(..., description="Summary of the review findings")
    issues: List[Issue] = Field(default=[], description="List of issues found")
    patches: List = Field(default=[], description="List of suggested patches")


# Export for reuse
__all__ = ["Issue", "ReviewOut"]
