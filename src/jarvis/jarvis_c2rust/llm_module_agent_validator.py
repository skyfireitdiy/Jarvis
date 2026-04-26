# -*- coding: utf-8 -*-
"""LLM 模块规划 Agent 的验证器。"""

import re
from typing import Any
from typing import Callable
from typing import List
from typing import Optional
from typing import Tuple


class ProjectValidator:
    """项目结构验证器。"""

    def __init__(
        self,
        crate_name_func: Callable[[], str],
        has_original_main_func: Callable[[], bool],
    ):
        self.crate_name_func = crate_name_func
        self.has_original_main_func = has_original_main_func

    def extract_json_from_project(self, text: str) -> str:
        """
        从 <PROJECT> 块中提取内容作为最终 JSON；若未匹配，返回原文本（兜底）。

        Args:
            text: 包含 <PROJECT> 块的文本

        Returns:
            提取的 JSON 文本
        """
        if not isinstance(text, str) or not text:
            return ""
        m_proj = re.search(r"<PROJECT>([\s\S]*?)</PROJECT>", text, flags=re.IGNORECASE)
        if m_proj:
            return m_proj.group(1).strip()
        return text.strip()

    def validate_project_entries(self, entries: List[Any]) -> Tuple[bool, str]:
        """
        校验目录结构是否满足强约束：
        - 必须存在 src/lib.rs
        - 若原始项目包含 main：
          * 不允许 src/main.rs
          * 必须包含 src/bin/<crate_name>.rs
        - 若原始项目不包含 main：
          * 不允许 src/main.rs
          * 不允许存在 src/bin/ 目录
        返回 (是否通过, 错误原因)
        """
        if not isinstance(entries, list) or not entries:
            return False, "JSON 不可解析或为空数组"

        # 提取 src 目录子项
        src_children: Optional[List[Any]] = None
        for it in entries:
            if isinstance(it, dict) and len(it) == 1:
                k, v = next(iter(it.items()))
                kk = str(k).rstrip("/").strip().lower()
                if kk == "src":
                    if isinstance(v, list):
                        src_children = v
                    else:
                        src_children = []
                    break
        if src_children is None:
            return False, "缺少 src 目录"

        # 建立便捷索引
        def has_file(name: str) -> bool:
            for ch in src_children or []:
                if isinstance(ch, str) and ch.strip().lower() == name.lower():
                    return True
            return False

        def find_dir(name: str) -> Optional[List[Any]]:
            for ch in src_children or []:
                if isinstance(ch, dict) and len(ch) == 1:
                    k, v = next(iter(ch.items()))
                    kk = str(k).rstrip("/").strip().lower()
                    if kk == name.lower():
                        return v if isinstance(v, list) else []
            return None

        # 1) 必须包含 lib.rs
        if not has_file("lib.rs"):
            return False, "src 目录下必须包含 lib.rs"

        has_main = self.has_original_main_func()
        crate_name = self.crate_name_func()

        # 2) 入口约束
        if has_main:
            # 不允许 src/main.rs
            if has_file("main.rs"):
                return (
                    False,
                    "原始项目包含 main：不应生成 src/main.rs，请使用 src/bin/<crate>.rs",
                )
            # 必须包含 src/bin/<crate_name>.rs
            bin_children = find_dir("bin")
            if bin_children is None:
                return False, f"原始项目包含 main：必须包含 src/bin/{crate_name}.rs"
            expect_bin = f"{crate_name}.rs".lower()
            if not any(
                isinstance(ch, str) and ch.strip().lower() == expect_bin
                for ch in bin_children
            ):
                return False, f"原始项目包含 main：必须包含 src/bin/{crate_name}.rs"
        else:
            # 不允许 src/main.rs
            if has_file("main.rs"):
                return False, "原始项目不包含 main：不应生成 src/main.rs"
            # 不允许有 bin 目录
            if find_dir("bin") is not None:
                return False, "原始项目不包含 main：不应生成 src/bin/ 目录"

        return True, ""
