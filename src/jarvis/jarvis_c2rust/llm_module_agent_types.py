# -*- coding: utf-8 -*-
"""LLM 模块规划 Agent 的数据类型和工具函数。"""

from dataclasses import dataclass
from typing import List


@dataclass
class FnMeta:
    """函数元数据。"""

    id: int
    name: str
    qname: str
    signature: str
    file: str
    refs: List[str]

    @property
    def label(self) -> str:
        """返回函数的标签（用于显示）。"""
        base = self.qname or self.name or f"fn_{self.id}"
        if self.signature and self.signature != base:
            return f"{base}\n{self.signature}"
        return base

    @property
    def top_namespace(self) -> str:
        """
        提取顶层命名空间/类名:
        - qualified_name 形如 ns1::ns2::Class::method -> 返回 ns1
        - C 函数或无命名空间 -> 返回 "c"
        """
        if self.qname and "::" in self.qname:
            return self.qname.split("::", 1)[0] or "c"
        return "c"


def sanitize_mod_name(s: str) -> str:
    """
    清理模块名称，使其符合 Rust 模块命名规范。

    Args:
        s: 原始名称

    Returns:
        清理后的模块名称
    """
    s = (s or "").replace("::", "__")
    safe = []
    for ch in s:
        if ch.isalnum() or ch == "_":
            safe.append(ch.lower())
        else:
            safe.append("_")
    out = "".join(safe).strip("_")
    return out[:80] or "mod"
