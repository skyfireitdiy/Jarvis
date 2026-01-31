"""Jarvis插件系统 - 模块热插拔机制

提供运行时动态加载、卸载和管理插件的能力。

主要功能：
- 插件发现：自动扫描指定目录发现插件
- 插件加载：动态加载插件模块
- 插件卸载：安全卸载插件并清理资源
- 生命周期管理：插件的初始化、启动、停止、销毁
- 依赖管理：处理插件间的依赖关系
"""

from jarvis.jarvis_plugin.plugin_manager import (
    PluginManager,
    PluginInfo,
    PluginState,
    PluginError,
    PluginLoadError,
    PluginUnloadError,
)
from jarvis.jarvis_plugin.plugin_base import PluginBase, PluginMeta

__all__ = [
    "PluginManager",
    "PluginInfo",
    "PluginState",
    "PluginError",
    "PluginLoadError",
    "PluginUnloadError",
    "PluginBase",
    "PluginMeta",
]
