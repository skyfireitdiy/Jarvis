# -*- coding: utf-8 -*-
"""
Library-based dependency replacer for C→Rust migration (LLM-only subtree evaluation).

要点:
- 不依赖 pruner，仅复用 scanner 的通用工具函数
- 将“依赖子树（根函数及其可达的函数集合）”的摘要与局部源码片段提供给 LLM，由 LLM 评估该子树是否可由“指定标准库/第三方 crate 的一个或多个成熟 API（可组合，多库协同）”整体替代
- 若可替代：将根函数的 ref 替换为该库 API，并删除其所有子孙函数节点（类型不受影响）
- 生成剪枝后的符号表与替代映射，并计算新的转译顺序（兼容输出别名）

输入数据:
- symbols.jsonl（或传入的 .jsonl 路径）：由 scanner 生成的统一符号表，字段参见 scanner.py

输出:
- symbols_library_pruned.jsonl：剪枝后的符号表（默认名，可通过参数自定义）
- library_replacements.jsonl：替代根到库 API 的映射（JSONL，每行一个 {id,name,qualified_name,library,function,confidence,mode}）
- 兼容输出：
  - symbols_prune.jsonl：与主输出等价
  - symbols.jsonl：通用别名（用于后续流程统一读取）
  - translation_order_prune.jsonl：剪枝阶段的转译顺序
  - translation_order.jsonl：通用别名（与剪枝阶段一致）
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import typer

# 依赖：仅使用 scanner 的工具函数，避免循环导入
from jarvis.jarvis_c2rust.scanner import (
    compute_translation_order_jsonl,
    find_root_function_ids,
)


def apply_library_replacement(
    db_path: Path,
    library_name: str,
    llm_group: Optional[str] = None,
    candidates: Optional[List[str]] = None,
    out_symbols_path: Optional[Path] = None,
    out_mapping_path: Optional[Path] = None,
    max_funcs: Optional[int] = None,
    disabled_libraries: Optional[List[str]] = None,
    resume: bool = True,
    checkpoint_path: Optional[Path] = None,
    checkpoint_interval: int = 1,
    clear_checkpoint_on_done: bool = True,
) -> Dict[str, Path]:
    """
    基于依赖图由 LLM 判定，对满足“整子树可由指定库单个 API 替代”的函数根进行替换并剪枝。

    参数:
      - db_path: 指向 symbols.jsonl 的路径或其所在目录
      - library_name: 指定库名（如 'std'、'regex'），要求 LLM 仅在该库中选择 API
      - llm_group: 可选，评估时使用的模型组
      - candidates: 仅评估这些函数作为根（名称或限定名）；缺省评估所有根函数（无入边）
      - out_symbols_path/out_mapping_path: 输出文件路径（若省略使用默认）
      - max_funcs: LLM 评估的最大根数量（限流/调试）
      - disabled_libraries: 禁用的开源库名称列表（不允许在评估/建议中使用；在提示词中明确说明）
    返回:
      Dict[str, Path]: {"symbols": 新符号表路径, "mapping": 替代映射路径, "symbols_prune": 兼容符号表路径, "order": 通用顺序路径, "order_prune": 剪枝阶段顺序路径}
    """

    def _resolve_symbols_jsonl_path(hint: Path) -> Path:
        p = Path(hint)
        if p.is_file() and p.suffix.lower() == ".jsonl":
            return p
        if p.is_dir():
            return p / ".jarvis" / "c2rust" / "symbols.jsonl"
        return Path(".") / ".jarvis" / "c2rust" / "symbols.jsonl"

    sjsonl = _resolve_symbols_jsonl_path(db_path)
    if not sjsonl.exists():
        raise FileNotFoundError(f"未找到 symbols.jsonl: {sjsonl}")

    data_dir = sjsonl.parent
    if out_symbols_path is None:
        out_symbols_path = data_dir / "symbols_library_pruned.jsonl"
    else:
        out_symbols_path = Path(out_symbols_path)
    if out_mapping_path is None:
        out_mapping_path = data_dir / "library_replacements.jsonl"
    else:
        out_mapping_path = Path(out_mapping_path)

    # 兼容输出
    out_symbols_prune_path = data_dir / "symbols_prune.jsonl"
    alias_symbols_path = data_dir / "symbols.jsonl"  # 通用别名
    order_prune_path = data_dir / "translation_order_prune.jsonl"
    alias_order_path = data_dir / "translation_order.jsonl"

    # Checkpoint 默认路径
    if checkpoint_path is None:
        checkpoint_path = data_dir / "library_replacer_checkpoint.json"

    # 读取符号
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

    # 构造函数内边（id→id）
    adj_func: Dict[int, List[int]] = {}
    for fid in func_ids:
        internal: List[int] = []
        for target in id_refs_names.get(fid, []):
            tid = name_to_id.get(target)
            if tid is not None and tid in func_ids and tid != fid:
                internal.append(tid)
        try:
            internal = list(dict.fromkeys(internal))
        except Exception:
            internal = sorted(list(set(internal)))
        adj_func[fid] = internal

    # 评估队列：从所有无入边函数作为种子开始，按层次遍历整个图，使“父先于子”被评估；
    # 若不存在无入边节点（如强连通环），则回退为全量函数集合。
    try:
        roots_all = find_root_function_ids(sjsonl)
    except Exception:
        roots_all = []
    seeds = [rid for rid in roots_all if rid in func_ids]
    if not seeds:
        seeds = sorted(list(func_ids))

    visited: Set[int] = set()
    order: List[int] = []
    q: List[int] = list(seeds)
    qi = 0
    while qi < len(q):
        u = q[qi]
        qi += 1
        if u in visited or u not in func_ids:
            continue
        visited.add(u)
        order.append(u)
        for v in adj_func.get(u, []):
            if v not in visited and v in func_ids:
                q.append(v)
    # 若存在未覆盖的孤立/循环组件，补充其节点（确保每个函数节点都将被作为“候选根”参与评估）
    if len(visited) < len(func_ids):
        leftovers = [fid for fid in sorted(func_ids) if fid not in visited]
        order.extend(leftovers)

    # 评估顺序：包含根节点与所有子节点（广度优先近似的父先子后），被覆盖/剪枝的节点将自动跳过
    root_funcs = order

    # 可达缓存（需在 candidates 使用前定义，避免前向引用）
    desc_cache: Dict[int, Set[int]] = {}

    def _collect_descendants(start: int) -> Set[int]:
        if start in desc_cache:
            return desc_cache[start]
        visited: Set[int] = set()
        stack: List[int] = [start]
        visited.add(start)
        while stack:
            u = stack.pop()
            for v in adj_func.get(u, []):
                if v not in visited:
                    visited.add(v)
                    stack.append(v)
        desc_cache[start] = visited
        return visited

    # 如果传入 candidates，则仅评估这些节点（按上面的顺序过滤），并限定作用域：
    # - 仅保留从这些根可达的函数；对不可达函数直接删除（类型记录保留）
    scope_unreachable_funcs: Set[int] = set()
    if candidates:
        cand_ids: Set[int] = set()
        # 支持重载：同名/同限定名可能对应多个函数ID，需全部纳入候选
        key_set = set(candidates)
        for rec in all_records:
            if (rec.get("category") or "") != "function":
                continue
            nm = rec.get("name") or ""
            qn = rec.get("qualified_name") or ""
            if nm in key_set or qn in key_set:
                try:
                    cand_ids.add(int(rec.get("id")))
                except Exception:
                    continue
        if cand_ids:
            root_funcs = [rid for rid in root_funcs if rid in cand_ids]
            # 计算从候选根出发的可达函数集合（含根）
            reachable_all: Set[int] = set()
            for rid in root_funcs:
                reachable_all.update(_collect_descendants(rid))
            # 不可达函数（仅限函数类别）将被直接删除
            scope_unreachable_funcs = {fid for fid in func_ids if fid not in reachable_all}
            if scope_unreachable_funcs:
                typer.secho(
                    f"[c2rust-library] 根据根列表，标记不可达函数删除: {len(scope_unreachable_funcs)} 个",
                    fg=typer.colors.YELLOW,
                    err=True,
                )

    # 读取源码片段（辅助 LLM）
    def _read_source_snippet(rec: Dict[str, Any], max_lines: int = 200) -> str:
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
            start_idx = max(sl - 1, 0)
            end_idx = min(el, len(lines))
            snippet_lines = lines[start_idx:end_idx]
            if len(snippet_lines) > max_lines:
                snippet_lines = snippet_lines[:max_lines]
            return "\n".join(snippet_lines)
        except Exception:
            return ""

    # LLM 可用性
    try:
        from jarvis.jarvis_platform.registry import PlatformRegistry  # type: ignore
        from jarvis.jarvis_utils.config import get_normal_platform_name, get_normal_model_name  # type: ignore
        _model_available = True
    except Exception:
        PlatformRegistry = None  # type: ignore
        get_normal_platform_name = None  # type: ignore
        get_normal_model_name = None  # type: ignore
        _model_available = False

    # 预处理禁用库
    disabled_norm: List[str] = []
    disabled_display: str = ""
    if isinstance(disabled_libraries, list):
        disabled_norm = [str(x).strip().lower() for x in disabled_libraries if str(x).strip()]
        disabled_display = ", ".join([str(x).strip() for x in disabled_libraries if str(x).strip()])

    # 断点恢复支持：工具函数与关键键构造
    def _norm_list(items: Optional[List[str]]) -> List[str]:
        if not isinstance(items, list):
            return []
        vals: List[str] = []
        for x in items:
            try:
                s = str(x).strip()
            except Exception:
                continue
            if s:
                vals.append(s)
        try:
            vals = list(dict.fromkeys(vals))
        except Exception:
            vals = sorted(set(vals))
        return vals

    def _norm_list_lower(items: Optional[List[str]]) -> List[str]:
        return [s.lower() for s in _norm_list(items)]

    ckpt_path: Path = Path(checkpoint_path) if checkpoint_path is not None else (data_dir / "library_replacer_checkpoint.json")

    def _make_ckpt_key() -> Dict[str, Any]:
        try:
            abs_sym = str(Path(sjsonl).resolve())
        except Exception:
            abs_sym = str(sjsonl)
        key: Dict[str, Any] = {
            "symbols": abs_sym,
            "library_name": str(library_name),
            "llm_group": str(llm_group or ""),
            "candidates": _norm_list(candidates),
            "disabled_libraries": _norm_list_lower(disabled_libraries),
            "max_funcs": (int(max_funcs) if isinstance(max_funcs, int) or (isinstance(max_funcs, float) and float(max_funcs).is_integer()) else None),
        }
        return key

    def _load_checkpoint_if_match() -> Optional[Dict[str, Any]]:
        try:
            if not resume:
                return None
            if not ckpt_path.exists():
                return None
            obj = json.loads(ckpt_path.read_text(encoding="utf-8"))
            if not isinstance(obj, dict):
                return None
            if obj.get("key") != _make_ckpt_key():
                return None
            return obj
        except Exception:
            return None

    def _atomic_write(path: Path, content: str) -> None:
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(path)
        except Exception:
            try:
                path.write_text(content, encoding="utf-8")
            except Exception:
                pass

    def _new_model() -> Optional[Any]:
        if not _model_available:
            return None
        try:
            registry = PlatformRegistry.get_global_platform_registry()  # type: ignore
            model = None
            if llm_group:
                try:
                    platform_name = get_normal_platform_name(llm_group)  # type: ignore
                    if platform_name:
                        model = registry.create_platform(platform_name)  # type: ignore
                except Exception:
                    model = None
            if model is None:
                model = registry.get_normal_platform()  # type: ignore
            try:
                model.set_model_group(llm_group)  # type: ignore
            except Exception:
                pass
            if llm_group:
                try:
                    mn = get_normal_model_name(llm_group)  # type: ignore
                    if mn:
                        model.set_model_name(mn)  # type: ignore
                except Exception:
                    pass
            model.set_system_prompt(  # type: ignore
                "你是资深 C→Rust 迁移专家。任务：给定一个函数及其调用子树（依赖图摘要、函数签名、源码片段），"
                "判断是否可以使用一个或多个成熟的 Rust 库整体替代该子树的功能（允许库内多个 API 协同，允许多个库组合；不允许使用不成熟/不常见库）。"
                "如可替代，请给出 libraries 列表（库名），可选给出代表性 API/模块与实现备注 notes（如何用这些库协作实现）。"
                "输出格式：仅输出一个 <yaml> 块，字段: replaceable(bool), libraries(list[str]), confidence(float 0..1)，可选 library(str,首选主库), api(str) 或 apis(list)，notes(str)。"
            )
            return model
        except Exception as e:
            typer.secho(
                f"[c2rust-library] 初始化 LLM 平台失败，将回退为保守策略: {e}",
                fg=typer.colors.YELLOW,
                err=True,
            )
            return None

    # 解析 YAML/JSON 结果
    def _parse_agent_yaml_summary(text: str) -> Optional[Dict[str, Any]]:
        if not isinstance(text, str) or not text.strip():
            return None
        import re as _re
        import json as _json
        try:
            import yaml  # type: ignore
        except Exception:
            yaml = None  # type: ignore

        m_sum = _re.search(r"<SUMMARY>([\s\S]*?)</SUMMARY>", text, flags=_re.IGNORECASE)
        block = (m_sum.group(1) if m_sum else text).strip()

        m_yaml = _re.search(r"<yaml>([\s\S]*?)</yaml>", block, flags=_re.IGNORECASE)
        if m_yaml:
            raw = m_yaml.group(1).strip()
            if raw and yaml:
                try:
                    data = yaml.safe_load(raw)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass

        m_code = _re.search(r"```(?:yaml|yml)\s*([\s\S]*?)```", block, flags=_re.IGNORECASE)
        if m_code:
            raw = m_code.group(1).strip()
            if raw and yaml:
                try:
                    data = yaml.safe_load(raw)
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass

        m_json = _re.search(r"\{[\s\S]*\}", block)
        if m_json:
            raw = m_json.group(0).strip()
            try:
                data = _json.loads(raw)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        # 宽松键值
        def _kv(pattern: str) -> Optional[str]:
            m = _re.search(pattern, block, flags=_re.IGNORECASE)
            return m.group(1).strip() if m else None

        rep_raw = _kv(r"replaceable\s*:\s*(.+)")
        lib_raw = _kv(r"library\s*:\s*(.+)")
        api_raw = _kv(r"(?:api|function)\s*:\s*(.+)")
        conf_raw = _kv(r"confidence\s*:\s*([0-9\.\-eE]+)")
        if any([rep_raw, lib_raw, api_raw, conf_raw]):
            result: Dict[str, Any] = {}
            if rep_raw is not None:
                rep_s = rep_raw.strip().strip("\"'")
                result["replaceable"] = rep_s.lower() in ("true", "yes", "y", "1")
            if lib_raw is not None:
                result["library"] = lib_raw.strip().strip("\"'")
            if api_raw is not None:
                result["api"] = api_raw.strip().strip("\"'")
            if conf_raw is not None:
                try:
                    result["confidence"] = float(conf_raw)
                except Exception:
                    pass
            return result if result else None
        return None

    def _llm_evaluate_subtree(fid: int, desc: Set[int]) -> Dict[str, Any]:
        if not _model_available:
            return {"replaceable": False}
        model = _new_model()
        if not model:
            return {"replaceable": False}

        root_rec = by_id.get(fid, {})
        root_name = root_rec.get("qualified_name") or root_rec.get("name") or f"sym_{fid}"
        root_sig = root_rec.get("signature") or ""
        root_lang = root_rec.get("language") or ""
        root_src = _read_source_snippet(root_rec)

        # 子树摘要（限制长度，避免超长）
        nodes_meta: List[str] = []
        for nid in sorted(desc):
            r = by_id.get(nid, {})
            nm = r.get("qualified_name") or r.get("name") or f"sym_{nid}"
            sg = r.get("signature") or ""
            if sg and sg != nm:
                nodes_meta.append(f"- {nm} | {sg}")
            else:
                nodes_meta.append(f"- {nm}")
        if len(nodes_meta) > 200:
            nodes_meta = nodes_meta[:200] + [f"...({len(desc)-200} more)"]

        # 选取部分代表性叶子/内部节点源码（最多 3 个）
        samples: List[str] = []
        sample_ids: List[int] = [fid]
        for ch in adj_func.get(fid, [])[:2]:
            sample_ids.append(ch)
        for sid in sample_ids:
            rec = by_id.get(sid, {})
            nm = rec.get("qualified_name") or rec.get("name") or f"sym_{sid}"
            sg = rec.get("signature") or ""
            src = _read_source_snippet(rec, max_lines=120)
            samples.append(f"--- BEGIN {nm} ---\n{sg}\n{src}\n--- END {nm} ---")

        # 构建依赖图（子树内的调用有向边）
        def _label(nid: int) -> str:
            r = by_id.get(nid, {})
            return r.get("qualified_name") or r.get("name") or f"sym_{nid}"

        edges_list: List[str] = []
        for u in sorted(desc):
            for v in adj_func.get(u, []):
                if v in desc:
                    edges_list.append(f"{_label(u)} -> {_label(v)}")
        edges_text: str
        if len(edges_list) > 400:
            edges_text = "\n".join(edges_list[:400] + [f"...({len(edges_list) - 400} more edges)"])
        else:
            edges_text = "\n".join(edges_list)

        # 适度提供 DOT（边数不大时），便于大模型直观看图
        dot_text = ""
        if len(edges_list) <= 200:
            dot_lines: List[str] = ["digraph subtree {", "  rankdir=LR;"]
            for u in sorted(desc):
                for v in adj_func.get(u, []):
                    if v in desc:
                        dot_lines.append(f'  "{_label(u)}" -> "{_label(v)}";')
            dot_lines.append("}")
            dot_text = "\n".join(dot_lines)

        disabled_hint = (
            f"重要约束：禁止使用以下库（若这些库为唯一可行选项则判定为不可替代）：{disabled_display}\n"
            if disabled_display else ""
        )

        prompt = (
            "请评估以下 C/C++ 函数子树是否可以由一个或多个成熟的 Rust 库整体替代（语义等价或更强）。"
            "允许库内多个 API 协同，允许多个库组合；如果必须依赖尚不成熟/冷门库或非 Rust 库，则判定为不可替代。\n"
            f"{disabled_hint}"
            "输出格式：仅输出一个 <yaml> 块，字段: replaceable(bool), libraries(list[str]), confidence(float 0..1)，"
            "可选字段: library(str,首选主库), api(str) 或 apis(list), notes(str: 简述如何由这些库协作实现的思路)。\n\n"
            f"根函数(被评估子树的根): {root_name}\n"
            f"签名: {root_sig}\n"
            f"语言: {root_lang}\n"
            "根函数源码片段（可能截断）:\n"
            f"{root_src}\n\n"
            f"子树规模: {len(desc)} 个函数\n"
            "子树函数列表（名称|签名）:\n"
            + "\n".join(nodes_meta)
            + "\n\n"
            "依赖图（调用边，caller -> callee）:\n"
            f"{edges_text}\n\n"
            + (f"DOT 表示（边数较少时提供）:\n```dot\n{dot_text}\n```\n\n" if dot_text else "")
            + "代表性源码样本（部分节点，可能截断，仅供辅助判断）:\n"
            + "\n".join(samples)
            + "\n"
        )

        try:
            result = model.chat_until_success(prompt)  # type: ignore
            parsed = _parse_agent_yaml_summary(result or "")
            if isinstance(parsed, dict):
                rep = bool(parsed.get("replaceable") is True)
                lib = str(parsed.get("library") or "").strip()
                api = str(parsed.get("api") or parsed.get("function") or "").strip()
                apis = parsed.get("apis")
                libs_raw = parsed.get("libraries")
                notes = str(parsed.get("notes") or "").strip()
                # 归一化 libraries
                libraries: List[str] = []
                if isinstance(libs_raw, list):
                    libraries = [str(x).strip() for x in libs_raw if str(x).strip()]
                elif isinstance(libs_raw, str):
                    libraries = [s.strip() for s in libs_raw.split(",") if s.strip()]
                conf = parsed.get("confidence")
                try:
                    conf = float(conf)
                except Exception:
                    conf = 0.0
                # 不强制要求具体 API 或特定库名；若缺省且存在 library 字段，则纳入 libraries
                if not libraries and lib:
                    libraries = [lib]

                # 禁用库命中时，强制视为不可替代
                if disabled_norm:
                    libs_lower = [l.lower() for l in libraries]
                    lib_single_lower = lib.lower() if lib else ""
                    banned_hit = any(l in disabled_norm for l in libs_lower) or (lib_single_lower and lib_single_lower in disabled_norm)
                    if banned_hit:
                        rep = False
                        warn_libs = ", ".join(sorted(set([lib] + libraries))) if (libraries or lib) else "(未提供库名)"
                        typer.secho(
                            f"[c2rust-library] 评估结果包含禁用库，强制判定为不可替代: {root_name} | 命中库: {warn_libs}",
                            fg=typer.colors.YELLOW,
                            err=True,
                        )
                        if notes:
                            notes = notes + f" | 禁用库命中: {warn_libs}"
                        else:
                            notes = f"禁用库命中: {warn_libs}"

                result_obj: Dict[str, Any] = {
                    "replaceable": rep,
                    "library": lib,
                    "libraries": libraries,
                    "api": api,
                    "confidence": conf,
                }
                if isinstance(apis, list):
                    result_obj["apis"] = apis
                if notes:
                    result_obj["notes"] = notes
                return result_obj
            typer.secho("[c2rust-library] LLM 结果解析失败，视为不可替代。", fg=typer.colors.YELLOW, err=True)
            return {"replaceable": False}
        except Exception as e:
            typer.secho(f"[c2rust-library] LLM 评估失败，视为不可替代: {e}", fg=typer.colors.YELLOW, err=True)
            return {"replaceable": False}

    # 评估阶段：若某节点评估不可替代，则继续评估其子节点（递归/深度优先）
    eval_counter = 0
    total_roots = len(root_funcs)
    pruned_dynamic: Set[int] = set()  # 动态累计的“将被剪除”的函数集合（不含选中根）
    selected_roots: List[Tuple[int, Dict[str, Any]]] = []  # 实时选中的可替代根（fid, LLM结果）
    processed_roots: Set[int] = set()  # 已处理（评估或跳过）的根集合
    last_ckpt_saved = 0  # 上次保存的计数

    # 若存在匹配的断点文件，则加载恢复
    _loaded_ckpt = _load_checkpoint_if_match()
    if resume and _loaded_ckpt:
        try:
            eval_counter = int(_loaded_ckpt.get("eval_counter") or 0)
        except Exception:
            pass
        try:
            processed_roots = set(int(x) for x in (_loaded_ckpt.get("processed_roots") or []))
        except Exception:
            processed_roots = set()
        try:
            pruned_dynamic = set(int(x) for x in (_loaded_ckpt.get("pruned_dynamic") or []))
        except Exception:
            pruned_dynamic = set()
        try:
            sr_list = []
            for it in (_loaded_ckpt.get("selected_roots") or []):
                if isinstance(it, dict) and "fid" in it and "res" in it:
                    sr_list.append((int(it["fid"]), it["res"]))
            selected_roots = sr_list
        except Exception:
            selected_roots = []
        typer.secho(
            f"[c2rust-library] 已从断点恢复: 已评估={eval_counter}, 已处理根={len(processed_roots)}, 已剪除={len(pruned_dynamic)}, 已选中替代根={len(selected_roots)}",
            fg=typer.colors.YELLOW,
            err=True,
        )

    def _current_checkpoint_state() -> Dict[str, Any]:
        try:
            ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        except Exception:
            ts = ""
        return {
            "key": _make_ckpt_key(),
            "eval_counter": eval_counter,
            "processed_roots": sorted(list(processed_roots)),
            "pruned_dynamic": sorted(list(pruned_dynamic)),
            "selected_roots": [{"fid": fid, "res": res} for fid, res in selected_roots],
            "timestamp": ts,
        }

    def _periodic_checkpoint_save(force: bool = False) -> None:
        nonlocal last_ckpt_saved
        if not resume:
            return
        try:
            interval = int(checkpoint_interval)
        except Exception:
            interval = 1
        need_save = force or (interval <= 0) or ((eval_counter - last_ckpt_saved) >= interval)
        if not need_save:
            return
        try:
            _atomic_write(ckpt_path, json.dumps(_current_checkpoint_state(), ensure_ascii=False, indent=2))
            last_ckpt_saved = eval_counter
        except Exception:
            pass

    def _evaluate_node(fid: int) -> None:
        nonlocal eval_counter
        # 限流
        if max_funcs is not None and eval_counter >= max_funcs:
            return
        # 若该节点已被标记剪除或已处理，跳过
        if fid in pruned_dynamic or fid in processed_roots or fid not in func_ids:
            return

        # 构造子树并打印进度
        desc = _collect_descendants(fid)
        rec_meta = by_id.get(fid, {})
        label = rec_meta.get("qualified_name") or rec_meta.get("name") or f"sym_{fid}"
        typer.secho(
            f"[c2rust-library] 正在评估: {label} (ID: {fid}), 子树函数数={len(desc)}",
            fg=typer.colors.CYAN,
            err=True,
        )

        # 执行 LLM 评估
        res = _llm_evaluate_subtree(fid, desc)
        eval_counter += 1
        processed_roots.add(fid)
        res["mode"] = "llm"
        _periodic_checkpoint_save()

        # 若可替代，打印评估结果摘要（库/参考API/置信度/备注），并即时标记子孙剪除与后续跳过
        try:
            if res.get("replaceable") is True:
                libs = res.get("libraries") or ([res.get("library")] if res.get("library") else [])
                libs = [str(x) for x in libs if str(x)]
                api = str(res.get("api") or "")
                apis = res.get("apis")
                notes = str(res.get("notes") or "")
                conf = res.get("confidence")
                try:
                    conf = float(conf)
                except Exception:
                    conf = 0.0
                libs_str = ", ".join(libs) if libs else "(未指定库)"
                apis_str = ", ".join([str(a) for a in apis]) if isinstance(apis, list) else (api if api else "")
                msg = f"[c2rust-library] 可替换: {label} -> 库: {libs_str}"
                if apis_str:
                    msg += f"; 参考API: {apis_str}"
                msg += f"; 置信度: {conf:.2f}"
                if notes:
                    msg += f"; 备注: {notes[:200]}"
                typer.secho(msg, fg=typer.colors.GREEN, err=True)

                # 入口函数保护：不替代 main（保留进行转译），改为深入评估其子节点
                nm = str(rec_meta.get("name") or "")
                qn = str(rec_meta.get("qualified_name") or "")
                # Configurable entry detection (avoid hard-coding 'main'):
                # Honor env vars: JARVIS_C2RUST_DELAY_ENTRY_SYMBOLS / JARVIS_C2RUST_DELAY_ENTRIES / C2RUST_DELAY_ENTRIES
                import os
                entries_env = os.environ.get("JARVIS_C2RUST_DELAY_ENTRY_SYMBOLS") or \
                              os.environ.get("JARVIS_C2RUST_DELAY_ENTRIES") or \
                              os.environ.get("C2RUST_DELAY_ENTRIES") or ""
                entries_set = set()
                if entries_env:
                    try:
                        import re as _re
                        parts = _re.split(r"[,\s;]+", entries_env.strip())
                    except Exception:
                        parts = [p.strip() for p in entries_env.replace(";", ",").split(",")]
                    entries_set = {p.strip().lower() for p in parts if p and p.strip()}
                if entries_set:
                    is_entry = (nm.lower() in entries_set) or (qn.lower() in entries_set) or any(qn.lower().endswith(f"::{e}") for e in entries_set)
                else:
                    is_entry = (nm.lower() == "main") or (qn.lower() == "main") or qn.lower().endswith("::main")
                if is_entry:
                    typer.secho(
                        "[c2rust-library] 入口函数保护：跳过对 main 的库替代，继续评估其子节点。",
                        fg=typer.colors.YELLOW,
                        err=True,
                    )
                    for ch in adj_func.get(fid, []):
                        _evaluate_node(ch)
                else:
                    # 即时剪枝（不含根）
                    to_prune = set(desc)
                    to_prune.discard(fid)

                    newly = len(to_prune - pruned_dynamic)
                    pruned_dynamic.update(to_prune)
                    selected_roots.append((fid, res))
                    _periodic_checkpoint_save()
                    typer.secho(
                        f"[c2rust-library] 即时标记剪除子节点(本次新增): +{newly} 个 (累计={len(pruned_dynamic)})",
                        fg=typer.colors.MAGENTA,
                        err=True,
                    )
            else:
                # 若不可替代，继续评估其子节点（深度优先）
                for ch in adj_func.get(fid, []):
                    _evaluate_node(ch)
        except Exception:
            pass

    # 对每个候选根进行评估；若根不可替代将递归评估其子节点
    for fid in root_funcs:
        _evaluate_node(fid)

    # 剪枝集合来自动态评估阶段的累计结果
    pruned_funcs: Set[int] = set(pruned_dynamic)
    # 若限定候选根（candidates）已指定，则将不可达函数一并删除
    try:
        pruned_funcs.update(scope_unreachable_funcs)
    except Exception:
        pass

    # 写出新符号表
    now_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    kept_ids: Set[int] = set()
    for rec in all_records:
        fid = int(rec.get("id"))
        cat = rec.get("category") or ""
        if cat == "function":
            if fid in pruned_funcs:
                continue
            kept_ids.add(fid)
        else:
            kept_ids.add(fid)

    sel_root_ids = set(fid for fid, _ in selected_roots)
    replacements: List[Dict[str, Any]] = []

    with open(out_symbols_path, "w", encoding="utf-8") as fo, \
         open(out_symbols_prune_path, "w", encoding="utf-8") as fo2:

        for rec in all_records:
            fid = int(rec.get("id"))
            if fid not in kept_ids:
                continue

            rec_out = dict(rec)
            if (rec.get("category") or "") == "function" and fid in sel_root_ids:
                # 以库级替代为语义：不要求具体 API；将根 ref 设置为库占位符（支持多库组合）
                conf = 0.0
                api = ""
                apis = None
                libraries_out: List[str] = []
                notes_out: str = ""
                lib_single: str = ""
                for rf, rres in selected_roots:
                    if rf == fid:
                        api = str(rres.get("api") or rres.get("function") or "")
                        apis = rres.get("apis")
                        libs_val = rres.get("libraries")
                        if isinstance(libs_val, list):
                            libraries_out = [str(x) for x in libs_val if str(x)]
                        lib_single = str(rres.get("library") or "").strip()
                        try:
                            conf = float(rres.get("confidence") or 0.0)
                        except Exception:
                            conf = 0.0
                        notes_val = rres.get("notes")
                        if isinstance(notes_val, str):
                            notes_out = notes_val
                        break
                # 若 libraries 存在则使用多库占位；否则若存在单个 library 字段则使用之；否则置空
                if libraries_out:
                    lib_markers = [f"lib::{lb}" for lb in libraries_out]
                elif lib_single:
                    lib_markers = [f"lib::{lib_single}"]
                else:
                    lib_markers = []
                rec_out["ref"] = lib_markers
                try:
                    rec_out["updated_at"] = now_ts
                except Exception:
                    pass
                # 保存库替代元数据到符号表，供后续转译阶段作为上下文使用
                try:
                    meta_apis = apis if isinstance(apis, list) else ([api] if api else [])
                    lib_primary = libraries_out[0] if libraries_out else lib_single
                    rec_out["lib_replacement"] = {
                        "libraries": libraries_out,
                        "library": lib_primary or "",
                        "apis": meta_apis,
                        "api": api,
                        "confidence": float(conf) if isinstance(conf, (int, float)) else 0.0,
                        "notes": notes_out,
                        "mode": "llm",
                        "updated_at": now_ts,
                    }
                except Exception:
                    # 忽略写入元数据失败，不阻塞主流程
                    pass
                rep_obj: Dict[str, Any] = {
                    "id": fid,
                    "name": rec.get("name") or "",
                    "qualified_name": rec.get("qualified_name") or "",
                    "library": (libraries_out[0] if libraries_out else lib_single),
                    "libraries": libraries_out,
                    "function": api,
                    "confidence": conf,
                    "mode": "llm",
                }
                if isinstance(apis, list):
                    rep_obj["apis"] = apis
                if notes_out:
                    rep_obj["notes"] = notes_out
                replacements.append(rep_obj)

            line = json.dumps(rec_out, ensure_ascii=False) + "\n"
            fo.write(line)
            fo2.write(line)
            # 不覆写 symbols.jsonl（保留原始扫描/整理结果作为基线）

    # 写出替代映射
    with open(out_mapping_path, "w", encoding="utf-8") as fm:
        for m in replacements:
            fm.write(json.dumps(m, ensure_ascii=False) + "\n")

    # 生成转译顺序（剪枝阶段与别名）
    order_path = None
    try:
        compute_translation_order_jsonl(Path(out_symbols_path), out_path=order_prune_path)
        shutil.copy2(order_prune_path, alias_order_path)
        order_path = alias_order_path
    except Exception as e:
        typer.secho(f"[c2rust-library] 基于剪枝符号表生成翻译顺序失败: {e}", fg=typer.colors.YELLOW, err=True)

    # 完成后清理断点（可选）
    try:
        if resume and clear_checkpoint_on_done and ckpt_path.exists():
            ckpt_path.unlink()
            typer.secho(f"[c2rust-library] 已清理断点文件: {ckpt_path}", fg=typer.colors.BLUE, err=True)
    except Exception:
        pass

    typer.secho(
        "[c2rust-library] 库替代剪枝完成（LLM 子树评估）:\n"
        f"- 选中替代根: {len(selected_roots)} 个\n"
        f"- 剪除函数: {len(pruned_funcs)} 个\n"
        f"- 新符号表: {out_symbols_path}\n"
        f"- 替代映射: {out_mapping_path}\n"
        f"- 兼容符号表输出: {out_symbols_prune_path}\n"
        + (f"- 转译顺序: {order_path}\n" if order_path else "")
        + f"- 兼容顺序输出: {order_prune_path}",
        fg=typer.colors.GREEN,
    )

    result: Dict[str, Path] = {
        "symbols": Path(out_symbols_path),
        "mapping": Path(out_mapping_path),
        "symbols_prune": Path(out_symbols_prune_path),
    }
    if order_path:
        result["order"] = Path(order_path)
    if order_prune_path:
        result["order_prune"] = Path(order_prune_path)
    return result



__all__ = ["apply_library_replacement"]