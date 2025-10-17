# AI Code Reviewer

A FastAPI-based MCP (Model Context Protocol) server that reviews code diffs using multiple AI agents (linter, security, complexity). Supports OpenAI, Groq, Convex/Supabase, and ElevenLabs integrations.

## Features

- **Multiple AI Agents**: Linter, Security, and Complexity analysis
- **MCP Compliance**: Full Model Context Protocol server implementation
- **Multiple LLM Providers**: OpenAI and Groq support
- **Database Integration**: Convex and Supabase support
- **Text-to-Speech**: ElevenLabs integration for audio summaries
- **YAML-based Rules**: Configurable approval and blocking rules
- **Async Execution**: Proper async/await patterns throughout
- **Mock Mode**: Testing without API keys

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `env.example` to `.env` and configure your API keys:

```bash
cp env.example .env
```

Edit `.env` with your API keys:
- `OPENAI_API_KEY` or `GROQ_API_KEY`
- Optional: `CONVEX_URL`, `SUPABASE_URL`, `ELEVENLABS_API_KEY`

### 3. Run the Server

#### FastAPI Server (HTTP API)
```bash
uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
```

#### MCP Server (Model Context Protocol)
```bash
python start_mcp_server.py
```

### 4. Test the Service

```bash
# Health check
curl http://localhost:8000/

# Review code
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{
    "diff": "def hello():\n    return \"world\"",
    "repo_meta": {"repo": "test"},
    "store_review": true
  }'
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PROVIDER` | LLM provider: "openai" or "groq" | "openai" |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `GROQ_API_KEY` | Groq API key | - |
| `MODEL` | OpenAI model name | "gpt-4o-mini" |
| `MOCK_MODE` | Use mock responses | "0" |
| `DATABASE_BACKEND` | Database: "convex", "supabase", or "none" | "none" |
| `CONVEX_URL` | Convex deployment URL | - |
| `SUPABASE_URL` | Supabase project URL | - |
| `SUPABASE_ANON_KEY` | Supabase anonymous key | - |
| `ELEVENLABS_API_KEY` | ElevenLabs API key | - |

### Approval Rules

Configure approval rules in `server/rules/approval_rules.yaml`:

```yaml
min_reviewers: 2
block_on:
  - security:high
warn_on:
  - style:low
auto_approve_if:
  - only_docs: true
```

## API Endpoints

### Core Endpoints

- `POST /review` - Review code diff
- `GET /reviews` - List recent reviews
- `GET /reviews/{id}` - Get specific review
- `GET /health` - Health check

### Status Endpoints

- `GET /` - Service information
- `GET /database/status` - Database connectivity
- `GET /tts/status` - TTS service status
- `GET /tts/voices` - Available TTS voices

## MCP Tools

The MCP server provides these tools:

- `review_code_diff` - Review code using all agents
- `get_review_health` - Check service health
- `list_available_agents` - List agent capabilities

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   FastAPI       │    │   MCP Server     │    │   Agents        │
│   HTTP API      │◄──►│   Protocol       │◄──►│   (Linter,       │
│                 │    │   Interface      │    │    Security,    │
└─────────────────┘    └──────────────────┘    │    Complexity)  │
         │                       │              └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Database      │    │   TTS Service    │    │   LLM Providers │
│   (Convex/      │    │   (ElevenLabs)   │    │   (OpenAI/      │
│    Supabase)    │    │                  │    │    Groq)        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Development

### Running Tests

```bash
pytest tests/
```

### Mock Mode

Set `MOCK_MODE=1` to test without API keys:

```bash
MOCK_MODE=1 python start_mcp_server.py
```

### Database Setup

#### Convex
1. Create a Convex project
2. Set up the `reviews` table schema
3. Configure `CONVEX_URL`

#### Supabase
1. Create a Supabase project
2. Create a `reviews` table
3. Configure `SUPABASE_URL` and `SUPABASE_ANON_KEY`

## License

MIT License - see LICENSE file for details.
