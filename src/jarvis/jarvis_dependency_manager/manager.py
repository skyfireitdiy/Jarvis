"""
Dependency Manager - Core Dependency Checking and Update Suggestion Logic

This module provides functionality to check dependency versions, query PyPI,
and generate update suggestions with compatibility analysis.
"""

import json
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from packaging.version import InvalidVersion, Version


@dataclass
class DependencyInfo:
    """Represents information about a dependency.

    Attributes:
        name: Name of the dependency package.
        current_version: Current installed version (from pyproject.toml or requirements.txt).
        latest_version: Latest version available on PyPI.
        installed: Whether the package is currently installed.
        specifiers: Version specifiers (e.g., ">=1.0.0,<2.0.0").
    """

    name: str
    current_version: str
    latest_version: Optional[str] = None
    installed: bool = False
    specifiers: str = ""


class UpdateType(Enum):
    """Type of update available."""

    MAJOR = "major"  # Breaking changes (e.g., 1.0.0 -> 2.0.0)
    MINOR = "minor"  # New features, backwards compatible (e.g., 1.0.0 -> 1.1.0)
    PATCH = "patch"  # Bug fixes (e.g., 1.0.0 -> 1.0.1)
    NONE = "none"  # No update available


@dataclass
class UpdateSuggestion:
    """Represents an update suggestion for a dependency.

    Attributes:
        dependency: Name of the dependency.
        current_version: Current version.
        latest_version: Latest version available.
        update_type: Type of update (major, minor, patch, none).
        compatible: Whether the update is compatible with current specifiers.
        risk_level: Risk level of the update (low, medium, high).
        reason: Explanation for the suggestion.
    """

    dependency: str
    current_version: str
    latest_version: str
    update_type: UpdateType
    compatible: bool
    risk_level: str
    reason: str


class DependencyManager:
    """Dependency manager for checking and suggesting updates.

    This class provides functionality to:
    - Parse dependency files (pyproject.toml, requirements.txt)
    - Query PyPI for latest versions
    - Compare versions and determine update types
    - Check version compatibility
    - Generate update suggestions

    Attributes:
        cache_dir: Directory for caching PyPI responses.

    Example:
        >>> manager = DependencyManager()
        >>> dependencies = manager.check_dependencies("/path/to/pyproject.toml")
        >>> suggestions = manager.get_update_suggestions(dependencies)
    """

    PYPI_API_URL = "https://pypi.org/pypi"
    REQUEST_TIMEOUT = 10  # seconds

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        """Initialize the DependencyManager.

        Args:
            cache_dir: Directory for caching PyPI responses. If None, uses temp dir.
        """
        if cache_dir is None:
            # Use secure temp directory from Python's tempfile module
            import tempfile as tf

            cache_dir = tf.gettempdir()

        self.cache_dir = Path(cache_dir) / "jarvis_dep_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def check_dependencies(
        self,
        project_root: Optional[str] = None,
    ) -> List[DependencyInfo]:
        """Check all dependencies in the project.

        Args:
            project_root: Root directory of the project. If None, uses current dir.

        Returns:
            List of dependency information.
        """
        if project_root is None:
            project_root = "."

        root_path = Path(project_root)
        dependencies: List[DependencyInfo] = []

        # Check pyproject.toml
        pyproject_path = root_path / "pyproject.toml"
        if pyproject_path.exists():
            pyproject_deps = self._parse_pyproject(pyproject_path)
            dependencies.extend(pyproject_deps)

        # Check requirements.txt
        requirements_path = root_path / "requirements.txt"
        if requirements_path.exists():
            requirements_deps = self._parse_requirements(requirements_path)
            dependencies.extend(requirements_deps)

        # Query PyPI for latest versions
        for dep in dependencies:
            latest = self._query_pypi_version(dep.name)
            if latest:
                dep.latest_version = latest

        return dependencies

    def _parse_pyproject(self, pyproject_path: Path) -> List[DependencyInfo]:
        """Parse dependencies from pyproject.toml.

        Args:
            pyproject_path: Path to pyproject.toml file.

        Returns:
            List of dependency information.
        """
        dependencies: List[DependencyInfo] = []

        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)

            # Get dependencies from [project.dependencies]
            deps_list = data.get("project", {}).get("dependencies", [])
            deps_list.extend(
                data.get("project", {}).get("optional-dependencies", {}).get("dev", [])
            )

            for dep_spec in deps_list:
                parsed = self._parse_dependency_spec(dep_spec)
                if parsed:
                    dependencies.append(parsed)
        except (FileNotFoundError, tomllib.TOMLDecodeError, KeyError):
            # Invalid or missing pyproject.toml
            pass

        return dependencies

    def _parse_requirements(self, requirements_path: Path) -> List[DependencyInfo]:
        """Parse dependencies from requirements.txt.

        Args:
            requirements_path: Path to requirements.txt file.

        Returns:
            List of dependency information.
        """
        dependencies: List[DependencyInfo] = []

        try:
            with open(requirements_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and empty lines
                    if not line or line.startswith("#"):
                        continue
                    # Skip -r, --find-links, etc.
                    if line.startswith("-"):
                        continue

                    parsed = self._parse_dependency_spec(line)
                    if parsed:
                        dependencies.append(parsed)
        except FileNotFoundError:
            # Missing requirements.txt
            pass

        return dependencies

    def _parse_dependency_spec(self, spec: str) -> Optional[DependencyInfo]:
        """Parse a dependency specification string.

        Args:
            spec: Dependency specification (e.g., "requests>=2.0.0", "numpy").

        Returns:
            DependencyInfo if parsing succeeded, None otherwise.
        """
        try:
            import re

            # Extract package name and version specifiers
            # Pattern: package_name[extras] (>=,<,>,==,~=,!=) version
            match = re.match(r"^([a-zA-Z0-9_\-\.\[\]]+)\s*(.*)", spec)
            if not match:
                return None

            name = match.group(1).split("[")[0]  # Remove extras
            specifiers = match.group(2).strip()

            # Extract current version from specifiers if pinned
            current_version = ""
            if "==" in specifiers:
                # Extract pinned version
                version_match = re.search(r"==([\d\.]+)", specifiers)
                if version_match:
                    current_version = version_match.group(1)
            elif ">=" in specifiers:
                version_match = re.search(r">=([\d\.]+)", specifiers)
                if version_match:
                    current_version = version_match.group(1)
            elif "~=" in specifiers:
                version_match = re.search(r"~=([\d\.]+)", specifiers)
                if version_match:
                    current_version = version_match.group(1)

            # If no version found, try to get installed version
            if not current_version:
                installed_version = self._get_installed_version(name)
                current_version = installed_version or ""

            return DependencyInfo(
                name=name,
                current_version=current_version or "unknown",
                specifiers=specifiers,
                installed=bool(current_version),
            )
        except Exception:
            return None

    def _get_installed_version(self, package_name: str) -> Optional[str]:
        """Get the installed version of a package.

        Args:
            package_name: Name of the package.

        Returns:
            Installed version string, or None if not installed.
        """
        try:
            import importlib.metadata

            return importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            return None

    def _query_pypi_version(self, package_name: str) -> Optional[str]:
        """Query PyPI for the latest version of a package.

        Args:
            package_name: Name of the package.

        Returns:
            Latest version string, or None if query failed.
        """
        # Check cache first
        cache_file = self.cache_dir / f"{package_name}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    cached_data = json.load(f)
                    # Cache valid for 1 hour
                    import time

                    if time.time() - cached_data.get("timestamp", 0) < 3600:
                        latest = cached_data.get("latest_version")
                        return latest if isinstance(latest, str) else None
            except (json.JSONDecodeError, KeyError):
                pass

        # Query PyPI API
        latest_version: Optional[str] = None
        try:
            # Validate URL to prevent SSRF attacks
            url = f"{self.PYPI_API_URL}/{package_name}/json"
            if not url.startswith(self.PYPI_API_URL):
                # URL validation failed - package_name might contain malicious input
                return None

            request = urllib.request.Request(url)

            # URL is validated and hardcoded to PyPI API (https://pypi.org/pypi) - safe
            with urllib.request.urlopen(
                request, timeout=self.REQUEST_TIMEOUT
            ) as response:  # nosec B310
                data = json.loads(response.read().decode("utf-8"))
                latest_version = data["info"]["version"]

                # Cache the result
                import time

                with open(cache_file, "w") as f:
                    json.dump(
                        {
                            "timestamp": time.time(),
                            "latest_version": latest_version,
                        },
                        f,
                    )

                return latest_version
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            json.JSONDecodeError,
            KeyError,
        ):
            return latest_version

    def get_update_suggestions(
        self, dependencies: List[DependencyInfo]
    ) -> List[UpdateSuggestion]:
        """Generate update suggestions for dependencies.

        Args:
            dependencies: List of dependency information.

        Returns:
            List of update suggestions.
        """
        suggestions: List[UpdateSuggestion] = []

        for dep in dependencies:
            if not dep.latest_version:
                continue

            try:
                current = (
                    Version(dep.current_version)
                    if dep.current_version != "unknown"
                    else None
                )
                latest = Version(dep.latest_version)

                if current is None:
                    # Unknown current version, suggest installing
                    suggestions.append(
                        UpdateSuggestion(
                            dependency=dep.name,
                            current_version=dep.current_version,
                            latest_version=dep.latest_version,
                            update_type=UpdateType.PATCH,
                            compatible=True,
                            risk_level="low",
                            reason="Package not installed, consider installing",
                        )
                    )
                    continue

                if latest > current:
                    update_type = self._determine_update_type(current, latest)
                    compatible = self._check_compatibility(dep, current, latest)
                    risk_level = self._assess_risk(update_type, compatible)
                    reason = self._generate_reason(
                        current, latest, update_type, compatible
                    )

                    suggestions.append(
                        UpdateSuggestion(
                            dependency=dep.name,
                            current_version=dep.current_version,
                            latest_version=dep.latest_version,
                            update_type=update_type,
                            compatible=compatible,
                            risk_level=risk_level,
                            reason=reason,
                        )
                    )
            except (InvalidVersion, ValueError):
                # Invalid version strings
                continue

        return suggestions

    def _determine_update_type(self, current: Version, latest: Version) -> UpdateType:
        """Determine the type of update needed.

        Args:
            current: Current version.
            latest: Latest version.

        Returns:
            UpdateType (major, minor, patch, or none).
        """
        if latest.major > current.major:
            return UpdateType.MAJOR
        elif latest.minor > current.minor:
            return UpdateType.MINOR
        elif latest.micro > current.micro:
            return UpdateType.PATCH
        else:
            return UpdateType.NONE

    def _check_compatibility(
        self, dep: DependencyInfo, current: Version, latest: Version
    ) -> bool:
        """Check if the update is compatible with version specifiers.

        Args:
            dep: Dependency information.
            current: Current version.
            latest: Latest version.

        Returns:
            True if compatible, False otherwise.
        """
        if not dep.specifiers:
            return True

        try:
            from packaging.specifiers import SpecifierSet

            spec_set = SpecifierSet(dep.specifiers)
            # Check if latest version satisfies specifiers
            return latest in spec_set
        except Exception:
            # If we can't parse specifiers, assume compatible
            return True

    def _assess_risk(self, update_type: UpdateType, compatible: bool) -> str:
        """Assess the risk level of an update.

        Args:
            update_type: Type of update.
            compatible: Whether the update is compatible.

        Returns:
            Risk level (low, medium, high).
        """
        if not compatible:
            return "high"

        if update_type == UpdateType.MAJOR:
            return "high"
        elif update_type == UpdateType.MINOR:
            return "medium"
        else:
            return "low"

    def _generate_reason(
        self,
        current: Version,
        latest: Version,
        update_type: UpdateType,
        compatible: bool,
    ) -> str:
        """Generate a reason for the update suggestion.

        Args:
            current: Current version.
            latest: Latest version.
            update_type: Type of update.
            compatible: Whether the update is compatible.

        Returns:
            Human-readable reason string.
        """
        if not compatible:
            return f"New version {latest} available but may break compatibility with current specifiers"

        if update_type == UpdateType.MAJOR:
            return f"Major update available ({current} -> {latest}), may contain breaking changes"
        elif update_type == UpdateType.MINOR:
            return (
                f"Minor update available ({current} -> {latest}), new features included"
            )
        elif update_type == UpdateType.PATCH:
            return f"Patch update available ({current} -> {latest}), bug fixes included"
        else:
            return "No update needed"
