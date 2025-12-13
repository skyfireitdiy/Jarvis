#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
文件变更后处理工具配置模块

提供文件变更后处理工具配置和命令生成功能（如格式化、自动修复等）。
"""

import os
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

import yaml

from jarvis.jarvis_utils.config import get_data_dir

# 文件变更后处理工具命令模板映射（文件扩展名/文件名 -> 命令模板列表）
# 占位符说明：
# - {file_path}: 单个文件的完整路径
# - {file_name}: 文件名（不含路径）
AFTER_CHANGE_COMMAND_TEMPLATES_BY_FILE: Dict[str, List[str]] = {
    # Python
    ".py": ["ruff format {file_path}"],
    ".pyw": ["ruff format {file_path}"],
    ".pyi": ["ruff format {file_path}"],
    ".pyx": ["ruff format {file_path}"],
    ".pxd": ["ruff format {file_path}"],
    # JavaScript/TypeScript
    ".js": ["prettier --write {file_path}"],
    ".mjs": ["prettier --write {file_path}"],
    ".cjs": ["prettier --write {file_path}"],
    ".jsx": ["prettier --write {file_path}"],
    ".ts": ["prettier --write {file_path}"],
    ".tsx": ["prettier --write {file_path}"],
    ".cts": ["prettier --write {file_path}"],
    ".mts": ["prettier --write {file_path}"],
    # Rust
    ".rs": ["rustfmt {file_path}"],
    # Go
    ".go": ["gofmt -w {file_path}"],
    # Java
    ".java": ["google-java-format -i {file_path}"],
    # C/C++
    ".c": ["clang-format -i {file_path}"],
    ".cpp": ["clang-format -i {file_path}"],
    ".cc": ["clang-format -i {file_path}"],
    ".cxx": ["clang-format -i {file_path}"],
    ".h": ["clang-format -i {file_path}"],
    ".hpp": ["clang-format -i {file_path}"],
    ".hxx": ["clang-format -i {file_path}"],
    ".inl": ["clang-format -i {file_path}"],
    ".ipp": ["clang-format -i {file_path}"],
    # HTML/CSS
    ".html": ["prettier --write {file_path}"],
    ".htm": ["prettier --write {file_path}"],
    ".xhtml": ["prettier --write {file_path}"],
    ".css": ["prettier --write {file_path}"],
    ".scss": ["prettier --write {file_path}"],
    ".sass": ["prettier --write {file_path}"],
    ".less": ["prettier --write {file_path}"],
    # JSON/YAML
    ".json": ["prettier --write {file_path}"],
    ".jsonl": ["prettier --write {file_path}"],
    ".json5": ["prettier --write {file_path}"],
    ".yaml": ["prettier --write {file_path}"],
    ".yml": ["prettier --write {file_path}"],
    # Markdown
    ".md": ["prettier --write {file_path}"],
    ".markdown": ["prettier --write {file_path}"],
    # SQL
    ".sql": ["sqlfluff format {file_path}"],
    # Shell/Bash
    ".sh": ["shfmt -w {file_path}"],
    ".bash": ["shfmt -w {file_path}"],
    # XML
    ".xml": [
        "xmllint --format {file_path} > {file_path}.tmp && mv {file_path}.tmp {file_path}"
    ],
    ".xsd": [
        "xmllint --format {file_path} > {file_path}.tmp && mv {file_path}.tmp {file_path}"
    ],
    ".dtd": [
        "xmllint --format {file_path} > {file_path}.tmp && mv {file_path}.tmp {file_path}"
    ],
}


def load_after_change_tools_config() -> Dict[str, List[str]]:
    """从yaml文件加载全局文件变更后处理工具配置

    Returns:
        Dict[str, List[str]]: 文件扩展名/文件名 -> 命令模板列表
    """
    config_path = os.path.join(get_data_dir(), "after_change_tools.yaml")
    if not os.path.exists(config_path):
        return {}

    with open(config_path, "r") as f:
        config = yaml.safe_load(f) or {}
        result = {}
        for k, v in config.items():
            k_lower = k.lower()
            # 支持格式: ["template1", "template2"] 或 [("tool1", "template1"), ("tool2", "template2")]
            if isinstance(v, list) and v:
                if isinstance(v[0], str):
                    # 新格式：直接是命令模板列表
                    result[k_lower] = v
                elif isinstance(v[0], (list, tuple)) and len(v[0]) == 2:
                    # 旧格式：需要提取模板
                    result[k_lower] = [template for _, template in v]
        return result


def load_project_after_change_tools_config(project_root: str) -> Dict[str, List[str]]:
    """从项目根目录加载文件变更后处理工具配置

    Args:
        project_root: 项目根目录

    Returns:
        Dict[str, List[str]]: 文件扩展名/文件名 -> 命令模板列表
    """
    project_config_path = os.path.join(
        project_root, ".jarvis", "after_change_tools.yaml"
    )
    if not os.path.exists(project_config_path):
        return {}

    with open(project_config_path, "r") as f:
        config = yaml.safe_load(f) or {}
        result = {}
        for k, v in config.items():
            k_lower = k.lower()
            # 支持格式: ["template1", "template2"] 或 [("tool1", "template1"), ("tool2", "template2")]
            if isinstance(v, list) and v:
                if isinstance(v[0], str):
                    # 新格式：直接是命令模板列表
                    result[k_lower] = v
                elif isinstance(v[0], (list, tuple)) and len(v[0]) == 2:
                    # 旧格式：需要提取模板
                    result[k_lower] = [template for _, template in v]
        return result


# 合并默认配置和全局yaml配置（项目级配置在运行时动态加载）
AFTER_CHANGE_COMMAND_TEMPLATES_BY_FILE.update(load_after_change_tools_config())


def _format_after_change_command(
    template: str,
    file_path: str,
    project_root: Optional[str] = None,
) -> Optional[str]:
    """
    格式化命令模板（内部函数）

    Args:
        template: 命令模板字符串
        file_path: 文件路径（相对或绝对路径）
        project_root: 项目根目录（可选，用于处理相对路径）

    Returns:
        命令字符串，如果无法生成则返回None
    """
    # 如果是绝对路径，直接使用；否则转换为绝对路径
    if os.path.isabs(file_path):
        abs_file_path = file_path
    elif project_root:
        abs_file_path = os.path.join(project_root, file_path)
    else:
        abs_file_path = os.path.abspath(file_path)

    # 准备占位符替换字典
    placeholders = {
        "file_path": abs_file_path,
        "file_name": os.path.basename(abs_file_path),
    }

    # 替换占位符
    try:
        command = template.format(**placeholders)
    except KeyError:
        # 如果模板中有未定义的占位符，返回None
        return None

    return command


def get_after_change_commands_for_files(
    files: List[str], project_root: Optional[str] = None
) -> List[Tuple[str, str]]:
    """
    获取多个文件的变更后处理命令列表

    Args:
        files: 文件路径列表
        project_root: 项目根目录（可选），如果提供则加载项目级配置

    Returns:
        [(file_path, command), ...] 格式的命令列表
    """
    # 加载项目级配置（如果提供项目根目录）
    # 项目级配置会覆盖全局配置
    config = AFTER_CHANGE_COMMAND_TEMPLATES_BY_FILE.copy()
    if project_root:
        project_config = load_project_after_change_tools_config(project_root)
        config.update(project_config)  # 项目配置覆盖全局配置

    commands = []

    for file_path in files:
        # 从文件扩展名/文件名直接获取命令模板列表
        filename = os.path.basename(file_path)
        filename_lower = filename.lower()

        # 优先尝试完整文件名匹配
        templates = config.get(filename_lower, [])

        # 如果文件名匹配失败，再尝试扩展名匹配
        if not templates:
            ext = os.path.splitext(filename)[1]
            if ext:
                templates = config.get(ext.lower(), [])

        for template in templates:
            command = _format_after_change_command(template, file_path, project_root)
            if command:
                commands.append((file_path, command))

    return commands
