"""SSRF and input validation defenses for dynamic radar sources."""

import ipaddress
import re
import socket
from urllib.parse import urlparse

GITHUB_REPO_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-]+$")


class SourceValidator:
    """Validates external sources to prevent SSRF and injection attacks."""

    @classmethod
    def validate_github_repo(cls, repo_identifier: str) -> str:
        """Ensure repo identifier matches strictly 'owner/repo' without URL schemes or traversal."""
        clean = repo_identifier.strip().lstrip("@")
        if not GITHUB_REPO_PATTERN.match(clean):
            raise ValueError(
                f"Invalid GitHub repository identifier '{repo_identifier}'. Expected format: 'owner/repo' (e.g. 'pydantic/pydantic-ai')."
            )
        return clean

    @classmethod
    def validate_rss_url(cls, url: str) -> str:
        """Validate RSS feed URL, enforcing HTTPS and blocking SSRF (loopback/private/cloud metadata)."""
        clean_url = url.strip()
        parsed = urlparse(clean_url)

        # 1. Enforce HTTPS only
        if parsed.scheme.lower() != "https":
            raise ValueError(f"SSRF Protection: Only HTTPS feeds are allowed (got: '{parsed.scheme}').")

        hostname = parsed.hostname
        if not hostname:
            raise ValueError("SSRF Protection: Missing or invalid hostname in URL.")

        # 2. Block direct localhost strings
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
            raise ValueError(f"SSRF Protection: Access to localhost or internal host '{hostname}' is blocked.")

        # 3. Resolve DNS and inspect target IP addresses
        try:
            addr_info = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
        except socket.gaierror as e:
            raise ValueError(f"DNS Resolution failed for '{hostname}': {e}")

        for _family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                # Strict RFC 1918 / Loopback / Link-Local / Carrier-Grade NAT blocking
                if (
                    ip_obj.is_loopback
                    or ip_obj.is_private
                    or ip_obj.is_link_local
                    or ip_obj.is_multicast
                    or ip_obj.is_reserved
                ):
                    raise ValueError(
                        f"SSRF Protection: Target '{hostname}' resolves to private or restricted IP ({ip_str}). Access denied."
                    )
            except ValueError as ip_err:
                if "SSRF Protection" in str(ip_err):
                    raise

        return clean_url
