# -*- coding: utf-8 -*-
"""
C2Rust 剪枝（prune）逻辑：评估函数是否可由 Rust 标准库或第三方 crate 的单个 API 直接替代，并据此裁剪符号表。

从 scanner.py 中拆分，避免扫描与剪枝逻辑耦合。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import typer

# 依赖扫描器提供的根识别工具（不引入循环：本模块不被 scanner 导入）
from jarvis.jarvis_c2rust.scanner import find_root_function_ids


def evaluate_third_party_replacements(
    db_path: Path,
    out_symbols_path: Optional[Path] = None,
    out_mapping_path: Optional[Path] = None,
    llm_group: Optional[str] = None,
    max_funcs: Optional[int] = None,
    mode: str = "lib",
) -> Dict[str, Path]:
    """
    自顶向下使用 Agent 评估函数是否可由 Rust 标准库（std）或开源第三方库的单个函数调用直接替代。
    剪枝行为由参数 mode 控制：
    - lib（保守）：仅移除被替代的当前函数本身（其子函数仍参与后续评估/转译）
    - bin（激进）：移除被替代函数，并采用不动点算法递归删除所有“其父级均位于已删除集合中的后继函数”；这些被删除的后继不再评估
    - 仅对函数（category == "function"）生效，类型记录不受影响
    - 生成新的符号表与替代映射清单

    输入:
      - db_path: 指向 symbols.jsonl 的路径或其所在目录
      - out_symbols_path: 输出新符号表路径（默认: <data_dir>/symbols_third_party_pruned.jsonl）
      - out_mapping_path: 替代映射路径（默认: <data_dir>/third_party_replacements.jsonl，兼容命名，实际包含 std/crate 两类替代）
      - llm_group: 可选，传给 CodeAgent 的 model_group，用于平台/模型选择
      - max_funcs: 可选，最多评估的函数数量（调试/限流用）
      - mode: 剪枝模式，"lib"（保守）或 "bin"（激进，按唯一父级不动点删除）

    返回:
      Dict[str, Path]: {"symbols": 新符号表路径, "mapping": 替代映射路径}

    说明:
      - 评估基于 Agent（如不可用或调用失败，则保守返回不可替代）
      - Agent 输出需包含一个 <yaml>...</yaml> 标签块（块内为 YAML 对象，字段如下），并在其后紧接着输出一行完成标识 <!!!COMPLETE!!!>：
          replaceable: true|false
          library: "<crate 名称或 'std'>"
          function: "<Rust API 完整路径或名称>"
          confidence: <0.0-1.0浮点>
    """
    def _resolve_symbols_jsonl_path(hint: Path) -> Path:
        p = Path(hint)
        # 若直接传入文件路径且为 .jsonl，则直接使用
        if p.is_file() and p.suffix.lower() == ".jsonl":
            return p
        # 仅支持目录下的标准路径
        if p.is_dir():
            prefer = p / ".jarvis" / "c2rust" / "symbols.jsonl"
            return prefer
        # 默认：项目 <cwd>/.jarvis/c2rust/symbols.jsonl
        return Path(".") / ".jarvis" / "c2rust" / "symbols.jsonl"

    sjsonl = _resolve_symbols_jsonl_path(db_path)
    if not sjsonl.exists():
        raise FileNotFoundError(f"未找到 symbols.jsonl: {sjsonl}")

    data_dir = sjsonl.parent
    if out_symbols_path is None:
        out_symbols_path = data_dir / "symbols_third_party_pruned.jsonl"
    else:
        out_symbols_path = Path(out_symbols_path)
    if out_mapping_path is None:
        out_mapping_path = data_dir / "third_party_replacements.jsonl"
    else:
        out_mapping_path = Path(out_mapping_path)
    # 断点续跑：状态文件路径
    state_path = data_dir / "third_party_pruner_state.json"
    # 计算 crate 根目录路径（用于在 Agent 上下文中明确路径）
    def _compute_project_root_from_data_dir(d: Path) -> Path:
        try:
            # data_dir 期望形如 <project_root>/.jarvis/c2rust
            return d.parent.parent
        except Exception:
            return d.parent

    def _default_crate_dir(prj_root: Path) -> Path:
        try:
            from pathlib import Path as _Path
            cwd = _Path(".").resolve()
            if prj_root.resolve() == cwd:
                return cwd / f"{cwd.name}_rs"
            else:
                return prj_root
        except Exception:
            return prj_root

    project_root = _compute_project_root_from_data_dir(data_dir)
    crate_dir = _default_crate_dir(project_root)

    # 1) 读取所有符号
    all_records: List[Dict[str, Any]] = []
    by_id: Dict[int, Dict[str, Any]] = {}
    name_to_id: Dict[str, int] = {}
    func_ids: Set[int] = set()
    id_refs_names: Dict[int, List[str]] = {}

    with open(sjsonl, "r", encoding="utf-8") as f:
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
            fid = int(obj.get("id") or idx)
            obj["id"] = fid
            nm = obj.get("name") or ""
            qn = obj.get("qualified_name") or ""
            cat = obj.get("category") or ""  # "function" | "type"
            refs = obj.get("ref")
            if not isinstance(refs, list):
                refs = []
            refs = [r for r in refs if isinstance(r, str) and r]

            all_records.append(obj)
            by_id[fid] = obj
            id_refs_names[fid] = refs
            if nm:
                name_to_id.setdefault(nm, fid)
            if qn:
                name_to_id.setdefault(qn, fid)
            if cat == "function":
                func_ids.add(fid)

    # 2) 构造仅函数内部的 id 引用邻接
    adj_func: Dict[int, List[int]] = {}
    for fid in func_ids:
        internal: List[int] = []
        for target in id_refs_names.get(fid, []):
            tid = name_to_id.get(target)
            if tid is not None and tid in func_ids and tid != fid:
                internal.append(tid)
        # 去重保持顺序
        try:
            internal = list(dict.fromkeys(internal))
        except Exception:
            internal = sorted(list(set(internal)))
        adj_func[fid] = internal

    # 2.1) 构造入边（父引用）映射，仅限函数内部图
    parents_map: Dict[int, Set[int]] = {}
    for _u, _vs in adj_func.items():
        for _v in _vs:
            parents_map.setdefault(_v, set()).add(_u)

    def _collect_exclusive_descendants(start: int) -> Set[int]:
        """
        bin 模式：仅移除 start 以及那些“其所有父级都在已移除集合（含 start 与之前已剪枝集合）中的后继”。
        采用不动点法逐层扩展。
        """
        removed: Set[int] = set([start])
        # 基于当前已剪枝集合，允许与其组合判断“父集合是否完全位于已移除集合中”
        base_removed: Set[int] = set(pruned)  # type: ignore[name-defined]
        changed = True
        while changed:
            changed = False
            frontier = list(removed)  # 仅从当前已移除集合的边界向外检查
            for u in frontier:
                for v in adj_func.get(u, []):
                    if v in removed or v in base_removed:
                        continue
                    parents = parents_map.get(v, set())
                    # 允许父集合为空的情况不触发移除（但在此图中若 v 为 u 的子节点则 parents 至少包含 u）
                    if parents and parents.issubset(base_removed.union(removed)):
                        removed.add(v)
                        changed = True
        return removed

    # 3) 根（无入边）函数集合（从全量符号根中过滤出函数）
    try:
        roots_all = find_root_function_ids(sjsonl)
    except Exception:
        roots_all = []
    root_funcs = [rid for rid in roots_all if rid in func_ids]
    # 如果未识别到根，则退化为全部函数（避免卡死）
    if not root_funcs:
        root_funcs = sorted(list(func_ids))

    # Determine the total set of functions that could potentially be processed by traversing from roots
    q = list(root_funcs)
    potential_funcs_to_process = set(q)
    head = 0
    while head < len(q):
        fid = q[head]
        head += 1
        for child in adj_func.get(fid, []):
            if child not in potential_funcs_to_process:
                potential_funcs_to_process.add(child)
                q.append(child)
    total_potential_count = len(potential_funcs_to_process)

    # 4) Agent 评估（可替代 -> 当前函数及其子引用全部剔除；子引用无需再评估）
    try:
        from jarvis.jarvis_agent import Agent  # 使用通用 Agent 进行评估
        _agent_available = True
    except Exception:
        _agent_available = False
        Agent = None  # type: ignore

    def _new_agent() -> Optional[Any]:
        """
        每次调用都创建一个全新的 Agent 实例，避免跨函数评估时复用带来的上下文污染。
        """
        if not _agent_available:
            return None
        try:
            return Agent(
                system_prompt=(
                    "你是资深 C→Rust 迁移专家。任务：根据给定的 C/C++ 函数信息，判断其是否可由 Rust 标准库（std）或 Rust 生态中的成熟第三方 crate 的单个 API 直接替代（用于 C 转译为 Rust 的场景）。"
                    "请先输出一个 <yaml> 块，且块内是一个 YAML 对象，包含字段：replaceable, library, function, confidence；随后在单独一行输出 <!!!COMPLETE!!!>；不要输出其它说明文字。"
                ),
                name="C2Rust-ThirdParty-Evaluator",
                model_group=llm_group,
                need_summary=False,
                auto_complete=True,
                use_tools=["execute_script"],
                plan=False,
                non_interactive=True,
                use_methodology=False,
                use_analysis=False,
            )
        except Exception as e:
            typer.secho(
                f"[c2rust-scanner] 初始化 Agent 失败，将回退为保守策略（不替代）。原因: {e}",
                fg=typer.colors.YELLOW,
                err=True,
            )
            return None

    def _read_source_snippet(rec: Dict[str, Any], max_lines: int = 400) -> str:
        path = rec.get("file") or ""
        try:
            if not path:
                return ""
            p = Path(path)
            if not p.exists():
                return ""
            sl = int(rec.get("start_line") or 1)
            el = int(rec.get("end_line") or sl)
            if el < sl:
                el = sl
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            # 1-based to 0-based
            start_idx = max(sl - 1, 0)
            end_idx = min(el, len(lines))
            snippet_lines = lines[start_idx:end_idx]
            if len(snippet_lines) > max_lines:
                snippet_lines = snippet_lines[:max_lines]
            return "\n".join(snippet_lines)
        except Exception:
            return ""

    def _parse_agent_json(text: str) -> Optional[Dict[str, Any]]:
        # 尝试从返回文本中提取第一个 JSON 对象（回退用）
        import re as _re
        candidates = _re.findall(r"\{.*\}", text or "", flags=_re.S)
        for c in candidates:
            try:
                obj = json.loads(c)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
        return None

    def _parse_agent_yaml_summary(text: str) -> Optional[Dict[str, Any]]:
        """
        解析带有 <yaml>...</yaml> 标签的 YAML 对象为字典（可存在于 <SUMMARY> 内或直接在文本中）。
        仅当检测到 <yaml> 标签时进行解析；否则返回 None。
        """
        if not isinstance(text, str) or not text.strip():
            return None
        import re as _re
        m_sum = _re.search(r"<SUMMARY>([\s\S]*?)</SUMMARY>", text, flags=_re.IGNORECASE)
        block = (m_sum.group(1) if m_sum else text).strip()
        m_yaml = _re.search(r"<yaml>([\s\S]*?)</yaml>", block, flags=_re.IGNORECASE)
        raw = (m_yaml.group(1).strip() if m_yaml else "").strip()
        if not raw:
            return None
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(raw)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    # 断点续跑：状态读写
    def _load_checkpoint(state_p: Path, symbols_path: Path) -> Optional[Dict[str, Any]]:
        try:
            if not state_p.exists():
                return None
            meta = symbols_path.stat()
            with open(state_p, "r", encoding="utf-8") as sf:
                st = json.load(sf)
            if not isinstance(st, dict):
                return None
            # 符号表变化则放弃断点
            if st.get("symbols_mtime") != meta.st_mtime or st.get("symbols_size") != meta.st_size:
                return None
            return st
        except Exception:
            return None

    def _save_checkpoint(
        state_p: Path,
        symbols_path: Path,
        visited_ids: Set[int],
        pruned_ids: Set[int],
        replacements_list: List[Dict[str, Any]],
        eval_cnt: int,
    ) -> None:
        try:
            meta = symbols_path.stat()
            st = {
                "symbols_mtime": meta.st_mtime,
                "symbols_size": meta.st_size,
                "visited_ids": sorted(list(int(x) for x in visited_ids)),
                "pruned_ids": sorted(list(int(x) for x in pruned_ids)),
                "replacements": replacements_list,
                "eval_count": int(eval_cnt),
                "timestamp": time.time(),
            }
            tmp_p = state_p.with_suffix(".json.tmp")
            with open(tmp_p, "w", encoding="utf-8") as of:
                json.dump(st, of, ensure_ascii=False, indent=2)
            tmp_p.replace(state_p)
        except Exception:
            # 忽略断点写入失败，不影响主流程
            pass

    def _evaluate_fn_replaceable(fid: int) -> Dict[str, Any]:
        rec = by_id.get(fid, {})
        if not _agent_available:
            return {"replaceable": False}
        name = rec.get("qualified_name") or rec.get("name") or f"sym_{fid}"
        sig = rec.get("signature") or ""
        lang = rec.get("language") or ""
        src = _read_source_snippet(rec)

        prompt = (
            "请根据给定的函数信息，判断其是否可以被 Rust 标准库（std）或成熟的第三方 crate 中的单个函数调用直接替代。\n"
            "要求：\n"
            "1) 仅当标准库/第三方库函数在功能与语义上能够完全覆盖当前函数（等价或更强）时，返回 replaceable=true；否则为 false。\n"
            "2) 优先考虑 Rust 标准库（std），其次考虑来自 crates.io 的常见、稳定的 crate。library 字段请填 'std' 或 crate 名称；function 字段请填可调用的 Rust API 名称/路径。\n"
            "3) 若无法判断或需要组合多个库/多步调用才能实现，不视为可替代（replaceable=false）。\n"
            "4) 请先输出一个 <yaml> 块（内容为 YAML 对象：replaceable, library, function, confidence），随后在单独一行输出 <!!!COMPLETE!!!>，不要输出其它文字。\n\n"
            f"语言: {lang}\n"
            f"函数: {name}\n"
            f"签名: {sig}\n"
            f"crate 根目录路径（推断）: {crate_dir}\n"
            "源码片段如下（可能截断，仅用于辅助理解）:\n"
            "-----BEGIN_SNIPPET-----\n"
            f"{src}\n"
            "-----END_SNIPPET-----\n"
        )
        try:
            # 每次评估均创建全新 Agent，避免复用
            _agent = _new_agent()
            if not _agent:
                return {"replaceable": False}
            attempt = 0
            while True:
                attempt += 1
                result = _agent.run(prompt)
                parsed = _parse_agent_yaml_summary(result or "")
                if isinstance(parsed, dict):
                    # 归一化
                    rep = bool(parsed.get("replaceable") is True)
                    lib = str(parsed.get("library") or "").strip()
                    fun = str(parsed.get("function") or "").strip()
                    conf = parsed.get("confidence")
                    try:
                        conf = float(conf)
                    except Exception:
                        conf = 0.0
                    if rep and (not lib or not fun):
                        # 不完整信息视为不可替代
                        rep = False
                    return {"replaceable": rep, "library": lib, "function": fun, "confidence": conf}
                # 仅解析失败时重试（不设上限）
                if attempt % 5 == 0:
                    typer.secho(f"[c2rust-scanner] 标准库/第三方替代评估解析失败，正在重试 (attempt={attempt}) ...", fg=typer.colors.YELLOW, err=True)
        except Exception as e:
            typer.secho(f"[c2rust-scanner] Agent 评估失败，已回退为不可替代: {e}", fg=typer.colors.YELLOW, err=True)
            return {"replaceable": False}

    # 5) 遍历与裁剪
    visited: Set[int] = set()
    pruned: Set[int] = set()          # 被剔除的函数（替代根及其可达子节点）
    replacements: List[Dict[str, Any]] = []

    # 尝试加载断点（与当前 symbols.jsonl 匹配时生效）
    _checkpoint_state = _load_checkpoint(state_path, sjsonl)
    _ckpt_eval_count = None
    if _checkpoint_state:
        try:
            v_ids = _checkpoint_state.get("visited_ids", [])
            p_ids = _checkpoint_state.get("pruned_ids", [])
            if isinstance(v_ids, list):
                for x in v_ids:
                    try:
                        visited.add(int(x))
                    except Exception:
                        continue
            if isinstance(p_ids, list):
                for x in p_ids:
                    try:
                        pruned.add(int(x))
                    except Exception:
                        continue
        except Exception:
            pass
        reps = _checkpoint_state.get("replacements", [])
        if isinstance(reps, list):
            replacements = [r for r in reps if isinstance(r, dict)]
        _ckpt_eval_count = _checkpoint_state.get("eval_count")

    # 已有替代映射的去重索引
    repl_ids: Set[int] = set()
    for _m in replacements:
        try:
            repl_ids.add(int(_m.get("id")))
        except Exception:
            pass

    if _checkpoint_state:
        typer.secho(
            f"[c2rust-pruner] 已加载断点: visited={len(visited)}, pruned={len(pruned)}, replacements={len(replacements)}, eval_count={int(_ckpt_eval_count or 0)}",
            fg=typer.colors.YELLOW,
            err=True,
        )

    def _collect_descendants(start: int) -> Set[int]:
        """收集从 start 沿函数内部边可达的所有后继（含自身）。"""
        res: Set[int] = set()
        stack: List[int] = [start]
        res.add(start)
        while stack:
            s = stack.pop()
            for v in adj_func.get(s, []):
                if v not in res:
                    res.add(v)
                    stack.append(v)
        return res

    eval_count = int(_ckpt_eval_count or 0)

    def _process(fid: int):
        nonlocal eval_count
        if fid in visited or fid in pruned:
            return
        visited.add(fid)

        rec = by_id.get(fid, {})
        func_name = rec.get("qualified_name") or rec.get("name") or f"sym_{fid}"
        simple_name = rec.get("name") or ""
        if simple_name == "main":
            typer.secho(f"[c2rust-pruner] 跳过 'main' 函数的替代评估，视为不可替代 (ID: {fid})", fg=typer.colors.YELLOW, err=True)
            # 不可替代：保存进度并继续向子节点传播
            _save_checkpoint(state_path, sjsonl, visited, pruned, replacements, eval_count)
            for child in adj_func.get(fid, []):
                if child not in visited and child not in pruned:
                    _process(child)
            return

        remaining_to_eval = total_potential_count - len(visited)
        typer.secho(
            f"[c2rust-pruner] 正在评估函数: {func_name} (ID: {fid}) (剩余约 {remaining_to_eval} 个)",
            fg=typer.colors.CYAN,
            err=True,
        )

        if max_funcs is not None and eval_count >= max_funcs:
            return
        # 仅当未被上层裁剪时，进行评估
        res = _evaluate_fn_replaceable(fid)
        eval_count += 1
        if res.get("replaceable") is True:
            # 记录替代映射（去重）
            if fid not in repl_ids:
                replacements.append(
                    {
                        "id": fid,
                        "name": rec.get("name") or "",
                        "qualified_name": rec.get("qualified_name") or "",
                        "library": res.get("library") or "",
                        "function": res.get("function") or "",
                        "confidence": res.get("confidence") or 0.0,
                    }
                )
                repl_ids.add(fid)
            # 剪枝：依据模式删除当前函数及可能的后继；在 bin 模式中，被删除的后继不再评估
            # 剪枝策略：bin 模式激进（不动点扩展删除依赖于已移除集合的子符号）；lib 模式保守（仅删除当前函数本身）
            if (mode or "lib").lower() == "bin":
                desc = _collect_exclusive_descendants(fid)
            else:
                desc = set([fid])
            lib = res.get("library")
            fun = res.get("function")
            typer.secho(
                f"[c2rust-pruner] 函数 {func_name} 可由 '{lib}' 中的 '{fun}' 替代，将剔除 {len(desc)} 个符号。",
                fg=typer.colors.GREEN,
                err=True,
            )
            pruned.update(desc)
            # 保存断点
            _save_checkpoint(state_path, sjsonl, visited, pruned, replacements, eval_count)
            return
        # 不可替代：保存进度并继续向子节点传播
        _save_checkpoint(state_path, sjsonl, visited, pruned, replacements, eval_count)
        for child in adj_func.get(fid, []):
            if child not in visited and child not in pruned:
                _process(child)

    for rid in root_funcs:
        if rid in pruned:
            continue
        _process(rid)

    # 6) 生成新符号表（移除 pruned 中的函数；类型保留）
    kept_ids: Set[int] = set()
    for rec in all_records:
        fid = int(rec.get("id"))
        cat = rec.get("category") or ""
        if cat == "function":
            if fid not in pruned:
                kept_ids.add(fid)
        else:
            kept_ids.add(fid)

    # 写出新 symbols.jsonl
    with open(out_symbols_path, "w", encoding="utf-8") as fo:
        for rec in all_records:
            fid = int(rec.get("id"))
            if fid in kept_ids:
                fo.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 写出替代映射（JSONL）
    with open(out_mapping_path, "w", encoding="utf-8") as fm:
        for m in replacements:
            fm.write(json.dumps(m, ensure_ascii=False) + "\n")
    # 清理断点文件（已完成）
    try:
        if state_path.exists():
            state_path.unlink()
    except Exception:
        pass

    typer.secho(
        f"[c2rust-scanner] 第三方/标准库替代评估完成: 评估 {eval_count} 个函数，剔除 {len(pruned)} 个函数（含子引用）。\n"
        f"新符号表: {out_symbols_path}\n替代映射: {out_mapping_path}",
        fg=typer.colors.GREEN,
    )
    return {"symbols": Path(out_symbols_path), "mapping": Path(out_mapping_path)}


__all__ = ["evaluate_third_party_replacements"]