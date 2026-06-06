# -*- coding: utf-8 -*-
"""定时器工具模块

支持定时执行工具、定时添加提示词到多行输入、延时执行工具。
支持相对/绝对/循环定时，定时器为全局实例，会话保存/恢复时需持久化。
"""

import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from jarvis.jarvis_utils.output import PrettyOutput


# 全局定时器管理器单例
_timer_manager_instance: Optional["TimerManager"] = None
_timer_manager_lock = threading.Lock()


def get_timer_manager() -> "TimerManager":
    """获取全局定时器管理器单例"""
    global _timer_manager_instance
    with _timer_manager_lock:
        if _timer_manager_instance is None:
            _timer_manager_instance = TimerManager()
        return _timer_manager_instance


class TimerTask:
    """定时任务数据类"""

    def __init__(
        self,
        task_id: str,
        task_type: str,
        time_type: str,
        time_value: Any,
        tool_name: Optional[str] = None,
        tool_args: Optional[Dict[str, Any]] = None,
        prompt_text: Optional[str] = None,
        interval_seconds: Optional[float] = None,
        status: str = "pending",
        created_at: Optional[str] = None,
        next_fire_time: Optional[str] = None,
    ) -> None:
        self.task_id = task_id
        self.task_type = task_type  # tool_call / prompt / delayed_tool_call
        self.time_type = time_type  # relative / absolute / interval
        self.time_value = time_value
        self.tool_name = tool_name
        self.tool_args = tool_args or {}
        self.prompt_text = prompt_text
        self.interval_seconds = interval_seconds
        self.status = status  # pending / running / completed / cancelled
        self.created_at = created_at or datetime.now().isoformat()
        self.next_fire_time = next_fire_time
        self._timer: Optional[threading.Timer] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "time_type": self.time_type,
            "time_value": self.time_value,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "prompt_text": self.prompt_text,
            "interval_seconds": self.interval_seconds,
            "status": self.status,
            "created_at": self.created_at,
            "next_fire_time": self.next_fire_time,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimerTask":
        """从字典反序列化"""
        return cls(
            task_id=data["task_id"],
            task_type=data["task_type"],
            time_type=data["time_type"],
            time_value=data["time_value"],
            tool_name=data.get("tool_name"),
            tool_args=data.get("tool_args", {}),
            prompt_text=data.get("prompt_text"),
            interval_seconds=data.get("interval_seconds"),
            status=data.get("status", "pending"),
            created_at=data.get("created_at"),
            next_fire_time=data.get("next_fire_time"),
        )


class TimerManager:
    """定时器管理器（全局单例）

    管理所有定时任务的创建、调度、取消和持久化。
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, TimerTask] = {}
        self._lock = threading.Lock()
        self._registry = None  # 延迟获取，避免循环导入

    def _get_registry(self):
        """延迟获取工具注册中心"""
        if self._registry is None:
            from jarvis.jarvis_tools.registry import ToolRegistry

            self._registry = ToolRegistry()
        return self._registry

    def _calculate_delay(self, time_type: str, time_value: Any) -> float:
        """计算到下次触发的延迟秒数"""
        if time_type == "relative":
            delay = float(time_value)
            if delay <= 0:
                raise ValueError("相对时间必须大于0")
            return delay
        elif time_type == "absolute":
            target_time = datetime.fromisoformat(time_value)
            delay = (target_time - datetime.now()).total_seconds()
            if delay <= 0:
                raise ValueError(f"绝对时间已过期: {time_value}")
            return delay
        elif time_type == "interval":
            interval = float(time_value)
            if interval <= 0:
                raise ValueError("循环间隔必须大于0")
            return interval
        else:
            raise ValueError(f"无效的时间类型: {time_type}")

    def add_task(
        self,
        task_type: str,
        time_type: str,
        time_value: Any,
        tool_name: Optional[str] = None,
        tool_args: Optional[Dict[str, Any]] = None,
        prompt_text: Optional[str] = None,
        interval_seconds: Optional[float] = None,
    ) -> TimerTask:
        """添加定时任务"""
        if task_type in ("tool_call", "delayed_tool_call") and not tool_name:
            raise ValueError(f"任务类型 {task_type} 必须指定 tool_name")
        if task_type == "prompt" and not prompt_text:
            raise ValueError("prompt 类型任务必须指定 prompt_text")
        if time_type == "interval" and not interval_seconds:
            interval_seconds = float(time_value)

        task_id = str(uuid.uuid4())[:8]
        delay = self._calculate_delay(time_type, time_value)
        next_fire = (datetime.now() + timedelta(seconds=delay)).isoformat()

        task = TimerTask(
            task_id=task_id,
            task_type=task_type,
            time_type=time_type,
            time_value=time_value,
            tool_name=tool_name,
            tool_args=tool_args or {},
            prompt_text=prompt_text,
            interval_seconds=interval_seconds,
            status="pending",
            next_fire_time=next_fire,
        )

        with self._lock:
            self._tasks[task_id] = task
            self._schedule_task(task, delay)

        return task

    def _schedule_task(self, task: TimerTask, delay: float) -> None:
        """调度定时任务"""
        if task._timer is not None:
            task._timer.cancel()
        task._timer = threading.Timer(delay, self._execute_task, args=(task.task_id,))
        task._timer.daemon = True
        task._timer.start()
        task.status = "pending"

    def _execute_task(self, task_id: str) -> None:
        """执行定时任务回调"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.status == "cancelled":
                return
        try:
            task.status = "running"
            if task.task_type == "prompt":
                self._execute_prompt_task(task)
            elif task.task_type in ("tool_call", "delayed_tool_call"):
                self._execute_tool_task(task)
            if task.time_type == "interval" and task.status != "cancelled":
                interval = task.interval_seconds or float(task.time_value)
                next_fire = (datetime.now() + timedelta(seconds=interval)).isoformat()
                task.next_fire_time = next_fire
                task.status = "pending"
                self._schedule_task(task, interval)
            else:
                task.status = "completed"
        except Exception as e:
            task.status = "completed"
            PrettyOutput.auto_print(f"定时任务 {task_id} 执行失败: {e}")

    def _inject_message(self, message: str, description: str = "") -> None:
        """统一的消息注入方法

        Args:
            message: 要注入的消息内容
            description: 用于日志的描述信息（如"定时提示"、"工具执行结果"）
        """
        from jarvis.jarvis_utils.globals import add_input_buffer, input_inject_callback

        # 优先使用输入注入回调（如果Agent正在等待输入）
        if input_inject_callback is not None:
            input_inject_callback(message)
        else:
            add_input_buffer(message)

        # 打印日志
        if description:
            PrettyOutput.auto_print(description)

    def _execute_prompt_task(self, task: TimerTask) -> None:
        """执行提示词注入任务"""
        try:
            # 构建注入消息，包含定时器信息
            inject_message = f"[Timer#{task.task_id[:8]}|{task.task_type}|{task.time_type}] {task.prompt_text}"
            self._inject_message(inject_message, f"定时提示已注入: {task.prompt_text}")
        except Exception as e:
            PrettyOutput.auto_print(f"提示词注入失败: {e}")

    def _execute_tool_task(self, task: TimerTask) -> None:
        """执行工具调用任务"""
        try:
            registry = self._get_registry()
            tool = registry.get_tool(task.tool_name)
            if tool:
                PrettyOutput.auto_print(f"定时执行工具: {task.tool_name}")
                result = tool.func(task.tool_args)

                # 构建结果消息
                result_message = (
                    result.get("message", str(result))
                    if result
                    else "工具执行完成（无返回值）"
                )
                PrettyOutput.auto_print(f"工具执行结果: {result_message}")

                inject_message = f"[Timer#{task.task_id[:8]}|{task.task_type}|{task.time_type}] 工具 {task.tool_name} 执行完成\n结果: {result_message}"
                self._inject_message(
                    inject_message, f"工具执行结果已注入: {result_message}"
                )
            else:
                error_message = f"工具不存在: {task.tool_name}"
                PrettyOutput.auto_print(error_message)
                inject_message = f"[Timer#{task.task_id[:8]}|{task.task_type}|{task.time_type}] {error_message}"
                self._inject_message(inject_message, f"工具错误已注入: {error_message}")
        except Exception as e:
            error_message = f"工具执行失败: {e}"
            PrettyOutput.auto_print(error_message)
            try:
                inject_message = f"[Timer#{task.task_id[:8]}|{task.task_type}|{task.time_type}] {error_message}"
                self._inject_message(inject_message, f"工具异常已注入: {error_message}")
            except Exception:
                pass  # 忽略二次异常

    def cancel_task(self, task_id: str) -> bool:
        """取消定时任务"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if task._timer is not None:
                task._timer.cancel()
            task.status = "cancelled"
            return True

    def list_tasks(self) -> list[Dict[str, Any]]:
        """列出所有定时任务"""
        with self._lock:
            return [
                task.to_dict()
                for task in self._tasks.values()
                if task.status != "cancelled"
            ]

    def clear_tasks(self) -> int:
        """清除所有定时任务"""
        with self._lock:
            count = 0
            for task in self._tasks.values():
                if task._timer is not None:
                    task._timer.cancel()
                if task.status != "cancelled":
                    count += 1
                task.status = "cancelled"
            self._tasks.clear()
            return count

    def get_state(self) -> Dict[str, Any]:
        """获取定时器状态用于持久化"""
        with self._lock:
            tasks_data = []
            for task in self._tasks.values():
                if task.status != "cancelled" and task.time_type != "relative":
                    tasks_data.append(task.to_dict())
            return {"tasks": tasks_data}

    def restore_state(self, state_data: Dict[str, Any]) -> None:
        """从持久化数据恢复定时器状态"""
        tasks_data = state_data.get("tasks", [])
        now = datetime.now()
        restored_count = 0
        skipped_count = 0
        for task_data in tasks_data:
            task = TimerTask.from_dict(task_data)
            if task.next_fire_time:
                try:
                    next_fire = datetime.fromisoformat(task.next_fire_time)
                    if next_fire <= now:
                        if task.time_type == "interval":
                            interval = task.interval_seconds or float(task.time_value)
                            delay = interval
                        else:
                            skipped_count += 1
                            continue
                    else:
                        delay = (next_fire - now).total_seconds()
                except (ValueError, TypeError):
                    skipped_count += 1
                    continue
            else:
                skipped_count += 1
                continue
            with self._lock:
                self._tasks[task.task_id] = task
                self._schedule_task(task, delay)
            restored_count += 1
        if restored_count > 0 or skipped_count > 0:
            msg = f"定时器已恢复: {restored_count} 个任务"
            if skipped_count > 0:
                msg += f", {skipped_count} 个已过期跳过"
            PrettyOutput.auto_print(msg)


class TimerTool:
    """定时器工具

    支持定时注入提示词到多行输入，支持相对/绝对/循环定时。
    注意：定时执行工具功能已集成到工具调用中，可在任意工具调用的 arguments 中添加 after/at/loop 参数。
    """

    name = "timer"
    description = "定时器工具：支持定时注入提示词，管理定时任务（取消/列出/清除）"
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "操作类型：add(添加定时提示词任务)、cancel(取消任务)、list(列出所有任务)、clear(清除所有任务)",
                "enum": ["add", "cancel", "list", "clear"],
            },
            "task_type": {
                "type": "string",
                "description": "任务类型（add操作必填）：仅支持 prompt(定时注入提示词)",
                "enum": ["prompt"],
            },
            "time_type": {
                "type": "string",
                "description": "时间类型（add操作必填）：relative(相对秒数)、absolute(绝对时间ISO格式)、interval(循环间隔秒数)",
                "enum": ["relative", "absolute", "interval"],
            },
            "time_value": {
                "type": "string",
                "description": "时间值（add操作必填）：relative时为秒数、absolute时为ISO时间字符串、interval时为间隔秒数",
            },
            "prompt_text": {
                "type": "string",
                "description": "提示词文本（add操作必填）",
            },
            "task_id": {
                "type": "string",
                "description": "任务ID（cancel操作必填）",
            },
        },
        "required": ["operation"],
    }

    def __init__(self) -> None:
        """初始化定时器工具"""
        self.manager = get_timer_manager()

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行定时器操作"""
        operation = args.get("operation", "")
        if operation == "add":
            return self._handle_add(args)
        elif operation == "cancel":
            return self._handle_cancel(args)
        elif operation == "list":
            return self._handle_list()
        elif operation == "clear":
            return self._handle_clear()
        else:
            return {"success": False, "message": f"无效的操作: {operation}"}

    def _handle_add(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """处理添加定时提示词任务"""
        task_type = kwargs.get("task_type")
        time_type = kwargs.get("time_type")
        time_value = kwargs.get("time_value")
        prompt_text = kwargs.get("prompt_text")

        if not task_type:
            return {"success": False, "message": "add操作必须指定 task_type"}
        if task_type != "prompt":
            return {
                "success": False,
                "message": "timer工具仅支持 prompt 类型任务。定时执行工具请在工具调用的 arguments 中添加 after/at/loop 参数。",
            }
        if not time_type:
            return {"success": False, "message": "add操作必须指定 time_type"}
        if not time_value:
            return {"success": False, "message": "add操作必须指定 time_value"}
        if not prompt_text:
            return {"success": False, "message": "prompt类型任务必须指定 prompt_text"}

        try:
            task = self.manager.add_task(
                task_type=task_type,
                time_type=time_type,
                time_value=time_value,
                prompt_text=prompt_text,
                interval_seconds=float(kwargs.get("time_value", 0))
                if time_type == "interval"
                else None,
            )
            return {
                "success": True,
                "stdout": f"定时任务已添加 (ID: {task.task_id})",
                "stderr": "",
                "task_id": task.task_id,
                "next_fire_time": task.next_fire_time,
            }
        except ValueError as e:
            return {"success": False, "stdout": "", "stderr": str(e)}

    def _handle_cancel(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """处理取消定时任务"""
        task_id = kwargs.get("task_id", "")
        if not task_id:
            return {"success": False, "message": "cancel操作必须指定 task_id"}
        if self.manager.cancel_task(task_id):
            return {
                "success": True,
                "stdout": f"定时任务 {task_id} 已取消",
                "stderr": "",
            }
        return {"success": False, "stdout": "", "stderr": f"定时任务 {task_id} 不存在"}

    def _handle_list(self) -> Dict[str, Any]:
        """处理列出定时任务"""
        tasks = self.manager.list_tasks()
        if not tasks:
            return {
                "success": True,
                "stdout": "当前没有定时任务",
                "stderr": "",
                "tasks": [],
            }
        lines = ["当前定时任务:"]
        for t in tasks:
            lines.append(
                f"  ID: {t['task_id']} | 类型: {t['task_type']} | 时间类型: {t['time_type']} | 状态: {t['status']}"
            )
            if t.get("tool_name"):
                lines.append(f"    工具: {t['tool_name']}")
            if t.get("prompt_text"):
                lines.append(f"    提示: {t['prompt_text']}")
            lines.append(f"    下次触发: {t.get('next_fire_time', 'N/A')}")
        return {"success": True, "message": "\n".join(lines), "tasks": tasks}

    def _handle_clear(self) -> Dict[str, Any]:
        """处理清除所有定时任务"""
        count = self.manager.clear_tasks()
        return {"success": True, "stdout": f"已清除 {count} 个定时任务", "stderr": ""}
