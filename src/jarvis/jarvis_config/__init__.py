# -*- coding: utf-8 -*-
"""
Jarvis 配置工具模块

基于 JSON Schema 动态生成配置 Web 页面的工具。
提供 CLI 命令行接口和 Web 服务。
"""

from .cli import app

__all__ = ["app"]
__version__ = "1.0.0"
