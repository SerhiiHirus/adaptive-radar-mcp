"""Input sanitizer for untrusted external changelogs and release notes."""

import html
import re
import unicodedata
from urllib.parse import urlparse


class ContentSanitizer:
    """Sanitizes untrusted release text to mitigate prompt injection and context hijacking."""

    INJECTION_PATTERNS = [
        r"ignore\s+(?:all\s+|the\s+)?(?:previous|prior|above|existing)\s+instructions",
        r"disregard\s+(?:all\s+|the\s+)?(?:instructions|rules|context)",
        r"system\s+prompt\s*:",
        r"you\s+are\s+now\s+(?:an?\s+)?(?:unconstrained|different|new)\s+agent",
        r"bypass\s+(?:all\s+)?(?:security|safety|restrictions)",
        r"exfiltrate\s+(?:data|credentials|tokens|keys|files)",
        r"<\s*script[^>]*>.*?<\s*/\s*script\s*>",
        r"javascript\s*:",
        r"data\s*:\s*text/html",
    ]

    @classmethod
    def _normalize_unicode(cls, text: str) -> str:
        """Normalize Unicode characters (NFKC) and strip zero-width/formatting characters."""
        if not text:
            return ""
        # Convert fullwidth characters (e.g. 'ｉｇｎｏｒｅ' -> 'ignore')
        normalized = unicodedata.normalize("NFKC", text)
        # Remove invisible/zero-width formatting characters (Category 'Cf')
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Cf")

    @classmethod
    def sanitize_title(cls, raw_title: str, max_length: int = 150) -> str:
        """Sanitize titles by removing newlines and markdown headers to prevent report spoofing."""
        if not raw_title:
            return "Untitled Release"

        # 1. Unicode NFKC normalization and zero-width stripping
        title = cls._normalize_unicode(raw_title)

        # 2. Strip newlines, tabs, and markdown heading markers
        title = re.sub(r"[\r\n\t]+", " ", title)
        title = title.replace("#", "").strip()

        # 3. Clean tags and inject protection
        title = cls.sanitize_text(title, max_length=max_length)
        return title.strip() or "Untitled Release"

    @classmethod
    def sanitize_url(cls, raw_url: str) -> str:
        """Validate and allow only safe http/https URLs without whitespace or CRLF."""
        if not raw_url:
            return ""

        url = cls._normalize_unicode(raw_url).strip()
        # Block CRLF or embedded whitespace in URL to prevent HTTP splitting or spoofing
        if any(c in url for c in ("\r", "\n", "\t", " ")):
            return ""

        try:
            parsed = urlparse(url)
            if parsed.scheme.lower() in ("https", "http") and parsed.netloc:
                return url
        except Exception:
            pass

        return ""

    @classmethod
    def sanitize_text(cls, raw_text: str, max_length: int = 600) -> str:
        """Sanitize raw markdown/text into safe, truncated text."""
        if not raw_text:
            return ""

        # 1. Unicode NFKC normalization and zero-width stripping
        cleaned = cls._normalize_unicode(raw_text)

        # 2. Unescape HTML entities, then strip raw HTML tags and comments
        cleaned = html.unescape(cleaned)
        cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)

        # 3. Neutralize prompt injection directives
        for pattern in cls.INJECTION_PATTERNS:
            cleaned = re.sub(pattern, "[BLOCKED_INJECTION_ATTEMPT]", cleaned, flags=re.IGNORECASE)

        # 4. Strip non-printable and suspicious control characters
        cleaned = "".join(ch for ch in cleaned if ch.isprintable() or ch in ("\n", "\t", " "))

        # 5. Collapse excessive whitespace
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

        # 6. Enforce strict length boundary to prevent context exhaustion
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length].rstrip() + "... [truncated for security]"

        return cleaned
