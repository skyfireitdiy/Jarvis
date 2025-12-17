# -*- coding: utf-8 -*-
"""任务列表模块。

该模块提供任务列表管理功能，支持多任务动态管理、上下文分层共享、Agent权限隔离。
"""

import json
import os
import time
from collections import OrderedDict
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from threading import Lock
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple

from jarvis.jarvis_utils.output import PrettyOutput


class TaskStatus(Enum):
    """任务状态枚举。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class AgentType(Enum):
    """Agent类型枚举。"""

    MAIN = "main"
    SUB = "sub"  # 子Agent，自动识别代码/通用任务类型


@dataclass
class Task:
    """任务实体。

    任务实体为最小数据单元，采用结构化字典存储。
    """

    task_id: str
    task_name: str
    task_desc: str
    priority: int
    status: TaskStatus
    expected_output: str
    agent_type: AgentType
    create_time: int
    update_time: int
    dependencies: List[str] = field(default_factory=list)
    actual_output: Optional[str] = None

    def __post_init__(self) -> None:
        """验证字段约束。"""
        # 验证 task_id 格式（支持数字ID格式：task-数字）
        if not self.task_id.startswith("task-"):
            raise ValueError(f"task_id 格式错误: {self.task_id}")

        # 验证数字部分是否为有效数字
        try:
            int(self.task_id[5:])  # 提取task-后面的数字部分
        except ValueError:
            raise ValueError(f"task_id 格式错误: {self.task_id}")

        # 验证 priority 为整数类型
        if not isinstance(self.priority, int):
            raise ValueError(f"priority 必须是整数类型: {type(self.priority).__name__}")

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        result = asdict(self)
        result["status"] = self.status.value
        result["agent_type"] = self.agent_type.value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """从字典创建任务。"""
        data = data.copy()
        data["status"] = TaskStatus(data["status"])
        data["agent_type"] = AgentType(data["agent_type"])
        return cls(**data)

    def update_status(
        self, new_status: TaskStatus, actual_output: Optional[str] = None
    ) -> bool:
        """更新任务状态。"""
        # 移除状态转换验证，允许任意状态转换
        self.status = new_status
        self.update_time = int(time.time() * 1000)
        if actual_output is not None:
            self.actual_output = actual_output
        return True


class TaskList:
    """任务列表容器。

    用于管理多个任务实体，采用有序字典存储。
    """

    def __init__(
        self,
        main_goal: str,
        max_active_tasks: int = 10,
        version: int = 1,
    ):
        """初始化任务列表。

        参数:
            main_goal: 用户核心需求
            max_active_tasks: 最大活跃任务数
            version: 版本号
        """
        self.main_goal = main_goal
        self.tasks: Dict[str, Task] = OrderedDict()
        self.max_active_tasks = max_active_tasks
        self.version = version
        self._lock = Lock()

    def _update_active_and_completed_lists(self) -> None:
        """更新活跃任务和已完成任务列表。"""
        # 这个方法主要用于内部维护，实际使用时通过属性访问
        pass

    @property
    def active_task_ids(self) -> List[str]:
        """获取活跃任务 ID 列表。"""
        return [
            task_id
            for task_id, task in self.tasks.items()
            if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        ]

    @property
    def completed_task_ids(self) -> List[str]:
        """获取已完成任务 ID 列表。"""
        return [
            task_id
            for task_id, task in self.tasks.items()
            if task.status == TaskStatus.COMPLETED
        ]

    def add_task(self, task: Task) -> bool:
        """添加任务。"""
        with self._lock:
            if task.task_id in self.tasks:
                return False
            # 验证依赖关系
            for dep_id in task.dependencies:
                if dep_id not in self.tasks:
                    return False
            self.tasks[task.task_id] = task
            self.version += 1
            return True

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务。"""
        return self.tasks.get(task_id)

    def update_task(self, task_id: str, **kwargs: Any) -> bool:
        """更新任务。"""
        with self._lock:
            if task_id not in self.tasks:
                return False
            task = self.tasks[task_id]
            for key, value in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, value)
            task.update_time = int(time.time() * 1000)
            self.version += 1
            return True

    def to_dict(self) -> dict[str, Any]:
        """转换为字典。"""
        return {
            "main_goal": self.main_goal,
            "tasks": {task_id: task.to_dict() for task_id, task in self.tasks.items()},
            "max_active_tasks": self.max_active_tasks,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskList":
        """从字典创建任务列表。"""
        task_list = cls(
            main_goal=data["main_goal"],
            max_active_tasks=data.get("max_active_tasks", 10),
            version=data.get("version", 1),
        )
        for task_id, task_data in data.get("tasks", {}).items():
            task = Task.from_dict(task_data)
            task_list.tasks[task_id] = task
        return task_list


class TaskListManager:
    """任务列表管理器。

    实现三层架构：数据层、核心逻辑层、接口层。
    """

    # 全局任务计数器，用于生成连续的数字任务ID
    _global_task_counter = 0
    _global_tasklist_counter = 0
    _counter_lock = Lock()

    def __init__(self, root_dir: str, persist_dir: Optional[str] = None):
        """初始化任务列表管理器。

        参数:
            root_dir: 项目根目录
            persist_dir: 持久化目录，默认为 .jarvis/task_lists
        """
        self.root_dir = root_dir
        self.persist_dir = persist_dir or os.path.join(
            root_dir, ".jarvis", "task_lists"
        )
        os.makedirs(self.persist_dir, exist_ok=True)

        # 内存存储：task_list_id -> TaskList
        self.task_lists: Dict[str, TaskList] = {}

        # 权限隔离：agent_id -> Set[task_id]
        self.agent_task_mapping: Dict[str, Set[str]] = {}

        # 版本快照：task_list_id -> List[Dict] (按版本号排序)
        self.version_snapshots: dict[str, list[dict[str, Any]]] = {}

        self._lock = Lock()

        # 加载持久化数据
        self._load_persisted_data()

    @classmethod
    def _get_next_task_id(cls) -> str:
        """获取下一个连续的数字任务ID。

        返回:
            str: 格式为 "task-数字" 的任务ID
        """
        with cls._counter_lock:
            cls._global_task_counter += 1
            return f"task-{cls._global_task_counter}"

    @classmethod
    def _get_next_tasklist_id(cls) -> str:
        """获取下一个连续的数字任务列表ID。

        返回:
            str: 格式为 "tasklist-数字" 的任务列表ID
        """
        with cls._counter_lock:
            cls._global_tasklist_counter += 1
            return f"tasklist-{cls._global_tasklist_counter}"

    def _load_persisted_data(self) -> None:
        """从磁盘加载持久化数据。"""
        snapshot_file = os.path.join(self.persist_dir, "snapshots.json")
        if os.path.exists(snapshot_file):
            try:
                with open(snapshot_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.version_snapshots = data.get("snapshots", {})
            except Exception as e:
                PrettyOutput.auto_print(f"⚠️ 加载快照数据失败: {e}")

    def _save_snapshot(self, task_list_id: str, task_list: TaskList) -> None:
        """保存版本快照。"""
        snapshot_file = os.path.join(self.persist_dir, "snapshots.json")
        try:
            snapshot_data = task_list.to_dict()
            if task_list_id not in self.version_snapshots:
                self.version_snapshots[task_list_id] = []
            self.version_snapshots[task_list_id].append(snapshot_data)
            # 只保留最近 10 个版本
            if len(self.version_snapshots[task_list_id]) > 10:
                self.version_snapshots[task_list_id] = self.version_snapshots[
                    task_list_id
                ][-10:]

            # 保存到磁盘
            with open(snapshot_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"snapshots": self.version_snapshots},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 保存快照失败: {e}")

    def _check_agent_permission(
        self, agent_id: str, task_id: str, is_main_agent: bool
    ) -> bool:
        """检查 Agent 权限。

        参数:
            agent_id: Agent ID
            task_id: 任务 ID
            is_main_agent: 是否为主 Agent

        返回:
            bool: 是否有权限
        """
        if is_main_agent:
            return True
        # 子 Agent 只能访问关联的任务
        return task_id in self.agent_task_mapping.get(agent_id, set())

    # ========== 接口层：主 Agent 专属接口 ==========

    def create_task_list(
        self, main_goal: str, agent_id: str
    ) -> Tuple[Optional[str], bool, Optional[str]]:
        """创建任务列表容器。

        参数:
            main_goal: 用户核心需求
            agent_id: 主 Agent ID

        返回:
            Tuple[task_list_id, status, error_msg]
        """
        try:
            task_list_id = self._get_next_tasklist_id()
            task_list = TaskList(main_goal=main_goal)

            with self._lock:
                self.task_lists[task_list_id] = task_list
                # 主 Agent 拥有所有权限
                self.agent_task_mapping[agent_id] = set()

            # 保存快照
            self._save_snapshot(task_list_id, task_list)

            return task_list_id, True, None
        except Exception as e:
            return None, False, str(e)

    def add_task(
        self, task_list_id: str, task_info: dict[str, Any], agent_id: str
    ) -> Tuple[Optional[str], bool, Optional[str]]:
        """添加任务至任务列表。

        参数:
            task_list_id: 任务列表 ID
            task_info: 任务信息字典（含 Task 必选字段）
            agent_id: 主 Agent ID

        返回:
            Tuple[task_id, status, error_msg]
        """
        try:
            with self._lock:
                if task_list_id not in self.task_lists:
                    return None, False, "任务列表不存在"

                task_list = self.task_lists[task_list_id]

                # 验证必选字段
                required_fields = [
                    "task_name",
                    "task_desc",
                    "priority",
                    "expected_output",
                    "agent_type",
                ]
                missing_fields = [
                    field for field in required_fields if field not in task_info
                ]
                if missing_fields:
                    return None, False, f"缺少必选字段: {', '.join(missing_fields)}"

                # 创建任务（使用连续数字ID替代UUID）
                task_id = self._get_next_task_id()
                current_time = int(time.time() * 1000)

                task = Task(
                    task_id=task_id,
                    task_name=task_info["task_name"],
                    task_desc=task_info["task_desc"],
                    priority=task_info["priority"],
                    status=TaskStatus.PENDING,
                    expected_output=task_info["expected_output"],
                    agent_type=AgentType(task_info["agent_type"]),
                    create_time=current_time,
                    update_time=current_time,
                    dependencies=task_info.get("dependencies", []),
                )

                # 验证依赖关系（检查循环依赖）
                if not self._validate_dependencies(task_list, task):
                    return None, False, "依赖关系验证失败：存在循环依赖或无效依赖"

                if not task_list.add_task(task):
                    return None, False, "添加任务失败：任务ID已存在或依赖无效"

                # 保存快照
                self._save_snapshot(task_list_id, task_list)

                return task_id, True, None
        except ValueError as e:
            return None, False, f"字段格式错误: {str(e)}"
        except Exception as e:
            return None, False, str(e)

    def add_tasks(
        self, task_list_id: str, tasks_info: list[dict[str, Any]], agent_id: str
    ) -> Tuple[List[str], bool, Optional[str]]:
        """批量添加任务至任务列表。

        参数:
            task_list_id: 任务列表 ID
            tasks_info: 任务信息字典列表（每个字典含 Task 必选字段）
            agent_id: 主 Agent ID

        返回:
            Tuple[task_ids, status, error_msg]
        """
        try:
            with self._lock:
                if task_list_id not in self.task_lists:
                    return [], False, "任务列表不存在"

                task_list = self.task_lists[task_list_id]

                if not tasks_info:
                    return [], False, "任务列表为空"

                # 验证必选字段
                required_fields = [
                    "task_name",
                    "task_desc",
                    "priority",
                    "expected_output",
                    "agent_type",
                ]

                # 先验证所有任务的基本字段
                for idx, task_info in enumerate(tasks_info):
                    missing_fields = [
                        field for field in required_fields if field not in task_info
                    ]
                    if missing_fields:
                        return (
                            [],
                            False,
                            f"第 {idx + 1} 个任务缺少必选字段: {', '.join(missing_fields)}",
                        )

                # 创建所有任务对象（先不添加到列表，用于验证依赖关系）
                current_time = int(time.time() * 1000)
                tasks_to_add = []
                task_ids = []
                # 创建任务名称到任务ID的映射（用于依赖关系匹配）
                name_to_id_map = {}

                # 第一遍：创建所有任务对象，建立名称到ID的映射
                for task_info in tasks_info:
                    task_id = self._get_next_task_id()
                    task_ids.append(task_id)
                    task_name = task_info["task_name"]
                    name_to_id_map[task_name] = task_id

                    task = Task(
                        task_id=task_id,
                        task_name=task_name,
                        task_desc=task_info["task_desc"],
                        priority=task_info["priority"],
                        status=TaskStatus.PENDING,
                        expected_output=task_info["expected_output"],
                        agent_type=AgentType(task_info["agent_type"]),
                        create_time=current_time,
                        update_time=current_time,
                        dependencies=[],  # 先不设置依赖，后续处理
                    )
                    tasks_to_add.append(task)

                # 第二遍：处理依赖关系，将任务名称转换为任务ID
                for idx, task_info in enumerate(tasks_info):
                    dependencies = task_info.get("dependencies", [])
                    if dependencies:
                        processed_deps = []
                        for dep in dependencies:
                            # 如果是任务名称，转换为任务ID
                            if dep in name_to_id_map:
                                processed_deps.append(name_to_id_map[dep])
                            else:
                                # 可能是任务ID，直接使用（也可能是已存在的任务名称）
                                # 检查是否是已存在的任务名称
                                found = False
                                for existing_task in task_list.tasks.values():
                                    if existing_task.task_name == dep:
                                        processed_deps.append(existing_task.task_id)
                                        found = True
                                        break
                                if not found:
                                    # 假设是任务ID，直接使用
                                    processed_deps.append(dep)
                        tasks_to_add[idx].dependencies = processed_deps

                # 验证所有任务的依赖关系（检查循环依赖和无效依赖）
                # 先检查依赖的任务是否都在本次批量添加的任务中，或者已经在任务列表中
                task_id_map = {t.task_id: t for t in tasks_to_add}
                for task in tasks_to_add:
                    for dep_id in task.dependencies:
                        # 检查依赖是否在本次要添加的任务中
                        dep_in_batch = dep_id in task_id_map
                        # 检查依赖是否已经在任务列表中
                        dep_in_list = task_list.get_task(dep_id) is not None
                        if not (dep_in_batch or dep_in_list):
                            return (
                                [],
                                False,
                                f"任务 {task.task_name} 的依赖 {dep_id} 不存在",
                            )

                # 临时添加所有任务到任务列表（用于循环依赖检查）
                temp_tasks = {}
                for task in tasks_to_add:
                    temp_tasks[task.task_id] = task
                    task_list.tasks[task.task_id] = task

                # 验证循环依赖
                try:
                    for task in tasks_to_add:
                        if not self._validate_dependencies_batch(
                            task_list, task, task_id_map
                        ):
                            return (
                                [],
                                False,
                                f"任务 {task.task_name} 的依赖关系验证失败：存在循环依赖",
                            )
                finally:
                    # 移除临时添加的任务
                    for task_id in temp_tasks:
                        if task_id in task_list.tasks:
                            del task_list.tasks[task_id]

                # 所有验证通过，批量添加任务
                added_task_ids = []
                for task in tasks_to_add:
                    if task_list.add_task(task):
                        added_task_ids.append(task.task_id)
                    else:
                        # 如果某个任务添加失败，回滚已添加的任务
                        for added_id in added_task_ids:
                            if added_id in task_list.tasks:
                                del task_list.tasks[added_id]
                        return (
                            [],
                            False,
                            f"添加任务 {task.task_id} 失败：任务ID已存在或依赖无效",
                        )

                # 保存快照
                self._save_snapshot(task_list_id, task_list)

                return added_task_ids, True, None
        except ValueError as e:
            return [], False, f"字段格式错误: {str(e)}"
        except Exception as e:
            return [], False, str(e)

    def _validate_dependencies(self, task_list: TaskList, task: Task) -> bool:
        """验证依赖关系，检查循环依赖。"""
        visited = set()

        def has_cycle(current_id: str) -> bool:
            if current_id in visited:
                return True
            visited.add(current_id)
            current_task = task_list.get_task(current_id)
            if current_task:
                for dep_id in current_task.dependencies:
                    if has_cycle(dep_id):
                        return True
            visited.remove(current_id)
            return False

        # 检查新任务的依赖是否会导致循环
        visited.add(task.task_id)
        for dep_id in task.dependencies:
            dep_task = task_list.get_task(dep_id)
            if not dep_task:
                # 依赖的任务不存在（可能在批量添加时，依赖的任务在本次批次中）
                # 这种情况下，在批量添加时会单独检查，这里先返回 True
                continue
            if has_cycle(dep_id):
                visited.remove(task.task_id)
                return False  # 存在循环依赖
        visited.remove(task.task_id)
        return True

    def _validate_dependencies_batch(
        self, task_list: TaskList, task: Task, batch_task_map: Dict[str, Task]
    ) -> bool:
        """验证批量添加时的依赖关系，检查循环依赖。"""
        visited = set()

        def has_cycle(current_id: str) -> bool:
            if current_id in visited:
                return True
            visited.add(current_id)
            # 先从批次中查找，再从任务列表中查找
            current_task = batch_task_map.get(current_id) or task_list.get_task(
                current_id
            )
            if current_task:
                for dep_id in current_task.dependencies:
                    if has_cycle(dep_id):
                        return True
            visited.remove(current_id)
            return False

        # 检查新任务的依赖是否会导致循环
        visited.add(task.task_id)
        for dep_id in task.dependencies:
            if has_cycle(dep_id):
                visited.remove(task.task_id)
                return False  # 存在循环依赖
        visited.remove(task.task_id)
        return True

    def get_next_task(
        self, task_list_id: str, agent_id: str
    ) -> Tuple[Optional[Task], Optional[str]]:
        """获取优先级最高的待执行任务。

        参数:
            task_list_id: 任务列表 ID
            agent_id: 主 Agent ID

        返回:
            Tuple[task, msg]
        """
        with self._lock:
            if task_list_id not in self.task_lists:
                return None, "任务列表不存在"

            task_list = self.task_lists[task_list_id]

            # 获取所有待执行任务（pending 状态）
            pending_tasks = [
                task
                for task in task_list.tasks.values()
                if task.status == TaskStatus.PENDING
            ]

            if not pending_tasks:
                return None, "暂无待执行任务"

            # 检查活跃任务数限制
            active_count = len(task_list.active_task_ids)
            if active_count >= task_list.max_active_tasks:
                return None, f"活跃任务数已达上限 ({task_list.max_active_tasks})"

            # 过滤出依赖已满足的任务
            ready_tasks = []
            completed_ids = set(task_list.completed_task_ids)

            for task in pending_tasks:
                if all(dep_id in completed_ids for dep_id in task.dependencies):
                    ready_tasks.append(task)

            if not ready_tasks:
                return None, "暂无满足依赖条件的待执行任务"

            # 按优先级排序（优先级高的在前），相同优先级按创建时间排序
            ready_tasks.sort(key=lambda t: (-t.priority, t.create_time))

            return ready_tasks[0], None

    def rollback_task_list(
        self, task_list_id: str, version: int, agent_id: str
    ) -> Tuple[bool, Optional[str]]:
        """回滚任务列表至指定版本。

        参数:
            task_list_id: 任务列表 ID
            version: 目标版本号
            agent_id: 主 Agent ID

        返回:
            Tuple[status, msg]
        """
        with self._lock:
            if task_list_id not in self.version_snapshots:
                return False, "任务列表不存在"

            snapshots = self.version_snapshots[task_list_id]
            target_snapshot = None
            for snapshot in snapshots:
                if snapshot.get("version") == version:
                    target_snapshot = snapshot
                    break

            if not target_snapshot:
                return False, "版本无效"

            try:
                task_list = TaskList.from_dict(target_snapshot)
                self.task_lists[task_list_id] = task_list
                return True, None
            except Exception as e:
                return False, f"回滚失败: {str(e)}"

    # ========== 接口层：主 Agent / 子 Agent 共享接口 ==========

    def update_task_status(
        self,
        task_list_id: str,
        task_id: str,
        status: str,
        agent_id: str,
        is_main_agent: bool,
        actual_output: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """更新任务状态与执行结果。

        参数:
            task_list_id: 任务列表 ID
            task_id: 任务 ID
            status: 新状态
            agent_id: Agent ID
            is_main_agent: 是否为主 Agent
            actual_output: 实际输出（可选）

        返回:
            Tuple[status, msg]
        """
        try:
            new_status = TaskStatus(status)
        except ValueError:
            return False, f"无效的状态值: {status}"

        try:
            with self._lock:
                if task_list_id not in self.task_lists:
                    return False, "任务列表不存在"

                # 权限检查
                if not self._check_agent_permission(agent_id, task_id, is_main_agent):
                    return False, "权限不足：无法访问该任务"

                task_list = self.task_lists[task_list_id]
                task = task_list.get_task(task_id)
                if not task:
                    return False, "任务不存在"

                # 状态转换
                if not task.update_status(new_status, actual_output):
                    return False, f"无效的状态转换: {task.status.value} -> {status}"

                task_list.version += 1

                # 保存快照
                self._save_snapshot(task_list_id, task_list)

                return True, None
        except Exception as e:
            return False, str(e)

    def get_task_detail(
        self, task_list_id: str, task_id: str, agent_id: str, is_main_agent: bool
    ) -> Tuple[Optional[Task], bool, Optional[str]]:
        """获取任务详细信息。

        参数:
            task_list_id: 任务列表 ID
            task_id: 任务 ID
            agent_id: Agent ID
            is_main_agent: 是否为主 Agent

        返回:
            Tuple[task, status, error_msg]
        """
        with self._lock:
            if task_list_id not in self.task_lists:
                return None, False, "任务列表不存在"

            # 权限检查
            if not self._check_agent_permission(agent_id, task_id, is_main_agent):
                return None, False, "权限不足：无法访问该任务"

            task_list = self.task_lists[task_list_id]
            task = task_list.get_task(task_id)
            if not task:
                return None, False, "任务不存在"

            return task, True, None

    def register_sub_agent(
        self, agent_id: str, task_ids: List[str], main_agent_id: str
    ) -> bool:
        """注册子 Agent 与任务的关联关系。

        参数:
            agent_id: 子 Agent ID
            task_ids: 关联的任务 ID 列表
            main_agent_id: 主 Agent ID（用于权限验证）

        返回:
            bool: 是否成功
        """
        with self._lock:
            # 验证主 Agent 权限（简化实现，实际可以更严格）
            if main_agent_id not in self.agent_task_mapping:
                return False

            self.agent_task_mapping[agent_id] = set(task_ids)
            return True

    def get_task_list(self, task_list_id: str) -> Optional[TaskList]:
        """获取任务列表（内部方法）。"""
        return self.task_lists.get(task_list_id)

    def get_task_list_summary(self, task_list_id: str) -> Optional[dict[str, Any]]:
        """获取任务列表摘要信息。

        返回:
            Dict: 包含任务统计信息的字典
        """
        with self._lock:
            if task_list_id not in self.task_lists:
                return None

            task_list = self.task_lists[task_list_id]
            tasks = list(task_list.tasks.values())

            summary = {
                "task_list_id": task_list_id,
                "main_goal": task_list.main_goal,
                "version": task_list.version,
                "total_tasks": len(tasks),
                "pending": len([t for t in tasks if t.status == TaskStatus.PENDING]),
                "running": len([t for t in tasks if t.status == TaskStatus.RUNNING]),
                "completed": len(
                    [t for t in tasks if t.status == TaskStatus.COMPLETED]
                ),
                "failed": len([t for t in tasks if t.status == TaskStatus.FAILED]),
                "abandoned": len(
                    [t for t in tasks if t.status == TaskStatus.ABANDONED]
                ),
                "tasks": [
                    {
                        "task_id": t.task_id,
                        "task_name": t.task_name,
                        "task_desc": t.task_desc,
                        "status": t.status.value,
                        "priority": t.priority,
                        "agent_type": t.agent_type.value,
                        "dependencies": t.dependencies,
                        "actual_output": t.actual_output,
                    }
                    for t in tasks
                ],
            }
            return summary
