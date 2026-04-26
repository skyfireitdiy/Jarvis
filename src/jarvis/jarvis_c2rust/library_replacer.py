# -*- coding: utf-8 -*-
"""
Library-based dependency replacer for C→Rust migration (LLM-only subtree evaluation).

要点:
- 不依赖 pruner，仅复用 scanner 的通用工具函数
- 将"依赖子树（根函数及其可达的函数集合）"的摘要与局部源码片段提供给 LLM，由 LLM 评估该子树是否可由"指定标准库/第三方 crate 的一个或多个成熟 API（可组合，多库协同）"整体替代
- 若可替代：将根函数的 ref 替换为该库 API（以 lib::<name> 形式的占位符，支持多库组合），并删除其所有子孙函数节点（类型不受影响）
- 支持禁用库约束：可传入 disabled_libraries（list[str]），若 LLM 建议命中禁用库，则强制判定为不可替代并记录备注
- 断点恢复（checkpoint/resume）：可启用 resume，使用 library_replacer_checkpoint.json 记录 eval_counter/processed/pruned/selected 等信息，基于关键输入组合键进行匹配恢复；落盘采用原子写以防损坏
- 主库字段回退策略：当存在 libraries 列表优先选择第一个作为 primary；否则回退到单一 library 字段；均为空则置空
- 入口保护：默认跳过 main（可通过环境变量 c2rust_delay_entry_symbols/c2rust_delay_entries/C2RUST_DELAY_ENTRIES 配置多个入口名）

输入数据:
- symbols.jsonl（或传入的 .jsonl 路径）：由 scanner 生成的统一符号表，字段参见 scanner.py
- 可选 candidates（名称或限定名列表）：仅评估这些符号作为根，作用域限定为其可达子树
- 可选 disabled_libraries（list[str]）：评估时禁止使用的库名（命中则视为不可替代）

输出:
- symbols_library_pruned.jsonl：剪枝后的符号表（默认名，可通过参数自定义）
- library_replacements.jsonl：替代根到库信息的映射（JSONL，每行一个 {id,name,qualified_name,library,libraries,function,apis?,confidence,notes?,mode}）
- 兼容输出：
  - symbols_prune.jsonl：与主输出等价
  - symbols.jsonl：通用别名（用于后续流程统一读取）
  - translation_order_prune.jsonl：剪枝阶段的转译顺序
  - translation_order.jsonl：通用别名（与剪枝阶段一致）
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple

from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_c2rust.constants import DEFAULT_CHECKPOINT_FILE
from jarvis.jarvis_c2rust.constants import DEFAULT_CHECKPOINT_INTERVAL
from jarvis.jarvis_c2rust.constants import MAX_NOTES_DISPLAY_LENGTH
from jarvis.jarvis_c2rust.library_replacer_checkpoint import create_checkpoint_state
from jarvis.jarvis_c2rust.library_replacer_checkpoint import load_checkpoint_if_match
from jarvis.jarvis_c2rust.library_replacer_checkpoint import make_checkpoint_key
from jarvis.jarvis_c2rust.library_replacer_checkpoint import periodic_checkpoint_save
from jarvis.jarvis_c2rust.library_replacer_llm import check_llm_availability
from jarvis.jarvis_c2rust.library_replacer_llm import create_llm_model
from jarvis.jarvis_c2rust.library_replacer_llm import llm_evaluate_subtree
from jarvis.jarvis_c2rust.library_replacer_loader import build_evaluation_order
from jarvis.jarvis_c2rust.library_replacer_loader import build_function_graph
from jarvis.jarvis_c2rust.library_replacer_loader import collect_descendants
from jarvis.jarvis_c2rust.library_replacer_loader import load_symbols
from jarvis.jarvis_c2rust.library_replacer_loader import process_candidate_scope
from jarvis.jarvis_c2rust.library_replacer_output import write_output_symbols
from jarvis.jarvis_c2rust.library_replacer_utils import is_entry_function
from jarvis.jarvis_c2rust.library_replacer_utils import load_additional_notes
from jarvis.jarvis_c2rust.library_replacer_utils import normalize_disabled_libraries
from jarvis.jarvis_c2rust.library_replacer_utils import resolve_symbols_jsonl_path
from jarvis.jarvis_c2rust.library_replacer_utils import setup_output_paths
from jarvis.jarvis_c2rust.scanner import compute_translation_order_jsonl


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
    checkpoint_interval: int = DEFAULT_CHECKPOINT_INTERVAL,
    clear_checkpoint_on_done: bool = True,
    non_interactive: bool = True,
) -> Dict[str, Path]:
    """
    基于依赖图由 LLM 判定，对满足"整子树可由指定库单个 API 替代"的函数根进行替换并剪枝。

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
    sjsonl = resolve_symbols_jsonl_path(db_path)
    if not sjsonl.exists():
        raise FileNotFoundError(f"未找到 symbols.jsonl: {sjsonl}")

    data_dir = sjsonl.parent
    (
        out_symbols_path,
        out_mapping_path,
        out_symbols_prune_path,
        order_prune_path,
        alias_order_path,
    ) = setup_output_paths(data_dir, out_symbols_path, out_mapping_path)

    # Checkpoint 默认路径
    if checkpoint_path is None:
        checkpoint_path = data_dir / DEFAULT_CHECKPOINT_FILE

    # 读取符号
    all_records, by_id, name_to_id, func_ids, id_refs_names = load_symbols(sjsonl)

    # 构造函数内边（id→id）
    adj_func = build_function_graph(func_ids, id_refs_names, name_to_id)

    # 构建评估顺序
    root_funcs = build_evaluation_order(sjsonl, func_ids, adj_func)

    # 可达缓存（需在 candidates 使用前定义，避免前向引用）
    desc_cache: Dict[int, Set[int]] = {}

    # 如果传入 candidates，则仅评估这些节点（按上面的顺序过滤），并限定作用域：
    # - 仅保留从这些根可达的函数；对不可达函数直接删除（类型记录保留）
    root_funcs, scope_unreachable_funcs = process_candidate_scope(
        candidates, all_records, root_funcs, func_ids, adj_func, desc_cache
    )

    # LLM 可用性
    (
        model_available,
        PlatformRegistry,
        get_smart_platform_name,
        get_smart_model_name,
        get_llm_config,
    ) = check_llm_availability()

    # 预处理禁用库
    disabled_norm, disabled_display = normalize_disabled_libraries(disabled_libraries)

    # 读取附加说明
    additional_notes = load_additional_notes(data_dir)

    # 断点恢复支持：工具函数与关键键构造
    ckpt_path: Path = (
        Path(checkpoint_path)
        if checkpoint_path is not None
        else (data_dir / DEFAULT_CHECKPOINT_FILE)
    )
    checkpoint_key = make_checkpoint_key(
        sjsonl, library_name, llm_group, candidates, disabled_libraries, max_funcs
    )

    def new_model() -> Optional[Any]:
        return create_llm_model(
            llm_group,
            disabled_display,
            model_available,
            PlatformRegistry,
            get_smart_platform_name,
            get_smart_model_name,
            get_llm_config,
        )

    # 评估阶段：若某节点评估不可替代，则继续评估其子节点（递归/深度优先）
    eval_counter = 0
    pruned_dynamic: Set[int] = set()  # 动态累计的"将被剪除"的函数集合（不含选中根）
    selected_roots: List[
        Tuple[int, Dict[str, Any]]
    ] = []  # 实时选中的可替代根（fid, LLM结果）
    processed_roots: Set[int] = set()  # 已处理（评估或跳过）的根集合
    root_funcs_processed: Set[int] = set()  # 已处理的初始根函数集合（用于进度显示）
    last_ckpt_saved = 0  # 上次保存的计数

    # 若存在匹配的断点文件，则加载恢复
    loaded_ckpt = load_checkpoint_if_match(ckpt_path, resume, checkpoint_key)
    if resume and loaded_ckpt:
        try:
            eval_counter = int(loaded_ckpt.get("eval_counter") or 0)
        except Exception:
            pass
        try:
            processed_roots = set(
                int(x) for x in (loaded_ckpt.get("processed_roots") or [])
            )
        except Exception:
            processed_roots = set()
        try:
            pruned_dynamic = set(
                int(x) for x in (loaded_ckpt.get("pruned_dynamic") or [])
            )
        except Exception:
            pruned_dynamic = set()
        try:
            sr_list = []
            for it in loaded_ckpt.get("selected_roots") or []:
                if isinstance(it, dict) and "fid" in it and "res" in it:
                    try:
                        fid_val = int(it["fid"])
                        res_val = it["res"]
                        if isinstance(res_val, dict):
                            sr_list.append((fid_val, res_val))
                    except (ValueError, TypeError, KeyError):
                        continue
            selected_roots = sr_list
            if selected_roots:
                PrettyOutput.auto_print(
                    f"[c2rust-library] 从断点恢复 selected_roots: {len(selected_roots)} 个替代根"
                )
            else:
                PrettyOutput.auto_print(
                    "[c2rust-library] 警告: 从断点恢复时 selected_roots 为空，可能导致 library_replacements.jsonl 为空"
                )
        except Exception as e:
            selected_roots = []
            PrettyOutput.auto_print(
                f"[c2rust-library] 从断点恢复 selected_roots 时出错: {e}，将使用空列表"
            )
        # 恢复已处理的初始根函数集合（从 processed_roots 中筛选出在 root_funcs 中的）
        try:
            root_funcs_processed = {fid for fid in processed_roots if fid in root_funcs}
        except Exception:
            root_funcs_processed = set()
        PrettyOutput.auto_print(
            f"[c2rust-library] 已从断点恢复: 已评估={eval_counter}, 已处理根={len(processed_roots)}, 已剪除={len(pruned_dynamic)}, 已选中替代根={len(selected_roots)}"
        )

    def evaluate_node(fid: int, is_root_func: bool = False) -> None:
        nonlocal eval_counter, last_ckpt_saved
        # 限流
        if max_funcs is not None and eval_counter >= max_funcs:
            return
        # 若该节点已被标记剪除或已处理，跳过
        if fid in pruned_dynamic or fid in processed_roots or fid not in func_ids:
            return

        # 构造子树并打印进度
        desc = collect_descendants(fid, adj_func, desc_cache)
        rec_meta = by_id.get(fid, {})
        label = rec_meta.get("qualified_name") or rec_meta.get("name") or f"sym_{fid}"
        # 计算进度：区分初始根函数和递归评估的子节点
        total_roots = len(root_funcs)
        total_evaluated = len(processed_roots) + 1  # +1 因为当前这个即将被处理
        if is_root_func:
            # 初始根函数：显示 (当前根函数索引/总根函数数)
            root_progress = len(root_funcs_processed) + 1
            progress_info = (
                f"({root_progress}/{total_roots})" if total_roots > 0 else ""
            )
        else:
            # 递归评估的子节点：显示 (当前根函数索引/总根函数数, 总评估节点数)
            root_progress = len(root_funcs_processed)
            if total_roots > 0:
                progress_info = (
                    f"({root_progress}/{total_roots}, 总评估={total_evaluated})"
                )
            else:
                progress_info = f"(总评估={total_evaluated})"
        PrettyOutput.auto_print(
            f"[c2rust-library] {progress_info} 正在评估: {label} (ID: {fid}), 子树函数数={len(desc)}"
        )

        # 执行 LLM 评估
        res = llm_evaluate_subtree(
            fid,
            desc,
            by_id,
            adj_func,
            disabled_norm,
            disabled_display,
            model_available,
            new_model,
            additional_notes,
        )
        eval_counter += 1
        processed_roots.add(fid)
        if is_root_func:
            root_funcs_processed.add(fid)
        res["mode"] = "llm"

        # 更新检查点
        checkpoint_state = create_checkpoint_state(
            checkpoint_key,
            eval_counter,
            processed_roots,
            pruned_dynamic,
            selected_roots,
        )
        last_ckpt_saved = periodic_checkpoint_save(
            ckpt_path,
            checkpoint_state,
            eval_counter,
            last_ckpt_saved,
            checkpoint_interval,
            resume,
        )

        # 若可替代，打印评估结果摘要（库/参考API/置信度/备注），并即时标记子孙剪除与后续跳过
        try:
            if res.get("replaceable") is True:
                libs = res.get("libraries") or (
                    [res.get("library")] if res.get("library") else []
                )
                libs = [str(x) for x in libs if str(x)]
                api = str(res.get("api") or "")
                apis = res.get("apis")
                notes = str(res.get("notes") or "")
                conf = res.get("confidence")
                try:
                    conf = float(conf) if conf is not None else 0.0
                except Exception:
                    conf = 0.0
                libs_str = ", ".join(libs) if libs else "(未指定库)"
                apis_str = (
                    ", ".join([str(a) for a in apis])
                    if isinstance(apis, list)
                    else (api if api else "")
                )
                # 计算进度：区分初始根函数和递归评估的子节点
                total_roots = len(root_funcs)
                if is_root_func:
                    # 初始根函数：显示 (当前根函数索引/总根函数数)
                    root_progress = len(root_funcs_processed)
                    progress_info = (
                        f"({root_progress}/{total_roots})" if total_roots > 0 else ""
                    )
                else:
                    # 递归评估的子节点：显示 (当前根函数索引/总根函数数, 总评估节点数)
                    root_progress = len(root_funcs_processed)
                    total_evaluated = len(processed_roots)
                    if total_roots > 0:
                        progress_info = (
                            f"({root_progress}/{total_roots}, 总评估={total_evaluated})"
                        )
                    else:
                        progress_info = f"(总评估={total_evaluated})"
                msg = f"[c2rust-library] {progress_info} 可替换: {label} -> 库: {libs_str}"
                if apis_str:
                    msg += f"; 参考API: {apis_str}"
                msg += f"; 置信度: {conf:.2f}"
                if notes:
                    msg += f"; 备注: {notes[:MAX_NOTES_DISPLAY_LENGTH]}"
                PrettyOutput.auto_print(msg)

                # 如果节点可替代，无论是否最终替代（如入口函数保护），都不评估其子节点
                # 入口函数保护：不替代 main（保留进行转译），但需要剪除其子节点（因为功能可由库实现）
                # 即时剪枝（不含根）：无论是否为入口函数，只要可替代就剪除子节点
                to_prune = set(desc)
                to_prune.discard(fid)

                newly = len(to_prune - pruned_dynamic)
                pruned_dynamic.update(to_prune)

                # 标记是否为入口函数，用于后续输出阶段判断是否修改 ref 字段
                is_entry = is_entry_function(rec_meta)
                if is_entry:
                    res["is_entry_function"] = True
                    PrettyOutput.auto_print(
                        f"[c2rust-library] 入口函数保护：{label} 保留转译（不修改 ref），但剪除其子节点（功能可由库实现）。"
                        f"替代信息将记录到 library_replacements.jsonl 供转译参考。"
                    )
                else:
                    res["is_entry_function"] = False

                # 无论是否为入口函数，都添加到 selected_roots（入口函数的替代信息需要记录供转译参考）
                selected_roots.append((fid, res))

                # 更新检查点
                checkpoint_state = create_checkpoint_state(
                    checkpoint_key,
                    eval_counter,
                    processed_roots,
                    pruned_dynamic,
                    selected_roots,
                )
                last_ckpt_saved = periodic_checkpoint_save(
                    ckpt_path,
                    checkpoint_state,
                    eval_counter,
                    last_ckpt_saved,
                    checkpoint_interval,
                    resume,
                )

                PrettyOutput.auto_print(
                    f"[c2rust-library] 即时标记剪除子节点(本次新增): +{newly} 个 (累计={len(pruned_dynamic)})"
                )
                # 注意：无论是否入口函数，只要 replaceable 为 True，都不评估子节点
            else:
                # 若不可替代，继续评估其子节点（深度优先）
                for ch in adj_func.get(fid, []):
                    evaluate_node(ch, is_root_func=False)
        except Exception as e:
            PrettyOutput.auto_print(
                f"[c2rust-library] 评估节点 {fid} ({label}) 时出错: {e}"
            )
            # 即使出错，也标记为已处理，避免无限循环
            processed_roots.add(fid)
            if is_root_func:
                root_funcs_processed.add(fid)

    # 对每个候选根进行评估；若根不可替代将递归评估其子节点
    for fid in root_funcs:
        evaluate_node(fid, is_root_func=True)

    # 剪枝集合来自动态评估阶段的累计结果
    pruned_funcs: Set[int] = set(pruned_dynamic)
    # 若限定候选根（candidates）已指定，则将不可达函数一并删除
    try:
        pruned_funcs.update(scope_unreachable_funcs)
    except Exception:
        pass

    # 写出新符号表
    replacements = write_output_symbols(
        all_records,
        pruned_funcs,
        selected_roots,
        out_symbols_path,
        out_symbols_prune_path,
    )

    # 写出替代映射
    with open(out_mapping_path, "w", encoding="utf-8") as fm:
        if replacements:
            for m in replacements:
                fm.write(json.dumps(m, ensure_ascii=False) + "\n")
        else:
            # 即使没有替代项，也记录统计信息，帮助调试
            summary = {
                "summary": {
                    "total_evaluated": eval_counter,
                    "total_processed_roots": len(processed_roots),
                    "total_selected_roots": len(selected_roots),
                    "total_pruned_funcs": len(pruned_funcs),
                    "note": "没有找到可替代的函数。可能原因：1) 所有函数都不可替代；2) 所有可替代的函数都是入口函数（被保护）；3) 从断点恢复时 selected_roots 为空。",
                }
            }
            fm.write(json.dumps(summary, ensure_ascii=False) + "\n")
            PrettyOutput.auto_print(
                f"[c2rust-library] 警告: 没有找到可替代的函数，library_replacements.jsonl 仅包含统计信息。"
                f"已评估={eval_counter}, 已处理根={len(processed_roots)}, 已选中替代根={len(selected_roots)}"
            )

    # 生成转译顺序（剪枝阶段与别名）
    order_path = None
    try:
        compute_translation_order_jsonl(
            Path(out_symbols_path), out_path=order_prune_path
        )
        shutil.copy2(order_prune_path, alias_order_path)
        order_path = alias_order_path
    except Exception as e:
        PrettyOutput.auto_print(f"[c2rust-library] 基于剪枝符号表生成翻译顺序失败: {e}")

    # 完成后清理断点（可选）
    try:
        if resume and clear_checkpoint_on_done and ckpt_path.exists():
            ckpt_path.unlink()
            PrettyOutput.auto_print(f"[c2rust-library] 已清理断点文件: {ckpt_path}")
    except Exception:
        pass

    PrettyOutput.auto_print(
        "[c2rust-library] 库替代剪枝完成（LLM 子树评估）:\n"
        f"- 选中替代根: {len(selected_roots)} 个\n"
        f"- 剪除函数: {len(pruned_funcs)} 个\n"
        f"- 新符号表: {out_symbols_path}\n"
        f"- 替代映射: {out_mapping_path}\n"
        f"- 兼容符号表输出: {out_symbols_prune_path}\n"
        + (f"- 转译顺序: {order_path}\n" if order_path else "")
        + f"- 兼容顺序输出: {order_prune_path}"
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
