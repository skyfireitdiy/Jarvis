#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Lint工具配置模块
"""

import os
from typing import Dict, List

import yaml

from jarvis.jarvis_utils.config import get_data_dir

# 默认的lint工具配置
LINT_TOOLS = {
    # C/C++
    '.c': ['cppcheck', 'clang-tidy'],
    '.cpp': ['cppcheck', 'clang-tidy'],
    '.cc': ['cppcheck', 'clang-tidy'],
    '.cxx': ['cppcheck', 'clang-tidy'],
    '.h': ['cppcheck', 'clang-tidy'],
    '.hpp': ['cppcheck', 'clang-tidy'],
    '.hxx': ['cppcheck', 'clang-tidy'],
    '.inl': ['cppcheck', 'clang-tidy'],
    '.ipp': ['cppcheck', 'clang-tidy'],
    
    # Go
    '.go': ['golint', 'go vet'],
    
    # Python
    '.py': ['black', 'pylint', 'mypy', 'isort'],
    '.pyw': ['black', 'pylint', 'mypy', 'isort'],
    '.pyi': ['black', 'pylint', 'mypy', 'isort'],
    '.pyx': ['black', 'pylint', 'mypy', 'isort'],
    '.pxd': ['black', 'pylint', 'mypy', 'isort'],
    
    # Rust
    '.rs': ['cargo clippy', 'rustfmt'],
    '.rlib': ['cargo clippy', 'rustfmt'],
    
    # Java
    '.java': ['checkstyle', 'pmd'],
    '.class': ['checkstyle', 'pmd'],
    '.jar': ['checkstyle', 'pmd'],
    
    # JavaScript/TypeScript
    '.js': ['eslint'],
    '.mjs': ['eslint'],
    '.cjs': ['eslint'],
    '.jsx': ['eslint'],
    '.ts': ['eslint', 'tsc'],
    '.tsx': ['eslint', 'tsc'],
    '.cts': ['eslint', 'tsc'],
    '.mts': ['eslint', 'tsc'],
    
    # PHP
    '.php': ['phpcs', 'phpstan'],
    '.phtml': ['phpcs', 'phpstan'],
    '.php5': ['phpcs', 'phpstan'],
    '.php7': ['phpcs', 'phpstan'],
    '.phps': ['phpcs', 'phpstan'],
    
    # Ruby
    '.rb': ['rubocop'],
    '.rake': ['rubocop'],
    '.gemspec': ['rubocop'],
    
    # Swift
    '.swift': ['swiftlint'],
    
    # Kotlin
    '.kt': ['ktlint'],
    '.kts': ['ktlint'],
    
    # C#
    '.cs': ['dotnet-format', 'roslynator'],
    '.csx': ['dotnet-format', 'roslynator'],
    
    # SQL
    '.sql': ['sqlfluff'],
    
    # Shell/Bash
    '.sh': ['shellcheck'],
    '.bash': ['shellcheck'],
    
    # HTML/CSS
    '.html': ['htmlhint'],
    '.htm': ['htmlhint'],
    '.xhtml': ['htmlhint'],
    '.css': ['stylelint'],
    '.scss': ['stylelint'],
    '.sass': ['stylelint'],
    '.less': ['stylelint'],
    
    # XML/JSON/YAML
    '.xml': ['xmllint'],
    '.xsd': ['xmllint'],
    '.dtd': ['xmllint'],
    '.tld': ['xmllint'],
    '.jsp': ['xmllint'],
    '.jspx': ['xmllint'],
    '.tag': ['xmllint'],
    '.tagx': ['xmllint'],
    '.json': ['jsonlint'],
    '.jsonl': ['jsonlint'],
    '.json5': ['jsonlint'],
    '.yaml': ['yamllint'],
    '.yml': ['yamllint'],
    
    # Markdown/Documentation
    '.md': ['markdownlint'],
    '.markdown': ['markdownlint'],
    '.rst': ['rstcheck'],
    '.adoc': ['asciidoctor-lint'],
    
    # Docker/Terraform/Makefile等无后缀文件
    'makefile': ['checkmake'],
    'dockerfile': ['hadolint'],
    'docker-compose.yml': ['hadolint'],
    'docker-compose.yaml': ['hadolint'],
    'jenkinsfile': ['jenkinsfile-linter'],
    'build': ['buildifier'],
    'workspace': ['buildifier'],
    '.bashrc': ['shellcheck'],
    '.bash_profile': ['shellcheck'],
    '.zshrc': ['shellcheck'],
    '.gitignore': ['git-lint'],
    '.editorconfig': ['editorconfig-checker'],
    '.eslintrc': ['eslint'],
    '.prettierrc': ['prettier'],
    'cmakelists.txt': ['cmake-format'],
    '.cmake': ['cmake-format'],
}

def load_lint_tools_config() -> Dict[str, List[str]]:
    """从yaml文件加载lint工具配置"""
    config_path = os.path.join(get_data_dir(), 'lint_tools.yaml')
    if not os.path.exists(config_path):
        return {}
    
    with open(config_path, 'r') as f:
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
