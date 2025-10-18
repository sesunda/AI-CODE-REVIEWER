import os
import difflib
import re
from typing import Any, Dict, List, Optional
from difflib import unified_diff

from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from server.schemas import ReviewIn, ReviewOut, DemoIn, DemoOut
from difflib import HtmlDiff

# Configuration
MAX_DIFF_BYTES = int(os.getenv("MAX_DIFF_BYTES", "5000"))

# Redaction patterns for sensitive data
REDACT_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)password\s*[:=]\s*\S+")
]

def redact(text: str) -> str:
    """Redact sensitive information from text"""
    for pat in REDACT_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text

from .agents import review_diff

router = APIRouter()




@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"ok": True}


class ReviewRequest(BaseModel):
    diff: str
    repo_meta: Optional[Dict[str, Any]] = None
    files_changed: Optional[List[str]] = None
    store_review: Optional[bool] = True
    generate_audio: Optional[bool] = False

@router.post("/review")
async def review_code(request: ReviewRequest):
    try:
        result = await review_diff(                       # <-- await exactly once
            diff=request.diff,
            meta=request.repo_meta or {},
            files=request.files_changed or [],
        )
        # attach review_id/audio here if you have DB/TTS; otherwise just:
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during code review: {e}")


@router.get("/reviews")
async def list_reviews(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    repo: Optional[str] = Query(None)
):
    """List recent code reviews"""
    try:
        reviews = await db_manager.list_reviews(limit, offset, repo)
        return {
            "reviews": [
                {
                    "id": review.id,
                    "verdict": review.verdict,
                    "summary": review.summary,
                    "timestamp": review.timestamp.isoformat(),
                    "repo": review.repo_meta.get("repo", "unknown")
                }
                for review in reviews
            ],
            "total": len(reviews)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing reviews: {e}")


@router.get("/reviews/{review_id}")
async def get_review(review_id: str):
    """Get a specific review by ID"""
    try:
        review = await db_manager.get_review(review_id)
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        
        return {
            "id": review.id,
            "diff": review.diff,
            "verdict": review.verdict,
            "summary": review.summary,
            "findings": review.findings,
            "repo_meta": review.repo_meta,
            "files_changed": review.files_changed,
            "timestamp": review.timestamp.isoformat(),
            "provider": review.provider
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving review: {e}")


@router.post("/demo")
async def demo_diff_review(
    old_code: str = Body(..., embed=True, example="print('hello')\n"),
    new_code: str = Body(..., embed=True, example="print('hello, world')\n"),
):
    diff = "\n".join(unified_diff(old_code.splitlines(), new_code.splitlines(), fromfile="old", tofile="new", lineterm=""))
    result = await review_diff(diff=diff, meta={}, files=[])
    return {"generated_diff": diff, "review_result": result}


@router.get("/tts/voices")
async def list_voices():
    """List available TTS voices"""
    try:
        voices = await tts_manager.get_available_voices()
        return {"voices": voices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing voices: {e}")

@router.get("/ui/diff", response_class=HTMLResponse, tags=["ui"], summary="Visual diff (HTML)")
async def ui_diff(old: str, new: str):
    """
    Quick visual diff for demos.
    Example:
    /ui/diff?old=print('hello')%0A&new=print('hello, world!')%0A
    """
    h = HtmlDiff(wrapcolumn=80)
    html = h.make_file(old.splitlines(), new.splitlines(), fromdesc="old", todesc="new")
    return HTMLResponse(content=html)


@router.get("/mcp/resources/{slug:path}")
async def get_resource(slug: str):
    """Get MCP resources by slug"""
    resources = {
        "rules/approval": {
            "uri": "server/rules/approval_rules.yaml",
            "mimeType": "application/x-yaml",
            "content": None
        },
        "prompts/system": {
            "uri": "server/prompts/reviewer_system.md", 
            "mimeType": "text/markdown",
            "content": None
        },
        "prompts/style-guide": {
            "uri": "server/prompts/style_guide.md",
            "mimeType": "text/markdown", 
            "content": None
        }
    }
    
    if slug not in resources:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    resource = resources[slug]
    try:
        with open(resource["uri"], "r", encoding="utf-8") as f:
            resource["content"] = f.read()
        return resource
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Resource file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading resource: {e}")


@router.get("/mcp/tools")
async def mcp_tools():
    return {
        "tools": [
            {
                "name": "review_diff",
                "description": "Analyze code diffs for quality, security, and complexity.",
                "endpoint": "/review",
            },
            {
                "name": "demo_diff",
                "description": "Generate a diff between two snippets and run review.",
                "endpoint": "/demo",
            },
        ]
    }


@router.get("/config")
def config_view():
    return {
        "provider": os.getenv("PROVIDER"),
        "model": os.getenv("GROQ_MODEL") or os.getenv("MODEL"),
        "mock_mode": os.getenv("MOCK_MODE"),
        "db_backend": os.getenv("DATABASE_BACKEND"),
    }

