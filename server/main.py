import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
load_dotenv()

logging.info(f"[Startup] PROVIDER={os.getenv('PROVIDER')} MODEL={os.getenv('GROQ_MODEL') or os.getenv('MODEL')}")

from .router import router
from .database import db_manager
from .tts import tts_manager

# TODO: Add slowapi rate limiting for public deployment
# Rate limiting should be enabled when deploying to production
# For local development, rate limiting is disabled by default
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False

# Rate limiting configuration
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
IS_PUBLIC_DEPLOYMENT = os.getenv("PUBLIC_DEPLOYMENT", "false").lower() == "true"

app = FastAPI(
    title="AI Code Reviewer",
    description=(
        "Multi-agent code review with approval rules. "
        "Use **/demo** to generate a diff, then **/review** to analyze.\n\n"
        "MCP discovery routes are available for reference under **/mcp/**.*"
    ),
    version="1.0.0",
    contact={"name": "Hackathon Team", "url": "https://example.com"},
    license_info={"name": "MIT"},
)

# Initialize rate limiter if available and enabled
limiter = None
if SLOWAPI_AVAILABLE and (RATE_LIMIT_ENABLED or IS_PUBLIC_DEPLOYMENT):
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["1000/hour"]  # Conservative default for public deployment
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add permissive CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the router
app.include_router(router)

# Health check with enhanced status
@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "AI Code Reviewer",
        "version": "1.0.0",
        "status": "healthy",
        "features": {
            "mcp_server": True,
            "database": db_manager.backend != "none",
            "tts": tts_manager.enabled,
            "providers": ["openai", "groq"]
        }
    }

# Database status endpoint
@app.get("/database/status")
async def database_status():
    """Check database connectivity"""
    return {
        "backend": db_manager.backend,
        "connected": db_manager.backend != "none"
    }

# TTS status endpoint
@app.get("/tts/status")
async def tts_status():
    """Check TTS service status"""
    return {
        "enabled": tts_manager.enabled,
        "provider": "elevenlabs" if tts_manager.enabled else None
    }

# uvicorn server.main:app --reload
