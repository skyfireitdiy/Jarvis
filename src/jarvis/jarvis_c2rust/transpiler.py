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
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Set

from jarvis.jarvis_utils.jsonnet_compat import loads as json5_loads
# json5 已替换为 jsonnet，通过 jsonnet_compat 模块提供兼容接口
import typer

from jarvis.jarvis_c2rust.scanner import compute_translation_order_jsonl
from jarvis.jarvis_agent import Agent
from jarvis.jarvis_code_agent.code_agent import CodeAgent
from jarvis.jarvis_utils.git_utils import get_latest_commit_hash


# 数据文件常量
C2RUST_DIRNAME = ".jarvis/c2rust"

SYMBOLS_JSONL = "symbols.jsonl"
ORDER_JSONL = "translation_order.jsonl"
PROGRESS_JSON = "progress.json"
SYMBOL_MAP_JSONL = "symbol_map.jsonl"

# 配置常量
ERROR_SUMMARY_MAX_LENGTH = 2000  # 错误信息摘要最大长度
DEFAULT_PLAN_MAX_RETRIES = 0  # 规划阶段默认最大重试次数（0表示无限重试）
DEFAULT_REVIEW_MAX_ITERATIONS = 0  # 审查阶段最大迭代次数（0表示无限重试）
DEFAULT_CHECK_MAX_RETRIES = 0  # cargo check 阶段默认最大重试次数（0表示无限重试）
DEFAULT_TEST_MAX_RETRIES = 0  # cargo test 阶段默认最大重试次数（0表示无限重试）

# 回退与重试常量
CONSECUTIVE_FIX_FAILURE_THRESHOLD = 10  # 连续修复失败次数阈值，达到此值将触发回退
MAX_FUNCTION_RETRIES = 10  # 函数重新开始处理的最大次数
DEFAULT_PLAN_MAX_RETRIES_ENTRY = 5  # run_transpile 入口函数的 plan_max_retries 默认值


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
    """原子性写入JSON文件：先写入临时文件，再重命名"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 使用临时文件确保原子性
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        # 原子性重命名
        temp_path.replace(path)
    except Exception:
        # 如果原子写入失败，回退到直接写入
        try:
            path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


def _extract_json_from_summary(text: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    从 Agent summary 中提取结构化数据（使用 JSON 格式）：
    - 仅在 <SUMMARY>...</SUMMARY> 块内查找；
    - 直接解析 <SUMMARY> 块内的内容为 JSON 对象（不需要额外的 <json> 标签）；
    - 使用 jsonnet 解析，支持更宽松的 JSON 语法（如尾随逗号、注释等）；
    返回(解析结果, 错误信息)
    如果解析成功，返回(data, None)
    如果解析失败，返回({}, 错误信息)
    """
    if not isinstance(text, str) or not text.strip():
        return {}, "摘要文本为空"

    # 提取 <SUMMARY> 块
    m = re.search(r"<SUMMARY>([\s\S]*?)</SUMMARY>", text, flags=re.IGNORECASE)
    block = (m.group(1) if m else text).strip()

    if not block:
        return {}, "未找到 <SUMMARY> 或 </SUMMARY> 标签，或标签内容为空"

    try:
        try:
            obj = json5_loads(block)
        except Exception as json_err:
            error_msg = f"JSON 解析失败: {str(json_err)}"
            return {}, error_msg
        if isinstance(obj, dict):
            return obj, None
        return {}, f"JSON 解析结果不是字典，而是 {type(obj).__name__}"
    except Exception as e:
        return {}, f"解析过程发生异常: {str(e)}"


class Transpiler:
    def __init__(
        self,
        project_root: Union[str, Path] = ".",
        crate_dir: Optional[Union[str, Path]] = None,
        llm_group: Optional[str] = None,
        plan_max_retries: int = DEFAULT_PLAN_MAX_RETRIES,  # 规划阶段最大重试次数（0表示无限重试）
        max_retries: int = 0,  # 兼容旧接口，如未设置则使用 check_max_retries 和 test_max_retries
        check_max_retries: Optional[int] = None,  # cargo check 阶段最大重试次数（0表示无限重试）
        test_max_retries: Optional[int] = None,  # cargo test 阶段最大重试次数（0表示无限重试）
        review_max_iterations: int = DEFAULT_REVIEW_MAX_ITERATIONS,  # 审查阶段最大迭代次数（0表示无限重试）
        resume: bool = True,
        only: Optional[List[str]] = None,  # 仅转译指定函数名（简单名或限定名）
        disabled_libraries: Optional[List[str]] = None,  # 禁用库列表（在实现时禁止使用这些库）
        non_interactive: bool = True,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.data_dir = self.project_root / C2RUST_DIRNAME
        self.progress_path = self.data_dir / PROGRESS_JSON
        # JSONL 路径
        self.symbol_map_path = self.data_dir / SYMBOL_MAP_JSONL
        self.llm_group = llm_group
        self.plan_max_retries = plan_max_retries
        # 兼容旧接口：如果只设置了 max_retries，则同时用于 check 和 test
        if max_retries > 0 and check_max_retries is None and test_max_retries is None:
            self.check_max_retries = max_retries
            self.test_max_retries = max_retries
        else:
            self.check_max_retries = check_max_retries if check_max_retries is not None else DEFAULT_CHECK_MAX_RETRIES
            self.test_max_retries = test_max_retries if test_max_retries is not None else DEFAULT_TEST_MAX_RETRIES
        self.max_retries = max(self.check_max_retries, self.test_max_retries)  # 保持兼容性
        self.review_max_iterations = review_max_iterations
        self.resume = resume
        self.only = set(only or [])
        self.disabled_libraries = disabled_libraries or []
        self.non_interactive = non_interactive
        typer.secho(f"[c2rust-transpiler][init] 初始化参数: project_root={self.project_root} crate_dir={Path(crate_dir) if crate_dir else _default_crate_dir(self.project_root)} llm_group={self.llm_group} plan_max_retries={self.plan_max_retries} check_max_retries={self.check_max_retries} test_max_retries={self.test_max_retries} review_max_iterations={self.review_max_iterations} resume={self.resume} only={sorted(list(self.only)) if self.only else []} disabled_libraries={self.disabled_libraries} non_interactive={self.non_interactive}", fg=typer.colors.BLUE)

        self.crate_dir = Path(crate_dir) if crate_dir else _default_crate_dir(self.project_root)
        # 使用自包含的 order.jsonl 记录构建索引，避免依赖 symbols.jsonl
        self.fn_index_by_id: Dict[int, FnRecord] = {}
        self.fn_name_to_id: Dict[str, int] = {}

        self.progress: Dict[str, Any] = _read_json(self.progress_path, {"current": None, "converted": []})
        # 使用 JSONL 存储的符号映射
        self.symbol_map = _SymbolMapJsonl(self.symbol_map_path)

        # 当前函数上下文与Agent复用缓存（按单个函数生命周期）
        self._current_agents: Dict[str, Any] = {}
        # 全量与精简上下文头部
        self._current_context_full_header: str = ""
        self._current_context_compact_header: str = ""
        # 是否已发送过全量头部（每函数仅一次）
        self._current_context_full_sent: bool = False
        # 兼容旧字段（不再使用）
        self._current_context_header: str = ""
        self._current_function_id: Optional[int] = None
        # 缓存 compile_commands.json 的解析结果
        self._compile_commands_cache: Optional[List[Dict[str, Any]]] = None
        self._compile_commands_path: Optional[Path] = None
        # 当前函数开始时的 commit id（用于失败回退）
        self._current_function_start_commit: Optional[str] = None
        # 连续修复失败的次数（用于判断是否需要回退）
        self._consecutive_fix_failures: int = 0

    def _find_compile_commands(self) -> Optional[Path]:
        """
        查找 compile_commands.json 文件。
        搜索顺序：
        1. project_root / compile_commands.json
        2. project_root / build / compile_commands.json
        3. project_root 的父目录及向上查找（最多向上3层）
        """
        # 首先在 project_root 下查找
        candidates = [
            self.project_root / "compile_commands.json",
            self.project_root / "build" / "compile_commands.json",
        ]
        # 向上查找（最多3层）
        current = self.project_root.parent
        for _ in range(3):
            if current and current.exists():
                candidates.append(current / "compile_commands.json")
                current = current.parent
            else:
                break
        
        for path in candidates:
            if path.exists() and path.is_file():
                return path.resolve()
        return None

    def _load_compile_commands(self) -> Optional[List[Dict[str, Any]]]:
        """
        加载 compile_commands.json 文件。
        如果已缓存，直接返回缓存结果。
        """
        if self._compile_commands_cache is not None:
            return self._compile_commands_cache
        
        compile_commands_path = self._find_compile_commands()
        if compile_commands_path is None:
            self._compile_commands_cache = []
            self._compile_commands_path = None
            return None
        
        try:
            with compile_commands_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self._compile_commands_cache = data
                    self._compile_commands_path = compile_commands_path
                    typer.secho(f"[c2rust-transpiler][compile_commands] 已加载: {compile_commands_path} ({len(data)} 条记录)", fg=typer.colors.BLUE)
                    return data
        except Exception as e:
            typer.secho(f"[c2rust-transpiler][compile_commands] 加载失败: {compile_commands_path}: {e}", fg=typer.colors.YELLOW)
            self._compile_commands_cache = []
            self._compile_commands_path = None
            return None
        
        self._compile_commands_cache = []
        self._compile_commands_path = None
        return None

    def _extract_compile_flags(self, c_file_path: Union[str, Path]) -> Optional[str]:
        """
        从 compile_commands.json 中提取指定 C 文件的编译参数。
        
        如果 compile_commands.json 中存在 arguments 字段，则用空格连接该数组并返回。
        如果只有 command 字段，则直接返回 command 字符串。
        
        返回格式：
        - 如果存在 arguments：用空格连接的参数字符串，例如 "-I/usr/include -DDEBUG"
        - 如果只有 command：完整的编译命令字符串，例如 "gcc -I/usr/include -DDEBUG file.c"
        
        如果未找到或解析失败，返回 None。
        """
        compile_commands = self._load_compile_commands()
        if not compile_commands:
            return None
        
        # 规范化目标文件路径
        try:
            target_path = Path(c_file_path)
            if not target_path.is_absolute():
                target_path = (self.project_root / target_path).resolve()
            target_path = target_path.resolve()
        except Exception:
            return None
        
        # 查找匹配的编译命令
        for entry in compile_commands:
            if not isinstance(entry, dict):
                continue
            
            entry_file = entry.get("file")
            if not entry_file:
                continue
            
            try:
                entry_path = Path(entry_file)
                if not entry_path.is_absolute() and entry.get("directory"):
                    entry_path = (Path(entry.get("directory")) / entry_path).resolve()
                entry_path = entry_path.resolve()
                
                # 路径匹配（支持相对路径和绝对路径）
                if entry_path == target_path:
                    # 如果存在 arguments，用空格连接并返回
                    arguments = entry.get("arguments")
                    if isinstance(arguments, list):
                        # 过滤掉空字符串，然后用空格连接
                        args = [str(arg) for arg in arguments if arg]
                        return " ".join(args) if args else None
                    # 如果只有 command，直接返回 command 字符串
                    elif entry.get("command"):
                        command = entry.get("command", "")
                        return command if command else None
            except Exception:
                continue
        
        return None

    def _save_progress(self) -> None:
        """保存进度，使用原子性写入"""
        _write_json(self.progress_path, self.progress)


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
        要求 summary 输出 JSON：
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
            "- 函数接口设计应遵循 Rust 最佳实践，不需要兼容 C 的数据类型；优先使用 Rust 原生类型（如 i32/u32/usize、&[T]/&mut [T]、String、Result<T, E> 等），而不是 C 风格类型（如 core::ffi::c_*、libc::c_*）；\n"
            "- 禁止使用 extern \"C\"；函数应使用标准的 Rust 调用约定，不需要 C ABI；\n"
            "- 参数个数与顺序可以保持与 C 一致，但类型设计应优先考虑 Rust 的惯用法和安全性；\n"
            "- **特殊处理：对于资源释放类函数（如文件关闭、内存释放、句柄释放等），在 Rust 中通常通过 RAII 自动管理，可以跳过实现或提供空实现；请在 notes 字段中标注此类情况；\n"
            "- 仅输出必要信息，避免冗余解释。"
        )
        # 提取编译参数
        compile_flags = self._extract_compile_flags(rec.file)
        compile_flags_section = ""
        if compile_flags:
            compile_flags_section = "\n".join([
                "",
                "C文件编译参数（来自 compile_commands.json）：",
                compile_flags,
            ])
        
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
            compile_flags_section,
            "",
            *([f"禁用库列表（禁止在实现中使用这些库）：{', '.join(self.disabled_libraries)}"] if self.disabled_libraries else []),
            *([""] if self.disabled_libraries else []),
            "当前crate目录结构（部分）：",
            "<CRATE_TREE>",
            crate_tree,
            "</CRATE_TREE>",
            "",
            "为避免完整读取体积较大的符号表，你也可以使用工具 read_symbols 按需获取指定符号记录：",
            "- 工具: read_symbols",
            "- 参数示例(JSON):",
            f"  {{\"symbols_file\": \"{(self.data_dir / 'symbols.jsonl').resolve()}\", \"symbols\": [\"符号1\", \"符号2\"]}}",
            "",
            "如果理解完毕，请进入总结阶段。",
        ])
        summary_prompt = (
            "请仅输出一个 <SUMMARY> 块，块内必须且只包含一个 JSON 对象，不得包含其它内容。\n"
            "允许字段（JSON 对象）：\n"
            '- "module": "<绝对路径>/src/xxx.rs 或 <绝对路径>/src/xxx/mod.rs；或相对路径 src/xxx.rs / src/xxx/mod.rs"\n'
            '- "rust_signature": "pub fn xxx(...)->..."\n'
            '- "skip_implementation": bool  // 可选，如果为 true，表示此函数可通过 RAII 自动管理，可以跳过实现阶段\n'
            '- "notes": "可选说明（若有上下文缺失或风险点，请在此列出）"\n'
            "注意：\n"
            "- module 必须位于 crate 的 src/ 目录下，接受绝对路径或以 src/ 开头的相对路径；尽量选择已有文件；如需新建文件，给出合理路径；\n"
            "- rust_signature 应遵循 Rust 最佳实践，不需要兼容 C 的数据类型；优先使用 Rust 原生类型和惯用法，而不是 C 风格类型。\n"
            "- **资源释放类函数处理**：如果函数是资源释放类（如文件关闭 fclose、内存释放 free、句柄释放、锁释放等），在 Rust 中通常通过 RAII（Drop trait）自动管理，可以跳过实现阶段；请设置 skip_implementation 为 true，并在 notes 字段中说明原因（如 \"通过 RAII 自动管理，无需显式实现\"）。\n"
            "- 类型设计原则：\n"
            "  * 基本类型：优先使用 i32/u32/i64/u64/isize/usize/f32/f64 等原生 Rust 类型，而不是 core::ffi::c_* 或 libc::c_*；\n"
            "  * 指针/引用：优先使用引用 &T/&mut T 或切片 &[T]/&mut [T]，而非原始指针 *const T/*mut T；仅在必要时使用原始指针；\n"
            "  * 字符串：优先使用 String、&str 而非 *const c_char/*mut c_char；\n"
            "  * 错误处理：考虑使用 Result<T, E> 而非 C 风格的错误码；\n"
            "  * 参数个数与顺序可以保持与 C 一致，但类型应优先考虑 Rust 的惯用法、安全性和可读性；\n"
            "- 函数签名应包含可见性修饰（pub）与函数名；类型应为 Rust 最佳实践的选择，而非简单映射 C 类型。\n"
            "- 禁止使用 extern \"C\"；函数应使用标准的 Rust 调用约定，不需要 C ABI。\n"
            "请严格按以下格式输出（JSON格式，支持jsonnet语法如尾随逗号、注释、|||分隔符多行字符串等）：\n"
            "示例1（正常函数）：\n"
            "<SUMMARY>\n{\n  \"module\": \"...\",\n  \"rust_signature\": \"...\",\n  \"notes\": \"...\"\n}\n</SUMMARY>\n"
            "示例2（资源释放类函数，可跳过实现）：\n"
            "<SUMMARY>\n{\n  \"module\": \"...\",\n  \"rust_signature\": \"...\",\n  \"skip_implementation\": true,\n  \"notes\": \"通过 RAII 自动管理，无需显式实现\"\n}\n</SUMMARY>"
        )
        return system_prompt, user_prompt, summary_prompt

    def _plan_module_and_signature(self, rec: FnRecord, c_code: str) -> Tuple[str, str, bool]:
        """调用 Agent 选择模块与签名，返回 (module_path, rust_signature, skip_implementation)，若格式不满足将自动重试直到满足"""
        crate_tree = _dir_tree(self.crate_dir)
        callees_ctx = self._collect_callees_context(rec)
        sys_p, usr_p, base_sum_p = self._build_module_selection_prompts(rec, c_code, callees_ctx, crate_tree)

        def _validate(meta: Any) -> Tuple[bool, str]:
            """基本格式检查，仅验证字段存在性，不做硬编码规则校验"""
            if not isinstance(meta, dict) or not meta:
                return False, "未解析到有效的 <SUMMARY> 中的 JSON 对象"
            module = meta.get("module")
            rust_sig = meta.get("rust_signature")
            if not isinstance(module, str) or not module.strip():
                return False, "缺少必填字段 module"
            if not isinstance(rust_sig, str) or not rust_sig.strip():
                return False, "缺少必填字段 rust_signature"
            # 路径归一化：容忍相对/简略路径，最终归一为 crate_dir 下的绝对路径（不做硬编码校验）
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
                # 将归一化后的绝对路径回写到 meta，避免后续流程二次解析歧义
                meta["module"] = str(mp)
            except Exception:
                # 路径归一化失败不影响，保留原始值
                pass
            return True, ""

        def _retry_sum_prompt(reason: str) -> str:
            return (
                base_sum_p
                + "\n\n[格式检查失败，必须重试]\n"
                + f"- 失败原因：{reason}\n"
                + "- 仅输出一个 <SUMMARY> 块；块内直接包含 JSON 对象（不需要额外的标签）；\n"
                + '- JSON 对象必须包含字段：module、rust_signature。\n'
            )

        attempt = 0
        last_reason = "未知错误"
        plan_max_retries_val = getattr(self, "plan_max_retries", 0)
        # 如果 plan_max_retries 为 0，表示无限重试
        use_direct_model = False  # 标记是否使用直接模型调用
        agent = None  # 在循环外声明，以便重试时复用
        
        # 注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表
        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
        while plan_max_retries_val == 0 or attempt < plan_max_retries_val:
            attempt += 1
            sum_p = base_sum_p if attempt == 1 else _retry_sum_prompt(last_reason)

            # 第一次创建 Agent，后续重试时复用（如果使用直接模型调用）
            # 注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表
            if agent is None or not use_direct_model:
                agent = Agent(
                    system_prompt=sys_p,
                    name="C2Rust-Function-Planner",
                    model_group=self.llm_group,
                    summary_prompt=sum_p,
                    need_summary=True,
                    auto_complete=True,
                    use_tools=["execute_script", "read_code", "retrieve_memory", "save_memory", "read_symbols"],
                    non_interactive=self.non_interactive,
                    use_methodology=False,
                    use_analysis=False,
                )
            
            if use_direct_model:
                # 格式校验失败后，直接调用模型接口
                # 构造包含摘要提示词和具体错误信息的完整提示
                error_guidance = ""
                if last_reason and last_reason != "未知错误":
                    if "JSON解析失败" in last_reason:
                        error_guidance = f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- {last_reason}\n\n请确保输出的JSON格式正确，包括正确的引号、逗号、大括号等。JSON 对象必须包含字段：module（字符串）、rust_signature（字符串）。支持jsonnet语法（如尾随逗号、注释、|||分隔符多行字符串等）。"
                    else:
                        error_guidance = f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- {last_reason}\n\n请确保输出格式正确：仅输出一个 <SUMMARY> 块，块内直接包含 JSON 对象（不需要额外的标签）；JSON 对象必须包含字段：module（字符串）、rust_signature（字符串）。支持jsonnet语法（如尾随逗号、注释、|||分隔符多行字符串等）。"
                
                full_prompt = f"{usr_p}{error_guidance}\n\n{sum_p}"
                try:
                    response = agent.model.chat_until_success(full_prompt)  # type: ignore
                    summary = response
                except Exception as e:
                    typer.secho(f"[c2rust-transpiler][plan] 直接模型调用失败: {e}，回退到 run()", fg=typer.colors.YELLOW)
                    summary = agent.run(usr_p)
            else:
                # 第一次使用 run()，让 Agent 完整运行（可能使用工具）
                summary = agent.run(usr_p)
            
            meta, parse_error = _extract_json_from_summary(str(summary or ""))
            if parse_error:
                # JSON解析失败，将错误信息反馈给模型
                typer.secho(f"[c2rust-transpiler][plan] JSON解析失败: {parse_error}", fg=typer.colors.YELLOW)
                last_reason = f"JSON解析失败: {parse_error}"
                use_direct_model = True
                # 解析失败，继续重试
                continue
            else:
                ok, reason = _validate(meta)
            if ok:
                module = str(meta.get("module") or "").strip()
                rust_sig = str(meta.get("rust_signature") or "").strip()
                skip_impl = bool(meta.get("skip_implementation") is True)
                if skip_impl:
                    notes = str(meta.get("notes") or "")
                    typer.secho(f"[c2rust-transpiler][plan] 第 {attempt} 次尝试成功: 模块={module}, 签名={rust_sig}, 跳过实现={skip_impl}", fg=typer.colors.GREEN)
                    if notes:
                        typer.secho(f"[c2rust-transpiler][plan] 跳过实现原因: {notes}", fg=typer.colors.CYAN)
                else:
                    typer.secho(f"[c2rust-transpiler][plan] 第 {attempt} 次尝试成功: 模块={module}, 签名={rust_sig}", fg=typer.colors.GREEN)
                return module, rust_sig, skip_impl
            else:
                typer.secho(f"[c2rust-transpiler][plan] 第 {attempt} 次尝试失败: {reason}", fg=typer.colors.YELLOW)
                last_reason = reason
                # 格式校验失败，后续重试使用直接模型调用
                use_direct_model = True
        
        # 规划超出重试上限：回退到兜底方案（默认模块 src/ffi.rs + 简单占位签名）
        # 注意：如果 plan_max_retries_val == 0（无限重试），理论上不应该到达这里
        try:
            crate_root = self.crate_dir.resolve()
            fallback_module = str((crate_root / "src" / "ffi.rs").resolve())
        except Exception:
            fallback_module = "src/ffi.rs"
        fallback_sig = f"pub fn {rec.name or ('fn_' + str(rec.id))}()"
        typer.secho(f"[c2rust-transpiler][plan] 超出规划重试上限({plan_max_retries_val if plan_max_retries_val > 0 else '无限'})，回退到兜底: module={fallback_module}, signature={fallback_sig}", fg=typer.colors.YELLOW)
        return fallback_module, fallback_sig, False

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



    # ========= Agent 复用与上下文拼接辅助 =========

    def _compose_prompt_with_context(self, prompt: str) -> str:
        """
        在复用Agent时，将此前构建的函数上下文头部拼接到当前提示词前，确保连续性。
        策略：
        - 每个函数生命周期内，首次调用拼接“全量头部”；
        - 后续调用仅拼接“精简头部”；
        - 如头部缺失则直接返回原提示。
        """
        # 首次发送全量上下文
        if (not getattr(self, "_current_context_full_sent", False)) and getattr(self, "_current_context_full_header", ""):
            self._current_context_full_sent = True
            return self._current_context_full_header + "\n\n" + prompt
        # 后续拼接精简上下文
        compact = getattr(self, "_current_context_compact_header", "")
        if compact:
            return compact + "\n\n" + prompt
        return prompt

    def _reset_function_context(self, rec: FnRecord, module: str, rust_sig: str, c_code: str) -> None:
        """
        初始化当前函数的上下文与复用Agent缓存。
        在单个函数实现开始时调用一次，之后复用代码编写与修复Agent/Review等Agent。
        """
        self._current_agents = {}
        self._current_function_id = rec.id

        # 汇总上下文头部，供后续复用时拼接
        callees_ctx = self._collect_callees_context(rec)
        crate_tree = _dir_tree(self.crate_dir)
        librep_ctx = rec.lib_replacement if isinstance(rec.lib_replacement, dict) else None
        # 提取编译参数
        compile_flags = self._extract_compile_flags(rec.file)

        header_lines = [
            "【当前函数上下文（复用Agent专用）】",
            f"- 函数: {rec.qname or rec.name} (id={rec.id})",
            f"- 源位置: {rec.file}:{rec.start_line}-{rec.end_line}",
            f"- 原 C 工程目录: {self.project_root.resolve()}",
            f"- 目标模块: {module}",
            f"- 建议/当前签名: {rust_sig}",
            f"- crate 根目录: {self.crate_dir.resolve()}",
            "",
            "原始C函数源码片段（只读参考）：",
            "<C_SOURCE>",
            c_code or "",
            "</C_SOURCE>",
            "",
            "被引用符号上下文：",
            json.dumps(callees_ctx, ensure_ascii=False, indent=2),
            "",
            "库替代上下文（若有）：",
            json.dumps(librep_ctx, ensure_ascii=False, indent=2),
        ]
        # 添加编译参数（如果存在）
        if compile_flags:
            header_lines.extend([
                "",
                "C文件编译参数（来自 compile_commands.json）：",
                compile_flags,
            ])
        header_lines.extend([
            "",
            "crate 目录结构（部分）：",
            "<CRATE_TREE>",
            crate_tree,
            "</CRATE_TREE>",
        ])
        # 精简头部（后续复用）
        compact_lines = [
            "【函数上下文简要（复用）】",
            f"- 函数: {rec.qname or rec.name} (id={rec.id})",
            f"- 原 C 工程目录: {self.project_root.resolve()}",
            f"- 模块: {module}",
            f"- 签名: {rust_sig}",
            f"- crate: {self.crate_dir.resolve()}",
        ]
        self._current_context_full_header = "\n".join(header_lines)
        self._current_context_compact_header = "\n".join(compact_lines)
        self._current_context_full_sent = False

        # 初始化代码生成Agent（CodeAgent），单个函数生命周期内复用
        # 注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表
        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
        # 代码生成阶段：禁用方法论和分析，仅启用强制记忆功能
        self._current_agents[f"code_agent_gen::{rec.id}"] = CodeAgent(
            need_summary=False,
            non_interactive=self.non_interactive,
            model_group=self.llm_group,
            use_methodology=False,
            use_analysis=False,
            force_save_memory=True,
        )
        # 初始化修复Agent（CodeAgent），单个函数生命周期内复用
        # 修复阶段：启用方法论、分析和强制记忆功能
        self._current_agents[f"code_agent_repair::{rec.id}"] = CodeAgent(
            need_summary=False,
            non_interactive=self.non_interactive,
            model_group=self.llm_group,
            use_methodology=True,
            use_analysis=True,
            force_save_memory=True,
        )

    def _get_generate_agent(self) -> CodeAgent:
        """
        获取代码生成Agent（CodeAgent）。若未初始化，则按当前函数id创建。
        代码生成阶段：禁用方法论和分析，仅启用强制记忆功能。
        注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表。
        """
        fid = self._current_function_id
        key = f"code_agent_gen::{fid}" if fid is not None else "code_agent_gen::default"
        agent = self._current_agents.get(key)
        if agent is None:
            # 注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表
            # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
            # 代码生成Agent禁用方法论和分析，仅启用强制记忆功能
            agent = CodeAgent(
                need_summary=False,
                non_interactive=self.non_interactive,
                model_group=self.llm_group,
                use_methodology=False,
                use_analysis=False,
                force_save_memory=True,
            )
            self._current_agents[key] = agent
        return agent

    def _get_repair_agent(self) -> CodeAgent:
        """
        获取修复Agent（CodeAgent）。若未初始化，则按当前函数id创建。
        修复阶段：启用方法论、分析和强制记忆功能。
        注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表。
        """
        fid = self._current_function_id
        key = f"code_agent_repair::{fid}" if fid is not None else "code_agent_repair::default"
        agent = self._current_agents.get(key)
        if agent is None:
            # 注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表
            # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
            # 修复Agent启用方法论、分析和强制记忆功能
            agent = CodeAgent(
                need_summary=False,
                non_interactive=self.non_interactive,
                model_group=self.llm_group,
                use_methodology=True,
                use_analysis=True,
                force_save_memory=True,
            )
            self._current_agents[key] = agent
        return agent

    def _refresh_compact_context(self, rec: FnRecord, module: str, rust_sig: str) -> None:
        """
        刷新精简上下文头部（在 sig-fix/ensure-impl 后调用，保证后续提示一致）。
        仅更新精简头部，不影响已发送的全量头部。
        """
        try:
            compact_lines = [
                "【函数上下文简要（复用）】",
                f"- 函数: {rec.qname or rec.name} (id={rec.id})",
                f"- 模块: {module}",
                f"- 签名: {rust_sig}",
                f"- crate: {self.crate_dir.resolve()}",
            ]
            self._current_context_compact_header = "\n".join(compact_lines)
        except Exception:
            pass

    # ========= 代码生成与修复 =========

    def _build_generate_impl_prompt(
        self, rec: FnRecord, c_code: str, module: str, rust_sig: str, unresolved: List[str]
    ) -> str:
        """
        构建代码生成提示词。
        
        返回完整的提示词字符串。
        """
        symbols_path = str((self.data_dir / "symbols.jsonl").resolve())
        requirement_lines = [
            f"目标：在 crate 目录 {self.crate_dir.resolve()} 的 {module} 中，为 C 函数 {rec.qname or rec.name} 生成对应的 Rust 实现，并同时生成测试用例。",
            "要求：",
            f"- 函数签名（建议）：{rust_sig}",
            f"- 原 C 工程目录位置：{self.project_root.resolve()}",
            "- 若 module 文件不存在则新建；为所在模块添加必要的 mod 声明（若需要）；",
            "- 若已有函数占位/实现，尽量最小修改，不要破坏现有代码；",
            "- 你可以参考原 C 函数的关联实现（如同文件/同模块的相关辅助函数、内联实现、宏与注释等），在保持语义一致的前提下以符合 Rust 风格的方式实现；避免机械复制粘贴；",
            f"- 如需参考原 C 工程中的其他文件，可在原 C 工程目录 {self.project_root.resolve()} 中查找；",
            "- 禁止在函数实现中使用 todo!/unimplemented! 作为占位；对于尚未实现的被调符号，请阅读其原 C 实现并在本次一并补齐等价的 Rust 实现，避免遗留占位；",
            "- 为保证行为等价，禁止使用占位返回或随意默认值；必须实现与 C 语义等价的返回逻辑，不得使用 panic!/todo!/unimplemented!；",
            "- **必须同时生成测试用例**：在生成函数实现的同时，必须在同一文件中添加测试模块（#[cfg(test)] mod tests），并编写至少一个可编译通过的单元测试；",
            "- **资源释放类函数特殊处理**：如果函数是资源释放类（如文件关闭 fclose、内存释放 free、句柄释放、资源清理等），在 Rust 中通常通过 RAII（Drop trait）自动管理，可以：",
            "  * 提供空实现（函数体为空或仅返回成功状态），并在文档注释中说明资源通过 RAII 自动管理；",
            "  * 或者完全跳过实现，仅保留函数签名（如果调用方不需要显式调用）；",
            "  * 在函数文档注释中明确说明：\"此函数在 Rust 中通过 RAII 自动管理资源，无需显式调用\"；",
            "- 不要删除或移动其他无关文件。",
            "",
            "编码原则与规范：",
            "- 函数接口设计应遵循 Rust 最佳实践，不需要兼容 C 的数据类型；优先使用 Rust 原生类型和惯用法：",
            "  * 基本类型：使用 i32/u32/i64/u64/isize/usize/f32/f64 等原生 Rust 类型，而非 core::ffi::c_* 或 libc::c_*；",
            "  * 指针/引用：优先使用引用 &T/&mut T 或切片 &[T]/&mut [T]，而非原始指针 *const T/*mut T；仅在必要时使用原始指针；",
            "  * 字符串：优先使用 String、&str 而非 *const c_char/*mut c_char；",
            "  * 错误处理：如适用，考虑使用 Result<T, E> 而非 C 风格的错误码；",
            "  * 禁止使用 extern \"C\"；函数应使用标准的 Rust 调用约定，不需要 C ABI；",
            "- 保持最小变更，避免无关重构与格式化；禁止批量重排/重命名/移动文件；",
            "- 命名遵循Rust惯例（函数/模块蛇形命名），公共API使用pub；",
            "- 优先使用安全Rust；如需unsafe，将范围最小化并添加注释说明原因与SAFETY保证；",
            "- 错误处理：遵循 C 语义保持等价行为（逻辑一致性），但在类型设计上优先使用 Rust 惯用法；避免 panic!/unwrap()；",
            "- 实现中禁止使用 todo!/unimplemented! 占位；对于尚未实现的被调符号，应基于其 C 源码补齐等价 Rust 实现；",
            "- 返回值必须与 C 语义等价，不得使用占位返回或随意默认值；避免 panic!/todo!/unimplemented!；",
            "- 若依赖未实现符号，请通过 read_symbols/read_code 获取其 C 源码并生成等价的 Rust 实现（可放置在同一模块或合理模块），而不是使用 todo!；",
            "- **强烈建议使用 retrieve_memory 工具召回已保存的函数实现记忆**：在实现之前，先尝试使用 retrieve_memory 工具检索相关的函数实现记忆，这些记忆可能包含之前已实现的类似函数、设计决策、实现模式等有价值的信息，可以显著提高实现效率和准确性；",
            "- 文档：为新增函数添加简要文档注释，注明来源C函数与意图；",
            "- 注释规范：所有代码注释（包括文档注释、行内注释、块注释等）必须使用中文；",
            "- 导入：禁止使用 use ...::* 通配；仅允许精确导入所需符号",
            "- 依赖管理：如引入新的外部 crate 或需要启用 feature，请同步更新 Cargo.toml 的 [dependencies]/[dev-dependencies]/[features]，避免未声明依赖导致构建失败；版本号可使用兼容范围（如 ^x.y）或默认值；",
            *([f"- **禁用库约束**：禁止在实现中使用以下库：{', '.join(self.disabled_libraries)}。如果这些库在 Cargo.toml 中已存在，请移除相关依赖；如果实现需要使用这些库的功能，请使用标准库或其他允许的库替代。"] if self.disabled_libraries else []),
            "",
            "【重要：资源释放类函数处理】",
            "- 识别标准：如果函数名或功能属于以下类别，通常可以通过 RAII 自动管理：",
            "  * 文件关闭：fclose、close、file_close 等；",
            "  * 内存释放：free、dealloc、memory_free 等；",
            "  * 句柄/资源释放：handle_close、resource_free、cleanup 等；",
            "  * 锁释放：mutex_unlock、lock_release 等（Rust 中通过作用域自动释放）；",
            "  * 其他资源清理函数；",
            "- 实现策略：",
            "  * 如果函数签名需要保留（用于兼容性），提供空实现或仅返回成功状态；",
            "  * 在函数文档注释中明确说明：\"此函数在 Rust 中通过 RAII（Drop trait）自动管理资源，无需显式调用。保留此函数仅用于 API 兼容性。\"；",
            "  * 如果函数签名不需要保留，可以完全跳过实现；",
            "  * 对于需要返回值的函数（如错误码），可以返回成功状态（如 Ok(()) 或 0）；",
            "- 测试处理：对于资源释放类函数，测试可以非常简单（如仅验证函数可以调用而不崩溃），或可以跳过测试（在文档注释中说明原因）；",
            "",
            "【重要：测试用例生成要求】",
            "- **必须同时生成测试用例**：在生成函数实现的同时，必须在同一文件中添加测试模块（#[cfg(test)] mod tests），并编写至少一个可编译通过的单元测试；",
            "- 测试函数命名：建议命名为 test_<函数名>_basic 或 test_<函数名>；",
            "- 测试要求：",
            "  * 测试必须能够编译通过，避免使用 panic!/todo!/unimplemented!；",
            "  * unsafe 函数必须以 unsafe 块调用；",
            "  * 必要时使用占位参数（如 0、core::ptr::null()/null_mut()、默认值、空切片等）以保证测试能够编译和执行；",
            "  * 测试应调用函数并验证基本行为（至少验证函数能够执行而不崩溃）；",
            "- 测试设计文档：在测试函数顶部使用文档注释（///）简要说明测试用例设计，包括：输入构造、预置条件、期望行为（或成功执行）、边界/异常不作为否决项；注释内容仅用于说明，不影响实现；",
            "- 可测试性判断：",
            "  * 若函数可测试（无需外部环境/IO/网络/全局状态），必须生成测试；",
            "  * 若函数依赖外部环境或调用未实现符号，仍应尝试生成基本测试（使用占位参数），并在函数文档注释中注明测试限制；",
            "  * 仅在函数完全无法测试时（如需要特定硬件、网络连接等），才可跳过测试生成，但必须在函数文档注释中详细说明不可测试原因；",
            "",
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
            "【工具使用建议】",
            "1. 召回记忆（推荐优先使用）：",
            "   - 工具: retrieve_memory",
            "   - 用途: 检索已保存的函数实现记忆，可能包含类似函数的实现模式、设计决策、关键逻辑等",
            "   - 建议标签: 使用 'c2rust', 'function_impl', 函数名等作为检索标签",
            "   - 示例: 在实现之前，先检索与当前函数或依赖函数相关的记忆，参考已有的实现模式",
            "",
            "2. 符号表检索：",
            "   - 工具: read_symbols",
            "   - 用途: 按需获取指定符号记录",
            "   - 参数示例(JSON):",
            f"     {{\"symbols_file\": \"{symbols_path}\", \"symbols\": [\"符号1\", \"符号2\"]}}",
            "",
            "3. 代码读取：",
            "   - 工具: read_code",
            "   - 用途: 读取 C 源码实现或 Rust 模块文件",
            "",
            "尚未转换的被调符号如下（请阅读这些符号的 C 源码并生成等价的 Rust 实现；必要时新增模块或签名）：",
            *[f"- {s}" for s in (unresolved or [])],
            "",
            "【重要：依赖检查与实现要求】",
            "在实现函数之前，请务必检查以下内容：",
            "1. 检查当前函数是否已实现：",
            f"   - 在目标模块 {module} 中查找函数 {rec.qname or rec.name} 的实现",
            "   - 如果已存在实现，检查其是否完整且正确",
            "2. 检查所有依赖函数是否已实现：",
            "   - 遍历当前函数调用的所有被调函数（包括直接调用和间接调用）",
            "   - 对于每个被调函数，检查其在 Rust crate 中是否已有完整实现",
            "   - 可以使用 read_code 工具读取相关模块文件进行检查",
            "   - 可以使用 retrieve_memory 工具检索已保存的函数实现记忆",
            "3. 对于未实现的依赖函数：",
            "   - 使用 read_symbols 工具获取其 C 源码和符号信息",
            "   - 使用 read_code 工具读取其 C 源码实现",
            "   - 在本次实现中一并补齐这些依赖函数的 Rust 实现",
            "   - 根据依赖关系选择合适的模块位置（可在同一模块或合理的新模块中）",
            "   - 确保所有依赖函数都有完整实现，禁止使用 todo!/unimplemented! 占位",
            "4. 实现顺序：",
            "   - 优先实现最底层的依赖函数（不依赖其他未实现函数的函数）",
            "   - 然后实现依赖这些底层函数的函数",
            "   - 最后实现当前目标函数",
            "5. 验证：",
            "   - 确保当前函数及其所有依赖函数都已完整实现",
            "   - 确保没有遗留的 todo!/unimplemented! 占位",
            "   - 确保所有函数调用都能正确解析",
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
        # 添加编译参数（如果存在）
        compile_flags = self._extract_compile_flags(rec.file)
        if compile_flags:
            requirement_lines.extend([
                "",
                "C文件编译参数（来自 compile_commands.json）：",
                compile_flags,
                "",
            ])
        requirement_lines.extend([
            "",
            "【重要：记忆保存要求】",
            "在完成函数实现之后，请务必使用 save_memory 工具记录以下关键信息，以便后续检索和复用：",
            f"- 函数名称：{rec.qname or rec.name} (id={rec.id})",
            f"- 源文件位置：{rec.file}:{rec.start_line}-{rec.end_line}",
            f"- 目标模块：{module}",
            f"- Rust 函数签名：{rust_sig}",
            "- C 函数的核心功能与语义",
            "- 关键实现细节与设计决策",
            "- 依赖关系与调用链",
            "- 类型转换与边界处理要点",
            "- 错误处理策略",
            "- 实际实现的 Rust 代码要点与关键逻辑",
            "记忆标签建议：使用 'c2rust', 'function_impl', 函数名等作为标签，便于后续检索。",
            "请在完成代码实现之后保存记忆，记录本次实现的完整信息。",
        ])
        return "\n".join(requirement_lines)

    def _codeagent_generate_impl(self, rec: FnRecord, c_code: str, module: str, rust_sig: str, unresolved: List[str]) -> None:
        """
        使用 CodeAgent 生成/更新目标模块中的函数实现。
        约束：最小变更，生成可编译的占位实现，尽可能保留后续细化空间。
        """
        # 构建提示词
        prompt = self._build_generate_impl_prompt(rec, c_code, module, rust_sig, unresolved)
        
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
        
        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
        agent = self._get_generate_agent()  # 使用代码生成Agent（禁用分析和方法论）
        agent.run(self._compose_prompt_with_context(prompt), prefix="[c2rust-transpiler][gen]", suffix="")

    def _extract_rust_fn_name_from_sig(self, rust_sig: str) -> str:
        """
        从 rust 签名中提取函数名，支持生命周期参数和泛型参数。
        例如: 'pub fn foo(a: i32) -> i32 { ... }' -> 'foo'
        例如: 'pub fn foo<'a>(bzf: &'a mut BzFile) -> Result<&'a [u8], BzError>' -> 'foo'
        """
        # 支持生命周期参数和泛型参数：fn name<'a, T>(...)
        m = re.search(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^>]+>)?\s*\(", rust_sig or "")
        return m.group(1) if m else ""

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
            parts = [p for p in inside.split("/") if p]  # 过滤空字符串
            if parts[-1].endswith(".rs"):
                if parts[-1] in ("lib.rs", "main.rs"):
                    return
                child = parts[-1][:-3]  # 去掉 .rs
                if len(parts) > 1:
                    start_dir = crate_root / "src" / "/".join(parts[:-1])
                else:
                    start_dir = crate_root / "src"
                # 确保 start_dir 在 crate/src 下
                try:
                    start_dir_rel = start_dir.relative_to(crate_root)
                    if not str(start_dir_rel).replace("\\", "/").startswith("src/"):
                        return
                except ValueError:
                    return
                # 在当前目录的 mod.rs 确保 pub mod <child>
                if start_dir.name != "src":
                    self._ensure_mod_rs_decl(start_dir, child)
                # 向上逐级确保父目录对当前目录的 pub mod 声明
                cur_dir = start_dir
            else:
                # 末尾为目录（mod.rs 情况）：确保父目录对该目录 pub mod
                if parts:
                    cur_dir = crate_root / "src" / "/".join(parts)
                    # 确保 cur_dir 在 crate/src 下
                    try:
                        cur_dir_rel = cur_dir.relative_to(crate_root)
                        if not str(cur_dir_rel).replace("\\", "/").startswith("src/"):
                            return
                    except ValueError:
                        return
                else:
                    return
            # 逐级向上到 src 根（不修改 src/mod.rs，顶层由 lib.rs 公开）
            while True:
                parent = cur_dir.parent
                if not parent.exists():
                    break
                # 确保不超过 crate 根目录
                try:
                    parent.relative_to(crate_root)
                except ValueError:
                    # parent 不在 crate_root 下，停止向上遍历
                    break
                if parent.name == "src":
                    # 顶层由 _ensure_top_level_pub_mod 负责
                    break
                # 在 parent/mod.rs 确保 pub mod <cur_dir.name>
                # 确保 parent 在 crate/src 下
                try:
                    parent_rel = parent.relative_to(crate_root)
                    if str(parent_rel).replace("\\", "/").startswith("src/"):
                        self._ensure_mod_rs_decl(parent, cur_dir.name)
                except (ValueError, Exception):
                    # parent 不在 crate/src 下，跳过
                    break
                cur_dir = parent
        except Exception:
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

        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
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
            agent = self._get_repair_agent()
            agent.run(self._compose_prompt_with_context(prompt), prefix=f"[c2rust-transpiler][todo-fix:{symbol}]", suffix="")

    def _classify_rust_error(self, text: str) -> List[str]:
        """
        朴素错误分类，用于提示 CodeAgent 聚焦修复：
        - missing_import: unresolved import / not found in this scope / cannot find ...
        - type_mismatch: mismatched types / expected ... found ...
        - visibility: private module/field/function
        - borrow_checker: does not live long enough / borrowed data escapes / cannot borrow as mutable
        - dependency_missing: failed to select a version / could not find crate
        - module_not_found: file not found for module / unresolved module
        """
        tags: List[str] = []
        t = (text or "").lower()
        def has(s: str) -> bool:
            return s in t
        if ("unresolved import" in t) or ("not found in this scope" in t) or ("cannot find" in t) or ("use of undeclared crate or module" in t):
            tags.append("missing_import")
        if ("mismatched types" in t) or ("expected" in t and "found" in t):
            tags.append("type_mismatch")
        if ("private" in t and "module" in t) or ("private" in t and "field" in t) or ("private" in t and "function" in t):
            tags.append("visibility")
        if ("does not live long enough" in t) or ("borrowed data escapes" in t) or ("cannot borrow" in t):
            tags.append("borrow_checker")
        if ("failed to select a version" in t) or ("could not find crate" in t) or ("no matching package named" in t):
            tags.append("dependency_missing")
        if ("file not found for module" in t) or ("unresolved module" in t):
            tags.append("module_not_found")
        # 去重
        try:
            tags = list(dict.fromkeys(tags))
        except Exception:
            tags = list(set(tags))
        return tags

    def _get_current_function_context(self) -> Tuple[Dict[str, Any], str, str, str]:
        """
        获取当前函数上下文信息。
        返回: (curr, sym_name, src_loc, c_code)
        """
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
        return curr, sym_name, src_loc, c_code

    def _build_repair_prompt_base(
        self, stage: str, tags: List[str], sym_name: str, src_loc: str, c_code: str,
        curr: Dict[str, Any], symbols_path: str, include_output_patch_hint: bool = False
    ) -> List[str]:
        """
        构建修复提示词的基础部分。
        
        返回基础行列表。
        """
        base_lines = [
            f"目标：以最小的改动修复问题，使 `{stage}` 命令可以通过。",
            f"阶段：{stage}",
            f"错误分类标签: {tags}",
            "允许的修复：修正入口/模块声明/依赖；对入口文件与必要mod.rs进行轻微调整；在缺失/未实现的被调函数导致错误时，一并补齐这些依赖的Rust实现（可新增合理模块/函数）；避免大范围改动。",
            "- 保持最小改动，避免与错误无关的重构或格式化；",
            "- 如构建失败源于缺失或未实现的被调函数/依赖，请阅读其 C 源码并在本次一并补齐等价的 Rust 实现；必要时可在合理的模块中新建函数；",
            "- 禁止使用 todo!/unimplemented! 作为占位；",
            "- 可使用工具 read_symbols/read_code 获取依赖符号的 C 源码与位置以辅助实现；仅精确导入所需符号，避免通配；",
            "- **强烈建议使用 retrieve_memory 工具召回已保存的函数实现记忆**：在修复之前，先尝试使用 retrieve_memory 工具检索相关的函数实现记忆，这些记忆可能包含之前已实现的类似函数、设计决策、实现模式等有价值的信息，可以显著提高修复效率和准确性；",
            f"- 注释规范：所有代码注释（包括文档注释、行内注释、块注释等）必须使用中文；",
            f"- 依赖管理：如修复中引入新的外部 crate 或需要启用 feature，请同步更新 Cargo.toml 的 [dependencies]/[dev-dependencies]/[features]{('，避免未声明依赖导致构建失败；版本号可使用兼容范围（如 ^x.y）或默认值' if stage == 'cargo test' else '')}；",
            *([f"- **禁用库约束**：禁止在修复中使用以下库：{', '.join(self.disabled_libraries)}。如果这些库在 Cargo.toml 中已存在，请移除相关依赖；如果修复需要使用这些库的功能，请使用标准库或其他允许的库替代。"] if self.disabled_libraries else []),
            "",
            "【重要：依赖检查与实现要求】",
            "在修复问题之前，请务必检查以下内容：",
            "1. 检查当前函数是否已完整实现：",
            f"   - 在目标模块中查找函数 {sym_name} 的实现",
            "   - 如果已存在实现，检查其是否完整且正确",
            "2. 检查所有依赖函数是否已实现：",
            "   - 分析构建错误，识别所有缺失或未实现的被调函数",
            "   - 遍历当前函数调用的所有被调函数（包括直接调用和间接调用）",
            "   - 对于每个被调函数，检查其在 Rust crate 中是否已有完整实现",
            "   - 可以使用 read_code 工具读取相关模块文件进行检查",
            "   - 可以使用 retrieve_memory 工具检索已保存的函数实现记忆",
            "3. 对于未实现的依赖函数：",
            "   - 使用 read_symbols 工具获取其 C 源码和符号信息",
            "   - 使用 read_code 工具读取其 C 源码实现",
            "   - 在本次修复中一并补齐这些依赖函数的 Rust 实现",
            "   - 根据依赖关系选择合适的模块位置（可在同一模块或合理的新模块中）",
            "   - 确保所有依赖函数都有完整实现，禁止使用 todo!/unimplemented! 占位",
            "4. 实现顺序：",
            "   - 优先实现最底层的依赖函数（不依赖其他未实现函数的函数）",
            "   - 然后实现依赖这些底层函数的函数",
            "   - 最后修复当前目标函数",
            "5. 验证：",
            "   - 确保当前函数及其所有依赖函数都已完整实现",
            "   - 确保没有遗留的 todo!/unimplemented! 占位",
            "   - 确保所有函数调用都能正确解析",
        ]
        if include_output_patch_hint:
            base_lines.append("- 请仅输出补丁，不要输出解释或多余文本。")
        base_lines.extend([
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
        ])
        # 添加编译参数（如果存在）
        c_file_path = curr.get("file") or ""
        if c_file_path:
            compile_flags = self._extract_compile_flags(c_file_path)
            if compile_flags:
                base_lines.extend([
                    "",
                    "C文件编译参数（来自 compile_commands.json）：",
                    compile_flags,
                ])
        base_lines.extend([
            "",
            "【工具使用建议】",
            "1. 召回记忆（推荐优先使用）：",
            "   - 工具: retrieve_memory",
            "   - 用途: 检索已保存的函数实现记忆，可能包含类似函数的实现模式、设计决策、关键逻辑等",
            "   - 建议标签: 使用 'c2rust', 'function_impl', 函数名等作为检索标签",
            "   - 示例: 检索与当前函数相关的记忆，特别是已实现的依赖函数记忆",
            "",
            "2. 符号表检索：",
            "   - 工具: read_symbols",
            "   - 用途: 定位或交叉验证 C 符号位置",
            "   - 参数示例(JSON):",
            f"     {{\"symbols_file\": \"{symbols_path}\", \"symbols\": [\"{sym_name}\"]}}",
            "",
            "3. 代码读取：",
            "   - 工具: read_code",
            "   - 用途: 读取 C 源码实现或 Rust 模块文件",
            "",
            "上下文：",
            f"- crate 根目录路径: {self.crate_dir.resolve()}",
        ])
        if stage == "cargo check":
            base_lines.append(f"- 包名称（用于 cargo -p）: {self.crate_dir.name}")
        else:
            base_lines.append(f"- 包名称（用于 cargo build -p）: {self.crate_dir.name}")
        return base_lines

    def _build_repair_prompt_stage_section(
        self, stage: str, output: str, command: Optional[str] = None
    ) -> List[str]:
        """
        构建修复提示词的阶段特定部分（测试或检查）。
        
        返回阶段特定的行列表。
        """
        section_lines: List[str] = []
        if stage == "cargo test":
            section_lines.extend([
                "",
                "【测试失败信息】",
                "以下输出来自 `cargo test` 命令，包含测试执行结果和失败详情：",
                "- 如果看到测试用例名称和断言失败，说明测试逻辑或实现有问题",
                "- 如果看到编译错误，说明代码存在语法或类型错误",
                "- 请仔细阅读失败信息，包括：测试用例名称、断言失败位置、期望值与实际值、堆栈跟踪等",
                "",
            ])
            if command:
                section_lines.append(f"执行的命令：{command}")
                section_lines.append("提示：如果不相信上述命令执行结果，可以使用 execute_script 工具自己执行一次该命令进行验证。")
            section_lines.extend([
                "",
                "请阅读以下测试失败信息并进行必要修复：",
                "<TEST_FAILURE>",
                output,
                "</TEST_FAILURE>",
                "",
                "修复后请再次执行 `cargo test` 进行验证。",
            ])
        else:
            section_lines.extend([
                "",
                "请阅读以下构建错误并进行必要修复：",
            ])
            if command:
                section_lines.append(f"执行的命令：{command}")
                section_lines.append("提示：如果不相信上述命令执行结果，可以使用 execute_script 工具自己执行一次该命令进行验证。")
            section_lines.extend([
                "",
                "<BUILD_ERROR>",
                output,
                "</BUILD_ERROR>",
                "",
                "修复后请再次执行 `cargo check` 验证，后续将自动运行 `cargo test`。",
            ])
        return section_lines

    def _build_repair_prompt(self, stage: str, output: str, tags: List[str], sym_name: str, src_loc: str, c_code: str, curr: Dict[str, Any], symbols_path: str, include_output_patch_hint: bool = False, command: Optional[str] = None) -> str:
        """
        构建修复提示词。
        
        Args:
            stage: 阶段名称（"cargo check" 或 "cargo test"）
            output: 构建错误输出
            tags: 错误分类标签
            sym_name: 符号名称
            src_loc: 源文件位置
            c_code: C 源码片段
            curr: 当前进度信息
            symbols_path: 符号表文件路径
            include_output_patch_hint: 是否包含"仅输出补丁"提示（test阶段需要）
            command: 执行的命令（可选）
        """
        base_lines = self._build_repair_prompt_base(
            stage, tags, sym_name, src_loc, c_code, curr, symbols_path, include_output_patch_hint
        )
        stage_lines = self._build_repair_prompt_stage_section(stage, output, command)
        return "\n".join(base_lines + stage_lines)

    def _detect_crate_kind(self) -> str:
        """
        检测 crate 类型：lib、bin 或 mixed。
        判定规则（尽量保守，避免误判）：
        - 若存在 src/lib.rs 或 Cargo.toml 中包含 [lib]，视为包含 lib
        - 若存在 src/main.rs 或 Cargo.toml 中包含 [[bin]]（或 [bin] 兼容），视为包含 bin
        - 同时存在则返回 mixed
        - 两者都不明确时，默认返回 lib（与默认模版一致）
        """
        try:
            cargo_path = (self.crate_dir / "Cargo.toml").resolve()
            txt = ""
            if cargo_path.exists():
                try:
                    txt = cargo_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    txt = ""
            txt_lower = txt.lower()
            has_lib = (self.crate_dir / "src" / "lib.rs").exists() or bool(re.search(r"(?m)^\s*\[lib\]\s*$", txt_lower))
            # 兼容：[[bin]] 为数组表，极少数项目也会写成 [bin]
            has_bin = (self.crate_dir / "src" / "main.rs").exists() or bool(re.search(r"(?m)^\s*\[\[bin\]\]\s*$", txt_lower) or re.search(r"(?m)^\s*\[bin\]\s*$", txt_lower))
            if has_lib and has_bin:
                return "mixed"
            if has_bin:
                return "bin"
            if has_lib:
                return "lib"
        except Exception:
            pass
        # 默认假设为 lib
        return "lib"

    def _get_crate_commit_hash(self) -> Optional[str]:
        """获取 crate 目录的当前 commit id"""
        try:
            # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
            commit_hash = get_latest_commit_hash()
            return commit_hash if commit_hash else None
        except Exception:
            return None

    def _reset_to_commit(self, commit_hash: str) -> bool:
        """回退 crate 目录到指定的 commit"""
        try:
            # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
            # 检查是否是 git 仓库
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                # 不是 git 仓库，无法回退
                return False
            
            # 执行硬重置
            result = subprocess.run(
                ["git", "reset", "--hard", commit_hash],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                # 清理未跟踪的文件
                subprocess.run(
                    ["git", "clean", "-fd"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                return True
            return False
        except Exception:
            return False

    def _run_cargo_check_and_fix(self, workspace_root: str, check_iter: int, test_iter: int) -> Tuple[bool, Optional[bool]]:
        """
        运行 cargo check 并在失败时修复。
        
        Returns:
            (是否成功, 是否需要回退重新开始，None表示需要回退)
        """
        res_check = subprocess.run(
            ["cargo", "check", "-q"],
            capture_output=True,
            text=True,
            check=False,
            cwd=workspace_root,
        )
        if res_check.returncode != 0:
            output = (res_check.stdout or "") + "\n" + (res_check.stderr or "")
            limit_info = f" (上限: {self.check_max_retries if self.check_max_retries > 0 else '无限'})" if check_iter % 10 == 0 or check_iter == 1 else ""
            typer.secho(f"[c2rust-transpiler][build] cargo check 失败 (第 {check_iter} 次尝试{limit_info})。", fg=typer.colors.RED)
            typer.secho(output, fg=typer.colors.RED)
            # 达到上限则记录并退出（0表示无限重试）
            maxr = self.check_max_retries
            if maxr > 0 and check_iter >= maxr:
                typer.secho(f"[c2rust-transpiler][build] 已达到最大重试次数上限({maxr})，停止构建修复循环。", fg=typer.colors.RED)
                try:
                    cur = self.progress.get("current") or {}
                    metrics = cur.get("metrics") or {}
                    metrics["check_attempts"] = int(check_iter)
                    metrics["test_attempts"] = int(test_iter)
                    cur["metrics"] = metrics
                    cur["impl_verified"] = False
                    cur["failed_stage"] = "check"
                    err_summary = (output or "").strip()
                    if len(err_summary) > ERROR_SUMMARY_MAX_LENGTH:
                        err_summary = err_summary[:ERROR_SUMMARY_MAX_LENGTH] + "...(truncated)"
                    cur["last_build_error"] = err_summary
                    self.progress["current"] = cur
                    self._save_progress()
                except Exception:
                    pass
                return (False, False)
            # 提示修复（分类标签）
            tags = self._classify_rust_error(output)
            symbols_path = str((self.data_dir / "symbols.jsonl").resolve())
            curr, sym_name, src_loc, c_code = self._get_current_function_context()
            repair_prompt = self._build_repair_prompt(
                stage="cargo check",
                output=output,
                tags=tags,
                sym_name=sym_name,
                src_loc=src_loc,
                c_code=c_code,
                curr=curr,
                symbols_path=symbols_path,
                include_output_patch_hint=False,
                command="cargo check -q",
            )
            # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
            agent = self._get_repair_agent()
            agent.run(self._compose_prompt_with_context(repair_prompt), prefix=f"[c2rust-transpiler][build-fix iter={check_iter}][check]", suffix="")
            # 修复后进行轻量验证：检查语法是否正确
            res_verify = subprocess.run(
                ["cargo", "check", "--message-format=short", "-q"],
                capture_output=True,
                text=True,
                check=False,
                cwd=workspace_root,
            )
            if res_verify.returncode == 0:
                typer.secho("[c2rust-transpiler][build] 修复后验证通过，继续构建循环", fg=typer.colors.GREEN)
                # 修复成功，重置连续失败计数
                self._consecutive_fix_failures = 0
                return (False, False)  # 需要继续循环
            else:
                typer.secho("[c2rust-transpiler][build] 修复后验证仍有错误，将在下一轮循环中处理", fg=typer.colors.YELLOW)
                # 修复失败，增加连续失败计数
                self._consecutive_fix_failures += 1
                # 检查是否需要回退
                if self._consecutive_fix_failures >= CONSECUTIVE_FIX_FAILURE_THRESHOLD and self._current_function_start_commit:
                    typer.secho(f"[c2rust-transpiler][build] 连续修复失败 {self._consecutive_fix_failures} 次，回退到函数开始时的 commit: {self._current_function_start_commit}", fg=typer.colors.RED)
                    if self._reset_to_commit(self._current_function_start_commit):
                        typer.secho("[c2rust-transpiler][build] 已回退到函数开始时的 commit，将重新开始处理该函数", fg=typer.colors.YELLOW)
                        # 返回特殊值，表示需要重新开始
                        return (False, None)  # type: ignore
                    else:
                        typer.secho("[c2rust-transpiler][build] 回退失败，继续尝试修复", fg=typer.colors.YELLOW)
                return (False, False)  # 需要继续循环
        return (True, False)  # check 成功

    def _run_cargo_test_and_fix(self, workspace_root: str, check_iter: int, test_iter: int) -> Tuple[bool, Optional[bool]]:
        """
        运行 cargo test 并在失败时修复。
        
        Returns:
            (是否成功, 是否需要回退重新开始，None表示需要回退)
        """
        # 测试失败时需要详细输出，移除 -q 参数以获取完整的测试失败信息（包括堆栈跟踪、断言详情等）
        res_test = subprocess.run(
            ["cargo", "test", "--", "--nocapture"],
            capture_output=True,
            text=True,
            check=False,
            cwd=workspace_root,
        )
        if res_test.returncode == 0:
            typer.secho("[c2rust-transpiler][build] Cargo 测试通过。", fg=typer.colors.GREEN)
            # 测试通过，重置连续失败计数
            self._consecutive_fix_failures = 0
            try:
                cur = self.progress.get("current") or {}
                metrics = cur.get("metrics") or {}
                metrics["check_attempts"] = int(check_iter)
                metrics["test_attempts"] = int(test_iter)
                cur["metrics"] = metrics
                cur["impl_verified"] = True
                cur["failed_stage"] = None
                self.progress["current"] = cur
                self._save_progress()
            except Exception:
                pass
            return (True, False)

        # 测试失败
        output = (res_test.stdout or "") + "\n" + (res_test.stderr or "")
        limit_info = f" (上限: {self.test_max_retries if self.test_max_retries > 0 else '无限'})" if test_iter % 10 == 0 or test_iter == 1 else ""
        typer.secho(f"[c2rust-transpiler][build] Cargo 测试失败 (第 {test_iter} 次尝试{limit_info})。", fg=typer.colors.RED)
        typer.secho(output, fg=typer.colors.RED)
        maxr = self.test_max_retries
        if maxr > 0 and test_iter >= maxr:
            typer.secho(f"[c2rust-transpiler][build] 已达到最大重试次数上限({maxr})，停止构建修复循环。", fg=typer.colors.RED)
            try:
                cur = self.progress.get("current") or {}
                metrics = cur.get("metrics") or {}
                metrics["check_attempts"] = int(check_iter)
                metrics["test_attempts"] = int(test_iter)
                cur["metrics"] = metrics
                cur["impl_verified"] = False
                cur["failed_stage"] = "test"
                err_summary = (output or "").strip()
                if len(err_summary) > ERROR_SUMMARY_MAX_LENGTH:
                    err_summary = err_summary[:ERROR_SUMMARY_MAX_LENGTH] + "...(truncated)"
                cur["last_build_error"] = err_summary
                self.progress["current"] = cur
                self._save_progress()
            except Exception:
                pass
            return (False, False)

        # 构建失败（测试阶段）修复
        tags = self._classify_rust_error(output)
        symbols_path = str((self.data_dir / "symbols.jsonl").resolve())
        curr, sym_name, src_loc, c_code = self._get_current_function_context()
        repair_prompt = self._build_repair_prompt(
            stage="cargo test",
            output=output,
            tags=tags,
            sym_name=sym_name,
            src_loc=src_loc,
            c_code=c_code,
            curr=curr,
            symbols_path=symbols_path,
            include_output_patch_hint=True,
            command="cargo test -- --nocapture",
        )
        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
        agent = self._get_repair_agent()
        agent.run(self._compose_prompt_with_context(repair_prompt), prefix=f"[c2rust-transpiler][build-fix iter={test_iter}][test]", suffix="")
        # 修复后进行轻量验证：检查语法是否正确
        res_verify = subprocess.run(
            ["cargo", "test", "--message-format=short", "-q", "--no-run"],
            capture_output=True,
            text=True,
            check=False,
            cwd=workspace_root,
        )
        if res_verify.returncode == 0:
            typer.secho("[c2rust-transpiler][build] 修复后验证通过，继续构建循环", fg=typer.colors.GREEN)
            # 修复成功，重置连续失败计数
            self._consecutive_fix_failures = 0
            return (False, False)  # 需要继续循环
        else:
            typer.secho("[c2rust-transpiler][build] 修复后验证仍有错误，将在下一轮循环中处理", fg=typer.colors.YELLOW)
            # 修复失败，增加连续失败计数
            self._consecutive_fix_failures += 1
            # 检查是否需要回退
            if self._consecutive_fix_failures >= CONSECUTIVE_FIX_FAILURE_THRESHOLD and self._current_function_start_commit:
                typer.secho(f"[c2rust-transpiler][build] 连续修复失败 {self._consecutive_fix_failures} 次，回退到函数开始时的 commit: {self._current_function_start_commit}", fg=typer.colors.RED)
                if self._reset_to_commit(self._current_function_start_commit):
                    typer.secho("[c2rust-transpiler][build] 已回退到函数开始时的 commit，将重新开始处理该函数", fg=typer.colors.YELLOW)
                    # 返回特殊值，表示需要重新开始
                    return (False, None)  # type: ignore
                else:
                    typer.secho("[c2rust-transpiler][build] 回退失败，继续尝试修复", fg=typer.colors.YELLOW)
            return (False, False)  # 需要继续循环

    def _cargo_build_loop(self) -> Optional[bool]:
        """在 crate 目录执行构建与测试：先 cargo check，再 cargo test（运行所有测试，不区分项目结构）。失败则最小化修复直到通过或达到上限。"""
        workspace_root = str(self.crate_dir)
        check_limit = f"最大重试: {self.check_max_retries if self.check_max_retries > 0 else '无限'}"
        test_limit = f"最大重试: {self.test_max_retries if self.test_max_retries > 0 else '无限'}"
        typer.secho(f"[c2rust-transpiler][build] 工作区={workspace_root}，开始构建循环（check -> test，{check_limit} / {test_limit}）", fg=typer.colors.MAGENTA)
        check_iter = 0
        test_iter = 0
        while True:
            # 阶段一：cargo check（更快）
            check_iter += 1
            check_success, need_restart = self._run_cargo_check_and_fix(workspace_root, check_iter, test_iter)
            if need_restart is None:
                return None  # 需要回退重新开始
            if not check_success:
                continue  # 继续循环
            
            # 阶段二：运行所有测试（不区分项目结构）
            # cargo test 会自动运行所有类型的测试：lib tests、bin tests、integration tests、doc tests 等
            test_iter += 1
            test_success, need_restart = self._run_cargo_test_and_fix(workspace_root, check_iter, test_iter)
            if need_restart is None:
                return None  # 需要回退重新开始
            if test_success:
                return True  # 测试通过
            # 测试失败，重置 check 迭代计数，因为修复后需要重新 check
            check_iter = 0

    def _review_and_optimize(self, rec: FnRecord, module: str, rust_sig: str) -> None:
        """
        审查生成的实现；若 summary 报告问题，则调用 CodeAgent 进行优化，直到无问题或次数用尽。
        合并了功能一致性审查和类型/边界严重问题审查，避免重复审查。
        审查只关注本次函数与相关最小上下文，避免全局重构。
        """
        def build_review_prompts() -> Tuple[str, str, str]:
            sys_p = (
                "你是Rust代码审查专家。验收标准：Rust 实现应与原始 C 实现在功能上一致，且不应包含可能导致功能错误的严重问题。\n"
                "审查标准（合并了功能一致性和严重问题检查）：\n"
                "1. 功能一致性检查：\n"
                "   - 核心输入输出、主要功能逻辑是否与 C 实现一致；\n"
                "   - 允许 Rust 实现修复 C 代码中的安全漏洞（如缓冲区溢出、空指针解引用、未初始化内存使用等），这些修复不应被视为功能不一致；\n"
                "   - 允许 Rust 实现使用不同的类型设计、错误处理方式、资源管理方式等，只要功能一致即可；\n"
                "2. 严重问题检查（可能导致功能错误）：\n"
                "   - 明显的空指针解引用或会导致 panic 的严重错误；\n"
                "   - 明显的越界访问或会导致程序崩溃的问题；\n"
                "不检查类型匹配、指针可变性、边界检查细节、资源释放细节、内存语义等技术细节（除非会导致功能错误）。\n"
                "**重要要求：在总结阶段，对于发现的每个问题，必须提供：**\n"
                "1. 详细的问题描述：明确指出问题所在的位置（文件、函数、行号等）、问题的具体表现、为什么这是一个问题\n"
                "2. 具体的修复建议：提供详细的修复方案，包括需要修改的代码位置、修改方式、预期效果等\n"
                "3. 问题分类：使用 [function] 标记功能一致性问题，使用 [critical] 标记严重问题\n"
                "请在总结阶段详细指出问题和修改建议，但不要尝试修复或修改任何代码，不要输出补丁。"
            )
            # 附加原始C函数源码片段，供审查作为只读参考
            c_code = self._read_source_span(rec) or ""
            # 附加被引用符号上下文与库替代上下文，以及crate目录结构，提供更完整审查背景
            callees_ctx = self._collect_callees_context(rec)
            librep_ctx = rec.lib_replacement if isinstance(rec.lib_replacement, dict) else None
            crate_tree = _dir_tree(self.crate_dir)
            # 提取编译参数
            compile_flags = self._extract_compile_flags(rec.file)
            
            usr_p_lines = [
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
                "审查说明（合并审查）：",
                "1. 功能一致性：",
                "   - 核心输入输出、主要功能逻辑是否与 C 实现一致；",
                "   - 允许Rust实现修复C代码中的安全漏洞（如缓冲区溢出、空指针解引用、未初始化内存使用等），这些修复不应被视为功能不一致；",
                "   - 允许Rust实现使用不同的类型设计、错误处理方式、资源管理方式等，只要功能一致即可；",
                "2. 严重问题（可能导致功能错误）：",
                "   - 明显的空指针解引用或会导致 panic 的严重错误；",
                "   - 明显的越界访问或会导致程序崩溃的问题；",
                "不检查类型匹配、指针可变性、边界检查细节等技术细节（除非会导致功能错误）。",
                "",
                "**重要：问题报告要求**",
                "对于发现的每个问题，必须在总结中提供：",
                "1. 详细的问题描述：明确指出问题所在的位置（文件、函数、行号等）、问题的具体表现、为什么这是一个问题",
                "2. 具体的修复建议：提供详细的修复方案，包括需要修改的代码位置、修改方式、预期效果等",
                "3. 问题分类：使用 [function] 标记功能一致性问题，使用 [critical] 标记严重问题",
                "示例：",
                '  "[function] 返回值处理缺失：在函数 foo 的第 42 行，当输入参数为负数时，函数没有返回错误码，但 C 实现中会返回 -1。修复建议：在函数开始处添加参数验证，当参数为负数时返回 Result::Err(Error::InvalidInput)。"',
                '  "[critical] 空指针解引用风险：在函数 bar 的第 58 行，直接解引用指针 ptr 而没有检查其是否为 null，可能导致 panic。修复建议：使用 if let Some(value) = ptr.as_ref() 进行空指针检查，或使用 Option<&T> 类型。"',
                "",
                "被引用符号上下文（如已转译则包含Rust模块信息）：",
                json.dumps(callees_ctx, ensure_ascii=False, indent=2),
                "",
                "库替代上下文（若存在）：",
                json.dumps(librep_ctx, ensure_ascii=False, indent=2),
                "",
                *([f"禁用库列表（禁止在实现中使用这些库）：{', '.join(self.disabled_libraries)}"] if self.disabled_libraries else []),
            ]
            # 添加编译参数（如果存在）
            if compile_flags:
                usr_p_lines.extend([
                    "",
                    "C文件编译参数（来自 compile_commands.json）：",
                    compile_flags,
                ])
            usr_p_lines.extend([
                "",
                "当前crate目录结构（部分）：",
                "<CRATE_TREE>",
                crate_tree,
                "</CRATE_TREE>",
                "",
                "如需定位或交叉验证 C 符号位置，请使用符号表检索工具：",
                "- 工具: read_symbols",
                "- 参数示例(JSON):",
                f"  {{\"symbols_file\": \"{(self.data_dir / 'symbols.jsonl').resolve()}\", \"symbols\": [\"{rec.qname or rec.name}\"]}}",
                "",
                "请阅读crate中该函数的当前实现（你可以在上述crate根路径下自行读取必要上下文），并准备总结。",
            ])
            usr_p = "\n".join(usr_p_lines)
            sum_p = (
                "请仅输出一个 <SUMMARY> 块，块内直接包含 JSON 对象（不需要额外的标签），字段：\n"
                '"ok": bool  // 若满足功能一致且无严重问题，则为 true\n'
                '"function_issues": [string, ...]  // 功能一致性问题，每项以 [function] 开头，必须包含详细的问题描述和修复建议\n'
                '"critical_issues": [string, ...]  // 严重问题（可能导致功能错误），每项以 [critical] 开头，必须包含详细的问题描述和修复建议\n'
                "注意：\n"
                "- 前置条件：必须在crate中找到该函数的实现（匹配函数名或签名）。若未找到，ok 必须为 false，function_issues 应包含 [function] function not found: 详细描述问题位置和如何查找函数实现\n"
                "- 若Rust实现修复了C代码中的安全漏洞或使用了不同的实现方式但保持了功能一致，且无严重问题，ok 应为 true\n"
                "- 仅报告功能不一致和严重问题，不报告类型匹配、指针可变性、边界检查细节等技术细节（除非会导致功能错误）\n"
                "- **重要：每个问题描述必须包含以下内容：**\n"
                "  1. 问题的详细描述：明确指出问题所在的位置（文件、函数、行号等）、问题的具体表现、为什么这是一个问题\n"
                "  2. 修复建议：提供具体的修复方案，包括需要修改的代码位置、修改方式、预期效果等\n"
                "  3. 问题格式：[function] 或 [critical] 开头，后跟详细的问题描述和修复建议\n"
                "  示例格式：\n"
                '    "[function] 返回值处理缺失：在函数 foo 的第 42 行，当输入参数为负数时，函数没有返回错误码，但 C 实现中会返回 -1。修复建议：在函数开始处添加参数验证，当参数为负数时返回 Result::Err(Error::InvalidInput)。"\n'
                '    "[critical] 空指针解引用风险：在函数 bar 的第 58 行，直接解引用指针 ptr 而没有检查其是否为 null，可能导致 panic。修复建议：使用 if let Some(value) = ptr.as_ref() 进行空指针检查，或使用 Option<&T> 类型。"\n'
                "请严格按以下格式输出（JSON格式，支持jsonnet语法如尾随逗号、注释、|||分隔符多行字符串等）：\n"
                "<SUMMARY>\n{\n  \"ok\": true,\n  \"function_issues\": [],\n  \"critical_issues\": []\n}\n</SUMMARY>"
            )
            return sys_p, usr_p, sum_p

        i = 0
        max_iterations = self.review_max_iterations
        # 复用 Review Agent（仅在本函数生命周期内构建一次）
        # 注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表
        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
        review_key = f"review::{rec.id}"
        sys_p_init, usr_p_init, sum_p_init = build_review_prompts()
        
        if self._current_agents.get(review_key) is None:
            self._current_agents[review_key] = Agent(
                system_prompt=sys_p_init,
                name="C2Rust-Review-Agent",
                model_group=self.llm_group,
                summary_prompt=sum_p_init,
                need_summary=True,
                auto_complete=True,
                use_tools=["execute_script", "read_code", "retrieve_memory", "save_memory", "read_symbols"],
                non_interactive=self.non_interactive,
                use_methodology=False,
                use_analysis=False,
            )

        # 0表示无限重试，否则限制迭代次数
        use_direct_model_review = False  # 标记是否使用直接模型调用
        parse_failed = False  # 标记上一次解析是否失败
        parse_error_msg: Optional[str] = None  # 保存上一次的YAML解析错误信息
        while max_iterations == 0 or i < max_iterations:
            agent = self._current_agents[review_key]
            # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
            # 如果是修复后的审查（i > 0），在提示词中明确说明代码已变更，需要重新读取
            if i > 0:
                code_changed_notice = "\n".join([
                    "",
                    "【重要提示：代码已变更】",
                    f"在本次审查之前（第 {i} 次迭代），已根据审查意见对代码进行了修复和优化。",
                    "目标函数的实现可能已经发生变化，包括但不限于：",
                    "- 函数实现逻辑的修改",
                    "- 类型和签名的调整",
                    "- 依赖关系的更新",
                    "- 错误处理的改进",
                    "",
                    "**请务必重新读取目标模块文件中的函数实现，不要基于之前的审查结果或缓存信息进行判断。**",
                    "请使用 read_code 工具重新读取以下文件的最新内容：",
                    f"- 目标模块文件: {module}",
                    "- 以及相关的依赖模块文件（如有需要）",
                    "",
                    "审查时请基于重新读取的最新代码内容进行评估。",
                    "",
                ])
                usr_p_with_notice = usr_p_init + code_changed_notice
                composed_prompt = self._compose_prompt_with_context(usr_p_with_notice)
            else:
                composed_prompt = self._compose_prompt_with_context(usr_p_init)
            
            if use_direct_model_review:
                # 格式解析失败后，直接调用模型接口
                # 构造包含摘要提示词和具体错误信息的完整提示
                error_guidance = ""
                # 检查上一次的解析结果
                if parse_error_msg:
                    # 如果有JSON解析错误，优先反馈
                    error_guidance = (
                        f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n"
                        f"- JSON解析失败: {parse_error_msg}\n\n"
                        f"请确保输出的JSON格式正确，包括正确的引号、逗号、大括号等。JSON 对象必须包含字段：ok（布尔值）、function_issues（字符串数组）、critical_issues（字符串数组）。支持jsonnet语法（如尾随逗号、注释、|||分隔符多行字符串等）。"
                    )
                elif parse_failed:
                    error_guidance = (
                        "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n"
                        "- 无法从摘要中解析出有效的 JSON 对象\n\n"
                        "请确保输出格式正确：仅输出一个 <SUMMARY> 块，块内直接包含 JSON 对象（不需要额外的标签），字段：ok（布尔值）、function_issues（字符串数组）、critical_issues（字符串数组）。支持jsonnet语法（如尾随逗号、注释、|||分隔符多行字符串等）。"
                    )
                
                full_prompt = f"{composed_prompt}{error_guidance}\n\n{sum_p_init}"
                typer.secho(f"[c2rust-transpiler][review] 直接调用模型接口修复格式错误（第 {i+1} 次重试）", fg=typer.colors.YELLOW)
                try:
                    response = agent.model.chat_until_success(full_prompt)  # type: ignore
                    summary = str(response or "")
                except Exception as e:
                    typer.secho(f"[c2rust-transpiler][review] 直接模型调用失败: {e}，回退到 run()", fg=typer.colors.YELLOW)
                    summary = str(agent.run(composed_prompt) or "")
            else:
                # 第一次使用 run()，让 Agent 完整运行（可能使用工具）
                summary = str(agent.run(composed_prompt) or "")
            
            # 解析 JSON 格式的审查结果
            verdict, parse_error_review = _extract_json_from_summary(summary)
            parse_failed = False
            parse_error_msg = None
            if parse_error_review:
                # JSON解析失败
                parse_failed = True
                parse_error_msg = parse_error_review
                typer.secho(f"[c2rust-transpiler][review] JSON解析失败: {parse_error_review}", fg=typer.colors.YELLOW)
                # 兼容旧格式：尝试解析纯文本 OK
                m = re.search(r"<SUMMARY>([\s\S]*?)</SUMMARY>", summary, flags=re.IGNORECASE)
                content = (m.group(1).strip() if m else summary.strip()).upper()
                if content == "OK":
                    verdict = {"ok": True, "function_issues": [], "critical_issues": []}
                    parse_failed = False  # 兼容格式成功，不算解析失败
                    parse_error_msg = None
                else:
                    # 无法解析，立即重试：设置标志并继续循环
                    use_direct_model_review = True
                    # 继续循环，立即重试
                    continue
            elif not isinstance(verdict, dict):
                parse_failed = True
                # 兼容旧格式：尝试解析纯文本 OK
                m = re.search(r"<SUMMARY>([\s\S]*?)</SUMMARY>", summary, flags=re.IGNORECASE)
                content = (m.group(1).strip() if m else summary.strip()).upper()
                if content == "OK":
                    verdict = {"ok": True, "function_issues": [], "critical_issues": []}
                    parse_failed = False  # 兼容格式成功，不算解析失败
                else:
                    # 无法解析，立即重试：设置标志并继续循环
                    use_direct_model_review = True
                    parse_error_msg = f"无法从摘要中解析出有效的 JSON 对象，得到的内容类型为: {type(verdict).__name__}"
                    # 继续循环，立即重试
                    continue
            
            ok = bool(verdict.get("ok") is True)
            function_issues = verdict.get("function_issues") if isinstance(verdict.get("function_issues"), list) else []
            critical_issues = verdict.get("critical_issues") if isinstance(verdict.get("critical_issues"), list) else []
            all_issues = function_issues + critical_issues
            
            typer.secho(f"[c2rust-transpiler][review][iter={i+1}] verdict ok={ok}, function_issues={len(function_issues)}, critical_issues={len(critical_issues)}", fg=typer.colors.CYAN)
            
            if ok and not all_issues:
                limit_info = f" (上限: {max_iterations if max_iterations > 0 else '无限'})"
                typer.secho(f"[c2rust-transpiler][review] 代码审查通过{limit_info} (共 {i+1} 次迭代)。", fg=typer.colors.GREEN)
                # 记录审查结果到进度
                try:
                    cur = self.progress.get("current") or {}
                    cur["review"] = {
                        "ok": True,
                        "function_issues": [],
                        "critical_issues": [],
                        "iterations": i + 1,
                    }
                    metrics = cur.get("metrics") or {}
                    metrics["review_iterations"] = i + 1
                    metrics["function_issues"] = 0
                    metrics["type_issues"] = 0
                    cur["metrics"] = metrics
                    self.progress["current"] = cur
                    self._save_progress()
                except Exception:
                    pass
                return
            
            # 需要优化：提供详细上下文背景，并明确审查意见仅针对 Rust crate，不修改 C 源码
            crate_tree = _dir_tree(self.crate_dir)
            issues_text = "\n".join([
                "功能一致性问题：" if function_issues else "",
                *[f"  - {issue}" for issue in function_issues],
                "严重问题（可能导致功能错误）：" if critical_issues else "",
                *[f"  - {issue}" for issue in critical_issues],
            ])
            fix_prompt = "\n".join([
                "请根据以下审查结论对目标函数进行最小优化（保留结构与意图，不进行大范围重构）：",
                "<REVIEW>",
                issues_text if issues_text.strip() else "审查发现问题，但未提供具体问题描述",
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
                "- 优先修复严重问题（可能导致功能错误），然后修复功能一致性问题；",
                "- 如审查问题涉及缺失/未实现的被调函数或依赖，请阅读其 C 源码并在本次一并补齐等价的 Rust 实现；必要时在合理模块新增函数或引入精确 use；",
                "- 禁止使用 todo!/unimplemented! 作为占位；",
                "- 可使用工具 read_symbols/read_code 获取依赖符号的 C 源码与位置以辅助实现；仅精确导入所需符号（禁止通配）；",
                "- **强烈建议使用 retrieve_memory 工具召回已保存的函数实现记忆**：在优化之前，先尝试使用 retrieve_memory 工具检索相关的函数实现记忆，这些记忆可能包含之前已实现的类似函数、设计决策、实现模式等有价值的信息，可以显著提高优化效率和准确性；",
                "- 注释规范：所有代码注释（包括文档注释、行内注释、块注释等）必须使用中文；",
                *([f"- **禁用库约束**：禁止在优化中使用以下库：{', '.join(self.disabled_libraries)}。如果这些库在 Cargo.toml 中已存在，请移除相关依赖；如果优化需要使用这些库的功能，请使用标准库或其他允许的库替代。"] if self.disabled_libraries else []),
                "",
                "【重要：依赖检查与实现要求】",
                "在优化函数之前，请务必检查以下内容：",
                "1. 检查当前函数是否已完整实现：",
                f"   - 在目标模块 {module} 中查找函数 {rec.qname or rec.name} 的实现",
                "   - 如果已存在实现，检查其是否完整且正确",
                "2. 检查所有依赖函数是否已实现：",
                "   - 遍历当前函数调用的所有被调函数（包括直接调用和间接调用）",
                "   - 对于每个被调函数，检查其在 Rust crate 中是否已有完整实现",
                "   - 可以使用 read_code 工具读取相关模块文件进行检查",
                "   - 可以使用 retrieve_memory 工具检索已保存的函数实现记忆",
                "3. 对于未实现的依赖函数：",
                "   - 使用 read_symbols 工具获取其 C 源码和符号信息",
                "   - 使用 read_code 工具读取其 C 源码实现",
                "   - 在本次优化中一并补齐这些依赖函数的 Rust 实现",
                "   - 根据依赖关系选择合适的模块位置（可在同一模块或合理的新模块中）",
                "   - 确保所有依赖函数都有完整实现，禁止使用 todo!/unimplemented! 占位",
                "4. 实现顺序：",
                "   - 优先实现最底层的依赖函数（不依赖其他未实现函数的函数）",
                "   - 然后实现依赖这些底层函数的函数",
                "   - 最后优化当前目标函数",
                "5. 验证：",
                "   - 确保当前函数及其所有依赖函数都已完整实现",
                "   - 确保没有遗留的 todo!/unimplemented! 占位",
                "   - 确保所有函数调用都能正确解析",
                "",
                "请仅以补丁形式输出修改，避免冗余解释。",
            ])
            # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
            ca = self._get_repair_agent()
            limit_info = f"/{max_iterations}" if max_iterations > 0 else "/∞"
            ca.run(self._compose_prompt_with_context(fix_prompt), prefix=f"[c2rust-transpiler][review-fix iter={i+1}{limit_info}]", suffix="")
            # 优化后进行一次构建验证；若未通过则进入构建修复循环，直到通过为止
            self._cargo_build_loop()
            
            # 记录本次审查结果
            try:
                cur = self.progress.get("current") or {}
                cur["review"] = {
                    "ok": False,
                    "function_issues": list(function_issues),
                    "critical_issues": list(critical_issues),
                    "iterations": i + 1,
                }
                metrics = cur.get("metrics") or {}
                metrics["function_issues"] = len(function_issues)
                metrics["type_issues"] = len(critical_issues)
                cur["metrics"] = metrics
                self.progress["current"] = cur
                self._save_progress()
            except Exception:
                pass
            
            i += 1
        
        # 达到迭代上限（仅当设置了上限时）
        if max_iterations > 0 and i >= max_iterations:
            typer.secho(f"[c2rust-transpiler][review] 已达到最大迭代次数上限({max_iterations})，停止审查优化。", fg=typer.colors.YELLOW)
            try:
                cur = self.progress.get("current") or {}
                cur["review_max_iterations_reached"] = True
                cur["review_iterations"] = i
                self.progress["current"] = cur
                self._save_progress()
            except Exception:
                pass

    def _mark_converted(self, rec: FnRecord, module: str, rust_sig: str) -> None:
        """记录映射：C 符号 -> Rust 符号与模块路径（JSONL，每行一条，支持重载/同名）"""
        rust_symbol = ""
        # 从签名中提取函数名（支持生命周期参数和泛型参数）
        # 支持生命周期参数和泛型参数：fn name<'a, T>(...)
        m = re.search(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^>]+>)?\s*\(", rust_sig)
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
        typer.secho("[c2rust-transpiler][start] 开始转译", fg=typer.colors.BLUE)
        # 切换到 crate 根目录，整个转译过程都在此目录下执行
        prev_cwd = os.getcwd()
        try:
            os.chdir(str(self.crate_dir))
            typer.secho(f"[c2rust-transpiler][start] 已切换到 crate 目录: {os.getcwd()}", fg=typer.colors.BLUE)
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
                module, rust_sig, skip_implementation = self._plan_module_and_signature(rec, c_code)
                typer.secho(f"[c2rust-transpiler][plan] 已选择 模块={module}, 签名={rust_sig}", fg=typer.colors.CYAN)

                # 记录当前进度
                self._update_progress_current(rec, module, rust_sig)
                typer.secho(f"[c2rust-transpiler][progress] 已更新当前进度记录 id={rec.id}", fg=typer.colors.CYAN)

                # 如果标记为跳过实现（通过 RAII 自动管理），则直接标记为已转换
                if skip_implementation:
                    typer.secho(f"[c2rust-transpiler][skip-impl] 函数 {rec.qname or rec.name} 通过 RAII 自动管理，跳过实现阶段", fg=typer.colors.CYAN)
                    # 直接标记为已转换，跳过代码生成、构建和审查阶段
                    self._mark_converted(rec, module, rust_sig)
                    typer.secho(f"[c2rust-transpiler][mark] 已标记并建立映射: {rec.qname or rec.name} -> {module} (跳过实现)", fg=typer.colors.GREEN)
                    continue

                # 初始化函数上下文与代码编写与修复Agent复用缓存（只在当前函数开始时执行一次）
                self._reset_function_context(rec, module, rust_sig, c_code)

                # 1.5) 确保模块声明链（提前到生成实现之前，避免生成的代码无法被正确引用）
                try:
                    self._ensure_mod_chain_for_module(module)
                    typer.secho(f"[c2rust-transpiler][mod] 已补齐 {module} 的 mod.rs 声明链", fg=typer.colors.GREEN)
                    # 确保顶层模块在 src/lib.rs 中被公开
                    mp = Path(module)
                    crate_root = self.crate_dir.resolve()
                    rel = mp.resolve().relative_to(crate_root) if mp.is_absolute() else Path(module)
                    rel_s = str(rel).replace("\\", "/")
                    if rel_s.startswith("./"):
                        rel_s = rel_s[2:]
                    if rel_s.startswith("src/"):
                        parts = rel_s[len("src/"):].strip("/").split("/")
                        if parts and parts[0]:
                            top_mod = parts[0]
                            if not top_mod.endswith(".rs"):
                                self._ensure_top_level_pub_mod(top_mod)
                                typer.secho(f"[c2rust-transpiler][mod] 已在 src/lib.rs 确保顶层 pub mod {top_mod}", fg=typer.colors.GREEN)
                    cur = self.progress.get("current") or {}
                    cur["mod_chain_fixed"] = True
                    cur["mod_visibility_fixed"] = True
                    self.progress["current"] = cur
                    self._save_progress()
                except Exception:
                    pass

                # 在处理函数前，记录当前的 commit id（用于失败回退）
                self._current_function_start_commit = self._get_crate_commit_hash()
                if self._current_function_start_commit:
                    typer.secho(f"[c2rust-transpiler][commit] 记录函数开始时的 commit: {self._current_function_start_commit}", fg=typer.colors.BLUE)
                else:
                    typer.secho("[c2rust-transpiler][commit] 警告：无法获取 commit id，将无法在失败时回退", fg=typer.colors.YELLOW)
                
                # 重置连续失败计数（每个新函数开始时重置）
                self._consecutive_fix_failures = 0

                # 使用循环来处理函数，支持失败回退后重新开始
                function_retry_count = 0
                max_function_retries = MAX_FUNCTION_RETRIES
                while function_retry_count <= max_function_retries:
                    if function_retry_count > 0:
                        typer.secho(f"[c2rust-transpiler][retry] 重新开始处理函数 (第 {function_retry_count} 次重试)", fg=typer.colors.YELLOW)
                        # 重新记录 commit id（回退后的新 commit）
                        self._current_function_start_commit = self._get_crate_commit_hash()
                        if self._current_function_start_commit:
                            typer.secho(f"[c2rust-transpiler][commit] 重新记录函数开始时的 commit: {self._current_function_start_commit}", fg=typer.colors.BLUE)
                        # 重置连续失败计数（重新开始时重置）
                        self._consecutive_fix_failures = 0

                    # 2) 生成实现
                    unresolved = self._untranslated_callee_symbols(rec)
                    typer.secho(f"[c2rust-transpiler][deps] 未解析的被调符号: {', '.join(unresolved) if unresolved else '(none)'}", fg=typer.colors.BLUE)
                    typer.secho(f"[c2rust-transpiler][gen] 正在为 {rec.qname or rec.name} 生成 Rust 实现", fg=typer.colors.GREEN)
                    self._codeagent_generate_impl(rec, c_code, module, rust_sig, unresolved)
                    typer.secho(f"[c2rust-transpiler][gen] 已在 {module} 生成或更新实现", fg=typer.colors.GREEN)
                    # 刷新精简上下文（防止签名/模块调整后提示不同步）
                    try:
                        self._refresh_compact_context(rec, module, rust_sig)
                    except Exception:
                        pass

                    # 3) 构建与修复
                    typer.secho("[c2rust-transpiler][build] 开始 cargo 测试循环", fg=typer.colors.MAGENTA)
                    ok = self._cargo_build_loop()
                    
                    # 检查是否需要重新开始（回退后）
                    if ok is None:
                        # 需要重新开始
                        function_retry_count += 1
                        if function_retry_count > max_function_retries:
                            typer.secho(f"[c2rust-transpiler] 函数重新开始次数已达上限({max_function_retries})，停止处理该函数", fg=typer.colors.RED)
                            # 保留当前状态，便于下次 resume
                            return
                        # 重置连续失败计数
                        self._consecutive_fix_failures = 0
                        # 继续循环，重新开始处理
                        continue
                    
                    typer.secho(f"[c2rust-transpiler][build] 构建结果: {'通过' if ok else '失败'}", fg=typer.colors.MAGENTA)
                    if not ok:
                        typer.secho("[c2rust-transpiler] 在重试次数限制内未能成功构建，已停止。", fg=typer.colors.RED)
                        # 保留当前状态，便于下次 resume
                        return
                    
                    # 构建成功，跳出循环继续后续流程
                    break

                # 4) 审查与优化（复用 Review Agent）
                typer.secho(f"[c2rust-transpiler][review] 开始代码审查: {rec.qname or rec.name}", fg=typer.colors.MAGENTA)
                self._review_and_optimize(rec, module, rust_sig)
                typer.secho("[c2rust-transpiler][review] 代码审查完成", fg=typer.colors.MAGENTA)

                # 5) 标记已转换与映射记录（JSONL）
                self._mark_converted(rec, module, rust_sig)
                typer.secho(f"[c2rust-transpiler][mark] 已标记并建立映射: {rec.qname or rec.name} -> {module}", fg=typer.colors.GREEN)

                # 6) 若此前有其它函数因依赖当前符号而在源码中放置了 todo!("<symbol>")，则立即回头消除（复用代码编写与修复Agent）
                current_rust_fn = self._extract_rust_fn_name_from_sig(rust_sig)
                # 收集需要处理的符号（去重，避免 qname 和 name 相同时重复处理）
                symbols_to_resolve = []
                if rec.qname:
                    symbols_to_resolve.append(rec.qname)
                if rec.name and rec.name != rec.qname:  # 如果 name 与 qname 不同，才添加
                    symbols_to_resolve.append(rec.name)
                # 处理每个符号（去重后）
                for sym in symbols_to_resolve:
                    typer.secho(f"[c2rust-transpiler][todo] 清理 todo!(\'{sym}\') 的出现位置", fg=typer.colors.BLUE)
                    self._resolve_pending_todos_for_symbol(sym, module, current_rust_fn, rust_sig)
                # 如果有处理任何符号，统一运行一次 cargo test（避免重复运行）
                if symbols_to_resolve:
                    typer.secho("[c2rust-transpiler][build] 处理 todo 后重新运行 cargo test", fg=typer.colors.MAGENTA)
                    self._cargo_build_loop()

            typer.secho("[c2rust-transpiler] 所有符合条件的函数均已处理完毕。", fg=typer.colors.GREEN)
        finally:
            os.chdir(prev_cwd)
            typer.secho(f"[c2rust-transpiler][end] 已恢复工作目录: {os.getcwd()}", fg=typer.colors.BLUE)


def run_transpile(
    project_root: Union[str, Path] = ".",
    crate_dir: Optional[Union[str, Path]] = None,
    llm_group: Optional[str] = None,
    plan_max_retries: int = DEFAULT_PLAN_MAX_RETRIES_ENTRY,
    max_retries: int = 0,  # 兼容旧接口
    check_max_retries: Optional[int] = None,
    test_max_retries: Optional[int] = None,
    review_max_iterations: int = DEFAULT_REVIEW_MAX_ITERATIONS,
    resume: bool = True,
    only: Optional[List[str]] = None,
    disabled_libraries: Optional[List[str]] = None,
    non_interactive: bool = True,
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
        plan_max_retries=plan_max_retries,
        max_retries=max_retries,
        check_max_retries=check_max_retries,
        test_max_retries=test_max_retries,
        review_max_iterations=review_max_iterations,
        resume=resume,
        only=only,
        disabled_libraries=disabled_libraries,
        non_interactive=non_interactive,
    )
    t.transpile()