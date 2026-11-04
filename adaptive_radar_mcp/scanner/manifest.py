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

    SAFE_PACKAGE_REGEX = re.compile(r"^(?:@[a-zA-Z0-9_\-\.]+\/)?[a-zA-Z0-9][a-zA-Z0-9_\-\.]+$")
    PACKAGE_SPEC_REGEX = re.compile(r"^([a-zA-Z0-9_\-\.]+)(?:[>=<~!\^].*)?$")

    @classmethod
    def _is_safe_package_name(cls, name: str) -> bool:
        """Validate package name against PEP 508 / npm format, strictly preventing CRLF and markdown."""
        if not name or len(name) > 100:
            return False
        if any(c in name for c in ("\r", "\n", "\t", "#", " ", "..", "\\", "<", ">", '"', "'")):
            return False
        return bool(cls.SAFE_PACKAGE_REGEX.match(name))

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
                raw_name = match.group(1)
                if cls._is_safe_package_name(raw_name):
                    pkg_name = raw_name.lower().replace("_", "-")
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
                    raw_name = match.group(1)
                    if cls._is_safe_package_name(raw_name):
                        dependencies[raw_name.lower().replace("_", "-")] = "declared"
            return dependencies

        try:
            data = tomllib.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
            # 1. PEP 621 dependencies: [project.dependencies]
            project_deps = data.get("project", {}).get("dependencies", [])
            if isinstance(project_deps, list):
                for dep in project_deps:
                    if isinstance(dep, str):
                        match = cls.PACKAGE_SPEC_REGEX.match(dep.strip())
                        if match:
                            raw_name = match.group(1)
                            if cls._is_safe_package_name(raw_name):
                                dependencies[raw_name.lower().replace("_", "-")] = "declared"

            # 2. Poetry dependencies: [tool.poetry.dependencies]
            poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            if isinstance(poetry_deps, dict):
                for pkg, ver in poetry_deps.items():
                    if pkg.lower() != "python" and cls._is_safe_package_name(pkg):
                        dependencies[pkg.lower().replace("_", "-")] = str(ver) if isinstance(ver, str) else "declared"
        except Exception:
            pass

        return dependencies

    @classmethod
    def parse_uv_lock(cls, file_path: Path) -> dict[str, str]:
        """Parse exact pinned versions from uv.lock."""
        dependencies: dict[str, str] = {}
        if not file_path.exists() or file_path.stat().st_size > 2 * 1024 * 1024:
            return dependencies

        if tomllib is None:
            return dependencies

        try:
            data = tomllib.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
            packages = data.get("package", [])
            if isinstance(packages, list):
                for pkg in packages:
                    if isinstance(pkg, dict):
                        name = pkg.get("name")
                        ver = pkg.get("version")
                        if isinstance(name, str) and isinstance(ver, str) and cls._is_safe_package_name(name):
                            dependencies[name.lower().replace("_", "-")] = ver.strip()
        except Exception:
            pass

        return dependencies

    @classmethod
    def parse_poetry_lock(cls, file_path: Path) -> dict[str, str]:
        """Parse exact pinned versions from poetry.lock."""
        dependencies: dict[str, str] = {}
        if not file_path.exists() or file_path.stat().st_size > 2 * 1024 * 1024:
            return dependencies

        if tomllib is None:
            return dependencies

        try:
            data = tomllib.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
            packages = data.get("package", [])
            if isinstance(packages, list):
                for pkg in packages:
                    if isinstance(pkg, dict):
                        name = pkg.get("name")
                        ver = pkg.get("version")
                        if isinstance(name, str) and isinstance(ver, str) and cls._is_safe_package_name(name):
                            dependencies[name.lower().replace("_", "-")] = ver.strip()
        except Exception:
            pass

        return dependencies

    @classmethod
    def parse_package_lock_json(cls, file_path: Path) -> dict[str, str]:
        """Parse exact pinned versions from package-lock.json."""
        import json
        dependencies: dict[str, str] = {}
        if not file_path.exists() or file_path.stat().st_size > 2 * 1024 * 1024:
            return dependencies

        try:
            data = json.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
            packages = data.get("packages", {})
            if isinstance(packages, dict):
                for path, info in packages.items():
                    if isinstance(info, dict) and "version" in info:
                        if path.startswith("node_modules/"):
                            pkg_name = path[len("node_modules/"):]
                            if cls._is_safe_package_name(pkg_name):
                                dependencies[pkg_name.lower()] = str(info["version"]).strip()

            if not dependencies:
                deps = data.get("dependencies", {})
                if isinstance(deps, dict):
                    for pkg_name, info in deps.items():
                        if isinstance(info, dict) and "version" in info:
                            if cls._is_safe_package_name(pkg_name):
                                dependencies[pkg_name.lower()] = str(info["version"]).strip()
        except Exception:
            pass

        return dependencies

    @classmethod
    def parse_package_json(cls, file_path: Path) -> dict[str, str]:
        """Parse Node.js dependencies strictly with PEP 508 / npm name validation."""
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
                            clean_pkg = pkg.strip()
                            if cls._is_safe_package_name(clean_pkg):
                                dependencies[clean_pkg.lower()] = ver.strip()[:50]
        except Exception:
            pass

        return dependencies

    @classmethod
    def scan_directory(cls, directory_path: str = ".", allowed_root: Path | None = None) -> dict[str, str]:
        """Scan a directory for manifests and lockfiles, prioritizing exact pinned versions."""
        target_dir = cls._validate_path_boundary(Path(directory_path), allowed_root)
        if not target_dir.is_dir():
            raise NotADirectoryError(f"Target is not a directory: {target_dir}")

        detected: dict[str, str] = {}

        # 1. Exact lockfiles first
        uv_lock = target_dir / "uv.lock"
        if uv_lock.is_file():
            detected.update(cls.parse_uv_lock(uv_lock))

        poetry_lock = target_dir / "poetry.lock"
        if poetry_lock.is_file():
            for k, v in cls.parse_poetry_lock(poetry_lock).items():
                detected.setdefault(k, v)

        pkg_lock = target_dir / "package-lock.json"
        if pkg_lock.is_file():
            for k, v in cls.parse_package_lock_json(pkg_lock).items():
                detected.setdefault(k, v)

        # 2. Manifest declarations (fallback / complement)
        pyproject_file = target_dir / "pyproject.toml"
        if pyproject_file.is_file():
            for k, v in cls.parse_pyproject_toml(pyproject_file).items():
                detected.setdefault(k, v)

        req_file = target_dir / "requirements.txt"
        if req_file.is_file():
            for k, v in cls.parse_requirements_txt(req_file).items():
                detected.setdefault(k, v)

        package_json_file = target_dir / "package.json"
        if package_json_file.is_file():
            for k, v in cls.parse_package_json(package_json_file).items():
                detected.setdefault(k, v)

        return detected
