# -*- coding: utf-8 -*-
"""
进度状态管理模块

提供结构化的进度状态文件，准确反映当前所处的阶段和进度。
状态文件格式：JSON，包含当前阶段、进度百分比、已完成/总数等信息。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Optional
from typing import cast


class StatusManager:
    """进度状态管理器"""

    def __init__(self, entry_path: str):
        """
        初始化状态管理器

        Args:
            entry_path: 待分析的根目录路径（可以是项目根目录或 .jarvis/sec 目录）
        """
        self.entry_path = Path(entry_path)
        # 检查 entry_path 是否已经是 .jarvis/sec 目录
        if self.entry_path.name == "sec" and self.entry_path.parent.name == ".jarvis":
            sec_dir = self.entry_path
        else:
            sec_dir = self.entry_path / ".jarvis" / "sec"
        self.status_path = sec_dir / "status.json"
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """确保状态文件目录存在"""
        self.status_path.parent.mkdir(parents=True, exist_ok=True)

    def _read_status(self) -> Dict[str, Any]:
        """读取当前状态"""
        if not self.status_path.exists():
            return {}
        try:
            with self.status_path.open("r", encoding="utf-8") as f:
                return cast(Dict[str, Any], json.load(f))
        except Exception:
            return {}

    def _write_status(self, status: Dict[str, Any]) -> None:
        """写入状态文件"""
        try:
            status["last_updated"] = datetime.utcnow().isoformat() + "Z"
            with self.status_path.open("w", encoding="utf-8") as f:
                json.dump(status, f, ensure_ascii=False, indent=2)
        except Exception:
            # 状态文件写入失败不影响主流程
            pass

    def update_stage(
        self,
        stage: str,
        progress: Optional[float] = None,
        current: Optional[int] = None,
        total: Optional[int] = None,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        更新当前阶段和进度

        Args:
            stage: 阶段名称（pre_scan, clustering, verification, completed, error）
            progress: 进度百分比（0-100），如果为None则根据current/total计算
            current: 当前已完成数量
            total: 总数量
            message: 状态消息
            details: 额外的详细信息
        """
        status = self._read_status()

        # 计算进度百分比
        if progress is None and current is not None and total is not None and total > 0:
            progress = (current / total) * 100

        # 更新状态
        status["stage"] = stage
        if progress is not None:
            status["progress"] = round(progress, 2)
        if current is not None:
            status["current"] = current
        if total is not None:
            status["total"] = total
        if message:
            status["message"] = message
        if details:
            status["details"] = details

        # 设置阶段开始时间（如果是新阶段）
        if "stage_history" not in status:
            status["stage_history"] = []

        # 检查是否是阶段切换
        last_stage = status.get("stage")
        if last_stage != stage:
            status["stage_history"].append(
                {"stage": stage, "started_at": datetime.utcnow().isoformat() + "Z"}
            )

        self._write_status(status)

    def update_pre_scan(
        self,
        current_files: Optional[int] = None,
        total_files: Optional[int] = None,
        issues_found: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        """更新启发式扫描阶段状态"""
        details = {}
        if issues_found is not None:
            details["issues_found"] = issues_found

        progress = None
        if current_files is not None and total_files is not None and total_files > 0:
            progress = (current_files / total_files) * 100

        self.update_stage(
            stage="pre_scan",
            progress=progress,
            current=current_files,
            total=total_files,
            message=message or "正在进行启发式扫描...",
            details=details,
        )

    def update_clustering(
        self,
        current_file: Optional[int] = None,
        total_files: Optional[int] = None,
        current_batch: Optional[int] = None,
        total_batches: Optional[int] = None,
        file_name: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        """更新聚类阶段状态"""
        details: Dict[str, Any] = {}
        if file_name:
            details["current_file"] = file_name
        if current_batch is not None:
            details["current_batch"] = current_batch
        if total_batches is not None:
            details["total_batches"] = total_batches

        # 计算总体进度（文件级别）
        progress = None
        if current_file is not None and total_files is not None and total_files > 0:
            progress = (current_file / total_files) * 100

        self.update_stage(
            stage="clustering",
            progress=progress,
            current=current_file,
            total=total_files,
            message=message or "正在进行聚类分析...",
            details=details,
        )

    def update_review(
        self,
        current_review: Optional[int] = None,
        total_reviews: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        """更新复核阶段状态"""
        details: Dict[str, Any] = {}

        # 计算总体进度
        progress = None
        if (
            current_review is not None
            and total_reviews is not None
            and total_reviews > 0
        ):
            progress = (current_review / total_reviews) * 100

        self.update_stage(
            stage="review",
            progress=progress,
            current=current_review,
            total=total_reviews,
            message=message or "正在进行无效聚类复核...",
            details=details,
        )

    def update_verification(
        self,
        current_batch: Optional[int] = None,
        total_batches: Optional[int] = None,
        current_task: Optional[int] = None,
        total_tasks: Optional[int] = None,
        batch_id: Optional[str] = None,
        file_name: Optional[str] = None,
        issues_found: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        """更新验证阶段状态"""
        details: Dict[str, Any] = {}
        if batch_id:
            details["batch_id"] = batch_id
        if file_name:
            details["file"] = file_name
        if issues_found is not None:
            details["issues_found"] = issues_found

        # 计算总体进度（批次级别）
        progress = None
        if (
            current_batch is not None
            and total_batches is not None
            and total_batches > 0
        ):
            progress = (current_batch / total_batches) * 100

        self.update_stage(
            stage="verification",
            progress=progress,
            current=current_batch,
            total=total_batches,
            message=message or "正在进行安全验证...",
            details=details,
        )

    def mark_completed(
        self,
        total_issues: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        """标记分析完成"""
        details = {}
        if total_issues is not None:
            details["total_issues"] = total_issues

        self.update_stage(
            stage="completed",
            progress=100.0,
            message=message or "安全分析已完成",
            details=details,
        )

    def mark_error(
        self,
        error_message: str,
        error_type: Optional[str] = None,
    ) -> None:
        """标记错误状态"""
        details = {"error_message": error_message}
        if error_type:
            details["error_type"] = error_type

        self.update_stage(
            stage="error",
            message=f"发生错误: {error_message}",
            details=details,
        )

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return self._read_status()


__all__ = ["StatusManager"]
