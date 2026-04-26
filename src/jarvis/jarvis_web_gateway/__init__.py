# -*- coding: utf-8 -*-
"""Web Gateway 独立服务入口。"""

from .app import create_app
from .app import run

__all__ = ["create_app", "run"]
