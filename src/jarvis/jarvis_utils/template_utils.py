# -*- coding: utf-8 -*-
"""Jinja2 模板渲染工具模块

提供统一的 jinja2 模板渲染功能，支持在模板中使用内置变量。
内置变量包括：
- current_dir: 当前工作目录
- script_dir: 脚本所在目录
- jarvis_data_dir: Jarvis数据目录
- jarvis_src_dir: Jarvis源码目录
- git_root_dir: Git根目录
- rule_file_dir: 规则文件所在目录
"""

import os
import subprocess
from pathlib import Path
from typing import Any

import jinja2
from jinja2 import TemplateError, TemplateSyntaxError

from jarvis.jarvis_utils.output import PrettyOutput


def render_rule_template(
    rule_content: str, rule_file_dir: str, file_path: str | None = None
) -> str:
    """使用jinja2渲染规则模板

    参数:
        rule_content: 规则原始内容
        rule_file_dir: 规则文件所在目录
        file_path: 规则文件完整路径（可选，用于打印加载成功信息）

    返回:
        str: 渲染后的内容，如果渲染失败则返回原始内容
    """
    if not rule_content:
        return rule_content

    # 构建jinja2上下文变量
    context: dict[str, Any] = {
        "current_dir": Path.cwd().as_posix(),
        "script_dir": Path(__file__).parent.as_posix(),  # 当前脚本所在目录
        "jarvis_data_dir": _get_jarvis_data_dir(),
        "jarvis_src_dir": _get_jarvis_src_dir(),
        "git_root_dir": _get_git_root(),
        "rule_file_dir": rule_file_dir,  # 当前规则文件所在目录
    }

    # 使用jinja2渲染模板
    try:
        template = jinja2.Template(rule_content)
        result = template.render(**context).strip()
        # 渲染成功，打印加载成功信息
        if file_path:
            rule_name = Path(file_path).stem
            PrettyOutput.auto_print(f"✅ 加载{rule_name}规则成功")
        return result
    except (TemplateError, TemplateSyntaxError):
        # 渲染失败时返回原始内容（向后兼容）
        return rule_content.strip()
    except Exception:
        # 其他异常（如内存错误等）也返回原始内容
        return rule_content.strip()


def _get_git_root() -> str:
    """获取git根目录

    如果当前目录不在git仓库中，将返回当前工作目录作为回退值。

    返回:
        str: git根目录的绝对路径（如果不在git仓库中则返回当前工作目录）
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    # 不在git仓库中，返回当前工作目录
    return os.getcwd()


def _get_jarvis_src_dir() -> str:
    """获取jarvis源码目录

    返回:
        str: jarvis源码目录的绝对路径
    """
    # 从当前文件位置向上定位到项目根目录
    # src/jarvis/jarvis_utils/template_utils.py -> 项目根目录
    return str(Path(__file__).parent.parent.parent.resolve())


def _get_jarvis_data_dir() -> str:
    """获取jarvis数据目录

    返回:
        str: jarvis数据目录路径
    """
    try:
        from jarvis.jarvis_utils.config import get_data_dir

        return get_data_dir()
    except ImportError:
        # 如果导入失败，返回默认路径
        return os.path.expanduser("~/.jarvis")
