import os
import difflib
import re
from typing import Any, Dict, List, Optional

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

from server.agents import review_async  # use the async reviewer
from server.database import db_manager, ReviewRecord
from server.tts import tts_manager, AudioConfig

router = APIRouter()




@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"ok": True}


@router.post("/review", response_model=ReviewOut, tags=["review"], summary="Review a unified diff", description="Runs linter, security, and complexity agents. Honors approval rules and returns a final verdict.")
async def review_code(payload: ReviewIn = Body(
    ...,
    examples={
        "docs_only": {
            "summary": "Docs-only change (auto-approve via rules)",
            "value": {
                "diff": "@@ -1 +1 @@\n-# Title\n+# Title (doc tweak)\n",
                "repo_meta": {"only_docs": True},
                "store_review": False
            }
        },
        "mixed_verdict": {
            "summary": "1 approve, 1 needs_changes, 1 block (overall block)",
            "value": {
                "diff": "@@ -1 +1 @@\n-query = f\"SELECT * FROM users WHERE id={user_input}\"\n+query = db.execute('SELECT * FROM users WHERE id = %s', [user_input])\n",
                "store_review": False
            }
        },
        "security_block": {
            "summary": "High-severity security issue (block)",
            "value": {
                "diff": "@@ -1 +1 @@\n-password = 'hardcoded'\n+password = os.getenv('APP_PASSWORD')\n",
                "store_review": False
            }
        }
    }
)):
    """Review code diff and return analysis"""
    try:
        # Validate diff size
        if len(payload.diff.encode("utf-8")) > MAX_DIFF_BYTES:
            raise HTTPException(413, "Diff too large; submit smaller chunks.")
        
        # Sanitize sensitive data
        diff = redact(payload.diff)
        
        # Run the review
        result = await review_async(
            diff=diff,
            meta=payload.repo_meta,
            files=payload.files_changed,
        )
        
        # Store in database if requested
        review_id = None
        if payload.store_review:
            review_record = ReviewRecord(
                diff=payload.diff,
                verdict=result["verdict"],
                summary=result["summary"],
                findings=result["findings"],
                repo_meta=payload.repo_meta or {},
                files_changed=payload.files_changed or [],
                provider=os.getenv("PROVIDER", "openai")
            )
            review_id = await db_manager.store_review(review_record)
        
        # Generate audio if requested
        audio_base64 = None
        if payload.generate_audio and tts_manager.enabled:
            audio_bytes = await tts_manager.generate_review_audio(
                result["summary"],
                result["findings"]
            )
            if audio_bytes:
                audio_base64 = tts_manager.audio_to_base64(audio_bytes)
        
        # Build response
        response = {
            "verdict": result["verdict"],
            "summary": result["summary"],
            "findings": result["findings"],
            "review_id": review_id,
            "audio": audio_base64
        }
        
        return response
        
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


@router.post("/demo", response_model=DemoOut, tags=["demo"], summary="Generate a diff and review it")
async def demo_code_comparison(payload: DemoIn = Body(
    ...,
    examples={
        "hello_world": {
            "summary": "Tiny change",
            "value": {"old_code":"print('hello')\n","new_code":"print('hello, world!')\n"}
        }
    }
)):
    """Demo endpoint for comparing old and new code"""
    try:
        # Generate unified diff using difflib
        diff_lines = list(difflib.unified_diff(
            payload.old_code.splitlines(keepends=True),
            payload.new_code.splitlines(keepends=True),
            fromfile="old",
            tofile="new"
        ))
        
        # Convert diff lines to string
        generated_diff = ''.join(diff_lines)
        
        # Validate generated diff size
        if len(generated_diff.encode("utf-8")) > MAX_DIFF_BYTES:
            raise HTTPException(413, "Generated diff too large")
        
        # Sanitize sensitive data
        diff = redact(generated_diff)
        
        # Run code review on the generated diff
        review_result = await review_async(
            diff=diff,
            meta={}
        )
        
        return {
            "generated_diff": generated_diff,
            "review_result": review_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during demo comparison: {e}")


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

