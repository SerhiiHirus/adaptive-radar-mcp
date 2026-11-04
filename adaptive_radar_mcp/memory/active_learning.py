"""Active learning module: Dynamically derives scoring weights and few-shot rules from user feedback."""

import re
from collections import Counter

from adaptive_radar_mcp.models import DecisionType, FeedbackRecord

FROZEN_STOPWORDS: set[str] = {
    "this", "that", "these", "those", "with", "without", "from", "into", "during",
    "including", "until", "against", "among", "throughout", "despite", "towards",
    "upon", "concerning", "about", "which", "there", "their", "where", "would",
    "could", "should", "shall", "might", "because", "while", "since", "before", "after", "above", "below", "between", "under", "again", "further",
    "then", "once", "here", "when", "why", "how", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "only", "own", "same", "than",
    "too", "very", "just", "also", "added", "fixed", "update", "updates", "changes",
    "release", "support", "supported", "version", "feature", "features", "need", "prefer"
}


class ActiveLearningEngine:
    """Derives dynamic weights and few-shot context from developer decisions."""

    @classmethod
    def _tokenize(cls, text: str) -> list[str]:
        """Extract clean words excluding stop-words and short tokens."""
        words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_\-]{3,}\b", text.lower())
        return [w for w in words if w not in FROZEN_STOPWORDS]

    @classmethod
    def analyze_feedback(cls, feedback_history: list[FeedbackRecord]) -> tuple[Counter, Counter]:
        """Count approved vs rejected patterns and tools."""
        accepted_keywords = Counter()
        rejected_keywords = Counter()

        for record in feedback_history:
            tokens = cls._tokenize(record.project_or_repo.replace("/", " ") + " " + record.reason)

            if record.decision == DecisionType.ACCEPTED:
                accepted_keywords.update(tokens)
            elif record.decision == DecisionType.REJECTED:
                rejected_keywords.update(tokens)

        return accepted_keywords, rejected_keywords

    @classmethod
    def calculate_preference_bias(
        cls, 
        tool_or_repo: str, 
        body_text: str, 
        feedback_history: list[FeedbackRecord]
    ) -> float:
        """Calculate score adjustment (+/-) based on past user feedback with strict word boundaries."""
        if not feedback_history:
            return 0.0

        accepted_counts, rejected_counts = cls.analyze_feedback(feedback_history)
        text_lower = f"{tool_or_repo} {body_text}".lower()

        bonus = 0.0
        penalty = 0.0

        for word, count in accepted_counts.items():
            pattern = r"\b" + re.escape(word) + r"\b"
            if re.search(pattern, text_lower):
                bonus += min(count * 0.5, 2.0)

        for word, count in rejected_counts.items():
            pattern = r"\b" + re.escape(word) + r"\b"
            if re.search(pattern, text_lower):
                penalty += min(count * 0.7, 3.0)

        return bonus - penalty

    @classmethod
    def build_few_shot_context(cls, feedback_history: list[FeedbackRecord], max_items: int = 5) -> str:
        """Build few-shot examples of past decisions to guide LLM/agent reasoning."""
        if not feedback_history:
            return "No previous feedback recorded yet. Base evaluation on standard architecture rules."

        lines = ["### Developer's Learned Decision History (Active Learning Few-Shot):"]
        for record in feedback_history[:max_items]:
            lines.append(
                f"- [{record.decision.value}] '{record.project_or_repo}': {record.reason}"
            )
        return "\n".join(lines)
