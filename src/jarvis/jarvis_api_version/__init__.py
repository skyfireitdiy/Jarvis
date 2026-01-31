"""Jarvis版本化API机制

提供API版本管理、路由和兼容性检查功能。

主要功能：
- API版本注册：注册不同版本的API处理器
- 版本路由：根据请求版本路由到对应处理器
- 兼容性检查：检查API版本兼容性
- 版本协商：自动选择最佳API版本
"""

from jarvis.jarvis_api_version.version_manager import (
    APIVersion,
    APIVersionManager,
    VersionedAPI,
    VersionError,
    VersionNotFoundError,
    VersionDeprecatedError,
)

__all__ = [
    "APIVersion",
    "APIVersionManager",
    "VersionedAPI",
    "VersionError",
    "VersionNotFoundError",
    "VersionDeprecatedError",
]
