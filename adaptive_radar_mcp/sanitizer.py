"""Input sanitizer for untrusted external changelogs and release notes."""

import html
import re
from typing import List


class ContentSanitizer:
    """Sanitizes untrusted release text to mitigate prompt injection and context hijacking."""

    INJECTION_PATTERNS = [
        r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions",
        r"system\s+prompt\s*:",
        r"you\s+are\s+now\s+(?:an?\s+)?(?:unconstrained|different|new)\s+agent",
        r"disregard\s+(?:all\s+)?rules",
        r"exfiltrate\s+(?:data|credentials|tokens|keys)",
        r"<\s*script[^>]*>.*?<\s*/\s*script\s*>",
        r"javascript\s*:",
        r"data\s*:\s*text/html",
    ]

    @classmethod
    def sanitize_text(cls, raw_text: str, max_length: int = 600) -> str:
        """Sanitize raw markdown/text into safe, truncated text."""
        if not raw_text:
            return ""

        # 1. Unescape HTML entities, then strip raw HTML tags and comments
        cleaned = html.unescape(raw_text)
        cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)

        # 2. Neutralize known prompt injection directives
        for pattern in cls.INJECTION_PATTERNS:
            cleaned = re.sub(pattern, "[BLOCKED_INJECTION_ATTEMPT]", cleaned, flags=re.IGNORECASE)

        # 3. Strip non-printable and suspicious control characters
        cleaned = "".join(ch for ch in cleaned if ch.isprintable() or ch in ("\n", "\t", " "))

        # 4. Collapse whitespace
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

        # 5. Enforce strict length boundary to prevent context flooding
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length].rstrip() + "... [truncated for security]"

        return cleaned

    @classmethod
    def extract_safe_highlights(cls, body: str) -> List[str]:
        """Extract bullet points or key phrases safely without raw markup."""
        sanitized = cls.sanitize_text(body, max_length=1500)
        bullets = []
        for line in sanitized.splitlines():
            line_str = line.strip().lstrip("•-* \t")
            if 15 <= len(line_str) <= 180 and not line_str.startswith("[BLOCKED"):
                bullets.append(line_str)
            if len(bullets) >= 4:
                break
        return bullets
