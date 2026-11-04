"""Changelog parser for AI Radar."""

import re
from pathlib import Path
from typing import List, Optional

from src.models import ChangelogDraft, ChangelogItem, UpdateCategory


class ChangelogParser:
    """Parses markdown changelog drafts into structured Pydantic models."""

    CATEGORY_PATTERNS = {
        UpdateCategory.AGENTIC: r"\[AGENTIC WORKFLOWS & FRAMEWORKS\]",
        UpdateCategory.LLMOPS: r"\[LLMOps, INFRASTRUCTURE & COST\]",
        UpdateCategory.MCP_TOOLS: r"\[TOOLS, PROTOCOLS & MCP\]",
    }

    @classmethod
    def parse_text(cls, text: str, date: str = "") -> ChangelogDraft:
        """Parse raw changelog text into a ChangelogDraft."""
        lines = text.splitlines()
        
        # Extract date from header if not provided
        if not date:
            date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
            date = date_match.group(1) if date_match else "unknown"

        title_match = re.search(r"(?:#\s*.*|🛠\s*AI Automation Daily Changelog[^\n]*)", text)
        title = title_match.group(0).strip("# ").strip() if title_match else f"AI Changelog {date}"

        # Extract backlog section if present
        backlog_summary = None
        backlog_match = re.search(r"📌\s*(?:Що взяти в беклог|Беклог)[:\s]*(.*?)(?:\n\n|\Z)", text, re.DOTALL)
        if backlog_match:
            backlog_summary = backlog_match.group(1).strip()

        # Split content into categories
        items: List[ChangelogItem] = []
        current_category = UpdateCategory.GENERAL

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Check category headers
            for cat, pattern in cls.CATEGORY_PATTERNS.items():
                if re.search(pattern, line_str, re.IGNORECASE):
                    current_category = cat
                    break

            # Parse item bullet
            if line_str.startswith("•") or line_str.startswith("-"):
                item_text = line_str.lstrip("•- ").strip()
                item = cls._parse_item(item_text, current_category, backlog_summary)
                items.append(item)
            elif items and line_str.startswith("💡"):
                # Append automation insight to the preceding item
                insight = line_str.replace("💡 Для автоматизації:", "").replace("💡", "").strip()
                items[-1].automation_insight = insight

        return ChangelogDraft(
            date=date,
            title=title,
            items=items,
            backlog_summary=backlog_summary
        )

    @classmethod
    def parse_file(cls, file_path: Path) -> ChangelogDraft:
        """Read and parse a changelog markdown file."""
        content = file_path.read_text(encoding="utf-8")
        return cls.parse_text(content)

    @classmethod
    def _parse_item(
        cls, 
        text: str, 
        category: UpdateCategory, 
        backlog_text: Optional[str] = None
    ) -> ChangelogItem:
        """Extract tool name, version, and details from an item line."""
        # Clean source markers like (Джерело) or [Source]
        cleaned_text = re.sub(r"\(Джерело\)|\(Source\)|\(link\)", "", text).strip()

        # Detect tool name & version, e.g. "PydanticAI v2.65.0: description"
        match = re.match(r"^([^:]+?)(?:\s+(v\d+[\w\.\-]+))?:\s*(.*)$", cleaned_text)
        if match:
            tool_part = match.group(1).strip()
            version_part = match.group(2)
            summary = match.group(3).strip()
            
            # Additional check if version is inside tool_part
            version_in_tool = re.search(r"(v\d+[\w\.\-]+)", tool_part)
            if version_in_tool and not version_part:
                version_part = version_in_tool.group(1)
                tool_part = re.sub(r"\s*v\d+[\w\.\-]+", "", tool_part).strip()

            tool_name = tool_part
            version = version_part
        else:
            tool_name = cleaned_text.split()[0] if cleaned_text else "Unknown"
            version = None
            summary = cleaned_text

        is_backlog = False
        if backlog_text and tool_name.lower() in backlog_text.lower():
            is_backlog = True

        return ChangelogItem(
            raw_title=cleaned_text,
            tool_name=tool_name,
            version=version,
            category=category,
            summary=summary,
            is_backlog_candidate=is_backlog
        )
