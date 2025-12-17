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

from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from jarvis.jarvis_utils.output import PrettyOutput

from jarvis.jarvis_agent import Agent  # noqa: F401
from jarvis.jarvis_sec.utils import (
    initialize_analysis_context as _initialize_analysis_context,
)
from jarvis.jarvis_sec.utils import (
    load_or_run_heuristic_scan as _load_or_run_heuristic_scan,
)
from jarvis.jarvis_sec.utils import prepare_candidates as _prepare_candidates
from jarvis.jarvis_sec.utils import (
    group_candidates_by_file as _group_candidates_by_file,
)
from jarvis.jarvis_sec.utils import create_report_writer as _create_report_writer
from jarvis.jarvis_sec.clustering import (
    process_clustering_phase as _process_clustering_phase,
)
from jarvis.jarvis_sec.verification import (
    process_verification_phase as _process_verification_phase,
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
        def update_pre_scan(self, **kwargs: Any) -> None:
            pass

        def update_clustering(self, **kwargs: Any) -> None:
            pass

        def update_review(self, **kwargs: Any) -> None:
            pass

        def update_verification(self, **kwargs: Any) -> None:
            pass

        def mark_completed(self, **kwargs: Any) -> None:
            pass

        def mark_error(self, **kwargs: Any) -> None:
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
                PrettyOutput.auto_print(
                    f"[jarvis-sec] 批次选择: 文件={selected_file} 数量={len(items)}"
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
    meta_records: List[Dict[str, Any]] = []
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
