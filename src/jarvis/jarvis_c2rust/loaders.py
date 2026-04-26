# -*- coding: utf-8 -*-
"""
C2Rust 转译器数据加载器
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_c2rust.constants import C2RUST_DIRNAME
from jarvis.jarvis_c2rust.constants import SYMBOLS_JSONL
from jarvis.jarvis_c2rust.models import FnRecord


class _DbLoader:
    """读取 symbols.jsonl 并提供按 id/name 查询与源码片段读取"""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.data_dir = self.project_root / C2RUST_DIRNAME

        self.symbols_path = self.data_dir / SYMBOLS_JSONL
        # 统一流程：仅使用 symbols.jsonl，不再兼容 functions.jsonl
        if not self.symbols_path.exists():
            raise FileNotFoundError(f"在目录下未找到 symbols.jsonl: {self.data_dir}")

        self.fn_by_id: Dict[int, FnRecord] = {}
        self.name_to_id: Dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        """
        读取统一的 symbols.jsonl。
        不区分函数与类型定义，均加载为通用记录（位置与引用信息）。
        """

        def _iter_records_from_file(path: Path) -> Any:
            try:
                with path.open("r", encoding="utf-8") as f:
                    idx = 0
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        idx += 1
                        yield idx, obj
            except FileNotFoundError:
                return

        # 加载所有符号记录（函数、类型等）
        for idx, obj in _iter_records_from_file(self.symbols_path):
            fid = int(obj.get("id") or idx)
            nm = obj.get("name") or ""
            qn = obj.get("qualified_name") or ""
            fp = obj.get("file") or ""
            refs = obj.get("ref")
            # 统一使用列表类型的引用字段
            if not isinstance(refs, list):
                refs = []
            refs = [c for c in refs if isinstance(c, str) and c]
            sr = int(obj.get("start_line") or 0)
            sc = int(obj.get("start_col") or 0)
            er = int(obj.get("end_line") or 0)
            ec = int(obj.get("end_col") or 0)
            lr = (
                obj.get("lib_replacement")
                if isinstance(obj.get("lib_replacement"), dict)
                else None
            )
            rec = FnRecord(
                id=fid,
                name=nm,
                qname=qn,
                file=fp,
                start_line=sr,
                start_col=sc,
                end_line=er,
                end_col=ec,
                refs=refs,
                lib_replacement=lr,
            )
            self.fn_by_id[fid] = rec
            if nm:
                self.name_to_id.setdefault(nm, fid)
            if qn:
                self.name_to_id.setdefault(qn, fid)

    def get(self, fid: int) -> Optional[FnRecord]:
        return self.fn_by_id.get(fid)

    def get_id_by_name(self, name_or_qname: str) -> Optional[int]:
        return self.name_to_id.get(name_or_qname)

    def read_source_span(self, rec: FnRecord) -> str:
        """按起止行读取源码片段（忽略列边界，尽量完整）"""
        try:
            p = Path(rec.file)
            # 若记录为相对路径，基于 project_root 解析
            if not p.is_absolute():
                p = (self.project_root / p).resolve()
            if not p.exists():
                return ""
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            s = max(1, rec.start_line)
            e = min(len(lines), max(rec.end_line, s))
            # Python 索引从0开始，包含终止行
            chunk = "\n".join(lines[s - 1 : e])
            return chunk
        except Exception:
            return ""


class _SymbolMapJsonl:
    """
    JSONL 形式的符号映射管理：
    - 每行一条记录，支持同名函数的多条映射（用于处理重载/同名符号）
    - 记录字段：
      {
        "c_name": "<简单名>",
        "c_qname": "<限定名，可为空字符串>",
        "c_file": "<源文件路径>",
        "start_line": <int>,
        "end_line": <int>,
        "module": "src/xxx.rs 或 src/xxx/mod.rs",
        "rust_symbol": "<Rust函数名>",
        "updated_at": "YYYY-MM-DDTHH:MM:SS"
      }
    - 提供按名称（c_name/c_qname）查询、按源位置判断是否已记录等能力
    """

    def __init__(self, jsonl_path: Path) -> None:
        self.jsonl_path = jsonl_path
        self.records: List[Dict[str, Any]] = []
        # 索引：名称 -> 记录列表索引
        self.by_key: Dict[str, List[int]] = {}
        # 唯一定位（避免同名冲突）：(c_file, start_line, end_line, c_qname or c_name) -> 记录索引列表
        self.by_pos: Dict[Tuple[str, int, int, str], List[int]] = {}
        self._load()

    def _load(self) -> None:
        self.records = []
        self.by_key = {}
        self.by_pos = {}
        # 读取 JSONL
        if self.jsonl_path.exists():
            try:
                with self.jsonl_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        self._add_record_in_memory(obj)
            except Exception:
                pass

    def _add_record_in_memory(self, rec: Dict[str, Any]) -> None:
        idx = len(self.records)
        self.records.append(rec)
        for key in [rec.get("c_name") or "", rec.get("c_qname") or ""]:
            k = str(key or "").strip()
            if not k:
                continue
            self.by_key.setdefault(k, []).append(idx)
        pos_key = (
            str(rec.get("c_file") or ""),
            int(rec.get("start_line") or 0),
            int(rec.get("end_line") or 0),
            str(rec.get("c_qname") or rec.get("c_name") or ""),
        )
        self.by_pos.setdefault(pos_key, []).append(idx)

    def has_symbol(self, sym: str) -> bool:
        return bool(self.by_key.get(sym))

    def get(self, sym: str) -> List[Dict[str, Any]]:
        idxs = self.by_key.get(sym) or []
        return [self.records[i] for i in idxs]

    def get_any(self, sym: str) -> Optional[Dict[str, Any]]:
        recs = self.get(sym)
        return recs[-1] if recs else None

    def has_rec(self, rec: FnRecord) -> bool:
        key = (
            str(rec.file or ""),
            int(rec.start_line or 0),
            int(rec.end_line or 0),
            str(rec.qname or rec.name or ""),
        )
        return bool(self.by_pos.get(key))

    def add(self, rec: FnRecord, module: str, rust_symbol: str) -> None:
        obj = {
            "c_name": rec.name or "",
            "c_qname": rec.qname or "",
            "c_file": rec.file or "",
            "start_line": int(rec.start_line or 0),
            "end_line": int(rec.end_line or 0),
            "module": str(module or ""),
            "rust_symbol": str(rust_symbol or (rec.name or f"fn_{rec.id}")),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        }
        # 先写盘，再更新内存索引
        try:
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with self.jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        except Exception:
            pass
        self._add_record_in_memory(obj)
