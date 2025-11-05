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
    return f"""
请将本轮“安全子任务（单点验证）”的结构化结果仅放入以下标记中，并使用 YAML 数组对象形式输出：
<REPORT>
# 仅输出全局编号（gid）与详细理由（不含位置信息），gid 为全局唯一的数字编号
# 示例：
# - gid: 1
#   has_risk: true
#   preconditions: "输入字符串 src 的长度大于等于 dst 的缓冲区大小"
#   trigger_path: "函数 foobar 调用 strcpy 时，其输入 src 来自于未经校验的网络数据包，可导致缓冲区溢出"
#   consequences: "缓冲区溢出，可能引发程序崩溃或任意代码执行"
#   suggestions: "使用 strncpy_s 或其他安全的字符串复制函数"
[]
</REPORT>
要求：
- 只能在 <REPORT> 与 </REPORT> 中输出 YAML 数组，且不得出现其他文本。
- 若确认本批次全部为误报或无问题，请返回空数组 []。
- 数组元素为对象，包含字段：
  - gid: 整数（全局唯一编号）
  - has_risk: 布尔值 (true/false)，表示该项是否存在真实安全风险。
  - preconditions: 字符串（触发漏洞的前置条件）
  - trigger_path: 字符串（漏洞的触发路径，即从可控输入到缺陷代码的完整调用链路或关键步骤）
  - consequences: 字符串（漏洞被触发后可能导致的后果）
  - suggestions: 字符串（修复或缓解该漏洞的建议）
- 不要在数组元素中包含 file/line/pattern 等位置信息；写入 jsonl 时系统会结合原始候选信息。
- **关键**：仅当 `has_risk` 为 `true` 时，才会被记录为确认的问题。对于确认是误报的条目，请确保 `has_risk` 为 `false` 或不输出该条目。
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
) -> str:
    """
    运行安全分析工作流（混合模式）。

    改进：
    - 即使在 agent 模式下，也先进行本地正则/启发式直扫，生成候选问题；
      然后将候选问题拆分为子任务，交由多Agent进行深入分析与聚合。

    参数：
    - entry_path: 待分析的根目录路径
    - languages: 限定扫描的语言扩展（例如 ["c", "cpp", "h", "hpp", "rs"]），为空则使用默认

    返回：
    - 最终报告（字符串），由 Aggregator 生成（JSON + Markdown）

    其他：
    - llm_group: 模型组名称（仅在当前调用链内生效，不覆盖全局配置），将直接传入 Agent 用于选择模型
    - report_file: 增量报告文件路径（JSONL）。当每个子任务检测到 issues 时，立即将一条记录追加到该文件；
      若未指定，则默认写入 entry_path/.jarvis/sec/agent_issues.jsonl
    - 断点续扫: 默认开启。会基于 .jarvis/sec/progress.jsonl 和 .jarvis/sec/heuristic_issues.jsonl 文件进行状态恢复。
    """
    import json

    langs = languages or ["c", "cpp", "h", "hpp", "rs"]

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
        pre_scan = direct_scan(entry_path, languages=langs)
        candidates = pre_scan.get("issues", [])
        summary = pre_scan.get("summary", {})
        _progress_append({
            "event": "pre_scan_done",
            "entry_path": entry_path,
            "languages": langs,
            "scanned_files": summary.get("scanned_files"),
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
    total = len(compact_candidates)
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
    for _file_idx, (_file, _items) in enumerate(_file_groups.items(), start=1):
        print(f"\n[JARVIS-SEC] 聚类文件 {_file_idx}/{total_files_to_cluster}: {_file}")
        # 过滤掉已完成
        pending_in_file: List[Dict] = []
        for c in _items:
            if not (_sig_of(c) in done_sigs):
                pending_in_file.append(c)
        if not pending_in_file:
            continue

        # 构造聚类Agent（每个文件一个Agent，按批次聚类）
        cluster_system_prompt = """
# 单Agent聚类约束
- 你的任务是对同一文件内的启发式候选进行“验证条件一致性”聚类。
- 验证条件：为了确认是否存在漏洞需要成立/验证的关键前置条件。例如：“指针p在解引用前非空”“拷贝长度不超过目标缓冲区容量”等。
- 工具优先：如需核对上下文，可使用 read_code 读取相邻代码；避免过度遍历。
- 禁止写操作；仅只读分析。
        """.strip()
        import json as _json2
        cluster_summary_prompt = """
请仅在 <CLUSTERS> 与 </CLUSTERS> 中输出 YAML 数组：
- 每个元素包含：
  - verification: 字符串（对该聚类的验证条件描述，简洁明确，可直接用于后续Agent验证）
  - gids: 整数数组（候选的全局唯一编号；输入JSON每个元素含 gid，可直接对应填入）
- 要求：
  - 严格要求：仅输出位于 <CLUSTERS> 与 </CLUSTERS> 间的 YAML 数组，其他位置不输出任何文本
  - 相同验证条件的候选合并为同一项
  - 不需要解释与长文本，仅给出可执行的验证条件短句
  - 若无法聚类，请将每个候选单独成组，verification 为该候选的最小确认条件
<CLUSTERS>
- verification: ""
  gids: []
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

                gid_to_item_resume: Dict[int, Dict] = {int(it.get("gid", 0)): it for it in pending_in_file_with_ids if int(it.get("gid", 0)) >= 1}
                for rec in _existing_clusters.get(_key, []):
                    verification = str(rec.get("verification", "")).strip()
                    gids_list = rec.get("gids", [])
                    norm_keys: List[int] = []
                    if isinstance(gids_list, list):
                        for x in gids_list:
                            try:
                                xi = int(x)
                                if xi >= 1:
                                    norm_keys.append(xi)
                            except Exception:
                                continue
                    members: List[Dict] = []
                    for k in norm_keys:
                        it = gid_to_item_resume.get(k)
                        if it:
                            it["verify"] = verification
                            members.append(it)
                    if members:
                        cluster_batches.append(members)
                        cluster_records.append(
                            {
                                "file": _file,
                                "verification": verification,
                                "gids": [m.get("gid") for m in members],
                                "count": len(members),
                                "batch_index": _chunk_idx,
                            }
                        )
                # 标记进度（断点复用）
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
                output_handler=[ToolRegistry()],
                disable_file_edit=True,
                use_tools=["read_code", "execute_script"],
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

            # 运行聚类Agent（简单重试一次）
            cluster_items = None
            for _attempt in range(2):
                _cluster_summary["text"] = ""
                cluster_agent.run(cluster_task)
                cluster_items = _parse_clusters_from_text(_cluster_summary.get("text", ""))
                # 校验结构
                valid = True
                if not isinstance(cluster_items, list) or not cluster_items:
                    valid = False
                else:
                    for it in cluster_items:
                        if not isinstance(it, dict):
                            valid = False
                            break
                        vals = it.get("gids", [])
                        if not isinstance(it.get("verification", ""), str) or not isinstance(vals, list):
                            valid = False
                            break
                if valid:
                    break
                else:
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

                _merged_count = 0
                for cl in cluster_items:
                    verification = str(cl.get("verification", "")).strip()
                    raw_gids = cl.get("gids", [])
                    raw_ids = None
                    norm_keys: List[int] = []
                    use_gid = True
                    if isinstance(raw_gids, list):
                        use_gid = True
                        for x in raw_gids:
                            try:
                                xi = int(x)
                                if xi >= 1:
                                    norm_keys.append(xi)
                            except Exception:
                                continue
                    elif False:
                        for x in raw_ids:
                            try:
                                xi = int(x)
                                if xi >= 1:
                                    norm_keys.append(xi)
                            except Exception:
                                continue
                    members: List[Dict] = []
                    for k in norm_keys:
                        it = gid_to_item.get(k)
                        if it:
                            it["verify"] = verification
                            members.append(it)
                    if members:
                        _merged_count += 1
                        cluster_batches.append(members)
                        cluster_records.append(
                            {
                                "file": _file,
                                "verification": verification,
                                "gids": [m.get("gid") for m in members],
                                "count": len(members),
                                "batch_index": _chunk_idx,
                            }
                        )
                # 标记聚类批次完成（进度）
                _progress_append(
                    {
                        "event": "cluster_status",
                        "status": "done",
                        "file": _file,
                        "batch_index": _chunk_idx,
                        "clusters_count": _merged_count,
                    }
                )
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

    # 若聚类失败或空，则回退为“按文件一次处理”
    if not cluster_batches:
        for _file, _items in _file_groups.items():
            b = [c for c in _items if not (resume and _sig_of(c) in done_sigs)]
            if b:
                cluster_batches.append(b)


    batches: List[List[Dict]] = cluster_batches
    total_batches = len(batches)
    # 占位 batch_size 以兼容后续日志
    batch_size = len(batches[0]) if batches else 0

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

        # 显示进度
        try:
            print(f"\n[JARVIS-SEC] 分析批次 {bidx}/{total_batches}: 大小={len(batch)} 文件='{batch[0].get('file') if batch else 'N/A'}'")
        except Exception:
            pass

        # 构造 Agent（单次处理一批候选）
        system_prompt = """
# 单Agent安全分析约束
- 你的核心任务是评估代码的安全问题，目标：针对本候选问题进行证据核实、风险评估与修复建议补充，查找漏洞触发路径，确认在某些条件下会触发；以此来判断是否是漏洞。
- 工具优先：使用 read_code 读取目标文件附近源码（行号前后各 ~50 行），必要时用 execute_script 辅助检索。
- 必要时需向上追溯调用者，查看完整的调用路径，以确认风险是否真实存在。例如，一个函数存在空指针解引用风险，但若所有调用者均能确保传入的指针非空，则该风险在当前代码库中可能不会实际触发。
- 若多条告警位于同一文件且行号相距不远，可一次性读取共享上下文，对这些相邻告警进行联合分析与判断；但仍需避免无关扩展与大范围遍历。
- 禁止修改任何文件或执行写操作命令（rm/mv/cp/echo >、sed -i、git、patch、chmod、chown 等）；仅进行只读分析与读取。
- 每次仅执行一个操作；等待工具结果后再进行下一步。
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
            output_handler=[ToolRegistry()],
            disable_file_edit=True,
            use_tools=["read_code", "execute_script"],
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
        for attempt in range(max_retries + 1):
            # 清空上一轮摘要容器
            summary_container["text"] = ""
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

            if _valid_items(parsed_items):
                summary_items = parsed_items
                break  # 成功，退出重试循环
            else:
                # 本次尝试失败：打印并准备重试
                try:
                    print(f"[JARVIS-SEC] 批次摘要无效 -> 重试 {attempt + 1}/{max_retries} (批次={bidx})")
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
                        gid_counts[gid] = gid_counts.get(gid, 0) + 1
            except Exception:
                pass  # 异常不影响流程

        # 汇总并报告
        if merged_items:
            all_issues.extend(merged_items)
            print(f"[JARVIS-SEC] 批次 {bidx}/{total_batches} 发现问题: 数量={len(merged_items)} -> 追加到报告")
            _append_report(merged_items, "summary", task_id, {"batch": True, "candidates": batch})
        elif parse_fail:
            print(f"[JARVIS-SEC] 批次 {bidx}/{total_batches} 解析失败 (摘要中无 <REPORT> 或字段无效)")
        else:
            print(f"[JARVIS-SEC] 批次 {bidx}/{total_batches} 未发现问题")

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
                "issues_count": len(merged_items),
                "parse_fail": parse_fail,
            }
        )

    # 4) 使用统一聚合器生成最终报告（JSON + Markdown）
    from jarvis.jarvis_sec.report import build_json_and_markdown
    return build_json_and_markdown(
        all_issues,
        scanned_root=summary.get("scanned_root"),
        scanned_files=summary.get("scanned_files"),
        meta=meta_records or None,
    )


def _try_parse_summary_report(text: str) -> Optional[object]:
    """
    从摘要文本中提取 <REPORT>...</REPORT> 内容，并解析为对象（dict 或 list，仅支持 YAML）。
    - 若提取/解析失败返回 None
    - YAML 解析采用安全模式，若环境无 PyYAML 则忽略
    """
    import json as _json
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