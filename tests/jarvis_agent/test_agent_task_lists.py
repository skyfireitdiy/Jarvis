# -*- coding: utf-8 -*-
"""Agent任务列表保存和恢复功能测试"""

import json
import os
import tempfile
from unittest.mock import Mock, patch

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.task_list import AgentType


class TestAgentTaskLists:
    """测试Agent类的任务列表保存和恢复功能"""

    def setup_method(self):
        """设置测试环境"""
        # 创建一个Mock模型
        self.mock_model = Mock()
        self.mock_model.platform_name.return_value = "test_platform"
        self.mock_model.name.return_value = "test_model"
        self.mock_model.set_system_prompt = Mock()
        self.mock_model.get_remaining_token_count = Mock(return_value=1000)

        # 使用临时目录作为工作目录
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

        # 创建一个带有任务列表的Agent实例进行测试
        with (
            patch(
                "jarvis.jarvis_platform.registry.PlatformRegistry.get_normal_platform",
                return_value=self.mock_model,
            ),
            patch(
                "jarvis.jarvis_platform.registry.PlatformRegistry.create_platform",
                return_value=self.mock_model,
            ),
            patch(
                "jarvis.jarvis_utils.config.get_normal_model_name",
                return_value="test_model",
            ),
            patch(
                "jarvis.jarvis_utils.config.get_normal_platform_name",
                return_value="test_platform",
            ),
            patch(
                "jarvis.jarvis_utils.config.get_data_dir",
                return_value=os.path.join(self.temp_dir, "data"),
            ),
        ):
            self.agent = Agent(system_prompt="Test system prompt", name="test_agent")

    def teardown_method(self):
        """清理测试环境"""
        os.chdir(self.original_cwd)
        # 清理临时目录
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_task_lists_no_tasks(self):
        """测试没有任务列表时的保存功能"""
        # 确保没有任务列表
        self.agent.task_list_manager.task_lists.clear()

        # 调用保存方法
        result = self.agent.session._save_task_lists()

        # 验证返回值
        assert result is True

    def test_save_and_restore_task_lists(self):
        """测试任务列表的保存和恢复功能"""
        # 创建一个任务列表
        task_list_id, success, error = self.agent.task_list_manager.create_task_list(
            main_goal="Test main goal", agent_id="test_agent"
        )
        assert success is True

        # 添加一个任务
        task_info = {
            "task_name": "Test Task",
            "task_desc": "Test task description",
            "expected_output": "Test expected output",
            "agent_type": "main",
        }
        task_id, success, error = self.agent.task_list_manager.add_task(
            task_list_id=task_list_id, task_info=task_info, agent_id="test_agent"
        )
        assert success is True

        # 验证任务已添加
        task_list = self.agent.task_list_manager.get_task_list(task_list_id)
        assert task_list is not None
        assert len(task_list.tasks) == 1

        # 保存任务列表
        save_result = self.agent.session._save_task_lists()
        assert save_result is True

        # 验证保存文件是否存在
        session_dir = os.path.join(self.temp_dir, ".jarvis", "sessions")
        platform_name = self.agent.model.platform_name()
        model_name = self.agent.model.name().replace("/", "_").replace("\\", "_")
        tasklist_file = os.path.join(
            session_dir,
            f"saved_session_{self.agent.name}_{platform_name}_{model_name}_tasklist.json",
        )

        assert os.path.exists(tasklist_file) is True

        # 验证保存的文件内容
        with open(tasklist_file, "r", encoding="utf-8") as f:
            saved_data = json.load(f)

        assert "task_lists" in saved_data
        assert task_list_id in saved_data["task_lists"]

        # 清空当前任务列表
        self.agent.task_list_manager.task_lists.clear()
        assert len(self.agent.task_list_manager.task_lists) == 0

        # 恢复任务列表
        restore_result = self.agent.session._restore_task_lists()
        assert restore_result is True

        # 验证任务列表已恢复
        assert len(self.agent.task_list_manager.task_lists) == 1
        assert task_list_id in self.agent.task_list_manager.task_lists

        restored_task_list = self.agent.task_list_manager.task_lists[task_list_id]
        assert restored_task_list.main_goal == "Test main goal"
        assert len(restored_task_list.tasks) == 1

        restored_task = list(restored_task_list.tasks.values())[0]
        assert restored_task.task_name == "Test Task"
        assert restored_task.task_desc == "Test task description"
        assert restored_task.expected_output == "Test expected output"
        assert restored_task.agent_type == AgentType.MAIN

    def test_restore_task_lists_file_not_exists(self):
        """测试恢复任务列表时文件不存在的情况"""
        # 确保没有保存任务列表文件
        result = self.agent.session._restore_task_lists()

        # 应该返回True（没有文件也视为成功）
        assert result is True

    def test_restore_task_lists_with_multiple_task_lists(self):
        """测试恢复多个任务列表"""
        # 创建第一个任务列表
        task_list_id1, success, error = self.agent.task_list_manager.create_task_list(
            main_goal="Test main goal 1", agent_id="test_agent"
        )
        assert success is True

        # 添加第一个任务
        task_info1 = {
            "task_name": "Test Task 1",
            "task_desc": "Test task description 1",
            "expected_output": "Test expected output 1",
            "agent_type": "main",
        }
        self.agent.task_list_manager.add_task(
            task_list_id=task_list_id1, task_info=task_info1, agent_id="test_agent"
        )

        # 创建第二个任务列表
        task_list_id2, success, error = self.agent.task_list_manager.create_task_list(
            main_goal="Test main goal 2", agent_id="test_agent"
        )
        assert success is True

        # 添加第二个任务
        task_info2 = {
            "task_name": "Test Task 2",
            "task_desc": "Test task description 2",
            "expected_output": "Test expected output 2",
            "agent_type": "sub",
        }
        self.agent.task_list_manager.add_task(
            task_list_id=task_list_id2, task_info=task_info2, agent_id="test_agent"
        )

        # 保存任务列表
        save_result = self.agent.session._save_task_lists()
        assert save_result is True

        # 验证保存的文件内容
        session_dir = os.path.join(self.temp_dir, ".jarvis", "sessions")
        platform_name = self.agent.model.platform_name()
        model_name = self.agent.model.name().replace("/", "_").replace("\\", "_")
        tasklist_file = os.path.join(
            session_dir,
            f"saved_session_{self.agent.name}_{platform_name}_{model_name}_tasklist.json",
        )

        with open(tasklist_file, "r", encoding="utf-8") as f:
            saved_data = json.load(f)

        assert len(saved_data["task_lists"]) == 2
        assert task_list_id1 in saved_data["task_lists"]
        assert task_list_id2 in saved_data["task_lists"]

        # 清空当前任务列表
        self.agent.task_list_manager.task_lists.clear()
        assert len(self.agent.task_list_manager.task_lists) == 0

        # 恢复任务列表
        restore_result = self.agent.session._restore_task_lists()
        assert restore_result is True

        # 验证两个任务列表都已恢复
        assert len(self.agent.task_list_manager.task_lists) == 2
        assert task_list_id1 in self.agent.task_list_manager.task_lists
        assert task_list_id2 in self.agent.task_list_manager.task_lists

        # 验证第一个任务列表
        restored_task_list1 = self.agent.task_list_manager.task_lists[task_list_id1]
        assert restored_task_list1.main_goal == "Test main goal 1"
        assert len(restored_task_list1.tasks) == 1

        # 验证第二个任务列表
        restored_task_list2 = self.agent.task_list_manager.task_lists[task_list_id2]
        assert restored_task_list2.main_goal == "Test main goal 2"
        assert len(restored_task_list2.tasks) == 1

    def test_restore_task_lists_with_task_dependencies(self):
        """测试恢复带依赖关系的任务列表"""
        # 创建一个任务列表
        task_list_id, success, error = self.agent.task_list_manager.create_task_list(
            main_goal="Test main goal with dependencies", agent_id="test_agent"
        )
        assert success is True

        # 添加两个任务，第二个依赖第一个
        task_info1 = {
            "task_name": "Test Task 1",
            "task_desc": "Test task description 1",
            "expected_output": "Test expected output 1",
            "agent_type": "main",
        }
        task_id1, success, error = self.agent.task_list_manager.add_task(
            task_list_id=task_list_id, task_info=task_info1, agent_id="test_agent"
        )
        assert success is True

        # 添加第二个任务，依赖第一个任务
        task_info2 = {
            "task_name": "Test Task 2",
            "task_desc": "Test task description 2",
            "expected_output": "Test expected output 2",
            "agent_type": "main",
            "dependencies": [task_id1],  # 依赖任务1
        }
        task_id2, success, error = self.agent.task_list_manager.add_task(
            task_list_id=task_list_id, task_info=task_info2, agent_id="test_agent"
        )
        assert success is True

        # 保存任务列表
        save_result = self.agent.session._save_task_lists()
        assert save_result is True

        # 验证保存的文件内容
        session_dir = os.path.join(self.temp_dir, ".jarvis", "sessions")
        platform_name = self.agent.model.platform_name()
        model_name = self.agent.model.name().replace("/", "_").replace("\\", "_")
        tasklist_file = os.path.join(
            session_dir,
            f"saved_session_{self.agent.name}_{platform_name}_{model_name}_tasklist.json",
        )

        with open(tasklist_file, "r", encoding="utf-8") as f:
            saved_data = json.load(f)

        # 验证依赖关系被正确保存
        task_list_data = saved_data["task_lists"][task_list_id]
        assert task_id1 in task_list_data["tasks"]
        assert task_id2 in task_list_data["tasks"]

        # 清空当前任务列表
        self.agent.task_list_manager.task_lists.clear()
        assert len(self.agent.task_list_manager.task_lists) == 0

        # 恢复任务列表
        restore_result = self.agent.session._restore_task_lists()
        assert restore_result is True

        # 验证恢复后依赖关系仍然存在
        restored_task_list = self.agent.task_list_manager.task_lists[task_list_id]
        assert len(restored_task_list.tasks) == 2

        restored_task2 = restored_task_list.tasks[task_id2]
        assert task_id1 in restored_task_list.tasks
        assert task_id2 in restored_task_list.tasks
        assert restored_task2.dependencies == [task_id1]

    def test_save_task_lists_with_empty_task_list(self):
        """测试保存空任务列表"""
        # 确保任务列表管理器中没有任务列表
        self.agent.task_list_manager.task_lists.clear()

        # 保存任务列表（应该成功，即使没有任务）
        save_result = self.agent.session._save_task_lists()
        assert save_result is True

        # 验证不会创建文件
        session_dir = os.path.join(self.temp_dir, ".jarvis", "sessions")
        platform_name = self.agent.model.platform_name()
        model_name = self.agent.model.name().replace("/", "_").replace("\\", "_")
        tasklist_file = os.path.join(
            session_dir,
            f"saved_session_{self.agent.name}_{platform_name}_{model_name}_tasklist.json",
        )

        # 文件不应存在，因为没有任务列表
        assert os.path.exists(tasklist_file) is False

    def test_restore_session_calls_restore_task_lists(self):
        """测试restore_session方法是否调用了_restore_task_lists"""
        # 创建一个任务列表以确保会创建保存文件
        task_list_id, success, error = self.agent.task_list_manager.create_task_list(
            main_goal="Test main goal", agent_id="test_agent"
        )
        assert success is True

        # 添加一个任务
        task_info = {
            "task_name": "Test Task",
            "task_desc": "Test task description",
            "expected_output": "Test expected output",
            "agent_type": "main",
        }
        task_id, success, error = self.agent.task_list_manager.add_task(
            task_list_id=task_list_id, task_info=task_info, agent_id="test_agent"
        )
        assert success is True

        # 保存任务列表
        save_result = self.agent.session._save_task_lists()
        assert save_result is True

        # 清空当前任务列表
        self.agent.task_list_manager.task_lists.clear()
        assert len(self.agent.task_list_manager.task_lists) == 0

        # 保存session以创建session文件
        with patch.object(self.agent.session, "save_session", return_value=True):
            session_saved = self.agent.save_session()
            assert session_saved is True

        # Mock restore_session 的依赖项，让它能完整执行
        with patch.object(
            self.agent.session,
            "_parse_session_files",
            return_value=[("fake_session.json", "20240101_120000", None)],
        ):
            with patch.object(
                self.agent.session, "_check_commit_consistency", return_value=True
            ):
                with patch.object(
                    self.agent.session.model, "restore", return_value=True
                ):
                    with patch.object(self.agent.session, "_restore_agent_state"):
                        with patch.object(
                            self.agent.session, "_restore_start_commit_info"
                        ):
                            with patch.object(
                                self.agent.session, "_restore_task_lists"
                            ) as mock_restore_task_lists:
                                # 执行restore_session
                                result = self.agent.restore_session()

                                # 验证restore_session返回True
                                assert result is True

                                # 验证_restore_task_lists被调用（现在由SessionManager调用）
                                mock_restore_task_lists.assert_called_once()
