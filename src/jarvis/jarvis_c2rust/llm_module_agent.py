# -*- coding: utf-8 -*-
"""
LLM 驱动的 Rust Crate 模块规划 Agent

目标:
- 复用 scanner 中的 find_root_function_ids 与调用图信息，构造“以根函数为起点”的上下文
- 通过 jarvis_agent.Agent 调用 LLM，基于上下文生成 Rust crate 的目录规划（YAML）

设计要点:
- 与现有 scanner/cli 解耦，最小侵入新增模块
- 使用 jarvis_agent.Agent 的平台与系统提示管理能力，但不走完整工具循环，直接进行一次性对话生成
- 对输出格式进行强约束：仅输出 YAML，无解释文本

用法:
  from jarvis.jarvis_c2rust.llm_module_agent import plan_crate_yaml_llm
  print(plan_crate_yaml_llm(project_root="."))

CLI 集成建议:
  可在 jarvis_c2rust/cli.py 中新增 llm-plan 子命令调用本模块的 plan_crate_yaml_llm（已独立封装，便于后续补充）
"""

from __future__ import annotations

import json
# removed sqlite3 (migrated to JSONL/JSON)
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import re

from jarvis.jarvis_c2rust.scanner import find_root_function_ids
from jarvis.jarvis_agent import Agent  # 复用 LLM Agent 能力
from jarvis.jarvis_utils.input import user_confirm


@dataclass
class _FnMeta:
    id: int
    name: str
    qname: str
    signature: str
    file: str
    refs: List[str]

    @property
    def label(self) -> str:
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


def _sanitize_mod_name(s: str) -> str:
    s = (s or "").replace("::", "__")
    safe = []
    for ch in s:
        if ch.isalnum() or ch == "_":
            safe.append(ch.lower())
        else:
            safe.append("_")
    out = "".join(safe).strip("_")
    return out[:80] or "mod"


class _GraphLoader:
    """
    从统一的 symbols.jsonl 或回退的 functions.jsonl 读取函数与调用关系，提供子图遍历能力
    - 优先使用 symbols.jsonl（包含函数与类型，按 category 过滤出函数）
    - 回退到 functions.jsonl（仅函数）
    """

    def __init__(self, db_path: Path, project_root: Path):
        self.project_root = Path(project_root).resolve()

        def _resolve_data_path(hint: Path) -> Path:
            p = Path(hint)
            # 仅支持 symbols.jsonl，不再兼容 functions.jsonl 或 calls 字段
            # 若直接传入文件路径且为 .jsonl，则直接使用（要求内部包含 category/ref 字段）
            if p.is_file() and p.suffix.lower() == ".jsonl":
                return p
            # 目录：必须存在 symbols.jsonl
            if p.is_dir():
                return p / "symbols.jsonl"
            # 默认：项目 .jarvis/c2rust/symbols.jsonl
            return self.project_root / ".jarvis" / "c2rust" / "symbols.jsonl"

        self.data_path = _resolve_data_path(Path(db_path))
        if not self.data_path.exists():
            raise FileNotFoundError(f"symbols.jsonl not found: {self.data_path}")
        # Initialize in-memory graph structures
        self.adj: Dict[int, List[str]] = {}
        self.name_to_id: Dict[str, int] = {}
        self.fn_by_id: Dict[int, _FnMeta] = {}
        """
        Load function metadata and adjacency from symbols.jsonl (preferred) or functions.jsonl (fallback).
        当 data_path 指向 symbols.jsonl 时，仅加载 category == "function" 的记录。
        """
        rows_loaded = 0
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    # 不区分函数与类型，统一处理 symbols.jsonl 中的所有记录
                    rows_loaded += 1
                    fid = int(obj.get("id") or rows_loaded)
                    nm = obj.get("name") or ""
                    qn = obj.get("qualified_name") or ""
                    sg = obj.get("signature") or ""
                    fp = obj.get("file") or ""
                    refs = obj.get("ref")
                    # 不兼容旧数据：严格要求为列表类型，缺失则视为空
                    if not isinstance(refs, list):
                        refs = []
                    refs = [c for c in refs if isinstance(c, str) and c]
                    self.adj[fid] = refs
                    # 建立名称索引与函数元信息，供子图遍历与上下文构造使用
                    if isinstance(nm, str) and nm:
                        self.name_to_id.setdefault(nm, fid)
                    if isinstance(qn, str) and qn:
                        self.name_to_id.setdefault(qn, fid)
                    try:
                        rel_file = self._rel_path(fp)
                    except Exception:
                        rel_file = fp
                    self.fn_by_id[fid] = _FnMeta(
                        id=fid,
                        name=nm,
                        qname=qn,
                        signature=sg,
                        file=rel_file,
                        refs=refs,
                    )
        except FileNotFoundError:
            raise
        except Exception:
            # keep robust: leave loader empty on error
            pass

    def _rel_path(self, abs_path: str) -> str:
        try:
            p = Path(abs_path).resolve()
            return str(p.relative_to(self.project_root))
        except Exception:
            return abs_path

    def collect_subgraph(self, root_id: int) -> Tuple[Set[int], Set[str]]:
        """
        从 root_id 出发，收集所有可达的内部函数 (visited_ids) 与外部调用名称 (externals)
        """
        visited: Set[int] = set()
        externals: Set[str] = set()
        stack: List[int] = [root_id]
        visited.add(root_id)
        while stack:
            src = stack.pop()
            for callee in self.adj.get(src, []):
                cid = self.name_to_id.get(callee)
                if cid is not None:
                    if cid not in visited:
                        visited.add(cid)
                        stack.append(cid)
                else:
                    externals.add(callee)
        return visited, externals

    def build_roots_context(
        self,
        roots: List[int],
        max_functions_per_ns: int = 200,
        max_namespaces_per_root: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        为每个根函数构造上下文（仅函数名的调用关系，且不包含任何其他信息）：
        - root_function: 根函数的简单名称（不包含签名/限定名）
        - functions: 该根函数子图内所有可达函数的简单名称列表（不包含签名/限定名），去重、排序、可选截断
        注意：
        - 不包含文件路径、签名、限定名、命名空间、外部符号等任何其他元信息
        """
        root_contexts: List[Dict[str, Any]] = []
        for rid in roots:
            meta = self.fn_by_id.get(rid)
            root_label = (meta.name or f"fn_{rid}") if meta else f"fn_{rid}"

            visited_ids, _externals = self.collect_subgraph(rid)
            # 收集所有简单函数名
            fn_names: List[str] = []
            for fid in sorted(visited_ids):
                m = self.fn_by_id.get(fid)
                if not m:
                    continue
                simple = m.name or f"fn_{fid}"
                fn_names.append(simple)

            # 去重并排序
            try:
                fn_names = sorted(list(dict.fromkeys(fn_names)))
            except Exception:
                fn_names = sorted(list(set(fn_names)))

            root_contexts.append(
                {
                    "root_function": root_label,
                    "functions": fn_names,
                }
            )
        return root_contexts


class LLMRustCratePlannerAgent:
    """
    使用 jarvis_agent.Agent 调用 LLM 来生成 Rust crate 规划（YAML）。
    """

    def __init__(
        self,
        project_root: Union[Path, str] = ".",
        db_path: Optional[Union[Path, str]] = None,
        llm_group: Optional[str] = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.db_path = (
            Path(db_path).resolve()
            if db_path is not None
            else (self.project_root / ".jarvis" / "c2rust" / "symbols.jsonl")
        )
        self.llm_group = llm_group
        self.loader = _GraphLoader(self.db_path, self.project_root)

    def _crate_name(self) -> str:
        """
        计算crate名称：
        - 当 project_root 为当前目录时，返回 "<当前目录名>-rs"
        - 否则返回 project_root 的目录名
        - 输出用于命名/提示，保持下划线风格（不影响 Cargo 包名）
        """
        try:
            cwd = Path(".").resolve()
            if self.project_root.resolve() == cwd:
                base = f"{cwd.name}-rs"
            else:
                base = self.project_root.name or "c2rust_crate"
        except Exception:
            base = "c2rust_crate"
        return _sanitize_mod_name(base)

    def _has_original_main(self) -> bool:
        """
        判断原始项目是否包含 main 函数：
        - 若 symbols 图谱中存在函数名为 'main' 或限定名以 '::main' 结尾，则认为存在
        """
        try:
            for m in self.loader.fn_by_id.values():
                n = (m.name or "").strip()
                q = (m.qname or "").strip()
                if n == "main" or q.endswith("::main"):
                    return True
        except Exception:
            pass
        return False

    def _build_user_prompt(self, roots_context: List[Dict[str, Any]]) -> str:
        """
        主对话阶段：传入上下文，不给出输出要求，仅用于让模型获取信息并触发进入总结阶段。
        请模型仅输出 <!!!COMPLETE!!!> 以进入总结（summary）阶段。
        """
        crate_name = self._crate_name()
        has_main = self._has_original_main()
        context_json = json.dumps(
            {"meta": {"crate_name": crate_name, "main_present": has_main}, "roots": roots_context},
            ensure_ascii=False,
            indent=2,
        )
        return f"""
下面提供了项目的调用图上下文（JSON），请先通读理解，不要输出任何规划或YAML内容：
<context>
{context_json}
</context>

如果已准备好进入总结阶段以生成完整输出，请仅输出：<!!!COMPLETE!!!>
""".strip()
        """
        主对话阶段：传入上下文，不给出输出要求，仅用于让模型获取信息并触发进入总结阶段。
        请模型仅输出 <!!!COMPLETE!!!> 以进入总结（summary）阶段。
        """
        crate_name = self._crate_name()
        context_json = json.dumps(
            {"roots": roots_context},
            ensure_ascii=False,
            indent=2,
        )
        return f"""
下面提供了项目的调用图上下文（JSON），请先通读理解，不要输出任何规划或YAML内容：
<context>
{context_json}
</context>

如果已准备好进入总结阶段以生成完整输出，请仅输出：<!!!COMPLETE!!!>
""".strip()

    def _build_system_prompt(self) -> str:
        """
        系统提示：描述如何基于依赖关系进行 crate 规划的原则（不涉及对话流程或输出方式）
        """
        crate_name = self._crate_name()
        return (
            "你是资深 Rust 架构师。任务：根据给定的函数级调用关系（仅包含 root_function 及其可达的函数名列表），为目标项目规划合理的 Rust crate 结构。\n"
            "\n"
            "规划原则：\n"
            "- 根导向：以每个 root_function 为边界组织顶层模块，形成清晰的入口与责任范围。\n"
            "- 内聚优先：按调用内聚性拆分子模块，使强相关函数位于同一子模块，减少跨模块耦合。\n"
            "- 去环与分层：尽量消除循环依赖；遵循由上到下的调用方向，保持稳定依赖方向与层次清晰。\n"
            "- 共享抽取：被多个 root 使用的通用能力抽取到 common/ 或 shared/ 模块，避免重复与交叉依赖。\n"
            "- 边界隔离：将平台/IO/外设等边界能力独立到 adapter/ 或 ffi/ 等模块（如存在）。\n"
            "- 命名规范：目录/文件采用小写下划线；模块名简洁可读，避免特殊字符与过长名称。\n"
            "- 可演进性：模块粒度适中，保留扩展点，便于后续重构与逐步替换遗留代码。\n"
            "- 模块组织：每个目录的 mod.rs 声明其子目录与 .rs 子模块；顶层 lib.rs 汇聚导出主要模块与公共能力。\n"
            "- 入口策略（务必遵循，bin 仅做入口，功能尽量在 lib 中实现）：\n"
            "  * 若原始项目包含 main 函数：不要生成 src/main.rs；使用 src/bin/"
            + crate_name
            + ".rs 作为唯一可执行入口，并在其中仅保留最小入口逻辑（调用库层）；共享代码放在 src/lib.rs；\n"
            "  * 若原始项目不包含 main 函数：不要生成任何二进制入口（不创建 src/main.rs 或 src/bin/），仅生成 src/lib.rs；\n"
            "  * 多可执行仅在确有多个清晰入口时才使用 src/bin/<name>.rs；每个 bin 文件仅做入口，尽量调用库；\n"
            "  * 二进制命名：<name> 使用小写下划线，体现入口意图，避免与模块/文件重名。\n"
        )

    def _build_summary_prompt(self, roots_context: List[Dict[str, Any]]) -> str:
        """
        总结阶段：只输出目录结构的 YAML。
        要求：
        - 仅输出一个 <PROJECT> 块
        - <PROJECT> 与 </PROJECT> 之间必须是可解析的 YAML 列表，使用两空格缩进
        - 目录以 '目录名/' 表示，子项为列表；文件为纯字符串
        - 块外不得有任何字符（包括空行、注释、Markdown、解释文字、schema等）
        - 不要输出 crate 名称或其他多余字段
        """
        has_main = self._has_original_main()
        crate_name = self._crate_name()
        guidance_common = """
输出规范：
- 只输出一个 <PROJECT> 块
- 块外不得有任何字符（包括空行、注释、Markdown 等）
- 块内必须是 YAML 列表：
  - 目录项使用 '<name>/' 作为键，并在后面加冒号 ':'，其值为子项列表
  - 文件为字符串项（例如 'lib.rs'）
- 不要创建与入口无关的占位文件
""".strip()
        if has_main:
            entry_rule = f"""
入口约定（基于原始项目存在 main）：
- 必须包含 src/lib.rs；
- 不要包含 src/main.rs；
- 必须包含 src/bin/{crate_name}.rs，作为唯一可执行入口（仅做入口，调用库逻辑）；
- 如无明确多个入口，不要创建额外 bin 文件。
正确示例（标准 YAML，带冒号）：
<PROJECT>
- Cargo.toml
- src/:
  - lib.rs
  - bin/:
    - {crate_name}.rs
</PROJECT>
""".strip()
        else:
            entry_rule = """
入口约定（基于原始项目不存在 main）：
- 必须包含 src/lib.rs；
- 不要包含 src/main.rs；
- 不要包含 src/bin/ 目录。
正确示例（标准 YAML，带冒号）：
<PROJECT>
- Cargo.toml
- src/:
  - lib.rs
</PROJECT>
""".strip()
        guidance = f"{guidance_common}\n{entry_rule}"
        return f"""
请基于之前对话中已提供的<context>信息，生成总结输出（项目目录结构的 YAML）。严格遵循以下要求：

{guidance}

你的输出必须仅包含以下单个块（用项目的真实目录结构替换块内内容）：
<PROJECT>
- ...
</PROJECT>
""".strip()
        """
        总结阶段：只输出目录结构的 YAML。
        要求：
        - 仅输出一个 <PROJECT> 块
        - <PROJECT> 与 </PROJECT> 之间必须是可解析的 YAML 列表，使用两空格缩进
        - 目录以 '目录名/' 表示，子项为列表；文件为纯字符串
        - 块外不得有任何字符（包括空行、注释、Markdown、解释文字、schema等）
        - 不要输出 crate 名称或其他多余字段
        """
        guidance = """
输出规范：
- 只输出一个 <PROJECT> 块
- 块外不得有任何字符（包括空行、注释、Markdown 等）
- 块内必须是 YAML 列表：
  - 目录项使用 '<name>/' 作为键，并在后面加冒号 ':'，其值为子项列表
  - 文件为字符串项（例如 'lib.rs'）
- 入口约定（按需）：
  - 仅库：必须包含 src/lib.rs，不要包含 src/main.rs
  - 单一可执行：包含 src/main.rs；可选包含 src/lib.rs 以沉淀共享逻辑
  - 多可执行：使用 src/bin/<name>.rs 为多个二进制入口；共享代码放在 src/lib.rs
  - 不要创建与入口无关的占位 main.rs 或冗余文件
- 正确示例（标准 YAML，带冒号）：
  <PROJECT>
  - Cargo.toml
  - src/:
    - lib.rs
    - bin/:
      - cli.rs
    - database/:
      - mod.rs
      - connect.rs
  </PROJECT>
        """.strip()
        return f"""
请基于之前对话中已提供的<context>信息，生成总结输出（项目目录结构的 YAML）。严格遵循以下要求：

{guidance}

你的输出必须仅包含以下单个块（用项目的真实目录结构替换块内内容）：
<PROJECT>
- ...
</PROJECT>
""".strip()

    def _extract_yaml_from_project(self, text: str) -> str:
        """
        从 <PROJECT> 块中提取内容作为最终 YAML；若未匹配，返回原文本（兜底）。
        """
        if not isinstance(text, str) or not text:
            return ""
        m_proj = re.search(r"<PROJECT>([\\s\\S]*?)</PROJECT>", text, flags=re.IGNORECASE)
        if m_proj:
            return m_proj.group(1).strip()
        return text.strip()

    def plan_crate_yaml_with_project(self) -> List[Any]:
        """
        执行主流程并返回解析后的 YAML 对象（列表）：
        - 列表项：
          * 字符串：文件，如 "lib.rs"
          * 字典：目录及其子项，如 {"src": [ ... ]}
        """
        roots = find_root_function_ids(self.db_path)
        roots_ctx = self.loader.build_roots_context(roots)

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(roots_ctx)
        summary_prompt = self._build_summary_prompt(roots_ctx)

        # 创建 LLM Agent，启用自动完成与总结；禁用工具与规划，非交互运行
        agent = Agent(
            system_prompt=system_prompt,
            name="C2Rust-LLM-Module-Planner",
            model_group=self.llm_group,
            summary_prompt=summary_prompt,
            need_summary=True,
            auto_complete=True,
            use_tools=[],        # 禁用工具，避免干扰
            plan=False,          # 关闭内置任务规划
            non_interactive=True, # 非交互
            use_methodology=False,
            use_analysis=False,
        )

        # 进入主循环：第一轮仅输出 <!!!COMPLETE!!!> 触发自动完成；随后 summary 输出 <PROJECT> 块（仅含 YAML）
        summary_output = agent.run(user_prompt)  # type: ignore
        project_text = str(summary_output) if summary_output is not None else ""
        yaml_text = self._extract_yaml_from_project(project_text)
        yaml_entries = _parse_project_yaml_entries(yaml_text)
        return yaml_entries

    def plan_crate_yaml_text(self) -> str:
        """
        执行主流程但返回原始 <PROJECT> YAML 文本，不进行解析。
        便于后续按原样应用目录结构，避免早期解析失败导致信息丢失。
        """
        roots = find_root_function_ids(self.db_path)
        roots_ctx = self.loader.build_roots_context(roots)

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(roots_ctx)
        summary_prompt = self._build_summary_prompt(roots_ctx)

        agent = Agent(
            system_prompt=system_prompt,
            name="C2Rust-LLM-Module-Planner",
            model_group=self.llm_group,
            summary_prompt=summary_prompt,
            need_summary=True,
            auto_complete=True,
            use_tools=[],        # 禁用工具，避免干扰
            plan=False,          # 关闭内置任务规划
            non_interactive=True, # 非交互
            use_methodology=False,
            use_analysis=False,
        )
        summary_output = agent.run(user_prompt)  # type: ignore
        project_text = str(summary_output) if summary_output is not None else ""
        yaml_text = self._extract_yaml_from_project(project_text)
        return yaml_text

def plan_crate_yaml_text(
    project_root: Union[Path, str] = ".",
    db_path: Optional[Union[Path, str]] = None,
    llm_group: Optional[str] = None,
    skip_cleanup: bool = False,
) -> str:
    """
    返回 LLM 生成的目录结构原始 YAML 文本（来自 <PROJECT> 块）。
    在规划前执行预清理并征询用户确认：删除将要生成的 crate 目录、当前目录的 Cargo.toml 工作区文件，以及 .jarvis/c2rust 下的 progress.json 与 symbol_map.json。
    用户不同意则退出程序。
    当 skip_cleanup=True 时，跳过清理与确认（用于外层已处理的场景）。
    """
    # 若外层已处理清理确认，则跳过本函数的清理与确认（避免重复询问）
    if skip_cleanup:
        agent = LLMRustCratePlannerAgent(project_root=project_root, db_path=db_path, llm_group=llm_group)
        return agent.plan_crate_yaml_text()

    # 预清理（需用户确认，仅当存在目标时才提示）
    try:
        import sys
        import shutil
        cwd = Path(".").resolve()
        try:
            requested_root = Path(project_root).resolve()
        except Exception:
            requested_root = Path(project_root)
        created_dir = cwd / f"{cwd.name}-rs" if requested_root == cwd else requested_root

        cargo_path = cwd / "Cargo.toml"
        data_dir = requested_root / ".jarvis" / "c2rust"
        progress_path = data_dir / "progress.json"
        symbol_map_path = data_dir / "symbol_map.json"

        # 同时检查当前目录与 project_root 下的 Cargo.toml（两者可能不同）
        workspace_candidates: List[Path] = []
        try:
            cwd_cargo = cwd / "Cargo.toml"
            workspace_candidates.append(cwd_cargo)
        except Exception:
            pass
        try:
            root_cargo = requested_root / "Cargo.toml"
            # 避免重复添加相同路径
            if str(root_cargo.resolve()) != str(workspace_candidates[0].resolve()):
                workspace_candidates.append(root_cargo)
        except Exception:
            pass

        # 仅收集存在的目标，若无则不提示
        targets: List[str] = []
        if created_dir.exists():
            targets.append(f"- 删除 crate 目录（如存在）：{created_dir}")
        # 收集存在的 workspace 文件（当前目录或 project_root）
        for wp in workspace_candidates:
            try:
                if wp.exists():
                    targets.append(f"- 删除工作区文件：{wp}")
                else:
                    pass
            except Exception:
                pass
        if progress_path.exists():
            targets.append(f"- 删除进度文件：{progress_path}")
        if symbol_map_path.exists():
            targets.append(f"- 删除符号映射文件：{symbol_map_path}")

        if targets:
            tip_lines = ["将执行以下清理操作："] + targets + ["", "是否继续？"]
            if not user_confirm("\n".join(tip_lines), default=False):
                print("[c2rust-llm-planner] 用户取消清理操作，退出。")
                sys.exit(0)

            # 用户已确认，仅删除存在的目标
            if created_dir.exists():
                shutil.rmtree(created_dir, ignore_errors=True)
            if cargo_path.exists():
                cargo_path.unlink()
            if progress_path.exists():
                progress_path.unlink()
            if symbol_map_path.exists():
                symbol_map_path.unlink()
    except Exception:
        pass

    agent = LLMRustCratePlannerAgent(project_root=project_root, db_path=db_path, llm_group=llm_group)
    return agent.plan_crate_yaml_text()

    # 预清理（需用户确认）
    try:
        import sys
        import shutil
        cwd = Path(".").resolve()
        try:
            requested_root = Path(project_root).resolve()
        except Exception:
            requested_root = Path(project_root)
        created_dir = cwd / f"{cwd.name}-rs" if requested_root == cwd else requested_root

        cargo_path = cwd / "Cargo.toml"
        data_dir = requested_root / ".jarvis" / "c2rust"
        progress_path = data_dir / "progress.json"
        symbol_map_path = data_dir / "symbol_map.json"

        tip_lines = [
            "将执行以下清理操作：",
            f"- 删除 crate 目录（如存在）：{created_dir}",
            f"- 删除当前目录的 workspace 文件：{cargo_path}",
            f"- 删除进度文件：{progress_path}",
            f"- 删除符号映射文件：{symbol_map_path}",
            "",
            "是否继续？"
        ]
        if not user_confirm("\n".join(tip_lines), default=False):
            print("[c2rust-llm-planner] 用户取消清理操作，退出。")
            sys.exit(0)

        if created_dir.exists():
            shutil.rmtree(created_dir, ignore_errors=True)
        if cargo_path.exists():
            cargo_path.unlink()
        for p in (progress_path, symbol_map_path):
            if p.exists():
                p.unlink()
    except Exception:
        pass

    agent = LLMRustCratePlannerAgent(project_root=project_root, db_path=db_path, llm_group=llm_group)
    return agent.plan_crate_yaml_text()


def plan_crate_yaml_llm(
    project_root: Union[Path, str] = ".",
    db_path: Optional[Union[Path, str]] = None,
    skip_cleanup: bool = False,
) -> List[Any]:
    """
    便捷函数：使用 LLM 生成 Rust crate 模块规划（解析后的对象）。
    在规划前执行预清理并征询用户确认：删除将要生成的 crate 目录、当前目录的 Cargo.toml 工作区文件，以及 .jarvis/c2rust 下的 progress.json 与 symbol_map.json。
    用户不同意则退出程序。
    当 skip_cleanup=True 时，跳过清理与确认（用于外层已处理的场景）。
    """
    # 若外层已处理清理确认，则跳过本函数的清理与确认（避免重复询问）
    if skip_cleanup:
        agent = LLMRustCratePlannerAgent(project_root=project_root, db_path=db_path)
        return agent.plan_crate_yaml_with_project()

    # 预清理（需用户确认，仅当存在目标时才提示）
    try:
        import sys
        import shutil
        cwd = Path(".").resolve()
        try:
            requested_root = Path(project_root).resolve()
        except Exception:
            requested_root = Path(project_root)
        created_dir = cwd / f"{cwd.name}-rs" if requested_root == cwd else requested_root

        cargo_path = cwd / "Cargo.toml"
        data_dir = requested_root / ".jarvis" / "c2rust"
        progress_path = data_dir / "progress.json"
        symbol_map_path = data_dir / "symbol_map.json"

        # 仅收集存在的目标，若无则不提示
        targets: List[str] = []
        if created_dir.exists():
            targets.append(f"- 删除 crate 目录（如存在）：{created_dir}")
        if cargo_path.exists():
            targets.append(f"- 删除当前目录的 workspace 文件：{cargo_path}")
        if progress_path.exists():
            targets.append(f"- 删除进度文件：{progress_path}")
        if symbol_map_path.exists():
            targets.append(f"- 删除符号映射文件：{symbol_map_path}")

        if targets:
            tip_lines = ["将执行以下清理操作："] + targets + ["", "是否继续？"]
            if not user_confirm("\n".join(tip_lines), default=False):
                print("[c2rust-llm-planner] 用户取消清理操作，退出。")
                sys.exit(0)

            # 用户已确认，仅删除存在的目标
            if created_dir.exists():
                shutil.rmtree(created_dir, ignore_errors=True)
            if cargo_path.exists():
                cargo_path.unlink()
            if progress_path.exists():
                progress_path.unlink()
            if symbol_map_path.exists():
                symbol_map_path.unlink()
    except Exception:
        pass

    agent = LLMRustCratePlannerAgent(project_root=project_root, db_path=db_path)
    return agent.plan_crate_yaml_with_project()

    # 预清理（需用户确认）
    try:
        import sys
        import shutil
        cwd = Path(".").resolve()
        try:
            requested_root = Path(project_root).resolve()
        except Exception:
            requested_root = Path(project_root)
        created_dir = cwd / f"{cwd.name}-rs" if requested_root == cwd else requested_root

        cargo_path = cwd / "Cargo.toml"
        data_dir = requested_root / ".jarvis" / "c2rust"
        progress_path = data_dir / "progress.json"
        symbol_map_path = data_dir / "symbol_map.json"

        tip_lines = [
            "将执行以下清理操作：",
            f"- 删除 crate 目录（如存在）：{created_dir}",
            f"- 删除当前目录的 workspace 文件：{cargo_path}",
            f"- 删除进度文件：{progress_path}",
            f"- 删除符号映射文件：{symbol_map_path}",
            "",
            "是否继续？"
        ]
        if not user_confirm("\n".join(tip_lines), default=False):
            print("[c2rust-llm-planner] 用户取消清理操作，退出。")
            sys.exit(0)

        if created_dir.exists():
            shutil.rmtree(created_dir, ignore_errors=True)
        if cargo_path.exists():
            cargo_path.unlink()
        for p in (progress_path, symbol_map_path):
            if p.exists():
                p.unlink()
    except Exception:
        pass

    agent = LLMRustCratePlannerAgent(project_root=project_root, db_path=db_path)
    return agent.plan_crate_yaml_with_project()

def entries_to_yaml(entries: List[Any]) -> str:
    """
    将解析后的 entries 列表序列化为 YAML 文本（目录使用 'name/:' 形式，文件为字符串）
    """
    def _entries_to_yaml(items, indent=0):
        lines: List[str] = []
        for it in (items or []):
            if isinstance(it, str):
                lines.append("  " * indent + f"- {it}")
            elif isinstance(it, dict) and len(it) == 1:
                name, children = next(iter(it.items()))
                name = str(name).rstrip("/")
                lines.append("  " * indent + f"- {name}/:")
                lines.extend(_entries_to_yaml(children or [], indent + 1))
        return lines

    return "\n".join(_entries_to_yaml(entries))


def _parse_project_yaml_entries_fallback(yaml_text: str) -> List[Any]:
    """
    Fallback 解析器：当 PyYAML 不可用或解析失败时，按约定的缩进/列表语法解析 <PROJECT> 块。
    支持的子集：
    - 列表项以 "- " 开头
    - 目录项以 "- <name>/:", 其子项为下一层缩进（+2 空格）的列表
    - 文件项为 "- <filename>"
    """
    def leading_spaces(s: str) -> int:
        return len(s) - len(s.lstrip(" "))

    lines = [ln.rstrip() for ln in str(yaml_text or "").splitlines()]
    idx = 0
    n = len(lines)

    # 跳过非列表起始行
    while idx < n and not lines[idx].lstrip().startswith("- "):
        idx += 1

    def parse_list(expected_indent: int) -> List[Any]:
        nonlocal idx
        items: List[Any] = []
        while idx < n:
            line = lines[idx]
            if not line.strip():
                idx += 1
                continue
            indent = leading_spaces(line)
            if indent < expected_indent:
                break
            if not line.lstrip().startswith("- "):
                break

            # 去掉 "- "
            content = line[indent + 2 :].strip()

            # 目录项：以 ":" 结尾（形如 "src/:"）
            if content.endswith(":"):
                key = content[:-1].strip()
                idx += 1  # 消费当前目录行
                children = parse_list(expected_indent + 2)
                # 规范化目录键为以 "/" 结尾（apply 时会 rstrip("/")，二者均可）
                if not str(key).endswith("/"):
                    key = f"{str(key).rstrip('/')}/"
                items.append({key: children})
            else:
                # 文件项
                items.append(content)
                idx += 1
        return items

    base_indent = leading_spaces(lines[idx]) if idx < n else 0
    return parse_list(base_indent)


def _parse_project_yaml_entries(yaml_text: str) -> List[Any]:
    """
    使用 PyYAML 解析 <PROJECT> 块中的目录结构 YAML 为列表结构:
    - 文件项: 字符串，如 "lib.rs"
    - 目录项: 字典，形如 {"src/": [ ... ]} 或 {"src": [ ... ]}
    优先使用 PyYAML；若不可用或解析失败，则回退到轻量解析器以最大化兼容性。
    """
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(yaml_text)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    # Fallback
    return _parse_project_yaml_entries_fallback(yaml_text)


def _apply_entries_with_mods(entries: List[Any], base_path: Path) -> None:
    """
    根据解析出的 entries 创建目录与文件结构，并在每个目录的 mod.rs 中添加子模块声明：
    - 对于目录项: 创建目录，并递归处理子项；生成/更新 mod.rs，包含:
      * 对子目录: mod <dir_name>;
      * 对子文件 *.rs（排除 mod.rs）: mod <file_stem>;
    - 对于文件项: 若不存在则创建空文件
    特殊规则：
    - 对 crate 根的 src 目录：不生成 src/mod.rs，而是将子模块声明写入 src/lib.rs；
      同时忽略对 lib.rs/main.rs 的自引用
    """
    def apply_item(item: Any, dir_path: Path) -> None:
        if isinstance(item, str):
            # 文件
            file_path = dir_path / item
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if not file_path.exists():
                try:
                    file_path.write_text("", encoding="utf-8")
                except Exception:
                    pass
            return

        if isinstance(item, dict) and len(item) == 1:
            dir_name, children = next(iter(item.items()))
            name = str(dir_name).rstrip("/").strip()
            new_dir = dir_path / name
            new_dir.mkdir(parents=True, exist_ok=True)

            child_mods: List[str] = []
            mod_rs_present = False
            # 是否为 crate 根下的 src 目录
            is_src_root_dir = (new_dir == base_path / "src")

            # 先创建子项
            for child in (children or []):
                if isinstance(child, str):
                    apply_item(child, new_dir)
                    # 收集 .rs 文件作为子模块
                    if child.endswith(".rs") and child != "mod.rs":
                        stem = Path(child).stem
                        # 在 src 根目录下，忽略 lib.rs 与 main.rs 的自引用
                        if is_src_root_dir and stem in ("lib", "main"):
                            pass
                        else:
                            child_mods.append(stem)
                    if child == "mod.rs":
                        mod_rs_present = True
                elif isinstance(child, dict):
                    # 子目录
                    sub_name = list(child.keys())[0]
                    sub_mod_name = str(sub_name).rstrip("/").strip()
                    child_mods.append(sub_mod_name)
                    apply_item(child, new_dir)

            # 对 crate 根的 src 目录，使用 lib.rs 聚合子模块，不创建/更新 src/mod.rs
            if is_src_root_dir:
                lib_rs_path = new_dir / "lib.rs"
                if not lib_rs_path.exists():
                    try:
                        lib_rs_path.write_text("", encoding="utf-8")
                    except Exception:
                        pass
                try:
                    lib_existing = lib_rs_path.read_text(encoding="utf-8") if lib_rs_path.exists() else ""
                except Exception:
                    lib_existing = ""
                lib_lines = lib_existing.splitlines()
                # 解析已存在的模块声明（支持 mod / pub mod / pub(...) mod），按名称收集索引，便于升级为 pub
                mod_decl_pattern = re.compile(r'^\s*(pub(?:\s*\([^)]+\))?\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;\s*$')
                name_to_indices: Dict[str, List[int]] = {}
                name_has_pub: Set[str] = set()
                for i, ln in enumerate(lib_lines):
                    m = mod_decl_pattern.match(ln.strip())
                    if not m:
                        continue
                    mod_name = m.group(2)
                    name_to_indices.setdefault(mod_name, []).append(i)
                    if m.group(1):  # 以 pub 或 pub(...) 开头
                        name_has_pub.add(mod_name)

                # 确保所有子模块以 pub mod 形式声明；若已存在非 pub 的 mod 声明则升级为 pub mod
                for mod_name in sorted(set(child_mods)):
                    if mod_name in name_to_indices:
                        if mod_name not in name_has_pub:
                            for idx in name_to_indices[mod_name]:
                                ws_match = re.match(r'^(\s*)', lib_lines[idx])
                                leading_ws = ws_match.group(1) if ws_match else ""
                                lib_lines[idx] = f"{leading_ws}pub mod {mod_name};"
                    else:
                        lib_lines.append(f"pub mod {mod_name};")
                # 写回 lib.rs
                try:
                    lib_rs_path.write_text("\n".join(lib_lines).rstrip() + ("\n" if lib_lines else ""), encoding="utf-8")
                except Exception:
                    pass
                return  # 不再为 src 目录处理 mod.rs

            # 非 src 目录：确保存在 mod.rs
            mod_rs_path = new_dir / "mod.rs"
            if not mod_rs_present and not mod_rs_path.exists():
                try:
                    mod_rs_path.write_text("", encoding="utf-8")
                except Exception:
                    pass

            # 更新 mod.rs 的子模块声明（统一使用 pub mod，已有非 pub 的声明就地升级）
            try:
                existing = mod_rs_path.read_text(encoding="utf-8") if mod_rs_path.exists() else ""
            except Exception:
                existing = ""
            existing_lines = existing.splitlines()
            # 支持解析 mod / pub mod / pub(...) mod，并按名称收集索引以便升级为 pub
            mod_decl_pattern = re.compile(r'^\s*(pub(?:\s*\([^)]+\))?\s+)?mod\s+([A-Za-z_][A-Za-z0-9_]*)\s*;\s*$')
            name_to_indices: Dict[str, List[int]] = {}
            name_has_pub: Set[str] = set()
            for i, ln in enumerate(existing_lines):
                m = mod_decl_pattern.match(ln.strip())
                if not m:
                    continue
                mod_name = m.group(2)
                name_to_indices.setdefault(mod_name, []).append(i)
                if m.group(1):  # 已是 pub 或 pub(...)
                    name_has_pub.add(mod_name)

            # 确保所有子模块以 pub mod 声明；若已有非 pub 的声明则就地升级
            for mod_name in sorted(set(child_mods)):
                if mod_name in name_to_indices:
                    if mod_name not in name_has_pub:
                        for idx in name_to_indices[mod_name]:
                            ws_match = re.match(r'^(\s*)', existing_lines[idx])
                            leading_ws = ws_match.group(1) if ws_match else ""
                            existing_lines[idx] = f"{leading_ws}pub mod {mod_name};"
                else:
                    existing_lines.append(f"pub mod {mod_name};")
            # 写回
            try:
                mod_rs_path.write_text("\n".join(existing_lines).rstrip() + ("\n" if existing_lines else ""), encoding="utf-8")
            except Exception:
                pass

    for entry in entries:
        apply_item(entry, base_path)

def _ensure_cargo_toml(base_dir: Path, package_name: str) -> None:
    """
    确保在 base_dir 下存在合理的 Cargo.toml：
    - 如果不存在，则创建最小可用的 Cargo.toml，并设置 package.name = package_name
    - 如果已存在，则不覆盖现有内容（避免误改）
    """
    cargo_path = base_dir / "Cargo.toml"
    if cargo_path.exists():
        return
    content = f"""[package]
name = "{package_name}"
version = "0.1.0"
edition = "2024"

[dependencies]
"""
    try:
        cargo_path.write_text(content, encoding="utf-8")
    except Exception:
        pass

def apply_project_structure_from_yaml(yaml_text: str, project_root: Union[Path, str] = ".") -> None:
    """
    基于 Agent 返回的 <PROJECT> 中的目录结构 YAML，创建实际目录与文件，并在每个目录的 mod.rs 中增加子 mod 声明。
    - project_root: 目标应用路径；当为 "."（默认）时，将使用“父目录/当前目录名-rs”作为crate根目录
    同时：在当前工作目录下建立/更新 Cargo.toml，将生成的 crate 目录设置为 workspace 的 member，以便在本地当前目录下直接构建。
    """
    entries = _parse_project_yaml_entries(yaml_text)
    if not entries:
        # 严格模式：解析失败直接报错并退出，由上层 CLI 捕获打印错误
        raise ValueError("[c2rust-llm-planner] Failed to parse directory structure from LLM output. Aborting.")
    requested_root = Path(project_root).resolve()
    try:
        cwd = Path(".").resolve()
        if requested_root == cwd:
            # 默认crate不能设置为 .，设置为 当前目录/当前目录名-rs
            base_dir = cwd / f"{cwd.name}-rs"
        else:
            base_dir = requested_root
    except Exception:
        base_dir = requested_root
    base_dir.mkdir(parents=True, exist_ok=True)
    # crate name 与目录名保持一致（用于 Cargo 包名，允许连字符）
    crate_pkg_name = base_dir.name
    _apply_entries_with_mods(entries, base_dir)
    # 确保 Cargo.toml 存在并设置包名
    _ensure_cargo_toml(base_dir, crate_pkg_name)

    # 在当前工作目录创建/更新 workspace，使该 crate 作为成员
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

    try:
        _ensure_workspace_member(Path(".").resolve(), base_dir)
    except Exception:
        # 忽略 workspace 写入失败，不影响后续流程
        pass

def execute_llm_plan(
    out: Optional[Union[Path, str]] = None,
    apply: bool = False,
    crate_name: Optional[Union[Path, str]] = None,
    llm_group: Optional[str] = None,
) -> List[Any]:
    """
    返回 LLM 生成的目录结构原始 YAML 文本（来自 <PROJECT> 块）。
    不进行解析，便于后续按原样应用并在需要时使用更健壮的解析器处理。
    """
    # 预清理已由 plan_crate_yaml_text/plan_crate_yaml_llm 处理，此处不再重复确认与清理
    yaml_text = plan_crate_yaml_text(llm_group=llm_group)
    entries = _parse_project_yaml_entries(yaml_text)
    if not entries:
        raise ValueError("[c2rust-llm-planner] Failed to parse directory structure from LLM output. Aborting.")

    # 2) 如需应用到磁盘
    if apply:
        target_root = crate_name if crate_name else "."
        try:
            apply_project_structure_from_yaml(yaml_text, project_root=target_root)
            print("[c2rust-llm-planner] Project structure applied.")
        except Exception as e:
            print(f"[c2rust-llm-planner] Apply project structure failed: {e}")
            raise

        # Post-apply: 检查生成的目录结构，使用 CodeAgent 更新 Cargo.toml
        from jarvis.jarvis_code_agent.code_agent import CodeAgent  # 延迟导入以避免全局耦合
        import os
        import subprocess

        # 解析 crate 目录路径（与 apply 逻辑保持一致）
        try:
            cwd = Path(".").resolve()
            try:
                resolved_target = Path(target_root).resolve()
            except Exception:
                resolved_target = Path(target_root)

            # 若目标根目录为当前目录（无论是 "." 还是绝对路径等价于 cwd），则在当前目录下创建 "<cwd.name>-rs"
            if target_root == "." or resolved_target == cwd:
                created_dir = cwd / f"{cwd.name}-rs"
            else:
                created_dir = resolved_target
        except Exception:
            # 兜底：无法解析时直接使用传入的 target_root
            created_dir = Path(target_root)

        # 初始化并提交一次目录结构（尽力而为）
        prev_cwd_commit = os.getcwd()
        try:
            os.chdir(str(created_dir))
            # ensure git repo
            res = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                check=False,
            )
            need_init_local = False
            if res.returncode != 0:
                # 未检测到git仓库，需初始化
                need_init_local = True
            else:
                # 可能检测到的是上层仓库，这里确保当前目录自身是一个仓库根
                top_res = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                toplevel = (top_res.stdout or "").strip()
                if toplevel and Path(toplevel).resolve() != Path(os.getcwd()).resolve():
                    # 当前目录不是仓库根，初始化一个本地仓库以避免后续切回上层目录
                    need_init_local = True
                else:
                    # 还可通过检查 .git 目录进一步确认
                    git_dir_here = Path(os.getcwd()) / ".git"
                    if not git_dir_here.exists():
                        need_init_local = True
            if need_init_local:
                init_res = subprocess.run(
                    ["git", "init"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if init_res.returncode == 0:
                    print("[c2rust-llm-planner] Initialized git repository in crate directory.")
            # add and commit
            subprocess.run(["git", "add", "."], check=False)
            commit_res = subprocess.run(
                ["git", "commit", "-m", "[c2rust-llm-planner] Initialize crate structure"],
                capture_output=True,
                text=True,
                check=False,
            )
            if commit_res.returncode == 0:
                print("[c2rust-llm-planner] Initial structure committed.")
            else:
                # 常见原因：无变更、未配置 user.name/email 等
                print("[c2rust-llm-planner] Initial commit skipped or failed (no changes or git config missing).")
        finally:
            os.chdir(prev_cwd_commit)

        # 构建用于 CodeAgent 的目录上下文（简化版树形）
        def _format_tree(root: Path) -> str:
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

        dir_ctx = _format_tree(created_dir)
        crate_pkg_name = created_dir.name

        requirement_lines = [
            "目标：在该 crate 目录下确保 `cargo build` 能成功完成；如失败则根据错误最小化修改并重试，直到构建通过为止。",
            f"- crate_dir: {created_dir}",
            f"- crate_name: {crate_pkg_name}",
            "目录结构（部分）：",
            dir_ctx,
            "",
            "执行与修复流程（务必按序执行，可多轮迭代）：",
            '1) 在 Cargo.toml 的 [package] 中设置 edition："2024"；若本地工具链不支持 2024，请降级为 "2021" 并在说明中记录原因；保留其他已有字段与依赖不变。',
            "2) 根据当前源代码实际情况配置入口：",
            "   - 仅库：仅配置 [lib]（path=src/lib.rs），不要生成 main.rs；",
            "   - 单一可执行：存在 src/main.rs 时配置 [[bin]] 或默认二进制；可选保留 [lib] 以沉淀共享逻辑；",
            "   - 多可执行：为每个 src/bin/<name>.rs 配置 [[bin]]；共享代码放在 src/lib.rs；",
            "   - 不要创建与目录结构不一致的占位入口。",
            "3) 对被作为入口的源文件：若不存在 fn main() 则仅添加最小可用实现（不要改动已存在的实现）：",
            '   fn main() { println!("ok"); }',
            "4) 执行一次构建验证：`cargo build -q`（或 `cargo check -q`）。",
            "5) 若构建失败，读取错误并进行最小化修复，然后再次构建；重复直至成功。仅允许的修复类型：",
            "   - 依赖缺失：在 [dependencies] 中添加必要且稳定版本的依赖（优先无特性），避免新增未使用依赖；",
            "   - 入口/crate-type 配置错误：修正 [lib] 或 [[bin]] 的 name/path/crate-type 使之与目录与入口文件一致；",
            "   - 语言/工具链不兼容：将 edition 从 2024 调整为 2021；必要时可添加 rust-version 要求；",
            "   - 语法级/最小实现缺失：仅在入口文件中补充必要的 use/空实现/feature gate 以通过编译，避免改动非入口业务文件；",
            "   - 不要删除或移动现有文件与目录。",
            "6) 每轮修改后必须再次运行 `cargo build -q` 验证，直到构建成功为止。",
            "",
            "修改约束：",
            "- 允许修改的文件范围：Cargo.toml、src/lib.rs、src/main.rs、src/bin/*.rs（仅最小必要变更）；除非为修复构建，不要修改其他文件。",
            "- 尽量保持现有内容与结构不变，不要引入与构建无关的改动或格式化。",
            "",
            "交付要求：",
            "- 以补丁方式提交实际修改的文件；",
            "- 在最终回复中简要说明所做变更与最终 `cargo build` 的结果（成功/失败及原因）。",
        ]
        requirement_text = "\n".join(requirement_lines)

        prev_cwd = os.getcwd()
        try:
            os.chdir(str(created_dir))
            print(f"[c2rust-llm-planner] 在 {os.getcwd()} 目录下执行命令: CodeAgent 初始化")
            # 先运行一次 CodeAgent（初始化与基本配置）
            agent = CodeAgent(need_summary=False, non_interactive=True, plan=False, model_group=llm_group)
            agent.run(requirement_text, prefix="[c2rust-llm-planner]", suffix="")
            print("[c2rust-llm-planner] Initial CodeAgent run completed.")
            # 由于 CodeAgent 可能切换到上层 Git 根目录，这里强制回到 crate 目录
            os.chdir(str(created_dir))

            # 进入构建与修复循环：构建失败则生成新的 CodeAgent，携带错误上下文进行最小修复
            iter_count = 0
            while True:
                iter_count += 1
                print(f"[c2rust-llm-planner] 在 {os.getcwd()} 目录下执行命令: cargo build")
                build_res = subprocess.run(
                    ["cargo", "build", "-p", crate_pkg_name],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=prev_cwd,
                )
                stdout = build_res.stdout or ""
                stderr = build_res.stderr or ""
                output = (stdout + "\n" + stderr).strip()

                if build_res.returncode == 0:
                    print("[c2rust-llm-planner] Cargo build succeeded.")
                    break

                print(f"[c2rust-llm-planner] Cargo build failed (iter={iter_count}).")
                # 打印编译错误输出，便于可视化与调试
                print("[c2rust-llm-planner] Build error output:")
                print(output)
                # 将错误信息作为上下文，附加修复原则，生成新的 CodeAgent 进行最小修复
                repair_prompt = "\n".join([
                    requirement_text,
                    "",
                    "请根据以下构建错误进行最小化修复，然后再次执行 `cargo build` 验证：",
                    "<BUILD_ERROR>",
                    output,
                    "</BUILD_ERROR>",
                ])

                repair_agent = CodeAgent(need_summary=False, non_interactive=True, plan=False, model_group=llm_group)
                repair_agent.run(repair_prompt, prefix=f"[c2rust-llm-planner][iter={iter_count}]", suffix="")
                # CodeAgent may change directory to git root; ensure we return to the crate directory
                os.chdir(str(created_dir))
        finally:
            os.chdir(prev_cwd)

    # 3) 输出 YAML 到文件（如指定），并返回解析后的 entries
    if out is not None:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # 使用原始文本写出，便于可读
        out_path.write_text(yaml_text, encoding="utf-8")
        print(f"[c2rust-llm-planner] YAML written: {out_path}")

    return entries