"""Markdown and Obsidian exporter for AI Radar evaluations."""

from datetime import datetime, timezone
from pathlib import Path
from typing import List

from adaptive_radar_mcp.models import ChangelogDraft, RadarEvaluation, RecommendationStatus


class RadarExporter:
    """Formats radar evaluations into clean markdown reports."""

    @classmethod
    def format_markdown(cls, draft: ChangelogDraft, evaluations: List[RadarEvaluation]) -> str:
        """Format evaluations into a human-readable markdown report."""
        recommended = [e for e in evaluations if e.status == RecommendationStatus.RECOMMENDED]
        monitor = [e for e in evaluations if e.status == RecommendationStatus.MONITOR]
        discarded = [e for e in evaluations if e.status == RecommendationStatus.DISCARDED]

        utc_now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        lines = [
            f"# 🛰 AI Radar Report — {draft.date}",
            f"> Source: **{draft.title}** | Generated: `{utc_now}`",
            "",
            "## 🎯 Actionable Recommendations (Ready for Implementation)",
        ]

        if not recommended:
            lines.append("_No immediate high-ROI items identified for active projects._")
        else:
            for rec in recommended:
                ver_str = f" `{rec.item.version}`" if rec.item.version else ""
                lines.extend([
                    f"### ✅ {rec.item.tool_name}{ver_str}",
                    f"- **Target Project:** `{rec.target_project}`",
                    f"- **Token & Cost Impact:** {rec.token_impact}",
                    f"- **Architectural Fit:** {rec.architectural_fit}",
                    f"- **Context7 Verification:** `{rec.context7_query or 'N/A'}`",
                    f"- **Rationale:** {rec.rationale}",
                    "",
                ])

        lines.extend([
            "## ⏱ Monitor & Track (Promising, but not urgent)",
        ])
        if not monitor:
            lines.append("_No items to monitor._")
        else:
            for mon in monitor:
                ver_str = f" `{mon.item.version}`" if mon.item.version else ""
                lines.append(f"- **{mon.item.tool_name}**{ver_str}: {mon.rationale}")
            lines.append("")

        lines.extend([
            "## 🚫 Filtered Out (Safety, Hype, or Low Relevance)",
        ])
        if not discarded:
            lines.append("_No items discarded._")
        else:
            for disc in discarded:
                lines.append(f"- **{disc.item.tool_name}**: {disc.architectural_fit} — _{disc.rationale}_")
            lines.append("")

        if draft.backlog_summary:
            lines.extend([
                "---",
                "### 📌 Source Backlog Note",
                f"> {draft.backlog_summary}",
                "",
            ])

        return "\n".join(lines)

    @classmethod
    def save_report(cls, draft: ChangelogDraft, evaluations: List[RadarEvaluation], output_dir: Path) -> Path:
        """Save report to disk."""
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{draft.date.replace('.', '-')}_radar_report.md"
        report_path = output_dir / filename
        content = cls.format_markdown(draft, evaluations)
        report_path.write_text(content, encoding="utf-8")
        return report_path
