"""SQLite storage layer for adaptive-radar-mcp with WAL mode, indexes, and strict permissions."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Generator, List, Optional

from adaptive_radar_mcp.models import (
    DecisionType,
    FeedbackRecord,
    SourceType,
    TechRelease,
    UserStackProfile,
)

CURRENT_SCHEMA_VERSION = 1


class RadarDatabase:
    """Manages local SQLite database for releases and active learning feedback."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            storage_dir = os.environ.get("RADAR_STORAGE_DIR")
            if storage_dir:
                base_dir = Path(storage_dir)
            else:
                base_dir = Path.home() / ".adaptive-radar"
            base_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            db_path = base_dir / "radar.db"

        self.db_path = db_path
        self._init_db()
        self._enforce_file_permissions()

    def _enforce_file_permissions(self) -> None:
        """Enforce strict 0o600 permissions on database, WAL, and SHM files."""
        base_dir = self.db_path.parent
        for filename in [self.db_path.name, f"{self.db_path.name}-wal", f"{self.db_path.name}-shm"]:
            target = base_dir / filename
            if target.exists():
                try:
                    os.chmod(target, 0o600)
                except OSError:
                    pass

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager that configures per-connection PRAGMAs, commits on success, and closes."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        # Configure per-connection concurrency and resilience PRAGMAs
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
            self._enforce_file_permissions()

    def _init_db(self) -> None:
        """Create tables, indexes, and configure schema version."""
        with self._connection() as conn:
            # 1. Base tables
            conn.execute("""
                CREATE TABLE IF NOT EXISTS releases (
                    release_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    project_or_repo TEXT NOT NULL,
                    version TEXT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    url TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    release_id TEXT NOT NULL,
                    project_or_repo TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profile (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            # 2. Performance indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_releases_published ON releases(published_at DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_releases_repo ON releases(project_or_repo);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_release ON user_feedback(release_id);")

            # 3. Schema version
            version_row = conn.execute("PRAGMA user_version;").fetchone()
            if version_row and version_row[0] == 0:
                conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION};")

    def save_release(self, release: TechRelease) -> bool:
        """Insert or update a release. Updates title/body if content changed."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO releases 
                (release_id, source_type, project_or_repo, version, title, body, url, published_at, content_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(release_id) DO UPDATE SET
                    title = excluded.title,
                    body = excluded.body,
                    content_hash = excluded.content_hash
                WHERE releases.content_hash != excluded.content_hash
                """,
                (
                    release.release_id,
                    release.source_type.value,
                    release.project_or_repo,
                    release.version,
                    release.title,
                    release.body,
                    release.url,
                    release.published_at,
                    release.content_hash,
                    now,
                ),
            )
            return cursor.rowcount > 0

    def get_unreviewed_releases(self, limit: int = 20) -> List[TechRelease]:
        """Fetch releases that haven't received a final decision (ACCEPTED or REJECTED)."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT r.* FROM releases r
                LEFT JOIN user_feedback f ON r.release_id = f.release_id 
                    AND f.decision IN ('ACCEPTED', 'REJECTED')
                WHERE f.id IS NULL
                ORDER BY r.published_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            return [
                TechRelease(
                    release_id=row["release_id"],
                    source_type=SourceType(row["source_type"]),
                    project_or_repo=row["project_or_repo"],
                    version=row["version"],
                    title=row["title"],
                    body=row["body"],
                    url=row["url"],
                    published_at=row["published_at"],
                    content_hash=row["content_hash"],
                )
                for row in rows
            ]

    def record_feedback(self, feedback: FeedbackRecord) -> None:
        """Store user feedback decision to train active learning memory."""
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO user_feedback (release_id, project_or_repo, decision, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    feedback.release_id,
                    feedback.project_or_repo,
                    feedback.decision.value,
                    feedback.reason,
                    feedback.timestamp,
                ),
            )

    def get_recent_feedback(self, limit: int = 15) -> List[FeedbackRecord]:
        """Fetch recent user feedback for few-shot prompt formulation."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM user_feedback
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            return [
                FeedbackRecord(
                    release_id=row["release_id"],
                    project_or_repo=row["project_or_repo"],
                    decision=DecisionType(row["decision"]),
                    reason=row["reason"],
                    timestamp=row["created_at"],
                )
                for row in rows
            ]

    def set_user_profile(self, profile: UserStackProfile) -> None:
        """Update or set the current user stack profile."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO user_profile (key, value, updated_at)
                VALUES ('stack_profile', ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (profile.model_dump_json(), now),
            )

    def get_user_profile(self) -> UserStackProfile:
        """Get the current user stack profile, or default if not set."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT value FROM user_profile WHERE key = 'stack_profile'"
            ).fetchone()

            if row:
                return UserStackProfile.model_validate_json(row["value"])

            return UserStackProfile(
                keywords=["python", "fastapi", "pydantic", "asyncio", "llm-agents", "mcp"],
                preferred_tools=["pydantic", "fastapi", "httpx", "litellm", "pytest"],
                banned_patterns=["dynamic eval", "unbounded self-evolution", "heavy orchestration wrappers"],
                notes="Standard AI engineering stack focusing on structured outputs and cost optimization.",
            )

    def get_release_by_id(self, release_id: str) -> Optional[dict]:
        """Retrieve release dict by release_id."""
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM releases WHERE release_id = ?", (release_id,)).fetchone()
            if row:
                return dict(row)
            return None
