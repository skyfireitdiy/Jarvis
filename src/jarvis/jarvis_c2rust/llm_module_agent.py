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
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from jarvis.jarvis_c2rust.scanner import find_root_function_ids
from jarvis.jarvis_agent import Agent  # 复用 LLM Agent 能力


@dataclass
class _FnMeta:
    id: int
    name: str
    qname: str
    signature: str
    file: str
    calls: List[str]

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
    从 functions.db 读取函数与调用关系，提供子图遍历能力
    """

    def __init__(self, db_path: Path, project_root: Path):
        self.db_path = Path(db_path)
        self.project_root = Path(project_root).resolve()
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        self.fn_by_id: Dict[int, _FnMeta] = {}
        self.name_to_id: Dict[str, int] = {}
        self.adj: Dict[int, List[str]] = {}
        self._load_db()

    def _load_db(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id, name, qualified_name, signature, file, calls_json FROM functions"
        ).fetchall()
        for fid, name, qname, sig, file_path, calls_json in rows:
            fid = int(fid)
            nm = name or ""
            qn = qname or ""
            sg = sig or ""
            fp = file_path or ""
            try:
                calls = json.loads(calls_json or "[]")
                if not isinstance(calls, list):
                    calls = []
                calls = [c for c in calls if isinstance(c, str) and c]
            except Exception:
                calls = []
            meta = _FnMeta(
                id=fid,
                name=nm,
                qname=qn,
                signature=sg,
                file=fp,
                calls=calls,
            )
            self.fn_by_id[fid] = meta
            if nm:
                self.name_to_id.setdefault(nm, fid)
            if qn:
                self.name_to_id.setdefault(qn, fid)
            self.adj[fid] = calls
        conn.close()

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
        为每个根函数构造上下文:
        - root_label
        - namespaces: [{name, functions(截断)}]，C 代码归类 'c'
        - source_files: 该子图涉及的相对路径文件列表（去重）
        - externals: 外部调用名（可能较多，做截断）
        """
        root_contexts: List[Dict[str, Any]] = []
        for rid in roots:
            meta = self.fn_by_id.get(rid)
            root_label = (meta.qname or meta.name or f"fn_{rid}") if meta else f"fn_{rid}"

            visited_ids, externals = self.collect_subgraph(rid)
            ns_groups: Dict[str, List[str]] = {}
            files: Set[str] = set()

            for fid in sorted(visited_ids):
                m = self.fn_by_id.get(fid)
                if not m:
                    continue
                ns = m.top_namespace
                ns_groups.setdefault(ns, [])
                if len(ns_groups[ns]) < max_functions_per_ns:
                    ns_groups[ns].append(m.qname or m.name or f"fn_{fid}")
                files.add(self._rel_path(m.file))

            ns_items = sorted(ns_groups.items(), key=lambda kv: kv[0])
            if len(ns_items) > max_namespaces_per_root:
                ns_items = ns_items[:max_namespaces_per_root]

            ns_list = [{"name": ns, "functions": fns} for ns, fns in ns_items]

            root_contexts.append(
                {
                    "root_function": root_label,
                    "namespaces": ns_list,
                    "source_files": sorted(list(files)),
                    "externals": sorted(list(externals))[:1000],
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
    ):
        self.project_root = Path(project_root).resolve()
        self.db_path = (
            Path(db_path).resolve()
            if db_path is not None
            else (self.project_root / ".jarvis" / "c2rust" / "functions.db")
        )
        self.loader = _GraphLoader(self.db_path, self.project_root)

    def _crate_name(self) -> str:
        base = self.project_root.name or "c2rust_crate"
        return _sanitize_mod_name(base)

    def _build_user_prompt(self, roots_context: List[Dict[str, Any]]) -> str:
        """
        构造 user prompt，包含必要上下文，强约束 LLM 输出 YAML
        """
        crate_name = self._crate_name()
        # 压缩上下文为 JSON（可读，易被模型消费）
        context_json = json.dumps(
            {"crate_name": crate_name, "roots": roots_context},
            ensure_ascii=False,
            indent=2,
        )

        # 约束输出 schema，避免啰嗦说明
        schema = """
请仅输出 YAML（不要包含任何解释文字、前后缀），遵循下列 schema 字段：
crate_name: <string>
src_tree:
  - "lib.rs"
  - { "ffi/": ["mod.rs"] }          # 如果需要
  - { "roots/": [ { "<root_mod>/": ["mod.rs"] }, ... ] }   # 按需要
lib_rs:
  modules:                          # 需要在 lib.rs 中声明的模块
    - <module_name>
modules:                            # 具体模块列表
  - name: <string>                  # 模块名，如 "ffi" 或 "root_<...>"
    path: <string>                  # 建议路径，如 "ffi/mod.rs" 或 "roots/<root_mod>/mod.rs"
    root_function: <string>         # 仅对根模块需要；ffi 可省略
    namespaces:                     # 按顶层命名空间聚类（C 代码归 'c'）
      - name: <string>
        functions:
          - <function_qualified_or_simple_name>
    source_files:
      - <relative_file_path>
    externals:                      # 不在 DB 的外部调用符号
      - <external_func_name>
summary:
  roots_count: <int>
  externals_count: <int>
""".strip()

        guidance = """
规划原则：
- 以“无内部调用者”的函数作为根，每个根 -> 一个顶层模块：root_<root_name>
- 根模块内部按顶层命名空间拆分（C 代码归 'c'，C++ 取第一个命名空间/类名作为分组）
- 对于 DB 外部调用（externals），建议汇总进 'ffi' 模块，lib.rs 应导出该模块（如存在）
- 保持模块名/文件名符合 Rust 规范（小写、下划线），避免使用特殊字符
- 请严格按照 schema 输出，仅输出 YAML，不要输出额外说明
""".strip()

        user_prompt = f"""
下面提供了项目的调用图上下文（JSON），请据此生成 Rust crate 的目录规划（仅输出 YAML）：
<context>
{context_json}
</context>

输出要求：
{schema}

{guidance}
""".strip()
        return user_prompt

    def _build_system_prompt(self) -> str:
        """
        系统提示：约束角色与输出风格（仅 YAML）
        """
        return (
            "你是资深 Rust 架构师。任务是根据给定的函数调用子图上下文，规划合理的 Rust crate 模块结构。\n"
            "务必只输出 YAML，不要输出额外说明、注释或 Markdown。"
        )

    def plan_crate_yaml(self) -> str:
        """
        主流程：准备上下文 -> 构造提示 -> 通过 Agent 的模型调用生成 YAML
        """
        roots = find_root_function_ids(self.db_path)
        roots_ctx = self.loader.build_roots_context(roots)

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(roots_ctx)

        # 创建 LLM Agent，但避免进入工具循环，直接使用其模型能力
        agent = Agent(
            system_prompt=system_prompt,
            name="C2Rust-LLM-Module-Planner",
            need_summary=False,
            auto_complete=True,
            use_tools=[],        # 禁用工具，避免干扰
            plan=False,          # 关闭内置任务规划
            non_interactive=True # 非交互
        )

        # 直接使用底层模型进行一次性对话，避免进入 run_loop
        yaml_text = agent.model.chat_until_success(user_prompt)  # type: ignore
        return yaml_text or ""


def plan_crate_yaml_llm(
    project_root: Union[Path, str] = ".",
    db_path: Optional[Union[Path, str]] = None,
) -> str:
    """
    便捷函数：使用 LLM 生成 Rust crate 模块规划（YAML）
    """
    agent = LLMRustCratePlannerAgent(project_root=project_root, db_path=db_path)
    return agent.plan_crate_yaml()