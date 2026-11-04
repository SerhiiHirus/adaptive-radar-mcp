"""Release evaluator: Computes Token ROI, Stack Match, Safety, and Context7 suggestions."""

import re
from typing import List, Optional

from adaptive_radar_mcp.evaluator.safety import SafetyChecker
from adaptive_radar_mcp.memory.active_learning import ActiveLearningEngine
from adaptive_radar_mcp.models import EvaluationResult, FeedbackRecord, TechRelease, UserStackProfile


class ReleaseEvaluator:
    """Evaluates tech releases against developer profile, safety policies, and token economics."""

    TOKEN_SAVING_SIGNALS = [
        ("prompt caching", 2.5, "Enables prompt caching (cuts input tokens by up to 50-80%)"),
        ("cache_control", 2.0, "API-level cache control for repeated system prompts"),
        ("structured output", 2.0, "Native structured outputs (eliminates retry token overhead)"),
        ("thinking effort", 1.5, "Dynamic thinking effort dials down reasoning tokens on simple steps"),
        ("distillation", 1.0, "Model distillation/quantization decreases per-call cost"),
        ("embedding 2", 1.0, "Higher embedding density reduces vector dimension storage & retrieval"),
        ("mcp", 1.5, "Model Context Protocol eliminates bloated DDL and schema prompt dumps"),
    ]

    @classmethod
    def evaluate(
        cls, 
        release: TechRelease, 
        profile: UserStackProfile, 
        feedback_history: Optional[List[FeedbackRecord]] = None
    ) -> EvaluationResult:
        """Score a release from 0.0 to 10.0."""
        text_full = f"{release.title}\n{release.body}".lower()
        token_notes = []

        # 1. Safety verification
        safety_verdict, safety_reason = SafetyChecker.inspect(release.title, release.body)
        if safety_verdict == "UNSAFE":
            return EvaluationResult(
                release_id=release.release_id,
                project_or_repo=release.project_or_repo,
                version=release.version,
                title=release.title,
                url=release.url,
                score=0.0,
                token_roi_summary="Zero / High Risk",
                safety_verdict=safety_verdict,
                recommended_action="IGNORE",
                context7_query=None,
                rationale=safety_reason,
            )

        # 2. Check user's banned patterns
        for banned in profile.banned_patterns:
            pattern = r"\b" + re.escape(banned.lower()) + r"\b"
            if re.search(pattern, text_full):
                return EvaluationResult(
                    release_id=release.release_id,
                    project_or_repo=release.project_or_repo,
                    version=release.version,
                    title=release.title,
                    url=release.url,
                    score=1.0,
                    token_roi_summary="Banned by architectural policy",
                    safety_verdict=safety_verdict,
                    recommended_action="IGNORE",
                    context7_query=None,
                    rationale=f"Dismissed: Matches banned pattern '{banned}' configured in user profile.",
                )

        # 3. Base score starts conservative (2.5)
        current_score = 2.5

        # 4. Token ROI calculation
        token_bonus = 0.0
        for signal, weight, note in cls.TOKEN_SAVING_SIGNALS:
            pattern = r"\b" + re.escape(signal) + r"\b"
            if re.search(pattern, text_full):
                token_bonus += weight
                token_notes.append(note)

        current_score += min(token_bonus, 3.5)
        token_roi_summary = "; ".join(token_notes) if token_notes else "Neutral token impact"

        # 5. Stack match calculation (Strict word boundary matching)
        stack_match_bonus = 0.0
        for keyword in profile.keywords:
            pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
            if re.search(pattern, text_full):
                stack_match_bonus += 0.8

        for tool in profile.preferred_tools:
            pattern = r"\b" + re.escape(tool.lower()) + r"\b"
            if re.search(pattern, release.project_or_repo.lower()):
                stack_match_bonus += 2.0

        current_score += min(stack_match_bonus, 3.0)

        # 6. Active Learning bias from developer's past decisions
        if feedback_history:
            bias = ActiveLearningEngine.calculate_preference_bias(
                release.project_or_repo, release.body, feedback_history
            )
            current_score += bias

        # Clamp score between 0.0 and 10.0
        final_score = round(max(0.0, min(10.0, current_score)), 1)

        # Determine recommended action
        if final_score >= 7.0:
            action = "IMPLEMENT"
        elif final_score >= 4.5:
            action = "EXPLORE"
        else:
            action = "IGNORE"

        # Formulate Context7 query
        context7_query = None
        repo_simple = release.project_or_repo.split("/")[-1]
        if final_score >= 5.5:
            context7_query = f"{repo_simple} {release.version or ''}".strip()

        rationale = f"Evaluated against profile ({len(profile.keywords)} keywords). "
        if token_notes:
            rationale += "Identified cost-saving mechanisms. "
        if feedback_history:
            rationale += "Active learning weights applied. "

        return EvaluationResult(
            release_id=release.release_id,
            project_or_repo=release.project_or_repo,
            version=release.version,
            title=release.title,
            url=release.url,
            score=final_score,
            token_roi_summary=token_roi_summary,
            safety_verdict=safety_verdict,
            recommended_action=action,
            context7_query=context7_query,
            rationale=rationale.strip(),
        )
