# -*- coding: utf-8 -*-
"""Jarvis Check - jck模块

用于检查系统工具的安装情况，提供友好的安装建议。
"""

from jarvis.jarvis_jck.core import ToolChecker
from jarvis.jarvis_jck.config import TOOLS_CONFIG

__all__ = ["ToolChecker", "TOOLS_CONFIG"]
