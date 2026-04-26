# -*- coding: utf-8 -*-
"""
上下文收集模块
"""

from pathlib import Path
from typing import Any
from typing import Dict
from typing import List

from jarvis.jarvis_c2rust.models import FnRecord


class ContextCollector:
    """上下文收集器"""

    def __init__(
        self,
        project_root: Path,
        fn_index_by_id: Dict[int, FnRecord],
        fn_name_to_id: Dict[str, int],
        symbol_map: Any,  # _SymbolMapJsonl
    ) -> None:
        self.project_root = project_root
        self.fn_index_by_id = fn_index_by_id
        self.fn_name_to_id = fn_name_to_id
        self.symbol_map = symbol_map

    def read_source_span(self, rec: FnRecord) -> str:
        """按起止行读取源码片段（忽略列边界，尽量完整）"""
        try:
            p = Path(rec.file)
            if not p.is_absolute():
                p = (self.project_root / p).resolve()
            if not p.exists():
                return ""
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            s = max(1, int(rec.start_line or 1))
            e = min(len(lines), max(int(rec.end_line or s), s))
            chunk = "\n".join(lines[s - 1 : e])
            return chunk
        except Exception:
            return ""

    def collect_callees_context(self, rec: FnRecord) -> List[Dict[str, Any]]:
        """
        生成被引用符号上下文列表（不区分函数与类型）：
        - 若已转译：提供 {name, qname, translated: true, rust_module, rust_symbol, ambiguous?}
        - 若未转译但存在扫描记录：提供 {name, qname, translated: false, file, start_line, end_line}
        - 若仅名称：提供 {name, qname, translated: false}
        注：若存在同名映射多条记录（重载/同名符号），此处标记 ambiguous=true，并选择最近一条作为提示。
        """
        ctx: List[Dict[str, Any]] = []
        for callee in rec.refs or []:
            entry: Dict[str, Any] = {"name": callee, "qname": callee}
            # 已转译映射
            if self.symbol_map.has_symbol(callee):
                recs = self.symbol_map.get(callee)
                m = recs[-1] if recs else None
                entry.update(
                    {
                        "translated": True,
                        "rust_module": (m or {}).get("module"),
                        "rust_symbol": (m or {}).get("rust_symbol"),
                    }
                )
                if len(recs) > 1:
                    entry["ambiguous"] = True
                ctx.append(entry)
                continue
            # 使用 order 索引按名称解析ID（函数或类型）
            cid = self.fn_name_to_id.get(callee)
            if cid:
                crec = self.fn_index_by_id.get(cid)
                if crec:
                    entry.update(
                        {
                            "translated": False,
                            "file": crec.file,
                            "start_line": crec.start_line,
                            "end_line": crec.end_line,
                        }
                    )
            else:
                entry.update({"translated": False})
            ctx.append(entry)
        return ctx

    def untranslated_callee_symbols(self, rec: FnRecord) -> List[str]:
        """
        返回尚未转换的被调函数符号（使用扫描记录中的名称/限定名作为键）
        """
        syms: List[str] = []
        for callee in rec.refs or []:
            if not self.symbol_map.has_symbol(callee):
                syms.append(callee)
        # 去重
        try:
            syms = list(dict.fromkeys(syms))
        except Exception:
            syms = sorted(list(set(syms)))
        return syms

    def append_additional_notes(self, prompt: str, additional_notes: str) -> str:
        """
        在提示词末尾追加附加说明（如果存在）。

        Args:
            prompt: 原始提示词
            additional_notes: 附加说明

        Returns:
            追加了附加说明的提示词
        """
        if additional_notes and additional_notes.strip():
            return (
                prompt
                + "\n\n"
                + "【附加说明（用户自定义）】\n"
                + additional_notes.strip()
            )
        return prompt
