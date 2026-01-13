# -*- coding: utf-8 -*-
"""工具配置定义

定义需要检查的工具列表及其相关信息。
"""

from typing import Dict, List

# 工具配置列表
TOOLS_CONFIG: List[Dict[str, str]] = [
    {
        "name": "git",
        "command": "git",
        "description": "分布式版本控制系统",
        "install_hint": "访问 https://git-scm.com/downloads 下载安装，或使用包管理器安装："
        "\n  Ubuntu/Debian: sudo apt install git"
        "\n  macOS: brew install git",
    },
    {
        "name": "ripgrep",
        "command": "rg",
        "description": "超快的文本搜索工具",
        "install_hint": "访问 https://github.com/BurntSushi/ripgrep#installation 安装，或使用包管理器："
        "\n  Ubuntu/Debian: sudo apt install ripgrep"
        "\n  macOS: brew install ripgrep",
    },
    {
        "name": "fd-find",
        "command": "fd",
        "description": "快速友好的文件查找工具",
        "install_hint": "访问 https://github.com/sharkdp/fd#installation 安装，或使用包管理器："
        "\n  Ubuntu/Debian: sudo apt install fd-find"
        "\n  macOS: brew install fd",
    },
    {
        "name": "fzf",
        "command": "fzf",
        "description": "命令行模糊搜索工具",
        "install_hint": "访问 https://github.com/junegunn/fzf#installation 安装，或使用包管理器："
        "\n  Ubuntu/Debian: sudo apt install fzf"
        "\n  macOS: brew install fzf",
    },
    {
        "name": "rustup",
        "command": "rustup",
        "description": "Rust工具链安装器",
        "install_hint": "访问 https://rustup.rs/ 安装，或运行："
        "\n  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
    },
    {
        "name": "cargo",
        "command": "cargo",
        "description": "Rust包管理器",
        "install_hint": "cargo通常随rustup一起安装，如果未安装请先安装rustup："
        "\n  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
    },
    {
        "name": "loc",
        "command": "loc",
        "description": "代码行数统计工具",
        "install_hint": "访问 https://github.com/cgag/loc 安装，或使用包管理器："
        "\n  Ubuntu/Debian: sudo apt install loc"
        "\n  macOS: brew install loc"
        "\n  Cargo: cargo install loc"
        "\n  pip: pip install loc",
    },
]

# Lint工具配置列表
LINT_TOOLS_CONFIG: List[Dict[str, str]] = [
    {
        "name": "ruff",
        "command": "ruff",
        "description": "Python代码linter和formatter",
        "install_hint": "安装：pip install ruff"
        "\n  或访问 https://docs.astral.sh/ruff/ 查看文档",
    },
    {
        "name": "mypy",
        "command": "mypy",
        "description": "Python静态类型检查器",
        "install_hint": "安装：pip install mypy"
        "\n  或访问 https://mypy.readthedocs.io/ 查看文档",
    },
    {
        "name": "pylint",
        "command": "pylint",
        "description": "Python代码分析工具",
        "install_hint": "安装：pip install pylint"
        "\n  或访问 https://pylint.org/ 查看文档",
    },
    {
        "name": "shellcheck",
        "command": "shellcheck",
        "description": "Shell脚本静态分析工具",
        "install_hint": "Ubuntu/Debian: sudo apt install shellcheck"
        "\n  macOS: brew install shellcheck"
        "\n  或访问 https://www.shellcheck.net/ 查看文档",
    },
    {
        "name": "clang-tidy",
        "command": "clang-tidy",
        "description": "C/C++ linter和静态分析工具",
        "install_hint": "Ubuntu/Debian: sudo apt install clang-tidy"
        "\n  macOS: brew install llvm"
        "\n  或访问 https://clang.llvm.org/extra/clang-tidy/ 查看文档",
    },
    {
        "name": "eslint",
        "command": "eslint",
        "description": "JavaScript/TypeScript linter",
        "install_hint": "安装：npm install -g eslint"
        "\n  或访问 https://eslint.org/ 查看文档",
    },
    {
        "name": "rubocop",
        "command": "rubocop",
        "description": "Ruby静态代码分析工具",
        "install_hint": "安装：gem install rubocop"
        "\n  或访问 https://docs.rubocop.org/ 查看文档",
    },
]

# 构建工具配置列表
BUILD_TOOLS_CONFIG: List[Dict[str, str]] = [
    {
        "name": "pytest",
        "command": "pytest",
        "description": "Python测试框架",
        "install_hint": "安装：pip install pytest"
        "\n  或访问 https://docs.pytest.org/ 查看文档",
    },
    {
        "name": "build",
        "command": "python -m build",
        "description": "Python包构建工具",
        "install_hint": "安装：pip install build"
        "\n  或访问 https://pypa-build.readthedocs.io/ 查看文档",
    },
    {
        "name": "twine",
        "command": "twine",
        "description": "PyPI包发布工具",
        "install_hint": "安装：pip install twine"
        "\n  或访问 https://twine.readthedocs.io/ 查看文档",
    },
    {
        "name": "cmake",
        "command": "cmake",
        "description": "跨平台构建系统生成器",
        "install_hint": "Ubuntu/Debian: sudo apt install cmake"
        "\n  macOS: brew install cmake"
        "\n  或访问 https://cmake.org/ 查看文档",
    },
    {
        "name": "go",
        "command": "go",
        "description": "Go语言工具链",
        "install_hint": "访问 https://go.dev/dl/ 下载安装，或使用包管理器："
        "\n  Ubuntu/Debian: sudo apt install golang-go"
        "\n  macOS: brew install go",
    },
    {
        "name": "gradle",
        "command": "gradle",
        "description": "Java自动化构建工具",
        "install_hint": "Ubuntu/Debian: sudo apt install gradle"
        "\n  macOS: brew install gradle"
        "\n  或访问 https://gradle.org/ 查看文档",
    },
    {
        "name": "maven",
        "command": "mvn",
        "description": "Java项目管理工具",
        "install_hint": "Ubuntu/Debian: sudo apt install maven"
        "\n  macOS: brew install maven"
        "\n  或访问 https://maven.apache.org/ 查看文档",
    },
    {
        "name": "npm",
        "command": "npm",
        "description": "Node.js包管理器",
        "install_hint": "安装Node.js时会自动包含npm"
        "\n  访问 https://nodejs.org/ 下载安装"
        "\n  或访问 https://docs.npmjs.com/ 查看文档",
    },
]

# 获取工具配置


def get_tools_config() -> List[Dict[str, str]]:
    """获取工具配置列表"""
    return TOOLS_CONFIG


def get_tool_config(tool_name: str) -> Dict[str, str] | None:
    """获取指定工具的配置

    参数:
        tool_name: 工具名称

    返回:
        工具配置字典，如果未找到则返回None
    """
    # 在所有配置列表中查找工具
    for config_list in [TOOLS_CONFIG, LINT_TOOLS_CONFIG, BUILD_TOOLS_CONFIG]:
        for tool in config_list:
            if tool["name"] == tool_name:
                return tool
    return None


def get_lint_tools_config() -> List[Dict[str, str]]:
    """获取lint工具配置列表"""
    return LINT_TOOLS_CONFIG


def get_build_tools_config() -> List[Dict[str, str]]:
    """获取构建工具配置列表"""
    return BUILD_TOOLS_CONFIG
