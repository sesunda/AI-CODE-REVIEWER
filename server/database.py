"""
Database integration for AI Code Reviewer.
Supports Convex, Supabase, and a local file fallback ("none").
"""

import os
import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field, asdict

# Optional: Convex integration (JS-first; Python client may not exist in all envs)
try:
    from convex import ConvexClient
    CONVEX_AVAILABLE = True
except Exception:
    CONVEX_AVAILABLE = False

# Supabase integration
try:
    from supabase import create_client, Client  # type: ignore
    SUPABASE_AVAILABLE = True
except Exception:
    SUPABASE_AVAILABLE = False


# -----------------------------
# Datamodel
# -----------------------------
@dataclass
class ReviewRecord:
    """Review record for database storage."""
    id: Optional[str] = None
    diff: str = ""
    verdict: str = ""
    summary: str = ""
    findings: List[Dict[str, Any]] = field(default_factory=list)
    repo_meta: Dict[str, Any] = field(default_factory=dict)
    files_changed: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())
    provider: str = "unknown"


# -----------------------------
# File fallback store (JSONL)
# -----------------------------
class _FileStore:
    def __init__(self, path: str = "reviews_log.jsonl") -> None:
        self.path = os.getenv("REVIEWS_LOG_PATH", path)

    def _ensure_file(self) -> None:
        if not os.path.exists(self.path):
            with open(self.path, "w", encoding="utf-8"):
                pass

    async def store_review(self, review: ReviewRecord) -> str:
        self._ensure_file()
        row = asdict(review)
        if not row.get("id"):
            row["id"] = row["id"] or f"local_{int(datetime.utcnow().timestamp()*1000)}"
        # ISO timestamp for consistency
        ts = row.get("timestamp")
        if isinstance(ts, datetime):
            row["timestamp"] = ts.isoformat() + "Z"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row["id"]

    async def get_review(self, review_id: str) -> Optional[ReviewRecord]:
        if not os.path.exists(self.path):
            return None
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if obj.get("id") == review_id:
                        # parse timestamp back to datetime
                        ts = obj.get("timestamp")
                        if isinstance(ts, str):
                            try:
                                obj["timestamp"] = datetime.fromisoformat(ts.replace("Z", ""))
                            except Exception:
                                obj["timestamp"] = datetime.utcnow()
                        return ReviewRecord(**obj)
                except json.JSONDecodeError:
                    continue
        return None

    async def list_reviews(self, limit: int = 50, offset: int = 0, repo_filter: Optional[str] = None) -> List[ReviewRecord]:
        if not os.path.exists(self.path):
            return []
        rows: List[ReviewRecord] = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    # filter by repo if requested
                    if repo_filter and obj.get("repo_meta", {}).get("repo") != repo_filter:
                        continue
                    ts = obj.get("timestamp")
                    if isinstance(ts, str):
                        try:
                            obj["timestamp"] = datetime.fromisoformat(ts.replace("Z", ""))
                        except Exception:
                            obj["timestamp"] = datetime.utcnow()
                    rows.append(ReviewRecord(**obj))
                except json.JSONDecodeError:
                    continue
        # newest first
        rows.sort(key=lambda r: r.timestamp, reverse=True)
        return rows[offset : offset + max(1, min(limit, 100))]


# -----------------------------
# Convex store
# -----------------------------
class _ConvexStore:
    def __init__(self, url: str) -> None:
        self.client = ConvexClient(url)

    async def store_review(self, review: ReviewRecord) -> str:
        try:
            data = asdict(review)
            # serialize timestamp
            data["timestamp"] = review.timestamp.isoformat() + "Z"
            result = await asyncio.to_thread(self.client.mutation, "reviews:create", data)
            return result.get("_id", f"convex_{int(datetime.utcnow().timestamp()*1000)}")
        except Exception as e:
            print(f"[DB] Convex store error: {e}")
            return f"error_{int(datetime.utcnow().timestamp()*1000)}"

    async def get_review(self, review_id: str) -> Optional[ReviewRecord]:
        try:
            result = await asyncio.to_thread(self.client.query, "reviews:get", {"id": review_id})
            if not result:
                return None
            data = dict(result)
            try:
                data["timestamp"] = datetime.fromisoformat(str(data["timestamp"]).replace("Z", ""))
            except Exception:
                data["timestamp"] = datetime.utcnow()
            return ReviewRecord(**data)
        except Exception as e:
            print(f"[DB] Convex get error: {e}")
            return None

    async def list_reviews(self, limit: int, offset: int, repo_filter: Optional[str]) -> List[ReviewRecord]:
        try:
            filters = {"limit": limit, "offset": offset}
            if repo_filter:
                filters["repo"] = repo_filter
            results = await asyncio.to_thread(self.client.query, "reviews:list", filters)
            rows: List[ReviewRecord] = []
            for data in (results or []):
                try:
                    data["timestamp"] = datetime.fromisoformat(str(data["timestamp"]).replace("Z", ""))
                except Exception:
                    data["timestamp"] = datetime.utcnow()
                rows.append(ReviewRecord(**data))
            return rows
        except Exception as e:
            print(f"[DB] Convex list error: {e}")
            return []


# -----------------------------
# Supabase store
# -----------------------------
class _SupabaseStore:
    def __init__(self, url: str, key: str) -> None:
        self.client: Client = create_client(url, key)
        self.table = "reviews"

    async def store_review(self, review: ReviewRecord) -> str:
        data = asdict(review)
        # Let DB assign UUID if not provided
        data.pop("id", None)
        data["timestamp"] = review.timestamp.isoformat() + "Z"
        # NOTE: wrap the sync call in a thread with a lambda
        resp = await asyncio.to_thread(lambda: self.client.table(self.table).insert(data).execute())
        if not getattr(resp, "data", None):
            raise RuntimeError(f"Supabase insert failed: {resp}")
        row = resp.data[0]
        return row.get("id") or ""

    async def get_review(self, review_id: str) -> Optional[ReviewRecord]:
        resp = await asyncio.to_thread(lambda: self.client.table(self.table).select("*").eq("id", review_id).single().execute())
        row = getattr(resp, "data", None)
        if not row:
            return None
        # parse timestamp
        ts = row.get("timestamp")
        if isinstance(ts, str):
            try:
                row["timestamp"] = datetime.fromisoformat(ts.replace("Z", ""))
            except Exception:
                row["timestamp"] = datetime.utcnow()
        return ReviewRecord(**row)

    async def list_reviews(self, limit: int, offset: int, repo_filter: Optional[str]) -> List[ReviewRecord]:
        # Build query
        def run():
            q = self.client.table(self.table).select("*")
            if repo_filter:
                # Use filter for JSON expression
                q = q.filter("repo_meta->>repo", "eq", repo_filter)
            q = q.order("timestamp", desc=True).range(offset, offset + max(1, min(limit, 100)) - 1)
            return q.execute()

        resp = await asyncio.to_thread(run)
        data = getattr(resp, "data", []) or []
        rows: List[ReviewRecord] = []
        for row in data:
            ts = row.get("timestamp")
            if isinstance(ts, str):
                try:
                    row["timestamp"] = datetime.fromisoformat(ts.replace("Z", ""))
                except Exception:
                    row["timestamp"] = datetime.utcnow()
            rows.append(ReviewRecord(**row))
        return rows


# -----------------------------
# Facade / Manager
# -----------------------------
class DatabaseManager:
    """Database manager supporting Convex, Supabase, and local file fallback."""

    def __init__(self) -> None:
        self.backend = os.getenv("DATABASE_BACKEND", "none").lower()
        self.store: Any

        if self.backend == "convex" and CONVEX_AVAILABLE:
            url = os.getenv("CONVEX_URL")
            if url:
                try:
                    self.store = _ConvexStore(url)
                    return
                except Exception as e:
                    print(f"[DB] Convex init failed: {e}")

        if self.backend == "supabase" and SUPABASE_AVAILABLE:
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_ANON_KEY")
            if url and key:
                try:
                    self.store = _SupabaseStore(url, key)
                    return
                except Exception as e:
                    print(f"[DB] Supabase init failed: {e}")

        # Default: local file fallback
        self.backend = "none"
        self.store = _FileStore()

    async def store_review(self, review: ReviewRecord) -> Optional[str]:
        return await self.store.store_review(review)

    async def get_review(self, review_id: str) -> Optional[ReviewRecord]:
        return await self.store.get_review(review_id)

    async def list_reviews(self, limit: int = 50, offset: int = 0, repo_filter: Optional[str] = None) -> List[ReviewRecord]:
        return await self.store.list_reviews(limit, offset, repo_filter)


# Global instance
db_manager = DatabaseManager()
