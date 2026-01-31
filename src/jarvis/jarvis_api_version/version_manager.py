"""API版本管理器

提供API版本注册、路由和兼容性检查功能。
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class VersionStatus(Enum):
    """版本状态"""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class VersionError(Exception):
    """版本错误基类"""

    pass


class VersionNotFoundError(VersionError):
    """版本未找到错误"""

    pass


class VersionDeprecatedError(VersionError):
    """版本已弃用错误"""

    pass


@dataclass
class APIVersion:
    """API版本信息"""

    major: int
    minor: int
    patch: int = 0
    status: VersionStatus = VersionStatus.ACTIVE
    deprecated_at: datetime | None = None
    sunset_at: datetime | None = None
    description: str = ""

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, APIVersion):
            return False
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
        )

    def __lt__(self, other: "APIVersion") -> bool:
        return (self.major, self.minor, self.patch) < (
            other.major,
            other.minor,
            other.patch,
        )

    def __le__(self, other: "APIVersion") -> bool:
        return self == other or self < other

    def __gt__(self, other: "APIVersion") -> bool:
        return not self <= other

    def __ge__(self, other: "APIVersion") -> bool:
        return not self < other

    @classmethod
    def parse(cls, version_str: str) -> "APIVersion":
        """解析版本字符串"""
        match = re.match(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$", version_str)
        if not match:
            raise ValueError(f"Invalid version format: {version_str}")
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3)) if match.group(3) else 0
        return cls(major=major, minor=minor, patch=patch)

    def is_compatible_with(self, other: "APIVersion") -> bool:
        """检查是否与另一个版本兼容（主版本号相同）"""
        return self.major == other.major

    def is_active(self) -> bool:
        """检查版本是否活跃"""
        return self.status == VersionStatus.ACTIVE

    def is_deprecated(self) -> bool:
        """检查版本是否已弃用"""
        return self.status == VersionStatus.DEPRECATED

    def is_retired(self) -> bool:
        """检查版本是否已退役"""
        return self.status == VersionStatus.RETIRED


@dataclass
class VersionedAPI:
    """版本化API定义"""

    name: str
    version: APIVersion
    handler: Callable[..., Any]
    description: str = ""
    tags: list[str] = field(default_factory=list)


class APIVersionManager:
    """API版本管理器"""

    def __init__(self) -> None:
        self._apis: dict[str, dict[APIVersion, VersionedAPI]] = {}
        self._default_versions: dict[str, APIVersion] = {}

    def register(
        self,
        name: str,
        version: APIVersion | str,
        handler: Callable[..., Any],
        description: str = "",
        tags: list[str] | None = None,
        set_default: bool = False,
    ) -> VersionedAPI:
        """注册API版本"""
        if isinstance(version, str):
            version = APIVersion.parse(version)

        if name not in self._apis:
            self._apis[name] = {}

        api = VersionedAPI(
            name=name,
            version=version,
            handler=handler,
            description=description,
            tags=tags or [],
        )
        self._apis[name][version] = api

        if set_default or name not in self._default_versions:
            self._default_versions[name] = version

        return api

    def unregister(self, name: str, version: APIVersion | str | None = None) -> None:
        """注销API版本"""
        if name not in self._apis:
            raise VersionNotFoundError(f"API '{name}' not found")

        if version is None:
            del self._apis[name]
            if name in self._default_versions:
                del self._default_versions[name]
        else:
            if isinstance(version, str):
                version = APIVersion.parse(version)
            if version not in self._apis[name]:
                raise VersionNotFoundError(
                    f"Version {version} of API '{name}' not found"
                )
            del self._apis[name][version]
            if self._default_versions.get(name) == version:
                if self._apis[name]:
                    self._default_versions[name] = max(self._apis[name].keys())
                else:
                    del self._default_versions[name]

    def get(self, name: str, version: APIVersion | str | None = None) -> VersionedAPI:
        """获取API"""
        if name not in self._apis:
            raise VersionNotFoundError(f"API '{name}' not found")

        if version is None:
            version = self._default_versions.get(name)
            if version is None:
                raise VersionNotFoundError(f"No default version for API '{name}'")
        elif isinstance(version, str):
            version = APIVersion.parse(version)

        if version not in self._apis[name]:
            raise VersionNotFoundError(f"Version {version} of API '{name}' not found")

        api = self._apis[name][version]

        if api.version.is_retired():
            raise VersionNotFoundError(
                f"Version {version} of API '{name}' has been retired"
            )

        if api.version.is_deprecated():
            raise VersionDeprecatedError(
                f"Version {version} of API '{name}' is deprecated"
            )

        return api

    def call(
        self,
        name: str,
        version: APIVersion | str | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """调用API"""
        api = self.get(name, version)
        return api.handler(*args, **kwargs)

    def deprecate(
        self,
        name: str,
        version: APIVersion | str,
        sunset_at: datetime | None = None,
    ) -> None:
        """标记API版本为弃用"""
        if isinstance(version, str):
            version = APIVersion.parse(version)

        if name not in self._apis or version not in self._apis[name]:
            raise VersionNotFoundError(f"Version {version} of API '{name}' not found")

        api = self._apis[name][version]
        api.version.status = VersionStatus.DEPRECATED
        api.version.deprecated_at = datetime.now()
        api.version.sunset_at = sunset_at

    def retire(self, name: str, version: APIVersion | str) -> None:
        """标记API版本为退役"""
        if isinstance(version, str):
            version = APIVersion.parse(version)

        if name not in self._apis or version not in self._apis[name]:
            raise VersionNotFoundError(f"Version {version} of API '{name}' not found")

        api = self._apis[name][version]
        api.version.status = VersionStatus.RETIRED

    def get_versions(self, name: str) -> list[APIVersion]:
        """获取API的所有版本"""
        if name not in self._apis:
            return []
        return sorted(self._apis[name].keys())

    def get_active_versions(self, name: str) -> list[APIVersion]:
        """获取API的所有活跃版本"""
        if name not in self._apis:
            return []
        return sorted(
            [v for v, api in self._apis[name].items() if api.version.is_active()]
        )

    def get_latest_version(self, name: str) -> APIVersion | None:
        """获取API的最新版本"""
        versions = self.get_active_versions(name)
        return versions[-1] if versions else None

    def set_default_version(self, name: str, version: APIVersion | str) -> None:
        """设置默认版本"""
        if isinstance(version, str):
            version = APIVersion.parse(version)

        if name not in self._apis or version not in self._apis[name]:
            raise VersionNotFoundError(f"Version {version} of API '{name}' not found")

        self._default_versions[name] = version

    def get_default_version(self, name: str) -> APIVersion | None:
        """获取默认版本"""
        return self._default_versions.get(name)

    def negotiate_version(
        self, name: str, requested: APIVersion | str | None = None
    ) -> APIVersion:
        """协商最佳版本"""
        if name not in self._apis:
            raise VersionNotFoundError(f"API '{name}' not found")

        active_versions = self.get_active_versions(name)
        if not active_versions:
            raise VersionNotFoundError(f"No active versions for API '{name}'")

        if requested is None:
            return active_versions[-1]

        if isinstance(requested, str):
            requested = APIVersion.parse(requested)

        compatible = [v for v in active_versions if v.is_compatible_with(requested)]

        if not compatible:
            return active_versions[-1]

        exact_match = [v for v in compatible if v == requested]
        if exact_match:
            return exact_match[0]

        return max(compatible)

    def list_apis(self) -> dict[str, list[str]]:
        """列出所有API及其版本"""
        return {
            name: [str(v) for v in sorted(versions.keys())]
            for name, versions in self._apis.items()
        }

    def get_status(self) -> dict[str, Any]:
        """获取管理器状态"""
        return {
            "total_apis": len(self._apis),
            "apis": {
                name: {
                    "versions": [
                        {
                            "version": str(v),
                            "status": api.version.status.value,
                            "description": api.description,
                        }
                        for v, api in sorted(versions.items())
                    ],
                    "default": str(self._default_versions.get(name, "")),
                }
                for name, versions in self._apis.items()
            },
        }
