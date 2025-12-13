# -*- coding: utf-8 -*-
"""
C2Rust 转译器数据模型
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Dict
from typing import List
from typing import Optional


@dataclass
class FnRecord:
    id: int
    name: str
    qname: str
    file: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    refs: List[str]
    # 额外元信息（来自 symbols/items）：函数签名、返回类型与参数（可选）
    signature: str = ""
    return_type: str = ""
    params: Optional[List[Dict[str, str]]] = None
    # 来自库替代阶段的上下文元数据（若存在）
    lib_replacement: Optional[Dict[str, Any]] = None
