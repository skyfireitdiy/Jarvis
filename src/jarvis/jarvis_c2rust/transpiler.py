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
  7) 标记函数已转译，并记录 C 符号 -> Rust 符号/模块映射到 symbol_map.json

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
SYMBOL_MAP_JSON = "symbol_map.json"


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
    calls: List[str]


class _DbLoader:
    """读取 symbols.jsonl 并提供按 id/name 查询与源码片段读取"""

    def __init__(self, project_root: Union[str, Path]) -> None:
        self.project_root = Path(project_root).resolve()
        self.data_dir = self.project_root / C2RUST_DIRNAME

        self.symbols_path = self.data_dir / SYMBOLS_JSONL
        # 统一流程：仅使用 symbols.jsonl，不再兼容 functions.jsonl
        if not self.symbols_path.exists():
            raise FileNotFoundError(
                f"symbols.jsonl not found under: {self.data_dir}"
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
                calls=refs,
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


def _ensure_order_file(project_root: Path) -> Path:
    """确保 translation_order.jsonl 存在，不存在则基于项目数据目录生成（使用统一引用图）"""
    data_dir = project_root / C2RUST_DIRNAME
    order_path = data_dir / ORDER_JSONL
    if order_path.exists():
        return order_path
    # 生成
    try:
        compute_translation_order_jsonl(data_dir, out_path=order_path)
    except Exception:
        # 尝试不传出参，由compute内部推断路径
        try:
            compute_translation_order_jsonl(data_dir)
        except Exception as e:
            raise RuntimeError(f"Failed to compute translation order: {e}")
    if not order_path.exists():
        # compute默认路径：同目录下 translation_order.jsonl
        guessed = data_dir / ORDER_JSONL
        if guessed.exists():
            return guessed
        raise FileNotFoundError(f"translation_order.jsonl not found after compute: {guessed}")
    return order_path


def _iter_order_steps(order_jsonl: Path) -> List[List[int]]:
    """读取翻译顺序，返回按步骤的函数id序列列表（扁平化为单个列表时，仍保持顺序）"""
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
            ids = obj.get("ids") or []
            if isinstance(ids, list) and ids:
                steps.append([int(x) for x in ids if isinstance(x, int) or (isinstance(x, str) and x.isdigit())])
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
    """遵循 llm_module_agent 的默认crate目录选择：<cwd>/<cwd.name>-rs 当传入为 '.' 时"""
    try:
        cwd = Path(".").resolve()
        if project_root.resolve() == cwd:
            return cwd / f"{cwd.name}-rs"
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
        self.symbol_map_path = self.data_dir / SYMBOL_MAP_JSON
        self.llm_group = llm_group
        self.max_retries = max_retries
        self.resume = resume
        self.only = set(only or [])

        self.crate_dir = Path(crate_dir) if crate_dir else _default_crate_dir(self.project_root)
        self.db = _DbLoader(self.project_root)

        self.progress: Dict[str, Any] = _read_json(self.progress_path, {"current": None, "converted": []})
        self.symbol_map: Dict[str, Dict[str, str]] = _read_json(self.symbol_map_path, {})

        # 尝试确保 crate 目录存在（不负责生成结构，假设 plan/apply 已完成）
        self.crate_dir.mkdir(parents=True, exist_ok=True)

    def _save_progress(self) -> None:
        _write_json(self.progress_path, self.progress)

    def _save_symbol_map(self) -> None:
        _write_json(self.symbol_map_path, self.symbol_map)

    def _should_skip(self, rec: FnRecord) -> bool:
        # 如果 only 列表非空，则仅处理匹配者
        if self.only:
            if rec.name in self.only or rec.qname in self.only:
                pass
            else:
                return True
        # 已转译的跳过
        if rec.qname and rec.qname in self.symbol_map:
            return True
        if rec.name and rec.name in self.symbol_map:
            return True
        return False

    def _collect_callees_context(self, rec: FnRecord) -> List[Dict[str, Any]]:
        """
        生成被引用符号上下文列表（不区分函数与类型）：
        - 若已转译：提供 {name, qname, translated: true, rust_module, rust_symbol}
        - 若未转译但存在扫描记录：提供 {name, qname, translated: false, file, start_line, end_line}
        - 若仅名称：提供 {name, qname, translated: false}
        """
        ctx: List[Dict[str, Any]] = []
        for callee in rec.calls or []:
            entry: Dict[str, Any] = {"name": callee, "qname": callee}
            # 已转映射
            if callee in self.symbol_map:
                m = self.symbol_map[callee]
                entry.update({
                    "translated": True,
                    "rust_module": m.get("module"),
                    "rust_symbol": m.get("rust_symbol"),
                })
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
        for callee in rec.calls or []:
            if callee not in self.symbol_map:
                syms.append(callee)
        # 去重
        try:
            syms = list(dict.fromkeys(syms))
        except Exception:
            syms = sorted(list(set(syms)))
        return syms
        """
        生成被调用函数上下文列表：
        - 若已转译：提供 {name, qname, translated: true, rust_module, rust_symbol}
        - 若未转译但存在扫描记录：提供 {name, qname, translated: false, file, start_line, end_line}
        - 若仅名称：提供 {name, qname, translated: false}
        """
        ctx: List[Dict[str, Any]] = []
        for callee in rec.calls or []:
            entry: Dict[str, Any] = {"name": callee, "qname": callee}
            # 已转映射
            if callee in self.symbol_map:
                m = self.symbol_map[callee]
                entry.update({
                    "translated": True,
                    "rust_module": m.get("module"),
                    "rust_symbol": m.get("rust_symbol"),
                })
                ctx.append(entry)
                continue
            # 尝试按名称解析ID
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
            '- module: "src/xxx.rs 或 src/xxx/mod.rs"\n'
            '- rust_signature: "pub fn xxx(...)->..."\n'
            '- notes: "可选说明（若有上下文缺失或风险点，请在此列出）"\n'
            "注意：\n"
            "- module 必须位于 crate 的 src/ 目录下；尽量选择已有文件；如需新建文件，给出合理路径；\n"
            "- rust_signature 请包含可见性修饰与函数名（可先用占位类型）。\n"
            "请严格按以下格式输出：\n"
            "<SUMMARY><yaml>\\nmodule: \"...\"\\nrust_signature: \"...\"\\nnotes: \"...\"\\n</yaml></SUMMARY>"
        )
        return system_prompt, user_prompt, summary_prompt

    def _plan_module_and_signature(self, rec: FnRecord, c_code: str) -> Tuple[str, str]:
        """调用 Agent 选择模块与签名，返回 (module_path, rust_signature)"""
        crate_tree = _dir_tree(self.crate_dir)
        callees_ctx = self._collect_callees_context(rec)
        sys_p, usr_p, sum_p = self._build_module_selection_prompts(rec, c_code, callees_ctx, crate_tree)

        agent = Agent(
            system_prompt=sys_p,
            name="C2Rust-Function-Planner",
            model_group=self.llm_group,
            summary_prompt=sum_p,
            need_summary=True,
            auto_complete=True,
            use_tools=[],
            plan=False,
            non_interactive=True,
            use_methodology=False,
            use_analysis=False,
        )
        summary = agent.run(usr_p)
        meta = _extract_json_from_summary(str(summary or ""))
        module = str(meta.get("module") or "").strip()
        rust_sig = str(meta.get("rust_signature") or "").strip()
        if not module:
            # 兜底：放入 src/lib.rs
            module = "src/lib.rs"
        if not rust_sig:
            # 兜底：基于C名字生成最小签名
            fn_name = rec.name or f"fn_{rec.id}"
            rust_sig = f"pub fn {fn_name}() {{ /* todo */ }}"
        return module, rust_sig

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
            f"目标：在 crate 目录 {self.crate_dir} 的 {module} 中，为 C 函数 {rec.qname or rec.name} 生成对应的 Rust 实现。",
            "要求：",
            f"- 函数签名（建议）：{rust_sig}",
            "- 若 module 文件不存在则新建；为所在模块添加必要的 mod 声明（若需要）；",
            "- 若已有函数占位/实现，尽量最小修改，不要破坏现有代码；",
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
        prev = os.getcwd()
        try:
            os.chdir(str(self.crate_dir))
            agent = CodeAgent(need_summary=False, non_interactive=True, plan=False, model_group=self.llm_group)
            agent.run(prompt, prefix="[c2rust-transpiler][gen]", suffix="")
        finally:
            os.chdir(prev)

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
                        # 记录相对 crate 根路径，便于在提示中引用
                        rel = str(p.resolve().relative_to(self.crate_dir.resolve()))
                    except Exception:
                        rel = str(p)
                    matches.append(rel)

        if not matches:
            return

        prev = os.getcwd()
        try:
            os.chdir(str(self.crate_dir))
            for rel_file in matches:
                prompt = "\n".join([
                    f"请在文件 {rel_file} 中，定位所有 todo!(\"{symbol}\") 占位并替换为对已转换函数的真实调用。",
                    "要求：",
                    f"- 已转换的目标函数名：{callee_rust_fn}",
                    f"- 其所在模块（crate路径提示）：{callee_path}",
                    f"- 函数签名提示：{callee_rust_sig}",
                    "- 你可以使用完全限定路径（如 crate::...::函数(...)），或在文件顶部添加合适的 use；",
                    "- 保持最小改动，不要进行与本次修复无关的重构或格式化；",
                    "- 如果参数列表暂不明确，可使用合理占位变量，确保编译通过。",
                    "",
                    f"仅修改 {rel_file} 中与 todo!(\"{symbol}\") 相关的代码，其他位置不要改动。",
                    "请仅输出补丁，不要输出解释或多余文本。",
                ])
                agent = CodeAgent(need_summary=False, non_interactive=True, plan=False, model_group=self.llm_group)
                agent.run(prompt, prefix=f"[c2rust-transpiler][todo-fix:{symbol}]", suffix="")
                # CodeAgent 可能切换目录，切回 crate
                os.chdir(str(self.crate_dir))
        finally:
            os.chdir(prev)

    def _cargo_build_loop(self) -> bool:
        """在 crate 目录执行 cargo build，失败则使用 CodeAgent 最小化修复，直到通过或达到上限"""
        prev = os.getcwd()
        try:
            os.chdir(str(self.crate_dir))
            i = 0
            while True:
                i += 1
                res = subprocess.run(
                    ["cargo", "build"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if res.returncode == 0:
                    print("[c2rust-transpiler] Cargo build succeeded.")
                    return True
                output = (res.stdout or "") + "\n" + (res.stderr or "")
                print(f"[c2rust-transpiler] Cargo build failed (iter={i}).")
                print(output)
                repair_prompt = "\n".join([
                    "目标：最小化修复以通过 cargo build。",
                    "允许的修复：修正入口/模块声明/依赖；对入口文件与必要mod.rs进行轻微调整；避免大范围改动。",
                    "- 保持最小改动，避免与错误无关的重构或格式化；",
                    "- 请仅输出补丁，不要输出解释或多余文本。",
                    "请阅读以下构建错误并进行必要修复：",
                    "<BUILD_ERROR>",
                    output,
                    "</BUILD_ERROR>",
                    "修复后请再次执行 cargo build 验证。",
                ])
                agent = CodeAgent(need_summary=False, non_interactive=True, plan=False, model_group=self.llm_group)
                agent.run(repair_prompt, prefix=f"[c2rust-transpiler][build-fix iter={i}]", suffix="")
                # CodeAgent 可能切换目录，切回 crate
                os.chdir(str(self.crate_dir))
        finally:
            os.chdir(prev)

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
                f"crate根目录路径：{self.crate_dir}",
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
                use_tools=[],
                plan=False,
                non_interactive=True,
                use_methodology=False,
                use_analysis=False,
            )
            summary = str(agent.run(usr_p) or "")
            m = re.search(r"<SUMMARY>([\s\S]*?)</SUMMARY>", summary, flags=re.IGNORECASE)
            content = (m.group(1).strip() if m else summary.strip()).upper()
            if content == "OK":
                print("[c2rust-transpiler] Review passed.")
                return
            # 需要优化
            fix_prompt = "\n".join([
                "请根据以下审查结论对目标函数进行最小优化（保留结构与意图，不进行大范围重构）：",
                "<REVIEW>",
                content,
                "</REVIEW>",
                "仅调整必要代码以消除审查问题。"
            ])
            prev = os.getcwd()
            try:
                os.chdir(str(self.crate_dir))
                ca = CodeAgent(need_summary=False, non_interactive=True, plan=False, model_group=self.llm_group)
                ca.run(fix_prompt, prefix=f"[c2rust-transpiler][review-fix iter={i}]", suffix="")
            finally:
                os.chdir(prev)

    def _mark_converted(self, rec: FnRecord, module: str, rust_sig: str) -> None:
        """记录映射：C 符号 -> Rust 符号与模块路径"""
        rust_symbol = ""
        # 从签名中提取函数名（简单启发：pub fn name(...)
        m = re.search(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", rust_sig)
        if m:
            rust_symbol = m.group(1)
        key = rec.qname or rec.name
        if key:
            self.symbol_map[key] = {
                "module": module,
                "rust_symbol": rust_symbol or (rec.name or f"fn_{rec.id}"),
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            }
            self._save_symbol_map()
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
            typer.secho("[c2rust-transpiler] No translation steps found.", fg=typer.colors.YELLOW)
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
                typer.secho("[c2rust-transpiler] Build not passed within retry limit; stop.", fg=typer.colors.RED)
                # 保留当前状态，便于下次 resume
                return

            # 4) 审查与优化
            self._review_and_optimize(rec, module, rust_sig)

            # 5) 标记已转换与映射记录
            self._mark_converted(rec, module, rust_sig)

            # 6) 若此前有其它函数因依赖当前符号而在源码中放置了 todo!("<symbol>")，则立即回头消除
            current_rust_fn = self._extract_rust_fn_name_from_sig(rust_sig)
            # 优先使用限定名匹配，其次使用简单名匹配
            for sym in [rec.qname, rec.name]:
                if sym:
                    self._resolve_pending_todos_for_symbol(sym, module, current_rust_fn, rust_sig)
                    # 尝试一次构建以验证修复
                    self._cargo_build_loop()

        typer.secho("[c2rust-transpiler] All eligible functions processed.", fg=typer.colors.GREEN)


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
    - crate_dir: Rust crate 根目录；默认遵循 "<cwd>/<cwd.name>-rs"（若 project_root 为 ".")
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