# -*- coding: utf-8 -*-
# mypy: disable-error-code=unreachable
"""聚类相关模块"""

import json
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional


from jarvis.jarvis_sec.agents import create_cluster_agent
from jarvis.jarvis_sec.agents import subscribe_summary_event
from jarvis.jarvis_sec.file_manager import get_all_clustered_gids
from jarvis.jarvis_sec.file_manager import get_clusters_file
from jarvis.jarvis_sec.file_manager import load_clusters
from jarvis.jarvis_sec.file_manager import save_cluster
from jarvis.jarvis_sec.file_manager import validate_clustering_completeness
from jarvis.jarvis_sec.parsers import parse_clusters_from_text
from jarvis.jarvis_sec.prompts import get_cluster_summary_prompt
from jarvis.jarvis_sec.utils import group_candidates_by_file
from jarvis.jarvis_utils.output import PrettyOutput


def load_existing_clusters(
    sec_dir: Path,
) -> tuple[Dict[tuple[str, int], List[Dict[str, Any]]], set[str], set[int]]:
    """
    读取已有聚类报告以支持断点恢复。

    优先使用新的 clusters.jsonl 文件，如果不存在则回退到旧的 cluster_report.jsonl。

    返回: (_existing_clusters, _completed_cluster_batches, _reviewed_invalid_gids)
    """
    _existing_clusters: Dict[tuple[str, int], List[Dict[str, Any]]] = {}
    _completed_cluster_batches: set[str] = set()
    _reviewed_invalid_gids: set[int] = set()  # 已复核的无效聚类的 gids

    try:
        # 优先使用新的 clusters.jsonl 文件
        clusters = load_clusters(sec_dir)

        if clusters:
            # 从新的 clusters.jsonl 加载
            for cluster in clusters:
                f_name = str(cluster.get("file") or "")
                bidx = int(cluster.get("batch_index", 1) or 1)
                _existing_clusters.setdefault((f_name, bidx), []).append(cluster)

                # 从分析结果文件中读取已复核的无效聚类
                # 如果聚类是无效的，且其gids都在分析结果中被标记为误报，则认为已复核
                if cluster.get("is_invalid", False):
                    gids_list = cluster.get("gids", [])
                    if isinstance(gids_list, list):
                        # 检查这些gid是否都在分析结果中被标记为误报
                        from jarvis.jarvis_sec.file_manager import (
                            get_false_positive_gids,
                        )

                        false_positive_gids = get_false_positive_gids(sec_dir)
                        all_false_positive = all(
                            int(gid_val) in false_positive_gids
                            for gid_val in gids_list
                            if isinstance(gid_val, (int, str))
                        )
                        if all_false_positive:
                            for gid_val in gids_list:
                                try:
                                    gid_int = int(gid_val)
                                    if gid_int >= 1:
                                        _reviewed_invalid_gids.add(gid_int)
                                except Exception:
                                    pass
        # 不再回退到旧的 cluster_report.jsonl，因为用户要求不考虑兼容
    except Exception:
        _existing_clusters = {}
        _completed_cluster_batches = set()
        _reviewed_invalid_gids = set()

    return _existing_clusters, _completed_cluster_batches, _reviewed_invalid_gids


def restore_clusters_from_checkpoint(
    _existing_clusters: Dict[tuple[str, int], List[Dict[str, Any]]],
    _file_groups: Dict[str, List[Dict[str, Any]]],
    _reviewed_invalid_gids: set[int],
) -> tuple[
    List[List[Dict[str, Any]]], List[Dict[str, Any]], List[Dict[str, Any]], set[int]
]:
    """
    从断点恢复聚类结果。

    返回: (cluster_batches, cluster_records, invalid_clusters_for_review, clustered_gids)
    """
    # 1. 收集所有候选的 gid
    all_candidate_gids_in_clustering = set[int]()
    gid_to_candidate: Dict[int, Dict[str, Any]] = {}
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
    clustered_gids = set[
        int
    ]()  # 已聚类的 gid（包括有效和无效的，因为无效的也需要进入复核阶段）
    invalid_clusters_for_review: List[Dict[str, Any]] = []  # 无效聚类列表（从断点恢复）
    cluster_batches: List[List[Dict[str, Any]]] = []
    cluster_records: List[Dict[str, Any]] = []
    skipped_reviewed_count = 0  # 已复核的无效聚类数量（跳过）
    missing_gids_in_restore = set[int]()  # 记录恢复时无法匹配的gid（用于诊断）

    # 首先，从所有聚类记录中收集所有已聚类的 gid（无论是否在当前候选集中）
    # 这样可以确保即使匹配失败，只要 gid 在 clusters.jsonl 中且在当前候选集中，就会被计入 clustered_gids
    all_clustered_gids_from_file = set[int]()
    for (_file_key, _batch_idx), cluster_recs in _existing_clusters.items():
        for rec in cluster_recs:
            gids_list = rec.get("gids", [])
            if isinstance(gids_list, list):
                for _gid in gids_list:
                    try:
                        _gid_int = int(_gid)
                        if _gid_int >= 1:
                            all_clustered_gids_from_file.add(_gid_int)
                    except Exception:
                        pass

    # 对于所有在 clusters.jsonl 中记录的 gid，如果它们也在当前候选集中，就计入 clustered_gids
    # 这样可以避免因为匹配失败而导致的遗漏
    for _gid_int in all_clustered_gids_from_file:
        if _gid_int in all_candidate_gids_in_clustering:
            clustered_gids.add(_gid_int)

    # 然后，尝试恢复具体的聚类信息（用于恢复 cluster_batches 和 invalid_clusters_for_review）
    for (_file_key, _batch_idx), cluster_recs in _existing_clusters.items():
        for rec in cluster_recs:
            gids_list = rec.get("gids", [])
            if not gids_list:
                continue
            is_invalid = rec.get("is_invalid", False)
            verification = str(rec.get("verification", "")).strip()
            members: List[Dict[str, Any]] = []
            for _gid in gids_list:
                try:
                    _gid_int = int(_gid)
                    if _gid_int >= 1:
                        if _gid_int in gid_to_candidate:
                            # 只有当 gid 在当前运行中存在时，才恢复该聚类
                            candidate = gid_to_candidate[_gid_int]
                            candidate["verify"] = verification
                            members.append(candidate)
                        else:
                            # gid不在gid_to_candidate中，说明无法直接匹配
                            # 可能的原因：
                            # 1. gid不在当前候选集中（候选列表变化）- 这是正常的，不应该计入clustered_gids
                            # 2. gid在当前候选集中但无法匹配（数据不一致）- 理论上不应该发生
                            # 由于all_candidate_gids_in_clustering是从_file_groups收集的，而gid_to_candidate也是从_file_groups构建的
                            # 如果gid在all_candidate_gids_in_clustering中，理论上应该在gid_to_candidate中
                            # 但为了保险起见，尝试从_file_groups中查找
                            if _gid_int in all_candidate_gids_in_clustering:
                                # gid在当前候选集中，尝试从_file_groups中查找（双重保险）
                                found_candidate = None
                                for _file, _items in _file_groups.items():
                                    for it in _items:
                                        try:
                                            it_gid = int(it.get("gid", 0))
                                            if it_gid == _gid_int:
                                                found_candidate = it
                                                break
                                        except Exception:
                                            pass
                                    if found_candidate:
                                        break

                                if found_candidate:
                                    # 找到了对应的候选，添加到members中
                                    found_candidate["verify"] = verification
                                    members.append(found_candidate)
                                else:
                                    # 理论上不应该到达这里，因为all_candidate_gids_in_clustering是从_file_groups收集的
                                    # 如果gid在all_candidate_gids_in_clustering中，应该能在_file_groups中找到
                                    # 但如果确实找不到，说明有bug，记录诊断信息
                                    # 注意：即使找不到，gid 也已经在上面的循环中被计入了 clustered_gids
                                    missing_gids_in_restore.add(_gid_int)
                            else:
                                # gid不在当前候选集中，说明候选列表发生了变化
                                # 这些gid不应该被计入clustered_gids，因为它们不在当前运行中
                                # 这是正常情况，不需要记录为遗漏（因为它们确实不在当前运行中）
                                pass
                except Exception:
                    pass

            # 只有当至少有一个gid在当前候选集中时，才恢复这个聚类
            # 如果所有gid都不在当前候选集中，说明这些gid对应的候选在当前运行中不存在
            # 这种情况下，不应该恢复这个聚类，因为这些gid不在当前运行中
            if members:
                if is_invalid:
                    # 检查该无效聚类的所有 gids 是否都已被复核过
                    cluster_gids = [m.get("gid") for m in members]
                    # 将 cluster_gids 转换为 int 类型进行比较
                    cluster_gids_int = set()
                    for gid_val in cluster_gids:
                        try:
                            if gid_val is None:
                                continue
                            gid_int = int(gid_val)
                            if gid_int >= 1:
                                cluster_gids_int.add(gid_int)
                        except Exception:
                            pass
                    # 检查所有 gid 是否都已被复核过
                    all_reviewed = cluster_gids_int and cluster_gids_int.issubset(
                        _reviewed_invalid_gids
                    )

                    if not all_reviewed:
                        # 如果还有未复核的 gid，收集到复核列表
                        invalid_clusters_for_review.append(
                            {
                                "file": _file_key,
                                "batch_index": _batch_idx,
                                "gids": cluster_gids,
                                "verification": verification,
                                "invalid_reason": str(
                                    rec.get("invalid_reason", "")
                                ).strip(),
                                "members": members,  # 保存候选信息，用于复核后可能重新加入验证
                                "count": len(members),
                            }
                        )
                    else:
                        # 如果所有 gid 都已被复核过，则跳过（不加入复核列表）
                        skipped_reviewed_count += 1
                else:
                    # 有效聚类：恢复到 cluster_batches
                    cluster_batches.append(members)
                    cluster_records.append(
                        {
                            "file": _file_key,
                            "verification": verification,
                            "gids": [m.get("gid") for m in members],
                            "count": len(members),
                            "batch_index": _batch_idx,
                            "is_invalid": False,
                        }
                    )

    # 输出统计信息
    if _reviewed_invalid_gids:
        try:
            PrettyOutput.auto_print(
                f"[jarvis-sec] 断点恢复：发现 {len(_reviewed_invalid_gids)} 个已复核的无效聚类 gids",
            )
        except Exception:
            pass
    if skipped_reviewed_count > 0:
        try:
            PrettyOutput.auto_print(
                f"[jarvis-sec] 断点恢复：跳过 {skipped_reviewed_count} 个已复核的无效聚类",
            )
        except Exception:
            pass
    if missing_gids_in_restore:
        # 诊断信息：记录恢复时无法匹配的gid数量
        # 注意：这些gid在当前候选集中，但无法匹配，说明可能存在数据不一致的问题
        # 正常情况下不应该出现这种情况
        missing_count = len(missing_gids_in_restore)
        try:
            if missing_count <= 20:
                missing_list = sorted(list(missing_gids_in_restore))
                PrettyOutput.auto_print(
                    f"[jarvis-sec] 断点恢复诊断：发现 {missing_count} 个gid在当前候选集中但无法匹配（可能存在数据不一致）: {missing_list}",
                )
            else:
                missing_list = sorted(list(missing_gids_in_restore))
                display_list = missing_list[:10] + ["..."] + missing_list[-10:]
                PrettyOutput.auto_print(
                    f"[jarvis-sec] 断点恢复诊断：发现 {missing_count} 个gid在当前候选集中但无法匹配（可能存在数据不一致）: {display_list}",
                )
        except Exception:
            pass

    return cluster_batches, cluster_records, invalid_clusters_for_review, clustered_gids


def create_cluster_snapshot_writer(
    sec_dir: Path,
    cluster_records: List[Dict[str, Any]],
    compact_candidates: List[Dict[str, Any]],
    _progress_append: Any,
) -> Any:
    """创建聚类快照写入函数"""

    def _write_cluster_batch_snapshot(batch_records: List[Dict[str, Any]]) -> None:
        """写入单个批次的聚类结果，支持增量保存"""
        try:
            # 按 (file, batch_index) 分组，为每个分组内的记录生成唯一的 cluster_index
            from collections import defaultdict

            records_by_key = defaultdict(list)
            for record in batch_records:
                file_name = str(record.get("file", ""))
                batch_index = int(record.get("batch_index", 0))
                key = (file_name, batch_index)
                records_by_key[key].append(record)

            # 为每个分组内的记录生成 cluster_index
            for (file_name, batch_index), records in records_by_key.items():
                for local_idx, record in enumerate(records):
                    # 如果 record 中没有 cluster_index，使用本地索引
                    cluster_index = record.get("cluster_index")
                    if cluster_index is None:
                        cluster_index = local_idx
                    else:
                        cluster_index = int(cluster_index)

                    cluster_id = f"{file_name}|{batch_index}|{cluster_index}"

                    # 转换为新的格式
                    cluster = {
                        "cluster_id": cluster_id,
                        "file": file_name,
                        "batch_index": batch_index,
                        "cluster_index": cluster_index,
                        "gids": record.get("gids", []),
                        "verification": str(record.get("verification", "")).strip(),
                        "is_invalid": record.get("is_invalid", False),
                        "invalid_reason": str(record.get("invalid_reason", "")).strip(),
                    }

                    # 使用新的文件管理器保存
                    save_cluster(sec_dir, cluster)
        except Exception:
            pass

    def _write_cluster_report_snapshot() -> None:
        """写入聚类报告快照"""
        try:
            # 为每个记录生成 cluster_id 并保存
            for idx, record in enumerate(cluster_records):
                file_name = str(record.get("file", ""))
                batch_index = int(record.get("batch_index", 0))
                cluster_index = idx  # 使用索引作为 cluster_index
                cluster_id = f"{file_name}|{batch_index}|{cluster_index}"

                # 转换为新的格式
                cluster = {
                    "cluster_id": cluster_id,
                    "file": file_name,
                    "batch_index": batch_index,
                    "cluster_index": cluster_index,
                    "gids": record.get("gids", []),
                    "verification": str(record.get("verification", "")).strip(),
                    "is_invalid": record.get("is_invalid", False),
                    "invalid_reason": str(record.get("invalid_reason", "")).strip(),
                }

                # 使用新的文件管理器保存
                save_cluster(sec_dir, cluster)

            _progress_append(
                {
                    "event": "cluster_report_snapshot",
                    "path": str(get_clusters_file(sec_dir)),
                    "clusters": len(cluster_records),
                    "total_candidates": len(compact_candidates),
                }
            )
        except Exception:
            pass

    return _write_cluster_batch_snapshot, _write_cluster_report_snapshot


def collect_candidate_gids(file_groups: Dict[str, List[Dict[str, Any]]]) -> set[int]:
    """收集所有候选的 gid"""
    all_gids = set[int]()
    for _file, _items in file_groups.items():
        for it in _items:
            try:
                _gid = int(it.get("gid", 0))
                if _gid >= 1:
                    all_gids.add(_gid)
            except Exception:
                pass
    return all_gids


def collect_clustered_gids(
    cluster_batches: List[List[Dict[str, Any]]],
    invalid_clusters_for_review: List[Dict[str, Any]],
) -> set[int]:
    """收集所有已聚类的 gid"""
    all_clustered_gids = set[int]()
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


# 注意：supplement_missing_gids_for_clustering函数已移除
# 由于gid现在保存在heuristic_issues.jsonl中，恢复逻辑已经能够正确匹配所有gid
# 理论上不应该再出现遗漏的gid，不需要补充处理


def filter_single_gid_clusters(
    cluster_batches: List[List[Dict[str, Any]]],
    sec_dir: Path,
    _progress_append: Any,
) -> List[List[Dict[str, Any]]]:
    """
    过滤掉单独聚类的批次（只包含1个gid的批次），避免分析工作量激增。

    这些单独聚类通常是之前为遗漏的gid自动创建的，现在不再需要。
    """
    filtered_batches: List[List[Dict[str, Any]]] = []
    removed_count = 0
    removed_gids = set[int]()

    # 读取已分析的gid（从analysis.jsonl）
    from jarvis.jarvis_sec.file_manager import get_all_analyzed_gids

    processed_gids = set[int](get_all_analyzed_gids(sec_dir))

    # 读取clusters.jsonl中的所有gid
    cluster_report_gids = get_all_clustered_gids(sec_dir)

    for batch in cluster_batches:
        # 检查批次大小
        if len(batch) == 1:
            # 这是单独聚类，检查是否需要保留
            single_item = batch[0]
            try:
                gid = int(single_item.get("gid", 0))
                if gid >= 1:
                    # 如果gid已经在analysis.jsonl中分析过，安全移除（不会遗漏）
                    if gid in processed_gids:
                        removed_count += 1
                        removed_gids.add(gid)
                        _progress_append(
                            {
                                "event": "single_cluster_removed",
                                "gid": gid,
                                "reason": "already_analyzed",
                            }
                        )
                        continue

                    # 检查verification字段，如果是默认的"验证候选 X 的安全风险"，说明是自动创建的单独聚类
                    verification = str(single_item.get("verify", "")).strip()
                    is_auto_created = verification.startswith(
                        "验证候选 "
                    ) and verification.endswith(" 的安全风险")

                    if is_auto_created:
                        # 这是自动创建的单独聚类
                        # 如果gid在clusters.jsonl中有记录，说明已经聚类过了，可以安全移除
                        # 如果不在clusters.jsonl中，也不在analysis.jsonl中，说明需要分析，应该保留
                        if gid in cluster_report_gids:
                            removed_count += 1
                            removed_gids.add(gid)
                            _progress_append(
                                {
                                    "event": "single_cluster_removed",
                                    "gid": gid,
                                    "reason": "auto_created_and_in_clusters",
                                }
                            )
                            continue
                        else:
                            # 自动创建的单独聚类，但不在clusters.jsonl中，也不在analysis.jsonl中
                            # 说明需要分析，保留它（避免遗漏告警）
                            # 但给出警告，因为这种情况不应该发生
                            try:
                                PrettyOutput.auto_print(
                                    f"[jarvis-sec] 警告：gid={gid}是自动创建的单独聚类，但不在clusters.jsonl中，保留以避免遗漏告警",
                                )
                            except Exception:
                                pass
                    else:
                        # 不是自动创建的单独聚类，可能是正常的单告警文件（handle_single_alert_file创建的）
                        # 保留它（避免遗漏告警）
                        pass
            except Exception:
                pass

        # 保留这个批次（不是单独聚类，或者单独聚类但需要保留）
        filtered_batches.append(batch)

    if removed_count > 0:
        try:
            if len(removed_gids) <= 20:
                PrettyOutput.auto_print(
                    f"[jarvis-sec] 已移除 {removed_count} 个单独聚类批次（共{len(removed_gids)}个gid），避免分析工作量激增",
                )
                PrettyOutput.auto_print(
                    f"[jarvis-sec] 移除的gid: {sorted(list(removed_gids))}",
                )
            else:
                removed_gids_list = sorted(list(removed_gids))
                display_list = (
                    removed_gids_list[:10] + ["..."] + removed_gids_list[-10:]
                )
                PrettyOutput.auto_print(
                    f"[jarvis-sec] 已移除 {removed_count} 个单独聚类批次（共{len(removed_gids)}个gid），避免分析工作量激增",
                )
                PrettyOutput.auto_print(
                    f"[jarvis-sec] 移除的gid（示例）: {display_list}",
                )
        except Exception:
            pass

    return filtered_batches


def handle_single_alert_file(
    file: str,
    single_item: Dict[str, Any],
    single_gid: int,
    cluster_batches: List[List[Dict[str, Any]]],
    cluster_records: List[Dict[str, Any]],
    _progress_append: Any,
    _write_cluster_batch_snapshot: Any,
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
        rec
        for rec in cluster_records
        if rec.get("file") == file and rec.get("batch_index") == 1
    ]
    if current_batch_records:
        _write_cluster_batch_snapshot(current_batch_records)
    PrettyOutput.auto_print(
        f"[jarvis-sec] 文件 {file} 仅有一个告警（gid={single_gid}），跳过聚类直接写入",
    )


def validate_cluster_format(
    cluster_items: List[Dict[str, Any]],
) -> tuple[bool, List[str]]:
    """验证聚类结果的格式，返回(是否有效, 错误详情列表)"""
    if not isinstance(cluster_items, list) or not cluster_items:
        return False, ["结果不是数组或数组为空"]

    errors: List[str] = []
    for idx, it in enumerate(cluster_items):
        # 验证每个元素必须是字典
        if not isinstance(it, dict):
            errors.append(f"元素{idx}不是字典")
            continue

        # 获取和验证必需字段
        vals = it.get("gids", [])
        verification = it.get("verification", "")

        # 验证verification字段
        if not isinstance(verification, str):
            errors.append(f"元素{idx}的verification不是字符串")
            continue

        # 验证gids字段
        if not isinstance(vals, list):
            errors.append(f"元素{idx}的gids不是数组")
            continue

        # 验证gids中的每个元素是有效整数
        for gid_idx, gid_val in enumerate(vals):
            try:
                gid_int = int(gid_val)
                if gid_int < 1:
                    errors.append(
                        f"元素{idx}的gids[{gid_idx}]不是有效的正整数（值为{gid_val}）"
                    )
                    break
            except (ValueError, TypeError):
                errors.append(
                    f"元素{idx}的gids[{gid_idx}]不是有效的整数（值为{gid_val}）"
                )
                break
        else:
            # 只有前面的验证都通过才继续
            # 验证is_invalid字段
            is_invalid_val = it.get("is_invalid")
            if is_invalid_val is None:
                errors.append(f"元素{idx}缺少is_invalid字段（必填）")
                continue
            if not isinstance(is_invalid_val, bool):
                errors.append(f"元素{idx}的is_invalid不是布尔值")
                continue

            # 如果is_invalid为true，验证invalid_reason
            if is_invalid_val is True:
                invalid_reason = it.get("invalid_reason", "")
                if not isinstance(invalid_reason, str) or not invalid_reason.strip():
                    errors.append(
                        f"元素{idx}的is_invalid为true但缺少invalid_reason字段或理由为空（必填）"
                    )

    if errors:
        return False, errors
    return True, []


def extract_classified_gids(cluster_items: List[Dict[str, Any]]) -> set[int]:
    """从聚类结果中提取所有已分类的gid

    注意：此函数假设格式验证已经通过，所有gid都是有效的整数。
    如果遇到格式错误的gid，会记录警告但不会抛出异常（因为格式验证应该已经捕获了这些问题）。
    """
    classified_gids = set[int]()
    for cl in cluster_items:
        raw_gids = cl.get("gids", [])
        if isinstance(raw_gids, list):
            for x in raw_gids:
                try:
                    xi = int(x)
                    if xi >= 1:
                        classified_gids.add(xi)
                except (ValueError, TypeError):
                    # 理论上不应该到达这里（格式验证应该已经捕获），但如果到达了，记录警告
                    try:
                        PrettyOutput.auto_print(
                            f"[jarvis-sec] 警告：在提取gid时遇到格式错误（值={x}，类型={type(x).__name__}），这不应该发生（格式验证应该已捕获）",
                        )
                    except Exception:
                        pass
                    continue
    return classified_gids


def build_cluster_retry_task(
    file: str,
    missing_gids: set[int],
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
        retry_task += (
            f"\n\n**遗漏的gid（共{missing_count}个，必须被分类）：**\n"
            + ", ".join(str(gid) for gid in missing_gids_list)
        )
    if error_details:
        retry_task += "\n\n**格式错误：**\n" + "\n".join(
            f"- {detail}" for detail in error_details
        )
    return retry_task


def build_cluster_error_guidance(
    error_details: List[str],
    missing_gids: set[int],
) -> str:
    """构建聚类错误指导信息"""
    error_guidance = ""
    if error_details:
        error_guidance = (
            "\n\n**格式错误详情（请根据以下错误修复输出格式）：**\n"
            + "\n".join(f"- {detail}" for detail in error_details)
        )
    if missing_gids:
        missing_gids_list = sorted(list(missing_gids))
        missing_count = len(missing_gids)
        error_guidance += (
            f"\n\n**完整性错误：遗漏了 {missing_count} 个 gid，这些 gid 必须被分类：**\n"
            + ", ".join(str(gid) for gid in missing_gids_list)
        )
    return error_guidance


def run_cluster_agent_direct_model(
    cluster_agent: Any,
    cluster_task: str,
    cluster_summary_prompt: str,
    file: str,
    missing_gids: set[int],
    error_details: List[str],
    _cluster_summary: Dict[str, str],
) -> None:
    """使用直接模型调用运行聚类Agent"""
    retry_task = build_cluster_retry_task(file, missing_gids, error_details)
    error_guidance = build_cluster_error_guidance(error_details, missing_gids)
    full_prompt = f"{retry_task}{error_guidance}\n\n{cluster_summary_prompt}"
    try:
        response = cluster_agent.model.chat_until_success(full_prompt)
        _cluster_summary["text"] = response
    except Exception as e:
        try:
            PrettyOutput.auto_print(
                f"[jarvis-sec] 直接模型调用失败: {e}，回退到 run()",
            )
        except Exception:
            pass
        cluster_agent.run(cluster_task)


def validate_cluster_result(
    cluster_items: Optional[List[Dict[str, Any]]],
    parse_error: Optional[str],
    attempt: int,
) -> tuple[bool, List[str]]:
    """验证聚类结果格式"""
    if parse_error:
        error_details = [f"JSON解析失败: {parse_error}"]
        PrettyOutput.auto_print(f"[jarvis-sec] JSON解析失败: {parse_error}")
        return False, error_details
    else:
        valid, error_details = validate_cluster_format(cluster_items or [])
        if not valid:
            PrettyOutput.auto_print(
                f"[jarvis-sec] 聚类结果格式无效（{'; '.join(error_details)}），重试第 {attempt} 次（使用直接模型调用）",
            )
        return valid, error_details


def check_cluster_completeness(
    cluster_items: List[Dict[str, Any]],
    input_gids: set[int],
    attempt: int,
) -> tuple[bool, set[int]]:
    """检查聚类完整性，返回(是否完整, 遗漏的gid)"""
    classified_gids = extract_classified_gids(cluster_items)
    missing_gids = input_gids - classified_gids
    if not missing_gids:
        PrettyOutput.auto_print(
            f"[jarvis-sec] 聚类完整性校验通过，所有gid已分类（共尝试 {attempt} 次）",
        )
        return True, set()
    else:
        missing_gids_list = sorted(list(missing_gids))
        missing_count = len(missing_gids)
        PrettyOutput.auto_print(
            f"[jarvis-sec] 聚类完整性校验失败：遗漏的gid: {missing_gids_list}（{missing_count}个），重试第 {attempt} 次（使用直接模型调用）",
        )
        return False, missing_gids


def run_cluster_agent_with_retry(
    cluster_agent: Any,
    cluster_task: str,
    cluster_summary_prompt: str,
    input_gids: set[int],
    file: str,
    _cluster_summary: Dict[str, str],
    create_agent_func: Optional[Any] = None,
) -> tuple[Optional[List[Dict[str, Any]]], Optional[str], bool]:
    """
    运行聚类Agent并永久重试直到所有gid都被分类，返回(聚类结果, 解析错误, 是否需要重新创建agent)
    如果需要重新创建agent，返回的第三个值为True
    """
    _attempt = 0
    use_direct_model = False
    error_details: List[str] = []
    missing_gids: set[int] = set()
    consecutive_failures = 0  # 连续失败次数

    while True:
        _attempt += 1
        _cluster_summary["text"] = ""

        if use_direct_model:
            run_cluster_agent_direct_model(
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

        cluster_summary_text = _cluster_summary.get("text", "")
        # 调试：如果解析失败，输出摘要文本的前500个字符用于调试
        cluster_items, parse_error = parse_clusters_from_text(cluster_summary_text)

        # 如果解析失败且是第一次尝试，输出调试信息
        if parse_error and _attempt == 1:
            preview = cluster_summary_text[:500] if cluster_summary_text else "(空)"
            try:
                PrettyOutput.auto_print(
                    f"[jarvis-sec] 调试：摘要文本预览（前500字符）: {preview}",
                )
            except Exception:
                pass

        # 校验结构
        valid, error_details = validate_cluster_result(
            cluster_items, parse_error, _attempt
        )

        # 完整性校验：检查所有输入的gid是否都被分类
        missing_gids = set[int]()
        if valid and cluster_items:
            is_complete, missing_gids = check_cluster_completeness(
                cluster_items, input_gids, _attempt
            )
            if is_complete:
                return cluster_items, None, False
            else:
                use_direct_model = True
                valid = False
                consecutive_failures += 1
        else:
            consecutive_failures += 1

        # 如果连续失败5次，且提供了创建agent的函数，则返回需要重新创建agent的标志
        if not valid and consecutive_failures >= 5 and create_agent_func is not None:
            try:
                PrettyOutput.auto_print(
                    f"[jarvis-sec] 连续失败 {consecutive_failures} 次，需要重新创建agent",
                )
            except Exception:
                pass
            return None, parse_error or "连续失败5次", True

        if not valid:
            use_direct_model = True
            cluster_items = None


def process_cluster_results(
    cluster_items: List[Dict[str, Any]],
    pending_in_file_with_ids: List[Dict[str, Any]],
    file: str,
    chunk_idx: int,
    cluster_batches: List[List[Dict[str, Any]]],
    cluster_records: List[Dict[str, Any]],
    invalid_clusters_for_review: List[Dict[str, Any]],
    _progress_append: Any,
) -> tuple[int, int]:
    """处理聚类结果，返回(有效聚类数, 无效聚类数)"""
    gid_to_item: Dict[int, Dict[str, Any]] = {}
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
    classified_gids_final = set[int]()

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

        members: List[Dict[str, Any]] = []
        for k in norm_keys:
            item = gid_to_item.get(k)
            if item is not None:
                item["verify"] = verification
                members.append(item)

        # 如果标记为无效，收集到复核列表
        if is_invalid:
            _invalid_count += 1
            invalid_gids = [m.get("gid") for m in members]
            invalid_reason = str(cl.get("invalid_reason", "")).strip()
            try:
                PrettyOutput.auto_print(
                    f"[jarvis-sec] 聚类阶段判定为无效（gids={invalid_gids}），将提交复核Agent验证",
                )
            except Exception:
                pass
            invalid_clusters_for_review.append(
                {
                    "file": file,
                    "batch_index": chunk_idx,
                    "gids": invalid_gids,
                    "verification": verification,
                    "invalid_reason": invalid_reason,
                    "members": members,
                    "count": len(members),
                }
            )
            _progress_append(
                {
                    "event": "cluster_invalid",
                    "file": file,
                    "batch_index": chunk_idx,
                    "gids": invalid_gids,
                    "verification": verification,
                    "count": len(members),
                }
            )
            cluster_records.append(
                {
                    "file": file,
                    "verification": verification,
                    "gids": invalid_gids,
                    "count": len(members),
                    "batch_index": chunk_idx,
                    "is_invalid": True,
                    "invalid_reason": invalid_reason,
                }
            )
        elif members:
            _merged_count += 1
            cluster_batches.append(members)
            cluster_records.append(
                {
                    "file": file,
                    "verification": verification,
                    "gids": [m.get("gid") for m in members],
                    "count": len(members),
                    "batch_index": chunk_idx,
                    "is_invalid": False,
                }
            )

    return _merged_count, _invalid_count


def supplement_missing_gids(
    missing_gids_final: set[int],
    gid_to_item: Dict[int, Dict[str, Any]],
    file: str,
    chunk_idx: int,
    cluster_batches: List[List[Dict[str, Any]]],
    cluster_records: List[Dict[str, Any]],
) -> int:
    """为遗漏的gid创建单独聚类，返回补充的聚类数"""
    supplemented_count = 0
    for missing_gid in sorted(missing_gids_final):
        missing_item = gid_to_item.get(missing_gid)
        if missing_item:
            default_verification = f"验证候选 {missing_gid} 的安全风险"
            missing_item["verify"] = default_verification
            cluster_batches.append([missing_item])
            cluster_records.append(
                {
                    "file": file,
                    "verification": default_verification,
                    "gids": [missing_gid],
                    "count": 1,
                    "batch_index": chunk_idx,
                    "note": "完整性校验补充的遗漏gid",
                }
            )
            supplemented_count += 1
    return supplemented_count


def build_cluster_task(
    pending_in_file_with_ids: List[Dict[str, Any]],
    entry_path: str,
    file: str,
    langs: List[str],
) -> str:
    """构建聚类任务上下文"""
    return f"""
# 聚类任务（分析输入）
上下文：
- entry_path: {entry_path}
- file: {file}
- languages: {langs}

候选(JSON数组，包含 gid/file/line/pattern/category/evidence)：
{json.dumps(pending_in_file_with_ids, ensure_ascii=False, indent=2)}
        """.strip()


def extract_input_gids(pending_in_file_with_ids: List[Dict[str, Any]]) -> set[int]:
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


def build_gid_to_item_mapping(
    pending_in_file_with_ids: List[Dict[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    """构建gid到项的映射"""
    gid_to_item: Dict[int, Dict[str, Any]] = {}
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


def process_cluster_chunk(
    chunk: List[Dict[str, Any]],
    chunk_idx: int,
    file: str,
    entry_path: str,
    langs: List[str],
    llm_group: Optional[str],
    cluster_batches: List[List[Dict[str, Any]]],
    cluster_records: List[Dict[str, Any]],
    invalid_clusters_for_review: List[Dict[str, Any]],
    _progress_append: Any,
    _write_cluster_batch_snapshot: Any,
    force_save_memory: bool = False,
) -> None:
    """处理单个聚类批次"""
    if not chunk:
        return

    pending_in_file_with_ids = list(chunk)

    # 记录聚类批次开始
    _progress_append(
        {
            "event": "cluster_status",
            "status": "running",
            "file": file,
            "batch_index": chunk_idx,
            "total_in_batch": len(pending_in_file_with_ids),
        }
    )

    # 创建聚类Agent
    cluster_agent = create_cluster_agent(
        file, chunk_idx, llm_group, force_save_memory=force_save_memory
    )

    # 构建任务上下文
    cluster_task = build_cluster_task(pending_in_file_with_ids, entry_path, file, langs)

    # 提取输入gid
    input_gids = extract_input_gids(pending_in_file_with_ids)

    # 运行聚类Agent（支持重新创建agent，不限次数）
    cluster_summary_prompt = get_cluster_summary_prompt()
    recreate_count = 0

    while True:
        # 订阅摘要事件（每次重新创建agent后需要重新订阅）
        cluster_summary = subscribe_summary_event(cluster_agent)

        cluster_items, parse_error, need_recreate = run_cluster_agent_with_retry(
            cluster_agent,
            cluster_task,
            cluster_summary_prompt,
            input_gids,
            file,
            cluster_summary,
            create_agent_func=lambda: create_cluster_agent(
                file, chunk_idx, llm_group, force_save_memory=force_save_memory
            ),
        )

        # 如果不需要重新创建agent，退出循环
        if not need_recreate:
            break

        # 需要重新创建agent（不限次数）
        recreate_count += 1
        try:
            PrettyOutput.auto_print(
                f"[jarvis-sec] 重新创建聚类Agent（第 {recreate_count} 次）",
            )
        except Exception:
            pass
        cluster_agent = create_cluster_agent(
            file, chunk_idx, llm_group, force_save_memory=force_save_memory
        )

    # 处理聚类结果
    _merged_count = 0
    _invalid_count = 0

    if isinstance(cluster_items, list) and cluster_items:
        gid_to_item = build_gid_to_item_mapping(pending_in_file_with_ids)

        _merged_count, _invalid_count = process_cluster_results(
            cluster_items,
            pending_in_file_with_ids,
            file,
            chunk_idx,
            cluster_batches,
            cluster_records,
            invalid_clusters_for_review,
            _progress_append,
        )

        classified_gids_final = extract_classified_gids(cluster_items)
        missing_gids_final = input_gids - classified_gids_final
        if missing_gids_final:
            PrettyOutput.auto_print(
                f"[jarvis-sec] 警告：仍有遗漏的gid {sorted(list(missing_gids_final))}，将为每个遗漏的gid创建单独聚类",
            )
            supplemented_count = supplement_missing_gids(
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
            PrettyOutput.auto_print(
                f"[jarvis-sec] 警告：聚类结果为空或None（文件={file}，批次={chunk_idx}），为所有gid创建单独聚类",
            )
            gid_to_item_fallback = build_gid_to_item_mapping(pending_in_file_with_ids)

            _merged_count = supplement_missing_gids(
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
    _progress_append(
        {
            "event": "cluster_status",
            "status": "done",
            "file": file,
            "batch_index": chunk_idx,
            "clusters_count": _merged_count,
            "invalid_clusters_count": _invalid_count,
        }
    )
    if _invalid_count > 0:
        try:
            PrettyOutput.auto_print(
                f"[jarvis-sec] 聚类批次完成: 有效聚类={_merged_count}，无效聚类={_invalid_count}（已跳过）",
            )
        except Exception:
            pass

    # 写入当前批次的聚类结果
    current_batch_records = [
        rec
        for rec in cluster_records
        if rec.get("file") == file and rec.get("batch_index") == chunk_idx
    ]
    if current_batch_records:
        _write_cluster_batch_snapshot(current_batch_records)


def filter_pending_items(
    items: List[Dict[str, Any]], clustered_gids: set[int]
) -> List[Dict[str, Any]]:
    """过滤出待聚类的项"""
    pending_in_file: List[Dict[str, Any]] = []
    for c in items:
        try:
            _gid = int(c.get("gid", 0))
            if _gid >= 1 and _gid not in clustered_gids:
                pending_in_file.append(c)
        except Exception:
            pass
    return pending_in_file


def process_file_clustering(
    file: str,
    items: List[Dict[str, Any]],
    clustered_gids: set[int],
    cluster_batches: List[List[Dict[str, Any]]],
    cluster_records: List[Dict[str, Any]],
    invalid_clusters_for_review: List[Dict[str, Any]],
    entry_path: str,
    langs: List[str],
    cluster_limit: int,
    llm_group: Optional[str],
    _progress_append: Any,
    _write_cluster_batch_snapshot: Any,
    force_save_memory: bool = False,
) -> None:
    """处理单个文件的聚类任务"""
    # 过滤掉已聚类的 gid
    pending_in_file = filter_pending_items(items, clustered_gids)
    if not pending_in_file:
        return

    # 优化：如果文件只有一个告警，跳过聚类，直接写入
    if len(pending_in_file) == 1:
        single_item = pending_in_file[0]
        single_gid = single_item.get("gid", 0)
        handle_single_alert_file(
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
    _limit = (
        cluster_limit if isinstance(cluster_limit, int) and cluster_limit > 0 else 50
    )
    _chunks: List[List[Dict[str, Any]]] = [
        pending_in_file[i : i + _limit] for i in range(0, len(pending_in_file), _limit)
    ]

    # 处理每个批次
    for _chunk_idx, _chunk in enumerate(_chunks, start=1):
        process_cluster_chunk(
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


# 注意：check_and_supplement_missing_gids函数已移除
# 由于gid现在保存在heuristic_issues.jsonl中，恢复逻辑已经能够正确匹配所有gid
# 理论上不应该再出现遗漏的gid，完整性检查已移至process_clustering_phase中


def initialize_clustering_context(
    compact_candidates: List[Dict[str, Any]],
    sec_dir: Path,
    _progress_append: Any,
) -> tuple[
    Dict[str, List[Dict[str, Any]]],
    Dict[tuple[str, int], List[Dict[str, Any]]],
    tuple[Any, Any],
    List[List[Dict[str, Any]]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    set[int],
]:
    """初始化聚类上下文，返回(文件分组, 已有聚类, 快照写入函数, 聚类批次, 聚类记录, 无效聚类, 已聚类gid)"""
    # 按文件分组构建待聚类集合
    _file_groups = group_candidates_by_file(compact_candidates)

    cluster_batches: List[List[Dict[str, Any]]] = []
    cluster_records: List[Dict[str, Any]] = []
    invalid_clusters_for_review: List[Dict[str, Any]] = []

    # 读取已有聚类报告以支持断点
    (
        _existing_clusters,
        _completed_cluster_batches,
        _reviewed_invalid_gids,
    ) = load_existing_clusters(sec_dir)

    # 创建快照写入函数
    (
        _write_cluster_batch_snapshot,
        _write_cluster_report_snapshot,
    ) = create_cluster_snapshot_writer(
        sec_dir, cluster_records, compact_candidates, _progress_append
    )

    # 从断点恢复聚类结果
    (
        cluster_batches,
        cluster_records,
        invalid_clusters_for_review,
        clustered_gids,
    ) = restore_clusters_from_checkpoint(
        _existing_clusters, _file_groups, _reviewed_invalid_gids
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


def check_unclustered_gids(
    all_candidate_gids: set[int],
    clustered_gids: set[int],
) -> set[int]:
    """检查未聚类的gid"""
    unclustered_gids = all_candidate_gids - clustered_gids
    if unclustered_gids:
        try:
            PrettyOutput.auto_print(
                f"[jarvis-sec] 发现 {len(unclustered_gids)} 个未聚类的 gid，将进行聚类",
            )
        except Exception:
            pass
    else:
        try:
            PrettyOutput.auto_print(
                f"[jarvis-sec] 所有 {len(all_candidate_gids)} 个候选已聚类，跳过聚类阶段",
            )
        except Exception:
            pass
    return unclustered_gids


def execute_clustering_for_files(
    file_groups: Dict[str, List[Dict[str, Any]]],
    clustered_gids: set[int],
    cluster_batches: List[List[Dict[str, Any]]],
    cluster_records: List[Dict[str, Any]],
    invalid_clusters_for_review: List[Dict[str, Any]],
    entry_path: str,
    langs: List[str],
    cluster_limit: int,
    llm_group: Optional[str],
    status_mgr: Any,
    _progress_append: Any,
    _write_cluster_batch_snapshot: Any,
    force_save_memory: bool = False,
) -> None:
    """执行文件聚类"""
    total_files_to_cluster = len(file_groups)
    # 更新聚类阶段状态
    if total_files_to_cluster > 0:
        status_mgr.update_clustering(
            current_file=0,
            total_files=total_files_to_cluster,
            message="开始聚类分析...",
        )
    for _file_idx, (_file, _items) in enumerate(file_groups.items(), start=1):
        PrettyOutput.auto_print(
            f"\n[jarvis-sec] 聚类文件 {_file_idx}/{total_files_to_cluster}: {_file}",
        )
        # 更新当前文件进度
        status_mgr.update_clustering(
            current_file=_file_idx,
            total_files=total_files_to_cluster,
            file_name=_file,
            message=f"正在聚类文件 {_file_idx}/{total_files_to_cluster}: {_file}",
        )
        # 使用子函数处理文件聚类
        process_file_clustering(
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


def record_clustering_completion(
    sec_dir: Path,
    cluster_records: List[Dict[str, Any]],
    compact_candidates: List[Dict[str, Any]],
    _progress_append: Any,
) -> None:
    """记录聚类阶段完成"""
    try:
        _cluster_path = sec_dir / "cluster_report.jsonl"
        _progress_append(
            {
                "event": "cluster_report_written",
                "path": str(_cluster_path),
                "clusters": len(cluster_records),
                "total_candidates": len(compact_candidates),
                "note": "每个批次已增量保存，无需重写整个文件",
            }
        )
    except Exception:
        pass


def fallback_to_file_based_batches(
    file_groups: Dict[str, List[Dict[str, Any]]],
    existing_clusters: Dict[tuple[str, int], List[Dict[str, Any]]],
) -> List[List[Dict[str, Any]]]:
    """若聚类失败或空，则回退为按文件一次处理"""
    fallback_batches: List[List[Dict[str, Any]]] = []

    # 收集所有未聚类的 gid（从所有候选 gid 中排除已聚类的）
    all_gids_in_file_groups = collect_candidate_gids(file_groups)
    gid_to_item_fallback: Dict[int, Dict[str, Any]] = {}
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

            unclustered_by_file: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
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


def process_clustering_phase(
    compact_candidates: List[Dict[str, Any]],
    entry_path: str,
    langs: List[str],
    cluster_limit: int,
    llm_group: Optional[str],
    sec_dir: Path,
    status_mgr: Any,
    _progress_append: Any,
    force_save_memory: bool = False,
) -> tuple[List[List[Dict[str, Any]]], List[Dict[str, Any]]]:
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
    ) = initialize_clustering_context(compact_candidates, sec_dir, _progress_append)

    # 收集所有候选的 gid（用于检查未聚类的 gid）
    all_candidate_gids_in_clustering = collect_candidate_gids(_file_groups)

    # 检查是否有未聚类的 gid
    unclustered_gids = check_unclustered_gids(
        all_candidate_gids_in_clustering, clustered_gids
    )

    # 如果有未聚类的 gid，继续执行聚类
    if unclustered_gids:
        execute_clustering_for_files(
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
    record_clustering_completion(
        sec_dir, cluster_records, compact_candidates, _progress_append
    )

    # 复核Agent：验证所有标记为无效的聚类（需要从review模块导入）
    from jarvis.jarvis_sec.review import process_review_phase

    cluster_batches = process_review_phase(
        invalid_clusters_for_review,
        entry_path,
        langs,
        llm_group,
        status_mgr,
        _progress_append,
        cluster_batches,
        sec_dir,
    )

    # 若聚类失败或空，则回退为"按文件一次处理"
    if not cluster_batches:
        fallback_batches = fallback_to_file_based_batches(
            _file_groups, _existing_clusters
        )
        cluster_batches.extend(fallback_batches)

    # 完整性检查：确保所有候选的 gid 都已被聚类
    # 使用新的文件管理器进行校验
    is_complete, missing_gids_final = validate_clustering_completeness(sec_dir)

    if missing_gids_final:
        # 如果还有遗漏的gid，说明恢复逻辑有问题，需要重新聚类
        try:
            missing_count = len(missing_gids_final)
            if missing_count <= 20:
                PrettyOutput.auto_print(
                    f"[jarvis-sec] 警告：发现 {missing_count} 个遗漏的gid（恢复逻辑可能有问题）: {sorted(list(missing_gids_final))}",
                )
            else:
                missing_list = sorted(list(missing_gids_final))
                display_list = missing_list[:10] + ["..."] + missing_list[-10:]
                PrettyOutput.auto_print(
                    f"[jarvis-sec] 警告：发现 {missing_count} 个遗漏的gid（恢复逻辑可能有问题）: {display_list}",
                )

        except Exception:
            pass

    # 清理之前创建的单独聚类（避免分析工作量激增）
    cluster_batches = filter_single_gid_clusters(
        cluster_batches,
        sec_dir,
        _progress_append,
    )

    return cluster_batches, invalid_clusters_for_review
