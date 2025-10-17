#!/usr/bin/env python3
"""
Startup script for the AI Code Reviewer MCP server.
This script can be used to run the MCP server directly.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the server directory to the Python path
server_dir = Path(__file__).parent / "server"
sys.path.insert(0, str(server_dir.parent))

from server.mcp_server import main

if __name__ == "__main__":
    print("Starting AI Code Reviewer MCP Server...")
    print("Make sure to set your environment variables:")
    print("- OPENAI_API_KEY or GROQ_API_KEY")
    print("- PROVIDER (openai or groq)")
    print("- Optional: DATABASE_BACKEND, CONVEX_URL, SUPABASE_URL, ELEVENLABS_API_KEY")
    print()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down MCP server...")
    except Exception as e:
        print(f"Error starting MCP server: {e}")
        sys.exit(1)
