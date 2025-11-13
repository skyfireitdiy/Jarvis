# -*- coding: utf-8 -*-
"""验证相关模块"""

from typing import Dict, List, Optional
import typer

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_sec.prompts import build_verification_summary_prompt
from jarvis.jarvis_sec.parsers import try_parse_summary_report
from jarvis.jarvis_sec.agents import create_analysis_agent, subscribe_summary_event
from jarvis.jarvis_sec.utils import git_restore_if_dirty, sig_of, count_issues_from_file
from jarvis.jarvis_sec.analysis import (
    build_analysis_task_context,
    run_analysis_agent_with_retry,
    expand_and_filter_analysis_results,
)


def build_gid_to_verification_mapping(verification_results: List[Dict]) -> Dict[int, Dict]:
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


def merge_verified_items(
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


def merge_verified_items_without_verification(
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


def is_valid_verification_item(item: Dict) -> bool:
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


def run_verification_agent_with_retry(
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
            verification_summary_prompt_text = build_verification_summary_prompt()
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
            _changed_verify = git_restore_if_dirty(entry_path)
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
            verification_parsed, parse_error_verify = try_parse_summary_report(verification_summary_text)
            if parse_error_verify:
                prev_parse_error_verify = parse_error_verify
                try:
                    typer.secho(f"[jarvis-sec] 验证结果JSON解析失败: {parse_error_verify}", fg=typer.colors.YELLOW)
                except Exception:
                    pass
            else:
                prev_parse_error_verify = None
                if isinstance(verification_parsed, list):
                    if verification_parsed and all(is_valid_verification_item(item) for item in verification_parsed):
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


def process_verification_batch(
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
    agent = create_analysis_agent(task_id, llm_group, force_save_memory=force_save_memory)
    
    # 构建任务上下文
    per_task = build_analysis_task_context(batch, entry_path, langs)
    
    # 订阅摘要事件
    summary_container = subscribe_summary_event(agent)
    
    # 运行分析Agent并重试
    summary_items, workspace_restore_info = run_analysis_agent_with_retry(
        agent, per_task, summary_container, entry_path, task_id, bidx, meta_records
    )
    
    # 处理分析结果
    parse_fail = summary_items is None
    verified_items: List[Dict] = []
    
    if summary_items:
        # 展开并过滤分析结果
        items_with_risk, items_without_risk = expand_and_filter_analysis_results(summary_items)
        
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
                verified_items = merge_verified_items_without_verification(items_with_risk, batch)
                if verified_items:
                    for item in verified_items:
                        gid = int(item.get("gid", 0))
                        if gid >= 1:
                            gid_counts[gid] = gid_counts.get(gid, 0) + 1
                    typer.secho(f"[jarvis-sec] 批次 {bidx}/{total_batches} 跳过验证，直接写入: 数量={len(verified_items)}", fg=typer.colors.GREEN)
                    _append_report(verified_items, "analysis_only", task_id, {"batch": True, "candidates": batch})
                    current_count = count_issues_from_file(sec_dir)
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
                    summary_prompt=build_verification_summary_prompt(),
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
                verification_summary_container = subscribe_summary_event(verification_agent)
                
                verification_results, verification_parse_error = run_verification_agent_with_retry(
                    verification_agent,
                    verification_task,
                    build_verification_summary_prompt(),
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
                    gid_to_verification = build_gid_to_verification_mapping(verification_results)
                    
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
                    verified_items = merge_verified_items(items_with_risk, batch, gid_to_verification)
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
                    current_count = count_issues_from_file(sec_dir)
                    status_mgr.update_verification(
                        current_batch=bidx,
                        total_batches=total_batches,
                        issues_found=current_count,
                        message=f"已验证 {bidx}/{total_batches} 批次，发现 {current_count} 个问题（验证通过）"
                    )
                else:
                    typer.secho(f"[jarvis-sec] 批次 {bidx}/{total_batches} 验证后无有效告警: 分析 Agent 发现 {len(items_with_risk)} 个有风险的问题，验证后全部不通过", fg=typer.colors.BLUE)
                    current_count = count_issues_from_file(sec_dir)
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
            current_count = count_issues_from_file(sec_dir)
            status_mgr.update_verification(
                current_batch=bidx,
                total_batches=total_batches,
                issues_found=current_count,
                message=f"已验证 {bidx}/{total_batches} 批次"
            )

    # 为本批次所有候选写入 done 记录
    for c in batch:
        sig = sig_of(c)
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


def process_verification_phase(
    cluster_batches: List[List[Dict]],
    entry_path: str,
    langs: List[str],
    llm_group: Optional[str],
    sec_dir,
    status_mgr,
    _progress_append,
    _append_report,
    enable_verification: bool = True,
    force_save_memory: bool = False,
) -> List[Dict]:
    """处理验证阶段，返回所有已保存的告警"""
    from jarvis.jarvis_sec.file_manager import load_analysis_results, get_all_analyzed_gids
    
    batches: List[List[Dict]] = cluster_batches
    total_batches = len(batches)
    
    # 从 analysis.jsonl 中读取已分析的结果
    analysis_results = load_analysis_results(sec_dir)
    analyzed_gids = get_all_analyzed_gids(sec_dir)
    
    # 构建已完成的批次集合（通过 cluster_id 匹配）
    completed_cluster_ids = set()
    for result in analysis_results:
        cluster_id = result.get("cluster_id", "")
        if cluster_id:
            completed_cluster_ids.add(cluster_id)
    
    if completed_cluster_ids:
        try:
            typer.secho(f"[jarvis-sec] 断点恢复：从 analysis.jsonl 读取到 {len(completed_cluster_ids)} 个已完成的聚类", fg=typer.colors.BLUE)
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
    
    # 加载 clusters.jsonl 以匹配批次和聚类
    from jarvis.jarvis_sec.file_manager import load_clusters
    clusters = load_clusters(sec_dir)
    
    for bidx, batch in enumerate(batches, start=1):
        task_id = f"JARVIS-SEC-Batch-{bidx}"
        batch_file = batch[0].get("file") if batch else None
        
        # 检查批次是否已完成
        is_batch_completed = False
        
        # 从批次中提取 gids
        batch_gids = set()
        for item in batch:
            try:
                _gid = int(item.get("gid", 0))
                if _gid >= 1:
                    batch_gids.add(_gid)
            except Exception:
                pass
        
        # 方法1：通过 cluster_id 检查是否已完成
        # 查找匹配的聚类
        for cluster in clusters:
            cluster_file = str(cluster.get("file", ""))
            cluster_gids = set(cluster.get("gids", []))
            
            if cluster_file == batch_file and cluster_gids == batch_gids:
                cluster_id = cluster.get("cluster_id", "")
                if cluster_id and cluster_id in completed_cluster_ids:
                    is_batch_completed = True
                    break
        
        # 方法2：如果所有 gid 都已分析，则认为该批次已完成
        if not is_batch_completed and batch_gids and analyzed_gids:
            if batch_gids.issubset(analyzed_gids):
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
        process_verification_batch(
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
    
    # 从 analysis.jsonl 读取所有已验证的问题
    from jarvis.jarvis_sec.file_manager import get_verified_issue_gids, load_candidates
    verified_gids = get_verified_issue_gids(sec_dir)
    candidates = load_candidates(sec_dir)
    
    # 构建问题列表（从 analysis.jsonl 的 issues 字段）
    all_issues = []
    for result in analysis_results:
        issues = result.get("issues", [])
        if isinstance(issues, list):
            all_issues.extend(issues)
    
    return all_issues
