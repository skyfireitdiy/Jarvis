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
        file_path: 规则文件完整路径（可选，用于打印加载成功信息和添加路径注释）

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

    # 如果提供了 file_path，添加 rule_file_path 到上下文
    if file_path:
        context["rule_file_path"] = (
            os.path.abspath(file_path) if not os.path.isabs(file_path) else file_path
        )

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
    return str(Path(__file__).parent.parent.parent.parent.resolve())


def _get_builtin_dir() -> Path | None:
    """获取 builtin 目录路径

    此函数会尝试从多个位置查找 builtin 目录：
    1. 从安装后的包位置查找（如果使用 uv tool install 等工具安装）
    2. 从源码位置查找（开发环境）

    返回:
        Path: builtin 目录的路径，如果未找到则返回 None
    """
    # 方法1: 尝试从当前文件位置向上查找 builtin 目录
    # 这对于开发环境和某些安装方式有效
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        builtin_dir = parent / "builtin"
        if builtin_dir.exists() and builtin_dir.is_dir():
            return builtin_dir

    # 方法2: 尝试从 jarvis 包安装位置查找
    # 如果使用 uv tool install，builtin 可能被安装到包数据目录
    try:
        import importlib.resources

        # 尝试从 jarvis 包中查找 builtin 目录
        try:
            # 检查是否有 builtin 作为包数据
            with importlib.resources.path("jarvis", "__init__.py") as jarvis_init:
                jarvis_pkg_dir = jarvis_init.parent
                # 尝试在包目录的父目录查找 builtin
                for parent in jarvis_pkg_dir.parents:
                    builtin_dir = parent / "builtin"
                    if builtin_dir.exists() and builtin_dir.is_dir():
                        return builtin_dir
        except (ImportError, ModuleNotFoundError, TypeError):
            pass
    except ImportError:
        pass

    # 方法3: 尝试从项目根目录查找（通过 git 或向上遍历）
    try:
        git_root = _get_git_root()
        if git_root:
            builtin_dir = Path(git_root) / "builtin"
            if builtin_dir.exists() and builtin_dir.is_dir():
                return builtin_dir
    except Exception:
        pass

    return None


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
