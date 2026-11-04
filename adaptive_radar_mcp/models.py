"""Pydantic data models for adaptive-radar-mcp."""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class UpdateCategory(str, Enum):
    AGENTIC = "AGENTIC WORKFLOWS & FRAMEWORKS"
    LLMOPS = "LLMOps, INFRASTRUCTURE & COST"
    MCP_TOOLS = "TOOLS, PROTOCOLS & MCP"
    GENERAL = "GENERAL"


class ChangelogItem(BaseModel):
    """Single item parsed from a changelog draft."""
    raw_title: str
    tool_name: str
    version: Optional[str] = None
    category: UpdateCategory = UpdateCategory.GENERAL
    summary: str
    automation_insight: Optional[str] = None
    is_backlog_candidate: bool = False
    source_url: Optional[str] = None


class ChangelogDraft(BaseModel):
    """Complete changelog document."""
    date: str
    title: str
    items: List[ChangelogItem] = Field(default_factory=list)
    backlog_summary: Optional[str] = None


class RecommendationStatus(str, Enum):
    RECOMMENDED = "RECOMMENDED"
    MONITOR = "MONITOR"
    DISCARDED = "DISCARDED"


class RadarEvaluation(BaseModel):
    """Legacy evaluation model for changelog text items."""
    item: ChangelogItem
    status: RecommendationStatus
    target_project: Optional[str] = None
    token_impact: str
    architectural_fit: str
    context7_query: Optional[str] = None
    rationale: str


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
    version: Optional[str] = None
    title: str
    body: str
    url: str
    published_at: str
    content_hash: str


class EvaluationResult(BaseModel):
    """Evaluated release against current user profile and stack."""
    release_id: str
    project_or_repo: str
    version: Optional[str] = None
    title: str
    url: str
    score: float = Field(..., ge=0.0, le=10.0, description="Overall relevance score (0-10)")
    token_roi_summary: str
    safety_verdict: str                  # "SAFE", "WARNING", "UNSAFE"
    recommended_action: str             # "IMPLEMENT", "EXPLORE", "IGNORE"
    context7_query: Optional[str] = None
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
    keywords: List[str] = Field(default_factory=list)
    preferred_tools: List[str] = Field(default_factory=list)
    banned_patterns: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
