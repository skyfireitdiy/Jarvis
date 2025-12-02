# -*- coding: utf-8 -*-
"""jarvis_platform.registry 模块单元测试"""

from unittest.mock import patch, MagicMock

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_platform.base import BasePlatform


class TestPlatformRegistry:
    """测试 PlatformRegistry 类"""

    @patch("jarvis.jarvis_platform.registry.get_data_dir")
    @patch("jarvis.jarvis_platform.registry.os.path.exists")
    @patch("jarvis.jarvis_platform.registry.os.makedirs")
    def test_get_platform_dir_existing(
        self, mock_makedirs, mock_exists, mock_get_data_dir
    ):
        """测试获取已存在的平台目录"""
        mock_get_data_dir.return_value = "/test/data"
        mock_exists.return_value = True

        result = PlatformRegistry.get_platform_dir()
        assert result == "/test/data/models"
        mock_makedirs.assert_not_called()

    @patch("jarvis.jarvis_platform.registry.get_data_dir")
    @patch("jarvis.jarvis_platform.registry.os.path.exists")
    @patch("jarvis.jarvis_platform.registry.os.makedirs")
    @patch("builtins.open")
    def test_get_platform_dir_create(
        self, mock_open, mock_makedirs, mock_exists, mock_get_data_dir
    ):
        """测试创建平台目录"""
        mock_get_data_dir.return_value = "/test/data"
        mock_exists.return_value = False
        mock_open.return_value.__enter__ = MagicMock()
        mock_open.return_value.__exit__ = MagicMock(return_value=None)

        result = PlatformRegistry.get_platform_dir()
        assert result == "/test/data/models"
        mock_makedirs.assert_called_once()

    def test_check_platform_implementation_valid(self):
        """测试检查有效的平台实现"""

        class ValidPlatform(BasePlatform):
            def chat(self, message: str):
                pass

            def name(self) -> str:
                return "test"

            def delete_chat(self) -> bool:
                return True

            def set_system_prompt(self, message: str):
                pass

            def set_model_name(self, model_name: str):
                pass

            def get_model_list(self):
                return []

            def upload_files(self, file_list):
                return True

            @classmethod
            def platform_name(cls) -> str:
                return "test_platform"

        result = PlatformRegistry.check_platform_implementation(ValidPlatform)
        assert result is True

    def test_check_platform_implementation_missing_method(self):
        """测试检查缺少方法的平台实现"""

        # 创建一个完全不实现必需方法的类
        class InvalidPlatform:
            def chat(self, message: str):
                pass

            # 缺少其他必需方法：name, delete_chat, set_system_prompt, set_model_name, get_model_list, upload_files

        result = PlatformRegistry.check_platform_implementation(InvalidPlatform)
        assert result is False

    def test_check_platform_implementation_wrong_params(self):
        """测试检查参数不匹配的平台实现"""

        class WrongParamsPlatform(BasePlatform):
            def chat(self, message: str, extra_param: str):  # 参数不匹配
                pass

            def name(self) -> str:
                return "test"

            def delete_chat(self) -> bool:
                return True

            def set_system_prompt(self, message: str):
                pass

            def set_model_name(self, model_name: str):
                pass

            def get_model_list(self):
                return []

            def upload_files(self, file_list):
                return True

            @classmethod
            def platform_name(cls) -> str:
                return "test_platform"

        result = PlatformRegistry.check_platform_implementation(WrongParamsPlatform)
        assert result is False

    def test_check_platform_implementation_non_callable(self):
        """测试检查非可调用方法的平台实现"""

        class NonCallablePlatform(BasePlatform):
            chat = "not a method"  # 不是可调用对象

            def name(self) -> str:
                return "test"

            def delete_chat(self) -> bool:
                return True

            def set_system_prompt(self, message: str):
                pass

            def set_model_name(self, model_name: str):
                pass

            def get_model_list(self):
                return []

            def upload_files(self, file_list):
                return True

            @classmethod
            def platform_name(cls) -> str:
                return "test_platform"

        result = PlatformRegistry.check_platform_implementation(NonCallablePlatform)
        assert result is False
