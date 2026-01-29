# -*- coding: utf-8 -*-
"""测试辅助函数"""

import os
import tempfile
from pathlib import Path
from typing import Any, Dict


def create_temp_file(content: str, suffix: str = ".py") -> Path:
    """创建临时文件"""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return Path(path)


def create_temp_directory() -> Path:
    """创建临时目录"""
    return Path(tempfile.mkdtemp())


def assert_dict_contains(subset: Dict[str, Any], superset: Dict[str, Any]) -> None:
    """断言字典包含子集"""
    for key, value in subset.items():
        assert key in superset, f"Key '{key}' not found in superset"
        assert superset[key] == value, (
            f"Value mismatch for key '{key}': expected {value}, got {superset[key]}"
        )
