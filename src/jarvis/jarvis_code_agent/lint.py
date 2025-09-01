#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Lint工具配置模块
"""

import os
from typing import Dict, List

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
    lint_tools = LINT_TOOLS.get(filename.lower(), [])
    if lint_tools:
        return lint_tools
    ext = os.path.splitext(filename)[1]
    return LINT_TOOLS.get(ext.lower(), [])
