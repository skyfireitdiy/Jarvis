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
    for tool in TOOLS_CONFIG:
        if tool["name"] == tool_name:
            return tool
    return None
