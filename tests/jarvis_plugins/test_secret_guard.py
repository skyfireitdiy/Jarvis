# -*- coding: utf-8 -*-
"""secret-guard 内置插件回调单元测试。

直接 import 回调函数测试各场景：
- 发送前脱敏（str 与多模态 List[ContentBlock]）
- 响应还原（含未知占位符保留）
- 工具输出二次脱敏（复用已有占位符，不新建）
- 同一敏感值复用同一占位符
- 会话持久化往返（映射随 agent 状态保存/恢复）

敏感样本以「片段拼接」方式在运行时构造，避免源码中出现完整敏感字面量
被 pre-commit 钩子/分享闸门误拦。
"""

import sys
from types import SimpleNamespace
from typing import Any

from jarvis.jarvis_agent.share_secret_scanner import extract_secrets

# ---------------------------------------------------------------------------
# 运行时构造的测试样本
# ---------------------------------------------------------------------------
FAKE_SECRET = "".join(["Super", "Secret", "1234567890", "abc"])  # 通用长口令样本
FAKE_GH_TOKEN = "".join(["ghp_", "ABCDEFGH", "IJKLMNOP", "QRSTUVWX", "YZabcdefghij"])


def _make_agent() -> SimpleNamespace:
    """构造一个带 secret_guard_mapping 的 mock agent。"""
    return SimpleNamespace(secret_guard_mapping={})


def _load_cb(name: str) -> Any:
    """从内置插件目录加载回调模块。"""
    import importlib.util
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    path = root / "builtin" / "plugins" / "secret-guard" / "callbacks" / name
    spec = importlib.util.spec_from_file_location(
        f"test_secret_guard_{name[:-3]}", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载回调模块: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


BEFORE_CB = _load_cb("before_model_call_cb.py")
AFTER_CB = _load_cb("after_model_call_cb.py")
SANITIZER_CB = _load_cb("tool_output_sanitizer_cb.py")


class TestBeforeModelCall:
    """发送前脱敏。"""

    def test_str_message_sanitized(self):
        agent = _make_agent()
        msg = f'password = "{FAKE_SECRET}"'
        out = BEFORE_CB.before_model_call_cb(agent, msg)
        assert FAKE_SECRET not in out
        assert "⟦SECRET_" in out
        # 映射已建立
        assert FAKE_SECRET in agent.secret_guard_mapping.values()

    def test_same_secret_reuses_placeholder(self):
        agent = _make_agent()
        msg1 = f'password = "{FAKE_SECRET}"'
        msg2 = f'again password = "{FAKE_SECRET}"'
        out1 = BEFORE_CB.before_model_call_cb(agent, msg1)
        out2 = BEFORE_CB.before_model_call_cb(agent, msg2)
        # 两次脱敏使用同一占位符
        placeholders = [
            p for p, real in agent.secret_guard_mapping.items() if real == FAKE_SECRET
        ]
        assert len(placeholders) == 1
        assert placeholders[0] in out1
        assert placeholders[0] in out2

    def test_multimodal_only_text_blocks(self):
        agent = _make_agent()
        msg = [
            {"type": "text", "text": f'password = "{FAKE_SECRET}"'},
            {"type": "image_url", "image_url": "https://example.com/a.png"},
        ]
        out = BEFORE_CB.before_model_call_cb(agent, msg)
        assert out[0]["type"] == "text"
        assert FAKE_SECRET not in out[0]["text"]
        assert "⟦SECRET_" in out[0]["text"]
        # 图片块原样保留
        assert out[1] == {"type": "image_url", "image_url": "https://example.com/a.png"}

    def test_plain_text_unchanged(self):
        agent = _make_agent()
        out = BEFORE_CB.before_model_call_cb(agent, "你好，普通文本")
        assert out == "你好，普通文本"


class TestAfterModelCall:
    """响应还原。"""

    def test_placeholder_restored(self):
        agent = _make_agent()
        msg = f'password = "{FAKE_SECRET}"'
        sanitized = BEFORE_CB.before_model_call_cb(agent, msg)
        # 模型原样回显占位符
        response = f"好的，我看到了 {sanitized}"
        out = AFTER_CB.after_model_call_cb(agent, response)
        assert FAKE_SECRET in out
        assert "⟦SECRET_" not in out

    def test_unknown_placeholder_kept(self):
        agent = _make_agent()
        response = "未知占位符 ⟦SECRET_abcdef⟧ 保留"
        out = AFTER_CB.after_model_call_cb(agent, response)
        assert "⟦SECRET_abcdef⟧" in out

    def test_plain_response_unchanged(self):
        agent = _make_agent()
        out = AFTER_CB.after_model_call_cb(agent, "没有敏感信息")
        assert out == "没有敏感信息"


class TestToolOutputSanitizer:
    """工具输出二次脱敏。"""

    def test_secret_replaced_with_existing_placeholder(self):
        agent = _make_agent()
        BEFORE_CB.before_model_call_cb(agent, f'password = "{FAKE_SECRET}"')
        placeholder = next(
            p for p, real in agent.secret_guard_mapping.items() if real == FAKE_SECRET
        )
        output = f'读取到配置 password = "{FAKE_SECRET}"，请处理'
        out = SANITIZER_CB.tool_output_sanitizer_cb(agent, output)
        assert FAKE_SECRET not in out
        assert placeholder in out

    def test_unknown_secret_not_replaced(self):
        agent = _make_agent()
        # 映射为空，工具输出中的敏感值不替换（无法安全还原）
        output = f'password = "{FAKE_GH_TOKEN}"'
        out = SANITIZER_CB.tool_output_sanitizer_cb(agent, output)
        assert out == output

    def test_no_mapping_returns_unchanged(self):
        agent = SimpleNamespace()  # 无 secret_guard_mapping 属性
        output = "普通输出"
        out = SANITIZER_CB.tool_output_sanitizer_cb(agent, output)
        assert out == "普通输出"


class TestSessionPersistence:
    """会话持久化往返：映射随 agent 状态保存/恢复。"""

    def test_mapping_roundtrip(self):
        import json

        agent = _make_agent()
        BEFORE_CB.before_model_call_cb(agent, f'password = "{FAKE_SECRET}"')
        # 模拟 _build_agent_state 序列化
        state = {"secret_guard_mapping": dict(agent.secret_guard_mapping)}
        serialized = json.dumps(state)
        # 模拟 _restore_agent_state 反序列化
        restored = json.loads(serialized)
        new_agent = _make_agent()
        new_agent.secret_guard_mapping = restored["secret_guard_mapping"]
        # 恢复后还原仍可用
        placeholder = next(
            p for p, real in new_agent.secret_guard_mapping.items() if real == FAKE_SECRET
        )
        out = AFTER_CB.after_model_call_cb(new_agent, f"口令是 {placeholder}")
        assert FAKE_SECRET in out


class TestExtractSecretsIntegration:
    """与 share_secret_scanner.extract_secrets 的集成一致性。"""

    def test_extract_detects_assignment_secret(self):
        assert FAKE_SECRET in extract_secrets(f'password = "{FAKE_SECRET}"')
