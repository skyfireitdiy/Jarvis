# -*- coding: utf-8 -*-
"""工具函数模块"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from jarvis.jarvis_utils.output import PrettyOutput

from jarvis.jarvis_sec.workflow import direct_scan


def git_restore_if_dirty(repo_root: str) -> int:
    """
    若 repo_root 为 git 仓库：检测工作区是否有变更；如有则使用 'git checkout -- .' 恢复。
    返回估算的变更文件数（基于 git status --porcelain 的行数）。
    """
    try:
        import subprocess as _sub

        root = Path(repo_root)
        if not (root / ".git").exists():
            return 0
        proc = _sub.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return 0
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        if lines:
            _sub.run(
                ["git", "checkout", "--", "."],
                cwd=str(root),
                capture_output=True,
                text=True,
            )
            return len(lines)
    except Exception:
        pass
    return 0


def get_sec_dir(base_path: str) -> Path:
    """获取 .jarvis/sec 目录路径，支持 base_path 是项目根目录或已经是 .jarvis/sec 目录"""
    base = Path(base_path)
    # 检查 base_path 是否已经是 .jarvis/sec 目录
    if base.name == "sec" and base.parent.name == ".jarvis":
        return base
    # 否则，假设 base_path 是项目根目录
    return base / ".jarvis" / "sec"


def initialize_analysis_context(
    entry_path: str,
    status_mgr: Any,
) -> Tuple[Path, Optional[str], Any]:
    """
    初始化分析上下文，包括状态管理、进度文件、目录等。

    返回: (sec_dir, progress_path, _progress_append)
    """
    # 获取 .jarvis/sec 目录
    sec_dir = get_sec_dir(entry_path)
    progress_path = None  # 不再使用 progress.jsonl

    # 进度追加函数（空函数，不再记录）
    def _progress_append(rec: Dict[str, Any]) -> None:
        pass  # 不再记录进度日志

    return sec_dir, progress_path, _progress_append


def load_or_run_heuristic_scan(
    entry_path: str,
    langs: List[str],
    exclude_dirs: Optional[List[str]],
    sec_dir: Path,
    status_mgr: Any,
    _progress_append: Any,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    加载或运行启发式扫描。

    优先从新的 candidates.jsonl 文件加载，如果不存在则回退到旧的 heuristic_issues.jsonl。

    返回: (candidates, summary)
    """
    candidates: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {}

    # 优先使用新的 candidates.jsonl 文件
    from jarvis.jarvis_sec.file_manager import get_candidates_file
    from jarvis.jarvis_sec.file_manager import load_candidates

    candidates = load_candidates(sec_dir)

    if candidates:
        try:
            PrettyOutput.auto_print(
                f"✨ [jarvis-sec] 从 {get_candidates_file(sec_dir)} 恢复启发式扫描",
                timestamp=True,
            )
            _progress_append(
                {
                    "event": "pre_scan_resumed",
                    "path": str(get_candidates_file(sec_dir)),
                    "issues_found": len(candidates),
                }
            )
        except Exception:
            pass
    else:
        # 回退到旧的 heuristic_issues.jsonl 文件（向后兼容）
        _heuristic_path = sec_dir / "heuristic_issues.jsonl"
        if _heuristic_path.exists():
            try:
                PrettyOutput.auto_print(
                    f"✨ [jarvis-sec] 从 {_heuristic_path} 恢复启发式扫描（旧格式）",
                    timestamp=True,
                )
                with _heuristic_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            candidates.append(json.loads(line))
                _progress_append(
                    {
                        "event": "pre_scan_resumed",
                        "path": str(_heuristic_path),
                        "issues_found": len(candidates),
                    }
                )
            except Exception as e:
                PrettyOutput.auto_print(
                    f"⚠️ [jarvis-sec] 恢复启发式扫描失败，执行完整扫描: {e}",
                    timestamp=True,
                )
                candidates = []  # 重置以便执行完整扫描

    if not candidates:
        _progress_append(
            {"event": "pre_scan_start", "entry_path": entry_path, "languages": langs}
        )
        status_mgr.update_pre_scan(message="开始启发式扫描...")
        pre_scan = direct_scan(entry_path, languages=langs, exclude_dirs=exclude_dirs)
        candidates = pre_scan.get("issues", [])
        summary = pre_scan.get("summary", {})
        scanned_files = summary.get("scanned_files", 0)
        status_mgr.update_pre_scan(
            current_files=scanned_files,
            total_files=scanned_files,
            issues_found=len(candidates),
            message=f"启发式扫描完成，发现 {len(candidates)} 个候选问题",
        )
        _progress_append(
            {
                "event": "pre_scan_done",
                "entry_path": entry_path,
                "languages": langs,
                "scanned_files": scanned_files,
                "issues_found": len(candidates),
            }
        )
        # 持久化
        try:
            _heuristic_path.parent.mkdir(parents=True, exist_ok=True)
            with _heuristic_path.open("w", encoding="utf-8") as f:
                for item in candidates:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            _progress_append(
                {
                    "event": "heuristic_report_written",
                    "path": str(_heuristic_path),
                    "issues_count": len(candidates),
                }
            )
            PrettyOutput.auto_print(
                f"✅ [jarvis-sec] 已将 {len(candidates)} 个启发式扫描问题写入 {_heuristic_path}",
                timestamp=True,
            )
        except Exception:
            pass
    else:
        # 从断点恢复启发式扫描结果
        status_mgr.update_pre_scan(
            issues_found=len(candidates),
            message=f"从断点恢复，已发现 {len(candidates)} 个候选问题",
        )

    return candidates, summary


def compact_candidate(it: Dict[str, Any]) -> Dict[str, Any]:
    """精简候选问题，只保留必要字段"""
    result = {
        "language": it.get("language"),
        "category": it.get("category"),
        "pattern": it.get("pattern"),
        "file": it.get("file"),
        "line": it.get("line"),
        "evidence": it.get("evidence"),
        "confidence": it.get("confidence"),
        "severity": it.get("severity", "medium"),
    }
    # 如果候选已经有gid，保留它（用于断点恢复）
    if "gid" in it:
        try:
            gid_val = int(it.get("gid", 0))
            if gid_val >= 1:
                result["gid"] = gid_val
        except Exception:
            pass
    return result


def prepare_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将候选问题精简为子任务清单，控制上下文长度，并分配全局唯一ID。

    返回: compact_candidates (已分配gid的候选列表)
    """
    compact_candidates = [compact_candidate(it) for it in candidates]

    # 检查是否所有候选都已经有gid（从heuristic_issues.jsonl恢复时）
    all_have_gid = all(
        "gid" in it and isinstance(it.get("gid"), int) and it.get("gid", 0) >= 1
        for it in compact_candidates
    )

    if not all_have_gid:
        # 如果有候选没有gid，需要分配
        # 优先保留已有的gid，为没有gid的候选分配新的gid
        existing_gids = set()
        for it in compact_candidates:
            try:
                gid_val = int(it.get("gid", 0))
                if gid_val >= 1:
                    existing_gids.add(gid_val)
            except Exception:
                pass

        # 为没有gid的候选分配新的gid
        next_gid = 1
        for it in compact_candidates:
            if (
                "gid" not in it
                or not isinstance(it.get("gid"), int)
                or it.get("gid", 0) < 1
            ):
                # 找到一个未使用的gid
                while next_gid in existing_gids:
                    next_gid += 1
                try:
                    it["gid"] = next_gid
                    existing_gids.add(next_gid)
                    next_gid += 1
                except Exception:
                    pass

    return compact_candidates


def group_candidates_by_file(
    candidates: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """按文件分组候选问题"""
    from collections import defaultdict

    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for it in candidates:
        groups[str(it.get("file") or "")].append(it)
    return groups


def create_report_writer(sec_dir: Path, report_file: Optional[str]) -> Any:
    """创建报告写入函数"""
    from jarvis.jarvis_sec.file_manager import load_clusters
    from jarvis.jarvis_sec.file_manager import save_analysis_result

    def _append_report(
        items: List[Dict[str, Any]], source: str, task_id: str, cand: Dict[str, Any]
    ) -> None:
        """
        将当前子任务的检测结果追加写入 analysis.jsonl 文件。

        参数:
        - items: 验证通过的问题列表（has_risk: true）
        - source: 来源（"analysis_only" 或 "verified"）
        - task_id: 任务ID（如 "JARVIS-SEC-Batch-1"）
        - cand: 候选信息，包含 batch 和 candidates
        """
        if not items:
            return

        try:
            # 从批次中提取信息
            batch = cand.get("batch", False)
            candidates = cand.get("candidates", [])

            if not batch or not candidates:
                # 如果没有批次信息，回退到旧格式（向后兼容）
                path = (
                    Path(report_file) if report_file else sec_dir / "agent_issues.jsonl"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as f:
                    for item in items:
                        line = json.dumps(item, ensure_ascii=False)
                        f.write(line + "\n")
                try:
                    PrettyOutput.auto_print(
                        f"✅ [jarvis-sec] 已将 {len(items)} 个问题写入 {path}（旧格式）",
                        timestamp=True,
                    )
                except Exception:
                    pass
                return

            # 从批次中提取 file 和 gids
            batch_file = candidates[0].get("file") if candidates else ""
            batch_gids = []
            for c in candidates:
                try:
                    gid = int(c.get("gid", 0))
                    if gid >= 1:
                        batch_gids.append(gid)
                except Exception:
                    pass

            # 从 clusters.jsonl 中查找对应的 cluster_id
            clusters = load_clusters(sec_dir)
            cluster_id = None
            batch_index = None
            cluster_index = None

            # 尝试从 task_id 中提取 batch_index（格式：JARVIS-SEC-Batch-1）
            try:
                if "Batch-" in task_id:
                    batch_index = int(task_id.split("Batch-")[1])
            except Exception:
                pass

            # 查找匹配的聚类（通过 file 和 gids）
            for cluster in clusters:
                cluster_file = str(cluster.get("file", ""))
                cluster_gids = cluster.get("gids", [])

                if cluster_file == batch_file and set(cluster_gids) == set(batch_gids):
                    cluster_id = cluster.get("cluster_id", "")
                    if not cluster_id:
                        # 如果没有 cluster_id，生成一个
                        cluster_id = f"{cluster_file}|{cluster.get('batch_index', batch_index or 0)}|{cluster.get('cluster_index', 0)}"
                    batch_index = cluster.get("batch_index", batch_index or 0)
                    cluster_index = cluster.get("cluster_index", 0)
                    break

            # 如果找不到匹配的聚类，生成一个临时的 cluster_id
            if not cluster_id:
                cluster_id = f"{batch_file}|{batch_index or 0}|0"
                batch_index = batch_index or 0
                cluster_index = 0

            # 分离验证为问题的gid和误报的gid
            verified_gids = []
            false_positive_gids = []
            issues = []

            # 从 items 中提取已验证的问题
            for item in items:
                try:
                    gid = int(item.get("gid", 0))
                    if gid >= 1:
                        has_risk = item.get("has_risk", False)
                        if has_risk:
                            verified_gids.append(gid)
                            issues.append(item)
                        else:
                            false_positive_gids.append(gid)
                except Exception:
                    pass

            # 从 candidates 中提取所有未在 items 中的 gid（这些可能是误报）
            for c in candidates:
                try:
                    gid = int(c.get("gid", 0))
                    if (
                        gid >= 1
                        and gid not in verified_gids
                        and gid not in false_positive_gids
                    ):
                        # 如果这个 gid 不在已验证的问题中，可能是误报
                        false_positive_gids.append(gid)
                except Exception:
                    pass

            # 构建分析结果记录
            analysis_result = {
                "cluster_id": cluster_id,
                "file": batch_file,
                "batch_index": batch_index,
                "cluster_index": cluster_index,
                "gids": batch_gids,
                "verified_gids": verified_gids,
                "false_positive_gids": false_positive_gids,
                "issues": issues,
            }

            # 保存到 analysis.jsonl
            save_analysis_result(sec_dir, analysis_result)

            try:
                PrettyOutput.auto_print(
                    f"✅ [jarvis-sec] 已将批次 {batch_index} 的分析结果写入 analysis.jsonl（问题: {len(verified_gids)}, 误报: {len(false_positive_gids)}）",
                    timestamp=True,
                )
            except Exception:
                pass
        except Exception as e:
            # 报告写入失败不影响主流程
            try:
                PrettyOutput.auto_print(f"⚠️ [jarvis-sec] 警告：保存分析结果失败: {e}")
            except Exception:
                pass

    return _append_report


def sig_of(c: Dict[str, Any]) -> str:
    """生成候选问题的签名"""
    return f"{c.get('language', '')}|{c.get('file', '')}|{c.get('line', '')}|{c.get('pattern', '')}"


def load_processed_gids_from_issues(sec_dir: Path) -> Set[int]:
    """从 agent_issues.jsonl 中读取已处理的 gid"""
    processed_gids = set()
    try:
        _agent_issues_path = sec_dir / "agent_issues.jsonl"
        if _agent_issues_path.exists():
            with _agent_issues_path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        issue_obj = json.loads(line)
                        _gid = int(issue_obj.get("gid", 0))
                        if _gid >= 1:
                            processed_gids.add(_gid)
                    except Exception:
                        pass
            if processed_gids:
                try:
                    PrettyOutput.auto_print(
                        f"✨ [jarvis-sec] 断点恢复：从 agent_issues.jsonl 读取到 {len(processed_gids)} 个已处理的 gid",
                        timestamp=True,
                    )
                except Exception:
                    pass
    except Exception:
        pass
    return processed_gids


def count_issues_from_file(sec_dir: Path) -> int:
    """从 analysis.jsonl 读取问题数量"""
    from jarvis.jarvis_sec.file_manager import get_verified_issue_gids

    verified_gids = get_verified_issue_gids(sec_dir)
    return len(verified_gids)


def count_issues_from_file_old(sec_dir: Path) -> int:
    """从 agent_issues.jsonl 中读取当前问题总数（用于状态显示）"""
    count = 0
    try:
        _agent_issues_path = sec_dir / "agent_issues.jsonl"
        if _agent_issues_path.exists():
            saved_gids = set()
            with _agent_issues_path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        gid = item.get("gid", 0)
                        if gid >= 1 and gid not in saved_gids:
                            # 只统计验证通过的告警（has_risk: true 且有 verification_notes）
                            if (
                                item.get("has_risk") is True
                                and "verification_notes" in item
                            ):
                                count += 1
                                saved_gids.add(gid)
                    except Exception:
                        pass
    except Exception:
        pass
    return count


def load_all_issues_from_file(sec_dir: Path) -> List[Dict[str, Any]]:
    """从 agent_issues.jsonl 读取所有已保存的告警"""
    all_issues: List[Dict[str, Any]] = []
    try:
        _agent_issues_path = sec_dir / "agent_issues.jsonl"
        if _agent_issues_path.exists():
            saved_gids_from_file = set()
            with _agent_issues_path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        gid = item.get("gid", 0)
                        if gid >= 1 and gid not in saved_gids_from_file:
                            # 只保留验证通过的告警（has_risk: true 且有 verification_notes）
                            if (
                                item.get("has_risk") is True
                                and "verification_notes" in item
                            ):
                                all_issues.append(item)
                                saved_gids_from_file.add(gid)
                    except Exception:
                        pass

            if all_issues:
                try:
                    PrettyOutput.auto_print(
                        f"✨ [jarvis-sec] 从 agent_issues.jsonl 加载了 {len(all_issues)} 个已保存的告警",
                        timestamp=True,
                    )
                except Exception:
                    pass
        else:
            try:
                PrettyOutput.auto_print(
                    "✨ [jarvis-sec] agent_issues.jsonl 不存在，当前运行未发现任何问题",
                    timestamp=True,
                )
            except Exception:
                pass
    except Exception as e:
        # 加载失败不影响主流程
        try:
            PrettyOutput.auto_print(
                f"⚠️ [jarvis-sec] 警告：从 agent_issues.jsonl 加载告警失败: {e}",
                timestamp=True,
            )
        except Exception:
            pass
    return all_issues


def load_processed_gids_from_agent_issues(sec_dir: Path) -> Set[int]:
    """从 agent_issues.jsonl 读取已处理的 gid"""
    processed_gids = set()
    try:
        _agent_issues_path = sec_dir / "agent_issues.jsonl"
        if _agent_issues_path.exists():
            with _agent_issues_path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        issue_obj = json.loads(line)
                        _gid = int(issue_obj.get("gid", 0))
                        if _gid >= 1:
                            processed_gids.add(_gid)
                    except Exception:
                        pass
    except Exception:
        pass
    return processed_gids
