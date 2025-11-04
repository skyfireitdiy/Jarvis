# -*- coding: utf-8 -*-
"""
OpenHarmony 安全分析套件

当前版本概述：
- 关键路径：直扫（direct_scan）→ 单Agent逐条验证（只读工具：read_code/execute_script）→ 聚合输出（JSON + Markdown）
- 目标范围：内存管理、缓冲区操作、错误处理等基础安全问题识别
- 约束：不修改核心框架文件，保持最小侵入；严格只读分析

集成方式：
- 复用 jarvis.jarvis_agent.Agent 与工具注册系统（jarvis.jarvis_tools.registry.ToolRegistry）
- 提供入口：
  - run_security_analysis(entry_path, ...)：直扫 + 单Agent逐条验证 + 聚合
  - workflow.run_security_analysis_fast(entry_path, ...)：直扫基线（不经 LLM 验证）
  - workflow.direct_scan(entry_path, ...)：仅启发式直扫

说明：
- 已移除 MultiAgent 编排与相关提示词；不存在“阶段一”等表述
"""

from typing import Dict, List, Optional

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_sec.workflow import run_security_analysis_fast, direct_scan, run_with_agent
from jarvis.jarvis_tools.registry import ToolRegistry


  


def _try_parse_issues_from_text(text: str) -> Optional[List[Dict]]:
    """
    尝试从模型输出中解析出 {"issues": [...]}，宽松容错：
    1) 直接作为完整JSON解析
    2) 从 ```json ... ``` 或 ``` ... ``` 代码块中提取JSON解析
    3) 从首个 { 开始进行大括号配对截取后解析

    返回:
    - 成功解析到 issues 列表则返回该列表（可为空列表）
    - 未能解析则返回 None
    """
    import json
    import re

    # 尝试直接解析
    try:
        data = json.loads(text)
        items = data.get("issues", [])
        if isinstance(items, list):
            return items
    except Exception:
        pass

    # 尝试从代码块提取
    try:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
        if m:
            data = json.loads(m.group(1))
            items = data.get("issues", [])
            if isinstance(items, list):
                return items
    except Exception:
        pass

    # 尝试基于大括号配对截取首个JSON对象
    try:
        start = text.find("{")
        if start != -1:
            stack = 0
            end = None
            for i, ch in enumerate(text[start:], start=start):
                if ch == "{":
                    stack += 1
                elif ch == "}":
                    stack -= 1
                    if stack == 0:
                        end = i + 1
                        break
            if end:
                snippet = text[start:end]
                data = json.loads(snippet)
                items = data.get("issues", [])
                if isinstance(items, list):
                    return items
    except Exception:
        pass

    return None


def _try_parse_summary_json(text: str) -> Optional[Dict]:
    """
    从模型摘要文本中尽力提取严格 JSON 对象（非仅 issues 列表）。
    解析顺序：
    1) 直接 JSON
    2) ```json ...``` 或 ```...``` 代码块中的 JSON
    3) 基于首个花括号的配对截取 JSON 对象
    成功时返回解析后的 dict；失败返回 None
    """
    import json
    import re

    # 直接解析
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 代码块提取
    try:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
        if m:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                return data
    except Exception:
        pass

    # 花括号配对截取
    try:
        start = text.find("{")
        if start != -1:
            stack = 0
            end = None
            for i, ch in enumerate(text[start:], start=start):
                if ch == "{":
                    stack += 1
                elif ch == "}":
                    stack -= 1
                    if stack == 0:
                        end = i + 1
                        break
            if end:
                snippet = text[start:end]
                data = json.loads(snippet)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass

    return None


def _build_summary_prompt(task_id: str, entry_path: str, languages: List[str], candidate: Dict) -> str:
    """
    构建摘要提示词：要求以 <REPORT>...</REPORT> 包裹的 JSON 或 YAML 输出。
    系统提示词不强制规定主对话输出格式，仅在摘要中给出结构化结果。
    """
    import json as _json
    cand_json = _json.dumps(candidate, ensure_ascii=False, indent=2)
    langs_json = _json.dumps(languages, ensure_ascii=False)
    return f"""
请将本轮“安全子任务（单点验证）”的结构化结果仅放入以下标记中，并使用 YAML 数组对象形式输出：
<REPORT>
# 仅输出编号与理由（不含位置信息），编号为本批次候选的序号（从1开始）
# 示例：
# - id: 1
#   reason: "使用不安全API，存在潜在缓冲区溢出风险"
# - id: 3
#   reason: "错误处理缺失，可能导致未定义行为"
[]
</REPORT>
要求：
- 只能在 <REPORT> 与 </REPORT> 中输出 YAML 数组，且不得出现其他文本。
- 若确认本批次全部为误报或无问题，请返回空数组 []。
- 数组元素为对象，包含字段：
  - id: 整数（本批次候选的序号，从1开始）
  - reason: 字符串（简洁说明返回该项的理由）
- 不要在数组元素中包含 file/line/pattern 等位置信息；写入 jsonl 时系统会结合原始候选信息。
""".strip()


# 注：当前版本不使用 MultiAgent 编排，已移除默认多智能体配置与创建函数。
# 请使用 run_security_analysis（单Agent逐条验证）或 workflow.run_security_analysis_fast（直扫基线）。 

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
    batch_limit: int = 10,
    resume: bool = True,
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
    - resume: 是否基于进度文件进行断点续扫（默认开启）。进度文件为 entry_path/.jarvis/sec/progress.jsonl
      将在每个子任务开始（running）与结束（done）时追加记录，异常中断后可自动跳过已完成项。
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
    if resume and progress_path.exists():
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

    # 1) 本地直扫，生成初始候选（不可完全依赖Agent进行发现）
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
    # 批量模式：按文件分组，仅选择一个文件的前 n 条候选（默认 n=10）
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
            limit = batch_limit if isinstance(batch_limit, int) and batch_limit > 0 else len(items)
            # 为实现“所有告警分批处理”，此处不截断，保留该文件的全部候选，后续按 batch_limit 分批提交给 Agent
            selected_candidates = items
            try:
                print(f"[JARVIS-SEC] batch selection: file={selected_file} count={len(selected_candidates)}/{len(items)} (limit={limit})")
            except Exception:
                pass
            # 记录批次选择信息
            _progress_append({
                "event": "batch_selection",
                "selected_file": selected_file,
                "selected_count": len(selected_candidates),
                "total_in_file": len(items),
                "limit": limit,
            })
        # 将待处理候选替换为本批次（仅一个文件的前 n 条）
        compact_candidates = selected_candidates
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
        将当前子任务的检测结果追加写入 JSONL 报告文件（每行一个JSON对象）。
        仅当 items 非空时写入。
        source: "summary" | "output_fallback"
        """
        if not items:
            return
        try:
            from pathlib import Path as _Path
            from datetime import datetime as _dt

            path = _Path(report_file) if report_file else _Path(entry_path) / ".jarvis/sec" / "agent_issues.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            rec = {
                "task_id": task_id,
                "candidate": cand,
                "issues": items,
                "meta": {
                    "entry_path": entry_path,
                    "languages": langs,
                    "source": source,
                    "timestamp": _dt.utcnow().isoformat() + "Z",
                },
            }
            line = json.dumps(rec, ensure_ascii=False)
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            try:
                print(f"[JARVIS-SEC] write {len(items)} issue(s) to {path}")
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

    pending: List[Dict] = []
    for c in compact_candidates:
        if not (resume and _sig_of(c) in done_sigs):
            pending.append(c)

    # 分批：每批次最多 batch_limit 条
    batch_size = batch_limit if isinstance(batch_limit, int) and batch_limit > 0 else len(pending)
    batches: List[List[Dict]] = [pending[i : i + batch_size] for i in range(0, len(pending), batch_size)]
    total_batches = len(batches)

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
            print(f"[JARVIS-SEC] Batch {bidx}/{total_batches}: size={len(batch)} file={batch[0].get('file') if batch else 'N/A'}")
        except Exception:
            pass

        # 构造 Agent（单次处理一批候选）
        system_prompt = """
# 单Agent安全分析约束
- 仅围绕输入候选的位置进行验证与细化；避免无关扩展与大范围遍历。
- 工具优先：使用 read_code 读取目标文件附近源码（行号前后各 ~50 行），必要时用 execute_script 辅助检索。
- 禁止修改任何文件或执行写操作命令（rm/mv/cp/echo >、sed -i、git、patch、chmod、chown 等）；仅进行只读分析与读取。
- 每次仅执行一个操作；等待工具结果后再进行下一步。
- 完成对本批次候选问题的判断后，主输出仅打印结束符“[END]”，不需要汇总结果；结构化结果仅在摘要中按规定格式输出。
""".strip()
        task_id = f"JARVIS-SEC-Batch-{bidx}"
        agent_kwargs: Dict = dict(
            system_prompt=system_prompt,
            name=task_id,
            auto_complete=True,
            need_summary=True,
            # 复用现有摘要提示词构建器，candidate 传入批次列表包一层
            summary_prompt=_build_summary_prompt(task_id, entry_path, langs, {"batch": True, "candidates": batch}),
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
        per_task = f"""
# 安全子任务批次（多点验证）
目标：针对本批次候选问题进行证据核实、风险评估与修复建议补充；若确认误报，对应候选不返回问题。
上下文参数：
- entry_path: {entry_path}
- languages: {langs}

批次候选(JSON数组):
{_json2.dumps(batch, ensure_ascii=False, indent=2)}

操作建议：
- 使用 read_code 读取目标文件（尽量提供绝对路径或以 entry_path 拼接），围绕各候选行号上下各约50行。
- 若需搜索更多线索，可使用 execute_script 调用 rg/find 对目标文件进行局部检索。
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
                        print(f"[JARVIS-SEC] workspace restored ({_changed} file(s)) via: git checkout -- .")
                    except Exception:
                        pass
            except Exception:
                pass

            # 解析摘要中的 <REPORT>（JSON/YAML）
            summary_text = summary_container.get("text", "")
            parsed_items: Optional[List] = None
            if summary_text:
                rep = _try_parse_summary_report(summary_text)
                if rep is None:
                    rep = _try_parse_summary_json(summary_text)
                if isinstance(rep, list):
                    parsed_items = rep
                elif isinstance(rep, dict):
                    items = rep.get("issues")
                    if isinstance(items, list):
                        parsed_items = items

            # 关键字段校验：当前要求每个元素为 {id:int, reason:str}
            def _valid_items(items: Optional[List]) -> bool:
                if not isinstance(items, list):
                    return False
                for it in items:
                    if not isinstance(it, dict):
                        return False
                    # 校验 id（批次内从1开始的整数）
                    if "id" not in it:
                        return False
                    try:
                        if int(it["id"]) < 1:
                            return False
                    except Exception:
                        return False
                    # 校验 reason（非空字符串）
                    if "reason" not in it:
                        return False
                    if not isinstance(it["reason"], str) or not it["reason"].strip():
                        return False
                return True

            if _valid_items(parsed_items):
                summary_items = parsed_items
                break  # 成功，退出重试循环
            else:
                # 本次尝试失败：打印并准备重试
                try:
                    print(f"[JARVIS-SEC] batch summary invalid -> retry {attempt + 1}/{max_retries} (batch={bidx})")
                except Exception:
                    pass

        # 重试结束：summary_items 为 None 则视为失败
        # 将检测结果写入报告，并按候选维度写入进度（done）
        if isinstance(summary_items, list):
            # 将 {id, reason} 映射回批次候选，并合并原始信息 + reason
            merged_items: List[Dict] = []
            id_counts: Dict[int, int] = {}
            try:
                for it in summary_items:
                    if not isinstance(it, dict):
                        continue
                    try:
                        idx = int(it.get("id", 0))
                    except Exception:
                        idx = 0
                    if 1 <= idx <= len(batch):
                        cand = dict(batch[idx - 1])
                        reason = str(it.get("reason", "")).strip()
                        cand["reason"] = reason if reason else ""
                        merged_items.append(cand)
                        id_counts[idx] = id_counts.get(idx, 0) + 1
            except Exception:
                pass

            # 汇总有效问题（非误报）
            if merged_items:
                all_issues.extend(merged_items)
                try:
                    print(f"[JARVIS-SEC] batch issues-found {bidx}/{total_batches}: count={len(merged_items)} -> append report (summary)")
                except Exception:
                    pass
                # 写入 JSONL 报告（批次）
                _append_report(merged_items, "summary", task_id, {"batch": True, "candidates": batch})
            else:
                try:
                    print(f"[JARVIS-SEC] batch no-issue {bidx}/{total_batches}")
                except Exception:
                    pass

            # 为每个候选写入 done 记录（断点续扫用）
            for i, c in enumerate(batch, start=1):
                sig = _sig_of(c)
                cnt = id_counts.get(i, 0)
                _progress_append(
                    {
                        "event": "task_status",
                        "status": "done",
                        "task_id": f"{task_id}",
                        "candidate_signature": sig,
                        "candidate": c,
                        "issues_count": int(cnt),
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
                }
            )
            continue

        # 摘要不可解析或关键字段缺失：记录失败并按候选维度写入 done（issues_count=0）
        try:
            print(f"[JARVIS-SEC] batch parse-fail {bidx}/{total_batches} (no <REPORT>/invalid fields in summary)")
        except Exception:
            pass
        for c in batch:
            _progress_append(
                {
                    "event": "task_status",
                    "status": "done",
                    "task_id": f"{task_id}",
                    "candidate_signature": _sig_of(c),
                    "candidate": c,
                    "issues_count": 0,
                    "parse_fail": True,
                    "workspace_restore": workspace_restore_info,
                    "batch_index": bidx,
                }
            )
        _progress_append(
            {
                "event": "batch_status",
                "status": "done",
                "batch_id": task_id,
                "batch_index": bidx,
                "total_batches": total_batches,
                "issues_count": 0,
                "parse_fail": True,
            }
        )

        def _sig_matches_item(sig: str, item: Dict) -> bool:
            # 用 file+line+pattern 粗略关联候选与输出项
            parts = sig.split("|", 3)
            f = parts[1] if len(parts) > 1 else ""
            ln = parts[2] if len(parts) > 2 else ""
            pat = parts[3] if len(parts) > 3 else ""
            return str(item.get("file")) == f and str(item.get("line")) == ln and str(item.get("pattern") or "") == pat

        # 将检测结果写入报告，并按候选维度写入进度（done）
        if isinstance(summary_items, list):
            # 将 {id, reason} 映射回批次候选，并合并原始信息 + reason
            merged_items: List[Dict] = []
            id_counts: Dict[int, int] = {}
            try:
                for it in summary_items:
                    if not isinstance(it, dict):
                        continue
                    try:
                        idx = int(it.get("id", 0))
                    except Exception:
                        idx = 0
                    if 1 <= idx <= len(batch):
                        cand = dict(batch[idx - 1])
                        reason = str(it.get("reason", "")).strip()
                        cand["reason"] = reason if reason else ""
                        merged_items.append(cand)
                        id_counts[idx] = id_counts.get(idx, 0) + 1
            except Exception:
                pass

            # 汇总有效问题（非误报）
            if merged_items:
                all_issues.extend(merged_items)
                try:
                    print(f"[JARVIS-SEC] batch issues-found {bidx}/{total_batches}: count={len(merged_items)} -> append report (summary)")
                except Exception:
                    pass
                # 写入 JSONL 报告（批次）
                _append_report(merged_items, "summary", task_id, {"batch": True, "candidates": batch})
            else:
                try:
                    print(f"[JARVIS-SEC] batch no-issue {bidx}/{total_batches}")
                except Exception:
                    pass

            # 为每个候选写入 done 记录（断点续扫用）
            for i, c in enumerate(batch, start=1):
                sig = _sig_of(c)
                cnt = id_counts.get(i, 0)
                _progress_append(
                    {
                        "event": "task_status",
                        "status": "done",
                        "task_id": f"{task_id}",
                        "candidate_signature": sig,
                        "candidate": c,
                        "issues_count": int(cnt),
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
                }
            )
            continue

        # 摘要不可解析：记录失败并按候选维度写入 done（issues_count=0）
        try:
            print(f"[JARVIS-SEC] batch parse-fail {bidx}/{total_batches} (no <REPORT> in summary)")
        except Exception:
            pass
        for c in batch:
            _progress_append(
                {
                    "event": "task_status",
                    "status": "done",
                    "task_id": f"{task_id}",
                    "candidate_signature": _sig_of(c),
                    "candidate": c,
                    "issues_count": 0,
                    "parse_fail": True,
                    "workspace_restore": workspace_restore_info,
                    "batch_index": bidx,
                }
            )
        _progress_append(
            {
                "event": "batch_status",
                "status": "done",
                "batch_id": task_id,
                "batch_index": bidx,
                "total_batches": total_batches,
                "issues_count": 0,
                "parse_fail": True,
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
    从摘要文本中提取 <REPORT>...</REPORT> 内容，并解析为对象（dict 或 list，支持 JSON 或 YAML）。
    - 若提取/解析失败返回 None
    - YAML 解析采用安全模式，若环境无 PyYAML 则忽略
    """
    import json as _json
    start = text.find("<REPORT>")
    end = text.find("</REPORT>")
    if start == -1 or end == -1 or end <= start:
        return None
    content = text[start + len("<REPORT>"):end].strip()
    # 优先 JSON
    try:
        data = _json.loads(content)
        if isinstance(data, (dict, list)):
            return data
    except Exception:
        pass
    # 回退 YAML
    try:
        import yaml as _yaml  # type: ignore
        data = _yaml.safe_load(content)
        if isinstance(data, (dict, list)):
            return data
    except Exception:
        pass
    # 回退 YAML
    try:
        import yaml as _yaml  # type: ignore
        data = _yaml.safe_load(content)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


__all__ = [
    
    "run_security_analysis",
    "run_security_analysis_fast",
    "direct_scan",
    "run_with_agent",
]