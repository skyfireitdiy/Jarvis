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

# 默认的lint工具配置
LINT_TOOLS = {
    # C/C++
    ".c": ["clang-tidy"],
    ".cpp": ["clang-tidy"],
    ".cc": ["clang-tidy"],
    ".cxx": ["clang-tidy"],
    ".h": ["clang-tidy"],
    ".hpp": ["clang-tidy"],
    ".hxx": ["clang-tidy"],
    ".inl": ["clang-tidy"],
    ".ipp": ["clang-tidy"],
    # Go
    ".go": ["go vet"],
    # Python
    ".py": ["ruff", "mypy"],
    ".pyw": ["ruff", "mypy"],
    ".pyi": ["ruff", "mypy"],
    ".pyx": ["ruff", "mypy"],
    ".pxd": ["ruff", "mypy"],
    # Rust
    ".rs": ["cargo clippy", "rustfmt"],
    ".rlib": ["cargo clippy", "rustfmt"],
    # Java
    ".java": ["pmd"],
    ".class": ["pmd"],
    ".jar": ["pmd"],
    # JavaScript/TypeScript
    ".js": ["eslint"],
    ".mjs": ["eslint"],
    ".cjs": ["eslint"],
    ".jsx": ["eslint"],
    ".ts": ["eslint", "tsc"],
    ".tsx": ["eslint", "tsc"],
    ".cts": ["eslint", "tsc"],
    ".mts": ["eslint", "tsc"],
    # PHP
    ".php": ["phpstan"],
    ".phtml": ["phpstan"],
    ".php5": ["phpstan"],
    ".php7": ["phpstan"],
    ".phps": ["phpstan"],
    # Ruby
    ".rb": ["rubocop"],
    ".rake": ["rubocop"],
    ".gemspec": ["rubocop"],
    # Swift
    ".swift": ["swiftlint"],
    # Kotlin
    ".kt": ["ktlint"],
    ".kts": ["ktlint"],
    # C#
    ".cs": ["roslynator"],
    ".csx": ["roslynator"],
    # SQL
    ".sql": ["sqlfluff"],
    # Shell/Bash
    ".sh": ["shellcheck"],
    ".bash": ["shellcheck"],
    # HTML/CSS
    ".html": ["htmlhint"],
    ".htm": ["htmlhint"],
    ".xhtml": ["htmlhint"],
    ".css": ["stylelint"],
    ".scss": ["stylelint"],
    ".sass": ["stylelint"],
    ".less": ["stylelint"],
    # XML/JSON/YAML
    ".xml": ["xmllint"],
    ".xsd": ["xmllint"],
    ".dtd": ["xmllint"],
    ".tld": ["xmllint"],
    ".jsp": ["xmllint"],
    ".jspx": ["xmllint"],
    ".tag": ["xmllint"],
    ".tagx": ["xmllint"],
    ".json": ["jsonlint"],
    ".jsonl": ["jsonlint"],
    ".json5": ["jsonlint"],
    ".yaml": ["yamllint"],
    ".yml": ["yamllint"],
    # Markdown/Documentation
    ".md": ["markdownlint"],
    ".markdown": ["markdownlint"],
    ".rst": ["rstcheck"],
    ".adoc": ["asciidoctor-lint"],
    # Docker/Terraform/Makefile等无后缀文件
    "makefile": ["checkmake"],
    "dockerfile": ["hadolint"],
    "docker-compose.yml": ["hadolint"],
    "docker-compose.yaml": ["hadolint"],
    "jenkinsfile": ["jenkinsfile-linter"],
    "build": ["buildifier"],
    "workspace": ["buildifier"],
    ".bashrc": ["shellcheck"],
    ".bash_profile": ["shellcheck"],
    ".zshrc": ["shellcheck"],
    ".gitignore": ["git-lint"],
    ".editorconfig": ["editorconfig-checker"],
    ".eslintrc": ["eslint"],
    ".prettierrc": ["prettier"],
    "cmakelists.txt": ["cmake-format"],
    ".cmake": ["cmake-format"],
}


def load_lint_tools_config() -> Dict[str, List[str]]:
    """从yaml文件加载lint工具配置"""
    config_path = os.path.join(get_data_dir(), "lint_tools.yaml")
    if not os.path.exists(config_path):
        return {}

    with open(config_path, "r") as f:
        config = yaml.safe_load(f) or {}
        return {k.lower(): v for k, v in config.items()}  # 确保key是小写


# 合并默认配置和yaml配置
LINT_TOOLS.update(load_lint_tools_config())


def get_lint_tools(filename: str) -> List[str]:
    """
    根据文件扩展名或文件名获取对应的lint工具列表

    Args:
        file_extension_or_name: 文件扩展名(如'.py')或文件名(如'Makefile')

    Returns:
        对应的lint工具列表，如果找不到则返回空列表
    """
    filename = os.path.basename(filename)
    ext = os.path.splitext(filename)[1]
    if ext:
        lint_tools = LINT_TOOLS.get(ext.lower(), [])
        if lint_tools:
            return lint_tools
    # 如果扩展名匹配失败或没有扩展名，再尝试用完整文件名匹配
    return LINT_TOOLS.get(filename.lower(), [])


# Lint工具命令模板映射
# 占位符说明：
# - {file_path}: 单个文件的完整路径
# - {files}: 多个文件路径，用空格分隔
# - {file_name}: 文件名（不含路径）
LINT_COMMAND_TEMPLATES: Dict[str, str] = {
    # Python
    "ruff": "ruff check {file_path}",
    "mypy": "mypy {file_path}",
    "pylint": "pylint {file_path}",
    "flake8": "flake8 {file_path}",
    "black": "black --check {file_path}",
    # JavaScript/TypeScript
    "eslint": "eslint {file_path}",
    "tsc": "tsc --noEmit {file_path}",
    # Rust
    "cargo clippy": "cargo clippy --message-format=short",
    "rustfmt": "rustfmt --check {file_path}",
    # Go
    "go vet": "go vet {file_path}",
    "golint": "golint {file_path}",
    # Java
    "pmd": "pmd check -d {file_path}",
    "checkstyle": "checkstyle -c {config} {file_path}",
    # C/C++
    "clang-tidy": "clang-tidy {file_path}",
    "cppcheck": "cppcheck {file_path}",
    # PHP
    "phpstan": "phpstan analyse {file_path}",
    # Ruby
    "rubocop": "rubocop {file_path}",
    # Swift
    "swiftlint": "swiftlint lint {file_path}",
    # Kotlin
    "ktlint": "ktlint {file_path}",
    # C#
    "roslynator": "roslynator analyze {file_path}",
    # SQL
    "sqlfluff": "sqlfluff lint {file_path}",
    # Shell/Bash
    "shellcheck": "shellcheck {file_path}",
    # HTML/CSS
    "htmlhint": "htmlhint {file_path}",
    "stylelint": "stylelint {file_path}",
    # XML/JSON/YAML
    "xmllint": "xmllint --noout {file_path}",
    "jsonlint": "jsonlint {file_path}",
    "yamllint": "yamllint {file_path}",
    # Markdown
    "markdownlint": "markdownlint {file_path}",
    "rstcheck": "rstcheck {file_path}",
    # Docker
    "hadolint": "hadolint {file_path}",
    # Makefile
    "checkmake": "checkmake {file_path}",
    # CMake
    "cmake-format": "cmake-format --check {file_path}",
    # Prettier
    "prettier": "prettier --check {file_path}",
}


def find_config_file(config_names: List[str], project_root: Optional[str] = None, file_path: Optional[str] = None) -> Optional[str]:
    """
    查找配置文件
    
    Args:
        config_names: 配置文件名列表（按优先级排序）
        project_root: 项目根目录
        file_path: 当前文件路径（可选，用于从文件所在目录向上查找）
    
    Returns:
        配置文件的绝对路径，如果未找到则返回None
    """
    search_dirs = []
    
    if project_root:
        search_dirs.append(project_root)
    
    # 如果提供了文件路径，从文件所在目录向上查找
    if file_path:
        if os.path.isabs(file_path):
            current_dir = os.path.dirname(file_path)
        elif project_root:
            current_dir = os.path.dirname(os.path.join(project_root, file_path))
        else:
            current_dir = os.path.dirname(os.path.abspath(file_path))
        
        # 向上查找直到项目根目录
        while current_dir:
            if current_dir not in search_dirs:
                search_dirs.append(current_dir)
            if project_root and current_dir == project_root:
                break
            parent = os.path.dirname(current_dir)
            if parent == current_dir:  # 到达根目录
                break
            current_dir = parent
    
    # 按优先级查找配置文件
    for config_name in config_names:
        for search_dir in search_dirs:
            config_path = os.path.join(search_dir, config_name)
            if os.path.exists(config_path) and os.path.isfile(config_path):
                return os.path.abspath(config_path)
    
    return None


# 工具配置文件映射（工具名 -> 可能的配置文件名列表）
TOOL_CONFIG_FILES: Dict[str, List[str]] = {
    "checkstyle": ["checkstyle.xml", ".checkstyle.xml", "checkstyle-config.xml"],
    "eslint": [".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml", ".eslintrc"],
    "prettier": [".prettierrc", ".prettierrc.json", ".prettierrc.yml", ".prettierrc.yaml", "prettier.config.js"],
    "stylelint": [".stylelintrc", ".stylelintrc.json", ".stylelintrc.yml", ".stylelintrc.yaml", "stylelint.config.js"],
    "yamllint": [".yamllint", ".yamllint.yml", ".yamllint.yaml"],
    "markdownlint": [".markdownlint.json", ".markdownlintrc"],
    "rubocop": [".rubocop.yml", ".rubocop.yaml", ".rubocop.toml"],
    "phpstan": ["phpstan.neon", "phpstan.neon.dist"],
    "sqlfluff": [".sqlfluff", "sqlfluff.ini", ".sqlfluff.ini"],
    "hadolint": [".hadolint.yaml", ".hadolint.yml"],
    "cmake-format": [".cmake-format.py", "cmake-format.json", ".cmake-format.json"],
}

# 必须配置文件的工具（未找到配置文件时不能执行）
REQUIRED_CONFIG_TOOLS = {"checkstyle"}

# 可选配置文件的工具（未找到配置文件时可以使用默认配置）
OPTIONAL_CONFIG_TOOLS = {"eslint", "prettier", "stylelint", "yamllint", "markdownlint", "rubocop", "phpstan", "sqlfluff", "hadolint", "cmake-format"}


def get_lint_command(tool_name: str, file_path: str, project_root: Optional[str] = None) -> Optional[str]:
    """
    获取lint工具的具体命令

    Args:
        tool_name: lint工具名称（如 'ruff', 'eslint'）
        file_path: 文件路径（相对或绝对路径）
        project_root: 项目根目录（可选，用于处理相对路径）

    Returns:
        命令字符串，如果工具不支持则返回None
    """
    template = LINT_COMMAND_TEMPLATES.get(tool_name)
    if not template:
        return None
    
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
    
    # 如果模板需要配置文件，尝试查找
    if "{config}" in template:
        config_names = TOOL_CONFIG_FILES.get(tool_name, [])
        if config_names:
            config_path = find_config_file(config_names, project_root, file_path)
            if config_path:
                placeholders["config"] = config_path
            else:
                # 未找到配置文件
                if tool_name in REQUIRED_CONFIG_TOOLS:
                    # 必须配置的工具，未找到配置文件则返回None
                    return None
                elif tool_name in OPTIONAL_CONFIG_TOOLS:
                    # 可选配置的工具，使用默认配置（移除config参数或使用默认值）
                    # 这里我们移除 {config} 占位符，让工具使用默认配置
                    # 但需要修改模板，所以这里我们返回None，让调用方知道需要处理
                    # 实际上，对于可选配置的工具，模板中不应该使用 {config}，或者应该提供默认值
                    # 为了简化，我们这里返回None，表示无法生成命令
                    # 更好的做法是在模板中提供默认值，如: "checkstyle {file_path}" 或 "checkstyle -c default.xml {file_path}"
                    return None
                else:
                    # 未定义的工具，返回None
                    return None
        else:
            # 工具需要配置但未定义配置文件名，返回None
            return None
    
    # 替换占位符
    try:
        command = template.format(**placeholders)
    except KeyError:
        # 如果模板中有未定义的占位符，返回None
        return None
    
    return command


def get_lint_commands_for_files(
    files: List[str], 
    project_root: Optional[str] = None
) -> List[Tuple[str, str, str]]:
    """
    获取多个文件的lint命令列表

    Args:
        files: 文件路径列表
        project_root: 项目根目录（可选）

    Returns:
        [(tool_name, file_path, command), ...] 格式的命令列表
    """
    commands = []
    # 记录不需要文件路径的工具（如 cargo clippy），避免重复执行
    project_level_tools = set()
    
    for file_path in files:
        tools = get_lint_tools(file_path)
        for tool_name in tools:
            # 检查是否是项目级别的工具（不需要文件路径）
            template = LINT_COMMAND_TEMPLATES.get(tool_name)
            if template and "{file_path}" not in template and "{file_name}" not in template:
                # 项目级别工具，每个项目只执行一次
                if tool_name not in project_level_tools:
                    project_level_tools.add(tool_name)
                    command = get_lint_command(tool_name, file_path, project_root)
                    if command:
                        # 使用第一个文件作为标识
                        commands.append((tool_name, file_path, command))
            else:
                # 文件级别工具，每个文件都执行
                command = get_lint_command(tool_name, file_path, project_root)
                if command:
                    commands.append((tool_name, file_path, command))
    
    return commands


def group_commands_by_tool(commands: List[Tuple[str, str, str]]) -> Dict[str, List[Tuple[str, str]]]:
    """
    按工具分组命令

    Args:
        commands: [(tool_name, file_path, command), ...] 格式的命令列表

    Returns:
        {tool_name: [(file_path, command), ...]} 格式的字典
    """
    grouped = {}
    for tool_name, file_path, command in commands:
        if tool_name not in grouped:
            grouped[tool_name] = []
        grouped[tool_name].append((file_path, command))
    return grouped
