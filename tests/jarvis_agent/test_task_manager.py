# -*- coding: utf-8 -*-
"""TaskManager 单元测试（load_tasks 与 select_task）"""
import os
from unittest.mock import Mock
import pytest

from jarvis.jarvis_agent.task_manager import TaskManager


class TestTaskManagerLoadTasks:
    def test_load_tasks_merges_and_overrides(self, tmp_path, monkeypatch):
        # 模拟 data_dir
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "jarvis.jarvis_agent.task_manager.get_data_dir", lambda: str(data_dir)
        )

        # 写入 data_dir/pre-command
        (data_dir / "pre-command").write_text(
            "TaskA: descA\nTaskB: descB\n", encoding="utf-8"
        )

        # 在当前目录下创建 .jarvis/pre-command
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / ".jarvis").mkdir()
        (proj / ".jarvis" / "pre-command").write_text(
            "TaskB: descB_local\nTaskC: descC\n", encoding="utf-8"
        )

        # 切到项目目录
        cwd = os.getcwd()
        os.chdir(proj)
        try:
            tasks = TaskManager.load_tasks()
        finally:
            os.chdir(cwd)

        # 合并且本地覆盖 data_dir 中的同名任务
        assert tasks == {
            "TaskA": "descA",
            "TaskB": "descB_local",
            "TaskC": "descC",
        }

    def test_load_tasks_invalid_yaml_graceful(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "jarvis.jarvis_agent.task_manager.get_data_dir", lambda: str(data_dir)
        )

        # data_dir/pre-command 写入非法 YAML
        (data_dir / "pre-command").write_text(
            "This is: [invalid: yaml", encoding="utf-8"
        )

        # 本地有效
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / ".jarvis").mkdir()
        (proj / ".jarvis" / "pre-command").write_text(
            "TaskX: X\nTaskY: Y\n", encoding="utf-8"
        )

        cwd = os.getcwd()
        os.chdir(proj)
        try:
            tasks = TaskManager.load_tasks()
        finally:
            os.chdir(cwd)

        assert tasks == {"TaskX": "X", "TaskY": "Y"}


class TestTaskManagerSelectTask:
    def test_select_task_empty_tasks(self):
        assert TaskManager.select_task({}) == ""

    def test_select_task_choose_first_without_additional(self, monkeypatch):
        tasks = {"T1": "do 1", "T2": "do 2"}

        # patch prompt, user_confirm
        monkeypatch.setattr(
            "jarvis.jarvis_agent.task_manager.prompt", lambda msg="": "1"
        )
        monkeypatch.setattr(
            "jarvis.jarvis_agent.task_manager.user_confirm",
            lambda msg, default=False: False,
        )

        result = TaskManager.select_task(tasks)
        assert result == "do 1"

    def test_select_task_with_additional_info(self, monkeypatch):
        tasks = {"T1": "base", "T2": "ignored"}

        # 选择 1，要求补充信息
        monkeypatch.setattr(
            "jarvis.jarvis_agent.task_manager.prompt", lambda msg="": "1"
        )
        monkeypatch.setattr(
            "jarvis.jarvis_agent.task_manager.user_confirm",
            lambda msg, default=False: True,
        )
        monkeypatch.setattr(
            "jarvis.jarvis_agent.task_manager.get_multiline_input",
            lambda msg="": "More details",
        )

        result = TaskManager.select_task(tasks)
        assert result == "base\n\n补充信息:\nMore details"

    def test_select_task_invalid_then_zero(self, monkeypatch):
        tasks = {"T1": "one"}

        inputs = iter(["abc", "0"])
        monkeypatch.setattr(
            "jarvis.jarvis_agent.task_manager.prompt", lambda msg="": next(inputs)
        )

        # 避免实际输出
        class DummyPretty:
            @staticmethod
            def print(*args, **kwargs):
                pass

        monkeypatch.setattr(
            "jarvis.jarvis_agent.task_manager.PrettyOutput", DummyPretty
        )

        result = TaskManager.select_task(tasks)
        assert result == ""

    def test_select_task_out_of_range_then_valid(self, monkeypatch):
        tasks = {"T1": "one", "T2": "two"}

        inputs = iter(["5", "2"])
        monkeypatch.setattr(
            "jarvis.jarvis_agent.task_manager.prompt", lambda msg="": next(inputs)
        )

        class DummyPretty:
            @staticmethod
            def print(*args, **kwargs):
                pass

        monkeypatch.setattr(
            "jarvis.jarvis_agent.task_manager.PrettyOutput", DummyPretty
        )

        # 不追加信息
        monkeypatch.setattr(
            "jarvis.jarvis_agent.task_manager.user_confirm",
            lambda msg, default=False: False,
        )

        result = TaskManager.select_task(tasks)
        assert result == "two"
