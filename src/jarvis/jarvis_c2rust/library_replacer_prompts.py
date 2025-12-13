# -*- coding: utf-8 -*-
"""库替换器的提示词构建模块。"""

from typing import Any
from typing import Dict
from typing import List
from typing import Set

from jarvis.jarvis_c2rust.constants import MAX_CHILD_SAMPLES
from jarvis.jarvis_c2rust.constants import MAX_DOT_EDGES
from jarvis.jarvis_c2rust.constants import MAX_SUBTREE_EDGES
from jarvis.jarvis_c2rust.constants import MAX_SUBTREE_NODES_META
from jarvis.jarvis_c2rust.constants import SUBTREE_SOURCE_SNIPPET_MAX_LINES
from jarvis.jarvis_c2rust.library_replacer_utils import read_source_snippet


def build_subtree_prompt(
    fid: int,
    desc: Set[int],
    by_id: Dict[int, Dict[str, Any]],
    adj_func: Dict[int, List[int]],
    disabled_display: str,
    additional_notes: str = "",
) -> str:
    """构建子树评估提示词"""
    root_rec = by_id.get(fid, {})
    root_name = root_rec.get("qualified_name") or root_rec.get("name") or f"sym_{fid}"
    root_sig = root_rec.get("signature") or ""
    root_lang = root_rec.get("language") or ""
    root_src = read_source_snippet(root_rec)

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
    if len(nodes_meta) > MAX_SUBTREE_NODES_META:
        nodes_meta = nodes_meta[:MAX_SUBTREE_NODES_META] + [
            f"...({len(desc) - MAX_SUBTREE_NODES_META} more)"
        ]

    # 选取部分代表性叶子/内部节点源码（最多 MAX_SOURCE_SAMPLES 个）
    samples: List[str] = []
    sample_ids: List[int] = [fid]
    for ch in adj_func.get(fid, [])[:MAX_CHILD_SAMPLES]:
        sample_ids.append(ch)
    for sid in sample_ids:
        rec = by_id.get(sid, {})
        nm = rec.get("qualified_name") or rec.get("name") or f"sym_{sid}"
        sg = rec.get("signature") or ""
        src = read_source_snippet(rec, max_lines=SUBTREE_SOURCE_SNIPPET_MAX_LINES)
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
    if len(edges_list) > MAX_SUBTREE_EDGES:
        edges_text = "\n".join(
            edges_list[:MAX_SUBTREE_EDGES]
            + [f"...({len(edges_list) - MAX_SUBTREE_EDGES} more edges)"]
        )
    else:
        edges_text = "\n".join(edges_list)

    # 适度提供 DOT（边数不大时），便于大模型直观看图
    dot_text = ""
    if len(edges_list) <= MAX_DOT_EDGES:
        dot_lines: List[str] = ["digraph subtree {", "  rankdir=LR;"]
        for u in sorted(desc):
            for v in adj_func.get(u, []):
                if v in desc:
                    dot_lines.append(f'  "{_label(u)}" -> "{_label(v)}";')
        dot_lines.append("}")
        dot_text = "\n".join(dot_lines)

    disabled_hint = (
        f"重要约束：禁止使用以下库（若这些库为唯一可行选项则判定为不可替代）：{disabled_display}\n"
        if disabled_display
        else ""
    )

    return (
        "请评估以下 C/C++ 函数子树是否可以由一个或多个成熟的 Rust 库整体替代（语义等价或更强）。"
        "允许库内多个 API 协同，允许多个库组合；如果必须依赖尚不成熟/冷门库或非 Rust 库，则判定为不可替代。"
        "如果当前调用的函数无法使用 crate 直接提供的功能而需要封装或者改造，则认为不可替代。\n"
        f"{disabled_hint}"
        "输出格式：仅输出一个 <SUMMARY> 块，块内直接包含 JSON 对象（不需要额外的标签），字段: replaceable(bool), libraries(list[str]), confidence(float 0..1)，"
        "可选字段: library(str,首选主库), api(str) 或 apis(list), notes(str: 简述如何由这些库协作实现的思路)。\n\n"
        f"根函数(被评估子树的根): {root_name}\n"
        f"签名: {root_sig}\n"
        f"语言: {root_lang}\n"
        "根函数源码片段（可能截断）:\n"
        f"{root_src}\n\n"
        f"子树规模: {len(desc)} 个函数\n"
        "子树函数列表（名称|签名）:\n" + "\n".join(nodes_meta) + "\n\n"
        "依赖图（调用边，caller -> callee）:\n"
        f"{edges_text}\n\n"
        + (
            f"DOT 表示（边数较少时提供）:\n```dot\n{dot_text}\n```\n\n"
            if dot_text
            else ""
        )
        + "代表性源码样本（部分节点，可能截断，仅供辅助判断）:\n"
        + "\n".join(samples)
        + "\n"
        + (
            f"\n【附加说明（用户自定义）】\n{additional_notes}\n"
            if additional_notes
            else ""
        )
    )
