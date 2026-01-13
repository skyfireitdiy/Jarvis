# -*- coding: utf-8 -*-
"""工具检查核心逻辑

提供工具检测的核心功能实现。
"""

import subprocess
import shutil
from typing import Any, Dict, List, Optional

from jarvis.jarvis_jck.config import (
    get_tools_config,
    get_tool_config,
    get_lint_tools_config,
    get_build_tools_config,
)


class ToolChecker:
    """工具检查器类

    用于检测系统中工具的安装情况，包括检测工具是否存在、
    获取版本信息等。
    """

    def __init__(self) -> None:
        """初始化工具检查器"""
        self.tools_config = get_tools_config()
        self.lint_tools_config = get_lint_tools_config()
        self.build_tools_config = get_build_tools_config()

    def check_tool_exists(self, command: str) -> bool:
        """检查工具命令是否存在

        参数:
            command: 工具命令名称

        返回:
            bool: 工具是否存在
        """
        return shutil.which(command) is not None

    def get_tool_version(self, command: str) -> Optional[str]:
        """获取工具版本信息

        参数:
            command: 工具命令名称

        返回:
            版本字符串，如果获取失败则返回None
        """
        if not self.check_tool_exists(command):
            return None

        # 常见的版本获取参数
        version_args = ["--version", "version", "-V", "-v"]

        for arg in version_args:
            try:
                result = subprocess.run(
                    [command, arg],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout:
                    # 只返回第一行版本信息
                    version = result.stdout.strip().split("\n")[0]
                    return version
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue

        return None

    def check_single_tool(self, tool_name: str) -> Dict[str, Any]:
        """检索单个工具

        参数:
            tool_name: 工具名称

        返回:
            包含工具检查结果的字典
        """
        tool_config = get_tool_config(tool_name)

        if not tool_config:
            return {
                "name": tool_name,
                "found": False,
                "error": f"未知的工具: {tool_name}",
                "description": "",
                "install_hint": "",
                "version": None,
            }

        command = tool_config["command"]
        exists = self.check_tool_exists(command)

        result = {
            "name": tool_name,
            "command": command,
            "found": exists,
            "description": tool_config["description"],
            "install_hint": tool_config["install_hint"],
            "version": None,
        }

        if exists:
            version = self.get_tool_version(command)
            result["version"] = version

        return result

    def check_all_tools(self) -> List[Dict[str, Any]]:
        """检查所有配置的工具

        返回:
            包含所有工具检查结果的列表
        """
        results = []

        for tool_config in self.tools_config:
            tool_name = tool_config["name"]
            result = self.check_single_tool(tool_name)
            results.append(result)

        return results

    def get_summary(self, results: List[Dict[str, Any]]) -> Dict[str, int]:
        """获取检查结果摘要

        参数:
            results: 工具检查结果列表

        返回:
            包含摘要统计的字典
        """
        total = len(results)
        found = sum(1 for r in results if r["found"])
        missing = total - found

        return {
            "total": total,
            "found": found,
            "missing": missing,
        }

    def check_lint_tools(self) -> List[Dict[str, Any]]:
        """检查所有lint工具

        返回:
            包含所有lint工具检查结果的列表
        """
        results = []

        for tool_config in self.lint_tools_config:
            tool_name = tool_config["name"]
            result = self.check_single_tool(tool_name)
            results.append(result)

        return results

    def check_build_tools(self) -> List[Dict[str, Any]]:
        """检查所有构建工具

        返回:
            包含所有构建工具检查结果的列表
        """
        results = []

        for tool_config in self.build_tools_config:
            tool_name = tool_config["name"]
            result = self.check_single_tool(tool_name)
            results.append(result)

        return results
