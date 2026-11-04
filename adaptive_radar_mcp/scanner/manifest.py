"""Secure workspace manifest scanner for dependencies with path traversal and injection guards."""

import re
from pathlib import Path

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


class ManifestScanner:
    """Safely extracts project dependencies without executing code or parsing untrusted freeform fields."""

    PACKAGE_NAME_REGEX = re.compile(r"^([a-zA-Z0-9_\-\.]+)(?:[>=<~!\^].*)?$")

    @classmethod
    def _validate_path_boundary(cls, target_path: Path, allowed_root: Path | None = None) -> Path:
        """Ensure the target path is strictly contained within the allowed root directory."""
        if allowed_root is None:
            allowed_root = Path.cwd().resolve()
        else:
            allowed_root = allowed_root.resolve()

        resolved_target = target_path.resolve()

        # Prevent directory traversal attacks (e.g., ../../etc/passwd)
        try:
            resolved_target.relative_to(allowed_root)
        except ValueError:
            raise PermissionError(
                f"Path Traversal Blocked: Target path '{resolved_target}' is outside allowed root '{allowed_root}'."
            )

        return resolved_target

    @classmethod
    def parse_requirements_txt(cls, file_path: Path) -> dict[str, str]:
        """Parse package names and version specifiers from requirements.txt."""
        dependencies: dict[str, str] = {}
        if not file_path.exists() or file_path.stat().st_size > 1024 * 1024:  # 1MB limit
            return dependencies

        for line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line_str = line.strip()
            # Ignore comments, options, and direct links
            if not line_str or line_str.startswith(("#", "-", "@", "git+")):
                continue

            # Strip inline comments
            line_str = line_str.split("#")[0].strip()
            match = re.match(r"^([a-zA-Z0-9_\-\.]+)(?:\s*([>=<~!\^]{1,2}\s*[0-9a-zA-Z\.\-]+))?", line_str)
            if match:
                pkg_name = match.group(1).lower().replace("_", "-")
                version_spec = match.group(2).replace(" ", "") if match.group(2) else "any"
                dependencies[pkg_name] = version_spec

        return dependencies

    @classmethod
    def parse_pyproject_toml(cls, file_path: Path) -> dict[str, str]:
        """Parse PEP 621 or Poetry dependencies strictly without reading metadata or scripts."""
        dependencies: dict[str, str] = {}
        if not file_path.exists() or file_path.stat().st_size > 1024 * 1024:
            return dependencies

        if tomllib is None:
            # Simple regex fallback if toml library is absent
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                match = re.match(r'^\s*["\']([a-zA-Z0-9_\-\.]+)(?:[>=<~!\^][^"\']*)?["\']', line)
                if match:
                    dependencies[match.group(1).lower().replace("_", "-")] = "declared"
            return dependencies

        try:
            data = tomllib.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
            # 1. PEP 621 dependencies: [project.dependencies]
            project_deps = data.get("project", {}).get("dependencies", [])
            if isinstance(project_deps, list):
                for dep in project_deps:
                    if isinstance(dep, str):
                        match = cls.PACKAGE_NAME_REGEX.match(dep.strip())
                        if match:
                            dependencies[match.group(1).lower().replace("_", "-")] = "declared"

            # 2. Poetry dependencies: [tool.poetry.dependencies]
            poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            if isinstance(poetry_deps, dict):
                for pkg, ver in poetry_deps.items():
                    if pkg.lower() != "python":
                        dependencies[pkg.lower().replace("_", "-")] = str(ver) if isinstance(ver, str) else "declared"
        except Exception:
            pass

        return dependencies

    @classmethod
    def parse_package_json(cls, file_path: Path) -> dict[str, str]:
        """Parse Node.js dependencies strictly ignoring scripts, description, and author."""
        import json
        dependencies: dict[str, str] = {}
        if not file_path.exists() or file_path.stat().st_size > 1024 * 1024:
            return dependencies

        try:
            data = json.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
            for section in ["dependencies", "devDependencies"]:
                deps = data.get(section, {})
                if isinstance(deps, dict):
                    for pkg, ver in deps.items():
                        if isinstance(pkg, str) and isinstance(ver, str):
                            dependencies[pkg.lower()] = ver
        except Exception:
            pass

        return dependencies

    @classmethod
    def scan_directory(cls, directory_path: str = ".", allowed_root: Path | None = None) -> dict[str, str]:
        """Scan a directory for known manifests and aggregate detected dependencies safely."""
        target_dir = cls._validate_path_boundary(Path(directory_path), allowed_root)
        if not target_dir.is_dir():
            raise NotADirectoryError(f"Target is not a directory: {target_dir}")

        detected: dict[str, str] = {}

        # 1. pyproject.toml
        pyproject_file = target_dir / "pyproject.toml"
        if pyproject_file.is_file():
            detected.update(cls.parse_pyproject_toml(pyproject_file))

        # 2. requirements.txt
        req_file = target_dir / "requirements.txt"
        if req_file.is_file():
            detected.update(cls.parse_requirements_txt(req_file))

        # 3. package.json
        package_json_file = target_dir / "package.json"
        if package_json_file.is_file():
            detected.update(cls.parse_package_json(package_json_file))

        return detected
