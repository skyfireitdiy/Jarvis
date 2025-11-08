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

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_sec.workflow import direct_scan, run_with_agent
from jarvis.jarvis_tools.registry import ToolRegistry


def _build_summary_prompt() -> str:
    """
    构建摘要提示词：要求以 <REPORT>...</REPORT> 包裹的 YAML 输出（仅YAML）。
    系统提示词不强制规定主对话输出格式，仅在摘要中给出结构化结果。
    """
    return """
请将本轮"安全子任务（单点验证）"的结构化结果仅放入以下标记中，并使用 YAML 数组对象形式输出。
仅输出全局编号（gid）与详细理由（不含位置信息），gid 为全局唯一的数字编号。

示例1：有告警的情况（has_risk: true）
<REPORT>
- gid: 1
  has_risk: true
  preconditions: "输入字符串 src 的长度大于等于 dst 的缓冲区大小"
  trigger_path: "调用路径推导：main() -> handle_network_request() -> parse_packet() -> foobar() -> strcpy()。数据流：网络数据包通过 handle_network_request() 接收，传递给 parse_packet() 解析，parse_packet() 未对数据长度进行校验，直接将 src 传递给 foobar()，foobar() 调用 strcpy(dst, src) 时未检查 src 长度，可导致缓冲区溢出。关键调用点：parse_packet() 函数未对输入长度进行校验。"
  consequences: "缓冲区溢出，可能引发程序崩溃或任意代码执行"
  suggestions: "使用 strncpy_s 或其他安全的字符串复制函数"
</REPORT>

示例2：误报或无问题（返回空数组）
<REPORT>
[]
</REPORT>

要求：
- 只能在 <REPORT> 与 </REPORT> 中输出 YAML 数组，且不得出现其他文本。
- 若确认本批次全部为误报或无问题，请返回空数组 []。
- 数组元素为对象，包含字段：
  - gid: 整数（全局唯一编号）
  - has_risk: 布尔值 (true/false)，表示该项是否存在真实安全风险。
  - preconditions: 字符串（触发漏洞的前置条件，仅当 has_risk 为 true 时必需）
  - trigger_path: 字符串（漏洞的触发路径，必须包含完整的调用路径推导，包括：1) 可控输入的来源；2) 从输入源到缺陷代码的完整调用链（函数调用序列）；3) 每个调用点的数据校验情况；4) 触发条件。格式示例："调用路径推导：函数A() -> 函数B() -> 函数C() -> 缺陷代码。数据流：输入来源 -> 传递路径。关键调用点：函数B()未做校验。"，仅当 has_risk 为 true 时必需）
  - consequences: 字符串（漏洞被触发后可能导致的后果，仅当 has_risk 为 true 时必需）
  - suggestions: 字符串（修复或缓解该漏洞的建议，仅当 has_risk 为 true 时必需）
- 不要在数组元素中包含 file/line/pattern 等位置信息；写入 jsonl 时系统会结合原始候选信息。
- **关键**：仅当 `has_risk` 为 `true` 时，才会被记录为确认的问题。对于确认是误报的条目，请确保 `has_risk` 为 `false` 或不输出该条目。
- **输出格式**：有告警的条目必须包含所有字段（gid, has_risk, preconditions, trigger_path, consequences, suggestions）；无告警的条目只需包含 gid 和 has_risk。
- **调用路径推导要求**：trigger_path 字段必须包含完整的调用路径推导，不能省略或简化。必须明确说明从可控输入到缺陷代码的完整调用链，以及每个调用点的校验情况。如果无法推导出完整的调用路径，应该判定为误报（has_risk: false）。
""".strip()


def _build_verification_summary_prompt() -> str:
    """
    构建验证 Agent 的摘要提示词：验证分析 Agent 给出的结论是否正确。
    """
    return """
请将本轮"验证分析结论"的结构化结果仅放入以下标记中，并使用 YAML 数组对象形式输出。
你需要验证分析 Agent 给出的结论是否正确，包括前置条件、触发路径、后果和建议是否合理。

示例1：验证通过（is_valid: true）
<REPORT>
- gid: 1
  is_valid: true
  verification_notes: "分析结论正确，前置条件合理，触发路径清晰，后果评估准确"
</REPORT>

示例2：验证不通过（is_valid: false）
<REPORT>
- gid: 1
  is_valid: false
  verification_notes: "前置条件过于宽泛，实际代码中已有输入校验，触发路径不成立"
</REPORT>

要求：
- 只能在 <REPORT> 与 </REPORT> 中输出 YAML 数组，且不得出现其他文本。
- 数组元素为对象，包含字段：
  - gid: 整数（全局唯一编号，对应分析 Agent 给出的 gid）
  - is_valid: 布尔值 (true/false)，表示分析 Agent 的结论是否正确
  - verification_notes: 字符串（验证说明，解释为什么结论正确或不正确）
- 必须对所有输入的 gid 进行验证，不能遗漏。
- 如果验证通过（is_valid: true），则保留该告警；如果验证不通过（is_valid: false），则视为误报，不记录为问题。
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


def run_security_analysis(
    entry_path: str,
    languages: Optional[List[str]] = None,
    llm_group: Optional[str] = None,
    report_file: Optional[str] = None,
    cluster_limit: int = 50,
    exclude_dirs: Optional[List[str]] = None,
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
            print(f"[JARVIS-SEC] 从状态文件恢复: 阶段={stage}, 进度={progress}%, {message}")
    except Exception:
        pass

    # 进度文件（JSONL，断点续扫）
    from pathlib import Path as _Path
    from datetime import datetime as _dt
    progress_path = _Path(entry_path) / ".jarvis/sec" / "progress.jsonl"

    def _progress_append(rec: Dict) -> None:
        try:
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            rec = dict(rec)
            rec.setdefault("timestamp", _dt.utcnow().isoformat() + "Z")
            import json as _json
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
            import json as _json
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

    # 1) 启发式扫描（支持断点续扫）
    from pathlib import Path as _Path
    _heuristic_path = _Path(entry_path) / ".jarvis/sec" / "heuristic_issues.jsonl"
    candidates: List[Dict] = []
    summary: Dict = {}

    if _heuristic_path.exists():
        try:
            print(f"[JARVIS-SEC] 从 {_heuristic_path} 恢复启发式扫描")
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
            print(f"[JARVIS-SEC] 恢复启发式扫描失败，执行完整扫描: {e}")
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
            print(f"[JARVIS-SEC] 已将 {len(candidates)} 个启发式扫描问题写入 {_heuristic_path}")
        except Exception:
            pass
    else:
        # 从断点恢复启发式扫描结果
        status_mgr.update_pre_scan(
            issues_found=len(candidates),
            message=f"从断点恢复，已发现 {len(candidates)} 个候选问题"
        )

    # 2) 将候选问题精简为子任务清单，控制上下文长度
    def _compact(it: Dict) -> Dict:
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

    compact_candidates = [_compact(it) for it in candidates]
    # 为所有候选分配全局唯一数字ID（gid: 1..N），用于跨批次/跨文件统一编号与跟踪
    for i, it in enumerate(compact_candidates, start=1):
        try:
            it["gid"] = i
        except Exception:
            pass
    # 为所有启发式候选分配稳定ID（HID），聚类改由 Agent 执行

    # candidates already compacted; no additional enrichment required
    try:
        from collections import defaultdict as _dd
        groups: Dict[str, List[Dict]] = _dd(list)
        for it in compact_candidates:
            groups[str(it.get("file") or "")].append(it)
        selected_file: Optional[str] = None
        selected_candidates: List[Dict] = []
        if groups:
            # 选择告警最多的文件作为本批次处理目标
            selected_file, items = max(groups.items(), key=lambda kv: len(kv[1]))

            # 为实现“所有告警分批处理”，此处不截断；后续改为按“聚类”逐个提交给验证Agent（不再使用 batch_limit）
            selected_candidates = items
            try:
                print(f"[JARVIS-SEC] 批次选择: 文件={selected_file} 数量={len(selected_candidates)}/{len(items)}")
            except Exception:
                pass
            # 记录批次选择信息
            _progress_append({
                "event": "batch_selection",
                "selected_file": selected_file,
                "selected_count": len(selected_candidates),
                "total_in_file": len(items),
            })
        # 将待处理候选替换为本批次（仅一个文件的前 n 条）
        # keep all files for clustering; do not narrow to a single file
        # compact_candidates = selected_candidates
    except Exception:
        # 分组失败时保留原候选（不进行批量限制）
        pass
    # 保留所有候选以逐条由Agent验证（当前批次）
    json.dumps(compact_candidates, ensure_ascii=False)
    # 进度总数
    len(compact_candidates)
    # 将检测出的 issues 增量写入报告文件（JSONL），便于长任务中途查看
    def _append_report(items, source: str, task_id: str, cand: Dict):
        """
        将当前子任务的检测结果追加写入 JSONL 报告文件（每行一个 issue）。
        仅当 items 非空时写入。
        """
        if not items:
            return
        try:
            from pathlib import Path as _Path

            path = _Path(report_file) if report_file else _Path(entry_path) / ".jarvis/sec" / "agent_issues.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                for item in items:
                    line = json.dumps(item, ensure_ascii=False)
                    f.write(line + "\n")
            try:
                print(f"[JARVIS-SEC] 已将 {len(items)} 个问题写入 {path}")
            except Exception:
                pass
        except Exception:
            # 报告写入失败不影响主流程
            pass

    # 3) 按批次将候选问题提交给单Agent验证（一次提交一个文件的前 n 条，直到该文件全部处理完）
    all_issues: List[Dict] = []
    meta_records: List[Dict] = []

    # 仅处理当前批次选择的文件的候选（compact_candidates 前面已替换为该文件的全部候选）
    # 基于进度文件跳过已完成的候选
    def _sig_of(c: Dict) -> str:
        return f"{c.get('language','')}|{c.get('file','')}|{c.get('line','')}|{c.get('pattern','')}"

    # 按文件分组构建待聚类集合，并逐文件创建Agent进行一次聚类（提供该文件的告警作为上下文）
    from collections import defaultdict as _dd2
    _file_groups: Dict[str, List[Dict]] = _dd2(list)
    for it in compact_candidates:
        _file_groups[str(it.get("file") or "")].append(it)

    cluster_batches: List[List[Dict]] = []
    cluster_records: List[Dict] = []
    # 收集所有标记为无效的聚类，用于后续复核
    invalid_clusters_for_review: List[Dict] = []

    # 解析聚类输出（仅 YAML）
    def _parse_clusters_from_text(text: str):
        try:
            start = text.find("<CLUSTERS>")
            end = text.find("</CLUSTERS>")
            if start == -1 or end == -1 or end <= start:
                return None
            content = text[start + len("<CLUSTERS>"):end].strip()
            import yaml as _yaml3  # type: ignore
            data = _yaml3.safe_load(content)
            if isinstance(data, list):
                return data
            return None
        except Exception:
            return None

    # 读取已有聚类报告以支持断点（若存在则按文件+批次复用既有聚类结果）
    _existing_clusters: Dict[tuple[str, int], List[Dict]] = {}
    try:
        from pathlib import Path as _Path2
        import json as _json
        _cluster_path = _Path2(entry_path) / ".jarvis/sec" / "cluster_report.jsonl"
        if _cluster_path.exists():
            try:
                with _cluster_path.open("r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        rec = _json.loads(line)
                        if not isinstance(rec, dict):
                            continue
                        f = str(rec.get("file") or "")
                        bidx = int(rec.get("batch_index", 1) or 1)
                        _existing_clusters.setdefault((f, bidx), []).append(rec)
            except Exception:
                _existing_clusters = {}
    except Exception:
        _existing_clusters = {}

    # 快照写入函数：每处理完一个聚类批次后，写入当前聚类结果，支持断点恢复
    def _write_cluster_report_snapshot():
        try:
            from pathlib import Path as _Path2
            import json as _json
            _cluster_path = _Path2(entry_path) / ".jarvis/sec" / "cluster_report.jsonl"
            _cluster_path.parent.mkdir(parents=True, exist_ok=True)
            
            with _cluster_path.open("w", encoding="utf-8") as f:
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

    total_files_to_cluster = len(_file_groups)
    # 更新聚类阶段状态
    if total_files_to_cluster > 0:
        status_mgr.update_clustering(
            current_file=0,
            total_files=total_files_to_cluster,
            message="开始聚类分析..."
        )
    for _file_idx, (_file, _items) in enumerate(_file_groups.items(), start=1):
        print(f"\n[JARVIS-SEC] 聚类文件 {_file_idx}/{total_files_to_cluster}: {_file}")
        # 更新当前文件进度
        status_mgr.update_clustering(
            current_file=_file_idx,
            total_files=total_files_to_cluster,
            file_name=_file,
            message=f"正在聚类文件 {_file_idx}/{total_files_to_cluster}: {_file}"
        )
        # 过滤掉已完成
        pending_in_file: List[Dict] = []
        for c in _items:
            if _sig_of(c) not in done_sigs:
                pending_in_file.append(c)
        if not pending_in_file:
            continue

        # 优化：如果文件只有一个告警，跳过聚类，直接写入
        if len(pending_in_file) == 1:
            single_item = pending_in_file[0]
            single_gid = single_item.get("gid", 0)
            # 为单个告警创建默认验证条件
            default_verification = f"验证候选 {single_gid} 的安全风险"
            single_item["verify"] = default_verification
            cluster_batches.append([single_item])
            cluster_records.append(
                {
                    "file": _file,
                    "verification": default_verification,
                    "gids": [single_gid],
                    "count": 1,
                    "batch_index": 1,
                    "note": "单告警跳过聚类",
                }
            )
            # 标记进度
            _progress_append(
                {
                    "event": "cluster_status",
                    "status": "done",
                    "file": _file,
                    "batch_index": 1,
                    "skipped": True,
                    "reason": "single_alert",
                }
            )
            # 写入快照
            _write_cluster_report_snapshot()
            print(f"[JARVIS-SEC] 文件 {_file} 仅有一个告警（gid={single_gid}），跳过聚类直接写入")
            continue

        # 构造聚类Agent（每个文件一个Agent，按批次聚类）
        cluster_system_prompt = """
# 单Agent聚类约束
- 你的任务是对同一文件内的启发式候选进行"验证条件一致性"聚类。
- 验证条件：为了确认是否存在漏洞需要成立/验证的关键前置条件。例如："指针p在解引用前非空""拷贝长度不超过目标缓冲区容量"等。
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
        import json as _json2
        cluster_summary_prompt = """
请仅在 <CLUSTERS> 与 </CLUSTERS> 中输出 YAML 数组：
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
  - 严格要求：仅输出位于 <CLUSTERS> 与 </CLUSTERS> 间的 YAML 数组，其他位置不输出任何文本
  - **必须要求**：输入JSON中的所有gid都必须被分类，不能遗漏任何一个gid。所有gid必须出现在某个聚类的gids数组中。
  - **必须要求**：每个聚类元素必须包含 is_invalid 字段，且值必须为 true 或 false，不能省略。
  - **必须要求**：当 is_invalid 为 true 时，必须提供 invalid_reason 字段，且理由必须充分详细。
  - 相同验证条件的候选合并为同一项
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
<CLUSTERS>
- verification: ""
  gids: []
  is_invalid: false
</CLUSTERS>
        """.strip()

        # 将该文件的告警按 cluster_limit 分批（每批最多 cluster_limit 条）
        _limit = cluster_limit if isinstance(cluster_limit, int) and cluster_limit > 0 else 50
        _chunks: List[List[Dict]] = [pending_in_file[i:i + _limit] for i in range(0, len(pending_in_file), _limit)]

        for _chunk_idx, _chunk in enumerate(_chunks, start=1):
            if not _chunk:
                continue
            # 构造本批次候选列表（元素已包含全局 gid）
            pending_in_file_with_ids = list(_chunk)

            # 若断点存在：优先使用已有聚类结果复建批次，跳过Agent运行（仅支持 gids）
            _key = (_file, _chunk_idx)
            if _key in _existing_clusters:
                # 收集输入的gid
                input_gids_resume = set()
                gid_to_item_resume: Dict[int, Dict] = {}
                for it in pending_in_file_with_ids:
                    try:
                        _gid = int(it.get("gid", 0))
                        if _gid >= 1:
                            input_gids_resume.add(_gid)
                            gid_to_item_resume[_gid] = it
                    except Exception:
                        pass
                
                # 收集已分类的gid
                classified_gids_resume = set()
                for rec in _existing_clusters.get(_key, []):
                    verification = str(rec.get("verification", "")).strip()
                    gids_list = rec.get("gids", [])
                    # 如果 is_invalid 字段缺失，跳过该记录（格式不完整，需要重新聚类）
                    if "is_invalid" not in rec:
                        try:
                            print(f"[JARVIS-SEC] 断点恢复：记录缺少 is_invalid 字段，跳过该记录，将重新聚类")
                        except Exception:
                            pass
                        continue
                    is_invalid_resume = rec["is_invalid"]
                    norm_keys: List[int] = []
                    if isinstance(gids_list, list):
                        for x in gids_list:
                            try:
                                xi = int(x)
                                if xi >= 1:
                                    norm_keys.append(xi)
                                    classified_gids_resume.add(xi)
                            except Exception:
                                continue
                    members: List[Dict] = []
                    for k in norm_keys:
                        it = gid_to_item_resume.get(k)
                        if it:
                            it["verify"] = verification
                            members.append(it)
                    
                    # 如果断点恢复的记录标记为无效，不恢复该聚类
                    if is_invalid_resume:
                        invalid_gids_resume = [m.get("gid") for m in members]
                        try:
                            print(f"[JARVIS-SEC] 断点恢复：跳过无效聚类（gids={invalid_gids_resume}）")
                        except Exception:
                            pass
                        # 记录到进度文件
                        _progress_append(
                            {
                                "event": "cluster_invalid_resumed",
                                "file": _file,
                                "batch_index": _chunk_idx,
                                "gids": invalid_gids_resume,
                                "verification": verification,
                                "count": len(members),
                            }
                        )
                    elif members:
                        # 只有非无效的聚类才恢复
                        cluster_batches.append(members)
                        cluster_records.append(
                            {
                                "file": _file,
                                "verification": verification,
                                "gids": [m.get("gid") for m in members],
                                "count": len(members),
                                "batch_index": _chunk_idx,
                                "is_invalid": False,
                            }
                        )
                
                # 检查断点恢复的完整性
                missing_gids_resume = input_gids_resume - classified_gids_resume
                if missing_gids_resume:
                    print(f"[JARVIS-SEC] 断点恢复：发现遗漏的gid {sorted(list(missing_gids_resume))}，将重新聚类")
                    # 不跳过，继续执行Agent运行以补充遗漏的gid
                else:
                    # 所有gid都已分类，标记进度（断点复用）
                    _progress_append(
                        {
                            "event": "cluster_status",
                            "status": "done",
                            "file": _file,
                            "batch_index": _chunk_idx,
                            "reused": True,
                            "clusters_count": len(_existing_clusters.get(_key, [])),
                        }
                    )
                    # 写入快照（断点）
                    _write_cluster_report_snapshot()
                    continue

            # 记录聚类批次开始（进度）
            _progress_append(
                {
                    "event": "cluster_status",
                    "status": "running",
                    "file": _file,
                    "batch_index": _chunk_idx,
                    "total_in_batch": len(pending_in_file_with_ids),
                }
            )

            cluster_task = f"""
# 聚类任务（分析输入）
上下文：
- entry_path: {entry_path}
- file: {_file}
- languages: {langs}

候选(JSON数组，包含 gid/file/line/pattern/category/evidence)：
{_json2.dumps(pending_in_file_with_ids, ensure_ascii=False, indent=2)}
            """.strip()

            agent_kwargs_cluster: Dict = dict(
                system_prompt=cluster_system_prompt,
                name=f"JARVIS-SEC-Cluster::{_file}::batch{_chunk_idx}",
                auto_complete=True,
                need_summary=True,
                summary_prompt=cluster_summary_prompt,
                non_interactive=True,
                in_multi_agent=False,
                use_methodology=False,
                use_analysis=False,
                plan=False,
                output_handler=[ToolRegistry()],
                disable_file_edit=True,
                use_tools=["read_code", "execute_script", "save_memory", "retrieve_memory"],  # 添加保存和召回记忆工具
            )
            if llm_group:
                agent_kwargs_cluster["model_group"] = llm_group
            cluster_agent = Agent(**agent_kwargs_cluster)

            # 捕捉 AFTER_SUMMARY
            try:
                from jarvis.jarvis_agent.events import AFTER_SUMMARY as _AFTER_SUMMARY2  # type: ignore
            except Exception:
                _AFTER_SUMMARY2 = None  # type: ignore
            _cluster_summary: Dict[str, str] = {"text": ""}
            if _AFTER_SUMMARY2:
                def _on_after_summary_cluster(**kwargs):
                    try:
                        _cluster_summary["text"] = str(kwargs.get("summary", "") or "")
                    except Exception:
                        _cluster_summary["text"] = ""
                try:
                    cluster_agent.event_bus.subscribe(_AFTER_SUMMARY2, _on_after_summary_cluster)
                except Exception:
                    pass

            # 运行聚类Agent（带完整性校验，无限重试直到所有gid都被分类）
            cluster_items = None
            input_gids = set()
            missing_gids = set()  # 初始化，避免未定义错误
            for it in pending_in_file_with_ids:
                try:
                    _gid = int(it.get("gid", 0))
                    if _gid >= 1:
                        input_gids.add(_gid)
                except Exception:
                    pass
            
            _attempt = 0
            use_direct_model = False  # 标记是否使用直接模型调用
            
            while True:
                _attempt += 1
                _cluster_summary["text"] = ""
                
                if use_direct_model:
                    # 格式校验失败后，直接调用模型接口
                    # 构造包含摘要提示词和具体错误信息的完整提示
                    error_guidance = ""
                    if error_details:
                        error_guidance = f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n" + "\n".join(f"- {detail}" for detail in error_details)
                    if missing_gids:
                        missing_gids_list = sorted(list(missing_gids))
                        missing_count = len(missing_gids)
                        error_guidance += f"\n\n**完整性错误：遗漏了 {missing_count} 个 gid，这些 gid 必须被分类：**\n" + ", ".join(str(gid) for gid in missing_gids_list)
                    
                    full_prompt = f"{cluster_task}{error_guidance}\n\n{cluster_summary_prompt}"
                    try:
                        response = cluster_agent.model.chat_until_success(full_prompt)  # type: ignore
                        # 从响应中提取摘要（假设摘要提示词会引导模型输出 <REPORT> 块）
                        _cluster_summary["text"] = response
                    except Exception as e:
                        try:
                            print(f"[JARVIS-SEC] 直接模型调用失败: {e}，回退到 run()")
                        except Exception:
                            pass
                        cluster_agent.run(cluster_task)
                else:
                    # 第一次使用 run()，让 Agent 完整运行（可能使用工具）
                    cluster_agent.run(cluster_task)
                
                cluster_items = _parse_clusters_from_text(_cluster_summary.get("text", ""))
                
                # 校验结构
                valid = True
                error_details = []
                if not isinstance(cluster_items, list) or not cluster_items:
                    valid = False
                    error_details.append("结果不是数组或数组为空")
                else:
                    for idx, it in enumerate(cluster_items):
                        if not isinstance(it, dict):
                            valid = False
                            error_details.append(f"元素{idx}不是字典")
                            break
                        vals = it.get("gids", [])
                        if not isinstance(it.get("verification", ""), str) or not isinstance(vals, list):
                            valid = False
                            error_details.append(f"元素{idx}的verification或gids格式错误")
                            break
                        # 校验 is_invalid 字段（必填）
                        if "is_invalid" not in it:
                            valid = False
                            error_details.append(f"元素{idx}缺少is_invalid字段（必填）")
                            break
                        is_invalid_val = it.get("is_invalid")
                        if not isinstance(is_invalid_val, bool):
                            valid = False
                            error_details.append(f"元素{idx}的is_invalid不是布尔值")
                            break
                        # 如果is_invalid为true，必须提供invalid_reason
                        if is_invalid_val is True:
                            invalid_reason = it.get("invalid_reason", "")
                            if not isinstance(invalid_reason, str) or not invalid_reason.strip():
                                valid = False
                                error_details.append(f"元素{idx}的is_invalid为true但缺少invalid_reason字段或理由为空（必填）")
                                break
                
                # 完整性校验：检查所有输入的gid是否都被分类
                missing_gids = set()
                if valid:
                    classified_gids = set()
                    for cl in cluster_items:
                        raw_gids = cl.get("gids", [])
                        if isinstance(raw_gids, list):
                            for x in raw_gids:
                                try:
                                    xi = int(x)
                                    if xi >= 1:
                                        classified_gids.add(xi)
                                except Exception:
                                    continue
                    
                    missing_gids = input_gids - classified_gids
                    if not missing_gids:
                        # 所有gid都被分类，校验通过
                        print(f"[JARVIS-SEC] 聚类完整性校验通过，所有gid已分类（共尝试 {_attempt} 次）")
                        break
                    else:
                        # 有遗漏的gid，需要重试
                        missing_gids_list = sorted(list(missing_gids))
                        missing_count = len(missing_gids)
                        print(f"[JARVIS-SEC] 聚类完整性校验失败：遗漏的gid: {missing_gids_list}（{missing_count}个），重试第 {_attempt} 次（使用直接模型调用）")
                        # 格式校验失败，后续重试使用直接模型调用
                        use_direct_model = True
                        # 更新任务，明确指出遗漏的gid
                        cluster_task = f"""
# 聚类任务（分析输入）
上下文：
- entry_path: {entry_path}
- file: {_file}
- languages: {langs}

候选(JSON数组，包含 gid/file/line/pattern/category/evidence)：
{_json2.dumps(pending_in_file_with_ids, ensure_ascii=False, indent=2)}

**重要提示**：上一次聚类结果中遗漏了以下gid（共{missing_count}个），这些gid必须被分类：
遗漏的gid: {missing_gids_list}

请确保所有输入的gid都被分类，包括上述遗漏的gid。请仔细检查每个gid，确保它们都出现在某个聚类的gids数组中。
                        """.strip()
                        valid = False
                
                if not valid:
                    # 格式校验失败，后续重试使用直接模型调用
                    use_direct_model = True
                    # 如果是格式错误（非遗漏gid），也继续重试
                    if not missing_gids:
                        if error_details:
                            print(f"[JARVIS-SEC] 聚类结果格式无效（{'; '.join(error_details)}），重试第 {_attempt} 次（使用直接模型调用）")
                            # 更新任务，明确指出格式错误
                            cluster_task = f"""
# 聚类任务（分析输入）
上下文：
- entry_path: {entry_path}
- file: {_file}
- languages: {langs}

候选(JSON数组，包含 gid/file/line/pattern/category/evidence)：
{_json2.dumps(pending_in_file_with_ids, ensure_ascii=False, indent=2)}

**重要提示**：上一次聚类结果格式无效：{'; '.join(error_details)}

请确保每个聚类元素都包含以下必填字段：
- verification: 字符串（验证条件描述）
- gids: 整数数组（候选的全局唯一编号）
- is_invalid: 布尔值（必填，true 或 false，不能省略）

请重新输出正确的聚类结果。
                            """.strip()
                        else:
                            print(f"[JARVIS-SEC] 聚类结果格式无效，重试第 {_attempt} 次（使用直接模型调用）")
                    cluster_items = None

            # 合并聚类结果
            if isinstance(cluster_items, list) and cluster_items:
                # id_to_item removed; use gid_to_item only
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

                # 再次检查格式完整性：如果缺少is_invalid字段，应该触发重试而不是跳过
                # 这种情况理论上不应该发生（格式校验已检查），但如果发生了，说明格式校验有问题
                has_format_error = False
                format_error_details = []
                for idx, cl in enumerate(cluster_items):
                    if "is_invalid" not in cl:
                        has_format_error = True
                        raw_gids = cl.get("gids", [])
                        format_error_details.append(f"元素{idx}缺少is_invalid字段（gids={raw_gids}）")
                
                if has_format_error:
                    # 格式错误，应该重试而不是继续处理
                    print(f"[JARVIS-SEC] 警告：聚类结果缺少 is_invalid 字段（{'; '.join(format_error_details)}），这是格式错误，触发重试")
                    # 重新进入循环进行重试
                    cluster_items = None
                    use_direct_model = True
                    # 更新任务，明确指出格式错误
                    cluster_task = f"""
# 聚类任务（分析输入）
上下文：
- entry_path: {entry_path}
- file: {_file}
- languages: {langs}

候选(JSON数组，包含 gid/file/line/pattern/category/evidence)：
{_json2.dumps(pending_in_file_with_ids, ensure_ascii=False, indent=2)}

**重要提示**：上一次聚类结果格式无效：{'; '.join(format_error_details)}

请确保每个聚类元素都包含以下必填字段：
- verification: 字符串（验证条件描述）
- gids: 整数数组（候选的全局唯一编号）
- is_invalid: 布尔值（必填，true 或 false，不能省略）

请重新输出正确的聚类结果。
                    """.strip()
                    # 继续while循环重试（通过设置cluster_items为None，下次循环会重新运行Agent）
                    continue

                _merged_count = 0
                _invalid_count = 0
                classified_gids_final = set()
                for cl in cluster_items:
                    verification = str(cl.get("verification", "")).strip()
                    raw_gids = cl.get("gids", [])
                    # 此时is_invalid字段一定存在（已通过上面的检查）
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
                                # gid解析失败，跳过该gid（格式错误不应该被计入）
                                pass
                    members: List[Dict] = []
                    for k in norm_keys:
                        it = gid_to_item.get(k)
                        if it:
                            it["verify"] = verification
                            members.append(it)
                    
                    # 如果标记为无效，收集到复核列表，不写入聚类批次和记录，但记录日志
                    if is_invalid:
                        _invalid_count += 1
                        invalid_gids = [m.get("gid") for m in members]
                        invalid_reason = str(cl.get("invalid_reason", "")).strip()
                        try:
                            print(f"[JARVIS-SEC] 聚类阶段判定为无效（gids={invalid_gids}），将提交复核Agent验证")
                        except Exception:
                            pass
                        # 收集到复核列表（包含候选、理由等信息）
                        invalid_clusters_for_review.append({
                            "file": _file,
                            "batch_index": _chunk_idx,
                            "gids": invalid_gids,
                            "verification": verification,
                            "invalid_reason": invalid_reason,
                            "members": members,  # 保存候选信息，用于复核后可能重新加入验证
                            "count": len(members),
                        })
                        # 记录到进度文件，但不写入聚类批次
                        _progress_append(
                            {
                                "event": "cluster_invalid",
                                "file": _file,
                                "batch_index": _chunk_idx,
                                "gids": invalid_gids,
                                "verification": verification,
                                "count": len(members),
                            }
                        )
                    elif members:
                        # 只有非无效的聚类才写入批次和记录
                        _merged_count += 1
                        cluster_batches.append(members)
                        cluster_records.append(
                            {
                                "file": _file,
                                "verification": verification,
                                "gids": [m.get("gid") for m in members],
                                "count": len(members),
                                "batch_index": _chunk_idx,
                                "is_invalid": False,
                            }
                        )
                
                # 最终完整性检查：如果仍有遗漏的gid，为每个遗漏的gid创建单独的聚类
                missing_gids_final = input_gids - classified_gids_final
                if missing_gids_final:
                    print(f"[JARVIS-SEC] 警告：仍有遗漏的gid {sorted(list(missing_gids_final))}，将为每个遗漏的gid创建单独聚类")
                    for missing_gid in sorted(missing_gids_final):
                        missing_item = gid_to_item.get(missing_gid)
                        if missing_item:
                            # 为遗漏的gid创建默认验证条件
                            default_verification = f"验证候选 {missing_gid} 的安全风险"
                            missing_item["verify"] = default_verification
                            cluster_batches.append([missing_item])
                            cluster_records.append(
                                {
                                    "file": _file,
                                    "verification": default_verification,
                                    "gids": [missing_gid],
                                    "count": 1,
                                    "batch_index": _chunk_idx,
                                    "note": "完整性校验补充的遗漏gid",
                                }
                            )
                            _merged_count += 1
                # 标记聚类批次完成（进度）
                _progress_append(
                    {
                        "event": "cluster_status",
                        "status": "done",
                        "file": _file,
                        "batch_index": _chunk_idx,
                        "clusters_count": _merged_count,
                        "invalid_clusters_count": _invalid_count,
                    }
                )
                # 如果有无效聚类，输出日志
                if _invalid_count > 0:
                    try:
                        print(f"[JARVIS-SEC] 聚类批次完成: 有效聚类={_merged_count}，无效聚类={_invalid_count}（已跳过）")
                    except Exception:
                        pass
                # 写入快照（断点）
                _write_cluster_report_snapshot()
    # 聚类报告（汇总所有文件）
    try:
        from pathlib import Path as _Path2
        import json as _json
        _cluster_path = _Path2(entry_path) / ".jarvis/sec" / "cluster_report.jsonl"
        _cluster_path.parent.mkdir(parents=True, exist_ok=True)

        with _cluster_path.open("w", encoding="utf-8") as f:
            for record in cluster_records:
                f.write(_json.dumps(record, ensure_ascii=False) + "\n")

        _progress_append(
            {
                "event": "cluster_report_written",
                "path": str(_cluster_path),
                "clusters": len(cluster_records),
                "total_candidates": len(compact_candidates),
            }
        )
    except Exception:
        pass

    # 复核Agent：验证所有标记为无效的聚类
    if invalid_clusters_for_review:
        print(f"\n[JARVIS-SEC] 开始复核 {len(invalid_clusters_for_review)} 个无效聚类...")
        status_mgr.update_review(
            current_review=0,
            total_reviews=len(invalid_clusters_for_review),
            message="开始复核无效聚类..."
        )
        
        # 构建复核Agent的系统提示词
        review_system_prompt = """
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
        
        # 构建复核摘要提示词
        review_summary_prompt = """
请将本轮"复核结论"的结构化结果仅放入以下标记中，并使用 YAML 数组对象形式输出。
你需要复核聚类Agent给出的无效理由是否充分，是否真的考虑了所有可能的路径。

示例1：理由充分（is_reason_sufficient: true）
<REPORT>
- gid: 1
  is_reason_sufficient: true
  review_notes: "聚类Agent已检查所有调用路径，确认所有调用者都有输入校验，理由充分"
</REPORT>

示例2：理由不充分（is_reason_sufficient: false）
<REPORT>
- gid: 1
  is_reason_sufficient: false
  review_notes: "聚类Agent遗漏了函数X的调用路径，该路径可能未做校验，理由不充分，需要重新验证"
</REPORT>

要求：
- 只能在 <REPORT> 与 </REPORT> 中输出 YAML 数组，且不得出现其他文本。
- 数组元素为对象，包含字段：
  - gid: 整数（全局唯一编号，对应无效聚类的gid）
  - is_reason_sufficient: 布尔值 (true/false)，表示无效理由是否充分
  - review_notes: 字符串（复核说明，解释为什么理由充分或不充分）
- 必须对所有输入的gid进行复核，不能遗漏。
- 如果理由不充分（is_reason_sufficient: false），该候选将重新加入验证流程；如果理由充分（is_reason_sufficient: true），该候选将被确认为无效。
        """.strip()
        
        # 按批次复核（每批最多10个无效聚类，避免上下文过长）
        review_batch_size = 10
        reviewed_clusters: List[Dict] = []
        reinstated_candidates: List[Dict] = []  # 重新加入验证的候选
        
        for review_idx in range(0, len(invalid_clusters_for_review), review_batch_size):
            review_batch = invalid_clusters_for_review[review_idx:review_idx + review_batch_size]
            current_review_num = review_idx // review_batch_size + 1
            total_review_batches = (len(invalid_clusters_for_review) + review_batch_size - 1) // review_batch_size
            
            print(f"[JARVIS-SEC] 复核批次 {current_review_num}/{total_review_batches}: {len(review_batch)} 个无效聚类")
            status_mgr.update_review(
                current_review=current_review_num,
                total_reviews=total_review_batches,
                message=f"正在复核批次 {current_review_num}/{total_review_batches}"
            )
            
            # 构建复核任务
            import json as _json_review
            review_task = f"""
# 复核无效聚类任务
上下文参数：
- entry_path: {entry_path}
- languages: {langs}

需要复核的无效聚类（JSON数组）：
{_json_review.dumps(review_batch, ensure_ascii=False, indent=2)}

请仔细复核每个无效聚类的invalid_reason是否充分，是否真的考虑了所有可能的路径、调用者和边界情况。
对于每个gid，请判断无效理由是否充分（is_reason_sufficient: true/false），并给出复核说明。
            """.strip()
            
            # 创建复核Agent
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
                plan=False,
                output_handler=[ToolRegistry()],
                disable_file_edit=True,
                use_tools=["read_code", "execute_script", "retrieve_memory", "save_memory"],
            )
            if llm_group:
                review_agent_kwargs["model_group"] = llm_group
            review_agent = Agent(**review_agent_kwargs)
            
            # 订阅复核Agent的摘要
            review_summary_container: Dict[str, str] = {"text": ""}
            try:
                from jarvis.jarvis_agent.events import AFTER_SUMMARY as _AFTER_SUMMARY_REVIEW
            except Exception:
                _AFTER_SUMMARY_REVIEW = None
            if _AFTER_SUMMARY_REVIEW:
                def _on_after_summary_review(**kwargs):
                    try:
                        review_summary_container["text"] = str(kwargs.get("summary", "") or "")
                    except Exception:
                        review_summary_container["text"] = ""
                try:
                    review_agent.event_bus.subscribe(_AFTER_SUMMARY_REVIEW, _on_after_summary_review)
                except Exception:
                    pass
            
            # 运行复核Agent（增加重试机制：格式校验失败时，使用直接模型调用）
            review_summary_container["text"] = ""
            review_results: Optional[List[Dict]] = None
            max_review_retries = 2  # 失败后最多重试2次（共执行最多3次）
            use_direct_model_review = False  # 标记是否使用直接模型调用
            
            for review_attempt in range(max_review_retries + 1):
                review_summary_container["text"] = ""
                
                if use_direct_model_review:
                    # 格式校验失败后，直接调用模型接口
                    # 构造包含摘要提示词和具体错误信息的完整提示
                    review_summary_prompt_text = _build_verification_summary_prompt()  # 复核使用验证摘要提示词
                    error_guidance = ""
                    if review_attempt > 0:
                        # 检查上一次的解析结果
                        prev_summary = review_summary_container.get("text", "")
                        if prev_summary:
                            prev_parsed = _try_parse_summary_report(prev_summary)
                            if not isinstance(prev_parsed, list):
                                error_guidance = "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- 无法从摘要中解析出有效的 YAML 数组"
                            elif not (prev_parsed and all(isinstance(item, dict) and "gid" in item and "is_reason_sufficient" in item for item in prev_parsed)):
                                validation_errors = []
                                for idx, item in enumerate(prev_parsed):
                                    if not isinstance(item, dict):
                                        validation_errors.append(f"元素{idx}不是字典")
                                        break
                                    if "gid" not in item:
                                        validation_errors.append(f"元素{idx}缺少必填字段 gid")
                                        break
                                    try:
                                        if int(item.get("gid", 0)) < 1:
                                            validation_errors.append(f"元素{idx}的 gid 必须 >= 1")
                                            break
                                    except Exception:
                                        validation_errors.append(f"元素{idx}的 gid 格式错误（必须是整数）")
                                        break
                                    if "is_reason_sufficient" not in item:
                                        validation_errors.append(f"元素{idx}缺少必填字段 is_reason_sufficient（必须是布尔值）")
                                        break
                                    if not isinstance(item.get("is_reason_sufficient"), bool):
                                        validation_errors.append(f"元素{idx}的 is_reason_sufficient 不是布尔值")
                                        break
                                if validation_errors:
                                    error_guidance = "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n" + "\n".join(f"- {err}" for err in validation_errors)
                    
                    full_review_prompt = f"{review_task}{error_guidance}\n\n{review_summary_prompt_text}"
                    try:
                        review_response = review_agent.model.chat_until_success(full_review_prompt)  # type: ignore
                        # 从响应中提取摘要（假设摘要提示词会引导模型输出 <REPORT> 块）
                        review_summary_container["text"] = review_response
                    except Exception as e:
                        try:
                            print(f"[JARVIS-SEC] 复核阶段直接模型调用失败: {e}，回退到 run()")
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
                            print(f"[JARVIS-SEC] 复核Agent工作区已恢复 ({_changed_review} 个文件)")
                        except Exception:
                            pass
                except Exception:
                    pass
                
                # 解析复核结果
                review_summary_text = review_summary_container.get("text", "")
                if review_summary_text:
                    review_parsed = _try_parse_summary_report(review_summary_text)
                    if isinstance(review_parsed, list):
                        # 简单校验：检查是否为有效列表，包含必要的字段
                        if review_parsed and all(isinstance(item, dict) and "gid" in item and "is_reason_sufficient" in item for item in review_parsed):
                            review_results = review_parsed
                            break  # 格式正确，退出重试循环
                
                # 格式校验失败，后续重试使用直接模型调用
                if review_attempt < max_review_retries:
                    use_direct_model_review = True
                    try:
                        print(f"[JARVIS-SEC] 复核结果格式无效 -> 重试 {review_attempt + 1}/{max_review_retries}（使用直接模型调用）")
                    except Exception:
                        pass
            
            # 处理复核结果
            if review_results:
                # 构建gid到复核结果的映射
                gid_to_review: Dict[int, Dict] = {}
                for rr in review_results:
                    if isinstance(rr, dict):
                        try:
                            r_gid = int(rr.get("gid", 0))
                            if r_gid >= 1:
                                gid_to_review[r_gid] = rr
                        except Exception:
                            pass
                
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
                        print(f"[JARVIS-SEC] 复核结果：无效聚类（gids={cluster_gids}）理由不充分，重新加入验证流程")
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
                        print(f"[JARVIS-SEC] 复核结果：无效聚类（gids={cluster_gids}）理由充分，确认为无效")
                        reviewed_clusters.append({
                            **invalid_cluster,
                            "review_result": "confirmed_invalid",
                            "review_notes": review_notes,
                        })
            else:
                # 复核结果解析失败，保守策略：重新加入验证流程
                print(f"[JARVIS-SEC] 警告：复核结果解析失败，保守策略：将批次中的所有候选重新加入验证流程")
                for invalid_cluster in review_batch:
                    cluster_members = invalid_cluster.get("members", [])
                    for member in cluster_members:
                        reinstated_candidates.append(member)
                    reviewed_clusters.append({
                        **invalid_cluster,
                        "review_result": "reinstated",
                        "review_notes": "复核结果解析失败，保守策略重新加入验证",
                    })
        
        # 将重新加入验证的候选添加到cluster_batches
        if reinstated_candidates:
            print(f"[JARVIS-SEC] 复核完成：{len(reinstated_candidates)} 个候选重新加入验证流程")
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
        else:
            print(f"[JARVIS-SEC] 复核完成：所有无效聚类理由充分，确认为无效")
        
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
    else:
        print(f"[JARVIS-SEC] 无无效聚类需要复核")

    # 若聚类失败或空，则回退为"按文件一次处理"
    if not cluster_batches:
        for _file, _items in _file_groups.items():
            b = [c for c in _items if _sig_of(c) not in done_sigs]
            if b:
                cluster_batches.append(b)

    # 分析阶段开始前的完整性检查：确保所有候选的gid都已被分类
    # 如果发现遗漏的gid，应该在分析阶段开始前就补充，而不是在分析阶段开始后再发现
    all_candidate_gids = set()
    for _file, _items in _file_groups.items():
        for it in _items:
            try:
                _gid = int(it.get("gid", 0))
                if _gid >= 1:
                    all_candidate_gids.add(_gid)
            except Exception:
                pass
    
    # 收集所有已分类的gid（从cluster_batches中）
    all_classified_gids = set()
    for batch in cluster_batches:
        for item in batch:
            try:
                _gid = int(item.get("gid", 0))
                if _gid >= 1:
                    all_classified_gids.add(_gid)
            except Exception:
                pass
    
    # 检查是否有遗漏的gid
    missing_gids_before_analysis = all_candidate_gids - all_classified_gids
    if missing_gids_before_analysis:
        print(f"[JARVIS-SEC] 警告：分析阶段开始前发现遗漏的gid {sorted(list(missing_gids_before_analysis))}，将补充聚类")
        # 为每个遗漏的gid创建单独的聚类
        for missing_gid in sorted(missing_gids_before_analysis):
            # 找到对应的候选
            missing_item = None
            for _file, _items in _file_groups.items():
                for it in _items:
                    try:
                        if int(it.get("gid", 0)) == missing_gid:
                            missing_item = it
                            break
                    except Exception:
                        pass
                if missing_item:
                    break
            
            if missing_item:
                # 为遗漏的gid创建默认验证条件
                default_verification = f"验证候选 {missing_gid} 的安全风险"
                missing_item["verify"] = default_verification
                cluster_batches.append([missing_item])
                _progress_append({
                    "event": "cluster_missing_gid_supplement",
                    "gid": missing_gid,
                    "file": missing_item.get("file"),
                    "note": "分析阶段开始前补充的遗漏gid",
                })
                try:
                    print(f"[JARVIS-SEC] 已为遗漏的gid {missing_gid} 创建单独聚类")
                except Exception:
                    pass

    batches: List[List[Dict]] = cluster_batches
    total_batches = len(batches)
    # 占位 batch_size 以兼容后续日志
    len(batches[0]) if batches else 0

    # 更新验证阶段状态
    if total_batches > 0:
        status_mgr.update_verification(
            current_batch=0,
            total_batches=total_batches,
            message="开始安全验证..."
        )

    for bidx, batch in enumerate(batches, start=1):
        # 进度：批次开始
        _progress_append(
            {
                "event": "batch_status",
                "status": "running",
                "batch_id": f"JARVIS-SEC-Batch-{bidx}",
                "batch_index": bidx,
                "total_batches": total_batches,
                "batch_size": len(batch),
                "file": batch[0].get("file") if batch else None,
            }
        )
        # 更新验证阶段进度
        batch_file = batch[0].get("file") if batch else None
        status_mgr.update_verification(
            current_batch=bidx,
            total_batches=total_batches,
            batch_id=f"JARVIS-SEC-Batch-{bidx}",
            file_name=batch_file,
            message=f"正在验证批次 {bidx}/{total_batches}"
        )

        # 显示进度
        try:
            print(f"\n[JARVIS-SEC] 分析批次 {bidx}/{total_batches}: 大小={len(batch)} 文件='{batch[0].get('file') if batch else 'N/A'}'")
        except Exception:
            pass

        # 构造 Agent（单次处理一批候选）
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
        task_id = f"JARVIS-SEC-Batch-{bidx}"
        agent_kwargs: Dict = dict(
            system_prompt=system_prompt,
            name=task_id,
            auto_complete=True,
            need_summary=True,
            # 复用现有摘要提示词构建器，candidate 传入批次列表包一层
            summary_prompt=_build_summary_prompt(),
            non_interactive=True,
            in_multi_agent=False,
            use_methodology=False,
            use_analysis=False,
            plan=False,
            output_handler=[ToolRegistry()],
            disable_file_edit=True,
            force_save_memory=True,  # 打开强制保存记忆开关
            use_tools=["read_code", "execute_script", "save_memory", "retrieve_memory"],  # 添加保存和召回记忆工具
        )
        if llm_group:
            agent_kwargs["model_group"] = llm_group
        agent = Agent(**agent_kwargs)

        # 任务上下文（批次）
        import json as _json2
        # 使用全局 gid 进行验证（不再构造局部 id），并保留 verify
        batch_ctx: List[Dict] = list(batch)
        # 聚类上下文：本批次所有候选共享同一“验证条件”，传入验证条件与当前批次的连续 id 列表
        cluster_verify = str(batch_ctx[0].get("verify") if batch_ctx else "")
        # cluster_ids_ctx removed (using global gid only)
        cluster_gids_ctx = [it.get("gid") for it in batch_ctx]
        per_task = f"""
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

        # 订阅 AFTER_SUMMARY，捕获Agent内部生成的摘要
        try:
            from jarvis.jarvis_agent.events import AFTER_SUMMARY as _AFTER_SUMMARY  # type: ignore
        except Exception:
            _AFTER_SUMMARY = None  # type: ignore
        summary_container: Dict[str, str] = {"text": ""}
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

        # 执行Agent（增加重试机制：摘要解析失败或关键字段缺失时，重新运行当前批次）
        summary_items: Optional[List[Dict]] = None
        workspace_restore_info: Optional[Dict] = None
        max_retries = 2  # 失败后最多重试2次（共执行最多3次）
        use_direct_model_analysis = False  # 标记是否使用直接模型调用
        prev_parsed_items: Optional[List] = None  # 保存上一次的解析结果，用于错误提示
        for attempt in range(max_retries + 1):
            # 清空上一轮摘要容器
            summary_container["text"] = ""
            
            if use_direct_model_analysis:
                # 格式校验失败后，直接调用模型接口
                # 构造包含摘要提示词和具体错误信息的完整提示
                summary_prompt_text = _build_summary_prompt()
                error_guidance = ""
                if prev_parsed_items is None:
                    error_guidance = "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- 无法从摘要中解析出有效的 YAML 数组"
                elif not _valid_items(prev_parsed_items):
                    # 收集具体的验证错误
                    validation_errors = []
                    if not isinstance(prev_parsed_items, list):
                        validation_errors.append("结果不是数组")
                    else:
                        for idx, it in enumerate(prev_parsed_items):
                            if not isinstance(it, dict):
                                validation_errors.append(f"元素{idx}不是字典")
                                break
                            if "gid" not in it:
                                validation_errors.append(f"元素{idx}缺少必填字段 gid")
                                break
                            try:
                                if int(it.get("gid", 0)) < 1:
                                    validation_errors.append(f"元素{idx}的 gid 必须 >= 1")
                                    break
                            except Exception:
                                validation_errors.append(f"元素{idx}的 gid 格式错误（必须是整数）")
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
                        error_guidance = "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n" + "\n".join(f"- {err}" for err in validation_errors)
                
                full_prompt = f"{per_task}{error_guidance}\n\n{summary_prompt_text}"
                try:
                    response = agent.model.chat_until_success(full_prompt)  # type: ignore
                    # 从响应中提取摘要（假设摘要提示词会引导模型输出 <REPORT> 块）
                    summary_container["text"] = response
                except Exception as e:
                    try:
                        print(f"[JARVIS-SEC] 直接模型调用失败: {e}，回退到 run()")
                    except Exception:
                        pass
                    agent.run(per_task)
            else:
                # 第一次使用 run()，让 Agent 完整运行（可能使用工具）
                agent.run(per_task)

            # 工作区保护：调用 Agent 后如检测到文件被修改，则恢复（每次尝试都执行）
            try:
                _changed = _git_restore_if_dirty(entry_path)
                workspace_restore_info = {
                    "performed": bool(_changed),
                    "changed_files_count": int(_changed or 0),
                    "action": "git checkout -- .",
                }
                meta_records.append(
                    {
                        "task_id": task_id,
                        "batch_index": bidx,
                        "workspace_restore": workspace_restore_info,
                        "attempt": attempt + 1,
                    }
                )
                if _changed:
                    try:
                        print(f"[JARVIS-SEC] 工作区已恢复 ({_changed} 个文件)，操作: git checkout -- .")
                    except Exception:
                        pass
            except Exception:
                pass

            # 解析摘要中的 <REPORT>（YAML）
            summary_text = summary_container.get("text", "")
            parsed_items: Optional[List] = None
            if summary_text:
                rep = _try_parse_summary_report(summary_text)

                if isinstance(rep, list):
                    parsed_items = rep
                elif isinstance(rep, dict):
                    items = rep.get("issues")
                    if isinstance(items, list):
                        parsed_items = items

            # 关键字段校验：当前要求每个元素为 {gid:int, has_risk:bool, ...}
            def _valid_items(items: Optional[List]) -> bool:
                if not isinstance(items, list):
                    return False
                for it in items:
                    if not isinstance(it, dict):
                        return False
                    # 校验 gid（全局唯一编号，>=1）
                    if "gid" not in it:
                        return False
                    try:
                        if int(it["gid"]) < 1:
                            return False
                    except Exception:
                        return False
                    # 校验 has_risk (布尔值)
                    if "has_risk" not in it or not isinstance(it["has_risk"], bool):
                        return False
                    # 如果有风险，则校验 reason 四元组（非空字符串）
                    if it.get("has_risk"):
                        for key in ["preconditions", "trigger_path", "consequences", "suggestions"]:
                            if key not in it:
                                return False
                            if not isinstance(it[key], str) or not it[key].strip():
                                return False
                return True

            # 保存本次解析结果，用于下次重试时的错误提示
            prev_parsed_items = parsed_items

            if _valid_items(parsed_items):
                summary_items = parsed_items
                break  # 成功，退出重试循环
            else:
                # 本次尝试失败：打印并准备重试
                # 格式校验失败，后续重试使用直接模型调用
                use_direct_model_analysis = True
                try:
                    print(f"[JARVIS-SEC] 批次摘要无效 -> 重试 {attempt + 1}/{max_retries} (批次={bidx}，使用直接模型调用)")
                except Exception:
                    pass

        # 重试结束：处理摘要结果
        merged_items: List[Dict] = []
        gid_counts: Dict[int, int] = {}
        parse_fail = not isinstance(summary_items, list)

        if not parse_fail:
            # 摘要解析成功：处理有风险的条目
            try:
                gid_to_item_batch: Dict[int, Dict] = {int(it.get("gid", 0)): it for it in batch if int(it.get("gid", 0)) >= 1}
                for it in summary_items:
                    if not isinstance(it, dict) or not it.get("has_risk"):
                        continue
                    gid = int(it.get("gid", 0))
                    cand_src = gid_to_item_batch.get(gid)
                    if cand_src:
                        cand = dict(cand_src)
                        cand["preconditions"] = str(it.get("preconditions", "")).strip()
                        cand["trigger_path"] = str(it.get("trigger_path", "")).strip()
                        cand["consequences"] = str(it.get("consequences", "")).strip()
                        cand["suggestions"] = str(it.get("suggestions", "")).strip()
                        cand["has_risk"] = True
                        merged_items.append(cand)
                        # 注意：gid_counts 将在验证通过后更新，这里先不计数
            except Exception:
                pass  # 异常不影响流程

        # 汇总并报告：如果分析 Agent 确认有告警，需要验证 Agent 二次验证
        verified_items: List[Dict] = []
        if merged_items:
            print(f"[JARVIS-SEC] 批次 {bidx}/{total_batches} 分析 Agent 发现问题: 数量={len(merged_items)} -> 启动验证 Agent 进行二次验证")
            
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
                plan=False,
                output_handler=[ToolRegistry()],
                disable_file_edit=True,
                use_tools=["read_code", "execute_script", "retrieve_memory"],  # 添加召回记忆工具
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

分析 Agent 给出的结论（需要验证）：
{_json3.dumps(merged_items, ensure_ascii=False, indent=2)}

请验证上述分析结论是否正确，包括：
1. 前置条件（preconditions）是否合理
2. 触发路径（trigger_path）是否成立
3. 后果（consequences）评估是否准确
4. 建议（suggestions）是否合适

对于每个 gid，请判断分析结论是否正确（is_valid: true/false），并给出验证说明。
""".strip()
            
            # 订阅验证 Agent 的摘要
            verification_summary_container: Dict[str, str] = {"text": ""}
            if _AFTER_SUMMARY:
                def _on_after_summary_verify(**kwargs):
                    try:
                        verification_summary_container["text"] = str(kwargs.get("summary", "") or "")
                    except Exception:
                        verification_summary_container["text"] = ""
                try:
                    verification_agent.event_bus.subscribe(_AFTER_SUMMARY, _on_after_summary_verify)
                except Exception:
                    pass
            
            # 运行验证 Agent（增加重试机制：格式校验失败时，使用直接模型调用）
            verification_summary_container["text"] = ""
            verification_results: Optional[List[Dict]] = None
            max_verify_retries = 2  # 失败后最多重试2次（共执行最多3次）
            use_direct_model_verify = False  # 标记是否使用直接模型调用
            
            for verify_attempt in range(max_verify_retries + 1):
                verification_summary_container["text"] = ""
                
                if use_direct_model_verify:
                    # 格式校验失败后，直接调用模型接口
                    # 构造包含摘要提示词和具体错误信息的完整提示
                    verification_summary_prompt_text = _build_verification_summary_prompt()
                    error_guidance = ""
                    if verify_attempt > 0:
                        # 检查上一次的解析结果
                        prev_summary = verification_summary_container.get("text", "")
                        if prev_summary:
                            prev_parsed = _try_parse_summary_report(prev_summary)
                            if not isinstance(prev_parsed, list):
                                error_guidance = "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- 无法从摘要中解析出有效的 YAML 数组"
                            elif not (prev_parsed and all(isinstance(item, dict) and "gid" in item and "is_valid" in item for item in prev_parsed)):
                                validation_errors = []
                                for idx, item in enumerate(prev_parsed):
                                    if not isinstance(item, dict):
                                        validation_errors.append(f"元素{idx}不是字典")
                                        break
                                    if "gid" not in item:
                                        validation_errors.append(f"元素{idx}缺少必填字段 gid")
                                        break
                                    try:
                                        if int(item.get("gid", 0)) < 1:
                                            validation_errors.append(f"元素{idx}的 gid 必须 >= 1")
                                            break
                                    except Exception:
                                        validation_errors.append(f"元素{idx}的 gid 格式错误（必须是整数）")
                                        break
                                    if "is_valid" not in item:
                                        validation_errors.append(f"元素{idx}缺少必填字段 is_valid（必须是布尔值）")
                                        break
                                    if not isinstance(item.get("is_valid"), bool):
                                        validation_errors.append(f"元素{idx}的 is_valid 不是布尔值")
                                        break
                                if validation_errors:
                                    error_guidance = "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n" + "\n".join(f"- {err}" for err in validation_errors)
                    
                    full_verify_prompt = f"{verification_task}{error_guidance}\n\n{verification_summary_prompt_text}"
                    try:
                        verify_response = verification_agent.model.chat_until_success(full_verify_prompt)  # type: ignore
                        # 从响应中提取摘要（假设摘要提示词会引导模型输出 <REPORT> 块）
                        verification_summary_container["text"] = verify_response
                    except Exception as e:
                        try:
                            print(f"[JARVIS-SEC] 验证阶段直接模型调用失败: {e}，回退到 run()")
                        except Exception:
                            pass
                        verification_agent.run(verification_task)
                else:
                    # 第一次使用 run()，让 Agent 完整运行（可能使用工具）
                    verification_agent.run(verification_task)
                
                # 工作区保护：调用验证 Agent 后如检测到文件被修改，则恢复
                try:
                    _changed_verify = _git_restore_if_dirty(entry_path)
                    if _changed_verify:
                        try:
                            print(f"[JARVIS-SEC] 验证 Agent 工作区已恢复 ({_changed_verify} 个文件)")
                        except Exception:
                            pass
                except Exception:
                    pass
                
                # 解析验证结果
                verification_summary_text = verification_summary_container.get("text", "")
                if verification_summary_text:
                    verification_parsed = _try_parse_summary_report(verification_summary_text)
                    if isinstance(verification_parsed, list):
                        # 简单校验：检查是否为有效列表
                        if verification_parsed and all(isinstance(item, dict) and "gid" in item and "is_valid" in item for item in verification_parsed):
                            verification_results = verification_parsed
                            break  # 格式正确，退出重试循环
                
                # 格式校验失败，后续重试使用直接模型调用
                if verify_attempt < max_verify_retries:
                    use_direct_model_verify = True
                    try:
                        print(f"[JARVIS-SEC] 验证结果格式无效 -> 重试 {verify_attempt + 1}/{max_verify_retries} (批次={bidx}，使用直接模型调用)")
                    except Exception:
                        pass
            
            # 根据验证结果筛选：只保留验证通过（is_valid: true）的告警
            if verification_results:
                # 构建 gid 到验证结果的映射
                gid_to_verification: Dict[int, Dict] = {}
                for vr in verification_results:
                    if isinstance(vr, dict):
                        try:
                            v_gid = int(vr.get("gid", 0))
                            if v_gid >= 1:
                                gid_to_verification[v_gid] = vr
                        except Exception:
                            pass
                
                # 只保留验证通过的告警
                for item in merged_items:
                    item_gid = int(item.get("gid", 0))
                    verification = gid_to_verification.get(item_gid)
                    if verification and verification.get("is_valid") is True:
                        # 添加验证说明
                        item["verification_notes"] = str(verification.get("verification_notes", "")).strip()
                        verified_items.append(item)
                    elif verification and verification.get("is_valid") is False:
                        # 验证不通过，记录日志但不加入最终结果
                        try:
                            print(f"[JARVIS-SEC] 验证 Agent 判定 gid={item_gid} 为误报: {verification.get('verification_notes', '')}")
                        except Exception:
                            pass
                    else:
                        # 验证结果中未找到该 gid，默认不通过（保守策略）
                        try:
                            print(f"[JARVIS-SEC] 警告：验证结果中未找到 gid={item_gid}，视为验证不通过")
                        except Exception:
                            pass
            else:
                # 验证结果解析失败，保守策略：不保留任何告警
                print(f"[JARVIS-SEC] 警告：验证 Agent 结果解析失败，不保留任何告警（保守策略）")
            
            # 只有验证通过的告警才写入文件
            if verified_items:
                all_issues.extend(verified_items)
                # 更新 gid_counts：只统计验证通过的告警
                for item in verified_items:
                    gid = int(item.get("gid", 0))
                    if gid >= 1:
                        gid_counts[gid] = gid_counts.get(gid, 0) + 1
                print(f"[JARVIS-SEC] 批次 {bidx}/{total_batches} 验证通过: 数量={len(verified_items)}/{len(merged_items)} -> 追加到报告")
                _append_report(verified_items, "verified", task_id, {"batch": True, "candidates": batch})
                # 更新状态：发现的问题数
                status_mgr.update_verification(
                    current_batch=bidx,
                    total_batches=total_batches,
                    issues_found=len(all_issues),
                    message=f"已验证 {bidx}/{total_batches} 批次，发现 {len(all_issues)} 个问题（验证通过）"
                )
            else:
                print(f"[JARVIS-SEC] 批次 {bidx}/{total_batches} 验证后无有效告警: 分析 Agent 发现 {len(merged_items)} 个，验证后全部不通过")
                # 更新状态：验证后无有效告警
                status_mgr.update_verification(
                    current_batch=bidx,
                    total_batches=total_batches,
                    issues_found=len(all_issues),
                    message=f"已验证 {bidx}/{total_batches} 批次，验证后无有效告警"
            )
        elif parse_fail:
            print(f"[JARVIS-SEC] 批次 {bidx}/{total_batches} 解析失败 (摘要中无 <REPORT> 或字段无效)")
        else:
            print(f"[JARVIS-SEC] 批次 {bidx}/{total_batches} 未发现问题")
            # 更新状态：继续验证
            status_mgr.update_verification(
                current_batch=bidx,
                total_batches=total_batches,
                issues_found=len(all_issues),
                message=f"已验证 {bidx}/{total_batches} 批次"
            )

        # 为本批次所有候选写入 done 记录（无论成功失败，都标记为已处理）
        for c in batch:
            sig = _sig_of(c)
            try:
                c_gid = int(c.get("gid", 0))
            except Exception:
                c_gid = 0
            cnt = gid_counts.get(c_gid, 0)
            _progress_append(
                {
                    "event": "task_status",
                    "status": "done",
                    "task_id": f"{task_id}",
                    "candidate_signature": sig,
                    "candidate": c,
                    "issues_count": int(cnt),
                    "parse_fail": parse_fail,
                    "workspace_restore": workspace_restore_info,
                    "batch_index": bidx,
                }
            )

        # 批次结束记录
        _progress_append(
            {
                "event": "batch_status",
                "status": "done",
                "batch_id": task_id,
                "batch_index": bidx,
                "total_batches": total_batches,
                "issues_count": len(verified_items) if merged_items else 0,  # 只统计验证通过的告警
                "parse_fail": parse_fail,
            }
        )

    # 4) 使用统一聚合器生成最终报告（JSON + Markdown）
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


def _try_parse_summary_report(text: str) -> Optional[object]:
    """
    从摘要文本中提取 <REPORT>...</REPORT> 内容，并解析为对象（dict 或 list，仅支持 YAML）。
    - 若提取/解析失败返回 None
    - YAML 解析采用安全模式，若环境无 PyYAML 则忽略
    """
    start = text.find("<REPORT>")
    end = text.find("</REPORT>")
    if start == -1 or end == -1 or end <= start:
        return None
    content = text[start + len("<REPORT>"):end].strip()
    try:
        import yaml as _yaml  # type: ignore
        data = _yaml.safe_load(content)
        if isinstance(data, (dict, list)):
            return data
    except Exception:
        return None
    return None


__all__ = [
    
    "run_security_analysis",

    "direct_scan",
    "run_with_agent",
]