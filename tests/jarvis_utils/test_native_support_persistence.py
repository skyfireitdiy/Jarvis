# -*- coding: utf-8 -*-
"""模型原生工具调用支持记录的持久化与「不再降级」行为测试。"""

import os

import pytest

from jarvis.jarvis_utils import config as cfg


@pytest.fixture()
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    return tmp_path


def test_unknown_model_not_supported(isolated_data_dir):
    assert cfg.is_model_native_supported("some-model") is False


def test_mark_then_query(isolated_data_dir):
    cfg.mark_model_native_supported("some-model")
    assert cfg.is_model_native_supported("some-model") is True
    # 记录写入数据目录下的文件
    assert os.path.exists(
        os.path.join(str(isolated_data_dir), "native_tool_support.json")
    )


def test_mark_is_idempotent_and_preserves_others(isolated_data_dir):
    cfg.mark_model_native_supported("m1")
    cfg.mark_model_native_supported("m2")
    cfg.mark_model_native_supported("m1")
    assert cfg.is_model_native_supported("m1") is True
    assert cfg.is_model_native_supported("m2") is True


def test_empty_model_name_ignored(isolated_data_dir):
    cfg.mark_model_native_supported("")
    assert cfg.is_model_native_supported("") is False


def test_corrupted_file_treated_as_unsupported(isolated_data_dir):
    path = os.path.join(str(isolated_data_dir), "native_tool_support.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not valid json")
    assert cfg.is_model_native_supported("m1") is False
    # 损坏后仍能重新写入
    cfg.mark_model_native_supported("m1")
    assert cfg.is_model_native_supported("m1") is True
