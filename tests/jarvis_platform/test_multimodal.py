"""
多模态功能测试

测试Platform模块的多模态支持功能
"""

import pytest
from typing import Dict, List, Tuple, Union


from jarvis.jarvis_platform.content_types import (
    TextContent,
    ImageURLContent,
    ContentBlock,
)
from jarvis.jarvis_platform.content_processor import ContentProcessor
from jarvis.jarvis_platform.base import BasePlatform


class TestContentTypes:
    """测试内容类型定义"""

    def test_text_content(self):
        """测试文本内容类型"""
        content: TextContent = {"type": "text", "text": "Hello, world!"}
        assert content["type"] == "text"
        assert content["text"] == "Hello, world!"

    def test_image_content(self):
        """测试图片内容类型"""
        content: ImageURLContent = {
            "type": "image_url",
            "image_url": "https://example.com/image.jpg",
            "detail": "high",
        }
        assert content["type"] == "image_url"
        assert content["image_url"] == "https://example.com/image.jpg"
        assert content["detail"] == "high"


class TestContentProcessor:
    """测试内容处理器"""

    def setup_method(self):
        """测试前准备"""
        self.processor = ContentProcessor()

    def test_process_string_input(self):
        """测试处理字符串输入"""
        result = self.processor.process_message("Hello, world!")
        assert len(result) == 1
        assert result[0]["type"] == "text"
        assert result[0]["text"] == "Hello, world!"

    def test_process_list_input(self):
        """测试处理列表输入"""
        content_list: List[ContentBlock] = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "world!"},
        ]
        result = self.processor.process_message(content_list)
        assert len(result) == 2
        # 使用类型断言来处理联合类型
        assert result[0]["type"] == "text"
        assert result[0]["text"] == "Hello"
        assert result[1]["type"] == "text"
        assert result[1]["text"] == "world!"

    def test_validate_text_content(self):
        """测试验证文本内容"""
        content: TextContent = {"type": "text", "text": "Hello"}
        assert self.processor.validate_content(content) is True

    def test_validate_image_content(self):
        """测试验证图片内容"""
        content: ImageURLContent = {
            "type": "image_url",
            "image_url": "https://example.com/image.jpg",
        }
        assert self.processor.validate_content(content) is True

    def test_validate_invalid_content(self):
        """测试验证无效内容"""
        content = {"type": "invalid", "data": "test"}
        with pytest.raises(ValueError):
            self.processor.validate_content(content)  # type: ignore


class TestBasePlatformMultimodal:
    """测试BasePlatform多模态支持"""

    def setup_method(self):
        """测试前准备"""

        # 创建一个具体的BasePlatform子类用于测试
        class TestPlatform(BasePlatform):
            def chat(self, message: Union[str, List[ContentBlock]]):
                # 处理多模态消息
                from jarvis.jarvis_platform.content_processor import ContentProcessor

                processed = ContentProcessor.process_message(message)
                # 返回处理后的内容
                yield "content", f"Processed: {len(processed)} content blocks"

            def name(self) -> str:
                return "TestPlatform"

            @classmethod
            def platform_name(cls) -> str:
                return "test"

            def delete_chat(self) -> bool:
                return True

            def set_messages(self, messages: List[Dict[str, str]]) -> None:
                pass

            def get_messages(self) -> List[Dict[str, str]]:
                return []

            def set_model_name(self, model_name: str):
                pass

            def set_system_prompt(self, message: str):
                pass

            def get_model_list(self) -> List[Tuple[str, str]]:
                return []

            @classmethod
            def get_required_env_keys(cls) -> List[str]:
                return []

            def trim_messages(self) -> bool:
                return True

        self.platform = TestPlatform()

    def test_chat_with_string(self):
        """测试使用字符串调用chat方法"""
        result = list(self.platform.chat("Hello, world!"))
        assert len(result) == 1
        assert result[0][0] == "content"
        assert "Processed: 1 content blocks" in result[0][1]

    def test_chat_with_multimodal(self):
        """测试使用多模态内容调用chat方法"""
        content_list: List[ContentBlock] = [
            {"type": "text", "text": "Hello"},
            {"type": "image_url", "image_url": "https://example.com/image.jpg"},
        ]
        result = list(self.platform.chat(content_list))
        assert len(result) == 1
        assert result[0][0] == "content"
        assert "Processed: 2 content blocks" in result[0][1]

    def test_process_multimodal_content(self):
        """测试处理多模态内容"""
        from jarvis.jarvis_platform.content_processor import ContentProcessor

        # 测试字符串输入
        result1 = ContentProcessor.process_message("Hello")
        assert len(result1) == 1
        assert result1[0]["type"] == "text"

        # 测试列表输入
        content_list: List[ContentBlock] = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "world!"},
        ]
        result2 = ContentProcessor.process_message(content_list)
        assert len(result2) == 2
        assert result2[0]["type"] == "text"
        assert result2[0]["text"] == "Hello"
        assert result2[1]["type"] == "text"
        assert result2[1]["text"] == "world!"

    def test_validate_content(self):
        """测试验证内容"""
        from jarvis.jarvis_platform.content_processor import ContentProcessor

        # 测试有效内容
        valid_content: TextContent = {"type": "text", "text": "Hello"}
        assert ContentProcessor.validate_content(valid_content) is True

        # 测试无效内容
        invalid_content = {"type": "invalid", "data": "test"}
        with pytest.raises(ValueError):
            ContentProcessor.validate_content(invalid_content)  # type: ignore


class TestMultimodalIntegration:
    """测试多模态集成功能"""

    def test_mixed_content_processing(self):
        """测试混合内容处理"""
        processor = ContentProcessor()

        # 创建混合内容
        mixed_content: List[ContentBlock] = [
            {"type": "text", "text": "Look at this image:"},
            {
                "type": "image_url",
                "image_url": "https://example.com/image.jpg",
                "detail": "high",
            },
            {"type": "text", "text": "And look at this image again:"},
            {
                "type": "image_url",
                "image_url": "https://example.com/image2.jpg",
            },
        ]

        # 处理混合内容
        result = processor.process_message(mixed_content)

        # 验证结果
        assert len(result) == 4
        assert result[0]["type"] == "text"
        assert result[0]["text"] == "Look at this image:"
        assert result[1]["type"] == "image_url"
        assert result[1]["image_url"] == "https://example.com/image.jpg"
        assert result[2]["type"] == "text"
        assert result[2]["text"] == "And look at this image again:"
        assert result[3]["type"] == "image_url"
        assert result[3]["image_url"] == "https://example.com/image2.jpg"

    def test_backward_compatibility(self):
        """测试向后兼容性"""
        processor = ContentProcessor()

        # 测试纯文本消息
        text_result = processor.process_message("Hello, world!")
        assert len(text_result) == 1
        assert text_result[0]["type"] == "text"
        assert text_result[0]["text"] == "Hello, world!"

        # 测试空字符串
        empty_result = processor.process_message("")
        assert len(empty_result) == 1
        assert empty_result[0]["type"] == "text"
        assert empty_result[0]["text"] == ""

    def test_content_validation(self):
        """测试内容验证"""
        processor = ContentProcessor()

        # 测试有效内容
        valid_contents = [
            {"type": "text", "text": "Hello"},
            {"type": "image_url", "image_url": "https://example.com/image.jpg"},
        ]

        for content in valid_contents:
            assert processor.validate_content(content) is True  # type: ignore

        # 测试无效内容
        invalid_contents = [
            {"type": "invalid"},
            {"type": "text"},  # 缺少text字段
            {"type": "image_url"},  # 缺少image_url字段
        ]

        for content in invalid_contents:
            with pytest.raises(ValueError):
                processor.validate_content(content)  # type: ignore


class TestMultimodalConfig:
    """测试多模态配置项"""

    def test_supports_multimodal_default(self):
        """测试 supports_multimodal 默认值为 False"""
        from jarvis.jarvis_platform.base import BasePlatform
        from unittest.mock import patch

        # 模拟 get_llm_config 返回空字典
        with patch("jarvis.jarvis_platform.base.get_llm_config", return_value={}):
            # 创建一个具体的子类来测试
            class TestPlatform(BasePlatform):
                def chat(self, message):
                    yield ("content", "test")

                def delete_chat(self):
                    pass

                def get_messages(self):
                    return []

                def get_model_list(self):
                    return []

                def get_required_env_keys(self):
                    return []

                def name(self):
                    return "test"

                def platform_name(self):
                    return "test"

                def set_messages(self, messages):
                    pass

                def set_model_name(self, model_name):
                    pass

                def set_system_prompt(self, message):
                    pass

                def trim_messages(self) -> bool:
                    return True

            platform = TestPlatform()
            assert platform.supports_multimodal() is False

    def test_supports_multimodal_enabled(self):
        """测试 supports_multimodal 设置为 True"""
        from jarvis.jarvis_platform.base import BasePlatform
        from unittest.mock import patch

        # 模拟 get_llm_config 返回 supports_multimodal: True
        with patch(
            "jarvis.jarvis_platform.base.get_llm_config",
            return_value={"supports_multimodal": True},
        ):

            class TestPlatform(BasePlatform):
                def chat(self, message):
                    yield ("content", "test")

                def delete_chat(self):
                    pass

                def get_messages(self):
                    return []

                def get_model_list(self):
                    return []

                def get_required_env_keys(self):
                    return []

                def name(self):
                    return "test"

                def platform_name(self):
                    return "test"

                def set_messages(self, messages):
                    pass

                def set_model_name(self, model_name):
                    pass

                def set_system_prompt(self, message):
                    pass

                def trim_messages(self) -> bool:
                    return True

            platform = TestPlatform()
            assert platform.supports_multimodal() is True

    def test_openai_rejects_multimodal_if_not_supported(self):
        """测试 OpenAIModel 在不支持多模态时拒绝多模态输入"""
        from jarvis.jarvis_platform.openai import OpenAIModel
        from jarvis.jarvis_platform.content_types import (
            TextContent,
            ImageURLContent,
            ContentBlock,
        )
        from unittest.mock import patch, MagicMock

        # 模拟 get_llm_config 返回 supports_multimodal: False
        with patch(
            "jarvis.jarvis_platform.base.get_llm_config",
            return_value={"supports_multimodal": False},
        ):
            # 模拟 OpenAI client
            mock_client = MagicMock()
            with patch(
                "jarvis.jarvis_platform.openai.OpenAI", return_value=mock_client
            ):
                platform = OpenAIModel()

                # 构造多模态消息
                text_content: TextContent = {
                    "type": "text",
                    "text": "What is in this image?",
                }
                image_content: ImageURLContent = {
                    "type": "image_url",
                    "image_url": "https://example.com/image.jpg",
                }
                multimodal_message: List[ContentBlock] = [text_content, image_content]

                # 验证抛出 Exception
                with pytest.raises(Exception, match="当前模型不支持多模态输入"):
                    # 触发 chat 方法，因为是生成器，需要迭代
                    for _ in platform.chat(multimodal_message):
                        pass

    def test_claude_rejects_multimodal_if_not_supported(self):
        """测试 ClaudeModel 在不支持多模态时拒绝多模态输入"""
        from jarvis.jarvis_platform.claude import ClaudeModel
        from jarvis.jarvis_platform.content_types import (
            TextContent,
            ImageURLContent,
            ContentBlock,
        )
        from unittest.mock import patch, MagicMock

        # 模拟 get_llm_config 返回 supports_multimodal: False
        with patch(
            "jarvis.jarvis_platform.base.get_llm_config",
            return_value={"supports_multimodal": False},
        ):
            # 模拟 Anthropic client
            mock_client = MagicMock()
            with patch(
                "jarvis.jarvis_platform.claude.Anthropic", return_value=mock_client
            ):
                platform = ClaudeModel()

                # 构造多模态消息
                text_content: TextContent = {
                    "type": "text",
                    "text": "What is in this image?",
                }
                image_content: ImageURLContent = {
                    "type": "image_url",
                    "image_url": "https://example.com/image.jpg",
                }
                multimodal_message: List[ContentBlock] = [text_content, image_content]

                # 验证抛出 Exception
                with pytest.raises(Exception, match="当前模型不支持多模态输入"):
                    for _ in platform.chat(multimodal_message):
                        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
