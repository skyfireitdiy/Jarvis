# -*- coding: utf-8 -*-
"""jarvis_utils.methodology 模块单元测试"""

from unittest.mock import MagicMock, patch

from jarvis.jarvis_utils.methodology import (
    _get_methodology_directory,
    _select_methodologies_with_normal_model,
    load_methodology,
)


class TestGetMethodologyDirectory:
    """测试 _get_methodology_directory 函数"""

    @patch("jarvis.jarvis_utils.methodology.get_data_dir")
    @patch("jarvis.jarvis_utils.methodology.os.path.exists")
    @patch("jarvis.jarvis_utils.methodology.os.makedirs")
    def test_existing_directory(self, mock_makedirs, mock_exists, mock_get_data_dir):
        """测试已存在的目录"""
        mock_get_data_dir.return_value = "/test/data"
        mock_exists.return_value = True

        result = _get_methodology_directory()
        assert result == "/test/data/methodologies"
        mock_makedirs.assert_not_called()

    @patch("jarvis.jarvis_utils.methodology.get_data_dir")
    @patch("jarvis.jarvis_utils.methodology.os.path.exists")
    @patch("jarvis.jarvis_utils.methodology.os.makedirs")
    def test_create_directory(self, mock_makedirs, mock_exists, mock_get_data_dir):
        """测试创建目录"""
        mock_get_data_dir.return_value = "/test/data"
        mock_exists.return_value = False

        result = _get_methodology_directory()
        assert result == "/test/data/methodologies"
        mock_makedirs.assert_called_once_with("/test/data/methodologies", exist_ok=True)

    @patch("jarvis.jarvis_utils.methodology.get_data_dir")
    @patch("jarvis.jarvis_utils.methodology.os.path.exists")
    @patch("jarvis.jarvis_utils.methodology.os.makedirs")
    def test_create_directory_error(
        self, mock_makedirs, mock_exists, mock_get_data_dir
    ):
        """测试创建目录失败"""
        mock_get_data_dir.return_value = "/test/data"
        mock_exists.return_value = False
        mock_makedirs.side_effect = OSError("Permission denied")

        # 应该仍然返回路径，即使创建失败
        result = _get_methodology_directory()
        assert result == "/test/data/methodologies"


class TestSelectMethodologiesWithNormalModel:
    """测试 _select_methodologies_with_normal_model 函数"""

    def _make_platform(self, response: str) -> MagicMock:
        platform = MagicMock()
        platform.chat_until_success.return_value = response
        return platform

    def test_parse_num_tag(self):
        """测试从 <NUM> 标签解析序号"""
        methodologies = [("A", "content-a"), ("B", "content-b"), ("C", "content-c")]
        platform = self._make_platform("<NUM>1,3</NUM>")

        result = _select_methodologies_with_normal_model(
            platform=platform,
            methodologies=methodologies,
            methodology_titles=["A", "B", "C"],
            prompt="",
            user_input="test",
        )
        assert result == [("A", "content-a"), ("C", "content-c")]

    def test_none_returns_empty(self):
        """测试返回 none 时返回空列表"""
        methodologies = [("A", "content-a")]
        platform = self._make_platform("<NUM>none</NUM>")

        result = _select_methodologies_with_normal_model(
            platform=platform,
            methodologies=methodologies,
            methodology_titles=["A"],
            prompt="",
            user_input="test",
        )
        assert result == []

    def test_out_of_range_index_ignored(self):
        """测试越界序号被忽略"""
        methodologies = [("A", "content-a")]
        platform = self._make_platform("<NUM>1,99</NUM>")

        result = _select_methodologies_with_normal_model(
            platform=platform,
            methodologies=methodologies,
            methodology_titles=["A"],
            prompt="",
            user_input="test",
        )
        assert result == [("A", "content-a")]


class TestLoadMethodologyEvalFirst:
    """测试 load_methodology 的 JEV 优先与 Normal 兜底路径"""

    METHODOLOGIES = [("A", "content-a"), ("B", "content-b")]

    def _patch_common(self):
        """返回一组通用 patch，避免真实平台与 token 计算"""
        return [
            patch(
                "jarvis.jarvis_utils.methodology._load_all_methodologies",
                return_value=self.METHODOLOGIES,
            ),
            patch("jarvis.jarvis_utils.methodology.PlatformRegistry"),
            patch(
                "jarvis.jarvis_utils.methodology.get_context_token_count",
                return_value=1,
            ),
            patch(
                "jarvis.jarvis_utils.methodology.get_cheap_max_input_token_count",
                return_value=100000,
            ),
        ]

    @staticmethod
    def _make_platform(selection_response: str) -> MagicMock:
        """构造平台 mock：选择提示词返回 selection_response，生成步骤返回固定文本"""
        platform = MagicMock()
        platform._get_platform_max_input_token_count.return_value = 100000

        def _chat(prompt: str) -> str:
            if "请严格按以下格式返回序号" in prompt:
                return selection_response
            return "GENERATED_STEPS"

        platform.chat_until_success.side_effect = _chat
        return platform

    def test_eval_model_selected_titles(self):
        """JEV 返回标题列表时，按标题回取方法论内容"""
        patches = self._patch_common()
        mocks = [p.start() for p in patches]
        try:
            platform = self._make_platform("<NUM>1</NUM>")
            mocks[1].return_value.get_normal_platform.return_value = platform

            with patch(
                "jarvis.jarvis_utils.methodology._select_methodologies_with_eval_model",
                return_value=["B"],
            ) as mock_eval:
                load_methodology("user input")

            mock_eval.assert_called_once()
            # 方法论内容出现在发给模型的生成步骤提示词中
            all_prompts = " ".join(
                str(c) for c in platform.chat_until_success.call_args_list
            )
            assert "content-b" in all_prompts
            assert "content-a" not in all_prompts
            # eval 路径下不应再走 normal 的选择提示词
            selection_calls = [
                c
                for c in platform.chat_until_success.call_args_list
                if "请严格按以下格式返回序号" in str(c)
            ]
            assert selection_calls == []
        finally:
            for p in patches:
                p.stop()

    def test_fallback_to_normal_when_eval_returns_none(self):
        """JEV 返回 None 时回退到 normal 流程"""
        patches = self._patch_common()
        mocks = [p.start() for p in patches]
        try:
            platform = self._make_platform("<NUM>1</NUM>")
            mocks[1].return_value.get_normal_platform.return_value = platform

            with patch(
                "jarvis.jarvis_utils.methodology._select_methodologies_with_eval_model",
                return_value=None,
            ):
                load_methodology("user input")

            # 回退路径应调用 normal 平台的选择提示词
            selection_calls = [
                c
                for c in platform.chat_until_success.call_args_list
                if "请严格按以下格式返回序号" in str(c)
            ]
            assert len(selection_calls) == 1
            # normal 选中的方法论内容出现在生成步骤提示词中
            all_prompts = " ".join(
                str(c) for c in platform.chat_until_success.call_args_list
            )
            assert "content-a" in all_prompts
        finally:
            for p in patches:
                p.stop()
