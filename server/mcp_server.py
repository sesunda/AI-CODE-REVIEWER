"""
MCP (Model Context Protocol) server implementation for AI Code Reviewer.
This module provides MCP-compliant tools for code review functionality.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional, Sequence
from dataclasses import dataclass

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource, 
    Tool, 
    TextContent, 
    ImageContent, 
    EmbeddedResource,
    LoggingLevel
)

from .agents import review_async
from .providers import llm_call


# Initialize MCP server
server = Server("ai-code-reviewer")


@dataclass
class CodeReviewRequest:
    """Request model for code review"""
    diff: str
    repo_meta: Optional[Dict[str, Any]] = None
    files_changed: Optional[List[str]] = None


@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available MCP tools"""
    return [
        Tool(
            name="review_code_diff",
            description="Review a code diff using multiple AI agents (linter, security, complexity)",
            inputSchema={
                "type": "object",
                "properties": {
                    "diff": {
                        "type": "string",
                        "description": "The unified diff to review"
                    },
                    "repo_meta": {
                        "type": "object",
                        "description": "Repository metadata (optional)",
                        "properties": {
                            "repo": {"type": "string"},
                            "branch": {"type": "string"},
                            "author": {"type": "string"},
                            "only_docs": {"type": "boolean"}
                        }
                    },
                    "files_changed": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of changed files (optional)"
                    }
                },
                "required": ["diff"]
            }
        ),
        Tool(
            name="get_review_health",
            description="Check the health status of the code review service",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="list_available_agents",
            description="List all available review agents and their capabilities",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> Sequence[TextContent]:
    """Handle MCP tool calls"""
    
    if name == "review_code_diff":
        try:
            # Extract arguments
            diff = arguments.get("diff", "")
            repo_meta = arguments.get("repo_meta", {})
            files_changed = arguments.get("files_changed", [])
            
            if not diff:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "No diff provided",
                        "verdict": "error"
                    }, indent=2)
                )]
            
            # Run the review
            result = await review_async(
                diff=diff,
                meta=repo_meta,
                files=files_changed
            )
            
            # Format response
            response = {
                "verdict": result["verdict"],
                "summary": result["summary"],
                "findings": result["findings"],
                "timestamp": asyncio.get_event_loop().time()
            }
            
            return [TextContent(
                type="text",
                text=json.dumps(response, indent=2)
            )]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Review failed: {str(e)}",
                    "verdict": "error"
                }, indent=2)
            )]
    
    elif name == "get_review_health":
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "healthy",
                "agents": ["linter", "security", "complexity"],
                "providers": ["openai", "mock"],
                "timestamp": asyncio.get_event_loop().time()
            }, indent=2)
        )]
    
    elif name == "list_available_agents":
        agents_info = {
            "linter": {
                "description": "Code style, formatting, and linting issues",
                "focus_areas": [
                    "Code style and formatting consistency",
                    "Variable and function naming conventions", 
                    "Dead code detection and removal",
                    "Cyclomatic complexity (flag if > 20)",
                    "Unused imports and variables",
                    "Code organization and structure"
                ]
            },
            "security": {
                "description": "Security vulnerabilities and risks",
                "focus_areas": [
                    "SQL injection vulnerabilities",
                    "Authorization and authentication flaws",
                    "Hardcoded secrets and credentials",
                    "SSRF (Server-Side Request Forgery) risks",
                    "Path traversal vulnerabilities",
                    "Unsafe deserialization",
                    "Input validation and sanitization",
                    "XSS and injection attacks"
                ]
            },
            "complexity": {
                "description": "Code complexity and maintainability issues",
                "focus_areas": [
                    "Functions longer than 60 lines",
                    "Nesting depth greater than 3 levels",
                    "Code duplication and DRY violations",
                    "Testability concerns",
                    "Maintainability issues",
                    "Performance bottlenecks",
                    "Cognitive complexity",
                    "Separation of concerns"
                ]
            }
        }
        
        return [TextContent(
            type="text",
            text=json.dumps(agents_info, indent=2)
        )]
    
    else:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": f"Unknown tool: {name}",
                "available_tools": ["review_code_diff", "get_review_health", "list_available_agents"]
            }, indent=2)
        )]


@server.list_resources()
async def list_resources() -> List[Resource]:
    """List available MCP resources"""
    return [
        Resource(
            uri="ai-code-reviewer://rules/approval",
            name="Approval Rules",
            description="YAML-based approval rules configuration",
            mimeType="application/x-yaml"
        ),
        Resource(
            uri="ai-code-reviewer://prompts/system",
            name="System Prompts",
            description="System prompts for code review agents",
            mimeType="text/markdown"
        ),
        Resource(
            uri="ai-code-reviewer://prompts/style-guide",
            name="Style Guide",
            description="Code style guidelines and standards",
            mimeType="text/markdown"
        )
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    """Read MCP resources"""
    if uri == "ai-code-reviewer://rules/approval":
        try:
            with open("server/rules/approval_rules.yaml", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return "# No approval rules configured"
    
    elif uri == "ai-code-reviewer://prompts/system":
        try:
            with open("server/prompts/reviewer_system.md", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return "# No system prompts configured"
    
    elif uri == "ai-code-reviewer://prompts/style-guide":
        try:
            with open("server/prompts/style_guide.md", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return "# No style guide configured"
    
    else:
        raise ValueError(f"Unknown resource: {uri}")


async def main():
    """Main entry point for MCP server"""
    # Run the MCP server using stdio transport
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="ai-code-reviewer",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities=None
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
