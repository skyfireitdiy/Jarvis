# -*- coding: utf-8 -*-
"""复核相关模块"""

from typing import Any, Dict, List, Optional

from jarvis.jarvis_utils.output import PrettyOutput

from jarvis.jarvis_sec.agents import create_review_agent
from jarvis.jarvis_sec.agents import subscribe_summary_event
from jarvis.jarvis_sec.parsers import try_parse_summary_report
from jarvis.jarvis_sec.prompts import build_verification_summary_prompt
from jarvis.jarvis_sec.prompts import get_review_summary_prompt
from jarvis.jarvis_sec.prompts import get_review_system_prompt
from jarvis.jarvis_sec.utils import git_restore_if_dirty


def build_review_task(
    review_batch: List[Dict[str, Any]], entry_path: str, langs: List[str]
) -> str:
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


def is_valid_review_item(item: Dict[str, Any]) -> bool:
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


def build_gid_to_review_mapping(
    review_results: List[Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    """构建gid到复核结果的映射（支持 gid 和 gids 两种格式）"""
    gid_to_review: Dict[int, Dict[str, Any]] = {}
    for rr in review_results:
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
                "review_notes": review_notes,
            }
    return gid_to_review


def process_review_batch(
    review_batch: List[Dict[str, Any]],
    review_results: Optional[List[Dict[str, Any]]],
    reviewed_clusters: List[Dict[str, Any]],
    reinstated_candidates: List[Dict[str, Any]],
    sec_dir: Optional[Any] = None,
) -> None:
    """处理单个复核批次的结果"""
    if review_results:
        # 构建gid到复核结果的映射
        gid_to_review = build_gid_to_review_mapping(review_results)

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
                PrettyOutput.auto_print(
                    f"🔵 [jarvis-sec] 复核结果：无效聚类（gids={cluster_gids}）理由不充分，重新加入验证流程"
                )
                for member in cluster_members:
                    reinstated_candidates.append(member)
                reviewed_clusters.append(
                    {
                        **invalid_cluster,
                        "review_result": "reinstated",
                        "review_notes": insufficient_review_result.get(
                            "review_notes", ""
                        )
                        if insufficient_review_result
                        else "",
                    }
                )
            else:
                # 理由充分，确认无效
                review_notes = ""
                if cluster_gids and gid_to_review.get(cluster_gids[0]):
                    review_notes = gid_to_review[cluster_gids[0]].get(
                        "review_notes", ""
                    )
                PrettyOutput.auto_print(
                    f"✅ [jarvis-sec] 复核结果：无效聚类（gids={cluster_gids}）理由充分，确认为无效"
                )
                reviewed_clusters.append(
                    {
                        **invalid_cluster,
                        "review_result": "confirmed_invalid",
                        "review_notes": review_notes,
                    }
                )

                # 将确认无效的gids保存到analysis.jsonl的false_positive_gids中，以便断点恢复时能正确识别已复核的无效聚类
                if sec_dir:
                    try:
                        from datetime import datetime
                        from pathlib import Path

                        from jarvis.jarvis_sec.file_manager import save_analysis_result

                        # 构建cluster_id
                        file_name = invalid_cluster.get("file", "")
                        batch_index = invalid_cluster.get("batch_index", 1)
                        cluster_id = f"{file_name}|{batch_index}|review"

                        # 将gids转换为整数列表
                        false_positive_gids = []
                        for gid_val in cluster_gids:
                            try:
                                gid_int = int(gid_val)
                                if gid_int >= 1:
                                    false_positive_gids.append(gid_int)
                            except Exception:
                                pass

                        # 保存分析结果
                        if false_positive_gids:
                            analysis_result = {
                                "cluster_id": cluster_id,
                                "file": file_name,
                                "batch_index": batch_index,
                                "gids": false_positive_gids,
                                "verified_gids": [],
                                "false_positive_gids": false_positive_gids,
                                "issues": [],
                                "analyzed_at": datetime.now().isoformat(),
                            }
                            save_analysis_result(Path(sec_dir), analysis_result)
                    except Exception as e:
                        # 保存失败不影响主流程，只记录警告
                        try:
                            PrettyOutput.auto_print(
                                f"⚠️ [jarvis-sec] 警告：保存复核结果到analysis.jsonl失败: {str(e)}"
                            )
                        except Exception:
                            pass
    else:
        # 复核结果解析失败，保守策略：重新加入验证流程
        PrettyOutput.auto_print(
            "⚠️ [jarvis-sec] 警告：复核结果解析失败，保守策略：将批次中的所有候选重新加入验证流程"
        )
        for invalid_cluster in review_batch:
            cluster_members = invalid_cluster.get("members", [])
            for member in cluster_members:
                reinstated_candidates.append(member)
            reviewed_clusters.append(
                {
                    **invalid_cluster,
                    "review_result": "reinstated",
                    "review_notes": "复核结果解析失败，保守策略重新加入验证",
                }
            )


def process_review_batch_items(
    review_batch: List[Dict[str, Any]],
    review_results: Optional[List[Dict[str, Any]]],
    reviewed_clusters: List[Dict[str, Any]],
    reinstated_candidates: List[Dict[str, Any]],
    sec_dir: Optional[Any] = None,
) -> None:
    """处理单个复核批次的结果"""
    process_review_batch(
        review_batch,
        review_results,
        reviewed_clusters,
        reinstated_candidates,
        sec_dir,
    )


def reinstated_candidates_to_cluster_batches(
    reinstated_candidates: List[Dict[str, Any]],
    cluster_batches: List[List[Dict[str, Any]]],
    _progress_append: Any,
) -> None:
    """将重新加入的候选添加到cluster_batches"""
    from collections import defaultdict as _dd2

    if not reinstated_candidates:
        return

    PrettyOutput.auto_print(
        f"🔄 [jarvis-sec] 复核完成：{len(reinstated_candidates)} 个候选重新加入验证流程"
    )
    # 按文件分组重新加入的候选
    reinstated_by_file: Dict[str, List[Dict[str, Any]]] = _dd2(list)
    for cand in reinstated_candidates:
        file_key = str(cand.get("file") or "")
        reinstated_by_file[file_key].append(cand)

    # 为每个文件的重新加入候选创建批次
    for file_key, cands in reinstated_by_file.items():
        if cands:
            cluster_batches.append(cands)
            _progress_append(
                {
                    "event": "review_reinstated",
                    "file": file_key,
                    "gids": [c.get("gid") for c in cands],
                    "count": len(cands),
                }
            )


def run_review_agent_with_retry(
    review_agent: Any,
    review_task: str,
    review_summary_prompt: str,
    entry_path: str,
    review_summary_container: Dict[str, str],
) -> tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """运行复核Agent并永久重试直到格式正确，返回(复核结果, 解析错误)"""
    use_direct_model_review = False
    prev_parse_error_review: Optional[str] = None
    review_attempt = 0

    while True:
        review_attempt += 1
        review_summary_container["text"] = ""

        if use_direct_model_review:
            # 格式校验失败后，直接调用模型接口
            review_summary_prompt_text = build_verification_summary_prompt()
            error_guidance = ""
            if prev_parse_error_review:
                error_guidance = f"\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n- JSON解析失败: {prev_parse_error_review}\n\n请确保输出的JSON格式正确，包括正确的引号、逗号、大括号等。仅输出一个 <REPORT> 块，块内直接包含 JSON 数组（不需要额外的标签）。支持jsonnet语法（如尾随逗号、注释、||| 或 ``` 分隔符多行字符串等）。"

            full_review_prompt = (
                f"{review_task}{error_guidance}\n\n{review_summary_prompt_text}"
            )
            try:
                review_response = review_agent.model.chat_until_success(
                    full_review_prompt
                )
                review_summary_container["text"] = review_response
            except Exception as e:
                try:
                    PrettyOutput.auto_print(
                        f"✨ [jarvis-sec] 复核阶段直接模型调用失败: {e}，回退到 run()",
                        timestamp=True,
                    )
                except Exception:
                    pass
                review_agent.run(review_task)
        else:
            review_agent.run(review_task)

        # 工作区保护
        try:
            _changed_review = git_restore_if_dirty(entry_path)
            if _changed_review:
                try:
                    PrettyOutput.auto_print(
                        f"✨ [jarvis-sec] 复核 Agent 工作区已恢复 ({_changed_review} 个文件）",
                        timestamp=True,
                    )
                except Exception:
                    pass
        except Exception:
            pass

        # 解析复核结果
        review_summary_text = review_summary_container.get("text", "")
        parse_error_review = None
        if review_summary_text:
            review_parsed, parse_error_review = try_parse_summary_report(
                review_summary_text
            )
            if parse_error_review:
                prev_parse_error_review = parse_error_review
                try:
                    PrettyOutput.auto_print(
                        f"✨ [jarvis-sec] 复核结果JSON解析失败: {parse_error_review}",
                        timestamp=True,
                    )
                except Exception:
                    pass
            else:
                prev_parse_error_review = None
                if isinstance(review_parsed, list):
                    # 验证复核结果格式
                    if review_parsed and all(
                        is_valid_review_item(item) for item in review_parsed
                    ):
                        return review_parsed, None

        # 格式校验失败，后续重试使用直接模型调用
        use_direct_model_review = True
        if parse_error_review:
            try:
                PrettyOutput.auto_print(
                    f"✨ [jarvis-sec] 复核结果JSON解析失败 -> 重试第 {review_attempt} 次 (使用直接模型调用，将反馈解析错误)",
                    timestamp=True,
                )
            except Exception:
                pass
        else:
            try:
                PrettyOutput.auto_print(
                    f"✨ [jarvis-sec] 复核结果格式无效 -> 重试第 {review_attempt} 次 (使用直接模型调用)",
                    timestamp=True,
                )
            except Exception:
                pass


def process_review_phase(
    invalid_clusters_for_review: List[Dict[str, Any]],
    entry_path: str,
    langs: List[str],
    llm_group: Optional[str],
    status_mgr: Any,
    _progress_append: Any,
    cluster_batches: List[List[Dict[str, Any]]],
    sec_dir: Optional[Any] = None,
) -> List[List[Dict[str, Any]]]:
    """
    处理复核阶段：验证所有标记为无效的聚类。

    返回: 更新后的 cluster_batches（包含重新加入验证的候选）
    """
    if not invalid_clusters_for_review:
        PrettyOutput.auto_print("🔵 [jarvis-sec] 无无效聚类需要复核")
        return cluster_batches

    PrettyOutput.auto_print(
        f"✨ \n[jarvis-sec] 开始复核 {len(invalid_clusters_for_review)} 个无效聚类...",
        timestamp=True,
    )
    status_mgr.update_review(
        current_review=0,
        total_reviews=len(invalid_clusters_for_review),
        message="开始复核无效聚类...",
    )

    # 按批次复核（每批最多10个无效聚类，避免上下文过长）
    review_batch_size = 10
    reviewed_clusters: List[Dict[str, Any]] = []
    reinstated_candidates: List[Dict[str, Any]] = []  # 重新加入验证的候选

    get_review_system_prompt()
    review_summary_prompt = get_review_summary_prompt()

    for review_idx in range(0, len(invalid_clusters_for_review), review_batch_size):
        review_batch = invalid_clusters_for_review[
            review_idx : review_idx + review_batch_size
        ]
        current_review_num = review_idx // review_batch_size + 1
        total_review_batches = (
            len(invalid_clusters_for_review) + review_batch_size - 1
        ) // review_batch_size

        PrettyOutput.auto_print(
            f"✨ [jarvis-sec] 复核批次 {current_review_num}/{total_review_batches}: {len(review_batch)} 个无效聚类",
            timestamp=True,
        )
        status_mgr.update_review(
            current_review=current_review_num,
            total_reviews=total_review_batches,
            message=f"正在复核批次 {current_review_num}/{total_review_batches}",
        )

        # 构建复核任务
        review_task = build_review_task(review_batch, entry_path, langs)

        # 创建复核Agent
        review_agent = create_review_agent(current_review_num, llm_group)

        # 订阅复核Agent的摘要
        review_summary_container = subscribe_summary_event(review_agent)

        # 运行复核Agent（永久重试直到格式正确）
        review_results, parse_error = run_review_agent_with_retry(
            review_agent,
            review_task,
            review_summary_prompt,
            entry_path,
            review_summary_container,
        )

        # 处理复核结果
        process_review_batch_items(
            review_batch,
            review_results,
            reviewed_clusters,
            reinstated_candidates,
            sec_dir,
        )

        # 记录每个已复核的无效聚类的 gids（包括确认无效的和重新加入验证的）
        for invalid_cluster in review_batch:
            cluster_gids = invalid_cluster.get("gids", [])
            if cluster_gids:
                _progress_append(
                    {
                        "event": "review_invalid_cluster",
                        "gids": cluster_gids,
                        "file": invalid_cluster.get("file"),
                        "batch_index": invalid_cluster.get("batch_index"),
                    }
                )

    # 将重新加入验证的候选添加到cluster_batches
    reinstated_candidates_to_cluster_batches(
        reinstated_candidates,
        cluster_batches,
        _progress_append,
    )

    if not reinstated_candidates:
        PrettyOutput.auto_print(
            "✨ [jarvis-sec] 复核完成：所有无效聚类理由充分，确认为无效", timestamp=True
        )

    # 记录复核结果（汇总）
    _progress_append(
        {
            "event": "review_completed",
            "total_reviewed": len(invalid_clusters_for_review),
            "reinstated": len(reinstated_candidates),
            "confirmed_invalid": len(invalid_clusters_for_review)
            - len(reinstated_candidates),
        }
    )

    # 记录所有已复核的无效聚类的 gids（用于断点恢复时跳过已复核的聚类）
    all_reviewed_gids = set()
    for invalid_cluster in invalid_clusters_for_review:
        cluster_gids = invalid_cluster.get("gids", [])
        for gid_val in cluster_gids:
            try:
                gid_int = int(gid_val)
                if gid_int >= 1:
                    all_reviewed_gids.add(gid_int)
            except Exception:
                pass

    if all_reviewed_gids:
        _progress_append(
            {
                "event": "review_all_gids",
                "gids": sorted(list(all_reviewed_gids)),
                "total": len(all_reviewed_gids),
            }
        )
    status_mgr.update_review(
        current_review=len(invalid_clusters_for_review),
        total_reviews=len(invalid_clusters_for_review),
        message=f"复核完成：{len(reinstated_candidates)} 个候选重新加入验证",
    )

    return cluster_batches
