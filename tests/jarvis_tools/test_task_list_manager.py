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


class TestTaskVerificationConfig:
    """测试任务验证配置项（task_verification.enabled）"""

    def setup_method(self):
        """设置测试环境"""
        self.tool = task_list_manager()
        self.mock_agent = Mock()
        self.mock_agent.name = "test_agent"

    def test_verification_disabled_by_default(self, monkeypatch):
        """测试默认情况下任务验证关闭"""
        monkeypatch.setattr(
            "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
            {},
        )
        assert self.tool._is_task_verification_enabled() is False

    def test_verification_enabled_when_configured(self, monkeypatch):
        """测试配置开启时任务验证启用"""
        monkeypatch.setattr(
            "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
            {"task_verification": {"enabled": True}},
        )
        assert self.tool._is_task_verification_enabled() is True

    def test_verification_disabled_when_explicitly_false(self, monkeypatch):
        """测试配置显式关闭时任务验证关闭"""
        monkeypatch.setattr(
            "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
            {"task_verification": {"enabled": False}},
        )
        assert self.tool._is_task_verification_enabled() is False

    def test_verification_disabled_when_config_not_dict(self, monkeypatch):
        """测试配置项非 dict 时按默认关闭处理"""
        monkeypatch.setattr(
            "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
            {"task_verification": "invalid"},
        )
        assert self.tool._is_task_verification_enabled() is False

    def test_verification_disabled_when_missing_enabled(self, monkeypatch):
        """测试配置项缺少 enabled 字段时按默认关闭处理"""
        monkeypatch.setattr(
            "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
            {"task_verification": {}},
        )
        assert self.tool._is_task_verification_enabled() is False


class TestUpdateTaskVerificationMethod:
    """测试 update_task 时 verification_method 的强制行为（由 task_verification.enabled 决定）"""

    def setup_method(self):
        """设置测试环境"""
        self.tool = task_list_manager()
        self.mock_agent = Mock()
        self.mock_agent.name = "test_agent"
        self.mock_agent.get_user_data.return_value = "test_list_id"
        self.mock_agent.set_user_data.return_value = None
        self.mock_agent.delete_user_data.return_value = None

        # 任务对象
        self.mock_task = Mock()
        self.mock_task.task_id = "task_1"
        self.mock_task.task_name = "测试任务"
        self.mock_task.task_desc = "任务描述"
        self.mock_task.expected_output = "预期输出"
        self.mock_task.status = TaskStatus.RUNNING
        self.mock_task.agent_type.value = "main"
        self.mock_task.model_call_count = 0
        self.mock_task.to_dict.return_value = {
            "task_id": "task_1",
            "task_name": "测试任务",
            "status": "running",
            "agent_type": "main",
        }

        # 任务列表
        self.mock_task_list = Mock()
        self.mock_task_list.tasks = {}
        self.mock_task_list.get_task.return_value = self.mock_task
        self.mock_task_list.update_task.return_value = True

        # 任务列表管理器
        self.mock_task_list_manager = Mock()
        self.mock_task_list_manager._check_agent_permission.return_value = True
        self.mock_task_list_manager.get_task_list.return_value = self.mock_task_list
        self.mock_task_list_manager.update_task_status.return_value = (True, None)

    def _call_update(self, verification_method=None):
        """构造并调用 _handle_update_task"""
        task_update_info = {"status": "completed", "actual_output": "完成"}
        if verification_method is not None:
            task_update_info["verification_method"] = verification_method
        args = {
            "action": "update_task",
            "task_id": "task_1",
            "task_update_info": task_update_info,
            "agent": self.mock_agent,
        }
        return self.tool._handle_update_task(
            args, self.mock_task_list_manager, "test_agent", True, self.mock_agent
        )

    def test_update_completed_without_verification_method_config_off(self, monkeypatch):
        """配置关闭时，update_task completed 不强制 verification_method，直接成功"""
        monkeypatch.setattr(
            "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
            {"task_verification": {"enabled": False}},
        )
        result = self._call_update()
        assert result["success"] is True
        # 状态被正常更新
        self.mock_task_list_manager.update_task_status.assert_called_once()

    def test_update_completed_without_verification_method_config_on(self, monkeypatch):
        """配置开启时，update_task completed 缺少 verification_method 应失败"""
        monkeypatch.setattr(
            "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
            {"task_verification": {"enabled": True}},
        )
        result = self._call_update()
        assert result["success"] is False
        assert "缺少 verification_method" in result["stderr"]
        # 状态不应被更新
        self.mock_task_list_manager.update_task_status.assert_not_called()

    def test_update_completed_with_verification_method_config_on_low_call_count(
        self, monkeypatch
    ):
        """配置开启且提供 verification_method，模型调用次数≤15 时跳过验证直接完成"""
        monkeypatch.setattr(
            "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
            {"task_verification": {"enabled": True}},
        )
        self.mock_task.model_call_count = 10
        result = self._call_update(verification_method="检查文件是否存在")
        assert result["success"] is True
        self.mock_task_list_manager.update_task_status.assert_called_once()
