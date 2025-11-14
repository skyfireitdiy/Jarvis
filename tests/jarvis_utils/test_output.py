# -*- coding: utf-8 -*-
"""jarvis_utils.output 模块单元测试"""


from jarvis.jarvis_utils.output import OutputType, OutputEvent


class TestOutputType:
    """测试 OutputType 枚举"""

    def test_enum_values(self):
        """测试枚举值"""
        assert OutputType.SYSTEM.value == "SYSTEM"
        assert OutputType.CODE.value == "CODE"
        assert OutputType.RESULT.value == "RESULT"
        assert OutputType.ERROR.value == "ERROR"
        assert OutputType.INFO.value == "INFO"
        assert OutputType.PLANNING.value == "PLANNING"
        assert OutputType.PROGRESS.value == "PROGRESS"
        assert OutputType.SUCCESS.value == "SUCCESS"
        assert OutputType.WARNING.value == "WARNING"
        assert OutputType.DEBUG.value == "DEBUG"
        assert OutputType.USER.value == "USER"
        assert OutputType.TOOL.value == "TOOL"

    def test_enum_comparison(self):
        """测试枚举比较"""
        assert OutputType.SYSTEM.value == "SYSTEM"
        assert OutputType.ERROR.value != "SUCCESS"

    def test_enum_membership(self):
        """测试枚举成员"""
        assert "SYSTEM" in [e.value for e in OutputType]
        assert "ERROR" in [e.value for e in OutputType]


class TestOutputEvent:
    """测试 OutputEvent 数据类"""

    def test_basic_creation(self):
        """测试基本创建"""
        event = OutputEvent(
            text="Test message",
            output_type=OutputType.INFO
        )
        assert event.text == "Test message"
        assert event.output_type == OutputType.INFO
        assert event.timestamp is True  # 默认值
        assert event.lang is None
        assert event.traceback is False
        assert event.section is None
        assert event.context is None

    def test_full_creation(self):
        """测试完整创建"""
        event = OutputEvent(
            text="Test message",
            output_type=OutputType.ERROR,
            timestamp=False,
            lang="python",
            traceback=True,
            section="Test Section",
            context={"key": "value"}
        )
        assert event.text == "Test message"
        assert event.output_type == OutputType.ERROR
        assert event.timestamp is False
        assert event.lang == "python"
        assert event.traceback is True
        assert event.section == "Test Section"
        assert event.context == {"key": "value"}

    def test_different_output_types(self):
        """测试不同的输出类型"""
        for output_type in OutputType:
            event = OutputEvent(
                text=f"Message for {output_type.value}",
                output_type=output_type
            )
            assert event.output_type == output_type
            assert event.text == f"Message for {output_type.value}"

    def test_empty_text(self):
        """测试空文本"""
        event = OutputEvent(
            text="",
            output_type=OutputType.INFO
        )
        assert event.text == ""
        assert event.output_type == OutputType.INFO

