# -*- coding: utf-8 -*-
"""
C2Rust 转译器模块

目标：
- 基于 scanner 生成的 translation_order.jsonl 顺序，逐个函数进行转译
- 为每个函数：
  1) 准备上下文：C 源码片段+位置信息、被调用符号（若已转译则提供Rust模块与符号，否则提供原C位置信息）、crate目录结构
  2) 创建“模块选择与签名Agent”：让其选择合适的Rust模块路径，并在summary输出函数签名
  3) 记录当前进度到 progress.json
  4) 基于上述信息与落盘位置，创建 CodeAgent 生成转译后的Rust函数
  5) 尝试 cargo build，如失败则携带错误上下文创建 CodeAgent 修复，直到构建通过或达到上限
  6) 创建代码审查Agent；若 summary 指出问题，则 CodeAgent 优化，直到 summary 表示无问题
  7) 标记函数已转译，并记录 C 符号 -> Rust 符号/模块映射到 symbol_map.jsonl（JSONL，每行一条映射，支持重复与重载）

说明：
- 本模块提供 run_transpile(...) 作为对外入口，后续在 cli.py 中挂载为子命令
- 尽量复用现有 Agent/CodeAgent 能力，保持最小侵入与稳定性
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Set

import typer

from jarvis.jarvis_c2rust.scanner import compute_translation_order_jsonl
from jarvis.jarvis_agent import Agent
from jarvis.jarvis_code_agent.code_agent import CodeAgent


# 数据文件常量
C2RUST_DIRNAME = ".jarvis/c2rust"

SYMBOLS_JSONL = "symbols.jsonl"
ORDER_JSONL = "translation_order.jsonl"
PROGRESS_JSON = "progress.json"
SYMBOL_MAP_JSONL = "symbol_map.jsonl"
# 兼容旧版：若存在 symbol_map.json 也尝试加载（只读）
LEGACY_SYMBOL_MAP_JSON = "symbol_map.json"


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


class _DbLoader:
    """读取 symbols.jsonl 并提供按 id/name 查询与源码片段读取"""

    def __init__(self, project_root: Union[str, Path]) -> None:
        self.project_root = Path(project_root).resolve()
        self.data_dir = self.project_root / C2RUST_DIRNAME

        self.symbols_path = self.data_dir / SYMBOLS_JSONL
        # 统一流程：仅使用 symbols.jsonl，不再兼容 functions.jsonl
        if not self.symbols_path.exists():
            raise FileNotFoundError(
                f"在目录下未找到 symbols.jsonl: {self.data_dir}"
            )

        self.fn_by_id: Dict[int, FnRecord] = {}
        self.name_to_id: Dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        """
        读取统一的 symbols.jsonl。
        不区分函数与类型定义，均加载为通用记录（位置与引用信息）。
        """
        def _iter_records_from_file(path: Path):
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
            lr = obj.get("lib_replacement") if isinstance(obj.get("lib_replacement"), dict) else None
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

    def __init__(self, jsonl_path: Path, legacy_json_path: Optional[Path] = None) -> None:
        self.jsonl_path = jsonl_path
        self.legacy_json_path = legacy_json_path
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
        # 兼容旧版 symbol_map.json（若存在则读入为“最后一条”）
        elif self.legacy_json_path and self.legacy_json_path.exists():
            try:
                legacy = json.loads(self.legacy_json_path.read_text(encoding="utf-8"))
                if isinstance(legacy, dict):
                    for k, v in legacy.items():
                        rec = {
                            "c_name": k,
                            "c_qname": k,
                            "c_file": "",
                            "start_line": 0,
                            "end_line": 0,
                            "module": v.get("module"),
                            "rust_symbol": v.get("rust_symbol"),
                            "updated_at": v.get("updated_at"),
                        }
                        self._add_record_in_memory(rec)
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
        pos_key = (str(rec.get("c_file") or ""), int(rec.get("start_line") or 0), int(rec.get("end_line") or 0), str(rec.get("c_qname") or rec.get("c_name") or ""))
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
        key = (str(rec.file or ""), int(rec.start_line or 0), int(rec.end_line or 0), str(rec.qname or rec.name or ""))
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


def _ensure_order_file(project_root: Path) -> Path:
    """确保 translation_order.jsonl 存在且包含有效步骤；仅基于 symbols.jsonl 生成，不使用任何回退。"""
    data_dir = project_root / C2RUST_DIRNAME
    order_path = data_dir / ORDER_JSONL
    typer.secho(f"[c2rust-transpiler][order] 目标顺序文件: {order_path}", fg=typer.colors.BLUE)

    def _has_steps(p: Path) -> bool:
        try:
            steps = _iter_order_steps(p)
            return bool(steps)
        except Exception:
            return False

    # 已存在则校验是否有步骤
    typer.secho(f"[c2rust-transpiler][order] 检查现有顺序文件有效性: {order_path}", fg=typer.colors.BLUE)
    if order_path.exists():
        if _has_steps(order_path):
            typer.secho(f"[c2rust-transpiler][order] 现有顺序文件有效，将使用 {order_path}", fg=typer.colors.GREEN)
            return order_path
        # 为空或不可读：基于标准路径重新计算（仅 symbols.jsonl）
        typer.secho("[c2rust-transpiler][order] 现有顺序文件为空/无效，正基于 symbols.jsonl 重新计算", fg=typer.colors.YELLOW)
        try:
            compute_translation_order_jsonl(data_dir, out_path=order_path)
        except Exception as e:
            raise RuntimeError(f"重新计算翻译顺序失败: {e}")
        return order_path

    # 不存在：按标准路径生成到固定文件名（仅 symbols.jsonl）
    try:
        compute_translation_order_jsonl(data_dir, out_path=order_path)
    except Exception as e:
        raise RuntimeError(f"计算翻译顺序失败: {e}")

    typer.secho(f"[c2rust-transpiler][order] 已生成顺序文件: {order_path} (exists={order_path.exists()})", fg=typer.colors.BLUE)
    if not order_path.exists():
        raise FileNotFoundError(f"计算后未找到 translation_order.jsonl: {order_path}")

    # 最终校验：若仍无有效步骤，直接报错并提示先执行 scan 或检查 symbols.jsonl
    if not _has_steps(order_path):
        raise RuntimeError("translation_order.jsonl 无有效步骤。请先执行 'jarvis-c2rust scan' 生成 symbols.jsonl 并重试。")

    return order_path

def _iter_order_steps(order_jsonl: Path) -> List[List[int]]:
    """
    读取翻译顺序（兼容新旧格式），返回按步骤的函数id序列列表。
    新格式：每行包含 "ids": [int, ...] 以及 "items": [完整符号对象,...]。
    不再兼容旧格式（不支持 "records"/"symbols" 键）。
    """
    # 旧格式已移除：不再需要基于 symbols.jsonl 的 name->id 映射

    steps: List[List[int]] = []
    with order_jsonl.open("r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except Exception:
                continue

            ids = obj.get("ids")
            if isinstance(ids, list) and ids:
                # 新格式：仅支持 ids
                try:
                    ids_int = [int(x) for x in ids if isinstance(x, (int, str)) and str(x).strip()]
                except Exception:
                    ids_int = []
                if ids_int:
                    steps.append(ids_int)
                continue
            # 不支持旧格式（无 ids 则跳过该行）
    return steps


def _dir_tree(root: Path) -> str:
    """格式化 crate 目录结构（过滤部分常见目录）"""
    lines: List[str] = []
    exclude = {".git", "target", ".jarvis"}
    if not root.exists():
        return ""
    for p in sorted(root.rglob("*")):
        if any(part in exclude for part in p.parts):
            continue
        rel = p.relative_to(root)
        depth = len(rel.parts) - 1
        indent = "  " * depth
        name = rel.name + ("/" if p.is_dir() else "")
        lines.append(f"{indent}- {name}")
    return "\n".join(lines)


def _default_crate_dir(project_root: Path) -> Path:
    """遵循 llm_module_agent 的默认crate目录选择：<parent>/<cwd.name>_rs（与当前目录同级）当传入为 '.' 时"""
    try:
        cwd = Path(".").resolve()
        if project_root.resolve() == cwd:
            return cwd.parent / f"{cwd.name}_rs"
        else:
            return project_root
    except Exception:
        return project_root


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path: Path, obj: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _extract_json_from_summary(text: str) -> Dict[str, Any]:
    """
    从 Agent summary 中提取结构化数据（仅支持 YAML）：
    - 仅在 <SUMMARY>...</SUMMARY> 块内查找；
    - 只接受 <yaml>...</yaml> 标签包裹的 YAML 对象；
    - 若未找到或解析失败，返回 {}。
    """
    if not isinstance(text, str) or not text.strip():
        return {}

    # 提取 <SUMMARY> 块
    m = re.search(r"<SUMMARY>([\s\S]*?)</SUMMARY>", text, flags=re.IGNORECASE)
    block = (m.group(1) if m else text).strip()

    # 仅解析 <yaml>...</yaml>
    mm = re.search(r"<yaml>([\s\S]*?)</yaml>", block, flags=re.IGNORECASE)
    raw_yaml = mm.group(1).strip() if mm else None
    if not raw_yaml:
        return {}

    try:
        import yaml  # type: ignore
        obj = yaml.safe_load(raw_yaml)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


class Transpiler:
    def __init__(
        self,
        project_root: Union[str, Path] = ".",
        crate_dir: Optional[Union[str, Path]] = None,
        llm_group: Optional[str] = None,
        max_retries: int = 0,
        resume: bool = True,
        only: Optional[List[str]] = None,  # 仅转译指定函数名（简单名或限定名）
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.data_dir = self.project_root / C2RUST_DIRNAME
        self.progress_path = self.data_dir / PROGRESS_JSON
        # JSONL 路径
        self.symbol_map_path = self.data_dir / SYMBOL_MAP_JSONL
        # 兼容旧版 JSON 字典格式
        self.legacy_symbol_map_path = self.data_dir / LEGACY_SYMBOL_MAP_JSON
        self.llm_group = llm_group
        self.max_retries = max_retries
        self.resume = resume
        self.only = set(only or [])
        typer.secho(f"[c2rust-transpiler][init] 初始化参数: project_root={self.project_root} crate_dir={Path(crate_dir) if crate_dir else _default_crate_dir(self.project_root)} llm_group={self.llm_group} max_retries={self.max_retries} resume={self.resume} only={sorted(list(self.only)) if self.only else []}", fg=typer.colors.BLUE)

        self.crate_dir = Path(crate_dir) if crate_dir else _default_crate_dir(self.project_root)
        # 使用自包含的 order.jsonl 记录构建索引，避免依赖 symbols.jsonl
        self.fn_index_by_id: Dict[int, FnRecord] = {}
        self.fn_name_to_id: Dict[str, int] = {}

        self.progress: Dict[str, Any] = _read_json(self.progress_path, {"current": None, "converted": []})
        # 使用 JSONL 存储的符号映射
        self.symbol_map = _SymbolMapJsonl(self.symbol_map_path, legacy_json_path=self.legacy_symbol_map_path)


    def _save_progress(self) -> None:
        _write_json(self.progress_path, self.progress)

    # JSONL 模式下不再整体写回 symbol_map；此方法保留占位（兼容旧调用），无操作
    def _save_symbol_map(self) -> None:
        return

    def _read_source_span(self, rec: FnRecord) -> str:
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

    def _load_order_index(self, order_jsonl: Path) -> None:
        """
        从自包含的 order.jsonl 中加载所有 records，建立：
        - fn_index_by_id: id -> FnRecord
        - fn_name_to_id: name/qname -> id
        若同一 id 多次出现，首次记录为准。
        """
        self.fn_index_by_id.clear()
        self.fn_name_to_id.clear()
        typer.secho(f"[c2rust-transpiler][index] 正在加载翻译顺序索引: {order_jsonl}", fg=typer.colors.BLUE)
        try:
            with order_jsonl.open("r", encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        obj = json.loads(ln)
                    except Exception:
                        continue
                    # 仅支持新格式：items
                    recs = obj.get("items")
                    if not isinstance(recs, list):
                        continue
                    for r in recs:
                        if not isinstance(r, dict):
                            continue
                        # 构建 FnRecord
                        try:
                            fid = int(r.get("id"))
                        except Exception:
                            continue
                        if fid in self.fn_index_by_id:
                            # 已收录
                            continue
                        nm = r.get("name") or ""
                        qn = r.get("qualified_name") or ""
                        fp = r.get("file") or ""
                        refs = r.get("ref")
                        if not isinstance(refs, list):
                            refs = []
                        refs = [c for c in refs if isinstance(c, str) and c]
                        sr = int(r.get("start_line") or 0)
                        sc = int(r.get("start_col") or 0)
                        er = int(r.get("end_line") or 0)
                        ec = int(r.get("end_col") or 0)
                        sg = r.get("signature") or ""
                        rt = r.get("return_type") or ""
                        pr = r.get("params") if isinstance(r.get("params"), list) else None
                        lr = r.get("lib_replacement") if isinstance(r.get("lib_replacement"), dict) else None
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
                            signature=str(sg or ""),
                            return_type=str(rt or ""),
                            params=pr,
                            lib_replacement=lr,
                        )
                        self.fn_index_by_id[fid] = rec
                        if nm:
                            self.fn_name_to_id.setdefault(nm, fid)
                        if qn:
                            self.fn_name_to_id.setdefault(qn, fid)
        except Exception:
            # 若索引构建失败，保持为空，后续流程将跳过
            pass
        typer.secho(f"[c2rust-transpiler][index] 索引构建完成: ids={len(self.fn_index_by_id)} names={len(self.fn_name_to_id)}", fg=typer.colors.BLUE)

    def _should_skip(self, rec: FnRecord) -> bool:
        # 如果 only 列表非空，则仅处理匹配者
        if self.only:
            if rec.name in self.only or rec.qname in self.only:
                pass
            else:
                return True
        # 已转译的跳过（按源位置与名称唯一性判断，避免同名不同位置的误判）
        if self.symbol_map.has_rec(rec):
            return True
        return False

    def _collect_callees_context(self, rec: FnRecord) -> List[Dict[str, Any]]:
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
                entry.update({
                    "translated": True,
                    "rust_module": (m or {}).get("module"),
                    "rust_symbol": (m or {}).get("rust_symbol"),
                })
                if len(recs) > 1:
                    entry["ambiguous"] = True
                ctx.append(entry)
                continue
            # 使用 order 索引按名称解析ID（函数或类型）
            cid = self.fn_name_to_id.get(callee)
            if cid:
                crec = self.fn_index_by_id.get(cid)
                if crec:
                    entry.update({
                        "translated": False,
                        "file": crec.file,
                        "start_line": crec.start_line,
                        "end_line": crec.end_line,
                    })
            else:
                entry.update({"translated": False})
            ctx.append(entry)
        return ctx

    def _untranslated_callee_symbols(self, rec: FnRecord) -> List[str]:
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

    def _build_module_selection_prompts(
        self,
        rec: FnRecord,
        c_code: str,
        callees_ctx: List[Dict[str, Any]],
        crate_tree: str,
    ) -> Tuple[str, str, str]:
        """
        返回 (system_prompt, user_prompt, summary_prompt)
        要求 summary 输出 YAML：
        {
          "module": "src/<path>.rs or module path (e.g., src/foo/mod.rs or src/foo/bar.rs)",
          "rust_signature": "pub fn ...",
          "notes": "optional"
        }
        """
        system_prompt = (
            "你是资深Rust工程师，擅长为C/C++函数选择合适的Rust模块位置并产出对应的Rust函数签名。\n"
            "目标：根据提供的C源码、调用者上下文与crate目录结构，为该函数选择合适的Rust模块文件并给出Rust函数签名（不实现）。\n"
            "原则：\n"
            "- 按功能内聚与依赖方向选择模块，避免循环依赖；\n"
            "- 模块路径必须落在 crate 的 src/ 下，优先放置到已存在的模块中；必要时可建议创建新的子模块文件；\n"
            "- 函数签名需尽量与 C 签名对齐：仅要求参数个数与顺序一致；类型可用合理占位，后续由实现阶段细化；\n"
            "- 仅输出必要信息，避免冗余解释。"
        )
        user_prompt = "\n".join([
            "请阅读以下上下文并准备总结：",
            f"- 函数标识: id={rec.id}, name={rec.name}, qualified={rec.qname}",
            f"- 源文件位置: {rec.file}:{rec.start_line}-{rec.end_line}",
            f"- crate 根目录路径: {self.crate_dir.resolve()}",
            "",
            "C函数源码片段：",
            "<C_SOURCE>",
            c_code,
            "</C_SOURCE>",
            "",
            "符号表签名与参数（只读参考）：",
            json.dumps({"signature": getattr(rec, "signature", ""), "params": getattr(rec, "params", None)}, ensure_ascii=False, indent=2),
            "",
            "被引用符号上下文（如已转译则包含Rust模块信息）：",
            json.dumps(callees_ctx, ensure_ascii=False, indent=2),
            "",
            "库替代上下文（若存在）：",
            json.dumps(getattr(rec, "lib_replacement", None), ensure_ascii=False, indent=2),
            "",
            "当前crate目录结构（部分）：",
            "<CRATE_TREE>",
            crate_tree,
            "</CRATE_TREE>",
            "",
            "为避免完整读取体积较大的符号表，你也可以使用工具 read_symbols 按需获取指定符号记录：",
            f"- 工具: read_symbols",
            "- 参数示例(YAML):",
            f"  symbols_file: \"{(self.data_dir / 'symbols.jsonl').resolve()}\"",
            "  symbols:",
            "    - 要读取的符号列表",
            "",
            "如果理解完毕，请进入总结阶段。",
        ])
        summary_prompt = (
            "请仅输出一个 <SUMMARY> 块，块内必须且只包含一个 <yaml>...</yaml>，不得包含其它内容。\n"
            "允许字段（YAML 对象）：\n"
            '- module: "<绝对路径>/src/xxx.rs 或 <绝对路径>/src/xxx/mod.rs；或相对路径 src/xxx.rs / src/xxx/mod.rs"\n'
            '- rust_signature: "pub fn xxx(...)->..."\n'
            '- notes: "可选说明（若有上下文缺失或风险点，请在此列出）"\n'
            "注意：\n"
            "- module 必须位于 crate 的 src/ 目录下，接受绝对路径或以 src/ 开头的相对路径；尽量选择已有文件；如需新建文件，给出合理路径；\n"
            "- rust_signature 应尽量与 C 签名对齐（仅要求参数个数与顺序一致，类型可用合理占位）；并包含可见性修饰与函数名（可先用占位类型）。\n"
            "请严格按以下格式输出：\n"
            "<SUMMARY><yaml>\nmodule: \"...\"\nrust_signature: \"...\"\nnotes: \"...\"\n</yaml></SUMMARY>"
        )
        return system_prompt, user_prompt, summary_prompt

    def _plan_module_and_signature(self, rec: FnRecord, c_code: str) -> Tuple[str, str]:
        """调用 Agent 选择模块与签名，返回 (module_path, rust_signature)，若格式不满足将自动重试直到满足"""
        crate_tree = _dir_tree(self.crate_dir)
        callees_ctx = self._collect_callees_context(rec)
        sys_p, usr_p, base_sum_p = self._build_module_selection_prompts(rec, c_code, callees_ctx, crate_tree)

        def _validate(meta: Any) -> Tuple[bool, str]:
            if not isinstance(meta, dict) or not meta:
                return False, "未解析到有效的 <SUMMARY><yaml> 对象"
            module = meta.get("module")
            rust_sig = meta.get("rust_signature")
            if not isinstance(module, str) or not module.strip():
                return False, "缺少必填字段 module"
            if not isinstance(rust_sig, str) or not rust_sig.strip():
                return False, "缺少必填字段 rust_signature"
            # 路径归一化与校验：容忍相对/简略路径，最终归一为 crate_dir 下的绝对路径
            try:
                raw = str(module).strip().replace("\\", "/")
                crate_root = self.crate_dir.resolve()
                mp: Path
                p = Path(raw)
                if p.is_absolute():
                    mp = p.resolve()
                else:
                    # 规范化相对路径：若不以 src/ 开头，自动补全为 src/<raw>
                    if raw.startswith("./"):
                        raw = raw[2:]
                    if not raw.startswith("src/"):
                        raw = f"src/{raw}"
                    mp = (crate_root / raw).resolve()
                # 必须位于 crate 根目录下
                _ = mp.relative_to(crate_root)
                # 必须位于 src/ 目录层级内
                rel = mp.relative_to(crate_root)
                parts = rel.parts
                if not parts or parts[0] != "src":
                    return False, "module 必须位于 crate 的 src/ 目录下"
                # 文件名后缀校验：必须是 .rs 或 mod.rs；禁止使用 src/main.rs 作为目标模块
                name = mp.name.lower()
                if not (name.endswith(".rs")):
                    return False, "module 必须指向以 .rs 结尾的文件（如 foo.rs 或 mod.rs）"
                if name == "main.rs":
                    return False, "禁止将 module 指向 src/main.rs，请选择库模块文件"
                # 将归一化后的绝对路径回写到 meta，避免后续流程二次解析歧义
                meta["module"] = str(mp)
            except Exception:
                return False, "module 路径不可解析或不在 crate/src 下"
            if not re.search(r"\bfn\s+[A-Za-z_][A-Za-z0-9_]*\s*\(", rust_sig):
                return False, "rust_signature 无效：未检测到 Rust 函数签名（fn 名称）"
            return True, ""

        def _retry_sum_prompt(reason: str) -> str:
            return (
                base_sum_p
                + "\n\n[格式校验失败，必须重试]\n"
                + f"- 失败原因：{reason}\n"
                + "- 仅输出一个 <SUMMARY> 块；块内仅包含单个 <yaml> 对象；\n"
                + '- YAML 对象必须包含字段：module（位于 src/ 下）、rust_signature（形如 "pub fn name(...)"）。\n'
            )

        attempt = 0
        last_reason = "未知错误"
        while True:
            attempt += 1
            sum_p = base_sum_p if attempt == 1 else _retry_sum_prompt(last_reason)

            agent = Agent(
                system_prompt=sys_p,
                name="C2Rust-Function-Planner",
                model_group=self.llm_group,
                summary_prompt=sum_p,
                need_summary=True,
                auto_complete=True,
                use_tools=["execute_script", "read_code", "retrieve_memory", "save_memory", "read_symbols"],
                plan=False,
                non_interactive=True,
                use_methodology=False,
                use_analysis=False,
                disable_file_edit=True,
            )
            prev_cwd = os.getcwd()
            try:
                os.chdir(str(self.crate_dir))
                summary = agent.run(usr_p)
            finally:
                os.chdir(prev_cwd)
            meta = _extract_json_from_summary(str(summary or ""))
            ok, reason = _validate(meta)
            if ok:
                module = str(meta.get("module") or "").strip()
                rust_sig = str(meta.get("rust_signature") or "").strip()
                typer.secho(f"[c2rust-transpiler][plan] 第 {attempt} 次尝试成功: 模块={module}, 签名={rust_sig}", fg=typer.colors.GREEN)
                return module, rust_sig
            else:
                typer.secho(f"[c2rust-transpiler][plan] 第 {attempt} 次尝试失败: {reason}", fg=typer.colors.YELLOW)
                last_reason = reason

    def _update_progress_current(self, rec: FnRecord, module: str, rust_sig: str) -> None:
        self.progress["current"] = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "id": rec.id,
            "name": rec.name,
            "qualified_name": rec.qname,
            "file": rec.file,
            "start_line": rec.start_line,
            "end_line": rec.end_line,
            "module": module,
            "rust_signature": rust_sig,
        }
        self._save_progress()

    def _infer_rust_signature_hint(self, rec: FnRecord) -> str:
        """
        根据 C 符号信息（signature/params/return_type）启发式给出 Rust 函数签名建议（仅签名字符串）。
        映射策略（保守、跨平台更稳）：
        - 整型优先 core::ffi c_* 类型（如 c_int/c_uint/c_long），float/double -> f32/f64，size_t -> usize
        - 指针：包含 '*' 视为指针；含 const 则 *const T，否则 *mut T；void* -> *mut std::ffi::c_void（const 则 *const）
        - char*：*mut/*const core::ffi::c_char
        - 参数名缺失则使用 argN
        仅为建议，不强制，供 LLM 参考与事后一致性校验。
        """
        try:
            def _base_ty(ct: str) -> str:
                s = (ct or "").strip()
                # 去掉 const/volatile 与多余空白
                s = s.replace("volatile", " ").replace("CONST", "const").replace("  ", " ")
                return s

            def _is_ptr(ct: str) -> bool:
                s = _base_ty(ct)
                return "*" in s or "[]" in s

            def _is_const(ct: str) -> bool:
                s = _base_ty(ct).lower()
                return "const" in s

            def _map_prim(s: str) -> str:
                t = s.lower().strip()
                # C/C++ 基本整型（使用 core::ffi 以跨平台规避宽度差异）
                if t in ("int", "signed int"):
                    return "core::ffi::c_int"
                if t in ("unsigned int", "uint"):
                    return "core::ffi::c_uint"
                if t in ("short", "short int", "signed short", "signed short int"):
                    return "core::ffi::c_short"
                if t in ("unsigned short", "unsigned short int"):
                    return "core::ffi::c_ushort"
                if t in ("long", "long int", "signed long", "signed long int"):
                    return "core::ffi::c_long"
                if t in ("unsigned long", "unsigned long int"):
                    return "core::ffi::c_ulong"
                if t in ("long long", "long long int", "signed long long"):
                    return "core::ffi::c_longlong"
                if t in ("unsigned long long", "unsigned long long int"):
                    return "core::ffi::c_ulonglong"
                # 字符类
                if t in ("char", "signed char"):
                    return "core::ffi::c_char"
                if t in ("unsigned char",):
                    return "u8"
                # 浮点
                if t in ("float",):
                    return "f32"
                if t in ("double",):
                    return "f64"
                # C/C++ 定宽与指针宽度类型
                if t in ("int8_t",):
                    return "i8"
                if t in ("uint8_t",):
                    return "u8"
                if t in ("int16_t",):
                    return "i16"
                if t in ("uint16_t",):
                    return "u16"
                if t in ("int32_t",):
                    return "i32"
                if t in ("uint32_t",):
                    return "u32"
                if t in ("int64_t",):
                    return "i64"
                if t in ("uint64_t",):
                    return "u64"
                if t in ("intptr_t",):
                    return "isize"
                if t in ("uintptr_t",):
                    return "usize"
                # 其他常见别名
                if t in ("size_t",):
                    return "usize"
                if t in ("ssize_t",):
                    return "isize"
                if t in ("bool", "_bool", "_bool_t", "boolean", "_bool32"):
                    return "bool"
                # 未知类型（结构体、typedef 等）原样返回，后续由指针包装逻辑处理
                return s  # 保留原样（结构体名等）

            def _map_type(ct: str, ptr: bool, is_const: bool) -> str:
                bs = _base_ty(ct)
                # 特例：void*
                if "void" in bs and ptr:
                    return "*const std::ffi::c_void" if is_const else "*mut std::ffi::c_void"
                # 特例：char*
                if "char" in bs and ptr:
                    return "*const core::ffi::c_char" if is_const else "*mut core::ffi::c_char"
                base = _map_prim(bs.replace("*", "").replace("const", "").strip())
                if ptr:
                    return f"*const {base}" if is_const else f"*mut {base}"
                return base

            name = rec.name or "func"
            # 参数映射
            params = rec.params or []
            args_rs = []
            for i, p in enumerate(params):
                pn = (p.get("name") or f"arg{i}").strip() if isinstance(p, dict) else f"arg{i}"
                ct = (p.get("type") or "").strip() if isinstance(p, dict) else ""
                ptr = _is_ptr(ct)
                cst = _is_const(ct)
                ty_rs = _map_type(ct, ptr, cst)
                args_rs.append(f"{pn}: {ty_rs}")
            args_s = ", ".join(args_rs)

            # 返回类型
            rt = getattr(rec, "return_type", "") or ""
            if not rt:
                ret_rs = ""
            else:
                # C 的 void 返回在 Rust 中无返回类型（省略 -> ...），仅当非指针时适用
                rts = rt.strip().lower()
                if ("void" in rts) and (not _is_ptr(rt)):
                    ret_rs = ""
                else:
                    prt = _is_ptr(rt)
                    pc = _is_const(rt)
                    ret_mapped = _map_type(rt, prt, pc)
                    ret_rs = f" -> {ret_mapped}" if ret_mapped else ""

            return f"pub fn {name}({args_s}){ret_rs}"
        except Exception:
            return ""

    def _check_signature_consistency(self, rust_sig: str, rec: FnRecord) -> List[str]:
        """
        基于 LLM 提供的 rust_sig 与 C 符号（params/return_type）进行轻量一致性检查：
        - 参数个数是否一致
        - 指针可变性（const -> *const / 非 const -> *mut）是否匹配（按位置比对）
        - 指针+长度参数组合的基本一致性（按位置对 param#i 与 param#i+1 进行启发式检查）
        返回问题列表（空列表表示通过）。
        """
        issues: List[str] = []
        try:
            # 提取 Rust 参数串
            m = re.search(r"\bfn\s+[A-Za-z_][A-Za-z0-9_]*\s*\((.*?)\)", rust_sig or "", flags=re.S)
            rs_inside = m.group(1) if m else ""
            # 朴素切分（足够用于一致性检查；复杂泛型暂不处理）
            rs_params = [x.strip() for x in rs_inside.split(",") if x.strip()] if rs_inside else []
            c_params = rec.params or []
            if len(rs_params) != len(c_params):
                issues.append(f"[sig] parameter count mismatch: rust={len(rs_params)} vs c={len(c_params)}")
            # 指针可变性检查（对齐位置）
            def _rust_ptr_kind(s: str) -> Optional[str]:
                ss = s.replace(" ", "")
                if "*const" in ss:
                    return "const"
                if "*mut" in ss:
                    return "mut"
                return None
            for i, cp in enumerate(c_params):
                if i >= len(rs_params):
                    break
                cty = (cp.get("type") or "").lower()
                is_ptr = ("*" in cty) or ("[]" in cty)
                if not is_ptr:
                    continue
                is_const = "const" in cty
                rk = _rust_ptr_kind(rs_params[i])
                if is_const and rk != "const":
                    issues.append(f"[sig] param#{i} pointer mutability: expected *const (from C 'const'), got {rk or 'none'}")
                if (not is_const) and rk != "mut":
                    issues.append(f"[sig] param#{i} pointer mutability: expected *mut (from C non-const), got {rk or 'none'}")
            # 指针+长度（ptr,len）组合启发式检查：当 C 形参 i 为指针且 i+1 为长度整型时
            def _is_c_len_type(t: str) -> bool:
                tt = (t or "").strip().lower()
                if not tt:
                    return False
                # 常见长度类型
                if any(x in tt for x in ("size_t", "ssize_t", "uint32_t", "uint64_t", "int32_t", "int64_t")):
                    return True
                # 宽泛匹配 int/unsigned int
                if tt in ("int", "unsigned int", "uint", "unsigned"):
                    return True
                return False
            def _rs_is_pointer_or_slice(s: str) -> bool:
                ss = (s or "").replace(" ", "")
                return ("*const" in ss) or ("*mut" in ss) or ("&[" in ss) or ("Vec<" in ss)
            def _rs_is_integer_like(s: str) -> bool:
                ss = (s or "").strip()
                if not ss:
                    return False
                # 允许 usize/isize 与 i*/u* 定宽
                if re.search(r"\b(u|i)(8|16|32|64|128)\b", ss):
                    return True
                if re.search(r"\b(u|i)size\b", ss):
                    return True
                # 允许 core::ffi::c_* 基本整型
                if "core::ffi::c_" in ss:
                    return True
                return False
            for i in range(len(c_params) - 1):
                cty_i = (c_params[i].get("type") or "").lower() if isinstance(c_params[i], dict) else ""
                cty_j = (c_params[i+1].get("type") or "").lower() if isinstance(c_params[i+1], dict) else ""
                c_is_ptr = ("*" in cty_i) or ("[]" in cty_i)
                if not c_is_ptr:
                    continue
                if not _is_c_len_type(cty_j):
                    continue
                # 对应的 Rust 参数存在性
                if i >= len(rs_params) or (i + 1) >= len(rs_params):
                    issues.append(f"[sig] param#{i} pointer+len mismatch: expected pointer or slice with separate len (param#{i+1})")
                    continue
                rs_i = rs_params[i]
                rs_j = rs_params[i+1]
                if not _rs_is_pointer_or_slice(rs_i):
                    issues.append(f"[sig] param#{i} pointer+len mismatch: expected pointer or slice with separate len (param#{i+1})")
                if not _rs_is_integer_like(rs_j):
                    issues.append(f"[sig] param#{i+1} length param missing or non-integer")
            # 返回类型指针可变性（若存在）
            rt = (getattr(rec, "return_type", "") or "").lower()
            if rt:
                is_ptr = ("*" in rt) or ("[]" in rt)
                if is_ptr:
                    is_const = "const" in rt
                    mret = re.search(r"\)\s*->\s*([^{;]+)", rust_sig or "")
                    rty = mret.group(1).strip() if mret else ""
                    rk = _rust_ptr_kind(rty)
                    if is_const and rk != "const":
                        issues.append(f"[sig] return pointer mutability: expected *const (from C 'const'), got {rk or 'none'}")
                    if (not is_const) and rk != "mut":
                        issues.append(f"[sig] return pointer mutability: expected *mut (from C non-const), got {rk or 'none'}")
        except Exception:
            # 解析失败不阻塞，仅不产生问题
            return issues
        return issues
        return issues

    def _codeagent_generate_impl(self, rec: FnRecord, c_code: str, module: str, rust_sig: str, unresolved: List[str]) -> None:
        """
        使用 CodeAgent 生成/更新目标模块中的函数实现。
        约束：最小变更，生成可编译的占位实现，尽可能保留后续细化空间。
        """
        symbols_path = str((self.data_dir / "symbols.jsonl").resolve())
        requirement_lines = [
            f"目标：在 crate 目录 {self.crate_dir.resolve()} 的 {module} 中，为 C 函数 {rec.qname or rec.name} 生成对应的 Rust 实现。",
            "要求：",
            f"- 函数签名（建议）：{rust_sig}",
            "- 若 module 文件不存在则新建；为所在模块添加必要的 mod 声明（若需要）；",
            "- 若已有函数占位/实现，尽量最小修改，不要破坏现有代码；",
            "- 你可以参考原 C 函数的关联实现（如同文件/同模块的相关辅助函数、内联实现、宏与注释等），在保持语义一致的前提下以符合 Rust 风格的方式实现；避免机械复制粘贴；",
            "- 禁止在函数实现中使用 todo!/unimplemented! 作为占位；对于尚未实现的被调符号，请阅读其原始 C 实现并在本次一并补齐等价的 Rust 实现，避免遗留占位；",
            "- 为保证行为等价，禁止使用占位返回或随意默认值；必须实现与 C 语义等价的返回逻辑，不得使用 panic!/todo!/unimplemented!；",
            "- 不要删除或移动其他无关文件。",
            "",
            "编码原则与规范：",
            "- 保持最小变更，避免无关重构与格式化；禁止批量重排/重命名/移动文件；",
            "- 命名遵循Rust惯例（函数/模块蛇形命名），公共API使用pub；",
            "- 优先使用安全Rust；如需unsafe，将范围最小化并添加注释说明原因与SAFETY保证；",
            "- 错误处理：遵循 C 语义保持等价行为，不引入占位性的 Result/Option；避免 panic!/unwrap()；必要时使用与 C 等价的错误码/返回值或合理的 Rust 表达方式；",
            "- 实现中禁止使用 todo!/unimplemented! 占位；对于尚未实现的被调符号，应基于其 C 源码补齐等价 Rust 实现；",
            "- 返回值必须与 C 语义等价，不得使用占位返回或随意默认值；避免 panic!/todo!/unimplemented!；",
            "- 若依赖未实现符号，请通过 read_symbols/read_code 获取其 C 源码并生成等价的 Rust 实现（可放置在同一模块或合理模块），而不是使用 todo!；",
            "- 文档：为新增函数添加简要文档注释，注明来源C函数与意图；",
            "- 导入：禁止使用 use ...::* 通配；仅允许精确导入所需符号",
"- 测试生成：若函数可测试（无需外部环境/IO/网络/全局状态），在同文件添加 #[cfg(test)] mod tests 并编写至少一个可编译的单元测试（建议命名为 test_<函数名>_basic）；测试仅调用函数，避免使用 panic!/todo!/unimplemented!；unsafe 函数以 unsafe 调用；必要时使用占位参数（如 0、core::ptr::null()/null_mut()、默认值）以保证通过。",
"- 测试设计文档：在测试函数顶部使用文档注释（///）简要说明测试用例设计，包括：输入构造、预置条件、期望行为（或成功执行）、边界/异常不作为否决项；注释内容仅用于说明，不影响实现。",
"- 不可测试时：如函数依赖外部环境或调用未实现符号，暂不生成测试，但请在函数文档注释中注明不可测试原因（例如外部依赖/未实现符号）。",
            "- 指针+长度参数：如 C 存在 <ptr, len> 组合，请优先保持成对出现；若暂不清晰，至少保留长度参数占位",
            "- 风格：遵循 rustfmt 默认风格，避免引入与本次改动无关的大范围格式变化；",
            "- 输出限制：仅以补丁形式修改目标文件，不要输出解释或多余文本。",
            "",
            "C 源码片段（供参考，不要原样粘贴）：",
            "<C_SOURCE>",
            c_code,
            "</C_SOURCE>",
            "",
            "符号表签名与参数（只读参考）：",
            json.dumps({"signature": getattr(rec, "signature", ""), "params": getattr(rec, "params", None)}, ensure_ascii=False, indent=2),
            "",
            "注意：所有修改均以补丁方式进行。",
            "",
            "如对实现细节不确定：可以使用工具 read_symbols 按需获取指定符号记录：",
            f"- 工具: read_symbols",
            "- 参数示例(YAML):",
            f"  symbols_file: \"{symbols_path}\"",
            "  symbols:",
            "    - 要读取的符号列表",
            "",
            "尚未转换的被调符号如下（请阅读这些符号的 C 源码并生成等价的 Rust 实现；必要时新增模块或签名）：",
            *[f"- {s}" for s in (unresolved or [])],
        ]
        # 若存在库替代上下文，则附加到实现提示中，便于生成器参考（多库组合、参考API、备注等）
        librep_ctx = None
        try:
            librep_ctx = getattr(rec, "lib_replacement", None)
        except Exception:
            librep_ctx = None
        if isinstance(librep_ctx, dict) and librep_ctx:
            requirement_lines.extend([
                "",
                "库替代上下文（若存在）：",
                json.dumps(librep_ctx, ensure_ascii=False, indent=2),
                "",
            ])
        # 附加启发式签名建议（仅供参考）
        try:
            sig_hint = self._infer_rust_signature_hint(rec)
        except Exception:
            sig_hint = ""
        if sig_hint:
            requirement_lines.extend([
                "",
                "Rust 签名建议（启发式，仅供参考）：",
                sig_hint,
                "",
            ])
        prompt = "\n".join(requirement_lines)
        # 确保目标模块文件存在（提高补丁应用与实现落盘的确定性）
        try:
            mp = Path(module)
            if not mp.is_absolute():
                mp = (self.crate_dir / module).resolve()
            mp.parent.mkdir(parents=True, exist_ok=True)
            if not mp.exists():
                try:
                    mp.write_text("// Auto-created by c2rust transpiler\n", encoding="utf-8")
                    typer.secho(f"[c2rust-transpiler][gen] auto-created module file: {mp}", fg=typer.colors.GREEN)
                except Exception:
                    pass
        except Exception:
            pass
        # 切换到 crate 目录运行 CodeAgent，运行完毕后恢复
        prev_cwd = os.getcwd()
        try:
            os.chdir(str(self.crate_dir))
            agent = CodeAgent(need_summary=False, non_interactive=True, plan=False, model_group=self.llm_group)
            agent.run(prompt, prefix="[c2rust-transpiler][gen]", suffix="")
        finally:
            os.chdir(prev_cwd)

    def _extract_rust_fn_name_from_sig(self, rust_sig: str) -> str:
        """
        从 rust 签名中提取函数名，例如: 'pub fn foo(a: i32) -> i32 { ... }' -> 'foo'
        """
        m = re.search(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", rust_sig or "")
        return m.group(1) if m else ""

    def _ensure_impl_present(self, module: str, rust_sig: str) -> bool:
        """
        静态校验目标模块中是否已存在目标函数的实现；若缺失，触发一次最小修复的 CodeAgent。
        返回 True 表示存在或修复后存在；False 表示仍未找到（交由构建修复环节处理）。
        """
        try:
            fn = self._extract_rust_fn_name_from_sig(rust_sig)
            if not fn:
                # 没有函数名无法进行可靠校验，交给构建环节
                return True
            mp = Path(module)
            if not mp.is_absolute():
                mp = (self.crate_dir / module).resolve()
            if not mp.exists():
                typer.secho(f"[c2rust-transpiler][verify] 未找到模块文件: {mp}", fg=typer.colors.RED)
                return False
            txt = mp.read_text(encoding="utf-8", errors="replace")
            pattern = re.compile(r'(?m)^\s*(?:pub(?:\s*\([^)]+\))?\s+)?(?:async\s+)?(?:unsafe\s+)?(?:extern\s+"[^"]+"\s+)?fn\s+' + re.escape(fn) + r'\s*\([^)]*\)\s*(?:->\s*[^ {][^{]*)?\s*\{')
            if pattern.search(txt):
                typer.secho(f"[c2rust-transpiler][verify] 已在 {mp} 找到目标实现", fg=typer.colors.GREEN)
                return True
            # 触发一次最小修复，确保存在该函数实现
            prompt = "\n" .join([
                f"请在文件 {mp} 中确保存在函数实现：{rust_sig}",
                "要求：",
                "- 如文件不存在该函数定义，请新增实现（使用最小必要代码，避免 todo!/unimplemented!）；",
                "- 必须为带函数体的实现（签名后紧跟 '{'），不是仅声明或 extern 原型；",
                "- 不要删除或大改已有代码；仅补充缺失的函数实现或最小修正签名；",
                "- 如函数调用缺失/未实现的依赖，请阅读其 C 源码并在本次一并补齐等价的 Rust 实现；必要时在合理模块新增函数或引入精确 use；禁止使用 todo!/unimplemented! 作为占位；可使用 read_symbols/read_code 获取依赖符号的 C 源码与位置以辅助实现；",
                f"- crate 根目录：{self.crate_dir.resolve()}",
                "仅输出补丁。"
            ])
            prev_cwd = os.getcwd()
            try:
                os.chdir(str(self.crate_dir))
                agent = CodeAgent(need_summary=False, non_interactive=True, plan=False, model_group=self.llm_group)
                agent.run(prompt, prefix="[c2rust-transpiler][ensure-impl]", suffix="")
            finally:
                os.chdir(prev_cwd)
            # 再次检查
            txt2 = mp.read_text(encoding="utf-8", errors="replace")
            return bool(pattern.search(txt2))
        except Exception:
            return False

    def _ensure_top_level_pub_mod(self, mod_name: str) -> None:
        """
        在 src/lib.rs 中确保存在 `pub mod <mod_name>;`
        - 如已存在 `pub mod`，不做改动
        - 如存在 `mod <mod_name>;`，升级为 `pub mod <mod_name>;`
        - 如都不存在，则在文件末尾追加一行 `pub mod <mod_name>;`
        - 最小改动，不覆盖其他内容
        """
        try:
            if not mod_name or mod_name in ("lib", "main"):
                return
            lib_rs = (self.crate_dir / "src" / "lib.rs").resolve()
            lib_rs.parent.mkdir(parents=True, exist_ok=True)
            if not lib_rs.exists():
                try:
                    lib_rs.write_text("// Auto-generated by c2rust transpiler\n", encoding="utf-8")
                    typer.secho(f"[c2rust-transpiler][mod] 已创建 src/lib.rs: {lib_rs}", fg=typer.colors.GREEN)
                except Exception:
                    return
            txt = lib_rs.read_text(encoding="utf-8", errors="replace")
            pub_pat = re.compile(rf'(?m)^\s*pub\s+mod\s+{re.escape(mod_name)}\s*;\s*$')
            mod_pat = re.compile(rf'(?m)^\s*mod\s+{re.escape(mod_name)}\s*;\s*$')
            if pub_pat.search(txt):
                return
            if mod_pat.search(txt):
                # 升级为 pub mod（保留原缩进）
                def _repl(m):
                    line = m.group(0)
                    ws = re.match(r'^(\s*)', line).group(1) if re.match(r'^(\s*)', line) else ""
                    return f"{ws}pub mod {mod_name};"
                new_txt = mod_pat.sub(_repl, txt, count=1)
            else:
                new_txt = (txt.rstrip() + f"\npub mod {mod_name};\n")
            lib_rs.write_text(new_txt, encoding="utf-8")
            typer.secho(f"[c2rust-transpiler][mod] updated src/lib.rs: ensured pub mod {mod_name}", fg=typer.colors.GREEN)
        except Exception:
            # 保持稳健，失败不阻塞主流程
            pass

    def _ensure_mod_rs_decl(self, dir_path: Path, child_mod: str) -> None:
        """
        在 dir_path/mod.rs 中确保存在 `pub mod <child_mod>;`
        - 如存在 `mod <child_mod>;` 则升级为 `pub mod <child_mod>;`
        - 如均不存在则在文件末尾追加 `pub mod <child_mod>;`
        - 最小改动，不覆盖其他内容
        """
        try:
            if not child_mod or child_mod in ("lib", "main"):
                return
            mod_rs = (dir_path / "mod.rs").resolve()
            mod_rs.parent.mkdir(parents=True, exist_ok=True)
            if not mod_rs.exists():
                try:
                    mod_rs.write_text("// Auto-generated by c2rust transpiler\n", encoding="utf-8")
                    typer.secho(f"[c2rust-transpiler][mod] 已创建 {mod_rs}", fg=typer.colors.GREEN)
                except Exception:
                    return
            txt = mod_rs.read_text(encoding="utf-8", errors="replace")
            pub_pat = re.compile(rf'(?m)^\s*pub\s+mod\s+{re.escape(child_mod)}\s*;\s*$')
            mod_pat = re.compile(rf'(?m)^\s*mod\s+{re.escape(child_mod)}\s*;\s*$')
            if pub_pat.search(txt):
                return
            if mod_pat.search(txt):
                # 升级为 pub mod（保留原缩进）
                def _repl(m):
                    line = m.group(0)
                    ws = re.match(r'^(\s*)', line).group(1) if re.match(r'^(\s*)', line) else ""
                    return f"{ws}pub mod {child_mod};"
                new_txt = mod_pat.sub(_repl, txt, count=1)
            else:
                new_txt = (txt.rstrip() + f"\npub mod {child_mod};\n")
            mod_rs.write_text(new_txt, encoding="utf-8")
            typer.secho(f"[c2rust-transpiler][mod] updated {mod_rs}: ensured pub mod {child_mod}", fg=typer.colors.GREEN)
        except Exception:
            pass

    def _ensure_mod_chain_for_module(self, module: str) -> None:
        """
        根据目标模块文件，补齐从该文件所在目录向上的 mod.rs 声明链：
        - 对于 src/foo/bar.rs：在 src/foo/mod.rs 确保 `pub mod bar;`
          并在上层 src/mod.rs（不修改）改为在 src/lib.rs 确保 `pub mod foo;`（已由顶层函数处理）
        - 对于 src/foo/bar/mod.rs：在 src/foo/mod.rs 确保 `pub mod bar;`
        - 对多级目录，逐级在上层 mod.rs 确保对子目录的 `pub mod <child>;`
        """
        try:
            mp = Path(module)
            base = mp
            if not mp.is_absolute():
                base = (self.crate_dir / module).resolve()
            crate_root = self.crate_dir.resolve()
            # 必须在 crate/src 下
            rel = base.relative_to(crate_root)
            rel_s = str(rel).replace("\\", "/")
            if not rel_s.startswith("src/"):
                return
            # 计算起始目录与首个子模块名
            inside = rel_s[len("src/"):].strip("/")
            if not inside:
                return
            parts = inside.split("/")
            if parts[-1].endswith(".rs"):
                if parts[-1] in ("lib.rs", "main.rs"):
                    return
                child = parts[-1][:-3]  # 去掉 .rs
                start_dir = crate_root / "src" / "/".join(parts[:-1]) if len(parts) > 1 else (crate_root / "src")
                # 在当前目录的 mod.rs 确保 pub mod <child>
                if start_dir.name != "src":
                    self._ensure_mod_rs_decl(start_dir, child)
                # 向上逐级确保父目录对当前目录的 pub mod 声明
                cur_dir = start_dir
            else:
                # 末尾为目录（mod.rs 情况）：确保父目录对该目录 pub mod
                cur_dir = crate_root / "src" / "/".join(parts)
            # 逐级向上到 src 根（不修改 src/mod.rs，顶层由 lib.rs 公开）
            while True:
                parent = cur_dir.parent
                if not parent.exists():
                    break
                if parent.name == "src":
                    # 顶层由 _ensure_top_level_pub_mod 负责
                    break
                # 在 parent/mod.rs 确保 pub mod <cur_dir.name>
                self._ensure_mod_rs_decl(parent, cur_dir.name)
                cur_dir = parent
        except Exception:
            pass

    def _ensure_minimal_tests(self, module: str, rust_sig: str) -> None:
        """
        在目标模块文件中确保存在最小可编译的单元测试：
        - 在 #[cfg(test)] mod tests 中添加针对当前函数的 smoke 测试
        - 测试仅调用函数，不断言具体行为，以避免误判
        - 对 unsafe fn，调用包裹在 unsafe 块内
        """
        try:
            fn_name = self._extract_rust_fn_name_from_sig(rust_sig)
            typer.secho(f"[c2rust-transpiler][test] 确保最小单元测试: 模块={module}, 函数={fn_name or '(unknown)'}", fg=typer.colors.BLUE)
            if not fn_name:
                return
            mp = Path(module)
            if not mp.is_absolute():
                mp = (self.crate_dir / module).resolve()
            if not mp.exists():
                return
            text = mp.read_text(encoding="utf-8", errors="replace")

            # 简单检测是否已存在针对该函数的测试
            test_fn_pat = re.compile(rf"(?m)^\s*#\[test\]\s*fn\s+test_{re.escape(fn_name)}_basic\s*\(", re.IGNORECASE)
            if test_fn_pat.search(text):
                typer.secho(f"[c2rust-transpiler][test] 测试 test_{fn_name}_basic 已存在，跳过", fg=typer.colors.GREEN)
                return

            # 提取参数列表，生成占位入参
            m = re.search(r"\bfn\s+[A-Za-z_][A-Za-z0-9_]*\s*\((.*?)\)", rust_sig, flags=re.S)
            params_s = m.group(1) if m else ""
            params = []
            if params_s.strip():
                # 朴素按逗号切分 name: type
                parts = [x.strip() for x in params_s.split(",") if x.strip()]
                for p in parts:
                    mm = p.split(":")
                    if len(mm) >= 2:
                        ty = mm[1].strip()
                    else:
                        ty = ""
                    # 生成占位表达式
                    tys = ty.replace(" ", "")
                    if "*const" in tys:
                        expr = "core::ptr::null()"
                    elif "*mut" in tys:
                        expr = "core::ptr::null_mut()"
                    elif re.search(r"\b(f32|f64)\b", tys):
                        expr = "0.0"
                    elif re.search(r"\b(u|i)(8|16|32|64|128)\b", tys) or re.search(r"\b(u|i)size\b", tys) or ("core::ffi::c_" in tys):
                        expr = f"(0 as {ty})"
                    else:
                        expr = "unsafe { std::mem::zeroed() }"
                    params.append(expr)
            args = ", ".join(params)

            call_line = f"let _res = {fn_name}({args});" if args else f"let _res = {fn_name}();"
            if "unsafe" in rust_sig:
                call_line = "unsafe { " + call_line + " }"

            tests_block = "\n".join([
                "",
                "#[cfg(test)]",
                "mod tests {",
                "    use super::*;",
                "    /// 测试用例设计: 冒烟测试，使用占位参数调用目标函数；验证可编译并可正常运行，不校验具体业务逻辑。",
                "    /// 输入: 指针参数使用 core::ptr::null()/null_mut()，数值参数使用 0/0.0，其他类型使用默认值或 mem::zeroed。",
                "    /// 预置条件: 无外部环境/IO/网络依赖；不依赖未实现符号。",
                f"    /// 期望: {fn_name} 能正常调用且不发生 panic；若为 unsafe 函数，则在 unsafe 块内调用。",
                "    #[test]",
                f"    fn test_{fn_name}_basic() {{",
                f"        {call_line}",
                "    }",
                "}",
                "",
            ])

            # 若已存在 #[cfg(test)] mod tests，则追加测试函数；否则追加整个测试模块
            tests_mod_pat = re.compile(r"(?s)#\s*\[\s*cfg\s*\(\s*test\s*\)\s*\]\s*mod\s+tests\s*\{.*?\}")
            if tests_mod_pat.search(text):
                # 直接在文件末尾追加新的测试（避免复杂插入）
                new_text = text.rstrip() + tests_block
            else:
                new_text = text.rstrip() + tests_block

            mp.write_text(new_text, encoding="utf-8")
            typer.secho(f"[c2rust-transpiler][test] 已为 {fn_name} 写入最小测试到 {mp}", fg=typer.colors.GREEN)
        except Exception:
            # 测试生成失败不阻塞主流程
            pass

    def _module_file_to_crate_path(self, module: str) -> str:
        """
        将模块文件路径转换为 crate 路径前缀：
        - src/lib.rs -> crate
        - src/foo/mod.rs -> crate::foo
        - src/foo/bar.rs -> crate::foo::bar
        支持绝对路径：若 module 为绝对路径且位于 crate 根目录下，会自动转换为相对路径再解析；
        其它（无法解析为 crate/src 下的路径）统一返回 'crate'
        """
        mod = str(module).strip()
        # 若传入绝对路径且在 crate_dir 下，转换为相对路径以便后续按 src/ 前缀解析
        try:
            mp = Path(mod)
            if mp.is_absolute():
                try:
                    rel = mp.resolve().relative_to(self.crate_dir.resolve())
                    mod = str(rel).replace("\\", "/")
                except Exception:
                    # 绝对路径不在 crate_dir 下，保持原样
                    pass
        except Exception:
            pass
        # 规范化 ./ 前缀
        if mod.startswith("./"):
            mod = mod[2:]
        # 仅处理位于 src/ 下的模块文件
        if not mod.startswith("src/"):
            return "crate"
        p = mod[len("src/"):]
        if p.endswith("mod.rs"):
            p = p[: -len("mod.rs")]
        elif p.endswith(".rs"):
            p = p[: -len(".rs")]
        p = p.strip("/")
        return "crate" if not p else "crate::" + p.replace("/", "::")

    def _resolve_pending_todos_for_symbol(self, symbol: str, callee_module: str, callee_rust_fn: str, callee_rust_sig: str) -> None:
        """
        当某个 C 符号对应的函数已转换为 Rust 后：
        - 扫描整个 crate（优先 src/ 目录）中所有 .rs 文件，查找占位：todo!("符号名") 或 unimplemented!("符号名")
        - 对每个命中的文件，创建 CodeAgent 将占位替换为对已转换函数的真实调用（可使用 crate::... 完全限定路径或 use 引入）
        - 最小化修改，避免无关重构

        说明：不再使用 todos.json，本方法直接搜索源码中的 todo!("xxxx") / unimplemented!("xxxx")。
        """
        if not symbol:
            return

        # 计算被调函数的crate路径前缀，便于在提示中提供调用路径建议
        callee_path = self._module_file_to_crate_path(callee_module)

        # 扫描 src 下的 .rs 文件，查找 todo!("symbol") 或 unimplemented!("symbol") 占位
        matches: List[str] = []
        src_root = (self.crate_dir / "src").resolve()
        if src_root.exists():
            for p in sorted(src_root.rglob("*.rs")):
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                pat_todo = re.compile(r'todo\s*!\s*\(\s*["\']' + re.escape(symbol) + r'["\']\s*\)')
                pat_unimpl = re.compile(r'unimplemented\s*!\s*\(\s*["\']' + re.escape(symbol) + r'["\']\s*\)')
                if pat_todo.search(text) or pat_unimpl.search(text):
                    try:
                        # 记录绝对路径，避免依赖当前工作目录
                        abs_path = str(p.resolve())
                    except Exception:
                        abs_path = str(p)
                    matches.append(abs_path)

        if not matches:
            typer.secho(f"[c2rust-transpiler][todo] 未在 src/ 中找到 todo!(\"{symbol}\") 或 unimplemented!(\"{symbol}\") 的出现", fg=typer.colors.BLUE)
            return

        # 在当前工作目录运行 CodeAgent，不进入 crate 目录
        typer.secho(f"[c2rust-transpiler][todo] 发现 {len(matches)} 个包含 todo!(\"{symbol}\") 或 unimplemented!(\"{symbol}\") 的文件", fg=typer.colors.YELLOW)
        for target_file in matches:
            prompt = "\n".join([
                f"请在文件 {target_file} 中，定位所有以下占位并替换为对已转换函数的真实调用：",
                f"- todo!(\"{symbol}\")",
                f"- unimplemented!(\"{symbol}\")",
                "要求：",
                f"- 已转换的目标函数名：{callee_rust_fn}",
                f"- 其所在模块（crate路径提示）：{callee_path}",
                f"- 函数签名提示：{callee_rust_sig}",
                f"- 当前 crate 根目录路径：{self.crate_dir.resolve()}",
                "- 优先使用完全限定路径（如 crate::...::函数(...)）；如需在文件顶部添加 use，仅允许精确导入，不允许通配（例如 use ...::*）；",
                "- 保持最小改动，不要进行与本次修复无关的重构或格式化；",
                "- 如果参数列表暂不明确，可使用合理占位变量，确保编译通过。",
                "",
                f"仅修改 {target_file} 中与上述占位相关的代码，其他位置不要改动。",
                "请仅输出补丁，不要输出解释或多余文本。",
            ])
            prev_cwd = os.getcwd()
            try:
                os.chdir(str(self.crate_dir))
                agent = CodeAgent(need_summary=False, non_interactive=True, plan=False, model_group=self.llm_group)
                agent.run(prompt, prefix=f"[c2rust-transpiler][todo-fix:{symbol}]", suffix="")
            finally:
                os.chdir(prev_cwd)

    def _cargo_build_loop(self) -> bool:
        """在 crate 目录执行 cargo build，失败则使用 CodeAgent 最小化修复，直到通过或达到上限"""
        # 在 crate 目录进行构建与修复循环（切换到 crate 目录执行构建命令）
        workspace_root = str(self.crate_dir)
        typer.secho(f"[c2rust-transpiler][build] 工作区={workspace_root}，开始 cargo 测试循环", fg=typer.colors.MAGENTA)
        i = 0
        while True:
            i += 1
            res = subprocess.run(
                ["cargo", "test", "-q"],
                capture_output=True,
                text=True,
                check=False,
                cwd=workspace_root,
            )
            if res.returncode == 0:
                typer.secho("[c2rust-transpiler][build] Cargo 测试通过。", fg=typer.colors.GREEN)
                # 记录构建成功的度量与状态（用于准确性诊断与断点续跑）
                try:
                    cur = self.progress.get("current") or {}
                    metrics = cur.get("metrics") or {}
                    metrics["build_attempts"] = int(i)
                    cur["metrics"] = metrics
                    cur["impl_verified"] = True
                    self.progress["current"] = cur
                    self._save_progress()
                except Exception:
                    # 记录失败不影响主流程
                    pass
                return True
            output = (res.stdout or "") + "\n" + (res.stderr or "")
            typer.secho(f"[c2rust-transpiler][build] Cargo 测试失败 (第 {i} 次尝试)。", fg=typer.colors.RED)
            typer.secho(output, fg=typer.colors.RED)
            # 准确性改进：尊重 max_retries 参数，防止无限循环
            try:
                maxr = int(self.max_retries)
            except Exception:
                maxr = 0
            if maxr > 0 and i >= maxr:
                typer.secho(f"[c2rust-transpiler][build] 已达到最大重试次数上限({maxr})，停止构建修复循环。", fg=typer.colors.RED)
                # 记录失败度量与状态，便于后续准确性诊断与续跑
                try:
                    cur = self.progress.get("current") or {}
                    metrics = cur.get("metrics") or {}
                    metrics["build_attempts"] = int(i)
                    cur["metrics"] = metrics
                    cur["impl_verified"] = False
                    # 保存最近一次构建错误摘要（截断以避免超长）
                    try:
                        err_summary = (output or "").strip()
                        if len(err_summary) > 2000:
                            err_summary = err_summary[:2000] + "...(truncated)"
                        cur["last_build_error"] = err_summary
                    except Exception:
                        pass
                    self.progress["current"] = cur
                    self._save_progress()
                except Exception:
                    pass
                return False
            # 为修复 Agent 提供更多上下文：symbols.jsonl 索引指引 + 最近处理的C源码片段
            symbols_path = str((self.data_dir / "symbols.jsonl").resolve())
            try:
                curr = self.progress.get("current") or {}
            except Exception:
                curr = {}
            sym_name = str(curr.get("qualified_name") or curr.get("name") or "")
            src_loc = f"{curr.get('file')}:{curr.get('start_line')}-{curr.get('end_line')}" if curr else ""
            c_code = ""
            try:
                cf = curr.get("file")
                s = int(curr.get("start_line") or 0)
                e = int(curr.get("end_line") or 0)
                if cf and s:
                    p = Path(cf)
                    if not p.is_absolute():
                        p = (self.project_root / p).resolve()
                    if p.exists():
                        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                        s0 = max(1, s)
                        e0 = min(len(lines), max(e, s0))
                        c_code = "\n".join(lines[s0 - 1 : e0])
            except Exception:
                c_code = ""

            repair_prompt = "\n".join([
                "目标：以最小的改动修复问题，使 `cargo test` 命令可以通过。",
                "允许的修复：修正入口/模块声明/依赖；对入口文件与必要mod.rs进行轻微调整；在缺失/未实现的被调函数导致错误时，一并补齐这些依赖的Rust实现（可新增合理模块/函数）；避免大范围改动。",
                "- 保持最小改动，避免与错误无关的重构或格式化；",
                "- 如构建失败源于缺失或未实现的被调函数/依赖，请阅读其 C 源码并在本次一并补齐等价的 Rust 实现；必要时可在合理的模块中新建函数；",
                "- 禁止使用 todo!/unimplemented! 作为占位；",
                "- 可使用工具 read_symbols/read_code 获取依赖符号的 C 源码与位置以辅助实现；仅精确导入所需符号，避免通配；",
                "- 请仅输出补丁，不要输出解释或多余文本。",
                "",
                "最近处理的函数上下文（供参考，优先修复构建错误）：",
                f"- 函数：{sym_name}",
                f"- 源位置：{src_loc}",
                f"- 目标模块（progress）：{curr.get('module') or ''}",
                f"- 建议签名（progress）：{curr.get('rust_signature') or ''}",
                "",
                "原始C函数源码片段（只读参考）：",
                "<C_SOURCE>",
                c_code,
                "</C_SOURCE>",
                "",
                "如需定位或交叉验证 C 符号位置，请使用符号表检索工具：",
                "- 工具: read_symbols",
                "- 参数示例(YAML):",
                f"  symbols_file: \"{symbols_path}\"",
                "  symbols:",
                f"    - \"{sym_name}\"",
                "",
                "上下文：",
                f"- crate 根目录路径: {self.crate_dir.resolve()}",
                f"- 包名称（用于 cargo build -p）: {self.crate_dir.name}",
                "",
                "请阅读以下构建错误并进行必要修复：",
                "<BUILD_ERROR>",
                output,
                "</BUILD_ERROR>",
                "修复后请再次执行 `cargo test` 进行验证。",
            ])
            prev_cwd = os.getcwd()
            try:
                os.chdir(str(self.crate_dir))
                agent = CodeAgent(need_summary=False, non_interactive=True, plan=False, model_group=self.llm_group)
                agent.run(repair_prompt, prefix=f"[c2rust-transpiler][build-fix iter={i}]", suffix="")
            finally:
                os.chdir(prev_cwd)

    def _review_and_optimize(self, rec: FnRecord, module: str, rust_sig: str) -> None:
        """
        审查生成的实现；若 summary 报告问题，则调用 CodeAgent 进行优化，直到无问题或次数用尽。
        审查只关注本次函数与相关最小上下文，避免全局重构。
        """
        def build_review_prompts() -> Tuple[str, str, str]:
            sys_p = (
                "你是Rust代码审查专家。验收标准：Rust 实现必须与原始 C 实现等价，涵盖主路径与边界条件的功能与可观测副作用；允许非功能性差异（如日志、风格、错误信息表述）。"
                "关注点：检查核心输入输出、状态变化以及边界/异常路径的处理是否与 C 实现一致；资源释放/内存语义需等价（如指针有效性、长度边界等）。"
                "不考虑安全、性能、风格等其他方面。仅在总结阶段输出审查结论。"
                "请在总结阶段详细指出问题和修改建议，但不要尝试修复或修改任何代码，不要输出补丁。"
            )
            # 附加原始C函数源码片段，供审查作为只读参考
            c_code = self._read_source_span(rec) or ""
            # 附加被引用符号上下文与库替代上下文，以及crate目录结构，提供更完整审查背景
            callees_ctx = self._collect_callees_context(rec)
            librep_ctx = rec.lib_replacement if isinstance(rec.lib_replacement, dict) else None
            crate_tree = _dir_tree(self.crate_dir)
            usr_p = "\n".join([
                f"待审查函数：{rec.qname or rec.name}",
                f"建议签名：{rust_sig}",
                f"目标模块：{module}",
                f"crate根目录路径：{self.crate_dir.resolve()}",
                f"源文件位置：{rec.file}:{rec.start_line}-{rec.end_line}",
                "",
                "原始C函数源码片段（只读参考，不要修改C代码）：",
                "<C_SOURCE>",
                c_code,
                "</C_SOURCE>",
                "",
                "被引用符号上下文（如已转译则包含Rust模块信息）：",
                json.dumps(callees_ctx, ensure_ascii=False, indent=2),
                "",
                "库替代上下文（若存在）：",
                json.dumps(librep_ctx, ensure_ascii=False, indent=2),
                "",
                "当前crate目录结构（部分）：",
                "<CRATE_TREE>",
                crate_tree,
                "</CRATE_TREE>",
                "",
                "如需定位或交叉验证 C 符号位置，请使用符号表检索工具：",
                "- 工具: read_symbols",
                "- 参数示例(YAML):",
                f"  symbols_file: \"{(self.data_dir / 'symbols.jsonl').resolve()}\"",
                "  symbols:",
                f"    - \"{rec.qname or rec.name}\"",
                "",
                "请阅读crate中该函数的当前实现（你可以在上述crate根路径下自行读取必要上下文），并准备总结。",
            ])
            sum_p = (
                "请仅输出一个 <SUMMARY> 块，内容为纯文本：\n"
                "- 若满足“关键逻辑一致”，请输出：OK\n"
                "- 前置条件：必须在crate中找到该函数的实现（匹配函数名或签名）。若未找到，禁止输出OK，请输出一行：[logic] function not found\n"
                "- 否则请详细列出发现的问题和修改建议（每项问题以 [logic] 开头，后面紧跟修改建议）。\n"
                "<SUMMARY>...</SUMMARY>\n"
                "不要在 <SUMMARY> 块外输出任何内容。"
            )
            return sys_p, usr_p, sum_p

        i = 0
        while True:
            sys_p, usr_p, sum_p = build_review_prompts()
            agent = Agent(
                system_prompt=sys_p,
                name="C2Rust-Review-Agent",
                model_group=self.llm_group,
                summary_prompt=sum_p,
                need_summary=True,
                auto_complete=True,
                use_tools=["execute_script", "read_code", "retrieve_memory", "save_memory", "read_symbols"],
                plan=False,
                non_interactive=True,
                use_methodology=False,
                use_analysis=False,
                disable_file_edit=True,
            )
            prev_cwd = os.getcwd()
            try:
                os.chdir(str(self.crate_dir))
                summary = str(agent.run(usr_p) or "")
            finally:
                os.chdir(prev_cwd)
            m = re.search(r"<SUMMARY>([\s\S]*?)</SUMMARY>", summary, flags=re.IGNORECASE)
            content = (m.group(1).strip() if m else summary.strip()).upper()
            if content == "OK":
                typer.secho("[c2rust-transpiler][review] 代码审查通过。", fg=typer.colors.GREEN)
                # 二次审查：类型/边界一致性检查与最小化修复
                try:
                    self._type_boundary_review_and_fix(rec, module, rust_sig)
                except Exception:
                    pass
                return
            # 需要优化：提供详细上下文背景，并明确审查意见仅针对 Rust crate，不修改 C 源码
            crate_tree = _dir_tree(self.crate_dir)
            fix_prompt = "\n".join([
                "请根据以下审查结论对目标函数进行最小优化（保留结构与意图，不进行大范围重构）：",
                "<REVIEW>",
                content,
                "</REVIEW>",
                "",
                "上下文背景信息：",
                f"- crate_dir: {self.crate_dir.resolve()}",
                f"- 目标模块文件: {module}",
                f"- 建议/当前 Rust 签名: {rust_sig}",
                "crate 目录结构（部分）：",
                crate_tree,
                "",
                "约束与范围：",
                "- 本次审查意见仅针对 Rust crate 的代码与配置；不要修改任何 C/C++ 源文件（*.c、*.h 等）。",
                "- 仅允许在 crate_dir 下进行最小必要修改（Cargo.toml、src/**/*.rs）；不要改动其他目录。",
                "- 保持最小改动，避免与问题无关的重构或格式化。",
                "- 如审查问题涉及缺失/未实现的被调函数或依赖，请阅读其 C 源码并在本次一并补齐等价的 Rust 实现；必要时在合理模块新增函数或引入精确 use；",
                "- 禁止使用 todo!/unimplemented! 作为占位；",
                "- 可使用工具 read_symbols/read_code 获取依赖符号的 C 源码与位置以辅助实现；仅精确导入所需符号（禁止通配）；",
                "",
                "请仅以补丁形式输出修改，避免冗余解释。",
            ])
            # 在当前工作目录运行 CodeAgent，不进入 crate 目录
            ca = CodeAgent(need_summary=False, non_interactive=True, plan=False, model_group=self.llm_group)
            prev_cwd = os.getcwd()
            try:
                os.chdir(str(self.crate_dir))
                ca.run(fix_prompt, prefix=f"[c2rust-transpiler][review-fix iter={i}]", suffix="")
                # 优化后进行一次构建验证；若未通过则进入构建修复循环，直到通过为止
                self._cargo_build_loop()
            finally:
                os.chdir(prev_cwd)

    def _mark_converted(self, rec: FnRecord, module: str, rust_sig: str) -> None:
        """记录映射：C 符号 -> Rust 符号与模块路径（JSONL，每行一条，支持重载/同名）"""
        rust_symbol = ""
        # 从签名中提取函数名（简单启发：pub fn name(...)
        m = re.search(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", rust_sig)
        if m:
            rust_symbol = m.group(1)
        # 写入 JSONL 映射（带源位置，用于区分同名符号）
        self.symbol_map.add(rec, module, rust_symbol or (rec.name or f"fn_{rec.id}"))

        # 更新进度：已转换集合
        converted = self.progress.get("converted") or []
        if rec.id not in converted:
            converted.append(rec.id)
        self.progress["converted"] = converted
        self.progress["current"] = None
        self._save_progress()

    def _type_boundary_review_and_fix(self, rec: FnRecord, module: str, rust_sig: str) -> None:
        """
        第二阶段审查：类型/边界一致性（仅准确性相关的最小问题）
        - 关注点：指针可变性/空指针检查、长度/边界检查（若有切片或指针+长度语义）、显式的 unsafe 使用范围说明
        - 输出：要求 Agent 仅在 <SUMMARY> 中给出 YAML verdict；若 not ok，触发一次最小修复 CodeAgent
        """
        try:
            sys_p = (
                "你是Rust类型与边界检查专家。仅检查以下问题：\n"
                "1) 指针参数/返回值的可变性是否与语义匹配（C const* -> *const，非const -> *mut）。\n"
                "2) 对来自指针的读写是否进行了必要的空指针检查/长度边界检查（如有长度参数或可判断长度的场景）。\n"
                "3) 任何 unsafe 块必须最小化范围并以注释说明 SAFETY 理由（只需存在，内容无需冗长）。\n"
                "不考虑风格/性能/日志等其他问题。"
            )
            # 仅提供必要上下文；Agent 可自行读取 crate 内代码
            c_code = self._read_source_span(rec) or ""
            usr_p = "\n".join([
                f"目标函数：{rec.qname or rec.name}",
                f"建议/当前签名：{rust_sig}",
                f"模块文件：{module}",
                f"crate 根目录：{self.crate_dir.resolve()}",
                "",
                "原始C函数源码片段（只读参考，不要修改C代码）：",
                "<C_SOURCE>",
                c_code,
                "</C_SOURCE>",
                "",
                "若函数包含指针参数/返回值，请重点检查：可变性（*const/*mut）、空指针检查、必要时的边界检查。",
                "若使用 unsafe，请确认 unsafe 块范围最小并有注释说明 SAFETY（存在即可）。",
            ])
            sum_p = (
                "请仅输出一个 <SUMMARY> 块，块内为单个 <yaml> 对象，字段：\n"
                "ok: bool\n"
                "issues: [string, ...]  # 每条以 [type] 开头，示例：[type] param#0 missing null check\n"
                "<SUMMARY><yaml>\nok: true\nissues: []\n</yaml></SUMMARY>"
            )
            agent = Agent(
                system_prompt=sys_p,
                name="C2Rust-TypeBoundary-Review",
                model_group=self.llm_group,
                summary_prompt=sum_p,
                need_summary=True,
                auto_complete=True,
                use_tools=["execute_script", "read_code", "retrieve_memory", "save_memory"],
                plan=False,
                non_interactive=True,
                use_methodology=False,
                use_analysis=False,
                disable_file_edit=True,
            )
            prev_cwd = os.getcwd()
            try:
                os.chdir(str(self.crate_dir))
                review = str(agent.run(usr_p) or "")
            finally:
                os.chdir(prev_cwd)
            verdict = _extract_json_from_summary(review)
            if not isinstance(verdict, dict):
                return
            ok = bool(verdict.get("ok") is True)
            typer.secho(f"[c2rust-transpiler][type-review] verdict ok={ok}, issues={len(verdict.get('issues') or [])}", fg=typer.colors.CYAN)
            issues = verdict.get("issues") if isinstance(verdict.get("issues"), list) else []
            if ok or not issues:
                # 记录类型/边界审查结果到进度（通过或无问题）
                try:
                    cur = self.progress.get("current") or {}
                    cur["type_boundary_review"] = {"ok": True, "issues": []}
                    # 增加度量统计：类型/边界问题计数
                    metrics = cur.get("metrics") or {}
                    metrics["type_issues"] = 0
                    cur["metrics"] = metrics
                    self.progress["current"] = cur
                    self._save_progress()
                except Exception:
                    pass
                return
            # 记录类型/边界审查问题与度量后，再进行最小化修复
            typer.secho("[c2rust-transpiler][type-review] applying minimal fixes for type/boundary issues", fg=typer.colors.YELLOW)
            try:
                cur = self.progress.get("current") or {}
                cur["type_boundary_review"] = {"ok": False, "issues": list(issues)}
                metrics = cur.get("metrics") or {}
                metrics["type_issues"] = int(len(issues))
                cur["metrics"] = metrics
                self.progress["current"] = cur
                self._save_progress()
            except Exception:
                pass

            # 最小化修复提示
            fix_lines = [
                "请对目标函数进行最小必要的修复，仅限以下范围：",
                "- 指针可变性不匹配：修正签名中的 *const / *mut；",
                "- 缺少空指针检查：在解引用/读写前添加显式检查；",
                "- 必要的边界检查：仅在可确定长度或需要防止越界的直观场景添加；",
                "- 如涉及 unsafe：缩小 unsafe 块范围，并添加一条简短 SAFETY 注释说明；",
                "- 如修复涉及缺失/未实现的被调函数或依赖，请阅读其 C 源码并在本次一并补齐等价的 Rust 实现；必要时在合理模块新增函数或引入精确 use；禁止使用 todo!/unimplemented! 作为占位；可使用 read_symbols/read_code 获取依赖符号的 C 源码与位置以辅助实现；",
                "",
                f"模块文件：{module}",
                f"crate 根目录：{self.crate_dir.resolve()}",
                "问题列表：",
                *[str(x) for x in issues],
                "",
                "仅输出补丁，不要输出解释；保持变更最小化。",
            ]
            prev = os.getcwd()
            try:
                os.chdir(str(self.crate_dir))
                ca = CodeAgent(need_summary=False, non_interactive=True, plan=False, model_group=self.llm_group)
                ca.run("\n".join(fix_lines), prefix="[c2rust-transpiler][type-boundary-fix]", suffix="")
            finally:
                os.chdir(prev)
        except Exception:
            # 二次审查失败不阻塞主流程
            pass

    def transpile(self) -> None:
        """主流程"""
        typer.secho("[c2rust-transpiler][start] 开始转译", fg=typer.colors.BLUE)
        # 准确性兜底：在未执行 prepare 的情况下，确保 crate 目录与最小 Cargo 配置存在
        try:
            cd = self.crate_dir.resolve()
            cd.mkdir(parents=True, exist_ok=True)
            cargo = cd / "Cargo.toml"
            src_dir = cd / "src"
            lib_rs = src_dir / "lib.rs"
            # 最小 Cargo.toml（不覆盖已有），edition 使用 2021 以兼容更广环境
            if not cargo.exists():
                pkg_name = cd.name
                content = (
                    f'[package]\nname = "{pkg_name}"\nversion = "0.1.0"\nedition = "2021"\n\n'
                    '[lib]\npath = "src/lib.rs"\n'
                )
                try:
                    cargo.write_text(content, encoding="utf-8")
                    typer.secho(f"[c2rust-transpiler][init] created Cargo.toml at {cargo}", fg=typer.colors.GREEN)
                except Exception:
                    pass
            # 确保 src/lib.rs 存在
            src_dir.mkdir(parents=True, exist_ok=True)
            if not lib_rs.exists():
                try:
                    lib_rs.write_text("// Auto-created by c2rust transpiler\n", encoding="utf-8")
                    typer.secho(f"[c2rust-transpiler][init] created src/lib.rs at {lib_rs}", fg=typer.colors.GREEN)
                except Exception:
                    pass
        except Exception:
            # 保持稳健，失败不阻塞主流程
            pass

        order_path = _ensure_order_file(self.project_root)
        steps = _iter_order_steps(order_path)
        if not steps:
            typer.secho("[c2rust-transpiler] 未找到翻译步骤。", fg=typer.colors.YELLOW)
            return

        # 构建自包含 order 索引（id -> FnRecord，name/qname -> id）
        self._load_order_index(order_path)

        # 扁平化顺序，按单个函数处理（保持原有顺序）
        seq: List[int] = []
        for grp in steps:
            seq.extend(grp)

        # 若支持 resume，则跳过 progress['converted'] 中已完成的
        done: Set[int] = set(self.progress.get("converted") or [])
        typer.secho(f"[c2rust-transpiler][order] 顺序信息: 步骤数={len(steps)} 总ID={sum(len(g) for g in steps)} 已转换={len(done)}", fg=typer.colors.BLUE)

        for fid in seq:
            if fid in done:
                continue
            rec = self.fn_index_by_id.get(fid)
            if not rec:
                continue
            if self._should_skip(rec):
                typer.secho(f"[c2rust-transpiler][skip] 跳过 {rec.qname or rec.name} (id={rec.id}) 位于 {rec.file}:{rec.start_line}-{rec.end_line}", fg=typer.colors.YELLOW)
                continue

            # 读取C函数源码
            typer.secho(f"[c2rust-transpiler][read] 读取 C 源码: {rec.qname or rec.name} (id={rec.id}) 来自 {rec.file}:{rec.start_line}-{rec.end_line}", fg=typer.colors.BLUE)
            c_code = self._read_source_span(rec)
            typer.secho(f"[c2rust-transpiler][read] 已加载 {len(c_code.splitlines()) if c_code else 0} 行", fg=typer.colors.BLUE)

            # 若缺少源码片段且缺乏签名/参数信息，则跳过本函数，记录进度以便后续处理
            if not c_code and not (getattr(rec, "signature", "") or getattr(rec, "params", None)):
                skipped = self.progress.get("skipped_missing_source") or []
                if rec.id not in skipped:
                    skipped.append(rec.id)
                self.progress["skipped_missing_source"] = skipped
                typer.secho(f"[c2rust-transpiler] 跳过：缺少源码与签名信息 -> {rec.qname or rec.name} (id={rec.id})", fg=typer.colors.YELLOW)
                self._save_progress()
                continue
            # 1) 规划：模块路径与Rust签名
            typer.secho(f"[c2rust-transpiler][plan] 正在规划模块与签名: {rec.qname or rec.name} (id={rec.id})", fg=typer.colors.CYAN)
            module, rust_sig = self._plan_module_and_signature(rec, c_code)
            typer.secho(f"[c2rust-transpiler][plan] 已选择 模块={module}, 签名={rust_sig}", fg=typer.colors.CYAN)

            # 记录当前进度
            self._update_progress_current(rec, module, rust_sig)
            typer.secho(f"[c2rust-transpiler][progress] 已更新当前进度记录 id={rec.id}", fg=typer.colors.CYAN)
            # 记录启发式签名建议，便于诊断与后续续跑
            try:
                hint = self._infer_rust_signature_hint(rec)
                cur = self.progress.get("current") or {}
                cur["signature_hint"] = hint or ""
                # 初始化度量：默认将签名问题计数置为 0（若后续发现问题会覆盖）
                try:
                    metrics = cur.get("metrics") or {}
                    if "sig_issues" not in metrics:
                        metrics["sig_issues"] = 0
                    cur["metrics"] = metrics
                except Exception:
                    # 记录失败不影响主流程
                    pass
                self.progress["current"] = cur
                self._save_progress()
            except Exception:
                pass

            # 2) 生成实现
            unresolved = self._untranslated_callee_symbols(rec)
            typer.secho(f"[c2rust-transpiler][deps] 未解析的被调符号: {', '.join(unresolved) if unresolved else '(none)'}", fg=typer.colors.BLUE)
            typer.secho(f"[c2rust-transpiler][gen] 正在为 {rec.qname or rec.name} 生成 Rust 实现", fg=typer.colors.GREEN)
            self._codeagent_generate_impl(rec, c_code, module, rust_sig, unresolved)
            typer.secho(f"[c2rust-transpiler][gen] 已在 {module} 生成或更新实现", fg=typer.colors.GREEN)
            # 2.1) 生成后进行一次静态存在性校验，缺失则最小化修复补齐实现
            try:
                ok_impl = self._ensure_impl_present(module, rust_sig)
                typer.secho(f"[c2rust-transpiler][verify] 实现存在: {bool(ok_impl)} 于 {module}", fg=typer.colors.GREEN)
                # 为当前函数生成最小可编译的单元测试，并在后续以 cargo test 验证
                try:
                    self._ensure_minimal_tests(module, rust_sig)
                    typer.secho(f"[c2rust-transpiler][test] 已确保 {module} 的最小单元测试", fg=typer.colors.GREEN)
                except Exception:
                    pass
            except Exception:
                pass
            # 2.2) 确保顶层模块在 src/lib.rs 中被公开（便于后续引用 crate::<mod>::...）
            try:
                mp = Path(module)
                crate_root = self.crate_dir.resolve()
                # 归一出相对路径（相对于 crate 根）
                rel = mp.resolve().relative_to(crate_root) if mp.is_absolute() else Path(module)
                rel_s = str(rel).replace("\\", "/")
                if rel_s.startswith("./"):
                    rel_s = rel_s[2:]
                if rel_s.startswith("src/"):
                    parts = rel_s[len("src/"):].strip("/").split("/")
                    if parts and parts[0]:
                        top_mod = parts[0]
                        # 排除直接文件 lib.rs/main.rs 的情况
                        if not top_mod.endswith(".rs"):
                            self._ensure_top_level_pub_mod(top_mod)
                            typer.secho(f"[c2rust-transpiler][mod] 已在 src/lib.rs 确保顶层 pub mod {top_mod}", fg=typer.colors.GREEN)
            except Exception:
                pass

            # 2.3) 签名一致性检查（基于 C 符号与 LLM 提供的 rust_sig）
            try:
                sig_hint_local = self._infer_rust_signature_hint(rec)
                issues = self._check_signature_consistency(rust_sig, rec)
                typer.secho(f"[c2rust-transpiler][sig] 签名一致性问题数: {len(issues)}", fg=typer.colors.YELLOW)
                if issues:
                    fix_prompt = "\n".join([
                        f"请在文件 {module} 中根据以下问题最小化修正函数签名（仅签名层面）：",
                        *issues,
                        "",
                        "上下文信息：",
                        f"- crate 根目录路径: {self.crate_dir.resolve()}",
                        f"- 目标模块文件: {module}",
                        f"- 当前/建议 Rust 签名: {rust_sig}",
                        "- 符号表签名与参数（只读参考）：",
                        json.dumps({"signature": getattr(rec, "signature", ""), "params": getattr(rec, "params", None)}, ensure_ascii=False, indent=2),
                        "",
                        "C 源码片段（供参考，不要原样粘贴）：",
                        "<C_SOURCE>",
                        c_code,
                        "</C_SOURCE>",
                        "",
                        "如需按需检索符号表记录，请使用符号表检索工具：",
                        "- 工具: read_symbols",
                        "- 参数示例(YAML):",
                        f"  symbols_file: \"{(self.data_dir / 'symbols.jsonl').resolve()}\"",
                        "  symbols:",
                        f"    - \"{rec.qname or rec.name}\"",
                        "",
                        "参考（启发式）Rust 签名建议（可按需调整）：",
                        sig_hint_local or "(无建议，保持最小改动)",
                        "",
                        "- 仅允许修改函数签名（参数类型/指针 *const/*mut、返回类型等），避免改动函数体逻辑；",
                        "- 不要删除函数或大范围重构；",
                        "- 修改后保证编译通过（若需引入 use，则最小化添加）。",
                        "仅输出补丁，不要输出解释。",
                    ])
                    prev = os.getcwd()
                    try:
                        os.chdir(str(self.crate_dir))
                        agent = CodeAgent(need_summary=False, non_interactive=True, plan=False, model_group=self.llm_group)
                        agent.run(fix_prompt, prefix="[c2rust-transpiler][sig-fix]", suffix="")
                    finally:
                        os.chdir(prev)
                    # 记录到进度，便于诊断与续跑（签名检查与类型/边界审查结果）
                    try:
                        cur = self.progress.get("current") or {}
                        cur["signature_check"] = {"hint": sig_hint_local, "issues": issues}
                        # 同步记录类型/边界审查结论与修复标记
                        tbr = cur.get("type_boundary_review") or {}
                        tbr.update({"ok": False, "issues": issues, "fixed": True})
                        cur["type_boundary_review"] = tbr
                        # 增加度量统计：记录签名问题计数（便于后续诊断与汇总）
                        try:
                            metrics = cur.get("metrics") or {}
                            metrics["sig_issues"] = int(len(issues))
                            cur["metrics"] = metrics
                        except Exception:
                            # 统计失败不阻塞流程
                            pass
                        self.progress["current"] = cur
                        self._save_progress()
                    except Exception:
                        pass
            except Exception:
                pass
            # 2.2b) 确保从目标模块向上的 mod.rs 声明链补齐
            try:
                self._ensure_mod_chain_for_module(module)
                typer.secho(f"[c2rust-transpiler][mod] 已补齐 {module} 的 mod.rs 声明链", fg=typer.colors.GREEN)
                # 标记当前函数的模块链已补齐，便于诊断与续跑；同时记录顶层可见性修复标记
                cur = self.progress.get("current") or {}
                cur["mod_chain_fixed"] = True
                cur["mod_visibility_fixed"] = True
                self.progress["current"] = cur
                self._save_progress()
            except Exception:
                pass

            # 3) 构建与修复
            typer.secho(f"[c2rust-transpiler][build] 开始 cargo 测试循环", fg=typer.colors.MAGENTA)
            ok = self._cargo_build_loop()
            typer.secho(f"[c2rust-transpiler][build] 构建结果: {'通过' if ok else '失败'}", fg=typer.colors.MAGENTA)
            if not ok:
                typer.secho("[c2rust-transpiler] 在重试次数限制内未能成功构建，已停止。", fg=typer.colors.RED)
                # 保留当前状态，便于下次 resume
                return

            # 4) 审查与优化
            typer.secho(f"[c2rust-transpiler][review] 开始代码审查: {rec.qname or rec.name}", fg=typer.colors.MAGENTA)
            self._review_and_optimize(rec, module, rust_sig)
            typer.secho(f"[c2rust-transpiler][review] 代码审查完成", fg=typer.colors.MAGENTA)

            # 5) 标记已转换与映射记录（JSONL）
            self._mark_converted(rec, module, rust_sig)
            typer.secho(f"[c2rust-transpiler][mark] 已标记并建立映射: {rec.qname or rec.name} -> {module}", fg=typer.colors.GREEN)

            # 6) 若此前有其它函数因依赖当前符号而在源码中放置了 todo!("<symbol>")，则立即回头消除
            current_rust_fn = self._extract_rust_fn_name_from_sig(rust_sig)
            # 优先使用限定名匹配，其次使用简单名匹配
            for sym in [rec.qname, rec.name]:
                if sym:
                    typer.secho(f"[c2rust-transpiler][todo] 清理 todo!(\'{sym}\') 的出现位置", fg=typer.colors.BLUE)
                    self._resolve_pending_todos_for_symbol(sym, module, current_rust_fn, rust_sig)
                    typer.secho(f"[c2rust-transpiler][build] 处理 todo 后重新运行 cargo test", fg=typer.colors.MAGENTA)
                    self._cargo_build_loop()

        typer.secho("[c2rust-transpiler] 所有符合条件的函数均已处理完毕。", fg=typer.colors.GREEN)


def run_transpile(
    project_root: Union[str, Path] = ".",
    crate_dir: Optional[Union[str, Path]] = None,
    llm_group: Optional[str] = None,
    max_retries: int = 0,
    resume: bool = True,
    only: Optional[List[str]] = None,
) -> None:
    """
    入口函数：执行转译流程
    - project_root: 项目根目录（包含 .jarvis/c2rust/symbols.jsonl）
    - crate_dir: Rust crate 根目录；默认遵循 "<parent>/<cwd_name>_rs"（与当前目录同级，若 project_root 为 ".")
    - llm_group: 指定 LLM 模型组
    - max_retries: 构建与审查迭代的最大次数
    - resume: 是否启用断点续跑
    - only: 仅转译给定列表中的函数（函数名或限定名）
    """
    t = Transpiler(
        project_root=project_root,
        crate_dir=crate_dir,
        llm_group=llm_group,
        max_retries=max_retries,
        resume=resume,
        only=only,
    )
    t.transpile()