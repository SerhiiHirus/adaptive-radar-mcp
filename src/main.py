"""CLI entry point for Adaptive Tech Radar."""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.evaluator.scoring import ReleaseEvaluator
from src.exporter import RadarExporter
from src.memory.db import RadarDatabase
from src.models import (
    ChangelogDraft,
    DecisionType,
    RadarEvaluation,
    RecommendationStatus,
    SourceType,
    TechRelease,
)
from src.parser import ChangelogParser


def main():
    parser = argparse.ArgumentParser(description="Adaptive Tech Radar & Decision Engine CLI")
    parser.add_argument("--file", type=str, help="Path to markdown changelog draft")
    parser.add_argument("--text", type=str, help="Raw text string of changelog")
    parser.add_argument("--output-dir", type=str, default="reports", help="Directory for output report")
    args = parser.parse_args()

    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: file not found: {file_path}", file=sys.stderr)
            sys.exit(1)
        draft = ChangelogParser.parse_file(file_path)
    elif args.text:
        draft = ChangelogParser.parse_text(args.text)
    else:
        # Check current directory for changelog drafts or ask for input
        local_drafts = Path("./drafts")
        if local_drafts.exists():
            changelogs = sorted(local_drafts.glob("*ai-automation*.md"), reverse=True)
            if changelogs:
                print(f"Reading latest changelog draft: {changelogs[0].name}")
                draft = ChangelogParser.parse_file(changelogs[0])
            else:
                print("No drafts found in ./drafts. Please specify --file or --text.", file=sys.stderr)
                sys.exit(1)
        else:
            print("Please provide --file <path> or --text '<content>'.", file=sys.stderr)
            sys.exit(1)

    db = RadarDatabase()
    profile = db.get_user_profile()
    feedback_history = db.get_recent_feedback(limit=20)

    # Evaluate each changelog item using ReleaseEvaluator
    evaluations = []
    for idx, item in enumerate(draft.items):
        release = TechRelease(
            release_id=f"draft:{draft.date}:{idx}:{item.tool_name}",
            source_type=SourceType.MANUAL_INGEST,
            project_or_repo=item.tool_name,
            version=item.version,
            title=f"{item.tool_name} {item.version or ''}: {item.raw_title}".strip(),
            body=f"{item.summary}\n{item.automation_insight or ''}".strip(),
            url=item.source_url or "changelog-draft",
            published_at=draft.date,
            content_hash=f"{draft.date}:{item.tool_name}:{idx}",
        )
        res = ReleaseEvaluator.evaluate(release, profile, feedback_history)
        
        status_map = {
            "IMPLEMENT": RecommendationStatus.RECOMMENDED,
            "EXPLORE": RecommendationStatus.MONITOR,
            "IGNORE": RecommendationStatus.DISCARDED,
        }
        evaluations.append(
            RadarEvaluation(
                item=item,
                status=status_map.get(res.recommended_action, RecommendationStatus.MONITOR),
                target_project=", ".join(profile.preferred_tools) if res.recommended_action == "IMPLEMENT" else None,
                token_impact=res.token_roi_summary,
                architectural_fit=res.safety_verdict,
                context7_query=res.context7_query,
                rationale=res.rationale,
            )
        )

    out_dir = Path(args.output_dir)
    report_file = RadarExporter.save_report(draft, evaluations, out_dir)
    print(f"✅ Report successfully generated at: {report_file}\n")
    print(RadarExporter.format_markdown(draft, evaluations))


if __name__ == "__main__":
    main()
