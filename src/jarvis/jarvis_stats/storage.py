"""
统计数据存储模块

负责统计数据的持久化存储和读取
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict
import sys
import time
import uuid


class StatsStorage:
    """统计数据存储类"""

    def __init__(self, storage_dir: Optional[str] = None):
        """
        初始化存储

        Args:
            storage_dir: 存储目录路径，默认为 ~/.jarvis/stats
        """
        if storage_dir is None:
            storage_dir = os.path.expanduser("~/.jarvis/stats")

        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 数据目录路径
        self.data_dir = self.storage_dir / "data"
        self.data_dir.mkdir(exist_ok=True)

        # 统计总量缓存目录（每个指标一个文件，内容为统计总量）
        self.totals_dir = self.storage_dir / "totals"
        self.totals_dir.mkdir(exist_ok=True)

        # 元数据文件路径
        self.meta_file = self.storage_dir / "stats_meta.json"

        # 初始化元数据
        self._init_metadata()

    def _init_metadata(self):
        """初始化元数据"""
        if not self.meta_file.exists():
            meta = {
                "version": "1.0.0",
                "created_at": datetime.now().isoformat(),
                "metrics": {},  # 存储各个指标的元信息
            }
            self._save_json(self.meta_file, meta)

    def _get_data_file(self, date_str: str) -> Path:
        """获取指定日期的数据文件路径"""
        return self.data_dir / f"stats_{date_str}.json"

    def _load_json(self, filepath: Path) -> Dict:
        """加载JSON文件"""
        if not filepath.exists():
            return {}

        # 重试机制处理并发访问
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data
            except (json.JSONDecodeError, IOError):
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))  # 递增延迟
                    continue
                return {}
        return {}

    def _save_json(self, filepath: Path, data: Dict):
        """保存JSON文件"""
        # 使用临时文件+重命名的原子操作来避免并发写入问题
        # 使用唯一的临时文件名避免并发冲突
        temp_suffix = f".tmp.{uuid.uuid4().hex[:8]}"
        temp_filepath = filepath.with_suffix(temp_suffix)
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # 先写入临时文件
                with open(temp_filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                # Windows上需要先删除目标文件（如果存在）
                if sys.platform == "win32" and filepath.exists():
                    filepath.unlink()

                # 原子性重命名
                temp_filepath.rename(filepath)
                return

            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))  # 递增延迟
                    continue
                # 清理临时文件
                if temp_filepath.exists():
                    try:
                        temp_filepath.unlink()
                    except OSError:
                        pass
                raise RuntimeError(f"保存数据失败: {e}") from e

    def _save_text_atomic(self, filepath: Path, text: str):
        """原子性地保存纯文本内容"""
        temp_suffix = f".tmp.{uuid.uuid4().hex[:8]}"
        temp_filepath = filepath.with_suffix(temp_suffix)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(temp_filepath, "w", encoding="utf-8") as f:
                    f.write(text)

                if sys.platform == "win32" and filepath.exists():
                    filepath.unlink()
                temp_filepath.rename(filepath)
                return
            except Exception:
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                if temp_filepath.exists():
                    try:
                        temp_filepath.unlink()
                    except OSError:
                        pass
                raise

    def add_metric(
        self,
        metric_name: str,
        value: float,
        unit: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        tags: Optional[Dict[str, str]] = None,
    ):
        """
        添加统计数据

        Args:
            metric_name: 指标名称
            value: 指标值
            unit: 单位
            timestamp: 时间戳，默认为当前时间
            tags: 标签字典，用于数据分类
        """
        if timestamp is None:
            timestamp = datetime.now()

        # 更新元数据
        meta = self._load_json(self.meta_file)
        if metric_name not in meta["metrics"]:
            meta["metrics"][metric_name] = {
                "unit": unit,
                "created_at": timestamp.isoformat(),
                "last_updated": timestamp.isoformat(),
            }
        else:
            meta["metrics"][metric_name]["last_updated"] = timestamp.isoformat()
            if unit and not meta["metrics"][metric_name].get("unit"):
                meta["metrics"][metric_name]["unit"] = unit

        # 记录分组信息（如果提供）
        if tags and isinstance(tags, dict):
            group = tags.get("group")
            if group:
                meta["metrics"][metric_name]["group"] = group

        self._save_json(self.meta_file, meta)

        # 获取日期对应的数据文件
        date_key = timestamp.strftime("%Y-%m-%d")
        hour_key = timestamp.strftime("%H")
        date_file = self._get_data_file(date_key)

        # 加载日期文件的数据
        data = self._load_json(date_file)

        # 组织数据结构：metric_name -> hour -> records
        if metric_name not in data:
            data[metric_name] = {}

        if hour_key not in data[metric_name]:
            data[metric_name][hour_key] = []

        # 添加数据记录
        record = {
            "timestamp": timestamp.isoformat(),
            "value": value,
            "tags": tags or {},
        }
        data[metric_name][hour_key].append(record)

        # 保存数据到日期文件
        self._save_json(date_file, data)

        # 更新总量缓存文件（每个指标一个文件，内容为累计统计值）
        try:
            total_file = self._get_total_file(metric_name)
            if total_file.exists():
                # 正常累加
                try:
                    with open(total_file, "r", encoding="utf-8") as tf:
                        current_total = float(tf.read().strip() or "0")
                except Exception:
                    current_total = 0.0
                new_total = current_total + float(value)
                self._save_text_atomic(total_file, str(new_total))
            else:
                # 首次生成：扫描历史数据（包含刚写入的这条记录）并写入
                # 注意：get_metric_total 内部会完成扫描并写入 totals 文件，这里无需再额外写入或累加
                _ = self.get_metric_total(metric_name)
        except Exception:
            # 静默失败，不影响主流程
            pass

    def get_metrics(
        self,
        metric_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> List[Dict]:
        """
        获取指定时间范围的统计数据

        Args:
            metric_name: 指标名称
            start_time: 开始时间
            end_time: 结束时间
            tags: 过滤标签

        Returns:
            数据记录列表
        """
        # 默认时间范围
        if end_time is None:
            end_time = datetime.now()
        if start_time is None:
            start_time = end_time - timedelta(days=7)  # 默认最近7天

        results = []

        # 遍历日期
        current_date = start_time.date()
        end_date = end_time.date()

        while current_date <= end_date:
            date_key = current_date.strftime("%Y-%m-%d")
            date_file = self._get_data_file(date_key)

            # 如果日期文件不存在，跳过
            if not date_file.exists():
                current_date += timedelta(days=1)
                continue

            # 加载日期文件的数据
            data = self._load_json(date_file)

            if metric_name in data:
                for hour_key, records in data[metric_name].items():
                    for record in records:
                        record_time = datetime.fromisoformat(record["timestamp"])

                        # 检查时间范围
                        if start_time <= record_time <= end_time:
                            # 检查标签过滤
                            if tags:
                                record_tags = record.get("tags", {})
                                if all(
                                    record_tags.get(k) == v for k, v in tags.items()
                                ):
                                    results.append(record)
                            else:
                                results.append(record)

            current_date += timedelta(days=1)

        # 按时间排序
        results.sort(key=lambda x: x["timestamp"])

        return results

    def _get_total_file(self, metric_name: str) -> Path:
        """获取某个指标的总量文件路径"""
        return self.totals_dir / metric_name

    def get_metric_total(self, metric_name: str) -> float:
        """
        获取某个指标的累计总量。
        - 如果总量缓存文件存在，直接读取
        - 如果不存在，则扫描历史数据计算一次并写入缓存
        """
        total_file = self._get_total_file(metric_name)
        # 优先读取缓存
        if total_file.exists():
            try:
                with open(total_file, "r", encoding="utf-8") as f:
                    return float((f.read() or "0").strip() or "0")
            except Exception:
                # 读取失败则重建
                pass

        # 扫描历史数据进行一次性计算，并尽可能推断分组信息
        total = 0.0
        group_counts: Dict[str, int] = {}
        try:
            for data_file in self.data_dir.glob("stats_*.json"):
                data = self._load_json(data_file)
                metric_data = data.get(metric_name) or {}
                # metric_data: {hour_key: [records]}
                for hour_records in metric_data.values():
                    for record in hour_records:
                        # 累加数值
                        try:
                            total += float(record.get("value", 0))
                        except Exception:
                            pass
                        # 统计历史记录中的分组标签
                        try:
                            tags = record.get("tags", {})
                            grp = tags.get("group")
                            if grp:
                                group_counts[grp] = group_counts.get(grp, 0) + 1
                        except Exception:
                            pass

            # 写入缓存
            self._save_text_atomic(total_file, str(total))

            # 如果元数据中没有该指标或缺少分组，则根据历史数据推断一次
            try:
                meta = self._load_json(self.meta_file)
                if "metrics" not in meta or not isinstance(meta.get("metrics"), dict):
                    meta["metrics"] = {}
                info = meta["metrics"].get(metric_name)
                now_iso = datetime.now().isoformat()
                if info is None:
                    info = {
                        "unit": None,
                        "created_at": now_iso,
                        "last_updated": now_iso,
                    }
                    meta["metrics"][metric_name] = info
                if not info.get("group"):
                    inferred_group = None
                    if group_counts:
                        inferred_group = max(
                            group_counts.items(), key=lambda kv: kv[1]
                        )[0]
                    # 名称启发式作为补充
                    if not inferred_group:
                        if (
                            metric_name.startswith("code_lines_")
                            or "commit" in metric_name
                        ):
                            inferred_group = "code_agent"
                    if inferred_group:
                        info["group"] = inferred_group
                # 保存元数据
                self._save_json(self.meta_file, meta)
            except Exception:
                # 分组推断失败不影响总量结果
                pass

        except Exception:
            # 失败则返回0
            return 0.0
        return total

    def resolve_metric_group(self, metric_name: str) -> Optional[str]:
        """
        解析并确保写回某个指标的分组信息：
        - 若元数据已存在group则直接返回
        - 否则扫描历史记录中的tags['group']做多数投票推断
        - 若仍无法得到，则用名称启发式(code_lines_*或包含commit -> code_agent)
        - 推断出group后会写回到元数据，返回推断值；否则返回None
        """
        try:
            # 优先从元数据读取
            meta = self._load_json(self.meta_file)
            metrics_meta = (
                meta.get("metrics", {}) if isinstance(meta.get("metrics"), dict) else {}
            )
            info = metrics_meta.get(metric_name)
            if info and isinstance(info, dict):
                grp = info.get("group")
                if grp:
                    return grp

            # 扫描历史记录以推断
            group_counts: Dict[str, int] = {}
            for data_file in self.data_dir.glob("stats_*.json"):
                data = self._load_json(data_file)
                metric_data = data.get(metric_name) or {}
                for hour_records in metric_data.values():
                    for record in hour_records:
                        try:
                            tags = record.get("tags", {})
                            grp = tags.get("group")
                            if grp:
                                group_counts[grp] = group_counts.get(grp, 0) + 1
                        except Exception:
                            continue

            inferred_group: Optional[str] = None
            if group_counts:
                inferred_group = max(group_counts.items(), key=lambda kv: kv[1])[0]

            # 名称启发式补充
            if not inferred_group:
                name = metric_name or ""
                if name.startswith("code_lines_") or ("commit" in name):
                    inferred_group = "code_agent"

            # 如果推断出了分组，写回元数据
            if inferred_group:
                if not isinstance(metrics_meta, dict):
                    meta["metrics"] = {}
                    metrics_meta = meta["metrics"]
                if info is None:
                    now_iso = datetime.now().isoformat()
                    info = {
                        "unit": None,
                        "created_at": now_iso,
                        "last_updated": now_iso,
                    }
                    metrics_meta[metric_name] = info
                info["group"] = inferred_group
                self._save_json(self.meta_file, meta)
                return inferred_group

            return None
        except Exception:
            return None

    def get_metric_info(self, metric_name: str) -> Optional[Dict]:
        """获取指标元信息"""
        meta = self._load_json(self.meta_file)
        return meta.get("metrics", {}).get(metric_name)

    def list_metrics(self) -> List[str]:
        """列出所有指标"""
        # 从元数据文件获取指标
        meta = self._load_json(self.meta_file)
        metrics_from_meta = set(meta.get("metrics", {}).keys())

        # 扫描所有数据文件获取实际存在的指标
        metrics_from_data: set[str] = set()
        for data_file in self.data_dir.glob("stats_*.json"):
            try:
                data = self._load_json(data_file)
                metrics_from_data.update(data.keys())
            except (json.JSONDecodeError, OSError):
                # 忽略无法读取的文件
                continue

        # 扫描总量缓存目录中已有的指标文件
        metrics_from_totals: set[str] = set()
        try:
            for f in self.totals_dir.glob("*"):
                if f.is_file():
                    metrics_from_totals.add(f.name)
        except Exception:
            pass

        # 合并三个来源的指标并返回排序后的列表
        all_metrics = metrics_from_meta.union(metrics_from_data).union(
            metrics_from_totals
        )
        return sorted(list(all_metrics))

    def aggregate_metrics(
        self,
        metric_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        aggregation: str = "hourly",
        tags: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        聚合统计数据

        Args:
            metric_name: 指标名称
            start_time: 开始时间
            end_time: 结束时间
            aggregation: 聚合方式 (hourly, daily)
            tags: 过滤标签

        Returns:
            聚合后的数据字典
        """
        records = self.get_metrics(metric_name, start_time, end_time, tags)

        if not records:
            return {}

        # 聚合数据
        aggregated: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "count": 0,
                "sum": 0,
                "min": float("inf"),
                "max": float("-inf"),
                "values": [],
            }
        )

        for record in records:
            timestamp = datetime.fromisoformat(record["timestamp"])
            value = record["value"]

            if aggregation == "hourly":
                key = timestamp.strftime("%Y-%m-%d %H:00")
            elif aggregation == "daily":
                key = timestamp.strftime("%Y-%m-%d")
            else:
                key = timestamp.strftime("%Y-%m-%d %H:00")

            aggregated[key]["count"] += 1
            aggregated[key]["sum"] += value
            aggregated[key]["min"] = min(aggregated[key]["min"], value)
            aggregated[key]["max"] = max(aggregated[key]["max"], value)
            aggregated[key]["values"].append(value)

        # 计算平均值
        result = {}
        for key, stats in aggregated.items():
            result[key] = {
                "count": stats["count"],
                "sum": stats["sum"],
                "min": stats["min"],
                "max": stats["max"],
                "avg": stats["sum"] / stats["count"] if stats["count"] > 0 else 0,
            }

        return result

    def delete_metric(self, metric_name: str) -> bool:
        """
        删除指定的指标及其所有数据

        Args:
            metric_name: 要删除的指标名称

        Returns:
            True 如果成功删除，False 如果指标不存在
        """
        # 检查指标是否存在
        meta = self._load_json(self.meta_file)
        if metric_name not in meta.get("metrics", {}):
            return False

        # 从元数据中删除指标
        del meta["metrics"][metric_name]
        self._save_json(self.meta_file, meta)

        # 遍历所有数据文件，删除该指标的数据
        for data_file in self.data_dir.glob("stats_*.json"):
            try:
                data = self._load_json(data_file)
                if metric_name in data:
                    del data[metric_name]
                    # 如果文件中还有其他数据，保存更新后的文件
                    if data:
                        self._save_json(data_file, data)
                    # 如果文件变空了，删除文件
                    else:
                        data_file.unlink()
            except Exception:
                # 忽略单个文件的错误，继续处理其他文件
                pass

        # 删除总量缓存文件
        try:
            total_file = self._get_total_file(metric_name)
            if total_file.exists():
                total_file.unlink()
        except Exception:
            pass

        return True

    def delete_old_data(self, days_to_keep: int = 30):
        """删除旧数据"""
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).date()

        # 遍历数据目录中的所有文件
        for data_file in self.data_dir.glob("stats_*.json"):
            try:
                # 从文件名中提取日期
                date_str = data_file.stem.replace("stats_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()

                # 如果文件日期早于截止日期，删除文件
                if file_date < cutoff_date:
                    data_file.unlink()
            except (ValueError, OSError):
                # 忽略无法解析或删除的文件
                continue
