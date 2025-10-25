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

    def _has_steps(p: Path) -> bool:
        try:
            steps = _iter_order_steps(p)
            return bool(steps)
        except Exception:
            return False

    # 已存在则校验是否有步骤
    if order_path.exists():
        if _has_steps(order_path):
            return order_path
        # 为空或不可读：基于标准路径重新计算（仅 symbols.jsonl）
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

    if not order_path.exists():
        raise FileNotFoundError(f"计算后未找到 translation_order.jsonl: {order_path}")

    # 最终校验：若仍无有效步骤，直接报错并提示先执行 scan 或检查 symbols.jsonl
    if not _has_steps(order_path):
        raise RuntimeError("translation_order.jsonl 无有效步骤。请先执行 'jarvis-c2rust scan' 生成 symbols.jsonl 并重试。")

    return order_path

def _iter_order_steps(order_jsonl: Path) -> List[List[int]]:
    """读取翻译顺序，返回按步骤的函数id序列列表（仅支持新格式）
    新格式要求：每行包含 "symbols": [str, ...]，其中元素为函数的 qualified_name 或 name。
    本函数会基于同目录下 symbols.jsonl 将名称/限定名解析为 id。
    """
    # 构建 name -> id 映射（基于同目录 symbols.jsonl）
    name_to_id: Dict[str, int] = {}
    try:
        data_dir = order_jsonl.parent
        symbols_path = data_dir / "symbols.jsonl"
        if symbols_path.exists():
            with symbols_path.open("r", encoding="utf-8") as sf:
                idx = 0
                for line in sf:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    idx += 1
                    fid = int(obj.get("id") or idx)
                    nm = obj.get("name") or ""
                    qn = obj.get("qualified_name") or ""
                    if nm:
                        name_to_id.setdefault(nm, fid)
                    if qn:
                        name_to_id.setdefault(qn, fid)
    except Exception:
        # 若映射构建失败，steps 将为空（严格新格式，不回退旧格式）
        name_to_id = {}

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

            syms = obj.get("symbols")
            if not (isinstance(syms, list) and syms):
                # 严格新格式：无 symbols 则跳过该行
                continue

            ids: List[int] = []
            for s in syms:
                if not isinstance(s, str) or not s:
                    continue
                tid = name_to_id.get(s)
                if isinstance(tid, int):
                    ids.append(tid)
            if ids:
                steps.append(ids)
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

        self.crate_dir = Path(crate_dir) if crate_dir else _default_crate_dir(self.project_root)
        self.db = _DbLoader(self.project_root)

        self.progress: Dict[str, Any] = _read_json(self.progress_path, {"current": None, "converted": []})
        # 使用 JSONL 存储的符号映射
        self.symbol_map = _SymbolMapJsonl(self.symbol_map_path, legacy_json_path=self.legacy_symbol_map_path)

        # 在当前工作目录创建/更新 workspace，使该 crate 作为成员，便于在本地当前目录直接构建
        def _ensure_workspace_member(root_dir: Path, member_path: Path) -> None:
            """
            在 root_dir 下的 Cargo.toml 中确保 [workspace] 成员包含 member_path（相对于 root_dir 的路径）。
            - 若 Cargo.toml 不存在：创建最小可用的 workspace 文件；
            - 若存在但无 [workspace]：追加 [workspace] 与 members；
            - 若存在且有 [workspace]：将成员路径加入 members（若不存在）。
            尽量保留原有内容与格式，最小修改。
            """
            cargo_path = root_dir / "Cargo.toml"
            # 计算成员的相对路径
            try:
                rel_member = str(member_path.resolve().relative_to(root_dir.resolve()))
            except Exception:
                rel_member = member_path.name

            if not cargo_path.exists():
                content = f"""[workspace]
members = ["{rel_member}"]
"""
                try:
                    cargo_path.write_text(content, encoding="utf-8")
                except Exception:
                    pass
                return

            try:
                txt = cargo_path.read_text(encoding="utf-8")
            except Exception:
                return

            if "[workspace]" not in txt:
                new_txt = txt.rstrip() + f"\n\n[workspace]\nmembers = [\"{rel_member}\"]\n"
                try:
                    cargo_path.write_text(new_txt, encoding="utf-8")
                except Exception:
                    pass
                return

            # 提取 workspace 区块（直到下一个表头或文件末尾）
            m_ws = re.search(r"(?s)(\[workspace\].*?)(?:\n\[|\Z)", txt)
            if not m_ws:
                new_txt = txt.rstrip() + f"\n\n[workspace]\nmembers = [\"{rel_member}\"]\n"
                try:
                    cargo_path.write_text(new_txt, encoding="utf-8")
                except Exception:
                    pass
                return

            ws_block = m_ws.group(1)

            # 查找 members 数组
            m_members = re.search(r"members\s*=\s*\[(.*?)\]", ws_block, flags=re.S)
            if not m_members:
                # 在 [workspace] 行后插入 members
                new_ws_block = re.sub(r"(\[workspace\]\s*)", r"\1\nmembers = [\"" + rel_member + "\"]\n", ws_block, count=1)
            else:
                inner = m_members.group(1)
                # 解析已有成员
                existing_vals = []
                for v in inner.split(","):
                    vv = v.strip()
                    if not vv:
                        continue
                    if vv.startswith('"') or vv.startswith("'"):
                        vv = vv.strip('"').strip("'")
                    existing_vals.append(vv)
                if rel_member in existing_vals:
                    new_ws_block = ws_block  # 已存在，不改动
                else:
                    # 根据原格式选择分隔符
                    sep = ", " if "\n" not in inner else ",\n"
                    new_inner = inner.strip()
                    if new_inner:
                        new_inner = new_inner + f"{sep}\"{rel_member}\""
                    else:
                        new_inner = f"\"{rel_member}\""
                    new_ws_block = ws_block[: m_members.start(1)] + new_inner + ws_block[m_members.end(1) :]

            # 写回更新后的 workspace 区块
            new_txt = txt[: m_ws.start(1)] + new_ws_block + txt[m_ws.end(1) :]
            try:
                cargo_path.write_text(new_txt, encoding="utf-8")
            except Exception:
                pass

        # 尝试确保 crate 目录存在（不负责生成结构，假设 plan/apply 已完成）
        self.crate_dir.mkdir(parents=True, exist_ok=True)
        # 按新策略：不再将 crate 添加到 workspace（构建在 crate 目录内进行）
        try:
            # 在 crate 目录内进行 Git 初始化（若未初始化），并尝试创建初始提交
            git_dir = self.crate_dir / ".git"
            if not git_dir.exists():
                subprocess.run(["git", "init"], check=False, cwd=str(self.crate_dir))
                subprocess.run(["git", "add", "-A"], check=False, cwd=str(self.crate_dir))
                subprocess.run(["git", "commit", "-m", "[c2rust-transpiler] init crate"], check=False, cwd=str(self.crate_dir))
        except Exception:
            # 忽略 git 初始化失败，不影响主流程
            pass

    def _save_progress(self) -> None:
        _write_json(self.progress_path, self.progress)

    # JSONL 模式下不再整体写回 symbol_map；此方法保留占位（兼容旧调用），无操作
    def _save_symbol_map(self) -> None:
        return

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
            # 已转映射
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
            # 尝试按名称解析ID（函数或类型）
            cid = self.db.get_id_by_name(callee)
            if cid:
                crec = self.db.get(cid)
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
            "- 函数签名请尽量在Rust中表达指针/数组/结构体语义（可先用简单类型占位，后续由实现阶段细化）；\n"
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
            "被引用符号上下文（如已转译则包含Rust模块信息）：",
            json.dumps(callees_ctx, ensure_ascii=False, indent=2),
            "",
            "当前crate目录结构（部分）：",
            "<CRATE_TREE>",
            crate_tree,
            "</CRATE_TREE>",
            "",
            "如果理解完毕，请进入总结阶段。",
        ])
        summary_prompt = (
            "请仅输出一个 <SUMMARY> 块，块内必须且只包含一个 <yaml>...</yaml>，不得包含其它内容。\n"
            "允许字段（YAML 对象）：\n"
            '- module: "<绝对路径>/src/xxx.rs 或 <绝对路径>/src/xxx/mod.rs"\n'
            '- rust_signature: "pub fn xxx(...)->..."\n'
            '- notes: "可选说明（若有上下文缺失或风险点，请在此列出）"\n'
            "注意：\n"
            "- module 必须位于 crate 的 src/ 目录下且使用绝对路径；尽量选择已有文件；如需新建文件，给出合理路径；\n"
            "- rust_signature 请包含可见性修饰与函数名（可先用占位类型）。\n"
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
            try:
                mp = Path(str(module).strip()).resolve()
                if not mp.is_absolute():
                    return False, "module 必须为绝对路径"
                crate_root = self.crate_dir.resolve()
                # 必须位于 crate/src 下
                rel = mp.relative_to(crate_root)
                parts = rel.parts
                if not parts or parts[0] != "src":
                    return False, "module 必须位于 crate 的 src/ 目录下（绝对路径）"
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
                use_tools=["execute_script", "read_code", "retrieve_memory", "save_memory"],
                plan=False,
                non_interactive=True,
                use_methodology=False,
                use_analysis=False,
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
                return module, rust_sig
            else:
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

    def _codeagent_generate_impl(self, rec: FnRecord, c_code: str, module: str, rust_sig: str, unresolved: List[str]) -> None:
        """
        使用 CodeAgent 生成/更新目标模块中的函数实现。
        约束：最小变更，生成可编译的占位实现，尽可能保留后续细化空间。
        """
        requirement_lines = [
            f"目标：在 crate 目录 {self.crate_dir.resolve()} 的 {module} 中，为 C 函数 {rec.qname or rec.name} 生成对应的 Rust 实现。",
            "要求：",
            f"- 函数签名（建议）：{rust_sig}",
            "- 若 module 文件不存在则新建；为所在模块添加必要的 mod 声明（若需要）；",
            "- 若已有函数占位/实现，尽量最小修改，不要破坏现有代码；",
            "- 你可以参考原 C 函数的关联实现（如同文件/同模块的相关辅助函数、内联实现、宏与注释等），在保持语义一致的前提下以符合 Rust 风格的方式实现；避免机械复制粘贴；",
            "- 禁止在函数实现中使用 todo!/unimplemented! 作为占位；仅当调用的函数尚未实现时，才在调用位置使用 todo!(\"符号名\") 占位；",
            "- 为保证 cargo build 通过，如需返回占位值，请使用合理默认值或 Result/Option 等，而非 panic!/todo!/unimplemented!；",
            "- 不要删除或移动其他无关文件。",
            "",
            "编码原则与规范：",
            "- 保持最小变更，避免无关重构与格式化；禁止批量重排/重命名/移动文件；",
            "- 命名遵循Rust惯例（函数/模块蛇形命名），公共API使用pub；",
            "- 优先使用安全Rust；如需unsafe，将范围最小化并添加注释说明原因与SAFETY保证；",
            "- 错误处理：可暂用 Result<_, anyhow::Error> 或 Option 作占位，避免 panic!/unwrap()；",
            "- 实现中禁止使用 todo!/unimplemented! 占位；仅允许为尚未实现的被调符号在调用位置使用 todo!(\"符号名\")；",
            "- 如需占位返回，使用合理默认值或 Result/Option 等而非 panic!/todo!/unimplemented!；",
            "- 依赖未实现符号时，务必使用 todo!(\"符号名\") 明确标记，便于后续自动替换；",
            "- 文档：为新增函数添加简要文档注释，注明来源C函数与意图；",
            "- 风格：遵循 rustfmt 默认风格，避免引入与本次改动无关的大范围格式变化；",
            "- 输出限制：仅以补丁形式修改目标文件，不要输出解释或多余文本。",
            "",
            "C 源码片段（供参考，不要原样粘贴）：",
            "<C_SOURCE>",
            c_code,
            "</C_SOURCE>",
            "",
            "注意：所有修改均以补丁方式进行。",
            "",
            "尚未转换的被调符号如下（请在调用位置使用 todo!(\"<符号>\") 作为占位，以便后续自动消除）：",
            *[f"- {s}" for s in (unresolved or [])],
        ]
        prompt = "\n".join(requirement_lines)
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

    def _module_file_to_crate_path(self, module: str) -> str:
        """
        将模块文件路径转换为 crate 路径前缀：
        - src/lib.rs -> crate
        - src/foo/mod.rs -> crate::foo
        - src/foo/bar.rs -> crate::foo::bar
        其它（非 src/ 前缀）统一返回 'crate'
        """
        mod = str(module).strip()
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
        - 扫描整个 crate（优先 src/ 目录）中所有 .rs 文件，查找 todo!("符号名") 占位
        - 对每个命中的文件，创建 CodeAgent 将占位替换为对已转换函数的真实调用（可使用 crate::... 完全限定路径或 use 引入）
        - 最小化修改，避免无关重构

        说明：不再使用 todos.json，本方法直接搜索源码中的 todo!("xxxx")。
        """
        if not symbol:
            return

        # 计算被调函数的crate路径前缀，便于在提示中提供调用路径建议
        callee_path = self._module_file_to_crate_path(callee_module)

        # 扫描 src 下的 .rs 文件，查找 todo!("symbol") 占位
        matches: List[str] = []
        src_root = (self.crate_dir / "src").resolve()
        if src_root.exists():
            for p in sorted(src_root.rglob("*.rs")):
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                needle = f'todo!("{symbol}")'
                if needle in text:
                    try:
                        # 记录绝对路径，避免依赖当前工作目录
                        abs_path = str(p.resolve())
                    except Exception:
                        abs_path = str(p)
                    matches.append(abs_path)

        if not matches:
            return

        # 在当前工作目录运行 CodeAgent，不进入 crate 目录
        for target_file in matches:
            prompt = "\n".join([
                f"请在文件 {target_file} 中，定位所有 todo!(\"{symbol}\") 占位并替换为对已转换函数的真实调用。",
                "要求：",
                f"- 已转换的目标函数名：{callee_rust_fn}",
                f"- 其所在模块（crate路径提示）：{callee_path}",
                f"- 函数签名提示：{callee_rust_sig}",
                f"- 当前 crate 根目录路径：{self.crate_dir.resolve()}",
                "- 你可以使用完全限定路径（如 crate::...::函数(...)），或在文件顶部添加合适的 use；",
                "- 保持最小改动，不要进行与本次修复无关的重构或格式化；",
                "- 如果参数列表暂不明确，可使用合理占位变量，确保编译通过。",
                "",
                f"仅修改 {target_file} 中与 todo!(\"{symbol}\") 相关的代码，其他位置不要改动。",
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
        i = 0
        while True:
            i += 1
            res = subprocess.run(
                ["cargo", "build", "-q"],
                capture_output=True,
                text=True,
                check=False,
                cwd=workspace_root,
            )
            if res.returncode == 0:
                print("[c2rust-transpiler] Cargo 构建成功。")
                return True
            output = (res.stdout or "") + "\n" + (res.stderr or "")
            print(f"[c2rust-transpiler] Cargo 构建失败 (第 {i} 次尝试)。")
            print(output)
            repair_prompt = "\n".join([
                "目标：以最小的改动修复问题，使 `cargo build` 命令可以通过。",
                "允许的修复：修正入口/模块声明/依赖；对入口文件与必要mod.rs进行轻微调整；避免大范围改动。",
                "- 保持最小改动，避免与错误无关的重构或格式化；",
                "- 请仅输出补丁，不要输出解释或多余文本。",
                "上下文：",
                f"- crate 根目录路径: {self.crate_dir.resolve()}",
                f"- 包名称（用于 cargo build -p）: {self.crate_dir.name}",
                "",
                "请阅读以下构建错误并进行必要修复：",
                "<BUILD_ERROR>",
                output,
                "</BUILD_ERROR>",
                "修复后请再次执行 `cargo build` 进行验证。",
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
                "你是严谨的Rust代码审查专家，目标是对给定函数的实现进行快速审查，指出明显问题并给出简要建议。"
                "仅在总结阶段输出审查结论。"
            )
            usr_p = "\n".join([
                f"待审查函数：{rec.qname or rec.name}",
                f"建议签名：{rust_sig}",
                f"目标模块：{module}",
                f"crate根目录路径：{self.crate_dir.resolve()}",
                "请阅读crate中该函数的当前实现（你可以在上述crate根路径下自行读取必要上下文），并准备总结。",
            ])
            sum_p = (
                "请仅输出一个 <SUMMARY> 块，内容为纯文本：\n"
                "- 若通过请输出：OK\n"
                "- 否则以简要列表形式指出问题点（避免长文）。\n"
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
                use_tools=["execute_script", "read_code", "retrieve_memory", "save_memory"],
                plan=False,
                non_interactive=True,
                use_methodology=False,
                use_analysis=False,
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
                print("[c2rust-transpiler] 代码审查通过。")
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
                "",
                "请仅以补丁形式输出修改，避免冗余解释。",
            ])
            # 在当前工作目录运行 CodeAgent，不进入 crate 目录
            ca = CodeAgent(need_summary=False, non_interactive=True, plan=False, model_group=self.llm_group)
            prev_cwd = os.getcwd()
            try:
                os.chdir(str(self.crate_dir))
                ca.run(fix_prompt, prefix=f"[c2rust-transpiler][review-fix iter={i}]", suffix="")
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

    def transpile(self) -> None:
        """主流程"""
        order_path = _ensure_order_file(self.project_root)
        steps = _iter_order_steps(order_path)
        if not steps:
            typer.secho("[c2rust-transpiler] 未找到翻译步骤。", fg=typer.colors.YELLOW)
            return

        # 扁平化顺序，按单个函数处理（保持原有顺序）
        seq: List[int] = []
        for grp in steps:
            seq.extend(grp)

        # 若支持 resume，则跳过 progress['converted'] 中已完成的
        done: Set[int] = set(self.progress.get("converted") or [])

        for fid in seq:
            if fid in done:
                continue
            rec = self.db.get(fid)
            if not rec:
                continue
            if self._should_skip(rec):
                continue

            # 读取C函数源码
            c_code = self.db.read_source_span(rec)

            # 1) 规划：模块路径与Rust签名
            module, rust_sig = self._plan_module_and_signature(rec, c_code)

            # 记录当前进度
            self._update_progress_current(rec, module, rust_sig)

            # 2) 生成实现
            unresolved = self._untranslated_callee_symbols(rec)
            self._codeagent_generate_impl(rec, c_code, module, rust_sig, unresolved)

            # 3) 构建与修复
            ok = self._cargo_build_loop()
            if not ok:
                typer.secho("[c2rust-transpiler] 在重试次数限制内未能成功构建，已停止。", fg=typer.colors.RED)
                # 保留当前状态，便于下次 resume
                return

            # 4) 审查与优化
            self._review_and_optimize(rec, module, rust_sig)

            # 5) 标记已转换与映射记录（JSONL）
            self._mark_converted(rec, module, rust_sig)

            # 6) 若此前有其它函数因依赖当前符号而在源码中放置了 todo!("<symbol>")，则立即回头消除
            current_rust_fn = self._extract_rust_fn_name_from_sig(rust_sig)
            # 优先使用限定名匹配，其次使用简单名匹配
            for sym in [rec.qname, rec.name]:
                if sym:
                    self._resolve_pending_todos_for_symbol(sym, module, current_rust_fn, rust_sig)
                    # 尝试一次构建以验证修复
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