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
请将本轮“安全子任务（单点验证）”的结构化结果仅放入以下标记中（允许 JSON 或 YAML）：
<REPORT>
# 推荐 JSON；如果使用 YAML 亦可
issues:
  - language: "c/cpp|rust"
    category: "unsafe_api|buffer_overflow|memory_mgmt|error_handling|unsafe_usage|concurrency|ffi"
    pattern: "命中的模式/关键字"
    file: "相对或绝对路径"
    line: 0
    evidence: "证据代码片段（单行简化）"
    description: "问题说明"
    suggestion: "修复建议"
    confidence: 0.0
    severity: "high|medium|low"
meta:
  task_id: "{task_id}"
  entry_path: "{entry_path}"
  languages: {langs_json}
  candidate: {cand_json}
</REPORT>
要求：
- 报告只能出现在 <REPORT> 与 </REPORT> 中，且不得出现其他文本。
- 若确认误报，请返回空列表 issues: []。
- 值需与实际分析一致；未调用工具时可省略 used_tools 等非必要字段。
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
    MAX_ITEMS = 200  # 避免提示过长
    compact_candidates = compact_candidates[:MAX_ITEMS]
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

    # 3) 针对每个候选，单独创建一次多Agent任务，逐条验证并收集结果
    all_issues: List[Dict] = []
    meta_records: List[Dict] = []
    for idx, cand in enumerate(compact_candidates, start=1):
        # 计算候选签名用于断点续扫（language|file|line|pattern）
        cand_sig = f"{cand.get('language','')}|{cand.get('file','')}|{cand.get('line','')}|{cand.get('pattern','')}"
        if resume and cand_sig in done_sigs:
            try:
                print(f"[JARVIS-SEC] resume-skip {idx}/{total}: {cand.get('file')}:{cand.get('line')} ({cand.get('language')})")
            except Exception:
                pass
            # 写入进度：任务跳过（skipped）
            _progress_append(
                {
                    "event": "task_status",
                    "status": "skipped",
                    "task_id": f"JARVIS-SEC-Analyzer-{idx}",
                    "idx": idx,
                    "total": total,
                    "candidate_signature": cand_sig,
                    "candidate": cand,
                }
            )
            continue
        # 使用单Agent逐条验证，避免多Agent复杂度与上下文污染
        system_prompt = """
# 单Agent安全分析约束
- 仅围绕输入候选的位置进行验证与细化；避免无关扩展与大范围遍历。
- 工具优先：使用 read_code 读取 {file} 附近源码（行号前后各 ~50 行），必要时用 execute_script 辅助检索。
- 禁止修改任何文件或执行写操作命令（rm/mv/cp/echo >、sed -i、git、patch、chmod、chown 等）；仅进行只读分析与读取。
- 每次仅执行一个操作；等待工具结果后再进行下一步。
""".strip()
        task_id = f"JARVIS-SEC-Analyzer-{idx}"
        # 显示当前进度
        try:
            print(f"[JARVIS-SEC] Progress {idx}/{total}: {cand.get('file')}:{cand.get('line')} ({cand.get('language')})")
        except Exception:
            # 打印失败不影响主流程
            pass
        agent_kwargs: Dict = dict(
            system_prompt=system_prompt,
            name=task_id,
            auto_complete=True,
            # 启用摘要，通过摘要统一结构化输出
            need_summary=True,
            summary_prompt=_build_summary_prompt(task_id, entry_path, langs, cand),
            non_interactive=True,
            in_multi_agent=False,
            # 显式禁用方法论与分析，确保Agent按指令执行
            use_methodology=False,
            use_analysis=False,
            output_handler=[ToolRegistry()],
            disable_file_edit = True,
            use_tools=["read_code", "execute_script"],
        )
        # 将 llm_group 仅传递给本次 Agent，不覆盖全局配置
        if llm_group:
            agent_kwargs["model_group"] = llm_group
        agent = Agent(**agent_kwargs)
        per_task = f"""
# 安全子任务（单点验证）
目标：针对候选问题进行证据核实、风险评估与修复建议补充；若确认误报，issues 应为空。
上下文参数：
- entry_path: {entry_path}
- languages: {langs}

候选(JSON):
{json.dumps(cand, ensure_ascii=False, indent=2)}

操作建议：
- 使用 read_code 读取目标文件（尽量提供绝对路径或以 entry_path 拼接），围绕候选行号上下各约50行。
- 若需搜索更多线索，可使用 execute_script 调用 rg/find 对目标文件进行局部检索。
""".strip()

        # 写入进度：任务开始（running）
        _progress_append(
            {
                "event": "task_status",
                "status": "running",
                "task_id": task_id,
                "idx": idx,
                "total": total,
                "candidate_signature": cand_sig,
                "candidate": cand,
            }
        )

        # 订阅 AFTER_SUMMARY，捕获Agent内部生成的摘要，避免二次调用模型
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
        agent.run(per_task)
        # 流程级工作区保护：调用 Agent 后如检测到文件被修改，则使用 git checkout -- . 恢复
        workspace_restore_info: Optional[Dict] = None
        try:
            _changed = _git_restore_if_dirty(entry_path)
            workspace_restore_info = {
                "performed": bool(_changed),
                "changed_files_count": int(_changed or 0),
                "action": "git checkout -- .",
            }
            # 审计记录：每轮 Agent 执行后的工作区恢复情况，写入最终报告的 meta
            meta_records.append(
                {
                    "task_id": task_id,
                    "candidate": cand,
                    "workspace_restore": workspace_restore_info,
                }
            )
            if _changed:
                try:
                    print(f"[JARVIS-SEC] workspace restored ({_changed} file(s)) via: git checkout -- .")
                except Exception:
                    pass
        except Exception:
            # 即使获取/写入审计信息失败，也不影响后续流程
            pass

        # 优先解析摘要中的 <REPORT>（JSON/YAML），失败再回退主输出解析
        summary_items: Optional[List[Dict]] = None
        summary_text = summary_container.get("text", "")
        if summary_text:
            rep = _try_parse_summary_report(summary_text)
            if rep is None:
                # 兼容：若摘要直接输出 JSON，则尝试旧解析
                rep = _try_parse_summary_json(summary_text)
            if isinstance(rep, dict):
                items = rep.get("issues")
                if isinstance(items, list):
                    summary_items = items

        if isinstance(summary_items, list):
            for it in summary_items:
                it.setdefault("language", cand.get("language"))
                it.setdefault("file", cand.get("file"))
                it.setdefault("line", cand.get("line"))
            if not summary_items:
                try:
                    print(f"[JARVIS-SEC] no-issue {idx}/{total}: {cand.get('file')}:{cand.get('line')} ({cand.get('language')})")
                except Exception:
                    pass
            else:
                all_issues.extend(summary_items)
                try:
                    print(f"[JARVIS-SEC] issues-found {idx}/{total}: count={len(summary_items)} -> append report (summary)")
                except Exception:
                    pass
                _append_report(summary_items, "summary", task_id, cand)
            # 写入进度：任务结束（done）
            _progress_append(
                {
                    "event": "task_status",
                    "status": "done",
                    "task_id": task_id,
                    "idx": idx,
                    "total": total,
                    "candidate_signature": cand_sig,
                    "candidate": cand,
                    "issues_count": len(summary_items) if isinstance(summary_items, list) else 0,
                    "workspace_restore": workspace_restore_info,
                }
            )
            continue  # 已通过摘要处理，进入下一条

        # 摘要不可解析时，禁止回退解析主输出；直接记录失败并进入下一条
        try:
            print(f"[JARVIS-SEC] parse-fail {idx}/{total} (no <REPORT> in summary): {cand.get('file')}:{cand.get('line')} ({cand.get('language')})")
        except Exception:
            pass
        # 写入进度：任务结束（done，解析失败视为0问题）
        _progress_append(
            {
                "event": "task_status",
                "status": "done",
                "task_id": task_id,
                "idx": idx,
                "total": total,
                "candidate_signature": cand_sig,
                "candidate": cand,
                "issues_count": 0,
                "parse_fail": True,
                "workspace_restore": workspace_restore_info,
            }
        )
        continue
    # 4) 使用统一聚合器生成最终报告（JSON + Markdown）
    from jarvis.jarvis_sec.report import build_json_and_markdown
    return build_json_and_markdown(
        all_issues,
        scanned_root=summary.get("scanned_root"),
        scanned_files=summary.get("scanned_files"),
        meta=meta_records or None,
    )


def _try_parse_summary_report(text: str) -> Optional[Dict]:
    """
    从摘要文本中提取 <REPORT>...</REPORT> 内容，并解析为 dict（支持 JSON 或 YAML）。
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
        if isinstance(data, dict):
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