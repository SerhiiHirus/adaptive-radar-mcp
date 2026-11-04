"""Pydantic data models for adaptive-radar-mcp."""

from enum import Enum

from pydantic import BaseModel, Field


class DecisionType(str, Enum):
    ACCEPTED = "ACCEPTED"    # User approved feature for backlog/implementation
    REJECTED = "REJECTED"    # User dismissed feature (out of scope, too complex, etc.)
    OBSERVED = "OBSERVED"    # Marked to keep tracking without action


class SourceType(str, Enum):
    GITHUB_RELEASE = "GITHUB_RELEASE"
    RSS_FEED = "RSS_FEED"
    MANUAL_INGEST = "MANUAL_INGEST"


class TechRelease(BaseModel):
    """Raw or structured release information."""
    release_id: str                      # Deterministic hash or repo/tag
    source_type: SourceType
    project_or_repo: str                # e.g. "pydantic/pydantic-ai"
    version: str | None = None
    title: str
    body: str
    url: str
    published_at: str
    content_hash: str


class EvaluationResult(BaseModel):
    """Evaluated release against current user profile and stack."""
    release_id: str
    project_or_repo: str
    version: str | None = None
    title: str
    url: str
    score: float = Field(..., ge=0.0, le=10.0, description="Overall relevance score (0-10)")
    token_roi_summary: str
    safety_verdict: str                  # "SAFE", "WARNING", "UNSAFE"
    recommended_action: str             # "IMPLEMENT", "EXPLORE", "IGNORE"
    context7_query: str | None = None
    rationale: str


class FeedbackRecord(BaseModel):
    """Feedback provided by user to train active learning memory."""
    release_id: str
    project_or_repo: str
    decision: DecisionType
    reason: str
    timestamp: str


class UserStackProfile(BaseModel):
    """Developer's preferences and active tech stack."""
    keywords: list[str] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    installed_packages: dict[str, str] = Field(default_factory=dict)
    banned_patterns: list[str] = Field(default_factory=list)
    notes: str | None = None
