# -*- coding: utf-8 -*-
"""
Jarvis 安全分析套件

当前版本概述：
- 关键路径：直扫（direct_scan）→ 单Agent逐条验证（只读工具：read_code/execute_script）→ 聚合输出（JSON + Markdown）
- 目标范围：内存管理、缓冲区操作、错误处理等基础安全问题识别
- 约束：不修改核心框架文件，保持最小侵入；严格只读分析

集成方式：
- 复用 jarvis.jarvis_agent.Agent 与工具注册系统（jarvis.jarvis_tools.registry.ToolRegistry）
- 提供入口：
  - run_security_analysis(entry_path, ...)：直扫 + 单Agent逐条验证 + 聚合

  - workflow.direct_scan(entry_path, ...)：仅启发式直扫

说明：
- 已移除 MultiAgent 编排与相关提示词；不存在"阶段一"等表述
- 模块化重构：将功能拆分为多个模块（prompts, parsers, utils, agents, clustering, analysis, verification, review）
"""

from typing import Dict
from typing import List
from typing import Optional

import typer

from jarvis.jarvis_agent import Agent  # noqa: F401
from jarvis.jarvis_sec.agents import create_analysis_agent as _create_analysis_agent
from jarvis.jarvis_sec.agents import create_cluster_agent as _create_cluster_agent
from jarvis.jarvis_sec.agents import create_review_agent as _create_review_agent
from jarvis.jarvis_sec.agents import subscribe_summary_event as _subscribe_summary_event  # noqa: F401
from jarvis.jarvis_sec.analysis import (
    build_analysis_task_context as _build_analysis_task_context,
)  # noqa: F401
from jarvis.jarvis_sec.analysis import (
    build_validation_error_guidance as _build_validation_error_guidance,
)
from jarvis.jarvis_sec.analysis import (
    expand_and_filter_analysis_results as _expand_and_filter_analysis_results,
)
from jarvis.jarvis_sec.analysis import (
    run_analysis_agent_with_retry as _run_analysis_agent_with_retry,
)
from jarvis.jarvis_sec.analysis import valid_items as _valid_items
from jarvis.jarvis_sec.clustering import (
    build_cluster_error_guidance as _build_cluster_error_guidance,
)
from jarvis.jarvis_sec.clustering import (
    build_cluster_retry_task as _build_cluster_retry_task,
)
from jarvis.jarvis_sec.clustering import build_cluster_task as _build_cluster_task
from jarvis.jarvis_sec.clustering import (
    build_gid_to_item_mapping as _build_gid_to_item_mapping,
)
from jarvis.jarvis_sec.clustering import (
    check_cluster_completeness as _check_cluster_completeness,
)
from jarvis.jarvis_sec.clustering import (
    check_unclustered_gids as _check_unclustered_gids,
)
from jarvis.jarvis_sec.clustering import (
    collect_candidate_gids as _collect_candidate_gids,
)
from jarvis.jarvis_sec.clustering import (
    collect_clustered_gids as _collect_clustered_gids,
)
from jarvis.jarvis_sec.clustering import (
    create_cluster_snapshot_writer as _create_cluster_snapshot_writer,
)
from jarvis.jarvis_sec.clustering import (
    execute_clustering_for_files as _execute_clustering_for_files,
)
from jarvis.jarvis_sec.clustering import (
    extract_classified_gids as _extract_classified_gids,
)
from jarvis.jarvis_sec.clustering import extract_input_gids as _extract_input_gids
from jarvis.jarvis_sec.clustering import (
    fallback_to_file_based_batches as _fallback_to_file_based_batches,
)
from jarvis.jarvis_sec.clustering import filter_pending_items as _filter_pending_items
from jarvis.jarvis_sec.clustering import (
    handle_single_alert_file as _handle_single_alert_file,
)
from jarvis.jarvis_sec.clustering import (
    initialize_clustering_context as _initialize_clustering_context,
)
from jarvis.jarvis_sec.clustering import (
    load_existing_clusters as _load_existing_clusters,
)  # noqa: F401; supplement_missing_gids_for_clustering已移除，不再需要; check_and_supplement_missing_gids已移除，完整性检查已移至process_clustering_phase中
from jarvis.jarvis_sec.clustering import process_cluster_chunk as _process_cluster_chunk
from jarvis.jarvis_sec.clustering import (
    process_cluster_results as _process_cluster_results,
)
from jarvis.jarvis_sec.clustering import (
    process_clustering_phase as _process_clustering_phase,
)
from jarvis.jarvis_sec.clustering import (
    process_file_clustering as _process_file_clustering,
)
from jarvis.jarvis_sec.clustering import (
    record_clustering_completion as _record_clustering_completion,
)
from jarvis.jarvis_sec.clustering import (
    restore_clusters_from_checkpoint as _restore_clusters_from_checkpoint,
)
from jarvis.jarvis_sec.clustering import (
    run_cluster_agent_direct_model as _run_cluster_agent_direct_model,
)
from jarvis.jarvis_sec.clustering import (
    run_cluster_agent_with_retry as _run_cluster_agent_with_retry,
)
from jarvis.jarvis_sec.clustering import (
    supplement_missing_gids as _supplement_missing_gids,
)
from jarvis.jarvis_sec.clustering import (
    validate_cluster_format as _validate_cluster_format,
)
from jarvis.jarvis_sec.clustering import (
    validate_cluster_result as _validate_cluster_result,
)
from jarvis.jarvis_sec.parsers import (
    parse_clusters_from_text as _parse_clusters_from_text,
)  # noqa: F401
from jarvis.jarvis_sec.parsers import (
    try_parse_summary_report as _try_parse_summary_report,
)

# 导入模块化后的函数（用于触发模块加载）
from jarvis.jarvis_sec.prompts import build_summary_prompt as _build_summary_prompt  # noqa: F401
from jarvis.jarvis_sec.prompts import (
    build_verification_summary_prompt as _build_verification_summary_prompt,
)
from jarvis.jarvis_sec.prompts import (
    get_cluster_summary_prompt as _get_cluster_summary_prompt,
)
from jarvis.jarvis_sec.prompts import (
    get_cluster_system_prompt as _get_cluster_system_prompt,
)
from jarvis.jarvis_sec.prompts import (
    get_review_summary_prompt as _get_review_summary_prompt,
)
from jarvis.jarvis_sec.prompts import (
    get_review_system_prompt as _get_review_system_prompt,
)
from jarvis.jarvis_sec.review import (
    build_gid_to_review_mapping as _build_gid_to_review_mapping,
)
from jarvis.jarvis_sec.review import build_review_task as _build_review_task  # noqa: F401
from jarvis.jarvis_sec.review import is_valid_review_item as _is_valid_review_item
from jarvis.jarvis_sec.review import process_review_batch as _process_review_batch
from jarvis.jarvis_sec.review import (
    process_review_batch_items as _process_review_batch_items,
)
from jarvis.jarvis_sec.review import process_review_phase as _process_review_phase
from jarvis.jarvis_sec.review import (
    reinstated_candidates_to_cluster_batches as _reinstated_candidates_to_cluster_batches,
)
from jarvis.jarvis_sec.review import (
    run_review_agent_with_retry as _run_review_agent_with_retry,
)
from jarvis.jarvis_sec.utils import compact_candidate as _compact_candidate
from jarvis.jarvis_sec.utils import count_issues_from_file as _count_issues_from_file
from jarvis.jarvis_sec.utils import create_report_writer as _create_report_writer
from jarvis.jarvis_sec.utils import get_sec_dir as _get_sec_dir
from jarvis.jarvis_sec.utils import git_restore_if_dirty as _git_restore_if_dirty  # noqa: F401
from jarvis.jarvis_sec.utils import (
    group_candidates_by_file as _group_candidates_by_file,
)
from jarvis.jarvis_sec.utils import (
    initialize_analysis_context as _initialize_analysis_context,
)
from jarvis.jarvis_sec.utils import (
    load_all_issues_from_file as _load_all_issues_from_file,
)
from jarvis.jarvis_sec.utils import (
    load_or_run_heuristic_scan as _load_or_run_heuristic_scan,
)
from jarvis.jarvis_sec.utils import (
    load_processed_gids_from_agent_issues as _load_processed_gids_from_agent_issues,
)
from jarvis.jarvis_sec.utils import (
    load_processed_gids_from_issues as _load_processed_gids_from_issues,
)
from jarvis.jarvis_sec.utils import prepare_candidates as _prepare_candidates
from jarvis.jarvis_sec.utils import sig_of as _sig_of
from jarvis.jarvis_sec.verification import (
    build_gid_to_verification_mapping as _build_gid_to_verification_mapping,
)  # noqa: F401
from jarvis.jarvis_sec.verification import (
    is_valid_verification_item as _is_valid_verification_item,
)
from jarvis.jarvis_sec.verification import merge_verified_items as _merge_verified_items
from jarvis.jarvis_sec.verification import (
    merge_verified_items_without_verification as _merge_verified_items_without_verification,
)
from jarvis.jarvis_sec.verification import (
    process_verification_batch as _process_verification_batch,
)
from jarvis.jarvis_sec.verification import (
    process_verification_phase as _process_verification_phase,
)
from jarvis.jarvis_sec.verification import (
    run_verification_agent_with_retry as _run_verification_agent_with_retry,
)
from jarvis.jarvis_sec.workflow import direct_scan
from jarvis.jarvis_sec.workflow import run_with_agent

# 注：当前版本不使用 MultiAgent 编排，已移除默认多智能体配置与创建函数。
# 请使用 run_security_analysis（单Agent逐条验证）或 workflow.direct_scan + format_markdown_report（直扫基线）。
# 注意：部分函数已迁移到模块化文件中（prompts.py, parsers.py, utils.py, agents.py, clustering.py, analysis.py, verification.py, review.py），
# 本文件中保留了这些函数的别名导入，以便向后兼容。


def run_security_analysis(
    entry_path: str,
    languages: Optional[List[str]] = None,
    llm_group: Optional[str] = None,
    report_file: Optional[str] = None,
    cluster_limit: int = 50,
    exclude_dirs: Optional[List[str]] = None,
    enable_verification: bool = True,
    force_save_memory: bool = False,
    output_file: Optional[str] = None,
) -> str:
    """
    运行安全分析工作流（混合模式）。

    改进：
    - 即使在 agent 模式下，也先进行本地正则/启发式直扫，生成候选问题；
      然后将候选问题拆分为子任务，交由多Agent进行深入分析与聚合。

    注意：此函数会在发生异常时更新状态文件为 error 状态。

    参数：
    - entry_path: 待分析的根目录路径
    - languages: 限定扫描的语言扩展（例如 ["c", "cpp", "h", "hpp", "rs"]），为空则使用默认

    返回：
    - 最终报告（字符串），由 Aggregator 生成（JSON + Markdown）

    其他：
    - llm_group: 模型组名称（仅在当前调用链内生效，不覆盖全局配置），将直接传入 Agent 用于选择模型
    - report_file: 增量报告文件路径（JSONL）。当每个子任务检测到 issues 时，立即将一条记录追加到该文件；
      若未指定，则默认写入 entry_path/.jarvis/sec/agent_issues.jsonl
    - cluster_limit: 聚类时每批次最多处理的告警数（默认 50），当单个文件告警过多时按批次进行聚类
    - exclude_dirs: 要排除的目录列表（可选），默认已包含测试目录（test, tests, __tests__, spec, testsuite, testdata）
    - enable_verification: 是否启用二次验证（默认 True），关闭后分析Agent确认的问题将直接写入报告
    - 断点续扫: 默认开启。会基于 .jarvis/sec/candidates.jsonl、clusters.jsonl 和 analysis.jsonl 文件进行状态恢复。
    """

    langs = languages or ["c", "cpp", "h", "hpp", "rs"]

    # 状态管理器（不再使用 status.json，使用空对象）
    class DummyStatusManager:
        def update_pre_scan(self, **kwargs):
            pass

        def update_clustering(self, **kwargs):
            pass

        def update_review(self, **kwargs):
            pass

        def update_verification(self, **kwargs):
            pass

        def mark_completed(self, **kwargs):
            pass

        def mark_error(self, **kwargs):
            pass

    status_mgr = DummyStatusManager()

    # 初始化分析上下文
    sec_dir, progress_path, _progress_append = _initialize_analysis_context(
        entry_path, status_mgr
    )

    # 1) 启发式扫描（支持断点续扫）
    candidates, summary = _load_or_run_heuristic_scan(
        entry_path, langs, exclude_dirs, sec_dir, status_mgr, _progress_append
    )

    # 2) 将候选问题精简为子任务清单，控制上下文长度
    compact_candidates = _prepare_candidates(candidates)

    # 3) 保存候选到新的 candidates.jsonl 文件（包含gid）
    from jarvis.jarvis_sec.file_manager import get_candidates_file
    from jarvis.jarvis_sec.file_manager import save_candidates

    try:
        save_candidates(sec_dir, compact_candidates)
        _progress_append(
            {
                "event": "candidates_saved",
                "path": str(get_candidates_file(sec_dir)),
                "issues_count": len(compact_candidates),
            }
        )
    except Exception:
        pass

    # 记录批次选择信息（可选，用于日志）
    try:
        groups = _group_candidates_by_file(compact_candidates)
        if groups:
            selected_file, items = max(groups.items(), key=lambda kv: len(kv[1]))
            try:
                typer.secho(
                    f"[jarvis-sec] 批次选择: 文件={selected_file} 数量={len(items)}",
                    fg=typer.colors.BLUE,
                )
            except Exception:
                pass
            _progress_append(
                {
                    "event": "batch_selection",
                    "selected_file": selected_file,
                    "selected_count": len(items),
                    "total_in_file": len(items),
                }
            )
    except Exception:
        pass

    # 创建报告写入函数
    _append_report = _create_report_writer(sec_dir, report_file)

    # 3) 处理聚类阶段
    cluster_batches, invalid_clusters_for_review = _process_clustering_phase(
        compact_candidates,
        entry_path,
        langs,
        cluster_limit,
        llm_group,
        sec_dir,
        status_mgr,
        _progress_append,
        force_save_memory=force_save_memory,
    )

    # 4) 处理验证阶段
    meta_records: List[Dict] = []
    all_issues = _process_verification_phase(
        cluster_batches,
        entry_path,
        langs,
        llm_group,
        sec_dir,
        status_mgr,
        _progress_append,
        _append_report,
        enable_verification=enable_verification,
        force_save_memory=force_save_memory,
    )

    # 5) 使用统一聚合器生成最终报告（JSON + Markdown）
    try:
        from jarvis.jarvis_sec.report import build_json_and_markdown

        result = build_json_and_markdown(
            all_issues,  # type: ignore[arg-type]
            scanned_root=summary.get("scanned_root"),
            scanned_files=summary.get("scanned_files"),
            meta=meta_records or None,
            output_file=output_file,
        )
        # 标记分析完成
        status_mgr.mark_completed(
            total_issues=len(all_issues),
            message=f"安全分析完成，共发现 {len(all_issues)} 个问题",
        )
        return result
    except Exception as e:
        # 发生错误时更新状态
        error_msg = str(e)
        status_mgr.mark_error(error_message=error_msg, error_type=type(e).__name__)
        raise
    finally:
        # 清理资源
        pass


__all__ = [
    "run_security_analysis",
    "direct_scan",
    "run_with_agent",
]
