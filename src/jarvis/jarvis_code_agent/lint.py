#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Lint工具配置模块

提供lint工具配置和命令生成功能。
"""

import os
from typing import Dict, List, Tuple, Optional

import yaml  # type: ignore

from jarvis.jarvis_utils.config import get_data_dir

# Lint工具命令模板映射（文件扩展名/文件名 -> 命令模板列表）
# 占位符说明：
# - {file_path}: 单个文件的完整路径
# - {file_name}: 文件名（不含路径）
# - {config}: 配置文件路径（可选）
LINT_COMMAND_TEMPLATES_BY_FILE: Dict[str, List[str]] = {
    # C/C++
    ".c": ["clang-tidy {file_path}"],
    ".cpp": ["clang-tidy {file_path}"],
    ".cc": ["clang-tidy {file_path}"],
    ".cxx": ["clang-tidy {file_path}"],
    ".h": ["clang-tidy {file_path}"],
    ".hpp": ["clang-tidy {file_path}"],
    ".hxx": ["clang-tidy {file_path}"],
    ".inl": ["clang-tidy {file_path}"],
    ".ipp": ["clang-tidy {file_path}"],
    # Go
    ".go": ["go vet {file_path}"],
    # Python
    ".py": [
        "ruff check {file_path}",
        "mypy {file_path}",
    ],
    ".pyw": [
        "ruff check {file_path}",
        "mypy {file_path}",
    ],
    ".pyi": [
        "ruff check {file_path}",
        "mypy {file_path}",
    ],
    ".pyx": [
        "ruff check {file_path}",
        "mypy {file_path}",
    ],
    ".pxd": [
        "ruff check {file_path}",
        "mypy {file_path}",
    ],
    # Rust
    ".rs": ["cargo clippy --message-format=short"],
    ".rlib": ["cargo clippy --message-format=short"],
    # Java
    ".java": ["pmd check -d {file_path}"],
    ".class": ["pmd check -d {file_path}"],
    ".jar": ["pmd check -d {file_path}"],
    # JavaScript/TypeScript
    ".js": ["eslint {file_path}"],
    ".mjs": ["eslint {file_path}"],
    ".cjs": ["eslint {file_path}"],
    ".jsx": ["eslint {file_path}"],
    ".ts": [
        "eslint {file_path}",
        "tsc --noEmit {file_path}",
    ],
    ".tsx": [
        "eslint {file_path}",
        "tsc --noEmit {file_path}",
    ],
    ".cts": [
        "eslint {file_path}",
        "tsc --noEmit {file_path}",
    ],
    ".mts": [
        "eslint {file_path}",
        "tsc --noEmit {file_path}",
    ],
    # PHP
    ".php": ["phpstan analyse {file_path}"],
    ".phtml": ["phpstan analyse {file_path}"],
    ".php5": ["phpstan analyse {file_path}"],
    ".php7": ["phpstan analyse {file_path}"],
    ".phps": ["phpstan analyse {file_path}"],
    # Ruby
    ".rb": ["rubocop {file_path}"],
    ".rake": ["rubocop {file_path}"],
    ".gemspec": ["rubocop {file_path}"],
    # Swift
    ".swift": ["swiftlint lint {file_path}"],
    # Kotlin
    ".kt": ["ktlint {file_path}"],
    ".kts": ["ktlint {file_path}"],
    # C#
    ".cs": ["roslynator analyze {file_path}"],
    ".csx": ["roslynator analyze {file_path}"],
    # SQL
    ".sql": ["sqlfluff lint {file_path}"],
    # Shell/Bash
    ".sh": ["shellcheck {file_path}"],
    ".bash": ["shellcheck {file_path}"],
    # HTML/CSS
    ".html": ["htmlhint {file_path}"],
    ".htm": ["htmlhint {file_path}"],
    ".xhtml": ["htmlhint {file_path}"],
    ".css": ["stylelint {file_path}"],
    ".scss": ["stylelint {file_path}"],
    ".sass": ["stylelint {file_path}"],
    ".less": ["stylelint {file_path}"],
    # XML/JSON/YAML
    ".xml": ["xmllint --noout {file_path}"],
    ".xsd": ["xmllint --noout {file_path}"],
    ".dtd": ["xmllint --noout {file_path}"],
    ".tld": ["xmllint --noout {file_path}"],
    ".jsp": ["xmllint --noout {file_path}"],
    ".jspx": ["xmllint --noout {file_path}"],
    ".tag": ["xmllint --noout {file_path}"],
    ".tagx": ["xmllint --noout {file_path}"],
    ".json": ["jsonlint {file_path}"],
    ".jsonl": ["jsonlint {file_path}"],
    ".json5": ["jsonlint {file_path}"],
    ".yaml": ["yamllint {file_path}"],
    ".yml": ["yamllint {file_path}"],
    # Markdown/Documentation
    ".md": ["markdownlint {file_path}"],
    ".markdown": ["markdownlint {file_path}"],
    ".rst": ["rstcheck {file_path}"],
    ".adoc": ["asciidoctor-lint {file_path}"],
    # Docker/Terraform/Makefile等无后缀文件
    "makefile": ["checkmake {file_path}"],
    "dockerfile": ["hadolint {file_path}"],
    "docker-compose.yml": ["hadolint {file_path}"],
    "docker-compose.yaml": ["hadolint {file_path}"],
    "jenkinsfile": ["jenkinsfile-linter {file_path}"],
    "build": ["buildifier {file_path}"],
    "workspace": ["buildifier {file_path}"],
    ".bashrc": ["shellcheck {file_path}"],
    ".bash_profile": ["shellcheck {file_path}"],
    ".zshrc": ["shellcheck {file_path}"],
    ".gitignore": ["git-lint {file_path}"],
    ".editorconfig": ["editorconfig-checker {file_path}"],
    ".eslintrc": ["eslint {file_path}"],
    ".prettierrc": ["prettier --check {file_path}"],
}


def load_lint_tools_config() -> Dict[str, List[str]]:
    """从yaml文件加载全局lint工具配置

    Returns:
        Dict[str, List[str]]: 文件扩展名/文件名 -> 命令模板列表
    """
    config_path = os.path.join(get_data_dir(), "lint_tools.yaml")
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


def load_project_lint_tools_config(project_root: str) -> Dict[str, List[str]]:
    """从项目根目录加载lint工具配置

    Args:
        project_root: 项目根目录

    Returns:
        Dict[str, List[str]]: 文件扩展名/文件名 -> 命令模板列表
    """
    project_config_path = os.path.join(project_root, ".jarvis", "lint_tools.yaml")
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
LINT_COMMAND_TEMPLATES_BY_FILE.update(load_lint_tools_config())


def _format_lint_command(
    template: str,
    file_path: str,
    project_root: Optional[str] = None,
) -> Optional[str]:
    """
    格式化lint命令模板（内部函数）

    Args:
        template: 命令模板字符串
        file_path: 文件路径（相对或绝对路径）
        project_root: 项目根目录（可选，用于处理相对路径）

    Returns:
        命令字符串，如果无法生成则返回None
    """
    # 特殊处理：某些工具不需要文件路径（如 cargo clippy）
    if "{file_path}" not in template and "{file_name}" not in template:
        # 不需要文件路径，直接返回模板
        return template

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

    # 如果模板中有 {config} 占位符，说明需要配置文件
    # 现在配置文件应该直接写在模板中，不支持自动查找
    if "{config}" in template:
        # 如果模板中有 {config} 但未提供，返回None
        # 用户应该在模板中直接指定配置文件路径，或使用其他占位符
        return None

    # 替换占位符
    try:
        command = template.format(**placeholders)
    except KeyError:
        # 如果模板中有未定义的占位符，返回None
        return None

    return command


def get_lint_commands_for_files(
    files: List[str], project_root: Optional[str] = None
) -> List[Tuple[str, str]]:
    """
    获取多个文件的lint命令列表

    Args:
        files: 文件路径列表
        project_root: 项目根目录（可选），如果提供则加载项目级配置

    Returns:
        [(file_path, command), ...] 格式的命令列表
    """
    # 加载项目级配置（如果提供项目根目录）
    # 项目级配置会覆盖全局配置
    config = LINT_COMMAND_TEMPLATES_BY_FILE.copy()
    if project_root:
        project_config = load_project_lint_tools_config(project_root)
        config.update(project_config)  # 项目配置覆盖全局配置

    commands = []
    # 记录不需要文件路径的工具模板（如 cargo clippy），避免重复执行
    project_level_templates = set()

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
            # 检查是否是项目级别的工具（不需要文件路径）
            if "{file_path}" not in template and "{file_name}" not in template:
                # 项目级别工具，每个项目只执行一次
                if template not in project_level_templates:
                    project_level_templates.add(template)
                    command = _format_lint_command(template, file_path, project_root)
                    if command:
                        # 使用第一个文件作为标识
                        commands.append((file_path, command))
            else:
                # 文件级别工具，每个文件都执行
                command = _format_lint_command(template, file_path, project_root)
                if command:
                    commands.append((file_path, command))

    return commands


def group_commands_by_template(
    commands: List[Tuple[str, str]],
) -> Dict[str, List[Tuple[str, str]]]:
    """
    按命令模板分组命令（通过命令的第一个单词识别）

    Args:
        commands: [(file_path, command), ...] 格式的命令列表

    Returns:
        {template_key: [(file_path, command), ...]} 格式的字典
        template_key 是命令的第一个单词
    """
    grouped = {}
    for file_path, command in commands:
        # 使用命令的第一个单词作为分组键
        template_key = command.split()[0] if command.split() else "unknown"
        if template_key not in grouped:
            grouped[template_key] = []
        grouped[template_key].append((file_path, command))
    return grouped


# 格式化工具配置（文件扩展名/文件名 -> 格式化工具列表）
POST_COMMAND_FOR_FILE_TYPE = {
    # Python
    ".py": ["ruff format"],
    ".pyw": ["ruff format"],
    ".pyi": ["ruff format"],
    ".pyx": ["ruff format"],
    ".pxd": ["ruff format"],
    # JavaScript/TypeScript
    ".js": ["prettier"],
    ".mjs": ["prettier"],
    ".cjs": ["prettier"],
    ".jsx": ["prettier"],
    ".ts": ["prettier"],
    ".tsx": ["prettier"],
    ".cts": ["prettier"],
    ".mts": ["prettier"],
    # Rust
    ".rs": ["rustfmt"],
    # Go
    ".go": ["gofmt"],
    # Java
    ".java": ["google-java-format"],
    # C/C++
    ".c": ["clang-format"],
    ".cpp": ["clang-format"],
    ".cc": ["clang-format"],
    ".cxx": ["clang-format"],
    ".h": ["clang-format"],
    ".hpp": ["clang-format"],
    ".hxx": ["clang-format"],
    ".inl": ["clang-format"],
    ".ipp": ["clang-format"],
    # HTML/CSS
    ".html": ["prettier"],
    ".htm": ["prettier"],
    ".xhtml": ["prettier"],
    ".css": ["prettier"],
    ".scss": ["prettier"],
    ".sass": ["prettier"],
    ".less": ["prettier"],
    # JSON/YAML
    ".json": ["prettier"],
    ".jsonl": ["prettier"],
    ".json5": ["prettier"],
    ".yaml": ["prettier"],
    ".yml": ["prettier"],
    # Markdown
    ".md": ["prettier"],
    ".markdown": ["prettier"],
    # SQL
    ".sql": ["sqlfluff format"],
    # Shell/Bash
    ".sh": ["shfmt"],
    ".bash": ["shfmt"],
    # XML
    ".xml": ["xmllint --format"],
    ".xsd": ["xmllint --format"],
    ".dtd": ["xmllint --format"],
}


def load_format_tools_config() -> Dict[str, List[str]]:
    """从yaml文件加载格式化工具配置"""
    config_path = os.path.join(get_data_dir(), "format_tools.yaml")
    if not os.path.exists(config_path):
        return {}

    with open(config_path, "r") as f:
        config = yaml.safe_load(f) or {}
        return {k.lower(): v for k, v in config.items()}  # 确保key是小写


# 合并默认配置和yaml配置
POST_COMMAND_FOR_FILE_TYPE.update(load_format_tools_config())


def get_format_tools(filename: str) -> List[str]:
    """
    根据文件扩展名或文件名获取对应的格式化工具列表
    优先级：完整文件名匹配 > 扩展名匹配

    Args:
        filename: 文件路径或文件名(如'test.py'或'Makefile')

    Returns:
        对应的格式化工具列表，如果找不到则返回空列表
    """
    filename = os.path.basename(filename)
    filename_lower = filename.lower()

    # 优先尝试完整文件名匹配
    format_tools = POST_COMMAND_FOR_FILE_TYPE.get(filename_lower, [])
    if format_tools:
        return format_tools

    # 如果文件名匹配失败，再尝试扩展名匹配
    ext = os.path.splitext(filename)[1]
    if ext:
        return POST_COMMAND_FOR_FILE_TYPE.get(ext.lower(), [])

    return []


# 格式化工具命令模板映射
# 占位符说明：
# - {file_path}: 单个文件的完整路径
# - {files}: 多个文件路径，用空格分隔
# - {file_name}: 文件名（不含路径）
FORMAT_COMMAND_TEMPLATES: Dict[str, str] = {
    # Python
    "black": "black {file_path}",
    "ruff format": "ruff format {file_path}",
    # JavaScript/TypeScript
    "prettier": "prettier --write {file_path}",
    # Rust
    "rustfmt": "rustfmt {file_path}",
    # Go
    "gofmt": "gofmt -w {file_path}",
    # Java
    "google-java-format": "google-java-format -i {file_path}",
    # C/C++
    "clang-format": "clang-format -i {file_path}",
    # SQL
    "sqlfluff format": "sqlfluff format {file_path}",
    # Shell/Bash
    "shfmt": "shfmt -w {file_path}",
    # XML (xmllint格式化需要特殊处理，使用临时文件)
    "xmllint --format": "xmllint --format {file_path} > {file_path}.tmp && mv {file_path}.tmp {file_path}",
}


def get_format_command(
    tool_name: str, file_path: str, project_root: Optional[str] = None
) -> Optional[str]:
    """
    获取格式化工具的具体命令

    Args:
        tool_name: 格式化工具名称（如 'black', 'prettier'）
        file_path: 文件路径（相对或绝对路径）
        project_root: 项目根目录（可选，用于处理相对路径）

    Returns:
        命令字符串，如果工具不支持则返回None
    """
    template = FORMAT_COMMAND_TEMPLATES.get(tool_name)
    if not template:
        return None

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


def get_post_commands_for_files(
    files: List[str], project_root: Optional[str] = None
) -> List[Tuple[str, str, str]]:
    """
    获取多个文件的格式化命令列表

    Args:
        files: 文件路径列表
        project_root: 项目根目录（可选）

    Returns:
        [(tool_name, file_path, command), ...] 格式的命令列表
    """
    commands = []

    for file_path in files:
        tools = get_format_tools(file_path)
        for tool_name in tools:
            command = get_format_command(tool_name, file_path, project_root)
            if command:
                commands.append((tool_name, file_path, command))

    return commands
