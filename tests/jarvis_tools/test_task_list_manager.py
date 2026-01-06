# -*- coding: utf-8 -*-
"""Task List Manager 依赖验证功能测试"""

import pytest
from unittest.mock import Mock
from jarvis.jarvis_agent.task_list import TaskStatus
from jarvis.jarvis_tools.task_list_manager import (
    task_list_manager,
    DependencyNotFoundError,
    DependencyNotCompletedError,
    DependencyFailedError,
)


class TestDependencyValidation:
    """测试依赖验证功能"""

    def setup_method(self):
        """设置测试环境"""
        self.tool = task_list_manager()
        self.mock_agent = Mock()
        self.mock_task_list_manager = Mock()
        self.mock_agent.task_list_manager = self.mock_task_list_manager
        self.mock_agent.name = "test_agent"

        # 设置默认的user_data行为
        self.mock_agent.get_user_data.return_value = None
        self.mock_agent.set_user_data.return_value = None

    def test_validate_dependencies_status_no_dependencies(self):
        """测试无依赖任务的情况"""
        # 创建没有依赖的任务
        mock_task = Mock()
        mock_task.dependencies = []

        # 应该正常返回，不抛出异常
        self.tool._validate_dependencies_status(
            task_list_manager=self.mock_task_list_manager,
            task_list_id="test_list_id",
            task=mock_task,
            agent_id="test_agent",
            is_main_agent=True,
        )

    def test_validate_dependencies_status_completed_dependency(self):
        """测试依赖任务已完成的情况"""
        # 创建已完成状态的依赖任务
        mock_task = Mock()
        mock_task.dependencies = ["dep_task_1"]

        mock_dep_task = Mock()
        mock_dep_task.status = TaskStatus.COMPLETED

        self.mock_task_list_manager.get_task_detail.return_value = (
            mock_dep_task,
            True,
            None,
        )

        # 应该正常返回，不抛出异常
        self.tool._validate_dependencies_status(
            task_list_manager=self.mock_task_list_manager,
            task_list_id="test_list_id",
            task=mock_task,
            agent_id="test_agent",
            is_main_agent=True,
        )

    def test_validate_dependencies_status_dependency_not_found(self):
        """测试依赖任务不存在的情况"""
        mock_task = Mock()
        mock_task.dependencies = ["non_existent_task"]

        self.mock_task_list_manager.get_task_detail.return_value = (
            None,
            False,
            "任务不存在",
        )

        # 应该抛出DependencyNotFoundError
        with pytest.raises(DependencyNotFoundError) as exc_info:
            self.tool._validate_dependencies_status(
                task_list_manager=self.mock_task_list_manager,
                task_list_id="test_list_id",
                task=mock_task,
                agent_id="test_agent",
                is_main_agent=True,
            )

        assert "依赖任务 'non_existent_task' 不存在" in str(exc_info.value)

    def test_validate_dependencies_status_dependency_failed(self):
        """测试依赖任务失败的情况"""
        mock_task = Mock()
        mock_task.dependencies = ["failed_task"]

        mock_dep_task = Mock()
        mock_dep_task.status = TaskStatus.FAILED
        mock_dep_task.task_name = "失败的任务"

        self.mock_task_list_manager.get_task_detail.return_value = (
            mock_dep_task,
            True,
            None,
        )

        # 应该抛出DependencyFailedError
        with pytest.raises(DependencyFailedError) as exc_info:
            self.tool._validate_dependencies_status(
                task_list_manager=self.mock_task_list_manager,
                task_list_id="test_list_id",
                task=mock_task,
                agent_id="test_agent",
                is_main_agent=True,
            )

        assert "依赖任务 'failed_task' 执行失败" in str(exc_info.value)

    def test_validate_dependencies_status_dependency_abandoned(self):
        """测试依赖任务被放弃的情况"""
        mock_task = Mock()
        mock_task.dependencies = ["abandoned_task"]

        mock_dep_task = Mock()
        mock_dep_task.status = TaskStatus.ABANDONED
        mock_dep_task.task_name = "被放弃的任务"

        self.mock_task_list_manager.get_task_detail.return_value = (
            mock_dep_task,
            True,
            None,
        )

        # 应该抛出DependencyFailedError
        with pytest.raises(DependencyFailedError) as exc_info:
            self.tool._validate_dependencies_status(
                task_list_manager=self.mock_task_list_manager,
                task_list_id="test_list_id",
                task=mock_task,
                agent_id="test_agent",
                is_main_agent=True,
            )

        assert "依赖任务 'abandoned_task' 已被放弃" in str(exc_info.value)

    def test_validate_dependencies_status_dependency_pending(self):
        """测试依赖任务尚未开始的情况"""
        mock_task = Mock()
        mock_task.dependencies = ["pending_task"]

        mock_dep_task = Mock()
        mock_dep_task.status = TaskStatus.PENDING
        mock_dep_task.task_name = "待执行的任务"

        self.mock_task_list_manager.get_task_detail.return_value = (
            mock_dep_task,
            True,
            None,
        )

        # 应该抛出DependencyNotCompletedError
        with pytest.raises(DependencyNotCompletedError) as exc_info:
            self.tool._validate_dependencies_status(
                task_list_manager=self.mock_task_list_manager,
                task_list_id="test_list_id",
                task=mock_task,
                agent_id="test_agent",
                is_main_agent=True,
            )

        assert "依赖任务 'pending_task' 尚未开始执行" in str(exc_info.value)

    def test_validate_dependencies_status_dependency_running(self):
        """测试依赖任务正在执行的情况"""
        mock_task = Mock()
        mock_task.dependencies = ["running_task"]

        mock_dep_task = Mock()
        mock_dep_task.status = TaskStatus.RUNNING
        mock_dep_task.task_name = "执行中的任务"

        self.mock_task_list_manager.get_task_detail.return_value = (
            mock_dep_task,
            True,
            None,
        )

        # 应该抛出DependencyNotCompletedError
        with pytest.raises(DependencyNotCompletedError) as exc_info:
            self.tool._validate_dependencies_status(
                task_list_manager=self.mock_task_list_manager,
                task_list_id="test_list_id",
                task=mock_task,
                agent_id="test_agent",
                is_main_agent=True,
            )

        assert "依赖任务 'running_task' 正在执行中" in str(exc_info.value)

    def test_validate_dependencies_status_multiple_dependencies(self):
        """测试多个依赖任务的情况"""
        mock_task = Mock()
        mock_task.dependencies = ["dep1", "dep2", "dep3"]

        # 设置不同的依赖状态
        def mock_get_task_detail(task_list_id, task_id, **kwargs):
            mock_dep_task = Mock()
            if task_id == "dep1":
                mock_dep_task.status = TaskStatus.COMPLETED
                return mock_dep_task, True, None
            elif task_id == "dep2":
                mock_dep_task.status = TaskStatus.FAILED
                mock_dep_task.task_name = "失败的任务"
                return mock_dep_task, True, None
            elif task_id == "dep3":
                mock_dep_task.status = TaskStatus.PENDING
                mock_dep_task.task_name = "待执行的任务"
                return mock_dep_task, True, None
            return None, False, "任务不存在"

        self.mock_task_list_manager.get_task_detail.side_effect = mock_get_task_detail

        # 应该抛出异常，因为dep2失败，dep3未完成
        with pytest.raises(DependencyFailedError) as exc_info:
            self.tool._validate_dependencies_status(
                task_list_manager=self.mock_task_list_manager,
                task_list_id="test_list_id",
                task=mock_task,
                agent_id="test_agent",
                is_main_agent=True,
            )

        # 应该发现第一个失败的依赖
        assert "依赖任务 'dep2' 执行失败" in str(exc_info.value)


class TestDependencyValidationIntegration:
    """测试依赖验证的集成场景"""

    def setup_method(self):
        """设置测试环境"""
        self.tool = task_list_manager()
        self.mock_agent = Mock()
        self.mock_task_list_manager = Mock()
        self.mock_agent.task_list_manager = self.mock_task_list_manager
        self.mock_agent.name = "test_agent"

        # 设置默认的user_data行为
        self.mock_agent.get_user_data.return_value = "test_list_id"
        self.mock_agent.set_user_data.return_value = None

    def test_execute_task_with_invalid_dependencies(self):
        """测试执行有无效依赖的任务"""
        # 创建待执行状态的任务
        mock_task = Mock()
        mock_task.task_id = "task_1"
        mock_task.status = TaskStatus.PENDING
        mock_task.dependencies = ["failed_dep"]
        mock_task.agent_type.value = "main"
        mock_task.task_name = "测试任务"
        mock_task.task_desc = "任务描述"
        mock_task.expected_output = "预期输出"

        # 依赖任务已失败
        mock_dep_task = Mock()
        mock_dep_task.status = TaskStatus.FAILED
        mock_dep_task.task_name = "失败的任务"

        def mock_get_task_detail(task_list_id, task_id, **kwargs):
            if task_id == "task_1":
                return mock_task, True, None
            elif task_id == "failed_dep":
                return mock_dep_task, True, None
            return None, False, "任务不存在"

        self.mock_task_list_manager.get_task_detail.side_effect = mock_get_task_detail

        args = {
            "action": "execute_task",
            "task_id": "task_1",
            "additional_info": "测试执行有无效依赖的任务",
            "agent": self.mock_agent,
        }

        result = self.tool.execute(args)

        # 验证依赖验证失败，任务不能执行
        assert result["success"] is False
        assert "依赖任务 'failed_dep' 执行失败" in result["stderr"]

    def test_check_dependencies_completed_all_completed(self):
        """测试所有依赖都已完成的情况"""
        dependencies = ["dep1", "dep2", "dep3"]

        def mock_get_task_detail(task_list_id, task_id, **kwargs):
            mock_dep_task = Mock()
            mock_dep_task.status = TaskStatus.COMPLETED
            return mock_dep_task, True, None

        self.mock_task_list_manager.get_task_detail.side_effect = mock_get_task_detail

        result = self.tool._check_dependencies_completed(
            task_list_manager=self.mock_task_list_manager,
            task_list_id="test_list_id",
            dependencies=dependencies,
            agent_id="test_agent",
            is_main_agent=True,
        )

        assert result["success"] is True
        assert result["stderr"] == ""

    def test_check_dependencies_completed_with_failures(self):
        """测试有依赖失败的情况"""
        dependencies = ["dep1", "dep2", "dep3"]

        def mock_get_task_detail(task_list_id, task_id, **kwargs):
            mock_dep_task = Mock()
            if task_id == "dep1":
                mock_dep_task.status = TaskStatus.COMPLETED
                mock_dep_task.task_name = "完成的任务"
                return mock_dep_task, True, None
            elif task_id == "dep2":
                mock_dep_task.status = TaskStatus.FAILED
                mock_dep_task.task_name = "失败的任务"
                return mock_dep_task, True, None
            elif task_id == "dep3":
                mock_dep_task.status = TaskStatus.PENDING
                mock_dep_task.task_name = "待执行的任务"
                return mock_dep_task, True, None
            return None, False, "任务不存在"

        self.mock_task_list_manager.get_task_detail.side_effect = mock_get_task_detail

        result = self.tool._check_dependencies_completed(
            task_list_manager=self.mock_task_list_manager,
            task_list_id="test_list_id",
            dependencies=dependencies,
            agent_id="test_agent",
            is_main_agent=True,
        )

        assert result["success"] is False
        assert "依赖任务 [失败的任务] 状态为 failed，无法执行" in result["stderr"]
        assert (
            "依赖任务 [待执行的任务] 状态为 pending，需要为 completed"
            in result["stderr"]
        )


class TestBatchExecution:
    """测试批量执行任务功能"""

    def setup_method(self):
        """设置测试环境"""
        self.tool = task_list_manager()
        self.mock_agent = Mock()
        self.mock_task_list_manager = Mock()
        self.mock_agent.task_list_manager = self.mock_task_list_manager
        self.mock_agent.name = "test_agent"

        # 设置默认的user_data行为
        self.mock_agent.get_user_data.return_value = None
        self.mock_agent.set_user_data.return_value = None

    def test_validate_batch_execution_conditions_empty_task_ids(self):
        """测试空任务ID列表的情况"""
        result = self.tool._validate_batch_execution_conditions(
            task_list_manager=self.mock_task_list_manager,
            task_list_id="test_list_id",
            task_ids=[],
            agent_id="test_agent",
            is_main_agent=True,
        )

        assert result[0] is False
        assert "任务ID列表为空" in result[1]
        assert result[2] == []

    def test_validate_batch_execution_conditions_task_not_found(self):
        """测试任务不存在的情况"""
        self.mock_task_list_manager.get_task_detail.return_value = (
            None,
            False,
            "任务不存在",
        )

        result = self.tool._validate_batch_execution_conditions(
            task_list_manager=self.mock_task_list_manager,
            task_list_id="test_list_id",
            task_ids=["task-1"],
            agent_id="test_agent",
            is_main_agent=True,
        )

        assert result[0] is False
        assert "不存在或无权访问" in result[1]

    def test_validate_batch_execution_conditions_not_sub_type(self):
        """测试任务类型不是sub的情况"""
        mock_task = Mock()
        mock_task.agent_type.value = "main"
        mock_task.status.value = "pending"
        mock_task.dependencies = []

        self.mock_task_list_manager.get_task_detail.return_value = (
            mock_task,
            True,
            None,
        )

        result = self.tool._validate_batch_execution_conditions(
            task_list_manager=self.mock_task_list_manager,
            task_list_id="test_list_id",
            task_ids=["task-1"],
            agent_id="test_agent",
            is_main_agent=True,
        )

        assert result[0] is False
        assert "类型不是 sub" in result[1]

    def test_validate_batch_execution_conditions_not_pending_status(self):
        """测试任务状态不是pending的情况"""
        mock_task = Mock()
        mock_task.agent_type.value = "sub"
        mock_task.status.value = "running"
        mock_task.dependencies = []

        self.mock_task_list_manager.get_task_detail.return_value = (
            mock_task,
            True,
            None,
        )

        result = self.tool._validate_batch_execution_conditions(
            task_list_manager=self.mock_task_list_manager,
            task_list_id="test_list_id",
            task_ids=["task-1"],
            agent_id="test_agent",
            is_main_agent=True,
        )

        assert result[0] is False
        assert "状态不是 pending" in result[1]

    def test_validate_batch_execution_conditions_dependency_not_completed(self):
        """测试依赖任务未完成的情况"""
        mock_task = Mock()
        mock_task.agent_type.value = "sub"
        mock_task.status.value = "pending"
        mock_task.dependencies = ["dep-1"]
        mock_task.task_name = "测试任务"

        self.mock_task_list_manager.get_task_detail.return_value = (
            mock_task,
            True,
            None,
        )

        self.tool._check_dependencies_completed = Mock(
            return_value={"success": False, "stderr": "依赖未完成"}
        )

        result = self.tool._validate_batch_execution_conditions(
            task_list_manager=self.mock_task_list_manager,
            task_list_id="test_list_id",
            task_ids=["task-1"],
            agent_id="test_agent",
            is_main_agent=True,
        )

        assert result[0] is False
        assert "依赖验证未通过" in result[1]

    def test_validate_batch_execution_conditions_dependent_on_each_other(self):
        """测试任务之间存在依赖关系的情况"""
        mock_task_1 = Mock()
        mock_task_1.task_id = "task-1"
        mock_task_1.task_name = "任务1"
        mock_task_1.agent_type.value = "sub"
        mock_task_1.status.value = "pending"
        mock_task_1.dependencies = ["task-2"]

        mock_task_2 = Mock()
        mock_task_2.task_id = "task-2"
        mock_task_2.task_name = "任务2"
        mock_task_2.agent_type.value = "sub"
        mock_task_2.status.value = "pending"
        mock_task_2.dependencies = []

        def mock_get_task_detail(task_list_id, task_id, **kwargs):
            if task_id == "task-1":
                return mock_task_1, True, None
            elif task_id == "task-2":
                return mock_task_2, True, None
            return None, False, "不存在"

        self.mock_task_list_manager.get_task_detail.side_effect = mock_get_task_detail
        self.tool._check_dependencies_completed = Mock(
            return_value={"success": True, "stderr": ""}
        )

        result = self.tool._validate_batch_execution_conditions(
            task_list_manager=self.mock_task_list_manager,
            task_list_id="test_list_id",
            task_ids=["task-1", "task-2"],
            agent_id="test_agent",
            is_main_agent=True,
        )

        assert result[0] is False
        assert "批量执行要求任务之间彼此独立" in result[1]

    def test_validate_batch_execution_conditions_success(self):
        """测试验证通过的情况"""
        mock_task_1 = Mock()
        mock_task_1.task_id = "task-1"
        mock_task_1.task_name = "任务1"
        mock_task_1.agent_type.value = "sub"
        mock_task_1.status.value = "pending"
        mock_task_1.dependencies = []

        mock_task_2 = Mock()
        mock_task_2.task_id = "task-2"
        mock_task_2.task_name = "任务2"
        mock_task_2.agent_type.value = "sub"
        mock_task_2.status.value = "pending"
        mock_task_2.dependencies = []

        def mock_get_task_detail(task_list_id, task_id, **kwargs):
            if task_id == "task-1":
                return mock_task_1, True, None
            elif task_id == "task-2":
                return mock_task_2, True, None
            return None, False, "不存在"

        self.mock_task_list_manager.get_task_detail.side_effect = mock_get_task_detail
        self.tool._check_dependencies_completed = Mock(
            return_value={"success": True, "stderr": ""}
        )

        result = self.tool._validate_batch_execution_conditions(
            task_list_manager=self.mock_task_list_manager,
            task_list_id="test_list_id",
            task_ids=["task-1", "task-2"],
            agent_id="test_agent",
            is_main_agent=True,
        )

        assert result[0] is True
        assert result[1] is None
        assert len(result[2]) == 2
