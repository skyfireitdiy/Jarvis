"""版本管理器测试"""

from datetime import datetime, timedelta

import pytest

from jarvis.jarvis_api_version import (
    APIVersion,
    APIVersionManager,
    VersionDeprecatedError,
    VersionNotFoundError,
)
from jarvis.jarvis_api_version.version_manager import VersionStatus


class TestAPIVersion:
    """APIVersion测试"""

    def test_create_version(self) -> None:
        v = APIVersion(major=1, minor=2, patch=3)
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3
        assert str(v) == "1.2.3"

    def test_default_values(self) -> None:
        v = APIVersion(major=1, minor=0)
        assert v.patch == 0
        assert v.status == VersionStatus.ACTIVE

    def test_parse_version(self) -> None:
        v = APIVersion.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_parse_version_with_v_prefix(self) -> None:
        v = APIVersion.parse("v2.0.1")
        assert v.major == 2
        assert v.minor == 0
        assert v.patch == 1

    def test_parse_version_without_patch(self) -> None:
        v = APIVersion.parse("1.5")
        assert v.major == 1
        assert v.minor == 5
        assert v.patch == 0

    def test_parse_invalid_version(self) -> None:
        with pytest.raises(ValueError, match="Invalid version format"):
            APIVersion.parse("invalid")

    def test_version_comparison(self) -> None:
        v1 = APIVersion(1, 0, 0)
        v2 = APIVersion(1, 1, 0)
        v3 = APIVersion(2, 0, 0)

        assert v1 < v2
        assert v2 < v3
        assert v1 <= v2
        assert v2 >= v1
        assert v3 > v2

    def test_version_equality(self) -> None:
        v1 = APIVersion(1, 2, 3)
        v2 = APIVersion(1, 2, 3)
        v3 = APIVersion(1, 2, 4)

        assert v1 == v2
        assert v1 != v3

    def test_version_hash(self) -> None:
        v1 = APIVersion(1, 2, 3)
        v2 = APIVersion(1, 2, 3)
        assert hash(v1) == hash(v2)

    def test_is_compatible_with(self) -> None:
        v1 = APIVersion(1, 0, 0)
        v2 = APIVersion(1, 5, 0)
        v3 = APIVersion(2, 0, 0)

        assert v1.is_compatible_with(v2)
        assert not v1.is_compatible_with(v3)

    def test_status_checks(self) -> None:
        v = APIVersion(1, 0, 0)
        assert v.is_active()
        assert not v.is_deprecated()
        assert not v.is_retired()

        v.status = VersionStatus.DEPRECATED
        assert not v.is_active()
        assert v.is_deprecated()

        v.status = VersionStatus.RETIRED
        assert v.is_retired()


class TestAPIVersionManager:
    """APIVersionManager测试"""

    def test_register_api(self) -> None:
        manager = APIVersionManager()
        api = manager.register(
            name="test_api",
            version="1.0.0",
            handler=lambda: "v1",
            description="Test API v1",
        )
        assert api.name == "test_api"
        assert str(api.version) == "1.0.0"

    def test_register_multiple_versions(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")
        manager.register("api", "2.0.0", lambda: "v2")

        versions = manager.get_versions("api")
        assert len(versions) == 2

    def test_get_api(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")

        api = manager.get("api", "1.0.0")
        assert api.name == "api"

    def test_get_api_default_version(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")

        api = manager.get("api")
        assert str(api.version) == "1.0.0"

    def test_get_api_not_found(self) -> None:
        manager = APIVersionManager()
        with pytest.raises(VersionNotFoundError):
            manager.get("nonexistent")

    def test_get_version_not_found(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")

        with pytest.raises(VersionNotFoundError):
            manager.get("api", "2.0.0")

    def test_call_api(self) -> None:
        manager = APIVersionManager()
        manager.register("add", "1.0.0", lambda a, b: a + b)

        result = manager.call("add", "1.0.0", 1, 2)
        assert result == 3

    def test_call_api_with_kwargs(self) -> None:
        manager = APIVersionManager()
        manager.register("greet", "1.0.0", lambda greeting: f"Hello, {greeting}!")

        result = manager.call("greet", "1.0.0", greeting="World")
        assert result == "Hello, World!"

    def test_unregister_api(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")
        manager.unregister("api")

        with pytest.raises(VersionNotFoundError):
            manager.get("api")

    def test_unregister_version(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")
        manager.register("api", "2.0.0", lambda: "v2")
        manager.unregister("api", "1.0.0")

        versions = manager.get_versions("api")
        assert len(versions) == 1
        assert str(versions[0]) == "2.0.0"

    def test_unregister_not_found(self) -> None:
        manager = APIVersionManager()
        with pytest.raises(VersionNotFoundError):
            manager.unregister("nonexistent")

    def test_deprecate_api(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")
        manager.deprecate("api", "1.0.0")

        with pytest.raises(VersionDeprecatedError):
            manager.get("api", "1.0.0")

    def test_retire_api(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")
        manager.retire("api", "1.0.0")

        with pytest.raises(VersionNotFoundError, match="retired"):
            manager.get("api", "1.0.0")

    def test_get_active_versions(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")
        manager.register("api", "2.0.0", lambda: "v2")
        manager.deprecate("api", "1.0.0")

        active = manager.get_active_versions("api")
        assert len(active) == 1
        assert str(active[0]) == "2.0.0"

    def test_get_latest_version(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")
        manager.register("api", "2.0.0", lambda: "v2")

        latest = manager.get_latest_version("api")
        assert str(latest) == "2.0.0"

    def test_get_latest_version_empty(self) -> None:
        manager = APIVersionManager()
        assert manager.get_latest_version("nonexistent") is None

    def test_set_default_version(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")
        manager.register("api", "2.0.0", lambda: "v2")
        manager.set_default_version("api", "1.0.0")

        default = manager.get_default_version("api")
        assert str(default) == "1.0.0"

    def test_negotiate_version_exact(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")
        manager.register("api", "1.1.0", lambda: "v1.1")
        manager.register("api", "2.0.0", lambda: "v2")

        negotiated = manager.negotiate_version("api", "1.0.0")
        assert str(negotiated) == "1.0.0"

    def test_negotiate_version_compatible(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")
        manager.register("api", "1.5.0", lambda: "v1.5")
        manager.register("api", "2.0.0", lambda: "v2")

        negotiated = manager.negotiate_version("api", "1.2.0")
        assert str(negotiated) == "1.5.0"

    def test_negotiate_version_no_compatible(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "2.0.0", lambda: "v2")

        negotiated = manager.negotiate_version("api", "1.0.0")
        assert str(negotiated) == "2.0.0"

    def test_negotiate_version_none(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")
        manager.register("api", "2.0.0", lambda: "v2")

        negotiated = manager.negotiate_version("api")
        assert str(negotiated) == "2.0.0"

    def test_list_apis(self) -> None:
        manager = APIVersionManager()
        manager.register("api1", "1.0.0", lambda: "v1")
        manager.register("api2", "2.0.0", lambda: "v2")

        apis = manager.list_apis()
        assert "api1" in apis
        assert "api2" in apis

    def test_get_status(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1", description="Test")

        status = manager.get_status()
        assert status["total_apis"] == 1
        assert "api" in status["apis"]

    def test_register_with_tags(self) -> None:
        manager = APIVersionManager()
        api = manager.register("api", "1.0.0", lambda: "v1", tags=["public", "stable"])
        assert api.tags == ["public", "stable"]

    def test_deprecate_with_sunset(self) -> None:
        manager = APIVersionManager()
        manager.register("api", "1.0.0", lambda: "v1")
        sunset = datetime.now() + timedelta(days=30)
        manager.deprecate("api", "1.0.0", sunset_at=sunset)

        api = manager._apis["api"][APIVersion.parse("1.0.0")]
        assert api.version.sunset_at == sunset
