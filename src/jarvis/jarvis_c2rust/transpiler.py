# -*- coding: utf-8 -*-
"""
C2Rust 转译器模块

目标：
- 基于 scanner 生成的 translation_order.jsonl 顺序，逐个函数进行转译
- 为每个函数：
  1) 准备上下文：C 源码片段+位置信息、被调用符号（若已转译则提供Rust模块与符号，否则提供原C位置信息）、crate目录结构
  2) 创建"模块选择与签名Agent"：让其选择合适的Rust模块路径，并在summary输出函数签名
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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Set

import typer

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_code_agent.code_agent import CodeAgent
from jarvis.jarvis_utils.git_utils import get_latest_commit_hash, get_diff_between_commits
from jarvis.jarvis_utils.config import get_max_input_token_count

from jarvis.jarvis_c2rust.constants import (
    C2RUST_DIRNAME,
    CONFIG_JSON,
    CONSECUTIVE_FIX_FAILURE_THRESHOLD,
    DEFAULT_CHECK_MAX_RETRIES,
    DEFAULT_PLAN_MAX_RETRIES,
    DEFAULT_PLAN_MAX_RETRIES_ENTRY,
    DEFAULT_REVIEW_MAX_ITERATIONS,
    DEFAULT_TEST_MAX_RETRIES,
    ERROR_SUMMARY_MAX_LENGTH,
    MAX_FUNCTION_RETRIES,
    PROGRESS_JSON,
    SYMBOL_MAP_JSONL,
)
from jarvis.jarvis_c2rust.loaders import _SymbolMapJsonl
from jarvis.jarvis_c2rust.models import FnRecord
from jarvis.jarvis_c2rust.utils import (
    default_crate_dir,
    dir_tree,
    ensure_order_file,
    extract_json_from_summary,
    iter_order_steps,
    read_json,
    write_json,
)


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
        disabled_libraries: Optional[List[str]] = None,  # 禁用库列表（在实现时禁止使用这些库）
        root_symbols: Optional[List[str]] = None,  # 根符号列表（这些符号对应的接口实现时要求对外暴露，main除外）
        non_interactive: bool = True,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.data_dir = self.project_root / C2RUST_DIRNAME
        self.progress_path = self.data_dir / PROGRESS_JSON
        self.config_path = self.data_dir / CONFIG_JSON
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
        self.non_interactive = non_interactive

        self.crate_dir = Path(crate_dir) if crate_dir else default_crate_dir(self.project_root)
        # 使用自包含的 order.jsonl 记录构建索引，避免依赖 symbols.jsonl
        self.fn_index_by_id: Dict[int, FnRecord] = {}
        self.fn_name_to_id: Dict[str, int] = {}

        # 断点续跑功能默认始终启用
        self.resume = True
        
        # 读取进度文件（仅用于进度信息，不包含配置）
        default_progress = {"current": None, "converted": []}
        self.progress: Dict[str, Any] = read_json(self.progress_path, default_progress)
        
        # 从独立的配置文件加载配置（支持从 progress.json 向后兼容迁移）
        config = self._load_config()
        
        # 如果提供了新的根符号或禁用库，更新配置；否则从配置文件中恢复
        # 优先使用传入的参数，如果为 None 则从配置文件恢复
        if root_symbols is not None:
            # 传入的参数不为 None，使用传入的值并保存
            self.root_symbols = root_symbols
        else:
            # 传入的参数为 None，从配置文件恢复
            # 如果配置文件中有配置则使用，否则使用空列表
            self.root_symbols = config.get("root_symbols", [])
        
        if disabled_libraries is not None:
            # 传入的参数不为 None，使用传入的值并保存
            self.disabled_libraries = disabled_libraries
        else:
            # 传入的参数为 None，从配置文件恢复
            # 如果配置文件中有配置则使用，否则使用空列表
            self.disabled_libraries = config.get("disabled_libraries", [])
        
        # 从配置文件读取附加说明（不支持通过参数传入，只能通过配置文件设置）
        self.additional_notes = config.get("additional_notes", "")
        
        # 保存配置到独立的配置文件
        self._save_config()
        
        # 在初始化完成后打印日志
        typer.secho(f"[c2rust-transpiler][init] 初始化参数: project_root={self.project_root} crate_dir={self.crate_dir} llm_group={self.llm_group} plan_max_retries={self.plan_max_retries} check_max_retries={self.check_max_retries} test_max_retries={self.test_max_retries} review_max_iterations={self.review_max_iterations} disabled_libraries={self.disabled_libraries} root_symbols={self.root_symbols} non_interactive={self.non_interactive}", fg=typer.colors.BLUE)
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
        write_json(self.progress_path, self.progress)

    def _load_config(self) -> Dict[str, Any]:
        """
        从独立的配置文件加载配置。
        如果配置文件不存在，尝试从 progress.json 迁移配置（向后兼容）。
        """
        config_path = self.data_dir / CONFIG_JSON
        default_config = {"root_symbols": [], "disabled_libraries": [], "additional_notes": ""}
        
        # 尝试从配置文件读取
        if config_path.exists():
            config = read_json(config_path, default_config)
            if isinstance(config, dict):
                # 确保包含所有必需的键（向后兼容）
                if "additional_notes" not in config:
                    config["additional_notes"] = ""
                return config
        
        # 向后兼容：如果配置文件不存在，尝试从 progress.json 迁移
        progress_config = self.progress.get("config", {})
        if progress_config:
            # 迁移配置到独立文件
            migrated_config = {
                "root_symbols": progress_config.get("root_symbols", []),
                "disabled_libraries": progress_config.get("disabled_libraries", []),
                "additional_notes": progress_config.get("additional_notes", ""),
            }
            write_json(config_path, migrated_config)
            typer.secho(f"[c2rust-transpiler][config] 已从 progress.json 迁移配置到 {config_path}", fg=typer.colors.YELLOW)
            # 从 progress.json 中移除 config（可选，保持兼容性）
            # if "config" in self.progress:
            #     del self.progress["config"]
            #     self._save_progress()
            return migrated_config
        
        return default_config

    def _save_config(self) -> None:
        """保存配置到独立的配置文件"""
        config_path = self.data_dir / CONFIG_JSON
        config = {
            "root_symbols": self.root_symbols,
            "disabled_libraries": self.disabled_libraries,
            "additional_notes": getattr(self, "additional_notes", ""),
        }
        write_json(config_path, config)


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

    def _append_additional_notes(self, prompt: str) -> str:
        """
        在提示词末尾追加附加说明（如果存在）。
        
        Args:
            prompt: 原始提示词
            
        Returns:
            追加了附加说明的提示词
        """
        additional_notes = getattr(self, "additional_notes", "")
        if additional_notes and additional_notes.strip():
            return prompt + "\n\n" + "【附加说明（用户自定义）】\n" + additional_notes.strip()
        return prompt

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
        is_root = self._is_root_symbol(rec)
        system_prompt = (
            "你是资深Rust工程师，擅长为C/C++函数选择合适的Rust模块位置并产出对应的Rust函数签名。\n"
            "目标：根据提供的C源码、调用者上下文与crate目录结构，为该函数选择合适的Rust模块文件并给出Rust函数签名（不实现）。\n"
            "原则：\n"
            "- 按功能内聚与依赖方向选择模块，避免循环依赖；\n"
            "- 模块路径必须落在 crate 的 src/ 下，优先放置到已存在的模块中；必要时可建议创建新的子模块文件；\n"
            "- 函数接口设计应遵循 Rust 最佳实践，不需要兼容 C 的数据类型；优先使用 Rust 原生类型（如 i32/u32/usize、&[T]/&mut [T]、String、Result<T, E> 等），而不是 C 风格类型（如 core::ffi::c_*、libc::c_*）；\n"
            "- 禁止使用 extern \"C\"；函数应使用标准的 Rust 调用约定，不需要 C ABI；\n"
            "- 参数个数与顺序可以保持与 C 一致，但类型设计应优先考虑 Rust 的惯用法和安全性；\n"
            f"{'- **根符号要求**：此函数是根符号，必须使用 `pub` 关键字对外暴露，确保可以从 crate 外部访问。同时，该函数所在的模块必须在 src/lib.rs 中被导出（使用 `pub mod <模块名>;`）。\n' if is_root else ''}"
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
            f"{'- **根符号要求**：此函数是根符号，rust_signature 必须包含 `pub` 关键字，确保可以从 crate 外部访问。同时，该函数所在的模块必须在 src/lib.rs 中被导出（使用 `pub mod <模块名>;`）。\n' if is_root else ''}"
            "- 函数签名应包含可见性修饰（pub）与函数名；类型应为 Rust 最佳实践的选择，而非简单映射 C 类型。\n"
            "- 禁止使用 extern \"C\"；函数应使用标准的 Rust 调用约定，不需要 C ABI。\n"
            "请严格按以下格式输出（JSON格式，支持jsonnet语法如尾随逗号、注释、|||分隔符多行字符串等）：\n"
            "示例1（正常函数）：\n"
            "<SUMMARY>\n{\n  \"module\": \"...\",\n  \"rust_signature\": \"...\",\n  \"notes\": \"...\"\n}\n</SUMMARY>\n"
            "示例2（资源释放类函数，可跳过实现）：\n"
            "<SUMMARY>\n{\n  \"module\": \"...\",\n  \"rust_signature\": \"...\",\n  \"skip_implementation\": true,\n  \"notes\": \"通过 RAII 自动管理，无需显式实现\"\n}\n</SUMMARY>"
        )
        # 在 user_prompt 和 summary_prompt 中追加附加说明（system_prompt 通常不需要）
        user_prompt = self._append_additional_notes(user_prompt)
        summary_prompt = self._append_additional_notes(summary_prompt)
        return system_prompt, user_prompt, summary_prompt

    def _plan_module_and_signature(self, rec: FnRecord, c_code: str) -> Tuple[str, str, bool]:
        """调用 Agent 选择模块与签名，返回 (module_path, rust_signature, skip_implementation)，若格式不满足将自动重试直到满足"""
        crate_tree = dir_tree(self.crate_dir)
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
                # 获取函数信息用于 Agent name
                fn_name = rec.qname or rec.name or f"fn_{rec.id}"
                agent_name = f"C2Rust-Function-Planner({fn_name})"
                agent = Agent(
                    system_prompt=sys_p,
                    name=agent_name,
                    model_group=self.llm_group,
                    summary_prompt=sum_p,
                    need_summary=True,
                    auto_complete=True,
                    use_tools=["execute_script", "read_code", "read_symbols"],
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
                        error_guidance = f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- {last_reason}\n\n请确保输出的JSON格式正确，包括正确的引号、逗号、大括号等。JSON 对象必须包含字段：module（字符串）、rust_signature（字符串）。支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。"
                    else:
                        error_guidance = f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- {last_reason}\n\n请确保输出格式正确：仅输出一个 <SUMMARY> 块，块内直接包含 JSON 对象（不需要额外的标签）；JSON 对象必须包含字段：module（字符串）、rust_signature（字符串）。支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。"
                
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
            
            meta, parse_error = extract_json_from_summary(str(summary or ""))
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
        crate_tree = dir_tree(self.crate_dir)
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


    def _get_code_agent(self) -> CodeAgent:
        """
        获取代码生成/修复Agent（CodeAgent）。若未初始化，则按当前函数id创建。
        统一用于代码生成和修复，启用方法论和分析功能以提供更好的代码质量。
        注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表。
        提示：代码生成遵循 TDD（测试驱动开发）方法，通过提示词指导 Agent 先写测试再写实现。
        """
        fid = self._current_function_id
        key = f"code_agent::{fid}" if fid is not None else "code_agent::default"
        agent = self._current_agents.get(key)
        if agent is None:
            # 注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表
            # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
            # 统一启用方法论和分析功能，提供更好的代码生成和修复能力
            # 获取函数信息用于 Agent name
            fn_name = ""
            if fid is not None:
                rec = self.fn_index_by_id.get(fid)
                if rec:
                    fn_name = rec.qname or rec.name or f"fn_{fid}"
            agent_name = f"C2Rust-CodeAgent" + (f"({fn_name})" if fn_name else "")
            agent = CodeAgent(
                name=agent_name,
                need_summary=False,
                non_interactive=self.non_interactive,
                model_group=self.llm_group,
                append_tools="read_symbols",
                use_methodology=True,
                use_analysis=True,
                force_save_memory=False,
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

    def _is_root_symbol(self, rec: FnRecord) -> bool:
        """判断函数是否为根符号（排除 main）"""
        if not self.root_symbols:
            return False
        # 检查函数名或限定名是否在根符号列表中
        return (rec.name in self.root_symbols) or (rec.qname in self.root_symbols)

    def _build_generate_impl_prompt(
        self, rec: FnRecord, c_code: str, module: str, rust_sig: str, unresolved: List[str]
    ) -> str:
        """
        构建代码生成提示词。
        
        返回完整的提示词字符串。
        """
        symbols_path = str((self.data_dir / "symbols.jsonl").resolve())
        is_root = self._is_root_symbol(rec)
        requirement_lines = [
            f"目标：在 {module} 中，使用 TDD 方法为 C 函数 {rec.qname or rec.name} 生成 Rust 实现。",
            f"函数签名：{rust_sig}",
            f"crate 目录：{self.crate_dir.resolve()}",
            f"C 工程目录：{self.project_root.resolve()}",
            *([f"根符号要求：必须使用 `pub` 关键字，模块必须在 src/lib.rs 中导出"] if is_root else []),
            "",
            "【TDD 流程】",
            "1. Red：先写测试（#[cfg(test)] mod tests），基于 C 函数行为设计测试用例",
            "2. Green：编写实现使测试通过，确保与 C 语义等价",
            "3. Refactor：优化代码，保持测试通过",
            "",
            "【核心要求】",
            "- 先写测试再写实现，测试必须可编译通过",
            "- 禁止使用 todo!/unimplemented!，必须实现完整功能",
            "- 使用 Rust 原生类型（i32/u32、&str/String、&[T]/&mut [T]、Result<T,E>），避免 C 风格类型",
            "- 禁止使用 extern \"C\"，使用标准 Rust 调用约定",
            "- 保持最小变更，避免无关重构",
            "- 注释使用中文，禁止 use ...::* 通配导入",
            "- 资源释放类函数（fclose/free 等）可通过 RAII 自动管理，提供空实现并在文档中说明",
            *([f"- 禁用库：{', '.join(self.disabled_libraries)}"] if self.disabled_libraries else []),
            "",
            "【依赖处理】",
            "- 检查依赖函数是否已实现，未实现的需一并补齐（遵循 TDD：先测试后实现）",
            "- 使用 read_symbols/read_code 获取 C 源码",
            "- 优先处理底层依赖，确保所有测试通过",
            "",
            "【工具】",
            f"- read_symbols: {{\"symbols_file\": \"{symbols_path}\", \"symbols\": [...]}}",
            "- read_code: 读取 C 源码或 Rust 模块",
            "",
            *([f"未转换符号：{', '.join(unresolved)}"] if unresolved else []),
            "",
            "C 源码：",
            "<C_SOURCE>",
            c_code,
            "</C_SOURCE>",
            "",
            "签名参考：",
            json.dumps({"signature": getattr(rec, "signature", ""), "params": getattr(rec, "params", None)}, ensure_ascii=False, indent=2),
            "",
            "仅输出补丁，不要解释。",
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
        prompt = "\n".join(requirement_lines)
        return self._append_additional_notes(prompt)

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
        agent = self._get_code_agent()
        agent.run(self._compose_prompt_with_context(prompt), prefix="[c2rust-transpiler][gen]", suffix="")
        
        # 如果是根符号，确保其模块在 lib.rs 中被暴露
        if self._is_root_symbol(rec):
            try:
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
                        # 过滤掉 "mod" 关键字和 .rs 文件
                        if top_mod != "mod" and not top_mod.endswith(".rs"):
                            self._ensure_top_level_pub_mod(top_mod)
                            typer.secho(f"[c2rust-transpiler][gen] 根符号 {rec.qname or rec.name} 的模块 {top_mod} 已在 lib.rs 中暴露", fg=typer.colors.GREEN)
            except Exception:
                pass

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
            if not mod_name or mod_name in ("lib", "main", "mod"):
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
            if not child_mod or child_mod in ("lib", "main", "mod"):
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
                # 过滤掉 "mod" 关键字
                if child == "mod":
                    return
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
                # 过滤掉 "mod" 关键字
                if cur_dir.name == "mod":
                    cur_dir = parent
                    continue
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
            agent = self._get_code_agent()
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
        # 检查是否为根符号
        is_root = sym_name in (self.root_symbols or [])
        base_lines = [
            f"目标：以最小的改动修复问题，使 `{stage}` 命令可以通过。",
            f"阶段：{stage}",
            f"错误分类标签: {tags}",
            "允许的修复：修正入口/模块声明/依赖；对入口文件与必要mod.rs进行轻微调整；在缺失/未实现的被调函数导致错误时，一并补齐这些依赖的Rust实现（可新增合理模块/函数）；避免大范围改动。",
            "- 保持最小改动，避免与错误无关的重构或格式化；",
            "- 如构建失败源于缺失或未实现的被调函数/依赖，请阅读其 C 源码并在本次一并补齐等价的 Rust 实现；必要时可在合理的模块中新建函数；",
            "- 禁止使用 todo!/unimplemented! 作为占位；",
            "- 可使用工具 read_symbols/read_code 获取依赖符号的 C 源码与位置以辅助实现；仅精确导入所需符号，避免通配；",
            "- **⚠️ 重要：修复后必须验证** - 修复完成后，必须使用 `execute_script` 工具执行相应的验证命令（如 `cargo check` 或 `cargo test`），确认修复是否成功。不要假设修复成功，必须实际执行命令验证。",
            "- 注释规范：所有代码注释（包括文档注释、行内注释、块注释等）必须使用中文；",
            f"- 依赖管理：如修复中引入新的外部 crate 或需要启用 feature，请同步更新 Cargo.toml 的 [dependencies]/[dev-dependencies]/[features]{('，避免未声明依赖导致构建失败；版本号可使用兼容范围（如 ^x.y）或默认值' if stage == 'cargo test' else '')}；",
            *([f"- **禁用库约束**：禁止在修复中使用以下库：{', '.join(self.disabled_libraries)}。如果这些库在 Cargo.toml 中已存在，请移除相关依赖；如果修复需要使用这些库的功能，请使用标准库或其他允许的库替代。"] if self.disabled_libraries else []),
            *([f"- **根符号要求**：此函数是根符号（{sym_name}），必须使用 `pub` 关键字对外暴露，确保可以从 crate 外部访问。同时，该函数所在的模块必须在 src/lib.rs 中被导出（使用 `pub mod <模块名>;`）。"] if is_root else []),
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
            "1. 符号表检索：",
            "   - 工具: read_symbols",
            "   - 用途: 定位或交叉验证 C 符号位置",
            "   - 参数示例(JSON):",
            f"     {{\"symbols_file\": \"{symbols_path}\", \"symbols\": [\"{sym_name}\"]}}",
            "",
            "2. 代码读取：",
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
                "【⚠️ 重要：测试失败 - 必须修复】",
                "以下输出来自 `cargo test` 命令，包含测试执行结果和失败详情：",
                "- **测试当前状态：失败** - 必须修复才能继续",
                "- 如果看到测试用例名称和断言失败，说明测试逻辑或实现有问题",
                "- 如果看到编译错误，说明代码存在语法或类型错误",
                "- **请仔细阅读失败信息**，包括：",
                "  * 测试用例名称（如 `test_bz_read_get_unused`）",
                "  * 失败位置（文件路径和行号，如 `src/ffi/decompress.rs:76:47`）",
                "  * 错误类型（如 `SequenceError`、`Result::unwrap()` 失败等）",
                "  * 期望值与实际值的差异",
                "  * 完整的堆栈跟踪信息",
                "",
                "**关键要求：**",
                "- 必须分析测试失败的根本原因，而不是假设问题已解决",
                "- 必须实际修复导致测试失败的代码，而不是只修改测试用例",
                "- 修复后必须确保测试能够通过，而不是只修复编译错误",
                "",
            ])
            if command:
                section_lines.append(f"执行的命令：{command}")
                section_lines.append("提示：如果不相信上述命令执行结果，可以使用 execute_script 工具自己执行一次该命令进行验证。")
            section_lines.extend([
                "",
                "【测试失败详细信息 - 必须仔细阅读并修复】",
                "以下是从 `cargo test` 命令获取的完整输出，包含测试失败的具体信息：",
                "<TEST_FAILURE>",
                output,
                "</TEST_FAILURE>",
                "",
                "**修复要求：**",
                "1. 仔细分析上述测试失败信息，找出失败的根本原因",
                "2. 定位到具体的代码位置（文件路径和行号）",
                "3. 修复导致测试失败的代码逻辑",
                "4. 确保修复后测试能够通过（不要只修复编译错误）",
                "5. 如果测试用例本身有问题，可以修改测试用例，但必须确保测试能够正确验证函数行为",
                "",
                "**⚠️ 重要：修复后必须验证**",
                "- 修复完成后，**必须使用 `execute_script` 工具执行以下命令验证修复效果**：",
                f"  - 命令：`{command or 'cargo test -- --nocapture'}`",
                "- 验证要求：",
                "  * 如果命令执行成功（返回码为 0），说明修复成功",
                "  * 如果命令执行失败（返回码非 0），说明修复未成功，需要继续修复",
                "  * **不要假设修复成功，必须实际执行命令验证**",
                "- 如果验证失败，请分析失败原因并继续修复，直到验证通过",
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
                "**⚠️ 重要：修复后必须验证**",
                "- 修复完成后，**必须使用 `execute_script` 工具执行以下命令验证修复效果**：",
                f"  - 命令：`{command or 'cargo check -q'}`",
                "- 验证要求：",
                "  * 如果命令执行成功（返回码为 0），说明修复成功",
                "  * 如果命令执行失败（返回码非 0），说明修复未成功，需要继续修复",
                "  * **不要假设修复成功，必须实际执行命令验证**",
                "- 如果验证失败，请分析失败原因并继续修复，直到验证通过",
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
        prompt = "\n".join(base_lines + stage_lines)
        return self._append_additional_notes(prompt)

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
            agent = self._get_code_agent()
            agent.run(self._compose_prompt_with_context(repair_prompt), prefix=f"[c2rust-transpiler][build-fix iter={check_iter}][check]", suffix="")
            # 修复后进行验证：检查编译是否正确
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
        
        # 调试输出：确认测试失败信息是否正确传递
        typer.secho(f"[c2rust-transpiler][debug] 测试失败信息长度: {len(output)} 字符", fg=typer.colors.CYAN)
        if output:
            # 提取关键错误信息用于调试
            error_lines = output.split('\n')
            key_errors = [line for line in error_lines if any(keyword in line.lower() for keyword in ['failed', 'error', 'panic', 'unwrap', 'sequence'])]
            if key_errors:
                typer.secho(f"[c2rust-transpiler][debug] 关键错误信息（前5行）:", fg=typer.colors.CYAN)
                for i, line in enumerate(key_errors[:5], 1):
                    typer.secho(f"  {i}. {line[:100]}", fg=typer.colors.CYAN)
        
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
        agent = self._get_code_agent()
        agent.run(self._compose_prompt_with_context(repair_prompt), prefix=f"[c2rust-transpiler][build-fix iter={test_iter}][test]", suffix="")
        # 修复后验证：先检查编译，再实际运行测试
        # 第一步：检查编译是否通过
        res_compile = subprocess.run(
            ["cargo", "test", "--message-format=short", "-q", "--no-run"],
            capture_output=True,
            text=True,
            check=False,
            cwd=workspace_root,
        )
        if res_compile.returncode != 0:
            typer.secho("[c2rust-transpiler][build] 修复后编译仍有错误，将在下一轮循环中处理", fg=typer.colors.YELLOW)
            # 编译失败，增加连续失败计数
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
        
        # 第二步：编译通过，实际运行测试验证
        res_test_verify = subprocess.run(
            ["cargo", "test", "--", "--nocapture"],
            capture_output=True,
            text=True,
            check=False,
            cwd=workspace_root,
        )
        if res_test_verify.returncode == 0:
            typer.secho("[c2rust-transpiler][build] 修复后测试通过，继续构建循环", fg=typer.colors.GREEN)
            # 测试真正通过，重置连续失败计数
            self._consecutive_fix_failures = 0
            return (False, False)  # 需要继续循环（但下次应该会通过）
        else:
            # 编译通过但测试仍然失败，说明修复没有解决测试逻辑问题
            typer.secho("[c2rust-transpiler][build] 修复后编译通过，但测试仍然失败，将在下一轮循环中处理", fg=typer.colors.YELLOW)
            # 测试失败，增加连续失败计数（即使编译通过）
            self._consecutive_fix_failures += 1
            # 检查是否需要回退
            if self._consecutive_fix_failures >= CONSECUTIVE_FIX_FAILURE_THRESHOLD and self._current_function_start_commit:
                typer.secho(f"[c2rust-transpiler][build] 连续修复失败 {self._consecutive_fix_failures} 次（编译通过但测试失败），回退到函数开始时的 commit: {self._current_function_start_commit}", fg=typer.colors.RED)
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
                "**审查优先级**：严重问题 > 破坏性变更 > 功能一致性 > 文件结构。优先处理可能导致程序崩溃或编译失败的问题。\n"
                "**审查范围**：主要审查当前函数的实现，相关依赖函数作为辅助参考。\n"
                "审查标准（合并了功能一致性和严重问题检查）：\n"
                "1. 功能一致性检查：\n"
                "   - **核心功能定义**：核心输入输出、主要功能逻辑是否与 C 实现一致。核心功能指函数的主要目的和预期行为（如'计算哈希值'、'解析字符串'、'压缩数据'等），不包括实现细节；\n"
                "   - **安全改进允许行为不一致**：允许 Rust 实现修复 C 代码中的安全漏洞（如缓冲区溢出、空指针解引用、未初始化内存使用、整数溢出、格式化字符串漏洞等），这些安全改进可能导致行为与 C 实现不一致，但这是允许的，不应被视为功能不一致；\n"
                "   - **忽略语言差异导致的行为不一致**：由于 Rust 和 C 语言的本质差异，以下行为差异是不可避免的，应被忽略：\n"
                "     * 整数溢出处理：Rust 在 debug 模式下会 panic，release 模式下会 wrapping，而 C 是未定义行为；\n"
                "     * 未定义行为：Rust 会避免或明确处理，而 C 可能产生未定义行为；\n"
                "     * 空指针/空引用：Rust 使用 Option<T> 或 Result<T, E> 处理，而 C 可能直接解引用导致崩溃；\n"
                "     * 内存安全：Rust 的借用检查器会阻止某些 C 中允许的不安全操作；\n"
                "     * 错误处理：Rust 使用 Result<T, E> 或 Option<T>，而 C 可能使用错误码或全局 errno；\n"
                "   - 允许 Rust 实现使用不同的类型设计、错误处理方式、资源管理方式等，只要功能一致即可；\n"
                "2. 严重问题检查（可能导致功能错误或程序崩溃）：\n"
                "   - 明显的空指针解引用或会导致 panic 的严重错误；\n"
                "   - 明显的越界访问或会导致程序崩溃的问题；\n"
                "   - 会导致程序无法正常运行的逻辑错误；\n"
                "3. 破坏性变更检测（对现有代码的影响）：\n"
                "   - 检查函数签名变更是否会导致调用方代码无法编译（如参数类型、参数数量、返回类型的变更）；\n"
                "   - 检查模块导出变更是否会影响其他模块的导入（如 pub 关键字缺失、模块路径变更）；\n"
                "   - 检查类型定义变更是否会导致依赖该类型的代码失效（如结构体字段变更、枚举变体变更）；\n"
                "   - 检查常量或静态变量变更是否会影响引用该常量的代码；\n"
                "   - **优先使用diff信息**：如果diff中已包含调用方代码信息，优先基于diff判断；只有在diff信息不足时，才使用 read_code 工具读取调用方代码进行验证；\n"
                "4. 文件结构合理性检查：\n"
                "   - 检查模块文件位置是否符合 Rust 项目约定（如 src/ 目录结构、模块层次）；\n"
                "   - 检查文件命名是否符合 Rust 命名规范（如 snake_case、模块文件命名）；\n"
                "   - 检查模块组织是否合理（如相关功能是否放在同一模块、模块拆分是否过度或不足）；\n"
                "   - 检查模块导出是否合理（如 lib.rs 中的 pub mod 声明是否正确、是否遗漏必要的导出）；\n"
                "   - 检查是否存在循环依赖或过度耦合；\n"
                "不检查类型匹配、指针可变性、边界检查细节、资源释放细节、内存语义等技术细节（除非会导致功能错误）。\n"
                "**重要要求：在总结阶段，对于发现的每个问题，必须提供：**\n"
                "1. 详细的问题描述：明确指出问题所在的位置（文件、函数、行号等）、问题的具体表现、为什么这是一个问题\n"
                "2. 具体的修复建议：提供详细的修复方案，包括需要修改的代码位置、修改方式、预期效果等\n"
                "3. 问题分类：使用 [function] 标记功能一致性问题，使用 [critical] 标记严重问题，使用 [breaking] 标记破坏性变更，使用 [structure] 标记文件结构问题\n"
                "请在总结阶段详细指出问题和修改建议，但不要尝试修复或修改任何代码，不要输出补丁。"
            )
            # 附加原始C函数源码片段，供审查作为只读参考
            c_code = self._read_source_span(rec) or ""
            # 附加被引用符号上下文与库替代上下文，以及crate目录结构，提供更完整审查背景
            callees_ctx = self._collect_callees_context(rec)
            librep_ctx = rec.lib_replacement if isinstance(rec.lib_replacement, dict) else None
            crate_tree = dir_tree(self.crate_dir)
            # 提取编译参数
            compile_flags = self._extract_compile_flags(rec.file)
            
            # 获取从初始commit到当前commit的变更作为上下文
            commit_diff = ""
            if self._current_function_start_commit:
                current_commit = self._get_crate_commit_hash()
                if current_commit and current_commit != self._current_function_start_commit:
                    try:
                        # 注意：transpile()开始时已切换到crate目录，此处无需再次切换
                        commit_diff = get_diff_between_commits(self._current_function_start_commit, current_commit)
                        if commit_diff and not commit_diff.startswith("获取") and not commit_diff.startswith("发生"):
                            # 成功获取diff，限制长度避免上下文过大
                            # 使用最大输入token数量的一半作为字符限制（1 token ≈ 4字符，所以 token/2 * 4 = token * 2）
                            max_input_tokens = get_max_input_token_count(self.llm_group)
                            max_diff_chars = max_input_tokens * 2  # 最大输入token数量的一半转换为字符数
                            if len(commit_diff) > max_diff_chars:
                                commit_diff = commit_diff[:max_diff_chars] + "\n... (差异内容过长，已截断)"
                    except Exception as e:
                        typer.secho(f"[c2rust-transpiler][review] 获取commit差异失败: {e}", fg=typer.colors.YELLOW)
            
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
                "**审查优先级**：严重问题 > 破坏性变更 > 功能一致性 > 文件结构。优先处理可能导致程序崩溃或编译失败的问题。",
                "",
                "1. 功能一致性：",
                "   - **核心功能定义**：核心输入输出、主要功能逻辑是否与 C 实现一致。核心功能指函数的主要目的和预期行为（如'计算哈希值'、'解析字符串'、'压缩数据'等），不包括实现细节；",
                "   - **安全改进允许行为不一致**：允许Rust实现修复C代码中的安全漏洞（如缓冲区溢出、空指针解引用、未初始化内存使用、整数溢出、格式化字符串漏洞等），这些安全改进可能导致行为与 C 实现不一致，但这是允许的，不应被视为功能不一致；",
                "   - **忽略语言差异导致的行为不一致**：由于 Rust 和 C 语言的本质差异，以下行为差异是不可避免的，应被忽略：",
                "     * 整数溢出处理：Rust 在 debug 模式下会 panic，release 模式下会 wrapping，而 C 是未定义行为；",
                "     * 未定义行为：Rust 会避免或明确处理，而 C 可能产生未定义行为；",
                "     * 空指针/空引用：Rust 使用 Option<T> 或 Result<T, E> 处理，而 C 可能直接解引用导致崩溃；",
                "     * 内存安全：Rust 的借用检查器会阻止某些 C 中允许的不安全操作；",
                "     * 错误处理：Rust 使用 Result<T, E> 或 Option<T>，而 C 可能使用错误码或全局 errno；",
                "   - 允许Rust实现使用不同的类型设计、错误处理方式、资源管理方式等，只要功能一致即可；",
                "2. 严重问题（可能导致功能错误）：",
                "   - 明显的空指针解引用或会导致 panic 的严重错误；",
                "   - 明显的越界访问或会导致程序崩溃的问题；",
                "3. 破坏性变更检测（对现有代码的影响）：",
                "   - 检查函数签名变更是否会导致调用方代码无法编译（如参数类型、参数数量、返回类型的变更）；",
                "   - 检查模块导出变更是否会影响其他模块的导入（如 pub 关键字缺失、模块路径变更）；",
                "   - 检查类型定义变更是否会导致依赖该类型的代码失效（如结构体字段变更、枚举变体变更）；",
                "   - 检查常量或静态变量变更是否会影响引用该常量的代码；",
                "   - **优先使用diff信息**：如果diff中已包含调用方代码信息，优先基于diff判断；只有在diff信息不足时，才使用 read_code 工具读取调用方代码进行验证；",
                "   - 如果该函数是根符号或被其他已转译函数调用，必须检查调用方代码是否仍能正常编译和使用；",
                "4. 文件结构合理性检查：",
                "   - 检查模块文件位置是否符合 Rust 项目约定（如 src/ 目录结构、模块层次）；",
                "   - 检查文件命名是否符合 Rust 命名规范（如 snake_case、模块文件命名）；",
                "   - 检查模块组织是否合理（如相关功能是否放在同一模块、模块拆分是否过度或不足）；",
                "   - 检查模块导出是否合理（如 lib.rs 中的 pub mod 声明是否正确、是否遗漏必要的导出）；",
                "   - 检查是否存在循环依赖或过度耦合；",
                "   - 检查文件大小是否合理（如单个文件是否过大需要拆分，或是否过度拆分导致文件过多）；",
                "不检查类型匹配、指针可变性、边界检查细节等技术细节（除非会导致功能错误）。",
                "",
                "**重要：问题报告要求**",
                "对于发现的每个问题，必须在总结中提供：",
                "1. 详细的问题描述：明确指出问题所在的位置（文件、函数、行号等）、问题的具体表现、为什么这是一个问题",
                "2. 具体的修复建议：提供详细的修复方案，包括需要修改的代码位置、修改方式、预期效果等",
                "3. 问题分类：使用 [function] 标记功能一致性问题，使用 [critical] 标记严重问题，使用 [breaking] 标记破坏性变更，使用 [structure] 标记文件结构问题",
                "示例：",
                '  "[function] 返回值处理缺失：在函数 foo 的第 42 行，当输入参数为负数时，函数没有返回错误码，但 C 实现中会返回 -1。修复建议：在函数开始处添加参数验证，当参数为负数时返回 Result::Err(Error::InvalidInput)。"',
                '  "[critical] 空指针解引用风险：在函数 bar 的第 58 行，直接解引用指针 ptr 而没有检查其是否为 null，可能导致 panic。修复建议：使用 if let Some(value) = ptr.as_ref() 进行空指针检查，或使用 Option<&T> 类型。"',
                '  "[breaking] 函数签名变更导致调用方无法编译：函数 baz 的签名从 `fn baz(x: i32) -> i32` 变更为 `fn baz(x: i64) -> i64`，但调用方代码（src/other.rs:15）仍使用 i32 类型调用，会导致类型不匹配错误。修复建议：保持函数签名与调用方兼容，或同时更新所有调用方代码。"',
                '  "[structure] 模块导出缺失：函数 qux 所在的模块 utils 未在 src/lib.rs 中导出，导致无法从 crate 外部访问。修复建议：在 src/lib.rs 中添加 `pub mod utils;` 声明。"',
                "",
                "被引用符号上下文（如已转译则包含Rust模块信息）：",
                json.dumps(callees_ctx, ensure_ascii=False, indent=2),
                "",
                "库替代上下文（若存在）：",
                json.dumps(librep_ctx, ensure_ascii=False, indent=2),
                "",
                *([f"禁用库列表（禁止在实现中使用这些库）：{', '.join(self.disabled_libraries)}"] if self.disabled_libraries else []),
                *([f"根符号要求：此函数是根符号（{rec.qname or rec.name}），必须使用 `pub` 关键字对外暴露，确保可以从 crate 外部访问。同时，该函数所在的模块必须在 src/lib.rs 中被导出（使用 `pub mod <模块名>;`）。"] if self._is_root_symbol(rec) else []),
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
            ])
            
            # 添加commit变更上下文（如果存在）
            if commit_diff:
                usr_p_lines.extend([
                    "",
                    "从函数开始到当前的commit变更（用于了解代码变更历史和上下文）：",
                    "<COMMIT_DIFF>",
                    commit_diff,
                    "</COMMIT_DIFF>",
                    "",
                    "**重要：commit变更上下文说明**",
                    "- 上述diff显示了从函数开始处理时的commit到当前commit之间的所有变更",
                    "- 这些变更可能包括：当前函数的实现、依赖函数的实现、模块结构的调整等",
                    "- **优先使用diff信息进行审查判断**：如果diff中已经包含了足够的信息（如函数实现、签名变更、模块结构等），可以直接基于diff进行审查，无需读取原始文件",
                    "- 只有在diff信息不足或需要查看完整上下文时，才使用 read_code 工具读取原始文件",
                    "- 在审查破坏性变更时，请特别关注这些变更对现有代码的影响",
                    "- 如果发现变更中存在问题（如破坏性变更、文件结构不合理等），请在审查报告中指出",
                ])
            else:
                usr_p_lines.extend([
                    "",
                    "**注意**：由于无法获取commit差异信息，请使用 read_code 工具读取目标模块文件的最新内容进行审查。",
                ])
            
            usr_p_lines.extend([
                "",
                "如需定位或交叉验证 C 符号位置，请使用符号表检索工具：",
                "- 工具: read_symbols",
                "- 参数示例(JSON):",
                f"  {{\"symbols_file\": \"{(self.data_dir / 'symbols.jsonl').resolve()}\", \"symbols\": [\"{rec.qname or rec.name}\"]}}",
                "",
                "**重要：审查要求**",
                "- **优先使用diff信息**：如果提供了commit差异（COMMIT_DIFF），优先基于diff信息进行审查判断，只有在diff信息不足时才使用 read_code 工具读取原始文件",
                "- 必须基于最新的代码进行审查，如果使用 read_code 工具，请读取目标模块文件的最新内容",
                "- 禁止依赖任何历史记忆、之前的审查结论或对话历史进行判断",
                "- 每次审查都必须基于最新的代码状态（通过diff或read_code获取），确保审查结果反映当前代码的真实状态",
                "- 结合commit变更上下文（如果提供），全面评估代码变更的影响和合理性",
                "",
                "请基于提供的diff信息（如果可用）或读取crate中该函数的当前实现进行审查，并准备总结。",
            ])
            usr_p = "\n".join(usr_p_lines)
            sum_p = (
                "请仅输出一个 <SUMMARY> 块，块内直接包含 JSON 对象（不需要额外的标签），字段：\n"
                '"ok": bool  // 若满足功能一致且无严重问题、无破坏性变更、文件结构合理，则为 true\n'
                '"function_issues": [string, ...]  // 功能一致性问题，每项以 [function] 开头，必须包含详细的问题描述和修复建议\n'
                '"critical_issues": [string, ...]  // 严重问题（可能导致功能错误），每项以 [critical] 开头，必须包含详细的问题描述和修复建议\n'
                '"breaking_issues": [string, ...]  // 破坏性变更问题（对现有代码的影响），每项以 [breaking] 开头，必须包含详细的问题描述和修复建议\n'
                '"structure_issues": [string, ...]  // 文件结构问题，每项以 [structure] 开头，必须包含详细的问题描述和修复建议\n'
                "注意：\n"
                "- 前置条件：必须在crate中找到该函数的实现（匹配函数名或签名）。若未找到，ok 必须为 false，function_issues 应包含 [function] function not found: 详细描述问题位置和如何查找函数实现\n"
                "- **安全改进允许行为不一致**：若Rust实现修复了C代码中的安全漏洞（如缓冲区溢出、空指针解引用、未初始化内存使用等），即使导致行为与 C 实现不一致，这也是允许的，不应被视为功能不一致；\n"
                "- **忽略语言差异导致的行为不一致**：由于 Rust 和 C 语言的本质差异（如内存安全、类型系统、错误处理、未定义行为处理等），某些行为差异是不可避免的，这些差异应被忽略，不应被视为功能不一致；\n"
                "- 若Rust实现使用了不同的实现方式但保持了功能一致，且无严重问题、无破坏性变更、文件结构合理，ok 应为 true\n"
                "- 仅报告功能不一致、严重问题、破坏性变更和文件结构问题，不报告类型匹配、指针可变性、边界检查细节等技术细节（除非会导致功能错误）\n"
                "- **重要：每个问题描述必须包含以下内容：**\n"
                "  1. 问题的详细描述：明确指出问题所在的位置（文件、函数、行号等）、问题的具体表现、为什么这是一个问题\n"
                "  2. 修复建议：提供具体的修复方案，包括需要修改的代码位置、修改方式、预期效果等\n"
                "  3. 问题格式：[function]、[critical]、[breaking] 或 [structure] 开头，后跟详细的问题描述和修复建议\n"
                "  示例格式：\n"
                '    "[function] 返回值处理缺失：在函数 foo 的第 42 行，当输入参数为负数时，函数没有返回错误码，但 C 实现中会返回 -1。修复建议：在函数开始处添加参数验证，当参数为负数时返回 Result::Err(Error::InvalidInput)。"\n'
                '    "[critical] 空指针解引用风险：在函数 bar 的第 58 行，直接解引用指针 ptr 而没有检查其是否为 null，可能导致 panic。修复建议：使用 if let Some(value) = ptr.as_ref() 进行空指针检查，或使用 Option<&T> 类型。"\n'
                '    "[breaking] 函数签名变更导致调用方无法编译：函数 baz 的签名从 `fn baz(x: i32) -> i32` 变更为 `fn baz(x: i64) -> i64`，但调用方代码（src/other.rs:15）仍使用 i32 类型调用，会导致类型不匹配错误。修复建议：保持函数签名与调用方兼容，或同时更新所有调用方代码。"\n'
                '    "[structure] 模块导出缺失：函数 qux 所在的模块 utils 未在 src/lib.rs 中导出，导致无法从 crate 外部访问。修复建议：在 src/lib.rs 中添加 `pub mod utils;` 声明。"\n'
                "请严格按以下格式输出（JSON格式，支持jsonnet语法如尾随逗号、注释、|||分隔符多行字符串等）：\n"
                "<SUMMARY>\n{\n  \"ok\": true,\n  \"function_issues\": [],\n  \"critical_issues\": [],\n  \"breaking_issues\": [],\n  \"structure_issues\": []\n}\n</SUMMARY>"
            )
            # 在 usr_p 和 sum_p 中追加附加说明（sys_p 通常不需要）
            usr_p = self._append_additional_notes(usr_p)
            sum_p = self._append_additional_notes(sum_p)
            return sys_p, usr_p, sum_p

        i = 0
        max_iterations = self.review_max_iterations
        # 复用 Review Agent（仅在本函数生命周期内构建一次）
        # 注意：Agent 必须在 crate 根目录下创建，以确保工具（如 read_symbols）能正确获取符号表
        # 由于 transpile() 开始时已切换到 crate 目录，此处无需再次切换
        review_key = f"review::{rec.id}"
        sys_p_init, usr_p_init, sum_p_init = build_review_prompts()
        
        # 获取函数信息用于 Agent name
        fn_name = rec.qname or rec.name or f"fn_{rec.id}"
        agent_name = f"C2Rust-Review-Agent({fn_name})"
        
        if self._current_agents.get(review_key) is None:
            self._current_agents[review_key] = Agent(
                system_prompt=sys_p_init,
                name=agent_name,
                model_group=self.llm_group,
                summary_prompt=sum_p_init,
                need_summary=True,
                auto_complete=True,
                use_tools=["execute_script", "read_code", "read_symbols"],
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
            # 如果是修复后的审查（i > 0），强制要求重新读取代码
            if i > 0:
                # 修复后重新创建 Agent，清除之前的对话历史和记忆，确保基于最新代码审查
                typer.secho(f"[c2rust-transpiler][review] 代码已修复，重新创建审查 Agent 以清除历史（第 {i+1} 次迭代）", fg=typer.colors.YELLOW)
                self._current_agents[review_key] = Agent(
                    system_prompt=sys_p_init,
                    name=agent_name,
                    model_group=self.llm_group,
                    summary_prompt=sum_p_init,
                    need_summary=True,
                    auto_complete=True,
                    use_tools=["execute_script", "read_code", "read_symbols"],
                    non_interactive=self.non_interactive,
                    use_methodology=False,
                    use_analysis=False,
                )
                agent = self._current_agents[review_key]
                
                code_changed_notice = "\n".join([
                    "",
                    "【重要：代码已更新】",
                    f"在本次审查之前（第 {i} 次迭代），已根据审查意见对代码进行了修复和优化。",
                    "目标函数的实现已经发生变化，包括但不限于：",
                    "- 函数实现逻辑的修改",
                    "- 类型和签名的调整",
                    "- 依赖关系的更新",
                    "- 错误处理的改进",
                    "",
                    "**审查要求：**",
                    "- **优先使用diff信息**：如果提供了最新的commit差异（COMMIT_DIFF），优先基于diff信息进行审查判断，只有在diff信息不足时才使用 read_code 工具读取原始文件",
                    "- 如果必须使用 read_code 工具，请读取目标模块文件的最新内容",
                    "- **禁止基于之前的审查结果、对话历史或任何缓存信息进行判断**",
                    "- 必须基于最新的代码状态（通过diff或read_code获取）进行审查评估",
                    "",
                    "如果diff信息充足，可以直接基于diff进行审查；如果diff信息不足，请使用 read_code 工具读取最新代码。",
                    "",
                ])
                usr_p_with_notice = usr_p_init + code_changed_notice
                composed_prompt = self._compose_prompt_with_context(usr_p_with_notice)
                # 修复后必须使用 Agent.run()，不能使用直接模型调用（因为需要工具调用）
                use_direct_model_review = False
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
                        f"请确保输出的JSON格式正确，包括正确的引号、逗号、大括号等。JSON 对象必须包含字段：ok（布尔值）、function_issues（字符串数组）、critical_issues（字符串数组）、breaking_issues（字符串数组）、structure_issues（字符串数组）。支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。"
                    )
                elif parse_failed:
                    error_guidance = (
                        "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n"
                        "- 无法从摘要中解析出有效的 JSON 对象\n\n"
                        "请确保输出格式正确：仅输出一个 <SUMMARY> 块，块内直接包含 JSON 对象（不需要额外的标签），字段：ok（布尔值）、function_issues（字符串数组）、critical_issues（字符串数组）、breaking_issues（字符串数组）、structure_issues（字符串数组）。支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。"
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
            verdict, parse_error_review = extract_json_from_summary(summary)
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
                    verdict = {"ok": True, "function_issues": [], "critical_issues": [], "breaking_issues": [], "structure_issues": []}
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
                    verdict = {"ok": True, "function_issues": [], "critical_issues": [], "breaking_issues": [], "structure_issues": []}
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
            breaking_issues = verdict.get("breaking_issues") if isinstance(verdict.get("breaking_issues"), list) else []
            structure_issues = verdict.get("structure_issues") if isinstance(verdict.get("structure_issues"), list) else []
            all_issues = function_issues + critical_issues + breaking_issues + structure_issues
            
            typer.secho(f"[c2rust-transpiler][review][iter={i+1}] verdict ok={ok}, function_issues={len(function_issues)}, critical_issues={len(critical_issues)}, breaking_issues={len(breaking_issues)}, structure_issues={len(structure_issues)}", fg=typer.colors.CYAN)
            
            # 如果 ok 为 true，表示审查通过（功能一致且无严重问题、无破坏性变更、文件结构合理），直接返回，不触发修复
            if ok:
                limit_info = f" (上限: {max_iterations if max_iterations > 0 else '无限'})"
                typer.secho(f"[c2rust-transpiler][review] 代码审查通过{limit_info} (共 {i+1} 次迭代)。", fg=typer.colors.GREEN)
                # 记录审查结果到进度
                try:
                    cur = self.progress.get("current") or {}
                    cur["review"] = {
                        "ok": True,
                        "function_issues": list(function_issues),
                        "critical_issues": list(critical_issues),
                        "breaking_issues": list(breaking_issues),
                        "structure_issues": list(structure_issues),
                        "iterations": i + 1,
                    }
                    metrics = cur.get("metrics") or {}
                    metrics["review_iterations"] = i + 1
                    metrics["function_issues"] = len(function_issues)
                    metrics["type_issues"] = len(critical_issues)
                    metrics["breaking_issues"] = len(breaking_issues)
                    metrics["structure_issues"] = len(structure_issues)
                    cur["metrics"] = metrics
                    self.progress["current"] = cur
                    self._save_progress()
                except Exception:
                    pass
                return
            
            # 需要优化：提供详细上下文背景，并明确审查意见仅针对 Rust crate，不修改 C 源码
            crate_tree = dir_tree(self.crate_dir)
            issues_text = "\n".join([
                "功能一致性问题：" if function_issues else "",
                *[f"  - {issue}" for issue in function_issues],
                "严重问题（可能导致功能错误）：" if critical_issues else "",
                *[f"  - {issue}" for issue in critical_issues],
                "破坏性变更问题（对现有代码的影响）：" if breaking_issues else "",
                *[f"  - {issue}" for issue in breaking_issues],
                "文件结构问题：" if structure_issues else "",
                *[f"  - {issue}" for issue in structure_issues],
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
                "- 注释规范：所有代码注释（包括文档注释、行内注释、块注释等）必须使用中文；",
                *([f"- **禁用库约束**：禁止在优化中使用以下库：{', '.join(self.disabled_libraries)}。如果这些库在 Cargo.toml 中已存在，请移除相关依赖；如果优化需要使用这些库的功能，请使用标准库或其他允许的库替代。"] if self.disabled_libraries else []),
                *([f"- **根符号要求**：此函数是根符号（{rec.qname or rec.name}），必须使用 `pub` 关键字对外暴露，确保可以从 crate 外部访问。同时，该函数所在的模块必须在 src/lib.rs 中被导出（使用 `pub mod <模块名>;`）。"] if self._is_root_symbol(rec) else []),
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
            ca = self._get_code_agent()
            limit_info = f"/{max_iterations}" if max_iterations > 0 else "/∞"
            fix_prompt_with_notes = self._append_additional_notes(fix_prompt)
            ca.run(self._compose_prompt_with_context(fix_prompt_with_notes), prefix=f"[c2rust-transpiler][review-fix iter={i+1}{limit_info}]", suffix="")
            # 优化后进行一次构建验证；若未通过则进入构建修复循环，直到通过为止
            self._cargo_build_loop()
            
            # 记录本次审查结果
            try:
                cur = self.progress.get("current") or {}
                cur["review"] = {
                    "ok": False,
                    "function_issues": list(function_issues),
                    "critical_issues": list(critical_issues),
                    "breaking_issues": list(breaking_issues),
                    "structure_issues": list(structure_issues),
                    "iterations": i + 1,
                }
                metrics = cur.get("metrics") or {}
                metrics["function_issues"] = len(function_issues)
                metrics["type_issues"] = len(critical_issues)
                metrics["breaking_issues"] = len(breaking_issues)
                metrics["structure_issues"] = len(structure_issues)
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

            order_path = ensure_order_file(self.project_root)
            steps = iter_order_steps(order_path)
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
            # 计算需要处理的函数总数（排除已完成的）
            total_to_process = len([fid for fid in seq if fid not in done])
            current_index = 0
            typer.secho(f"[c2rust-transpiler][order] 顺序信息: 步骤数={len(steps)} 总ID={sum(len(g) for g in steps)} 已转换={len(done)} 待处理={total_to_process}", fg=typer.colors.BLUE)

            for fid in seq:
                if fid in done:
                    continue
                rec = self.fn_index_by_id.get(fid)
                if not rec:
                    continue
                if self._should_skip(rec):
                    typer.secho(f"[c2rust-transpiler][skip] 跳过 {rec.qname or rec.name} (id={rec.id}) 位于 {rec.file}:{rec.start_line}-{rec.end_line}", fg=typer.colors.YELLOW)
                    continue

                # 更新进度索引
                current_index += 1
                progress_info = f"({current_index}/{total_to_process})" if total_to_process > 0 else ""

                # 读取C函数源码
                typer.secho(f"[c2rust-transpiler][read] {progress_info} 读取 C 源码: {rec.qname or rec.name} (id={rec.id}) 来自 {rec.file}:{rec.start_line}-{rec.end_line}", fg=typer.colors.BLUE)
                c_code = self._read_source_span(rec)
                typer.secho(f"[c2rust-transpiler][read] 已加载 {len(c_code.splitlines()) if c_code else 0} 行", fg=typer.colors.BLUE)

                # 若缺少源码片段且缺乏签名/参数信息，则跳过本函数，记录进度以便后续处理
                if not c_code and not (getattr(rec, "signature", "") or getattr(rec, "params", None)):
                    skipped = self.progress.get("skipped_missing_source") or []
                    if rec.id not in skipped:
                        skipped.append(rec.id)
                    self.progress["skipped_missing_source"] = skipped
                    typer.secho(f"[c2rust-transpiler] {progress_info} 跳过：缺少源码与签名信息 -> {rec.qname or rec.name} (id={rec.id})", fg=typer.colors.YELLOW)
                    self._save_progress()
                    continue
                # 1) 规划：模块路径与Rust签名
                typer.secho(f"[c2rust-transpiler][plan] {progress_info} 正在规划模块与签名: {rec.qname or rec.name} (id={rec.id})", fg=typer.colors.CYAN)
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
                            # 过滤掉 "mod" 关键字和 .rs 文件
                            if top_mod != "mod" and not top_mod.endswith(".rs"):
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
                    typer.secho(f"[c2rust-transpiler][deps] {progress_info} 未解析的被调符号: {', '.join(unresolved) if unresolved else '(none)'}", fg=typer.colors.BLUE)
                    typer.secho(f"[c2rust-transpiler][gen] {progress_info} 正在为 {rec.qname or rec.name} 生成 Rust 实现", fg=typer.colors.GREEN)
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
                typer.secho(f"[c2rust-transpiler][review] {progress_info} 开始代码审查: {rec.qname or rec.name}", fg=typer.colors.MAGENTA)
                self._review_and_optimize(rec, module, rust_sig)
                typer.secho("[c2rust-transpiler][review] 代码审查完成", fg=typer.colors.MAGENTA)

                # 5) 标记已转换与映射记录（JSONL）
                self._mark_converted(rec, module, rust_sig)
                typer.secho(f"[c2rust-transpiler][mark] {progress_info} 已标记并建立映射: {rec.qname or rec.name} -> {module}", fg=typer.colors.GREEN)

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
    disabled_libraries: Optional[List[str]] = None,  # None 表示从配置文件恢复
    root_symbols: Optional[List[str]] = None,  # None 表示从配置文件恢复
    non_interactive: bool = True,
) -> None:
    """
    入口函数：执行转译流程
    - project_root: 项目根目录（包含 .jarvis/c2rust/symbols.jsonl）
    - crate_dir: Rust crate 根目录；默认遵循 "<parent>/<cwd_name>_rs"（与当前目录同级，若 project_root 为 ".")
    - llm_group: 指定 LLM 模型组
    - max_retries: 构建与审查迭代的最大次数
    注意: 断点续跑功能默认始终启用
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
        disabled_libraries=disabled_libraries,
        root_symbols=root_symbols,
        non_interactive=non_interactive,
    )
    t.transpile()