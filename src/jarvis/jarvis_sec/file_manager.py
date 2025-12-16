# -*- coding: utf-8 -*-
"""
状态文件管理模块

重构后的3个配置文件：
1. candidates.jsonl - 只扫结果文件：保存每个原始告警的信息，包括gid
2. clusters.jsonl - 聚类信息文件：所有聚类（包括无效聚类），每个聚类包括的gids
3. analysis.jsonl - 分析结果文件：包括所有聚类，聚类中哪些问题是问题，哪些问题是误报
"""

import json
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Set
from typing import Tuple

from jarvis.jarvis_utils.output import PrettyOutput

# ==================== 文件路径定义 ====================


def get_candidates_file(sec_dir: Path) -> Path:
    """获取只扫结果文件路径"""
    return sec_dir / "candidates.jsonl"


def get_clusters_file(sec_dir: Path) -> Path:
    """获取聚类信息文件路径"""
    return sec_dir / "clusters.jsonl"


def get_analysis_file(sec_dir: Path) -> Path:
    """获取分析结果文件路径"""
    return sec_dir / "analysis.jsonl"


# ==================== 只扫结果文件 (candidates.jsonl) ====================


def save_candidates(sec_dir: Path, candidates: List[Dict[str, Any]]) -> None:
    """
    保存只扫结果到 candidates.jsonl

    格式：每行一个候选，包含所有原始信息 + gid
    {
        "gid": 1,
        "language": "c",
        "category": "buffer_overflow",
        "pattern": "strcpy",
        "file": "src/main.c",
        "line": 42,
        "evidence": "...",
        "confidence": 0.8,
        "severity": "high"
    }
    """
    path = get_candidates_file(sec_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    # 覆盖模式，确保文件内容是最新的
    with path.open("w", encoding="utf-8") as f:
        for candidate in candidates:
            f.write(json.dumps(candidate, ensure_ascii=False) + "\n")

    try:
        PrettyOutput.auto_print(
            f"✅ [jarvis-sec] 已保存 {len(candidates)} 个候选到 {path}"
        )
    except Exception:
        pass


def load_candidates(sec_dir: Path) -> List[Dict[str, Any]]:
    """
    从 candidates.jsonl 加载只扫结果

    返回: 候选列表，每个候选包含gid
    """
    path = get_candidates_file(sec_dir)
    candidates = []

    if path.exists():
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        candidate = json.loads(line)
                        candidates.append(candidate)
                    except Exception:
                        pass
        except Exception as e:
            try:
                PrettyOutput.auto_print(
                    f"⚠️ [jarvis-sec] 警告：加载 candidates.jsonl 失败: {e}"
                )
            except Exception:
                pass

    return candidates


def get_all_candidate_gids(sec_dir: Path) -> Set[int]:
    """获取所有候选的gid集合"""
    candidates = load_candidates(sec_dir)
    gids = set()
    for candidate in candidates:
        try:
            gid = int(candidate.get("gid", 0))
            if gid >= 1:
                gids.add(gid)
        except Exception:
            pass
    return gids


# ==================== 聚类信息文件 (clusters.jsonl) ====================


def save_cluster(sec_dir: Path, cluster: Dict[str, Any]) -> None:
    """
    保存单个聚类到 clusters.jsonl（追加模式）

    格式：每行一个聚类记录
    {
        "cluster_id": "file_path|batch_index|index",  # 唯一标识
        "file": "src/main.c",
        "batch_index": 1,
        "cluster_index": 0,  # 同一批次中的聚类索引
        "gids": [1, 2, 3],  # 该聚类包含的gid列表
        "verification": "验证候选的安全风险",  # 聚类验证描述
        "is_invalid": false,  # 是否为无效聚类
        "invalid_reason": "",  # 无效原因（如果is_invalid为true）
        "created_at": "2024-01-01T00:00:00"  # 创建时间（可选）
    }
    """
    path = get_clusters_file(sec_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    # 追加模式
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(cluster, ensure_ascii=False) + "\n")


def load_clusters(sec_dir: Path) -> List[Dict[str, Any]]:
    """
    从 clusters.jsonl 加载所有聚类

    返回: 聚类列表
    """
    path = get_clusters_file(sec_dir)
    clusters = []

    if path.exists():
        try:
            # 使用字典合并：key 为 cluster_id，合并同一个 cluster_id 的所有记录的 gid
            seen_clusters: Dict[str, Dict[str, Any]] = {}
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        cluster = json.loads(line)
                        cluster_id = cluster.get("cluster_id", "")
                        if cluster_id:
                            if cluster_id in seen_clusters:
                                # 如果已存在，合并 gid 列表（去重）
                                existing_gids = set(
                                    seen_clusters[cluster_id].get("gids", [])
                                )
                                new_gids = set(cluster.get("gids", []))
                                merged_gids = sorted(list(existing_gids | new_gids))
                                seen_clusters[cluster_id]["gids"] = merged_gids
                                # 保留最新的其他字段（verification, is_invalid 等）
                                seen_clusters[cluster_id].update(
                                    {
                                        k: v
                                        for k, v in cluster.items()
                                        if k != "gids" and k != "cluster_id"
                                    }
                                )
                            else:
                                # 第一次遇到这个 cluster_id，直接保存
                                seen_clusters[cluster_id] = cluster
                    except Exception:
                        pass

            clusters = list(seen_clusters.values())
        except Exception as e:
            try:
                PrettyOutput.auto_print(
                    f"⚠️ [jarvis-sec] 警告：加载 clusters.jsonl 失败: {e}"
                )
            except Exception:
                pass

    return clusters


def get_all_clustered_gids(sec_dir: Path) -> Set[int]:
    """获取所有已聚类的gid集合"""
    clusters = load_clusters(sec_dir)
    gids = set()
    for cluster in clusters:
        gids_list = cluster.get("gids", [])
        if isinstance(gids_list, list):
            for gid_val in gids_list:
                try:
                    gid_int = int(gid_val)
                    if gid_int >= 1:
                        gids.add(gid_int)
                except Exception:
                    pass
    return gids


def validate_clustering_completeness(sec_dir: Path) -> Tuple[bool, Set[int]]:
    """
    校验聚类完整性，确保所有候选的gid都被聚类

    返回: (is_complete, missing_gids)
    """
    all_candidate_gids = get_all_candidate_gids(sec_dir)
    all_clustered_gids = get_all_clustered_gids(sec_dir)
    missing_gids = all_candidate_gids - all_clustered_gids

    return len(missing_gids) == 0, missing_gids


# ==================== 分析结果文件 (analysis.jsonl) ====================


def save_analysis_result(sec_dir: Path, analysis: Dict[str, Any]) -> None:
    """
    保存单个分析结果到 analysis.jsonl（追加模式）

    格式：每行一个分析结果记录
    {
        "cluster_id": "file_path|batch_index|index",  # 对应的聚类ID
        "file": "src/main.c",
        "batch_index": 1,
        "cluster_index": 0,
        "gids": [1, 2, 3],  # 该聚类包含的所有gid
        "verified_gids": [1, 2],  # 验证为问题的gid（has_risk: true）
        "false_positive_gids": [3],  # 验证为误报的gid（has_risk: false）
        "issues": [  # 详细的问题列表（仅verified_gids对应的）
            {
                "gid": 1,
                "has_risk": true,
                "verification_notes": "...",
                "severity": "high",
                ...
            },
            ...
        ],
        "analyzed_at": "2024-01-01T00:00:00"  # 分析时间（可选）
    }
    """
    path = get_analysis_file(sec_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    # 追加模式
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(analysis, ensure_ascii=False) + "\n")


def load_analysis_results(sec_dir: Path) -> List[Dict[str, Any]]:
    """
    从 analysis.jsonl 加载所有分析结果

    返回: 分析结果列表
    """
    path = get_analysis_file(sec_dir)
    results = []

    if path.exists():
        try:
            # 使用字典合并：key 为 cluster_id，合并同一个 cluster_id 的所有记录
            seen_results: Dict[str, Dict[str, Any]] = {}
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        result = json.loads(line)
                        cluster_id = result.get("cluster_id", "")
                        if cluster_id:
                            if cluster_id in seen_results:
                                # 如果已存在，合并 gid、verified_gids、false_positive_gids 和 issues
                                existing = seen_results[cluster_id]

                                # 合并 gids（去重）
                                existing_gids = set(existing.get("gids", []))
                                new_gids = set(result.get("gids", []))
                                existing["gids"] = sorted(
                                    list(existing_gids | new_gids)
                                )

                                # 合并 verified_gids（去重）
                                existing_verified = set(
                                    existing.get("verified_gids", [])
                                )
                                new_verified = set(result.get("verified_gids", []))
                                existing["verified_gids"] = sorted(
                                    list(existing_verified | new_verified)
                                )

                                # 合并 false_positive_gids（去重）
                                existing_false = set(
                                    existing.get("false_positive_gids", [])
                                )
                                new_false = set(result.get("false_positive_gids", []))
                                existing["false_positive_gids"] = sorted(
                                    list(existing_false | new_false)
                                )

                                # 合并 issues（通过 gid 去重）
                                existing_issues = {
                                    issue.get("gid"): issue
                                    for issue in existing.get("issues", [])
                                }
                                for issue in result.get("issues", []):
                                    gid = issue.get("gid")
                                    if gid:
                                        existing_issues[gid] = issue  # 保留最新的 issue
                                existing["issues"] = list(existing_issues.values())

                                # 保留最新的其他字段
                                existing.update(
                                    {
                                        k: v
                                        for k, v in result.items()
                                        if k
                                        not in [
                                            "gids",
                                            "verified_gids",
                                            "false_positive_gids",
                                            "issues",
                                            "cluster_id",
                                        ]
                                    }
                                )
                            else:
                                # 第一次遇到这个 cluster_id，直接保存
                                seen_results[cluster_id] = result
                    except Exception:
                        pass

            results = list(seen_results.values())
        except Exception as e:
            try:
                PrettyOutput.auto_print(
                    f"⚠️ [jarvis-sec] 警告：加载 analysis.jsonl 失败: {e}"
                )
            except Exception:
                pass

    return results


def get_all_analyzed_gids(sec_dir: Path) -> Set[int]:
    """获取所有已分析的gid集合（包括问题和误报）"""
    results = load_analysis_results(sec_dir)
    gids = set()
    for result in results:
        gids_list = result.get("gids", [])
        if isinstance(gids_list, list):
            for gid_val in gids_list:
                try:
                    gid_int = int(gid_val)
                    if gid_int >= 1:
                        gids.add(gid_int)
                except Exception:
                    pass
    return gids


def get_verified_issue_gids(sec_dir: Path) -> Set[int]:
    """获取所有验证为问题的gid集合"""
    results = load_analysis_results(sec_dir)
    gids = set()
    for result in results:
        verified_gids = result.get("verified_gids", [])
        if isinstance(verified_gids, list):
            for gid_val in verified_gids:
                try:
                    gid_int = int(gid_val)
                    if gid_int >= 1:
                        gids.add(gid_int)
                except Exception:
                    pass
    return gids


def get_false_positive_gids(sec_dir: Path) -> Set[int]:
    """获取所有验证为误报的gid集合"""
    results = load_analysis_results(sec_dir)
    gids = set()
    for result in results:
        false_positive_gids = result.get("false_positive_gids", [])
        if isinstance(false_positive_gids, list):
            for gid_val in false_positive_gids:
                try:
                    gid_int = int(gid_val)
                    if gid_int >= 1:
                        gids.add(gid_int)
                except Exception:
                    pass
    return gids


# ==================== 断点恢复状态检查 ====================


def get_resume_status(sec_dir: Path) -> Dict[str, Any]:
    """
    根据3个配置文件的存在性和状态，推断断点恢复状态

    返回: {
        "has_candidates": bool,  # 是否有只扫结果
        "has_clusters": bool,  # 是否有聚类结果
        "has_analysis": bool,  # 是否有分析结果
        "candidates_count": int,  # 候选数量
        "clusters_count": int,  # 聚类数量
        "analysis_count": int,  # 分析结果数量
        "clustering_complete": bool,  # 聚类是否完整
        "missing_gids": Set[int],  # 遗漏的gid（如果聚类不完整）
    }
    """
    status = {
        "has_candidates": False,
        "has_clusters": False,
        "has_analysis": False,
        "candidates_count": 0,
        "clusters_count": 0,
        "analysis_count": 0,
        "clustering_complete": False,
        "missing_gids": set(),
    }

    # 检查只扫结果
    candidates = load_candidates(sec_dir)
    if candidates:
        status["has_candidates"] = True
        status["candidates_count"] = len(candidates)

    # 检查聚类结果
    clusters = load_clusters(sec_dir)
    if clusters:
        status["has_clusters"] = True
        status["clusters_count"] = len(clusters)

    # 检查分析结果
    results = load_analysis_results(sec_dir)
    if results:
        status["has_analysis"] = True
        status["analysis_count"] = len(results)

    # 校验聚类完整性
    if status["has_candidates"]:
        is_complete, missing_gids = validate_clustering_completeness(sec_dir)
        status["clustering_complete"] = is_complete
        status["missing_gids"] = missing_gids

    return status
