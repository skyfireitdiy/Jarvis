# -*- coding: utf-8 -*-
"""工具函数模块"""

from typing import Dict, List, Optional
from pathlib import Path
import json
import typer

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
        proc = _sub.run(["git", "status", "--porcelain"], cwd=str(root), capture_output=True, text=True)
        if proc.returncode != 0:
            return 0
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        if lines:
            _sub.run(["git", "checkout", "--", "."], cwd=str(root), capture_output=True, text=True)
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
    status_mgr,
) -> tuple:
    """
    初始化分析上下文，包括状态管理、进度文件、目录等。
    
    返回: (sec_dir, progress_path, _progress_append, done_sigs)
    """
    from datetime import datetime as _dt
    
    # 获取 .jarvis/sec 目录
    sec_dir = get_sec_dir(entry_path)
    progress_path = sec_dir / "progress.jsonl"
    
    # 进度追加函数
    def _progress_append(rec: Dict) -> None:
        try:
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            rec = dict(rec)
            rec.setdefault("timestamp", _dt.utcnow().isoformat() + "Z")
            line = json.dumps(rec, ensure_ascii=False)
            with progress_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            # 进度文件失败不影响主流程
            pass
    
    # 已完成集合（按候选签名）
    done_sigs: set = set()
    if progress_path.exists():
        try:
            for line in progress_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("event") == "task_status" and obj.get("status") == "done":
                    sig = obj.get("candidate_signature")
                    if sig:
                        done_sigs.add(sig)
        except Exception:
            pass
    
    return sec_dir, progress_path, _progress_append, done_sigs


def load_or_run_heuristic_scan(
    entry_path: str,
    langs: List[str],
    exclude_dirs: Optional[List[str]],
    sec_dir: Path,
    status_mgr,
    _progress_append,
) -> tuple[List[Dict], Dict]:
    """
    加载或运行启发式扫描。
    
    返回: (candidates, summary)
    """
    _heuristic_path = sec_dir / "heuristic_issues.jsonl"
    candidates: List[Dict] = []
    summary: Dict = {}
    
    if _heuristic_path.exists():
        try:
            typer.secho(f"[jarvis-sec] 从 {_heuristic_path} 恢复启发式扫描", fg=typer.colors.BLUE)
            with _heuristic_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        candidates.append(json.loads(line))
            _progress_append({
                "event": "pre_scan_resumed",
                "path": str(_heuristic_path),
                "issues_found": len(candidates)
            })
        except Exception as e:
            typer.secho(f"[jarvis-sec] 恢复启发式扫描失败，执行完整扫描: {e}", fg=typer.colors.YELLOW)
            candidates = []  # 重置以便执行完整扫描
    
    if not candidates:
        _progress_append({"event": "pre_scan_start", "entry_path": entry_path, "languages": langs})
        status_mgr.update_pre_scan(message="开始启发式扫描...")
        pre_scan = direct_scan(entry_path, languages=langs, exclude_dirs=exclude_dirs)
        candidates = pre_scan.get("issues", [])
        summary = pre_scan.get("summary", {})
        scanned_files = summary.get("scanned_files", 0)
        status_mgr.update_pre_scan(
            current_files=scanned_files,
            total_files=scanned_files,
            issues_found=len(candidates),
            message=f"启发式扫描完成，发现 {len(candidates)} 个候选问题"
        )
        _progress_append({
            "event": "pre_scan_done",
            "entry_path": entry_path,
            "languages": langs,
            "scanned_files": scanned_files,
            "issues_found": len(candidates)
        })
        # 持久化
        try:
            _heuristic_path.parent.mkdir(parents=True, exist_ok=True)
            with _heuristic_path.open("w", encoding="utf-8") as f:
                for item in candidates:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            _progress_append({
                "event": "heuristic_report_written",
                "path": str(_heuristic_path),
                "issues_count": len(candidates),
            })
            typer.secho(f"[jarvis-sec] 已将 {len(candidates)} 个启发式扫描问题写入 {_heuristic_path}", fg=typer.colors.GREEN)
        except Exception:
            pass
    else:
        # 从断点恢复启发式扫描结果
        status_mgr.update_pre_scan(
            issues_found=len(candidates),
            message=f"从断点恢复，已发现 {len(candidates)} 个候选问题"
        )
    
    return candidates, summary


def compact_candidate(it: Dict) -> Dict:
    """精简候选问题，只保留必要字段"""
    return {
        "language": it.get("language"),
        "category": it.get("category"),
        "pattern": it.get("pattern"),
        "file": it.get("file"),
        "line": it.get("line"),
        "evidence": it.get("evidence"),
        "confidence": it.get("confidence"),
        "severity": it.get("severity", "medium"),
    }


def prepare_candidates(candidates: List[Dict]) -> List[Dict]:
    """
    将候选问题精简为子任务清单，控制上下文长度，并分配全局唯一ID。
    
    返回: compact_candidates (已分配gid的候选列表)
    """
    compact_candidates = [compact_candidate(it) for it in candidates]
    # 为所有候选分配全局唯一数字ID（gid: 1..N），用于跨批次/跨文件统一编号与跟踪
    for i, it in enumerate(compact_candidates, start=1):
        try:
            it["gid"] = i
        except Exception:
            pass
    
    return compact_candidates


def group_candidates_by_file(candidates: List[Dict]) -> Dict[str, List[Dict]]:
    """按文件分组候选问题"""
    from collections import defaultdict
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for it in candidates:
        groups[str(it.get("file") or "")].append(it)
    return groups


def create_report_writer(sec_dir: Path, report_file: Optional[str]):
    """创建报告写入函数"""
    def _append_report(items, source: str, task_id: str, cand: Dict):
        """将当前子任务的检测结果追加写入 JSONL 报告文件（每行一个 issue）。仅当 items 非空时写入。"""
        if not items:
            return
        try:
            path = Path(report_file) if report_file else sec_dir / "agent_issues.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                for item in items:
                    line = json.dumps(item, ensure_ascii=False)
                    f.write(line + "\n")
            try:
                typer.secho(f"[jarvis-sec] 已将 {len(items)} 个问题写入 {path}", fg=typer.colors.GREEN)
            except Exception:
                pass
        except Exception:
            # 报告写入失败不影响主流程
            pass
    
    return _append_report


def sig_of(c: Dict) -> str:
    """生成候选问题的签名"""
    return f"{c.get('language','')}|{c.get('file','')}|{c.get('line','')}|{c.get('pattern','')}"


def load_processed_gids_from_issues(sec_dir: Path) -> set:
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
                    typer.secho(f"[jarvis-sec] 断点恢复：从 agent_issues.jsonl 读取到 {len(processed_gids)} 个已处理的 gid", fg=typer.colors.BLUE)
                except Exception:
                    pass
    except Exception:
        pass
    return processed_gids


def count_issues_from_file(sec_dir: Path) -> int:
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
                            if item.get("has_risk") is True and "verification_notes" in item:
                                count += 1
                                saved_gids.add(gid)
                    except Exception:
                        pass
    except Exception:
        pass
    return count


def load_completed_batch_ids(progress_path: Path) -> set:
    """从 progress.jsonl 读取已完成的批次ID"""
    completed_batch_ids = set()
    try:
        if progress_path.exists():
            with progress_path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        # 检查 batch_status 事件，status 为 "done" 表示批次已完成
                        if obj.get("event") == "batch_status" and obj.get("status") == "done":
                            batch_id = obj.get("batch_id")
                            if batch_id:
                                completed_batch_ids.add(batch_id)
                    except Exception:
                        pass
    except Exception:
        pass
    return completed_batch_ids


def load_all_issues_from_file(sec_dir: Path) -> List[Dict]:
    """从 agent_issues.jsonl 读取所有已保存的告警"""
    all_issues: List[Dict] = []
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
                            if item.get("has_risk") is True and "verification_notes" in item:
                                all_issues.append(item)
                                saved_gids_from_file.add(gid)
                    except Exception:
                        pass
            
            if all_issues:
                try:
                    typer.secho(f"[jarvis-sec] 从 agent_issues.jsonl 加载了 {len(all_issues)} 个已保存的告警", fg=typer.colors.BLUE)
                except Exception:
                    pass
        else:
            try:
                typer.secho(f"[jarvis-sec] agent_issues.jsonl 不存在，当前运行未发现任何问题", fg=typer.colors.BLUE)
            except Exception:
                pass
    except Exception as e:
        # 加载失败不影响主流程
        try:
            typer.secho(f"[jarvis-sec] 警告：从 agent_issues.jsonl 加载告警失败: {e}", fg=typer.colors.YELLOW)
        except Exception:
            pass
    return all_issues


def load_processed_gids_from_agent_issues(sec_dir: Path) -> set:
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

