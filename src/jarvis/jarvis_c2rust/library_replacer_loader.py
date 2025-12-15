# -*- coding: utf-8 -*-
"""库替换器的符号表加载和图构建模块。"""

import json
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Set

from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_c2rust.scanner import find_root_function_ids


def load_symbols(
    sjsonl: Path,
) -> tuple[
    List[Dict[str, Any]],
    Dict[int, Dict[str, Any]],
    Dict[str, int],
    Set[int],
    Dict[int, List[str]],
]:
    """加载符号表，返回(所有记录, id到记录映射, 名称到id映射, 函数id集合, id到引用名称映射)"""
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

    return all_records, by_id, name_to_id, func_ids, id_refs_names


def build_function_graph(
    func_ids: Set[int],
    id_refs_names: Dict[int, List[str]],
    name_to_id: Dict[str, int],
) -> Dict[int, List[int]]:
    """构建函数依赖图，返回id到依赖id列表的映射"""
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
    return adj_func


def build_evaluation_order(
    sjsonl: Path,
    func_ids: Set[int],
    adj_func: Dict[int, List[int]],
) -> List[int]:
    """构建评估顺序（广度优先，父先子后）"""
    # 评估队列：从所有无入边函数作为种子开始，按层次遍历整个图，使"父先于子"被评估；
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
    # 若存在未覆盖的孤立/循环组件，补充其节点（确保每个函数节点都将被作为"候选根"参与评估）
    if len(visited) < len(func_ids):
        leftovers = [fid for fid in sorted(func_ids) if fid not in visited]
        order.extend(leftovers)

    return order


def collect_descendants(
    start: int,
    adj_func: Dict[int, List[int]],
    desc_cache: Dict[int, Set[int]],
) -> Set[int]:
    """收集从start开始的所有后代节点（使用缓存）"""
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


def process_candidate_scope(
    candidates: Optional[List[str]],
    all_records: List[Dict[str, Any]],
    root_funcs: List[int],
    func_ids: Set[int],
    adj_func: Dict[int, List[int]],
    desc_cache: Dict[int, Set[int]],
) -> tuple[List[int], Set[int]]:
    """处理候选根和作用域，返回(过滤后的根函数列表, 不可达函数集合)"""

    scope_unreachable_funcs: Set[int] = set()
    if not candidates:
        return root_funcs, scope_unreachable_funcs

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
                rec_id = rec.get("id")
                if rec_id is not None:
                    cand_ids.add(int(rec_id))
            except Exception:
                continue

    if not cand_ids:
        return root_funcs, scope_unreachable_funcs

    filtered_roots = [rid for rid in root_funcs if rid in cand_ids]
    # 计算从候选根出发的可达函数集合（含根）
    reachable_all: Set[int] = set()
    for rid in filtered_roots:
        reachable_all.update(collect_descendants(rid, adj_func, desc_cache))
    # 不可达函数（仅限函数类别）将被直接删除
    scope_unreachable_funcs = {fid for fid in func_ids if fid not in reachable_all}
    if scope_unreachable_funcs:
        PrettyOutput.auto_print(
            f"⚠️ [c2rust-library] 根据根列表，标记不可达函数删除: {len(scope_unreachable_funcs)} 个"
        )

    return filtered_roots, scope_unreachable_funcs
