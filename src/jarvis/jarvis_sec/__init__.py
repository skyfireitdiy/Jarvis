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
- 已移除 MultiAgent 编排与相关提示词；不存在“阶段一”等表述
"""

from typing import Dict, List, Optional

import typer
import json5 as json

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_sec.workflow import direct_scan, run_with_agent
from jarvis.jarvis_tools.registry import ToolRegistry


def _build_summary_prompt() -> str:
    """
    构建摘要提示词：要求以 <REPORT>...</REPORT> 包裹的 JSON 输出（仅JSON）。
    系统提示词不强制规定主对话输出格式，仅在摘要中给出结构化结果。
    """
    return """
请将本轮"安全子任务（单点验证）"的结构化结果仅放入以下标记中，并使用 JSON 数组对象形式输出。
仅输出全局编号（gid）与详细理由（不含位置信息），gid 为全局唯一的数字编号。

示例1：有告警的情况（has_risk: true，单个gid）
<REPORT>
[
  {
    "gid": 1,
    "has_risk": true,
    "preconditions": "输入字符串 src 的长度大于等于 dst 的缓冲区大小",
    "trigger_path": "调用路径推导：main() -> handle_network_request() -> parse_packet() -> foobar() -> strcpy()。数据流：网络数据包通过 handle_network_request() 接收，传递给 parse_packet() 解析，parse_packet() 未对数据长度进行校验，直接将 src 传递给 foobar()，foobar() 调用 strcpy(dst, src) 时未检查 src 长度，可导致缓冲区溢出。关键调用点：parse_packet() 函数未对输入长度进行校验。",
    "consequences": "缓冲区溢出，可能引发程序崩溃或任意代码执行",
    "suggestions": "使用 strncpy_s 或其他安全的字符串复制函数"
  }
]
</REPORT>

示例2：有告警的情况（has_risk: true，多个gid合并，路径和原因一致）
<REPORT>
[
  {
    "gids": [1, 2, 3],
    "has_risk": true,
    "preconditions": "输入字符串 src 的长度大于等于 dst 的缓冲区大小",
    "trigger_path": "调用路径推导：main() -> handle_network_request() -> parse_packet() -> foobar() -> strcpy()。数据流：网络数据包通过 handle_network_request() 接收，传递给 parse_packet() 解析，parse_packet() 未对数据长度进行校验，直接将 src 传递给 foobar()，foobar() 调用 strcpy(dst, src) 时未检查 src 长度，可导致缓冲区溢出。关键调用点：parse_packet() 函数未对输入长度进行校验。",
    "consequences": "缓冲区溢出，可能引发程序崩溃或任意代码执行",
    "suggestions": "使用 strncpy_s 或其他安全的字符串复制函数"
  }
]
</REPORT>

示例3：误报或无问题（返回空数组）
<REPORT>
[]
</REPORT>

要求：
- 只能在 <REPORT> 与 </REPORT> 中输出 JSON 数组，且不得出现其他文本。
- 若确认本批次全部为误报或无问题，请返回空数组 []。
- 数组元素为对象，包含字段：
  - gid: 整数（全局唯一编号，单个告警时使用）
  - gids: 整数数组（全局唯一编号数组，多个告警合并时使用）
  - has_risk: 布尔值 (true/false)，表示该项是否存在真实安全风险。
  - preconditions: 字符串（触发漏洞的前置条件，仅当 has_risk 为 true 时必需）
  - trigger_path: 字符串（漏洞的触发路径，必须包含完整的调用路径推导，包括：1) 可控输入的来源；2) 从输入源到缺陷代码的完整调用链（函数调用序列）；3) 每个调用点的数据校验情况；4) 触发条件。格式示例："调用路径推导：函数A() -> 函数B() -> 函数C() -> 缺陷代码。数据流：输入来源 -> 传递路径。关键调用点：函数B()未做校验。"，仅当 has_risk 为 true 时必需）
  - consequences: 字符串（漏洞被触发后可能导致的后果，仅当 has_risk 为 true 时必需）
  - suggestions: 字符串（修复或缓解该漏洞的建议，仅当 has_risk 为 true 时必需）
- **合并格式优化**：如果多个告警（gid）的路径（trigger_path）、原因（preconditions/consequences/suggestions）完全一致，可以使用 gids 数组格式合并输出，减少重复内容。单个告警使用 gid，多个告警合并使用 gids。gid 和 gids 不能同时出现。
- 不要在数组元素中包含 file/line/pattern 等位置信息；写入 jsonl 时系统会结合原始候选信息。
- **关键**：仅当 `has_risk` 为 `true` 时，才会被记录为确认的问题。对于确认是误报的条目，请确保 `has_risk` 为 `false` 或不输出该条目。
- **输出格式**：有告警的条目必须包含所有字段（gid 或 gids, has_risk, preconditions, trigger_path, consequences, suggestions）；无告警的条目只需包含 gid 和 has_risk。
- **调用路径推导要求**：trigger_path 字段必须包含完整的调用路径推导，不能省略或简化。必须明确说明从可控输入到缺陷代码的完整调用链，以及每个调用点的校验情况。如果无法推导出完整的调用路径，应该判定为误报（has_risk: false）。
- 支持json5语法（如尾随逗号、注释等）。
""".strip()


def _build_verification_summary_prompt() -> str:
    """
    构建验证 Agent 的摘要提示词：验证分析 Agent 给出的结论是否正确。
    """
    return """
请将本轮"验证分析结论"的结构化结果仅放入以下标记中，并使用 JSON 数组对象形式输出。
你需要验证分析 Agent 给出的结论是否正确，包括前置条件、触发路径、后果和建议是否合理。

示例1：验证通过（is_valid: true，单个gid）
<REPORT>
[
  {
    "gid": 1,
    "is_valid": true,
    "verification_notes": "分析结论正确，前置条件合理，触发路径清晰，后果评估准确"
  }
]
</REPORT>

示例2：验证通过（is_valid: true，多个gid合并）
<REPORT>
[
  {
    "gids": [1, 2, 3],
    "is_valid": true,
    "verification_notes": "分析结论正确，前置条件合理，触发路径清晰，后果评估准确"
  }
]
</REPORT>

示例3：验证不通过（is_valid: false）
<REPORT>
[
  {
    "gid": 1,
    "is_valid": false,
    "verification_notes": "前置条件过于宽泛，实际代码中已有输入校验，触发路径不成立"
  }
]
</REPORT>

要求：
- 只能在 <REPORT> 与 </REPORT> 中输出 JSON 数组，且不得出现其他文本。
- 数组元素为对象，包含字段：
  - gid: 整数（全局唯一编号，对应分析 Agent 给出的 gid，单个告警时使用）
  - gids: 整数数组（全局唯一编号数组，对应分析 Agent 给出的 gids，多个告警合并时使用）
  - is_valid: 布尔值 (true/false)，表示分析 Agent 的结论是否正确
  - verification_notes: 字符串（验证说明，解释为什么结论正确或不正确）
- **合并格式优化**：如果多个告警（gid）的验证结果（is_valid）和验证说明（verification_notes）完全一致，可以使用 gids 数组格式合并输出，减少重复内容。单个告警使用 gid，多个告警合并使用 gids。gid 和 gids 不能同时出现。
- 必须对所有输入的 gid 进行验证，不能遗漏。
- 如果验证通过（is_valid: true），则保留该告警；如果验证不通过（is_valid: false），则视为误报，不记录为问题。
- 支持json5语法（如尾随逗号、注释等）。
""".strip()


# 注：当前版本不使用 MultiAgent 编排，已移除默认多智能体配置与创建函数。
# 请使用 run_security_analysis（单Agent逐条验证）或 workflow.direct_scan + format_markdown_report（直扫基线）。 

def _git_restore_if_dirty(repo_root: str) -> int:
    """
    若 repo_root 为 git 仓库：检测工作区是否有变更；如有则使用 'git checkout -- .' 恢复。
    返回估算的变更文件数（基于 git status --porcelain 的行数）。
    """
    try:
        from pathlib import Path as _Path
        import subprocess as _sub
        root = _Path(repo_root)
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


def _get_sec_dir(base_path: str):
    """获取 .jarvis/sec 目录路径，支持 base_path 是项目根目录或已经是 .jarvis/sec 目录"""
    from pathlib import Path as _Path
    base = _Path(base_path)
    # 检查 base_path 是否已经是 .jarvis/sec 目录
    if base.name == "sec" and base.parent.name == ".jarvis":
        return base
    # 否则，假设 base_path 是项目根目录
    return base / ".jarvis" / "sec"


def _initialize_analysis_context(
    entry_path: str,
    status_mgr,
) -> tuple:
    """
    初始化分析上下文，包括状态管理、进度文件、目录等。
    
    返回: (sec_dir, progress_path, _progress_append, done_sigs)
    """
    from pathlib import Path as _Path
    from datetime import datetime as _dt
    import json as _json
    
    # 获取 .jarvis/sec 目录
    sec_dir = _get_sec_dir(entry_path)
    progress_path = sec_dir / "progress.jsonl"
    
    # 进度追加函数
    def _progress_append(rec: Dict) -> None:
        try:
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            rec = dict(rec)
            rec.setdefault("timestamp", _dt.utcnow().isoformat() + "Z")
            line = _json.dumps(rec, ensure_ascii=False)
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
                    obj = _json.loads(line)
                except Exception:
                    continue
                if obj.get("event") == "task_status" and obj.get("status") == "done":
                    sig = obj.get("candidate_signature")
                    if sig:
                        done_sigs.add(sig)
        except Exception:
            pass
    
    return sec_dir, progress_path, _progress_append, done_sigs


def _load_or_run_heuristic_scan(
    entry_path: str,
    langs: List[str],
    exclude_dirs: Optional[List[str]],
    sec_dir,
    status_mgr,
    _progress_append,
) -> tuple[List[Dict], Dict]:
    """
    加载或运行启发式扫描。
    
    返回: (candidates, summary)
    """
    import json
    from pathlib import Path as _Path
    
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


def _compact_candidate(it: Dict) -> Dict:
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


def _prepare_candidates(candidates: List[Dict]) -> List[Dict]:
    """
    将候选问题精简为子任务清单，控制上下文长度，并分配全局唯一ID。
    
    返回: compact_candidates (已分配gid的候选列表)
    """
    compact_candidates = [_compact_candidate(it) for it in candidates]
    # 为所有候选分配全局唯一数字ID（gid: 1..N），用于跨批次/跨文件统一编号与跟踪
    for i, it in enumerate(compact_candidates, start=1):
        try:
            it["gid"] = i
        except Exception:
            pass
    
    return compact_candidates


def _load_existing_clusters(
    sec_dir,
    progress_path,
) -> tuple[Dict[tuple[str, int], List[Dict]], set]:
    """
    读取已有聚类报告以支持断点恢复。
    
    返回: (_existing_clusters, _completed_cluster_batches)
    """
    _existing_clusters: Dict[tuple[str, int], List[Dict]] = {}
    _completed_cluster_batches: set = set()
    
    try:
        from pathlib import Path as _Path2
        import json as _json
        _cluster_path = sec_dir / "cluster_report.jsonl"
        
        # 从 progress.jsonl 中读取已完成的聚类批次（优先检查）
        if progress_path.exists():
            try:
                for line in progress_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = _json.loads(line)
                    except Exception:
                        continue
                    # 检查 cluster_status 事件，status 为 "done" 表示已完成
                    if obj.get("event") == "cluster_status" and obj.get("status") == "done":
                        file_name = obj.get("file")
                        batch_idx = obj.get("batch_index")
                        if file_name and batch_idx:
                            _completed_cluster_batches.add((str(file_name), int(batch_idx)))
            except Exception:
                pass
        
        # 读取 cluster_report.jsonl（由于使用追加模式，可能有重复，需要去重）
        if _cluster_path.exists():
            try:
                # 使用字典去重：key 为 (file, batch_index, verification, gids 的字符串表示)
                seen_records: Dict[tuple, Dict] = {}
                with _cluster_path.open("r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        rec = _json.loads(line)
                        if not isinstance(rec, dict):
                            continue
                        f_name = str(rec.get("file") or "")
                        bidx = int(rec.get("batch_index", 1) or 1)
                        # 使用 gids 的排序后元组作为去重键
                        gids_list = rec.get("gids", [])
                        gids_key = tuple(sorted(gids_list)) if isinstance(gids_list, list) else ()
                        key = (f_name, bidx, str(rec.get("verification", "")), gids_key)
                        # 保留最新的记录（后写入的覆盖先写入的）
                        seen_records[key] = rec
                
                # 按 (file, batch_index) 分组
                for rec in seen_records.values():
                    f_name = str(rec.get("file") or "")
                    bidx = int(rec.get("batch_index", 1) or 1)
                    _existing_clusters.setdefault((f_name, bidx), []).append(rec)
            except Exception:
                _existing_clusters = {}
    except Exception:
        _existing_clusters = {}
        _completed_cluster_batches = set()
    
    return _existing_clusters, _completed_cluster_batches


def _restore_clusters_from_checkpoint(
    _existing_clusters: Dict[tuple[str, int], List[Dict]],
    _file_groups: Dict[str, List[Dict]],
) -> tuple[List[List[Dict]], List[Dict], List[Dict], set]:
    """
    从断点恢复聚类结果。
    
    返回: (cluster_batches, cluster_records, invalid_clusters_for_review, clustered_gids)
    """
    # 1. 收集所有候选的 gid
    all_candidate_gids_in_clustering = set()
    gid_to_candidate: Dict[int, Dict] = {}
    for _file, _items in _file_groups.items():
        for it in _items:
            try:
                _gid = int(it.get("gid", 0))
                if _gid >= 1:
                    all_candidate_gids_in_clustering.add(_gid)
                    gid_to_candidate[_gid] = it
            except Exception:
                pass
    
    # 2. 从 cluster_report.jsonl 恢复所有聚类结果
    clustered_gids = set()  # 已聚类的 gid（包括有效和无效的，因为无效的也需要进入复核阶段）
    invalid_clusters_for_review: List[Dict] = []  # 无效聚类列表（从断点恢复）
    cluster_batches: List[List[Dict]] = []
    cluster_records: List[Dict] = []
    
    for (_file_key, _batch_idx), cluster_recs in _existing_clusters.items():
        for rec in cluster_recs:
            gids_list = rec.get("gids", [])
            if not gids_list:
                continue
            is_invalid = rec.get("is_invalid", False)
            verification = str(rec.get("verification", "")).strip()
            members: List[Dict] = []
            for _gid in gids_list:
                try:
                    _gid_int = int(_gid)
                    if _gid_int >= 1 and _gid_int in gid_to_candidate:
                        # 只有当 gid 在当前运行中存在时，才恢复该聚类
                        candidate = gid_to_candidate[_gid_int]
                        candidate["verify"] = verification
                        members.append(candidate)
                        # 无论有效还是无效，都计入已聚类的 gid（避免被重新聚类）
                        clustered_gids.add(_gid_int)
                except Exception:
                    pass
            
            if members:
                if is_invalid:
                    # 无效聚类：收集到复核列表，不加入 cluster_batches
                    invalid_clusters_for_review.append({
                        "file": _file_key,
                        "batch_index": _batch_idx,
                        "gids": [m.get("gid") for m in members],
                        "verification": verification,
                        "invalid_reason": str(rec.get("invalid_reason", "")).strip(),
                        "members": members,  # 保存候选信息，用于复核后可能重新加入验证
                        "count": len(members),
                    })
                else:
                    # 有效聚类：恢复到 cluster_batches
                    cluster_batches.append(members)
                    cluster_records.append({
                        "file": _file_key,
                        "verification": verification,
                        "gids": [m.get("gid") for m in members],
                        "count": len(members),
                        "batch_index": _batch_idx,
                        "is_invalid": False,
                    })
    
    return cluster_batches, cluster_records, invalid_clusters_for_review, clustered_gids


def _get_review_system_prompt() -> str:
    """获取复核Agent的系统提示词"""
    return """
# 复核Agent约束
- 你的核心任务是复核聚类Agent给出的无效结论是否充分和正确。
- 你需要仔细检查聚类Agent提供的invalid_reason是否充分，是否真的考虑了所有可能的路径。
- 工具优先：使用 read_code 读取目标文件附近源码（行号前后各 ~50 行），必要时用 execute_script 辅助检索。
- 必要时需向上追溯调用者，查看完整的调用路径，以确认聚类Agent的结论是否成立。
- 禁止修改任何文件或执行写操作命令；仅进行只读分析与读取。
- 每次仅执行一个操作；等待工具结果后再进行下一步。
- **记忆使用**：
  - 在复核过程中，充分利用 retrieve_memory 工具检索已有的记忆，特别是与当前文件或函数相关的记忆。
  - 这些记忆可能包含函数的分析要点、指针判空情况、输入校验情况、调用路径分析结果等。
- **复核原则**：
  - 必须验证聚类Agent是否真的检查了所有可能的调用路径和调用者。
  - 必须验证聚类Agent是否真的确认了所有路径都有保护措施。
  - 如果发现聚类Agent遗漏了某些路径、调用者或边界情况，必须判定为理由不充分。
  - 保守策略：有疑问时，一律判定为理由不充分，将候选重新加入验证流程。
- 完成复核后，主输出仅打印结束符 <!!!COMPLETE!!!> ，不需要汇总结果。
    """.strip()


def _get_review_summary_prompt() -> str:
    """获取复核Agent的摘要提示词"""
    return """
请将本轮"复核结论"的结构化结果仅放入以下标记中，并使用 JSON 数组对象形式输出。
你需要复核聚类Agent给出的无效理由是否充分，是否真的考虑了所有可能的路径。

示例1：理由充分（is_reason_sufficient: true，单个gid）
<REPORT>
[
  {
    "gid": 1,
    "is_reason_sufficient": true,
    "review_notes": "聚类Agent已检查所有调用路径，确认所有调用者都有输入校验，理由充分"
  }
]
</REPORT>

示例2：理由充分（is_reason_sufficient: true，多个gid合并）
<REPORT>
[
  {
    "gids": [1, 2, 3],
    "is_reason_sufficient": true,
    "review_notes": "聚类Agent已检查所有调用路径，确认所有调用者都有输入校验，理由充分"
  }
]
</REPORT>

示例3：理由不充分（is_reason_sufficient: false）
<REPORT>
[
  {
    "gid": 1,
    "is_reason_sufficient": false,
    "review_notes": "聚类Agent遗漏了函数X的调用路径，该路径可能未做校验，理由不充分，需要重新验证"
  }
]
</REPORT>

要求：
- 只能在 <REPORT> 与 </REPORT> 中输出 JSON 数组，且不得出现其他文本。
- 数组元素为对象，包含字段：
  - gid: 整数（全局唯一编号，对应无效聚类的gid，单个告警时使用）
  - gids: 整数数组（全局唯一编号数组，对应无效聚类的gids，多个告警合并时使用）
  - is_reason_sufficient: 布尔值 (true/false)，表示无效理由是否充分
  - review_notes: 字符串（复核说明，解释为什么理由充分或不充分）
- **合并格式优化**：如果多个告警（gid）的复核结果（is_reason_sufficient）和复核说明（review_notes）完全一致，可以使用 gids 数组格式合并输出，减少重复内容。单个告警使用 gid，多个告警合并使用 gids。gid 和 gids 不能同时出现。
- 必须对所有输入的gid进行复核，不能遗漏。
- 如果理由不充分（is_reason_sufficient: false），该候选将重新加入验证流程；如果理由充分（is_reason_sufficient: true），该候选将被确认为无效。
- 支持json5语法（如尾随逗号、注释等）。
    """.strip()


def _build_review_task(review_batch: List[Dict], entry_path: str, langs: List[str]) -> str:
    """构建复核任务上下文"""
    import json as _json_review
    return f"""
# 复核无效聚类任务
上下文参数：
- entry_path: {entry_path}
- languages: {langs}

需要复核的无效聚类（JSON数组）：
{_json_review.dumps(review_batch, ensure_ascii=False, indent=2)}

请仔细复核每个无效聚类的invalid_reason是否充分，是否真的考虑了所有可能的路径、调用者和边界情况。
对于每个gid，请判断无效理由是否充分（is_reason_sufficient: true/false），并给出复核说明。
        """.strip()


def _create_review_agent(
    current_review_num: int,
    llm_group: Optional[str],
) -> Agent:
    """创建复核Agent"""
    review_system_prompt = _get_review_system_prompt()
    review_summary_prompt = _get_review_summary_prompt()
    
    review_task_id = f"JARVIS-SEC-Review-Batch-{current_review_num}"
    review_agent_kwargs: Dict = dict(
        system_prompt=review_system_prompt,
        name=review_task_id,
        auto_complete=True,
        need_summary=True,
        summary_prompt=review_summary_prompt,
        non_interactive=True,
        in_multi_agent=False,
        use_methodology=False,
        use_analysis=False,
        output_handler=[ToolRegistry()],
        use_tools=["read_code", "execute_script", "retrieve_memory", "save_memory"],
    )
    if llm_group:
        review_agent_kwargs["model_group"] = llm_group
    return Agent(**review_agent_kwargs)


def _process_review_batch_items(
    review_batch: List[Dict],
    review_results: Optional[List[Dict]],
    reviewed_clusters: List[Dict],
    reinstated_candidates: List[Dict],
) -> None:
    """处理单个复核批次的结果"""
    _process_review_batch(
        review_batch,
        review_results,
        reviewed_clusters,
        reinstated_candidates,
    )


def _reinstated_candidates_to_cluster_batches(
    reinstated_candidates: List[Dict],
    cluster_batches: List[List[Dict]],
    _progress_append,
) -> None:
    """将重新加入的候选添加到cluster_batches"""
    from collections import defaultdict as _dd2
    
    if not reinstated_candidates:
        return
    
    typer.secho(f"[jarvis-sec] 复核完成：{len(reinstated_candidates)} 个候选重新加入验证流程", fg=typer.colors.GREEN)
    # 按文件分组重新加入的候选
    reinstated_by_file: Dict[str, List[Dict]] = _dd2(list)
    for cand in reinstated_candidates:
        file_key = str(cand.get("file") or "")
        reinstated_by_file[file_key].append(cand)
    
    # 为每个文件的重新加入候选创建批次
    for file_key, cands in reinstated_by_file.items():
        if cands:
            cluster_batches.append(cands)
            _progress_append({
                "event": "review_reinstated",
                "file": file_key,
                "gids": [c.get("gid") for c in cands],
                "count": len(cands),
            })


def _process_review_phase(
    invalid_clusters_for_review: List[Dict],
    entry_path: str,
    langs: List[str],
    llm_group: Optional[str],
    status_mgr,
    _progress_append,
    cluster_batches: List[List[Dict]],
) -> List[List[Dict]]:
    """
    处理复核阶段：验证所有标记为无效的聚类。
    
    返回: 更新后的 cluster_batches（包含重新加入验证的候选）
    """
    if not invalid_clusters_for_review:
        typer.secho(f"[jarvis-sec] 无无效聚类需要复核", fg=typer.colors.BLUE)
        return cluster_batches
    
    typer.secho(f"\n[jarvis-sec] 开始复核 {len(invalid_clusters_for_review)} 个无效聚类...", fg=typer.colors.MAGENTA)
    status_mgr.update_review(
        current_review=0,
        total_reviews=len(invalid_clusters_for_review),
        message="开始复核无效聚类..."
    )
    
    # 按批次复核（每批最多10个无效聚类，避免上下文过长）
    review_batch_size = 10
    reviewed_clusters: List[Dict] = []
    reinstated_candidates: List[Dict] = []  # 重新加入验证的候选
    
    review_system_prompt = _get_review_system_prompt()
    review_summary_prompt = _get_review_summary_prompt()
    
    for review_idx in range(0, len(invalid_clusters_for_review), review_batch_size):
        review_batch = invalid_clusters_for_review[review_idx:review_idx + review_batch_size]
        current_review_num = review_idx // review_batch_size + 1
        total_review_batches = (len(invalid_clusters_for_review) + review_batch_size - 1) // review_batch_size
        
        typer.secho(f"[jarvis-sec] 复核批次 {current_review_num}/{total_review_batches}: {len(review_batch)} 个无效聚类", fg=typer.colors.CYAN)
        status_mgr.update_review(
            current_review=current_review_num,
            total_reviews=total_review_batches,
            message=f"正在复核批次 {current_review_num}/{total_review_batches}"
        )
        
        # 构建复核任务
        review_task = _build_review_task(review_batch, entry_path, langs)
        
        # 创建复核Agent
        review_agent = _create_review_agent(current_review_num, llm_group)
        
        # 订阅复核Agent的摘要
        review_summary_container = _subscribe_summary_event(review_agent)
        
        # 运行复核Agent（永久重试直到格式正确）
        review_results, parse_error = _run_review_agent_with_retry(
            review_agent,
            review_task,
            review_summary_prompt,
            entry_path,
            review_summary_container,
        )
        
        # 处理复核结果
        _process_review_batch_items(
            review_batch,
            review_results,
            reviewed_clusters,
            reinstated_candidates,
        )
    
    # 将重新加入验证的候选添加到cluster_batches
    _reinstated_candidates_to_cluster_batches(
        reinstated_candidates,
        cluster_batches,
        _progress_append,
    )
    
    if not reinstated_candidates:
        typer.secho(f"[jarvis-sec] 复核完成：所有无效聚类理由充分，确认为无效", fg=typer.colors.GREEN)
    
    # 记录复核结果
    _progress_append({
        "event": "review_completed",
        "total_reviewed": len(invalid_clusters_for_review),
        "reinstated": len(reinstated_candidates),
        "confirmed_invalid": len(invalid_clusters_for_review) - len(reinstated_candidates),
    })
    status_mgr.update_review(
        current_review=len(invalid_clusters_for_review),
        total_reviews=len(invalid_clusters_for_review),
        message=f"复核完成：{len(reinstated_candidates)} 个候选重新加入验证"
    )
    
    return cluster_batches


def _build_gid_to_review_mapping(review_results: List[Dict]) -> Dict[int, Dict]:
    """构建gid到复核结果的映射（支持 gid 和 gids 两种格式）"""
    gid_to_review: Dict[int, Dict] = {}
    for rr in review_results:
        if not isinstance(rr, dict):
            continue
        
        # 支持 gid 和 gids 两种格式
        gids_to_process: List[int] = []
        if "gids" in rr and isinstance(rr.get("gids"), list):
            # 合并格式：gids 数组
            for gid_val in rr.get("gids", []):
                try:
                    gid_int = int(gid_val)
                    if gid_int >= 1:
                        gids_to_process.append(gid_int)
                except Exception:
                    pass
        elif "gid" in rr:
            # 单个格式：gid
            try:
                gid_int = int(rr.get("gid", 0))
                if gid_int >= 1:
                    gids_to_process.append(gid_int)
            except Exception:
                pass
        
        # 为每个 gid 创建复核结果映射
        is_reason_sufficient = rr.get("is_reason_sufficient")
        review_notes = str(rr.get("review_notes", "")).strip()
        for gid in gids_to_process:
            gid_to_review[gid] = {
                "is_reason_sufficient": is_reason_sufficient,
                "review_notes": review_notes
            }
    return gid_to_review


def _process_review_batch(
    review_batch: List[Dict],
    review_results: Optional[List[Dict]],
    reviewed_clusters: List[Dict],
    reinstated_candidates: List[Dict],
) -> None:
    """处理单个复核批次的结果"""
    if review_results:
        # 构建gid到复核结果的映射
        gid_to_review = _build_gid_to_review_mapping(review_results)
        
        # 处理每个无效聚类
        for invalid_cluster in review_batch:
            cluster_gids = invalid_cluster.get("gids", [])
            cluster_members = invalid_cluster.get("members", [])
            
            # 检查该聚类中的所有gid的复核结果
            all_sufficient = True
            any_reviewed = False
            insufficient_review_result = None
            for gid in cluster_gids:
                review_result = gid_to_review.get(gid)
                if review_result:
                    any_reviewed = True
                    if review_result.get("is_reason_sufficient") is not True:
                        all_sufficient = False
                        if not insufficient_review_result:
                            insufficient_review_result = review_result
                        break
            
            if any_reviewed and not all_sufficient:
                # 理由不充分，重新加入验证流程
                typer.secho(f"[jarvis-sec] 复核结果：无效聚类（gids={cluster_gids}）理由不充分，重新加入验证流程", fg=typer.colors.BLUE)
                for member in cluster_members:
                    reinstated_candidates.append(member)
                reviewed_clusters.append({
                    **invalid_cluster,
                    "review_result": "reinstated",
                    "review_notes": insufficient_review_result.get("review_notes", "") if insufficient_review_result else "",
                })
            else:
                # 理由充分，确认无效
                review_notes = ""
                if cluster_gids and gid_to_review.get(cluster_gids[0]):
                    review_notes = gid_to_review[cluster_gids[0]].get("review_notes", "")
                typer.secho(f"[jarvis-sec] 复核结果：无效聚类（gids={cluster_gids}）理由充分，确认为无效", fg=typer.colors.GREEN)
                reviewed_clusters.append({
                    **invalid_cluster,
                    "review_result": "confirmed_invalid",
                    "review_notes": review_notes,
                })
    else:
        # 复核结果解析失败，保守策略：重新加入验证流程
        typer.secho(f"[jarvis-sec] 警告：复核结果解析失败，保守策略：将批次中的所有候选重新加入验证流程", fg=typer.colors.YELLOW)
        for invalid_cluster in review_batch:
            cluster_members = invalid_cluster.get("members", [])
            for member in cluster_members:
                reinstated_candidates.append(member)
            reviewed_clusters.append({
                **invalid_cluster,
                "review_result": "reinstated",
                "review_notes": "复核结果解析失败，保守策略重新加入验证",
            })


def _run_review_agent_with_retry(
    review_agent,
    review_task: str,
    review_summary_prompt: str,
    entry_path: str,
    review_summary_container: Dict[str, str],
) -> tuple[Optional[List[Dict]], Optional[str]]:
    """运行复核Agent并永久重试直到格式正确，返回(复核结果, 解析错误)"""
    use_direct_model_review = False
    prev_parse_error_review: Optional[str] = None
    review_attempt = 0
    
    while True:
        review_attempt += 1
        review_summary_container["text"] = ""
        
        if use_direct_model_review:
            # 格式校验失败后，直接调用模型接口
            review_summary_prompt_text = _build_verification_summary_prompt()
            error_guidance = ""
            if prev_parse_error_review:
                error_guidance = f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- JSON解析失败: {prev_parse_error_review}\n\n请确保输出的JSON格式正确，包括正确的引号、逗号、大括号等。仅输出一个 <REPORT> 块，块内直接包含 JSON 数组（不需要额外的标签）。支持json5语法（如尾随逗号、注释等）。"
            
            full_review_prompt = f"{review_task}{error_guidance}\n\n{review_summary_prompt_text}"
            try:
                review_response = review_agent.model.chat_until_success(full_review_prompt)  # type: ignore
                review_summary_container["text"] = review_response
            except Exception as e:
                try:
                    typer.secho(f"[jarvis-sec] 复核阶段直接模型调用失败: {e}，回退到 run()", fg=typer.colors.YELLOW)
                except Exception:
                    pass
                review_agent.run(review_task)
        else:
            review_agent.run(review_task)
        
        # 工作区保护
        try:
            _changed_review = _git_restore_if_dirty(entry_path)
            if _changed_review:
                try:
                    typer.secho(f"[jarvis-sec] 复核 Agent 工作区已恢复 ({_changed_review} 个文件）", fg=typer.colors.BLUE)
                except Exception:
                    pass
        except Exception:
            pass
        
        # 解析复核结果
        review_summary_text = review_summary_container.get("text", "")
        parse_error_review = None
        if review_summary_text:
            review_parsed, parse_error_review = _try_parse_summary_report(review_summary_text)
            if parse_error_review:
                prev_parse_error_review = parse_error_review
                try:
                    typer.secho(f"[jarvis-sec] 复核结果JSON解析失败: {parse_error_review}", fg=typer.colors.YELLOW)
                except Exception:
                    pass
            else:
                prev_parse_error_review = None
                if isinstance(review_parsed, list):
                    # 验证复核结果格式
                    if review_parsed and all(_is_valid_review_item(item) for item in review_parsed):
                        return review_parsed, None
        
        # 格式校验失败，后续重试使用直接模型调用
        use_direct_model_review = True
        if parse_error_review:
            try:
                typer.secho(f"[jarvis-sec] 复核结果JSON解析失败 -> 重试第 {review_attempt} 次 (使用直接模型调用，将反馈解析错误)", fg=typer.colors.YELLOW)
            except Exception:
                pass
        else:
            try:
                typer.secho(f"[jarvis-sec] 复核结果格式无效 -> 重试第 {review_attempt} 次 (使用直接模型调用)", fg=typer.colors.YELLOW)
            except Exception:
                pass


def _is_valid_review_item(item: Dict) -> bool:
    """验证复核结果项的格式"""
    if not isinstance(item, dict) or "is_reason_sufficient" not in item:
        return False
    has_gid = "gid" in item
    has_gids = "gids" in item
    if not has_gid and not has_gids:
        return False
    if has_gid and has_gids:
        return False  # gid 和 gids 不能同时出现
    if has_gid:
        try:
            return int(item["gid"]) >= 1
        except Exception:
            return False
    elif has_gids:
        if not isinstance(item["gids"], list) or len(item["gids"]) == 0:
            return False
        try:
            return all(int(gid_val) >= 1 for gid_val in item["gids"])
        except Exception:
            return False
    return False


def _load_processed_gids_from_issues(sec_dir) -> set:
    """从 agent_issues.jsonl 中读取已处理的 gid"""
    processed_gids = set()
    try:
        from pathlib import Path as _Path
        _agent_issues_path = sec_dir / "agent_issues.jsonl"
        if _agent_issues_path.exists():
            import json as _json
            with _agent_issues_path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        issue_obj = _json.loads(line)
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


def _count_issues_from_file(sec_dir) -> int:
    """从 agent_issues.jsonl 中读取当前问题总数（用于状态显示）"""
    count = 0
    try:
        from pathlib import Path as _Path
        import json as _json
        _agent_issues_path = sec_dir / "agent_issues.jsonl"
        if _agent_issues_path.exists():
            saved_gids = set()
            with _agent_issues_path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = _json.loads(line)
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


def _create_analysis_agent(task_id: str, llm_group: Optional[str], force_save_memory: bool = False) -> Agent:
    """创建分析Agent"""
    system_prompt = """
# 单Agent安全分析约束
- 你的核心任务是评估代码的安全问题，目标：针对本候选问题进行证据核实、风险评估与修复建议补充，查找漏洞触发路径，确认在某些条件下会触发；以此来判断是否是漏洞。
- **必须进行调用路径推导**：
  - 对于每个候选问题，必须明确推导从可控输入到缺陷代码的完整调用路径。
  - 调用路径推导必须包括：
    1. 识别可控输入的来源（例如：用户输入、网络数据、文件读取、命令行参数等）
    2. 追踪数据流：从输入源开始，逐步追踪数据如何传递到缺陷代码位置
    3. 识别调用链：明确列出从入口函数到缺陷代码的所有函数调用序列（例如：main() -> parse_input() -> process_data() -> vulnerable_function()）
    4. 分析每个调用点的数据校验情况：检查每个函数是否对输入进行了校验、边界检查或安全检查
    5. 确认触发条件：明确说明在什么条件下，未校验或恶意输入能够到达缺陷代码位置
  - 如果无法推导出完整的调用路径，或者所有调用路径都有充分的保护措施，则应该判定为误报。
  - 调用路径推导必须在分析过程中明确展示，不能省略或假设。
- 工具优先：使用 read_code 读取目标文件附近源码（行号前后各 ~50 行），必要时用 execute_script 辅助检索。
- **调用路径追溯要求**：
  - 必须向上追溯所有可能的调用者，查看完整的调用路径，以确认风险是否真实存在。
  - 使用 read_code 和 execute_script 工具查找函数的调用者（例如：使用 grep 搜索函数名，查找所有调用该函数的位置）。
  - 对于每个调用者，必须检查其是否对输入进行了校验。
  - 如果发现任何调用路径未做校验，必须明确记录该路径。
  - 例如：一个函数存在空指针解引用风险，必须检查所有调用者。如果所有调用者均能确保传入的指针非空，则该风险在当前代码库中可能不会实际触发；但如果存在任何调用者未做校验，则风险真实存在。
- 若多条告警位于同一文件且行号相距不远，可一次性读取共享上下文，对这些相邻告警进行联合分析与判断；但仍需避免无关扩展与大范围遍历。
- 禁止修改任何文件或执行写操作命令（rm/mv/cp/echo >、sed -i、git、patch、chmod、chown 等）；仅进行只读分析与读取。
- 每次仅执行一个操作；等待工具结果后再进行下一步。
- **记忆使用**：
  - 在分析过程中，充分利用 retrieve_memory 工具检索已有的记忆，特别是与当前分析函数相关的记忆。
  - 如果有必要，使用 save_memory 工具保存每个函数的分析要点，使用函数名作为 tag（例如：函数名、文件名等）。
  - 记忆内容示例：某个函数的指针已经判空、某个函数已有输入校验、某个函数的调用路径分析结果等。
  - 这样可以避免重复分析，提高效率，并保持分析的一致性。
- 完成对本批次候选问题的判断后，主输出仅打印结束符 <!!!COMPLETE!!!> ，不需要汇总结果。
""".strip()
    
    agent_kwargs: Dict = dict(
        system_prompt=system_prompt,
        name=task_id,
        auto_complete=True,
        need_summary=True,
        summary_prompt=_build_summary_prompt(),
        non_interactive=True,
        in_multi_agent=False,
        use_methodology=False,
        use_analysis=False,
        output_handler=[ToolRegistry()],
        force_save_memory=force_save_memory,
        use_tools=["read_code", "execute_script", "save_memory", "retrieve_memory"],
    )
    if llm_group:
        agent_kwargs["model_group"] = llm_group
    return Agent(**agent_kwargs)


def _build_analysis_task_context(batch: List[Dict], entry_path: str, langs: List[str]) -> str:
    """构建分析任务上下文"""
    import json as _json2
    batch_ctx: List[Dict] = list(batch)
    cluster_verify = str(batch_ctx[0].get("verify") if batch_ctx else "")
    cluster_gids_ctx = [it.get("gid") for it in batch_ctx]
    return f"""
# 安全子任务批次
上下文参数：
- entry_path: {entry_path}
- languages: {langs}
- cluster_verification: {cluster_verify}

- cluster_gids: {cluster_gids_ctx}
- note: 每个候选含 gid/verify 字段，模型仅需输出 gid 统一给出验证/判断结论（全局编号）；无需使用局部 id

批次候选(JSON数组):
{_json2.dumps(batch_ctx, ensure_ascii=False, indent=2)}
""".strip()


def _subscribe_summary_event(agent: Agent) -> Dict[str, str]:
    """订阅Agent摘要事件"""
    summary_container: Dict[str, str] = {"text": ""}
    try:
        from jarvis.jarvis_agent.events import AFTER_SUMMARY as _AFTER_SUMMARY
    except Exception:
        _AFTER_SUMMARY = None
    
    if _AFTER_SUMMARY:
        def _on_after_summary(**kwargs):
            try:
                summary_container["text"] = str(kwargs.get("summary", "") or "")
            except Exception:
                summary_container["text"] = ""
        try:
            agent.event_bus.subscribe(_AFTER_SUMMARY, _on_after_summary)
        except Exception:
            pass
    return summary_container


def _build_validation_error_guidance(
    parse_error_analysis: Optional[str],
    prev_parsed_items: Optional[List],
) -> str:
    """构建验证错误指导信息"""
    if parse_error_analysis:
        return f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- JSON解析失败: {parse_error_analysis}\n\n请确保输出的JSON格式正确，包括正确的引号、逗号、大括号等。仅输出一个 <REPORT> 块，块内直接包含 JSON 数组（不需要额外的标签）。支持json5语法（如尾随逗号、注释等）。"
    elif prev_parsed_items is None:
        return "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- 无法从摘要中解析出有效的 JSON 数组"
    elif not _valid_items(prev_parsed_items):
        validation_errors = []
        if not isinstance(prev_parsed_items, list):
            validation_errors.append("结果不是数组")
        else:
            for idx, it in enumerate(prev_parsed_items):
                if not isinstance(it, dict):
                    validation_errors.append(f"元素{idx}不是字典")
                    break
                has_gid = "gid" in it
                has_gids = "gids" in it
                if not has_gid and not has_gids:
                    validation_errors.append(f"元素{idx}缺少必填字段 gid 或 gids")
                    break
                if has_gid and has_gids:
                    validation_errors.append(f"元素{idx}不能同时包含 gid 和 gids")
                    break
                if has_gid:
                    try:
                        if int(it.get("gid", 0)) < 1:
                            validation_errors.append(f"元素{idx}的 gid 必须 >= 1")
                            break
                    except Exception:
                        validation_errors.append(f"元素{idx}的 gid 格式错误（必须是整数）")
                        break
                elif has_gids:
                    if not isinstance(it.get("gids"), list) or len(it.get("gids", [])) == 0:
                        validation_errors.append(f"元素{idx}的 gids 必须是非空数组")
                        break
                    try:
                        for gid_idx, gid_val in enumerate(it.get("gids", [])):
                            if int(gid_val) < 1:
                                validation_errors.append(f"元素{idx}的 gids[{gid_idx}] 必须 >= 1")
                                break
                        if validation_errors:
                            break
                    except Exception:
                        validation_errors.append(f"元素{idx}的 gids 格式错误（必须是整数数组）")
                        break
                if "has_risk" not in it or not isinstance(it.get("has_risk"), bool):
                    validation_errors.append(f"元素{idx}缺少必填字段 has_risk（必须是布尔值）")
                    break
                if it.get("has_risk"):
                    for key in ["preconditions", "trigger_path", "consequences", "suggestions"]:
                        if key not in it:
                            validation_errors.append(f"元素{idx}的 has_risk 为 true，但缺少必填字段 {key}")
                            break
                        if not isinstance(it[key], str) or not it[key].strip():
                            validation_errors.append(f"元素{idx}的 {key} 字段不能为空")
                            break
                    if validation_errors:
                        break
        if validation_errors:
            return "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n" + "\n".join(f"- {err}" for err in validation_errors)
    return ""


def _run_analysis_agent_with_retry(
    agent: Agent,
    per_task: str,
    summary_container: Dict[str, str],
    entry_path: str,
    task_id: str,
    bidx: int,
    meta_records: List[Dict],
) -> tuple[Optional[List[Dict]], Optional[Dict]]:
    """运行分析Agent并重试直到成功"""
    summary_items: Optional[List[Dict]] = None
    workspace_restore_info: Optional[Dict] = None
    use_direct_model_analysis = False
    prev_parsed_items: Optional[List] = None
    parse_error_analysis: Optional[str] = None
    attempt = 0
    
    while True:
        attempt += 1
        summary_container["text"] = ""
        
        if use_direct_model_analysis:
            summary_prompt_text = _build_summary_prompt()
            error_guidance = _build_validation_error_guidance(parse_error_analysis, prev_parsed_items)
            full_prompt = f"{per_task}{error_guidance}\n\n{summary_prompt_text}"
            try:
                response = agent.model.chat_until_success(full_prompt)  # type: ignore
                summary_container["text"] = response
            except Exception as e:
                try:
                    typer.secho(f"[jarvis-sec] 直接模型调用失败: {e}，回退到 run()", fg=typer.colors.YELLOW)
                except Exception:
                    pass
                agent.run(per_task)
        else:
            agent.run(per_task)

        # 工作区保护
        try:
            _changed = _git_restore_if_dirty(entry_path)
            workspace_restore_info = {
                "performed": bool(_changed),
                "changed_files_count": int(_changed or 0),
                "action": "git checkout -- .",
            }
            meta_records.append({
                "task_id": task_id,
                "batch_index": bidx,
                "workspace_restore": workspace_restore_info,
                "attempt": attempt + 1,
            })
            if _changed:
                try:
                    typer.secho(f"[jarvis-sec] 工作区已恢复 ({_changed} 个文件），操作: git checkout -- .", fg=typer.colors.BLUE)
                except Exception:
                    pass
        except Exception:
            pass

        # 解析摘要中的 <REPORT>（JSON）
        summary_text = summary_container.get("text", "")
        parsed_items: Optional[List] = None
        parse_error_analysis = None
        if summary_text:
            rep, parse_error_analysis = _try_parse_summary_report(summary_text)
            if parse_error_analysis:
                try:
                    typer.secho(f"[jarvis-sec] 分析结果JSON解析失败: {parse_error_analysis}", fg=typer.colors.YELLOW)
                except Exception:
                    pass
            elif isinstance(rep, list):
                parsed_items = rep
            elif isinstance(rep, dict):
                items = rep.get("issues")
                if isinstance(items, list):
                    parsed_items = items

        # 关键字段校验
        # 空数组 [] 是有效的（表示没有发现问题），需要单独处理
        if parsed_items is not None:
            if len(parsed_items) == 0:
                # 空数组表示没有发现问题，这是有效的格式
                summary_items = parsed_items
                break
            elif _valid_items(parsed_items):
                # 非空数组需要验证格式
                summary_items = parsed_items
                break
        
        # 格式校验失败，后续重试使用直接模型调用
        use_direct_model_analysis = True
        prev_parsed_items = parsed_items
        if parse_error_analysis:
            try:
                typer.secho(f"[jarvis-sec] 分析结果JSON解析失败 -> 重试第 {attempt} 次 (批次={bidx}，使用直接模型调用，将反馈解析错误)", fg=typer.colors.YELLOW)
            except Exception:
                pass
        else:
            try:
                typer.secho(f"[jarvis-sec] 分析结果格式无效 -> 重试第 {attempt} 次 (批次={bidx}，使用直接模型调用)", fg=typer.colors.YELLOW)
            except Exception:
                pass
    
    return summary_items, workspace_restore_info


def _expand_and_filter_analysis_results(summary_items: List[Dict]) -> tuple[List[Dict], List[Dict]]:
    """展开gids格式为单个gid格式，并过滤出有风险的项目"""
    items_with_risk: List[Dict] = []
    items_without_risk: List[Dict] = []
    merged_items: List[Dict] = []
    
    for it in summary_items:
        has_risk = it.get("has_risk") is True
        if "gids" in it and isinstance(it.get("gids"), list):
            for gid_val in it.get("gids", []):
                try:
                    gid_int = int(gid_val)
                    if gid_int >= 1:
                        item = {
                            **{k: v for k, v in it.items() if k != "gids"},
                            "gid": gid_int,
                        }
                        if has_risk:
                            merged_items.append(item)
                            items_with_risk.append(item)
                        else:
                            items_without_risk.append(item)
                except Exception:
                    pass
        elif "gid" in it:
            if has_risk:
                merged_items.append(it)
                items_with_risk.append(it)
            else:
                items_without_risk.append(it)
    
    return items_with_risk, items_without_risk


def _build_gid_to_verification_mapping(verification_results: List[Dict]) -> Dict[int, Dict]:
    """构建gid到验证结果的映射"""
    gid_to_verification: Dict[int, Dict] = {}
    for vr in verification_results:
        if not isinstance(vr, dict):
            continue
        gids_to_process: List[int] = []
        if "gids" in vr and isinstance(vr.get("gids"), list):
            for gid_val in vr.get("gids", []):
                try:
                    gid_int = int(gid_val)
                    if gid_int >= 1:
                        gids_to_process.append(gid_int)
                except Exception as e:
                    try:
                        typer.secho(f"[jarvis-sec] 警告：验证结果中 gids 数组元素格式错误: {gid_val}, 错误: {e}", fg=typer.colors.YELLOW)
                    except Exception:
                        pass
        elif "gid" in vr:
            try:
                gid_val = vr.get("gid", 0)
                gid_int = int(gid_val)
                if gid_int >= 1:
                    gids_to_process.append(gid_int)
                else:
                    try:
                        typer.secho(f"[jarvis-sec] 警告：验证结果中 gid 值无效: {gid_val} (必须 >= 1)", fg=typer.colors.YELLOW)
                    except Exception:
                        pass
            except Exception as e:
                try:
                    typer.secho(f"[jarvis-sec] 警告：验证结果中 gid 格式错误: {vr.get('gid')}, 错误: {e}", fg=typer.colors.YELLOW)
                except Exception:
                    pass
        else:
            try:
                typer.secho(f"[jarvis-sec] 警告：验证结果项缺少 gid 或 gids 字段: {vr}", fg=typer.colors.YELLOW)
            except Exception:
                pass
        
        is_valid = vr.get("is_valid")
        verification_notes = str(vr.get("verification_notes", "")).strip()
        for gid in gids_to_process:
            gid_to_verification[gid] = {
                "is_valid": is_valid,
                "verification_notes": verification_notes
            }
    return gid_to_verification


def _merge_verified_items(
    items_with_risk: List[Dict],
    batch: List[Dict],
    gid_to_verification: Dict[int, Dict],
) -> List[Dict]:
    """合并验证通过的告警"""
    gid_to_candidate: Dict[int, Dict] = {}
    for c in batch:
        try:
            c_gid = int(c.get("gid", 0))
            if c_gid >= 1:
                gid_to_candidate[c_gid] = c
        except Exception:
            pass
    
    verified_items: List[Dict] = []
    for item in items_with_risk:
        item_gid = int(item.get("gid", 0))
        verification = gid_to_verification.get(item_gid)
        if verification and verification.get("is_valid") is True:
            # 合并原始候选信息（file, line, pattern, category, language, evidence, confidence, severity 等）
            candidate = gid_to_candidate.get(item_gid, {})
            merged_item = {
                **candidate,  # 原始候选信息
                **item,  # 分析结果
                "verification_notes": str(verification.get("verification_notes", "")).strip(),
            }
            verified_items.append(merged_item)
        elif verification and verification.get("is_valid") is False:
            try:
                typer.secho(f"[jarvis-sec] 验证 Agent 判定 gid={item_gid} 为误报: {verification.get('verification_notes', '')}", fg=typer.colors.BLUE)
            except Exception:
                pass
        else:
            try:
                typer.secho(f"[jarvis-sec] 警告：验证结果中未找到 gid={item_gid}，视为验证不通过", fg=typer.colors.YELLOW)
            except Exception:
                pass
    return verified_items


def _merge_verified_items_without_verification(
    items_with_risk: List[Dict],
    batch: List[Dict],
) -> List[Dict]:
    """合并分析Agent确认的问题（不进行二次验证）"""
    gid_to_candidate: Dict[int, Dict] = {}
    for c in batch:
        try:
            c_gid = int(c.get("gid", 0))
            if c_gid >= 1:
                gid_to_candidate[c_gid] = c
        except Exception:
            pass
    
    verified_items: List[Dict] = []
    for item in items_with_risk:
        item_gid = int(item.get("gid", 0))
        # 处理 gids 数组的情况
        if "gids" in item:
            gids = item.get("gids", [])
            for gid in gids:
                candidate = gid_to_candidate.get(gid, {})
                merged_item = {
                    **candidate,  # 原始候选信息
                    **item,  # 分析结果
                    "gid": gid,  # 使用单个 gid
                    "verification_notes": "未进行二次验证（--no-verification）",
                }
                # 移除 gids 字段，因为已经展开为单个 gid
                merged_item.pop("gids", None)
                verified_items.append(merged_item)
        else:
            # 单个 gid 的情况
            candidate = gid_to_candidate.get(item_gid, {})
            merged_item = {
                **candidate,  # 原始候选信息
                **item,  # 分析结果
                "verification_notes": "未进行二次验证（--no-verification）",
            }
            verified_items.append(merged_item)
    return verified_items


def _process_verification_batch(
    batch: List[Dict],
    bidx: int,
    total_batches: int,
    entry_path: str,
    langs: List[str],
    llm_group: Optional[str],
    status_mgr,
    _progress_append,
    _append_report,
    meta_records: List[Dict],
    gid_counts: Dict[int, int],
    sec_dir,
    enable_verification: bool = True,
    force_save_memory: bool = False,
) -> None:
    """
    处理单个验证批次。
    
    参数:
    - batch: 当前批次的候选列表
    - bidx: 批次索引
    - total_batches: 总批次数
    - 其他参数用于状态管理和结果收集
    """
    task_id = f"JARVIS-SEC-Batch-{bidx}"
    batch_file = batch[0].get("file") if batch else None
    
    # 进度：批次开始
    _progress_append(
        {
            "event": "batch_status",
            "status": "running",
            "batch_id": task_id,
            "batch_index": bidx,
            "total_batches": total_batches,
            "batch_size": len(batch),
            "file": batch_file,
        }
    )
    # 更新验证阶段进度
    status_mgr.update_verification(
        current_batch=bidx,
        total_batches=total_batches,
        batch_id=task_id,
        file_name=batch_file,
        message=f"正在验证批次 {bidx}/{total_batches}"
    )

    # 显示进度
    try:
        typer.secho(f"\n[jarvis-sec] 分析批次 {bidx}/{total_batches}: 大小={len(batch)} 文件='{batch_file}'", fg=typer.colors.CYAN)
    except Exception:
        pass

    # 创建分析Agent
    agent = _create_analysis_agent(task_id, llm_group, force_save_memory=force_save_memory)
    
    # 构建任务上下文
    per_task = _build_analysis_task_context(batch, entry_path, langs)
    
    # 订阅摘要事件
    summary_container = _subscribe_summary_event(agent)
    
    # 运行分析Agent并重试
    summary_items, workspace_restore_info = _run_analysis_agent_with_retry(
        agent, per_task, summary_container, entry_path, task_id, bidx, meta_records
    )
    
    # 处理分析结果
    parse_fail = summary_items is None
    verified_items: List[Dict] = []
    
    if summary_items:
        # 展开并过滤分析结果
        items_with_risk, items_without_risk = _expand_and_filter_analysis_results(summary_items)
        
        # 记录无风险项目的日志
        if items_without_risk:
            try:
                typer.secho(f"[jarvis-sec] 批次 {bidx}/{total_batches} 分析 Agent 判定 {len(items_without_risk)} 个候选为无风险（has_risk: false），跳过验证", fg=typer.colors.BLUE)
            except Exception:
                pass
        
        # 运行验证Agent（仅当分析Agent发现有风险的问题时，且启用二次验证）
        if items_with_risk:
            if not enable_verification:
                # 如果关闭二次验证，直接将分析Agent确认的问题作为已验证的问题
                verified_items = _merge_verified_items_without_verification(items_with_risk, batch)
                if verified_items:
                    for item in verified_items:
                        gid = int(item.get("gid", 0))
                        if gid >= 1:
                            gid_counts[gid] = gid_counts.get(gid, 0) + 1
                    typer.secho(f"[jarvis-sec] 批次 {bidx}/{total_batches} 跳过验证，直接写入: 数量={len(verified_items)}", fg=typer.colors.GREEN)
                    _append_report(verified_items, "analysis_only", task_id, {"batch": True, "candidates": batch})
                    current_count = _count_issues_from_file(sec_dir)
                    status_mgr.update_verification(
                        current_batch=bidx,
                        total_batches=total_batches,
                        issues_found=current_count,
                        message=f"已处理 {bidx}/{total_batches} 批次，发现 {current_count} 个问题（未验证）"
                    )
            else:
                # 启用二次验证，运行验证Agent
                # 创建验证 Agent 来验证分析 Agent 的结论
                verification_system_prompt = """
# 验证 Agent 约束
- 你的核心任务是验证分析 Agent 给出的安全结论是否正确。
- 你需要仔细检查分析 Agent 给出的前置条件、触发路径、后果和建议是否合理、准确。
- 工具优先：使用 read_code 读取目标文件附近源码（行号前后各 ~50 行），必要时用 execute_script 辅助检索。
- 必要时需向上追溯调用者，查看完整的调用路径，以确认分析 Agent 的结论是否成立。
- 禁止修改任何文件或执行写操作命令；仅进行只读分析与读取。
- 每次仅执行一个操作；等待工具结果后再进行下一步。
- **记忆使用**：
  - 在验证过程中，充分利用 retrieve_memory 工具检索已有的记忆，特别是分析 Agent 保存的与当前验证函数相关的记忆。
  - 这些记忆可能包含函数的分析要点、指针判空情况、输入校验情况、调用路径分析结果等，可以帮助你更准确地验证分析结论。
  - 如果发现分析 Agent 的结论与记忆中的信息不一致，需要仔细核实。
- 完成验证后，主输出仅打印结束符 <!!!COMPLETE!!!> ，不需要汇总结果。
""".strip()
                
                verification_task_id = f"JARVIS-SEC-Verify-Batch-{bidx}"
                verification_agent_kwargs: Dict = dict(
                    system_prompt=verification_system_prompt,
                    name=verification_task_id,
                    auto_complete=True,
                    need_summary=True,
                    summary_prompt=_build_verification_summary_prompt(),
                    non_interactive=True,
                    in_multi_agent=False,
                    use_methodology=False,
                    use_analysis=False,
                    output_handler=[ToolRegistry()],
                    use_tools=["read_code", "execute_script", "retrieve_memory"],
                )
                if llm_group:
                    verification_agent_kwargs["model_group"] = llm_group
                verification_agent = Agent(**verification_agent_kwargs)
                
                # 构造验证任务上下文
                import json as _json3
                verification_task = f"""
# 验证分析结论任务
上下文参数：
- entry_path: {entry_path}
- languages: {langs}

分析 Agent 给出的结论（需要验证，仅包含 has_risk: true 的项目）：
{_json3.dumps(items_with_risk, ensure_ascii=False, indent=2)}

请验证上述分析结论是否正确，包括：
1. 前置条件（preconditions）是否合理
2. 触发路径（trigger_path）是否成立
3. 后果（consequences）评估是否准确
4. 建议（suggestions）是否合适

对于每个 gid，请判断分析结论是否正确（is_valid: true/false），并给出验证说明。
""".strip()
                
                # 订阅验证 Agent 的摘要
                verification_summary_container = _subscribe_summary_event(verification_agent)
                
                verification_results, verification_parse_error = _run_verification_agent_with_retry(
                    verification_agent,
                    verification_task,
                    _build_verification_summary_prompt(),
                    entry_path,
                    verification_summary_container,
                    bidx,
                )
                
                # 调试日志：显示验证结果
                if verification_results is None:
                    try:
                        typer.secho(f"[jarvis-sec] 警告：验证 Agent 返回 None，可能解析失败", fg=typer.colors.YELLOW)
                    except Exception:
                        pass
                elif not isinstance(verification_results, list):
                    try:
                        typer.secho(f"[jarvis-sec] 警告：验证 Agent 返回类型错误，期望 list，实际: {type(verification_results)}", fg=typer.colors.YELLOW)
                    except Exception:
                        pass
                elif len(verification_results) == 0:
                    try:
                        typer.secho(f"[jarvis-sec] 警告：验证 Agent 返回空列表", fg=typer.colors.YELLOW)
                    except Exception:
                        pass
                else:
                    try:
                        typer.secho(f"[jarvis-sec] 验证 Agent 返回 {len(verification_results)} 个结果项", fg=typer.colors.BLUE)
                    except Exception:
                        pass
                
                # 根据验证结果筛选：只保留验证通过（is_valid: true）的告警
                if verification_results:
                    gid_to_verification = _build_gid_to_verification_mapping(verification_results)
                    
                    # 调试日志：显示提取到的验证结果
                    if gid_to_verification:
                        try:
                            typer.secho(f"[jarvis-sec] 从验证结果中提取到 {len(gid_to_verification)} 个 gid: {sorted(gid_to_verification.keys())}", fg=typer.colors.BLUE)
                        except Exception:
                            pass
                    else:
                        try:
                            typer.secho(f"[jarvis-sec] 警告：验证结果解析成功，但未提取到任何有效的 gid。验证结果: {verification_results}", fg=typer.colors.YELLOW)
                        except Exception:
                            pass
                    
                    # 合并验证通过的告警
                    verified_items = _merge_verified_items(items_with_risk, batch, gid_to_verification)
                else:
                    typer.secho(f"[jarvis-sec] 警告：验证 Agent 结果解析失败，不保留任何告警（保守策略）", fg=typer.colors.YELLOW)
                
                # 只有验证通过的告警才写入文件
                if verified_items:
                    for item in verified_items:
                        gid = int(item.get("gid", 0))
                        if gid >= 1:
                            gid_counts[gid] = gid_counts.get(gid, 0) + 1
                    typer.secho(f"[jarvis-sec] 批次 {bidx}/{total_batches} 验证通过: 数量={len(verified_items)}/{len(items_with_risk)} -> 写入文件", fg=typer.colors.GREEN)
                    _append_report(verified_items, "verified", task_id, {"batch": True, "candidates": batch})
                    # 从文件读取当前总数（用于状态显示）
                    current_count = _count_issues_from_file(sec_dir)
                    status_mgr.update_verification(
                        current_batch=bidx,
                        total_batches=total_batches,
                        issues_found=current_count,
                        message=f"已验证 {bidx}/{total_batches} 批次，发现 {current_count} 个问题（验证通过）"
                    )
                else:
                    typer.secho(f"[jarvis-sec] 批次 {bidx}/{total_batches} 验证后无有效告警: 分析 Agent 发现 {len(items_with_risk)} 个有风险的问题，验证后全部不通过", fg=typer.colors.BLUE)
                    current_count = _count_issues_from_file(sec_dir)
                    status_mgr.update_verification(
                        current_batch=bidx,
                        total_batches=total_batches,
                        issues_found=current_count,
                        message=f"已验证 {bidx}/{total_batches} 批次，验证后无有效告警"
                    )
        elif parse_fail:
            typer.secho(f"[jarvis-sec] 批次 {bidx}/{total_batches} 解析失败 (摘要中无 <REPORT> 或字段无效)", fg=typer.colors.YELLOW)
        else:
            typer.secho(f"[jarvis-sec] 批次 {bidx}/{total_batches} 未发现问题", fg=typer.colors.BLUE)
            current_count = _count_issues_from_file(sec_dir)
            status_mgr.update_verification(
                current_batch=bidx,
                total_batches=total_batches,
                issues_found=current_count,
                message=f"已验证 {bidx}/{total_batches} 批次"
            )

    # 为本批次所有候选写入 done 记录
    for c in batch:
        sig = _sig_of(c)
        try:
            c_gid = int(c.get("gid", 0))
        except Exception:
            c_gid = 0
        cnt = gid_counts.get(c_gid, 0)
        _progress_append({
            "event": "task_status",
            "status": "done",
            "task_id": task_id,
            "candidate_signature": sig,
            "candidate": c,
            "issues_count": int(cnt),
            "parse_fail": parse_fail,
            "workspace_restore": workspace_restore_info,
            "batch_index": bidx,
        })

    # 批次结束记录
    _progress_append({
        "event": "batch_status",
        "status": "done",
        "batch_id": task_id,
        "batch_index": bidx,
        "total_batches": total_batches,
        "issues_count": len(verified_items),
        "parse_fail": parse_fail,
    })


def _valid_items(items: Optional[List]) -> bool:
    """验证分析结果项的格式"""
    if not isinstance(items, list):
        return False
    for it in items:
        if not isinstance(it, dict):
            return False
        has_gid = "gid" in it
        has_gids = "gids" in it
        if not has_gid and not has_gids:
            return False
        if has_gid and has_gids:
            return False
        if has_gid:
            try:
                if int(it["gid"]) < 1:
                    return False
            except Exception:
                return False
        elif has_gids:
            if not isinstance(it["gids"], list) or len(it["gids"]) == 0:
                return False
            for gid_val in it["gids"]:
                try:
                    if int(gid_val) < 1:
                        return False
                except Exception:
                    return False
        if "has_risk" not in it or not isinstance(it["has_risk"], bool):
            return False
        if it.get("has_risk"):
            for key in ["preconditions", "trigger_path", "consequences", "suggestions"]:
                if key not in it:
                    return False
                if not isinstance(it[key], str) or not it[key].strip():
                    return False
    return True


def _is_valid_verification_item(item: Dict) -> bool:
    """验证验证结果项的格式"""
    if not isinstance(item, dict) or "is_valid" not in item:
        return False
    has_gid = "gid" in item
    has_gids = "gids" in item
    if not has_gid and not has_gids:
        return False
    if has_gid and has_gids:
        return False  # gid 和 gids 不能同时出现
    if has_gid:
        try:
            return int(item["gid"]) >= 1
        except Exception:
            return False
    elif has_gids:
        if not isinstance(item["gids"], list) or len(item["gids"]) == 0:
            return False
        try:
            return all(int(gid_val) >= 1 for gid_val in item["gids"])
        except Exception:
            return False
    return False


def _run_verification_agent_with_retry(
    verification_agent,
    verification_task: str,
    verification_summary_prompt: str,
    entry_path: str,
    verification_summary_container: Dict[str, str],
    bidx: int,
) -> tuple[Optional[List[Dict]], Optional[str]]:
    """运行验证Agent并永久重试直到格式正确，返回(验证结果, 解析错误)"""
    use_direct_model_verify = False
    prev_parse_error_verify: Optional[str] = None
    verify_attempt = 0
    
    while True:
        verify_attempt += 1
        verification_summary_container["text"] = ""
        
        if use_direct_model_verify:
            verification_summary_prompt_text = _build_verification_summary_prompt()
            error_guidance = ""
            if prev_parse_error_verify:
                error_guidance = f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- JSON解析失败: {prev_parse_error_verify}\n\n请确保输出的JSON格式正确，包括正确的引号、逗号、大括号等。仅输出一个 <REPORT> 块，块内直接包含 JSON 数组（不需要额外的标签）。支持json5语法（如尾随逗号、注释等）。"
            
            full_verify_prompt = f"{verification_task}{error_guidance}\n\n{verification_summary_prompt_text}"
            try:
                verify_response = verification_agent.model.chat_until_success(full_verify_prompt)  # type: ignore
                verification_summary_container["text"] = verify_response
            except Exception as e:
                try:
                    typer.secho(f"[jarvis-sec] 验证阶段直接模型调用失败: {e}，回退到 run()", fg=typer.colors.YELLOW)
                except Exception:
                    pass
                verification_agent.run(verification_task)
        else:
            verification_agent.run(verification_task)
        
        # 工作区保护
        try:
            _changed_verify = _git_restore_if_dirty(entry_path)
            if _changed_verify:
                try:
                    typer.secho(f"[jarvis-sec] 验证 Agent 工作区已恢复 ({_changed_verify} 个文件）", fg=typer.colors.BLUE)
                except Exception:
                    pass
        except Exception:
            pass
        
        # 解析验证结果
        verification_summary_text = verification_summary_container.get("text", "")
        parse_error_verify = None
        if verification_summary_text:
            verification_parsed, parse_error_verify = _try_parse_summary_report(verification_summary_text)
            if parse_error_verify:
                prev_parse_error_verify = parse_error_verify
                try:
                    typer.secho(f"[jarvis-sec] 验证结果JSON解析失败: {parse_error_verify}", fg=typer.colors.YELLOW)
                except Exception:
                    pass
            else:
                prev_parse_error_verify = None
                if isinstance(verification_parsed, list):
                    if verification_parsed and all(_is_valid_verification_item(item) for item in verification_parsed):
                        return verification_parsed, None
        
        # 格式校验失败，后续重试使用直接模型调用
        use_direct_model_verify = True
        if parse_error_verify:
            try:
                typer.secho(f"[jarvis-sec] 验证结果JSON解析失败 -> 重试第 {verify_attempt} 次 (批次={bidx}，使用直接模型调用，将反馈解析错误)", fg=typer.colors.YELLOW)
            except Exception:
                pass
        else:
            try:
                typer.secho(f"[jarvis-sec] 验证结果格式无效 -> 重试第 {verify_attempt} 次 (批次={bidx}，使用直接模型调用)", fg=typer.colors.YELLOW)
            except Exception:
                pass


def run_security_analysis(
    entry_path: str,
    languages: Optional[List[str]] = None,
    llm_group: Optional[str] = None,
    report_file: Optional[str] = None,
    cluster_limit: int = 50,
    exclude_dirs: Optional[List[str]] = None,
    enable_verification: bool = True,
    force_save_memory: bool = False,
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
    - 断点续扫: 默认开启。会基于 .jarvis/sec/progress.jsonl 和 .jarvis/sec/heuristic_issues.jsonl 文件进行状态恢复。
    """
    import json

    langs = languages or ["c", "cpp", "h", "hpp", "rs"]

    # 状态管理器（结构化进度状态文件）
    from jarvis.jarvis_sec.status import StatusManager
    status_mgr = StatusManager(entry_path)
    
    # 尝试从状态文件恢复并显示当前状态
    try:
        current_status = status_mgr.get_status()
        if current_status:
            stage = current_status.get("stage", "unknown")
            progress = current_status.get("progress", 0)
            message = current_status.get("message", "")
            typer.secho(f"[jarvis-sec] 从状态文件恢复: 阶段={stage}, 进度={progress}%, {message}", fg=typer.colors.BLUE)
    except Exception:
        pass

    # 初始化分析上下文
    sec_dir, progress_path, _progress_append, done_sigs = _initialize_analysis_context(
        entry_path, status_mgr
    )

    # 1) 启发式扫描（支持断点续扫）
    candidates, summary = _load_or_run_heuristic_scan(
        entry_path, langs, exclude_dirs, sec_dir, status_mgr, _progress_append
    )

    # 2) 将候选问题精简为子任务清单，控制上下文长度
    compact_candidates = _prepare_candidates(candidates)
    
    # 记录批次选择信息（可选，用于日志）
    try:
        groups = _group_candidates_by_file(compact_candidates)
        if groups:
            selected_file, items = max(groups.items(), key=lambda kv: len(kv[1]))
            try:
                typer.secho(f"[jarvis-sec] 批次选择: 文件={selected_file} 数量={len(items)}", fg=typer.colors.BLUE)
            except Exception:
                pass
            _progress_append({
                "event": "batch_selection",
                "selected_file": selected_file,
                "selected_count": len(items),
                "total_in_file": len(items),
            })
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
        progress_path,
        status_mgr,
        _progress_append,
        force_save_memory=force_save_memory,
    )

    # 4) 处理验证阶段
    meta_records: List[Dict] = []
    gid_counts: Dict[int, int] = {}
    all_issues = _process_verification_phase(
        cluster_batches,
        entry_path,
        langs,
        llm_group,
        sec_dir,
        progress_path,
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
            all_issues,
            scanned_root=summary.get("scanned_root"),
            scanned_files=summary.get("scanned_files"),
            meta=meta_records or None,
        )
        # 标记分析完成
        status_mgr.mark_completed(
            total_issues=len(all_issues),
            message=f"安全分析完成，共发现 {len(all_issues)} 个问题"
        )
        return result
    except Exception as e:
        # 发生错误时更新状态
        error_msg = str(e)
        status_mgr.mark_error(
            error_message=error_msg,
            error_type=type(e).__name__
        )
        raise


def _group_candidates_by_file(candidates: List[Dict]) -> Dict[str, List[Dict]]:
    """按文件分组候选问题"""
    from collections import defaultdict
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for it in candidates:
        groups[str(it.get("file") or "")].append(it)
    return groups


def _create_report_writer(sec_dir, report_file):
    """创建报告写入函数"""
    import json
    from pathlib import Path
    
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


def _sig_of(c: Dict) -> str:
    """生成候选问题的签名"""
    return f"{c.get('language','')}|{c.get('file','')}|{c.get('line','')}|{c.get('pattern','')}"


def _create_signature_function():
    """创建候选签名函数（已废弃，直接使用 _sig_of）"""
    return _sig_of


def _parse_clusters_from_text(text: str) -> tuple[Optional[List], Optional[str]]:
    """解析聚类文本，返回(解析结果, 错误信息)"""
    try:
        start = text.find("<CLUSTERS>")
        end = text.find("</CLUSTERS>")
        if start == -1 or end == -1 or end <= start:
            return None, "未找到 <CLUSTERS> 或 </CLUSTERS> 标签，或标签顺序错误"
        content = text[start + len("<CLUSTERS>"):end].strip()
        if not content:
            return None, "JSON 内容为空"
        try:
            data = json.loads(content)
        except Exception as json_err:
            error_msg = f"JSON 解析失败: {str(json_err)}"
            return None, error_msg
        if isinstance(data, list):
            return data, None
        return None, f"JSON 解析结果不是数组，而是 {type(data).__name__}"
    except Exception as e:
        return None, f"解析过程发生异常: {str(e)}"


def _create_cluster_snapshot_writer(sec_dir, cluster_records, compact_candidates, _progress_append):
    """创建聚类快照写入函数"""
    def _write_cluster_batch_snapshot(batch_records: List[Dict]):
        """写入单个批次的聚类结果，支持增量保存"""
        try:
            from pathlib import Path as _Path2
            import json as _json
            _cluster_path = sec_dir / "cluster_report.jsonl"
            _cluster_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 追加模式，每次只追加当前批次的记录
            with _cluster_path.open("a", encoding="utf-8") as f:
                for record in batch_records:
                    f.write(_json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass
    
    def _write_cluster_report_snapshot():
        """写入聚类报告快照"""
        try:
            from pathlib import Path as _Path2
            import json as _json
            _cluster_path = sec_dir / "cluster_report.jsonl"
            _cluster_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 使用追加模式，每次只追加当前批次的记录
            # 注意：这会导致重复记录，需要在读取时去重
            with _cluster_path.open("a", encoding="utf-8") as f:
                for record in cluster_records:
                    f.write(_json.dumps(record, ensure_ascii=False) + "\n")

            _progress_append(
                {
                    "event": "cluster_report_snapshot",
                    "path": str(_cluster_path),
                    "clusters": len(cluster_records),
                    "total_candidates": len(compact_candidates),
                }
            )
        except Exception:
            pass
    
    return _write_cluster_batch_snapshot, _write_cluster_report_snapshot


def _collect_candidate_gids(file_groups: Dict[str, List[Dict]]) -> set:
    """收集所有候选的 gid"""
    all_gids = set()
    for _file, _items in file_groups.items():
        for it in _items:
            try:
                _gid = int(it.get("gid", 0))
                if _gid >= 1:
                    all_gids.add(_gid)
            except Exception:
                pass
    return all_gids


def _collect_clustered_gids(cluster_batches: List[List[Dict]], invalid_clusters_for_review: List[Dict]) -> set:
    """收集所有已聚类的 gid"""
    all_clustered_gids = set()
    for batch in cluster_batches:
        for item in batch:
            try:
                _gid = int(item.get("gid", 0))
                if _gid >= 1:
                    all_clustered_gids.add(_gid)
            except Exception:
                pass
    # 也收集无效聚类中的 gid（它们已经进入复核流程）
    for invalid_cluster in invalid_clusters_for_review:
        gids_list = invalid_cluster.get("gids", [])
        for _gid in gids_list:
            try:
                _gid_int = int(_gid)
                if _gid_int >= 1:
                    all_clustered_gids.add(_gid_int)
            except Exception:
                pass
    return all_clustered_gids


def _load_processed_gids_from_agent_issues(sec_dir) -> set:
    """从 agent_issues.jsonl 读取已处理的 gid"""
    processed_gids = set()
    try:
        from pathlib import Path
        import json
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


def _load_completed_batch_ids(progress_path) -> set:
    """从 progress.jsonl 读取已完成的批次ID"""
    completed_batch_ids = set()
    try:
        import json
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


def _load_all_issues_from_file(sec_dir) -> List[Dict]:
    """从 agent_issues.jsonl 读取所有已保存的告警"""
    all_issues: List[Dict] = []
    try:
        from pathlib import Path
        import json
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


def _supplement_missing_gids_for_clustering(
    missing_gids: set,
    gid_to_candidate: Dict[int, Dict],
    cluster_batches: List[List[Dict]],
    _progress_append,
    processed_gids_from_issues: set,
) -> tuple[int, int]:
    """为遗漏的 gid 补充聚类，返回(补充数量, 跳过数量)"""
    supplemented_count = 0
    skipped_count = 0
    
    for missing_gid in sorted(missing_gids):
        # 如果该 gid 已经在 agent_issues.jsonl 中有结果，说明已经验证过了
        # 不需要重新聚类，但记录一下
        if missing_gid in processed_gids_from_issues:
            skipped_count += 1
            _progress_append({
                "event": "cluster_missing_gid_skipped",
                "gid": missing_gid,
                "note": "已在agent_issues.jsonl中有验证结果，跳过重新处理",
                "reason": "already_processed",
            })
            continue
        
        # 找到对应的候选
        missing_item = gid_to_candidate.get(missing_gid)
        if missing_item:
            # 为遗漏的 gid 创建默认验证条件
            default_verification = f"验证候选 {missing_gid} 的安全风险"
            missing_item["verify"] = default_verification
            cluster_batches.append([missing_item])
            supplemented_count += 1
            _progress_append({
                "event": "cluster_missing_gid_supplement",
                "gid": missing_gid,
                "file": missing_item.get("file"),
                "note": "分析阶段开始前补充的遗漏gid",
            })
    
    return supplemented_count, skipped_count


def _handle_single_alert_file(
    file: str,
    single_item: Dict,
    single_gid: int,
    cluster_batches: List[List[Dict]],
    cluster_records: List[Dict],
    _progress_append,
    _write_cluster_batch_snapshot,
) -> None:
    """处理单告警文件：跳过聚类，直接写入"""
    default_verification = f"验证候选 {single_gid} 的安全风险"
    single_item["verify"] = default_verification
    cluster_batches.append([single_item])
    cluster_records.append(
        {
            "file": file,
            "verification": default_verification,
            "gids": [single_gid],
            "count": 1,
            "batch_index": 1,
            "note": "单告警跳过聚类",
        }
    )
    _progress_append(
        {
            "event": "cluster_status",
            "status": "done",
            "file": file,
            "batch_index": 1,
            "skipped": True,
            "reason": "single_alert",
        }
    )
    current_batch_records = [
        rec for rec in cluster_records
        if rec.get("file") == file and rec.get("batch_index") == 1
    ]
    if current_batch_records:
        _write_cluster_batch_snapshot(current_batch_records)
    typer.secho(f"[jarvis-sec] 文件 {file} 仅有一个告警（gid={single_gid}），跳过聚类直接写入", fg=typer.colors.BLUE)


def _validate_cluster_format(cluster_items: List[Dict]) -> tuple[bool, List[str]]:
    """验证聚类结果的格式，返回(是否有效, 错误详情列表)"""
    if not isinstance(cluster_items, list) or not cluster_items:
        return False, ["结果不是数组或数组为空"]
    
    error_details = []
    for idx, it in enumerate(cluster_items):
        if not isinstance(it, dict):
            error_details.append(f"元素{idx}不是字典")
            return False, error_details
        
        vals = it.get("gids", [])
        if not isinstance(it.get("verification", ""), str) or not isinstance(vals, list):
            error_details.append(f"元素{idx}的verification或gids格式错误")
            return False, error_details
        
        # 校验 gids 列表中的每个元素是否都是有效的整数
        if isinstance(vals, list):
            for gid_idx, gid_val in enumerate(vals):
                try:
                    gid_int = int(gid_val)
                    if gid_int < 1:
                        error_details.append(f"元素{idx}的gids[{gid_idx}]不是有效的正整数（值为{gid_val}）")
                        return False, error_details
                except (ValueError, TypeError):
                    error_details.append(f"元素{idx}的gids[{gid_idx}]不是有效的整数（值为{gid_val}，类型为{type(gid_val).__name__}）")
                    return False, error_details
        
        # 校验 is_invalid 字段（必填）
        if "is_invalid" not in it:
            error_details.append(f"元素{idx}缺少is_invalid字段（必填）")
            return False, error_details
        
        is_invalid_val = it.get("is_invalid")
        if not isinstance(is_invalid_val, bool):
            error_details.append(f"元素{idx}的is_invalid不是布尔值")
            return False, error_details
        
        # 如果is_invalid为true，必须提供invalid_reason
        if is_invalid_val is True:
            invalid_reason = it.get("invalid_reason", "")
            if not isinstance(invalid_reason, str) or not invalid_reason.strip():
                error_details.append(f"元素{idx}的is_invalid为true但缺少invalid_reason字段或理由为空（必填）")
                return False, error_details
    
    return True, []


def _extract_classified_gids(cluster_items: List[Dict]) -> set:
    """从聚类结果中提取所有已分类的gid
    
    注意：此函数假设格式验证已经通过，所有gid都是有效的整数。
    如果遇到格式错误的gid，会记录警告但不会抛出异常（因为格式验证应该已经捕获了这些问题）。
    """
    classified_gids = set()
    for cl in cluster_items:
        raw_gids = cl.get("gids", [])
        if isinstance(raw_gids, list):
            for x in raw_gids:
                try:
                    xi = int(x)
                    if xi >= 1:
                        classified_gids.add(xi)
                except (ValueError, TypeError) as e:
                    # 理论上不应该到达这里（格式验证应该已经捕获），但如果到达了，记录警告
                    try:
                        typer.secho(f"[jarvis-sec] 警告：在提取gid时遇到格式错误（值={x}，类型={type(x).__name__}），这不应该发生（格式验证应该已捕获）", fg=typer.colors.YELLOW)
                    except Exception:
                        pass
                    continue
    return classified_gids


def _build_cluster_retry_task(
    file: str,
    missing_gids: set,
    error_details: List[str],
) -> str:
    """构建聚类重试任务"""
    retry_task = f"""
# 聚类任务重试
文件: {file}

**重要提示**：请重新输出聚类结果。
""".strip()
    if missing_gids:
        missing_gids_list = sorted(list(missing_gids))
        missing_count = len(missing_gids)
        retry_task += f"\n\n**遗漏的gid（共{missing_count}个，必须被分类）：**\n" + ", ".join(str(gid) for gid in missing_gids_list)
    if error_details:
        retry_task += f"\n\n**格式错误：**\n" + "\n".join(f"- {detail}" for detail in error_details)
    return retry_task


def _build_cluster_error_guidance(
    error_details: List[str],
    missing_gids: set,
) -> str:
    """构建聚类错误指导信息"""
    error_guidance = ""
    if error_details:
        error_guidance = f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n" + "\n".join(f"- {detail}" for detail in error_details)
    if missing_gids:
        missing_gids_list = sorted(list(missing_gids))
        missing_count = len(missing_gids)
        error_guidance += f"\n\n**完整性错误：遗漏了 {missing_count} 个 gid，这些 gid 必须被分类：**\n" + ", ".join(str(gid) for gid in missing_gids_list)
    return error_guidance


def _run_cluster_agent_direct_model(
    cluster_agent,
    cluster_task: str,
    cluster_summary_prompt: str,
    file: str,
    missing_gids: set,
    error_details: List[str],
    _cluster_summary: Dict[str, str],
) -> None:
    """使用直接模型调用运行聚类Agent"""
    retry_task = _build_cluster_retry_task(file, missing_gids, error_details)
    error_guidance = _build_cluster_error_guidance(error_details, missing_gids)
    full_prompt = f"{retry_task}{error_guidance}\n\n{cluster_summary_prompt}"
    try:
        response = cluster_agent.model.chat_until_success(full_prompt)  # type: ignore
        _cluster_summary["text"] = response
    except Exception as e:
        try:
            typer.secho(f"[jarvis-sec] 直接模型调用失败: {e}，回退到 run()", fg=typer.colors.YELLOW)
        except Exception:
            pass
        cluster_agent.run(cluster_task)


def _validate_cluster_result(
    cluster_items: Optional[List[Dict]],
    parse_error: Optional[str],
    attempt: int,
) -> tuple[bool, List[str]]:
    """验证聚类结果格式"""
    if parse_error:
        error_details = [f"JSON解析失败: {parse_error}"]
        typer.secho(f"[jarvis-sec] JSON解析失败: {parse_error}", fg=typer.colors.YELLOW)
        return False, error_details
    else:
        valid, error_details = _validate_cluster_format(cluster_items)
        if not valid:
            typer.secho(f"[jarvis-sec] 聚类结果格式无效（{'; '.join(error_details)}），重试第 {attempt} 次（使用直接模型调用）", fg=typer.colors.YELLOW)
        return valid, error_details


def _check_cluster_completeness(
    cluster_items: List[Dict],
    input_gids: set,
    attempt: int,
) -> tuple[bool, set]:
    """检查聚类完整性，返回(是否完整, 遗漏的gid)"""
    classified_gids = _extract_classified_gids(cluster_items)
    missing_gids = input_gids - classified_gids
    if not missing_gids:
        typer.secho(f"[jarvis-sec] 聚类完整性校验通过，所有gid已分类（共尝试 {attempt} 次）", fg=typer.colors.GREEN)
        return True, set()
    else:
        missing_gids_list = sorted(list(missing_gids))
        missing_count = len(missing_gids)
        typer.secho(f"[jarvis-sec] 聚类完整性校验失败：遗漏的gid: {missing_gids_list}（{missing_count}个），重试第 {attempt} 次（使用直接模型调用）", fg=typer.colors.YELLOW)
        return False, missing_gids


def _run_cluster_agent_with_retry(
    cluster_agent,
    cluster_task: str,
    cluster_summary_prompt: str,
    input_gids: set,
    file: str,
    _cluster_summary: Dict[str, str],
) -> tuple[Optional[List[Dict]], Optional[str]]:
    """运行聚类Agent并永久重试直到所有gid都被分类，返回(聚类结果, 解析错误)"""
    _attempt = 0
    use_direct_model = False
    error_details: List[str] = []
    missing_gids = set()
    
    while True:
        _attempt += 1
        _cluster_summary["text"] = ""
        
        if use_direct_model:
            _run_cluster_agent_direct_model(
                cluster_agent,
                cluster_task,
                cluster_summary_prompt,
                file,
                missing_gids,
                error_details,
                _cluster_summary,
            )
        else:
            # 第一次使用 run()，让 Agent 完整运行（可能使用工具）
            cluster_agent.run(cluster_task)
        
        cluster_items, parse_error = _parse_clusters_from_text(_cluster_summary.get("text", ""))
        
        # 校验结构
        valid, error_details = _validate_cluster_result(cluster_items, parse_error, _attempt)
        
        # 完整性校验：检查所有输入的gid是否都被分类
        missing_gids = set()
        if valid and cluster_items:
            is_complete, missing_gids = _check_cluster_completeness(cluster_items, input_gids, _attempt)
            if is_complete:
                return cluster_items, None
            else:
                use_direct_model = True
                valid = False
        
        if not valid:
            use_direct_model = True
            cluster_items = None


def _process_cluster_results(
    cluster_items: List[Dict],
    pending_in_file_with_ids: List[Dict],
    file: str,
    chunk_idx: int,
    cluster_batches: List[List[Dict]],
    cluster_records: List[Dict],
    invalid_clusters_for_review: List[Dict],
    _progress_append,
) -> tuple[int, int]:
    """处理聚类结果，返回(有效聚类数, 无效聚类数)"""
    gid_to_item: Dict[int, Dict] = {}
    try:
        for it in pending_in_file_with_ids:
            try:
                _gid = int(it.get("gid", 0))
                if _gid >= 1:
                    gid_to_item[_gid] = it
            except Exception:
                pass
    except Exception:
        gid_to_item = {}
    
    _merged_count = 0
    _invalid_count = 0
    classified_gids_final = set()
    
    for cl in cluster_items:
        verification = str(cl.get("verification", "")).strip()
        raw_gids = cl.get("gids", [])
        is_invalid = cl["is_invalid"]
        norm_keys: List[int] = []
        if isinstance(raw_gids, list):
            for x in raw_gids:
                try:
                    xi = int(x)
                    if xi >= 1:
                        norm_keys.append(xi)
                        classified_gids_final.add(xi)
                except Exception:
                    pass
        
        members: List[Dict] = []
        for k in norm_keys:
            it = gid_to_item.get(k)
            if it:
                it["verify"] = verification
                members.append(it)
        
        # 如果标记为无效，收集到复核列表
        if is_invalid:
            _invalid_count += 1
            invalid_gids = [m.get("gid") for m in members]
            invalid_reason = str(cl.get("invalid_reason", "")).strip()
            try:
                typer.secho(f"[jarvis-sec] 聚类阶段判定为无效（gids={invalid_gids}），将提交复核Agent验证", fg=typer.colors.BLUE)
            except Exception:
                pass
            invalid_clusters_for_review.append({
                "file": file,
                "batch_index": chunk_idx,
                "gids": invalid_gids,
                "verification": verification,
                "invalid_reason": invalid_reason,
                "members": members,
                "count": len(members),
            })
            _progress_append({
                "event": "cluster_invalid",
                "file": file,
                "batch_index": chunk_idx,
                "gids": invalid_gids,
                "verification": verification,
                "count": len(members),
            })
            cluster_records.append({
                "file": file,
                "verification": verification,
                "gids": invalid_gids,
                "count": len(members),
                "batch_index": chunk_idx,
                "is_invalid": True,
                "invalid_reason": invalid_reason,
            })
        elif members:
            _merged_count += 1
            cluster_batches.append(members)
            cluster_records.append({
                "file": file,
                "verification": verification,
                "gids": [m.get("gid") for m in members],
                "count": len(members),
                "batch_index": chunk_idx,
                "is_invalid": False,
            })
    
    return _merged_count, _invalid_count


def _supplement_missing_gids(
    missing_gids_final: set,
    gid_to_item: Dict[int, Dict],
    file: str,
    chunk_idx: int,
    cluster_batches: List[List[Dict]],
    cluster_records: List[Dict],
) -> int:
    """为遗漏的gid创建单独聚类，返回补充的聚类数"""
    supplemented_count = 0
    for missing_gid in sorted(missing_gids_final):
        missing_item = gid_to_item.get(missing_gid)
        if missing_item:
            default_verification = f"验证候选 {missing_gid} 的安全风险"
            missing_item["verify"] = default_verification
            cluster_batches.append([missing_item])
            cluster_records.append({
                "file": file,
                "verification": default_verification,
                "gids": [missing_gid],
                "count": 1,
                "batch_index": chunk_idx,
                "note": "完整性校验补充的遗漏gid",
            })
            supplemented_count += 1
    return supplemented_count


def _get_cluster_system_prompt() -> str:
    """获取聚类Agent的系统提示词"""
    return """
# 单Agent聚类约束
- 你的任务是对同一文件内的启发式候选进行聚类，将可以一起验证的问题归为一类。
- **聚类原则**：
  - 可以一起验证的问题归为一类，不一定是验证条件完全一致才能归为一类。
  - 如果多个候选问题可以通过同一个验证过程来确认，即使它们的验证条件略有不同，也可以归为一类。
  - 例如：多个指针解引用问题可以归为一类（验证"指针在解引用前非空"），即使它们涉及不同的指针变量。
  - 例如：多个缓冲区操作问题可以归为一类（验证"拷贝长度不超过目标缓冲区容量"），即使它们涉及不同的缓冲区。
- 验证条件：为了确认是否存在漏洞需要成立/验证的关键前置条件。例如："指针p在解引用前非空""拷贝长度不超过目标缓冲区容量"等。
- **完整性要求**：每个gid都必须出现在某个类别中，不能遗漏任何一个gid。所有输入的gid都必须被分类。
- 工具优先：如需核对上下文，可使用 read_code 读取相邻代码；避免过度遍历。
- 禁止写操作；仅只读分析。
- **重要：关于无效判断的保守策略**：
  - 在判断候选是否无效时，必须充分考虑所有可能的路径、调用链和边界情况。
  - 必须考虑：所有可能的调用者、所有可能的输入来源、所有可能的执行路径、所有可能的边界条件。
  - 只要存在任何可能性（即使很小）导致漏洞可被触发，就不应该标记为无效（is_invalid: false）。
  - 只有在完全确定、没有任何可能性、所有路径都已验证安全的情况下，才能标记为无效（is_invalid: true）。
  - 保守原则：有疑问时，一律标记为 false（需要进入后续验证阶段），让分析Agent和验证Agent进行更深入的分析。
  - 不要因为看到局部有保护措施就认为无效，要考虑是否有其他调用路径绕过这些保护。
  - 不要因为看到某些调用者已做校验就认为无效，要考虑是否有其他调用者未做校验。
- **记忆使用**：
  - 在聚类过程中，充分利用 retrieve_memory 工具检索已有的记忆，特别是与当前文件或函数相关的记忆。
  - 如果有必要，使用 save_memory 工具保存聚类过程中发现的函数或代码片段的要点，使用函数名或文件名作为 tag。
  - 记忆内容示例：某个函数的指针已经判空、某个函数已有输入校验、某个代码片段的上下文信息等。
  - 这些记忆可以帮助后续的分析Agent和验证Agent更高效地工作。
    """.strip()


def _get_cluster_summary_prompt() -> str:
    """获取聚类Agent的摘要提示词"""
    return """
请仅在 <CLUSTERS> 与 </CLUSTERS> 中输出 JSON 数组：
- 每个元素包含（所有字段均为必填）：
  - verification: 字符串（对该聚类的验证条件描述，简洁明确，可直接用于后续Agent验证）
  - gids: 整数数组（候选的全局唯一编号；输入JSON每个元素含 gid，可直接对应填入）
  - is_invalid: 布尔值（必填，true 或 false）。如果为 true，表示该聚类中的所有候选已被确认为无效/误报，将不会进入后续验证阶段；如果为 false，表示该聚类中的候选需要进入后续验证阶段。
  - invalid_reason: 字符串（当 is_invalid 为 true 时必填，当 is_invalid 为 false 时可省略）。必须详细说明为什么这些候选是无效的，包括：
    * 已检查的所有调用路径和调用者
    * 已确认的保护措施和校验逻辑
    * 为什么这些保护措施在所有路径上都有效
    * 为什么不存在任何可能的触发路径
    * 必须足够详细，以便复核Agent能够验证你的判断
- 要求：
  - 严格要求：仅输出位于 <CLUSTERS> 与 </CLUSTERS> 间的 JSON 数组，其他位置不输出任何文本
  - **完整性要求（最重要）**：输入JSON中的所有gid都必须被分类，不能遗漏任何一个gid。所有gid必须出现在某个聚类的gids数组中。这是强制要求，必须严格遵守。
  - **聚类原则**：可以一起验证的问题归为一类，不一定是验证条件完全一致才能归为一类。如果多个候选问题可以通过同一个验证过程来确认，即使它们的验证条件略有不同，也可以归为一类。
  - **必须要求**：每个聚类元素必须包含 is_invalid 字段，且值必须为 true 或 false，不能省略。
  - **必须要求**：当 is_invalid 为 true 时，必须提供 invalid_reason 字段，且理由必须充分详细。
  - 不需要解释与长文本，仅给出可执行的验证条件短句
  - 若无法聚类，请将每个候选单独成组，verification 为该候选的最小确认条件
  - **关于 is_invalid 的保守判断原则**：
    - 必须充分考虑所有可能的路径、调用链、输入来源和边界情况。
    - 只要存在任何可能性（即使很小）导致漏洞可被触发，必须设置 is_invalid: false。
    - 只有在完全确定、没有任何可能性、所有路径都已验证安全的情况下，才能设置 is_invalid: true。
    - 保守策略：有疑问时，一律设置为 false，让后续的分析Agent和验证Agent进行更深入的分析。
    - 不要因为局部有保护措施就设置为 true，要考虑是否有其他路径绕过保护。
    - 不要因为某些调用者已做校验就设置为 true，要考虑是否有其他调用者未做校验。
    - 如果设置为 true，必须在 invalid_reason 中详细说明已检查的所有路径和原因。
  - 支持json5语法（如尾随逗号、注释等）。
<CLUSTERS>
[
  {
    "verification": "",
    "gids": [],
    "is_invalid": false
  }
]
</CLUSTERS>
    """.strip()


def _create_cluster_agent(
    file: str,
    chunk_idx: int,
    llm_group: Optional[str],
    force_save_memory: bool = False,
) -> Agent:
    """创建聚类Agent"""
    cluster_system_prompt = _get_cluster_system_prompt()
    cluster_summary_prompt = _get_cluster_summary_prompt()
    
    agent_kwargs_cluster: Dict = dict(
        system_prompt=cluster_system_prompt,
        name=f"JARVIS-SEC-Cluster::{file}::batch{chunk_idx}",
        auto_complete=True,
        need_summary=True,
        summary_prompt=cluster_summary_prompt,
        non_interactive=True,
        in_multi_agent=False,
        use_methodology=False,
        use_analysis=False,
        output_handler=[ToolRegistry()],
        force_save_memory=force_save_memory,
        use_tools=["read_code", "execute_script", "save_memory", "retrieve_memory"],
    )
    if llm_group:
        agent_kwargs_cluster["model_group"] = llm_group
    return Agent(**agent_kwargs_cluster)


def _build_cluster_task(
    pending_in_file_with_ids: List[Dict],
    entry_path: str,
    file: str,
    langs: List[str],
) -> str:
    """构建聚类任务上下文"""
    import json as _json2
    return f"""
# 聚类任务（分析输入）
上下文：
- entry_path: {entry_path}
- file: {file}
- languages: {langs}

候选(JSON数组，包含 gid/file/line/pattern/category/evidence)：
{_json2.dumps(pending_in_file_with_ids, ensure_ascii=False, indent=2)}
        """.strip()


def _extract_input_gids(pending_in_file_with_ids: List[Dict]) -> set:
    """从待聚类项中提取gid集合"""
    input_gids = set()
    for it in pending_in_file_with_ids:
        try:
            _gid = int(it.get("gid", 0))
            if _gid >= 1:
                input_gids.add(_gid)
        except Exception:
            pass
    return input_gids


def _build_gid_to_item_mapping(pending_in_file_with_ids: List[Dict]) -> Dict[int, Dict]:
    """构建gid到项的映射"""
    gid_to_item: Dict[int, Dict] = {}
    try:
        for it in pending_in_file_with_ids:
            try:
                _gid = int(it.get("gid", 0))
                if _gid >= 1:
                    gid_to_item[_gid] = it
            except Exception:
                pass
    except Exception:
        pass
    return gid_to_item


def _process_cluster_chunk(
    chunk: List[Dict],
    chunk_idx: int,
    file: str,
    entry_path: str,
    langs: List[str],
    llm_group: Optional[str],
    cluster_batches: List[List[Dict]],
    cluster_records: List[Dict],
    invalid_clusters_for_review: List[Dict],
    _progress_append,
    _write_cluster_batch_snapshot,
    force_save_memory: bool = False,
) -> None:
    """处理单个聚类批次"""
    if not chunk:
        return
    
    pending_in_file_with_ids = list(chunk)
    
    # 记录聚类批次开始
    _progress_append({
        "event": "cluster_status",
        "status": "running",
        "file": file,
        "batch_index": chunk_idx,
        "total_in_batch": len(pending_in_file_with_ids),
    })
    
    # 创建聚类Agent
    cluster_agent = _create_cluster_agent(file, chunk_idx, llm_group, force_save_memory=force_save_memory)
    
    # 构建任务上下文
    cluster_task = _build_cluster_task(pending_in_file_with_ids, entry_path, file, langs)
    
    # 订阅摘要事件
    cluster_summary = _subscribe_summary_event(cluster_agent)
    
    # 提取输入gid
    input_gids = _extract_input_gids(pending_in_file_with_ids)
    
    # 运行聚类Agent
    cluster_summary_prompt = _get_cluster_summary_prompt()
    cluster_items, parse_error = _run_cluster_agent_with_retry(
        cluster_agent,
        cluster_task,
        cluster_summary_prompt,
        input_gids,
        file,
        cluster_summary,
    )
    
    # 处理聚类结果
    _merged_count = 0
    _invalid_count = 0
    
    if isinstance(cluster_items, list) and cluster_items:
        gid_to_item = _build_gid_to_item_mapping(pending_in_file_with_ids)
        
        _merged_count, _invalid_count = _process_cluster_results(
            cluster_items,
            pending_in_file_with_ids,
            file,
            chunk_idx,
            cluster_batches,
            cluster_records,
            invalid_clusters_for_review,
            _progress_append,
        )
        
        classified_gids_final = _extract_classified_gids(cluster_items)
        missing_gids_final = input_gids - classified_gids_final
        if missing_gids_final:
            typer.secho(f"[jarvis-sec] 警告：仍有遗漏的gid {sorted(list(missing_gids_final))}，将为每个遗漏的gid创建单独聚类", fg=typer.colors.YELLOW)
            supplemented_count = _supplement_missing_gids(
                missing_gids_final,
                gid_to_item,
                file,
                chunk_idx,
                cluster_batches,
                cluster_records,
            )
            _merged_count += supplemented_count
    else:
        # 聚类结果为空或None：为所有输入的gid创建单独聚类（保守策略）
        if pending_in_file_with_ids:
            typer.secho(f"[jarvis-sec] 警告：聚类结果为空或None（文件={file}，批次={chunk_idx}），为所有gid创建单独聚类", fg=typer.colors.YELLOW)
            gid_to_item_fallback = _build_gid_to_item_mapping(pending_in_file_with_ids)
            
            _merged_count = _supplement_missing_gids(
                input_gids,
                gid_to_item_fallback,
                file,
                chunk_idx,
                cluster_batches,
                cluster_records,
            )
            _invalid_count = 0
        else:
            _merged_count = 0
            _invalid_count = 0
    
    # 标记聚类批次完成
    _progress_append({
        "event": "cluster_status",
        "status": "done",
        "file": file,
        "batch_index": chunk_idx,
        "clusters_count": _merged_count,
        "invalid_clusters_count": _invalid_count,
    })
    if _invalid_count > 0:
        try:
            typer.secho(f"[jarvis-sec] 聚类批次完成: 有效聚类={_merged_count}，无效聚类={_invalid_count}（已跳过）", fg=typer.colors.GREEN)
        except Exception:
            pass
    
    # 写入当前批次的聚类结果
    current_batch_records = [
        rec for rec in cluster_records
        if rec.get("file") == file and rec.get("batch_index") == chunk_idx
    ]
    if current_batch_records:
        _write_cluster_batch_snapshot(current_batch_records)


def _filter_pending_items(items: List[Dict], clustered_gids: set) -> List[Dict]:
    """过滤出待聚类的项"""
    pending_in_file: List[Dict] = []
    for c in items:
        try:
            _gid = int(c.get("gid", 0))
            if _gid >= 1 and _gid not in clustered_gids:
                pending_in_file.append(c)
        except Exception:
            pass
    return pending_in_file


def _process_file_clustering(
    file: str,
    items: List[Dict],
    clustered_gids: set,
    cluster_batches: List[List[Dict]],
    cluster_records: List[Dict],
    invalid_clusters_for_review: List[Dict],
    entry_path: str,
    langs: List[str],
    cluster_limit: int,
    llm_group: Optional[str],
    _progress_append,
    _write_cluster_batch_snapshot,
    force_save_memory: bool = False,
) -> None:
    """处理单个文件的聚类任务"""
    # 过滤掉已聚类的 gid
    pending_in_file = _filter_pending_items(items, clustered_gids)
    if not pending_in_file:
        return
    
    # 优化：如果文件只有一个告警，跳过聚类，直接写入
    if len(pending_in_file) == 1:
        single_item = pending_in_file[0]
        single_gid = single_item.get("gid", 0)
        _handle_single_alert_file(
            file,
            single_item,
            single_gid,
            cluster_batches,
            cluster_records,
            _progress_append,
            _write_cluster_batch_snapshot,
        )
        return
    
    # 将该文件的告警按 cluster_limit 分批
    _limit = cluster_limit if isinstance(cluster_limit, int) and cluster_limit > 0 else 50
    _chunks: List[List[Dict]] = [pending_in_file[i:i + _limit] for i in range(0, len(pending_in_file), _limit)]
    
    # 处理每个批次
    for _chunk_idx, _chunk in enumerate(_chunks, start=1):
        _process_cluster_chunk(
            _chunk,
            _chunk_idx,
            file,
            entry_path,
            langs,
            llm_group,
            cluster_batches,
            cluster_records,
            invalid_clusters_for_review,
            _progress_append,
            _write_cluster_batch_snapshot,
            force_save_memory=force_save_memory,
        )


def _is_valid_review_item(item: Dict) -> bool:
    """验证复核结果项的格式"""
    if not isinstance(item, dict) or "is_reason_sufficient" not in item:
        return False
    has_gid = "gid" in item
    has_gids = "gids" in item
    if not has_gid and not has_gids:
        return False
    if has_gid and has_gids:
        return False  # gid 和 gids 不能同时出现
    if has_gid:
        try:
            return int(item["gid"]) >= 1
        except Exception:
            return False
    elif has_gids:
        if not isinstance(item["gids"], list) or len(item["gids"]) == 0:
            return False
        try:
            return all(int(gid_val) >= 1 for gid_val in item["gids"])
        except Exception:
            return False
    return False


def _build_gid_to_review_mapping(review_results: List[Dict]) -> Dict[int, Dict]:
    """构建gid到复核结果的映射（支持 gid 和 gids 两种格式）"""
    gid_to_review: Dict[int, Dict] = {}
    for rr in review_results:
        if not isinstance(rr, dict):
            continue
        
        # 支持 gid 和 gids 两种格式
        gids_to_process: List[int] = []
        if "gids" in rr and isinstance(rr.get("gids"), list):
            # 合并格式：gids 数组
            for gid_val in rr.get("gids", []):
                try:
                    gid_int = int(gid_val)
                    if gid_int >= 1:
                        gids_to_process.append(gid_int)
                except Exception:
                    pass
        elif "gid" in rr:
            # 单个格式：gid
            try:
                gid_int = int(rr.get("gid", 0))
                if gid_int >= 1:
                    gids_to_process.append(gid_int)
            except Exception:
                pass
        
        # 为每个 gid 创建复核结果映射
        is_reason_sufficient = rr.get("is_reason_sufficient")
        review_notes = str(rr.get("review_notes", "")).strip()
        for gid in gids_to_process:
            gid_to_review[gid] = {
                "is_reason_sufficient": is_reason_sufficient,
                "review_notes": review_notes
            }
    return gid_to_review


def _process_review_batch(
    review_batch: List[Dict],
    review_results: Optional[List[Dict]],
    reviewed_clusters: List[Dict],
    reinstated_candidates: List[Dict],
) -> None:
    """处理单个复核批次的结果"""
    if review_results:
        # 构建gid到复核结果的映射
        gid_to_review = _build_gid_to_review_mapping(review_results)
        
        # 处理每个无效聚类
        for invalid_cluster in review_batch:
            cluster_gids = invalid_cluster.get("gids", [])
            cluster_members = invalid_cluster.get("members", [])
            
            # 检查该聚类中的所有gid的复核结果
            all_sufficient = True
            any_reviewed = False
            insufficient_review_result = None
            for gid in cluster_gids:
                review_result = gid_to_review.get(gid)
                if review_result:
                    any_reviewed = True
                    if review_result.get("is_reason_sufficient") is not True:
                        all_sufficient = False
                        if not insufficient_review_result:
                            insufficient_review_result = review_result
                        break
            
            if any_reviewed and not all_sufficient:
                # 理由不充分，重新加入验证流程
                typer.secho(f"[jarvis-sec] 复核结果：无效聚类（gids={cluster_gids}）理由不充分，重新加入验证流程", fg=typer.colors.BLUE)
                for member in cluster_members:
                    reinstated_candidates.append(member)
                reviewed_clusters.append({
                    **invalid_cluster,
                    "review_result": "reinstated",
                    "review_notes": insufficient_review_result.get("review_notes", "") if insufficient_review_result else "",
                })
            else:
                # 理由充分，确认无效
                review_notes = ""
                if cluster_gids and gid_to_review.get(cluster_gids[0]):
                    review_notes = gid_to_review[cluster_gids[0]].get("review_notes", "")
                typer.secho(f"[jarvis-sec] 复核结果：无效聚类（gids={cluster_gids}）理由充分，确认为无效", fg=typer.colors.GREEN)
                reviewed_clusters.append({
                    **invalid_cluster,
                    "review_result": "confirmed_invalid",
                    "review_notes": review_notes,
                })
    else:
        # 复核结果解析失败，保守策略：重新加入验证流程
        typer.secho(f"[jarvis-sec] 警告：复核结果解析失败，保守策略：将批次中的所有候选重新加入验证流程", fg=typer.colors.YELLOW)
        for invalid_cluster in review_batch:
            cluster_members = invalid_cluster.get("members", [])
            for member in cluster_members:
                reinstated_candidates.append(member)
            reviewed_clusters.append({
                **invalid_cluster,
                "review_result": "reinstated",
                "review_notes": "复核结果解析失败，保守策略重新加入验证",
            })


def _run_review_agent_with_retry(
    review_agent,
    review_task: str,
    review_summary_prompt: str,
    entry_path: str,
    review_summary_container: Dict[str, str],
) -> tuple[Optional[List[Dict]], Optional[str]]:
    """运行复核Agent并永久重试直到格式正确，返回(复核结果, 解析错误)"""
    use_direct_model_review = False
    prev_parse_error_review: Optional[str] = None
    review_attempt = 0
    
    while True:
        review_attempt += 1
        review_summary_container["text"] = ""
        
        if use_direct_model_review:
            # 格式校验失败后，直接调用模型接口
            review_summary_prompt_text = _build_verification_summary_prompt()
            error_guidance = ""
            if prev_parse_error_review:
                error_guidance = f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- JSON解析失败: {prev_parse_error_review}\n\n请确保输出的JSON格式正确，包括正确的引号、逗号、大括号等。仅输出一个 <REPORT> 块，块内直接包含 JSON 数组（不需要额外的标签）。支持json5语法（如尾随逗号、注释等）。"
            
            full_review_prompt = f"{review_task}{error_guidance}\n\n{review_summary_prompt_text}"
            try:
                review_response = review_agent.model.chat_until_success(full_review_prompt)  # type: ignore
                review_summary_container["text"] = review_response
            except Exception as e:
                try:
                    typer.secho(f"[jarvis-sec] 复核阶段直接模型调用失败: {e}，回退到 run()", fg=typer.colors.YELLOW)
                except Exception:
                    pass
                review_agent.run(review_task)
        else:
            # 第一次使用 run()，让 Agent 完整运行（可能使用工具）
            review_agent.run(review_task)
        
        # 工作区保护
        try:
            _changed_review = _git_restore_if_dirty(entry_path)
            if _changed_review:
                try:
                    typer.secho(f"[jarvis-sec] 复核Agent工作区已恢复 ({_changed_review} 个文件）", fg=typer.colors.BLUE)
                except Exception:
                    pass
        except Exception:
            pass
        
        # 解析复核结果
        review_summary_text = review_summary_container.get("text", "")
        parse_error_review = None
        if review_summary_text:
            review_parsed, parse_error_review = _try_parse_summary_report(review_summary_text)
            if parse_error_review:
                prev_parse_error_review = parse_error_review
                try:
                    typer.secho(f"[jarvis-sec] 复核结果JSON解析失败: {parse_error_review}", fg=typer.colors.YELLOW)
                except Exception:
                    pass
            else:
                prev_parse_error_review = None
                if isinstance(review_parsed, list):
                    if review_parsed and all(_is_valid_review_item(item) for item in review_parsed):
                        return review_parsed, None
        
        # 格式校验失败，后续重试使用直接模型调用
        use_direct_model_review = True
        if parse_error_review:
            try:
                typer.secho(f"[jarvis-sec] 复核结果JSON解析失败 -> 重试第 {review_attempt} 次（使用直接模型调用，将反馈解析错误）", fg=typer.colors.YELLOW)
            except Exception:
                pass
        else:
            try:
                typer.secho(f"[jarvis-sec] 复核结果格式无效 -> 重试第 {review_attempt} 次（使用直接模型调用）", fg=typer.colors.YELLOW)
            except Exception:
                pass


def _check_and_supplement_missing_gids(
    file_groups: Dict[str, List[Dict]],
    cluster_batches: List[List[Dict]],
    invalid_clusters_for_review: List[Dict],
    sec_dir,
    _progress_append,
) -> None:
    """检查并补充遗漏的 gid"""
    # 1. 收集所有候选的 gid
    all_candidate_gids = _collect_candidate_gids(file_groups)
    gid_to_candidate_for_check: Dict[int, Dict] = {}
    for _file, _items in file_groups.items():
        for it in _items:
            try:
                _gid = int(it.get("gid", 0))
                if _gid >= 1:
                    gid_to_candidate_for_check[_gid] = it
            except Exception:
                pass
    
    # 2. 收集所有已聚类的 gid
    all_clustered_gids = _collect_clustered_gids(cluster_batches, invalid_clusters_for_review)
    
    # 3. 读取已处理的 gid（从 agent_issues.jsonl）
    processed_gids_from_issues_for_check = _load_processed_gids_from_agent_issues(sec_dir)
    
    # 4. 检查是否有遗漏的 gid（未聚类）
    missing_gids_before_analysis = all_candidate_gids - all_clustered_gids
    if missing_gids_before_analysis:
        missing_count = len(missing_gids_before_analysis)
        missing_list = sorted(list(missing_gids_before_analysis))
        if missing_count > 50:
            # 如果遗漏的gid太多，只显示前10个和后10个
            display_list = missing_list[:10] + ["..."] + missing_list[-10:]
            typer.secho(f"[jarvis-sec] 警告：分析阶段开始前发现遗漏的gid（共{missing_count}个）：{display_list}，将检查是否需要补充聚类", fg=typer.colors.YELLOW)
        else:
            typer.secho(f"[jarvis-sec] 警告：分析阶段开始前发现遗漏的gid {missing_list}，将检查是否需要补充聚类", fg=typer.colors.YELLOW)
        
        # 为每个遗漏的 gid 创建单独的聚类
        supplemented_count, skipped_count = _supplement_missing_gids_for_clustering(
            missing_gids_before_analysis,
            gid_to_candidate_for_check,
            cluster_batches,
            _progress_append,
            processed_gids_from_issues_for_check,
        )
        
        # 输出统计信息
        if skipped_count > 0:
            try:
                typer.secho(f"[jarvis-sec] 已跳过 {skipped_count} 个已在agent_issues.jsonl中处理的gid", fg=typer.colors.GREEN)
            except Exception:
                pass
        if supplemented_count > 0:
            try:
                typer.secho(f"[jarvis-sec] 已为 {supplemented_count} 个遗漏的gid创建单独聚类", fg=typer.colors.GREEN)
            except Exception:
                pass


def _initialize_clustering_context(
    compact_candidates: List[Dict],
    sec_dir,
    progress_path,
    _progress_append,
) -> tuple[Dict[str, List[Dict]], Dict, tuple, List[List[Dict]], List[Dict], List[Dict], set]:
    """初始化聚类上下文，返回(文件分组, 已有聚类, 快照写入函数, 聚类批次, 聚类记录, 无效聚类, 已聚类gid)"""
    # 按文件分组构建待聚类集合
    _file_groups = _group_candidates_by_file(compact_candidates)
    
    cluster_batches: List[List[Dict]] = []
    cluster_records: List[Dict] = []
    invalid_clusters_for_review: List[Dict] = []
    
    # 读取已有聚类报告以支持断点
    _existing_clusters, _completed_cluster_batches = _load_existing_clusters(
        sec_dir, progress_path
    )
    
    # 创建快照写入函数
    _write_cluster_batch_snapshot, _write_cluster_report_snapshot = _create_cluster_snapshot_writer(
        sec_dir, cluster_records, compact_candidates, _progress_append
    )
    
    # 从断点恢复聚类结果
    cluster_batches, cluster_records, invalid_clusters_for_review, clustered_gids = _restore_clusters_from_checkpoint(
        _existing_clusters, _file_groups
    )
    
    return (
        _file_groups,
        _existing_clusters,
        (_write_cluster_batch_snapshot, _write_cluster_report_snapshot),
        cluster_batches,
        cluster_records,
        invalid_clusters_for_review,
        clustered_gids,
    )


def _check_unclustered_gids(
    all_candidate_gids: set,
    clustered_gids: set,
) -> set:
    """检查未聚类的gid"""
    unclustered_gids = all_candidate_gids - clustered_gids
    if unclustered_gids:
        try:
            typer.secho(f"[jarvis-sec] 发现 {len(unclustered_gids)} 个未聚类的 gid，将进行聚类", fg=typer.colors.YELLOW)
        except Exception:
            pass
    else:
        try:
            typer.secho(f"[jarvis-sec] 所有 {len(all_candidate_gids)} 个候选已聚类，跳过聚类阶段", fg=typer.colors.GREEN)
        except Exception:
            pass
    return unclustered_gids


def _execute_clustering_for_files(
    file_groups: Dict[str, List[Dict]],
    clustered_gids: set,
    cluster_batches: List[List[Dict]],
    cluster_records: List[Dict],
    invalid_clusters_for_review: List[Dict],
    entry_path: str,
    langs: List[str],
    cluster_limit: int,
    llm_group: Optional[str],
    status_mgr,
    _progress_append,
    _write_cluster_batch_snapshot,
    force_save_memory: bool = False,
) -> None:
    """执行文件聚类"""
    total_files_to_cluster = len(file_groups)
    # 更新聚类阶段状态
    if total_files_to_cluster > 0:
        status_mgr.update_clustering(
            current_file=0,
            total_files=total_files_to_cluster,
            message="开始聚类分析..."
        )
    for _file_idx, (_file, _items) in enumerate(file_groups.items(), start=1):
        typer.secho(f"\n[jarvis-sec] 聚类文件 {_file_idx}/{total_files_to_cluster}: {_file}", fg=typer.colors.CYAN)
        # 更新当前文件进度
        status_mgr.update_clustering(
            current_file=_file_idx,
            total_files=total_files_to_cluster,
            file_name=_file,
            message=f"正在聚类文件 {_file_idx}/{total_files_to_cluster}: {_file}"
        )
        # 使用子函数处理文件聚类
        _process_file_clustering(
            _file,
            _items,
            clustered_gids,
            cluster_batches,
            cluster_records,
            invalid_clusters_for_review,
            entry_path,
            langs,
            cluster_limit,
            llm_group,
            _progress_append,
            _write_cluster_batch_snapshot,
            force_save_memory=force_save_memory,
        )


def _record_clustering_completion(
    sec_dir,
    cluster_records: List[Dict],
    compact_candidates: List[Dict],
    _progress_append,
) -> None:
    """记录聚类阶段完成"""
    try:
        from pathlib import Path
        import json
        _cluster_path = sec_dir / "cluster_report.jsonl"
        _progress_append({
            "event": "cluster_report_written",
            "path": str(_cluster_path),
            "clusters": len(cluster_records),
            "total_candidates": len(compact_candidates),
            "note": "每个批次已增量保存，无需重写整个文件",
        })
    except Exception:
        pass


def _fallback_to_file_based_batches(
    file_groups: Dict[str, List[Dict]],
    existing_clusters: Dict,
) -> List[List[Dict]]:
    """若聚类失败或空，则回退为按文件一次处理"""
    fallback_batches: List[List[Dict]] = []
    
    # 收集所有未聚类的 gid（从所有候选 gid 中排除已聚类的）
    all_gids_in_file_groups = _collect_candidate_gids(file_groups)
    gid_to_item_fallback: Dict[int, Dict] = {}
    for _file, _items in file_groups.items():
        for c in _items:
            try:
                _gid = int(c.get("gid", 0))
                if _gid >= 1:
                    gid_to_item_fallback[_gid] = c
            except Exception:
                pass
    
    # 如果还有未聚类的 gid，按文件分组创建批次
    if all_gids_in_file_groups:
        # 收集已聚类的 gid（从 cluster_report.jsonl）
        clustered_gids_fallback = set()
        for (_file_key, _batch_idx), cluster_recs in existing_clusters.items():
            for rec in cluster_recs:
                if rec.get("is_invalid", False):
                    continue
                gids_list = rec.get("gids", [])
                for _gid in gids_list:
                    try:
                        _gid_int = int(_gid)
                        if _gid_int >= 1:
                            clustered_gids_fallback.add(_gid_int)
                    except Exception:
                        pass
        
        unclustered_gids_fallback = all_gids_in_file_groups - clustered_gids_fallback
        if unclustered_gids_fallback:
            # 按文件分组未聚类的 gid
            from collections import defaultdict
            unclustered_by_file: Dict[str, List[Dict]] = defaultdict(list)
            for _gid in unclustered_gids_fallback:
                item = gid_to_item_fallback.get(_gid)
                if item:
                    file_key = str(item.get("file") or "")
                    unclustered_by_file[file_key].append(item)
            
            # 为每个文件创建批次
            for _file, _items in unclustered_by_file.items():
                if _items:
                    fallback_batches.append(_items)
    
    return fallback_batches


def _process_clustering_phase(
    compact_candidates: List[Dict],
    entry_path: str,
    langs: List[str],
    cluster_limit: int,
    llm_group: Optional[str],
    sec_dir,
    progress_path,
    status_mgr,
    _progress_append,
    force_save_memory: bool = False,
) -> tuple[List[List[Dict]], List[Dict]]:
    """处理聚类阶段，返回(cluster_batches, invalid_clusters_for_review)"""
    # 初始化聚类上下文
    (
        _file_groups,
        _existing_clusters,
        (_write_cluster_batch_snapshot, _write_cluster_report_snapshot),
        cluster_batches,
        cluster_records,
        invalid_clusters_for_review,
        clustered_gids,
    ) = _initialize_clustering_context(compact_candidates, sec_dir, progress_path, _progress_append)
    
    # 收集所有候选的 gid（用于检查未聚类的 gid）
    all_candidate_gids_in_clustering = _collect_candidate_gids(_file_groups)
    
    # 检查是否有未聚类的 gid
    unclustered_gids = _check_unclustered_gids(all_candidate_gids_in_clustering, clustered_gids)
    
    # 如果有未聚类的 gid，继续执行聚类
    if unclustered_gids:
        _execute_clustering_for_files(
            _file_groups,
            clustered_gids,
            cluster_batches,
            cluster_records,
            invalid_clusters_for_review,
            entry_path,
            langs,
            cluster_limit,
            llm_group,
            status_mgr,
            _progress_append,
            _write_cluster_batch_snapshot,
            force_save_memory=force_save_memory,
        )
    
    # 记录聚类阶段完成
    _record_clustering_completion(sec_dir, cluster_records, compact_candidates, _progress_append)
    
    # 复核Agent：验证所有标记为无效的聚类
    cluster_batches = _process_review_phase(
        invalid_clusters_for_review,
        entry_path,
        langs,
        llm_group,
        status_mgr,
        _progress_append,
        cluster_batches,
    )
    
    # 若聚类失败或空，则回退为"按文件一次处理"
    if not cluster_batches:
        fallback_batches = _fallback_to_file_based_batches(_file_groups, _existing_clusters)
        cluster_batches.extend(fallback_batches)
    
    # 完整性检查：确保所有候选的 gid 都已被聚类
    _check_and_supplement_missing_gids(
        _file_groups,
        cluster_batches,
        invalid_clusters_for_review,
        sec_dir,
        _progress_append,
    )
    
    return cluster_batches, invalid_clusters_for_review


def _process_verification_phase(
    cluster_batches: List[List[Dict]],
    entry_path: str,
    langs: List[str],
    llm_group: Optional[str],
    sec_dir,
    progress_path,
    status_mgr,
    _progress_append,
    _append_report,
    enable_verification: bool = True,
    force_save_memory: bool = False,
) -> List[Dict]:
    """处理验证阶段，返回所有已保存的告警"""
    batches: List[List[Dict]] = cluster_batches
    total_batches = len(batches)
    
    # 从 agent_issues.jsonl 中读取已处理的 gid
    processed_gids_from_issues = _load_processed_gids_from_issues(sec_dir)
    
    # 从 progress.jsonl 中读取已完成的批次
    completed_batch_ids = _load_completed_batch_ids(progress_path)
    
    if completed_batch_ids:
        try:
            typer.secho(f"[jarvis-sec] 断点恢复：从 progress.jsonl 读取到 {len(completed_batch_ids)} 个已完成的批次", fg=typer.colors.BLUE)
        except Exception:
            pass
    
    # 更新验证阶段状态
    if total_batches > 0:
        status_mgr.update_verification(
            current_batch=0,
            total_batches=total_batches,
            message="开始安全验证..."
        )
    
    meta_records: List[Dict] = []
    gid_counts: Dict[int, int] = {}
    
    for bidx, batch in enumerate(batches, start=1):
        task_id = f"JARVIS-SEC-Batch-{bidx}"
        batch_file = batch[0].get("file") if batch else None
        
        # 检查批次是否已完成：优先检查 progress.jsonl 中的批次状态
        is_batch_completed = False
        
        # 方法1：检查 progress.jsonl 中是否有该批次的完成记录
        if task_id in completed_batch_ids:
            is_batch_completed = True
        else:
            # 方法2：检查批次中的所有 gid 是否都在 agent_issues.jsonl 中
            batch_gids = set()
            for item in batch:
                try:
                    _gid = int(item.get("gid", 0))
                    if _gid >= 1:
                        batch_gids.add(_gid)
                except Exception:
                    pass
            
            # 如果批次中的所有 gid 都已处理，则认为该批次已完成
            if batch_gids and processed_gids_from_issues and batch_gids.issubset(processed_gids_from_issues):
                is_batch_completed = True
        
        if is_batch_completed:
            try:
                typer.secho(f"[jarvis-sec] 跳过批次 {bidx}/{total_batches}：已在之前的运行中完成", fg=typer.colors.GREEN)
            except Exception:
                pass
            # 更新进度但不实际处理
            status_mgr.update_verification(
                current_batch=bidx,
                total_batches=total_batches,
                batch_id=task_id,
                file_name=batch_file,
                message=f"跳过已完成的批次 {bidx}/{total_batches}"
            )
            continue
        
        # 处理验证批次
        _process_verification_batch(
            batch,
            bidx,
            total_batches,
            entry_path,
            langs,
            llm_group,
            status_mgr,
            _progress_append,
            _append_report,
            meta_records,
            gid_counts,
            sec_dir,
            enable_verification=enable_verification,
            force_save_memory=force_save_memory,
        )
    
    # 从 agent_issues.jsonl 读取所有已保存的告警
    return _load_all_issues_from_file(sec_dir)


def _try_parse_summary_report(text: str) -> tuple[Optional[object], Optional[str]]:
    """
    从摘要文本中提取 <REPORT>...</REPORT> 内容，并解析为对象（dict 或 list，使用 JSON）。
    返回(解析结果, 错误信息)
    如果解析成功，返回(data, None)
    如果解析失败，返回(None, 错误信息)
    """
    start = text.find("<REPORT>")
    end = text.find("</REPORT>")
    if start == -1 or end == -1 or end <= start:
        return None, "未找到 <REPORT> 或 </REPORT> 标签，或标签顺序错误"
    content = text[start + len("<REPORT>"):end].strip()
    if not content:
        return None, "JSON 内容为空"
    try:
        try:
            data = json.loads(content)
        except Exception as json_err:
            error_msg = f"JSON 解析失败: {str(json_err)}"
            return None, error_msg
        if isinstance(data, (dict, list)):
            return data, None
        return None, f"JSON 解析结果不是字典或数组，而是 {type(data).__name__}"
    except Exception as e:
        return None, f"解析过程发生异常: {str(e)}"


__all__ = [
    
    "run_security_analysis",

    "direct_scan",
    "run_with_agent",
]