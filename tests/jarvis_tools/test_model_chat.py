# -*- coding: utf-8 -*-
"""model_chat 工具测试。

守护目标（对应 NLSpec .jarvis/.df/specs/model-chat.md）：
1. 正常路径：传入 {message, system_prompt, model_group} 返回
   {success: true, content: <模型回复>, model_group: <组名>}。
2. 参数校验：message 缺失/非字符串 → success:false 且 error 含 "message is required"；
   model_group 非法 → success:false 且 error 含合法取值。
3. 错误语义显式：平台创建失败（create_platform 返回 None）、模型调用异常、
   返回空结果，均返回 success:false 并附可读错误信息，不抛异常穿透。
4. 无状态：调用前后不触发 dialogue_recorder 副作用（record_user_message /
   record_assistant_message 不被调用）。
5. 输出抑制：调用期间对平台调用 set_suppress_output(True)。
6. system_prompt 可选：传入时设置到平台，缺省不设置。
7. 工具注册契约：name 等于模块名 stem（model_chat），实现 check()/execute()。

隔离：mock 平台层（PlatformRegistry.create_platform 与 BasePlatform.complete），
不发起真实网络请求。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.jarvis_tools.model_chat import ModelChatTool

VALID_GROUPS = ["normal", "cheap", "smart", "eval"]


class FakePlatform:
    """模拟 BasePlatform 的最小实现。"""

    def __init__(self, reply="hello from model", system_prompt_set=None):
        self.reply = reply
        self.suppress_output = False
        self.system_prompt_set = system_prompt_set
        self.delete_chat_called = False

    def set_suppress_output(self, suppress: bool):
        self.suppress_output = suppress

    def set_system_prompt(self, message: str):
        self.system_prompt_set = message

    def complete(self, prompt: str, **kwargs) -> str:
        return self.reply

    def delete_chat(self) -> bool:
        self.delete_chat_called = True
        return True


@pytest.fixture
def tool():
    return ModelChatTool()


@pytest.fixture
def fake_platform():
    return FakePlatform()


def _patch_registry(monkeypatch, platform):
    """把 PlatformRegistry.create_platform 替换为返回指定平台的桩。"""
    import jarvis.jarvis_tools.model_chat as module

    monkeypatch.setattr(
        module.PlatformRegistry,
        "create_platform",
        lambda self, platform_type="normal", silent=False: platform,
    )


# ---------------- 正常路径 ----------------


def test_execute_success_returns_content(tool, monkeypatch, fake_platform):
    """正常调用返回 success:true + content + model_group。"""
    _patch_registry(monkeypatch, fake_platform)
    result = tool.execute(message="你好", model_group="normal")
    assert result["success"] is True
    assert result["content"] == "hello from model"
    assert result["model_group"] == "normal"


def test_execute_success_default_model_group(tool, monkeypatch, fake_platform):
    """缺省 model_group 为 normal。"""
    _patch_registry(monkeypatch, fake_platform)
    result = tool.execute(message="hi")
    assert result["success"] is True
    assert result["model_group"] == "normal"


@pytest.mark.parametrize("group", VALID_GROUPS)
def test_execute_success_all_groups(tool, monkeypatch, fake_platform, group):
    """四种合法模型组均可调用。"""
    _patch_registry(monkeypatch, fake_platform)
    result = tool.execute(message="hi", model_group=group)
    assert result["success"] is True
    assert result["model_group"] == group


def test_execute_sets_suppress_output(tool, monkeypatch, fake_platform):
    """调用期间必须抑制平台输出。"""
    _patch_registry(monkeypatch, fake_platform)
    tool.execute(message="hi")
    assert fake_platform.suppress_output is True


def test_execute_sets_system_prompt(tool, monkeypatch, fake_platform):
    """传入 system_prompt 时设置到平台。"""
    _patch_registry(monkeypatch, fake_platform)
    tool.execute(message="hi", system_prompt="你是助手")
    assert fake_platform.system_prompt_set == "你是助手"


def test_execute_without_system_prompt(tool, monkeypatch, fake_platform):
    """不传 system_prompt 时平台不设置系统提示。"""
    _patch_registry(monkeypatch, fake_platform)
    tool.execute(message="hi")
    assert fake_platform.system_prompt_set is None


def test_execute_passes_message_to_complete(tool, monkeypatch, fake_platform):
    """message 原样传给平台 complete。"""
    captured = {}

    class CapturingPlatform(FakePlatform):
        def complete(self, prompt: str, **kwargs) -> str:
            captured["prompt"] = prompt
            return self.reply

    _patch_registry(monkeypatch, CapturingPlatform())
    tool.execute(message="请解释量子计算")
    assert captured["prompt"] == "请解释量子计算"


# ---------------- 参数校验 ----------------


def test_execute_requires_message(tool, monkeypatch, fake_platform):
    """message 缺失返回 success:false 且 error 含 message is required。"""
    _patch_registry(monkeypatch, fake_platform)
    result = tool.execute()
    assert result["success"] is False
    assert "message is required" in result["error"]
    assert result["content"] == ""


def test_execute_message_non_string(tool, monkeypatch, fake_platform):
    """message 非字符串返回 success:false。"""
    _patch_registry(monkeypatch, fake_platform)
    result = tool.execute(message=12345)
    assert result["success"] is False
    assert "message is required" in result["error"]


@pytest.mark.parametrize("bad_group", ["foo", "", "NORMAL", "normal ", None])
def test_execute_invalid_model_group(tool, monkeypatch, fake_platform, bad_group):
    """非法 model_group 返回 success:false 且 error 含合法取值。"""
    _patch_registry(monkeypatch, fake_platform)
    result = tool.execute(message="hi", model_group=bad_group)
    assert result["success"] is False
    assert "normal" in result["error"]
    assert "cheap" in result["error"]
    assert "smart" in result["error"]
    assert "eval" in result["error"]


# ---------------- 错误语义 ----------------


def test_execute_platform_create_fails(tool, monkeypatch):
    """create_platform 返回 None 时返回 success:false。"""
    import jarvis.jarvis_tools.model_chat as module

    monkeypatch.setattr(
        module.PlatformRegistry,
        "create_platform",
        lambda self, platform_type="normal", silent=False: None,
    )
    result = tool.execute(message="hi")
    assert result["success"] is False
    assert result["content"] == ""
    assert result["error"]


def test_execute_complete_raises(tool, monkeypatch, fake_platform):
    """complete 抛异常时返回 success:false 且附异常信息。"""

    class RaisingPlatform(FakePlatform):
        def complete(self, prompt: str, **kwargs) -> str:
            raise RuntimeError("boom: api down")

    _patch_registry(monkeypatch, RaisingPlatform())
    result = tool.execute(message="hi")
    assert result["success"] is False
    assert "boom" in result["error"]


def test_execute_complete_empty_result(tool, monkeypatch, fake_platform):
    """complete 返回空字符串时返回 success:false。"""

    class EmptyPlatform(FakePlatform):
        def complete(self, prompt: str, **kwargs) -> str:
            return ""

    _patch_registry(monkeypatch, EmptyPlatform())
    result = tool.execute(message="hi")
    assert result["success"] is False
    assert result["error"]


def test_execute_complete_whitespace_result(tool, monkeypatch, fake_platform):
    """complete 返回纯空白时视为空结果返回 success:false。"""

    class WhitespacePlatform(FakePlatform):
        def complete(self, prompt: str, **kwargs) -> str:
            return "   \n  "

    _patch_registry(monkeypatch, WhitespacePlatform())
    result = tool.execute(message="hi")
    assert result["success"] is False
    assert result["error"]


# ---------------- 无状态 / 副作用 ----------------


def test_execute_does_not_trigger_dialogue_recorder(tool, monkeypatch, fake_platform):
    """调用不触发 dialogue_recorder 副作用（record_user_message/record_assistant_message）。"""
    import jarvis.jarvis_utils.dialogue_recorder as recorder_module

    _patch_registry(monkeypatch, fake_platform)
    calls = {"user": 0, "assistant": 0}

    def fake_record_user(msg):
        calls["user"] += 1

    def fake_record_assistant(msg):
        calls["assistant"] += 1

    monkeypatch.setattr(recorder_module, "record_user_message", fake_record_user)
    monkeypatch.setattr(recorder_module, "record_assistant_message", fake_record_assistant)

    result = tool.execute(message="hi")
    assert result["success"] is True
    assert calls["user"] == 0
    assert calls["assistant"] == 0


# ---------------- 工具注册契约 ----------------


def test_tool_name_matches_module():
    """工具类 name 必须等于模块名 stem（registry 的 item.name == module_name 契约）。"""
    assert ModelChatTool.name == "model_chat"


def test_tool_has_check_and_execute():
    """工具必须实现 check()/execute()。"""
    assert callable(ModelChatTool.check)
    assert callable(ModelChatTool().execute)


def test_check_returns_true():
    """check() 返回 True（模型直聊工具始终可用）。"""
    assert ModelChatTool.check() is True
