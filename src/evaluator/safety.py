"""Safety and security inspection for AI updates."""

import re
from typing import Tuple


class SafetyChecker:
    """Inspects releases for security risks, prompt injection attack vectors, or unsafe execution."""

    DANGEROUS_PATTERNS = [
        (r"\b(?:eval|exec)\s*\(\s*(?:code|user_input|payload|request|raw_string)\b", "Dynamic code execution on untrusted input"),
        (r"self-evolving\s+agent\s+(?:without|with\s+no)\s+sandbox", "Unconstrained self-evolving code execution"),
        (r"unconstrained\s+(?:bash|shell)\s+access", "Unconstrained shell access"),
        (r"arbitrary\s+remote\s+code\s+execution", "Arbitrary remote code execution risk"),
    ]

    WARNING_PATTERNS = [
        (r"breaking\s+change", "Contains breaking API changes"),
        (r"experimental\s+alpha", "Experimental/Unstable release"),
        (r"unpinned\s+telemetry", "Bundled analytics/telemetry"),
    ]

    @classmethod
    def inspect(cls, title: str, body: str) -> Tuple[str, str]:
        """Returns (verdict, reason). Verdict is one of SAFE, WARNING, UNSAFE."""
        combined = f"{title}\n{body}".lower()

        for pattern, reason in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, combined):
                return "UNSAFE", f"Security Alert: {reason}. Bypasses architectural boundaries."

        for pattern, reason in cls.WARNING_PATTERNS:
            if re.search(pattern, combined):
                return "WARNING", f"Caution: {reason}."

        return "SAFE", "No critical security flags detected."
