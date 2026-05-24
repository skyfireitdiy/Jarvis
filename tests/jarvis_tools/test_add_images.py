# -*- coding: utf-8 -*-
"""jarvis_tools.add_images 模块单元测试"""

import base64
import os
import tempfile
from unittest.mock import MagicMock

import pytest

from jarvis.jarvis_tools.add_images import AddImagesTool


class TestAddImagesTool:
    """测试 AddImagesTool 类"""

    @pytest.fixture
    def tool(self):
        """创建测试用的 AddImagesTool 实例"""
        return AddImagesTool()

    @pytest.fixture
    def mock_agent(self):
        """创建模拟的 Agent 实例"""
        agent = MagicMock()
        agent.add_multimodal_content = MagicMock()
        return agent

    @pytest.fixture
    def sample_image(self):
        """创建示例图片文件"""
        # 创建一个简单的 1x1 像素的 PNG 图片
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        )
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".png", delete=False) as f:
            f.write(png_data)
            filepath = f.name

        yield filepath

        # 清理
        if os.path.exists(filepath):
            os.unlink(filepath)

    @pytest.fixture
    def sample_jpg_image(self):
        """创建示例 JPG 图片文件"""
        # 创建一个简单的 JPG 图片（实际是文本文件，但用于测试格式验证）
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jpg", delete=False) as f:
            f.write("fake jpg content")
            filepath = f.name

        yield filepath

        # 清理
        if os.path.exists(filepath):
            os.unlink(filepath)

    def test_add_single_local_image(self, tool, mock_agent, sample_image):
        """测试添加单个本地图片"""
        args = {
            "images": [{"path": sample_image}],
            "agent": mock_agent,
        }

        result = tool.execute(args)

        assert result["success"] is True
        assert "成功添加 1 张图片" in result["stdout"]
        assert mock_agent.add_multimodal_content.called
        # 验证传递给 agent 的内容
        call_args = mock_agent.add_multimodal_content.call_args[0][0]
        assert len(call_args) == 2  # prompt + image
        assert call_args[0]["type"] == "text"
        assert call_args[1]["type"] == "image_url"

    def test_add_multiple_local_images(self, tool, mock_agent, sample_image):
        """测试添加多个本地图片"""
        args = {
            "images": [
                {"path": sample_image, "description": "图片1"},
                {"path": sample_image, "description": "图片2"},
            ],
            "agent": mock_agent,
        }

        result = tool.execute(args)

        assert result["success"] is True
        assert "成功添加 2 张图片" in result["stdout"]
        assert mock_agent.add_multimodal_content.called
        # 验证传递给 agent 的内容
        call_args = mock_agent.add_multimodal_content.call_args[0][0]
        assert len(call_args) == 5  # prompt + (desc + image) * 2

    def test_add_image_with_description(self, tool, mock_agent, sample_image):
        """测试添加带描述的图片"""
        args = {
            "images": [{"path": sample_image, "description": "这是一张测试图片"}],
            "agent": mock_agent,
        }

        result = tool.execute(args)

        assert result["success"] is True
        assert "成功添加 1 张图片" in result["stdout"]
        # 验证描述被添加
        call_args = mock_agent.add_multimodal_content.call_args[0][0]
        # 应该有：prompt, description, image
        assert len(call_args) == 3
        assert call_args[1]["type"] == "text"
        assert "这是一张测试图片" in call_args[1]["text"]

    def test_add_image_with_custom_prompt(self, tool, mock_agent, sample_image):
        """测试添加图片时使用自定义提示"""
        args = {
            "images": [{"path": sample_image}],
            "prompt": "请详细描述这张图片：",
            "agent": mock_agent,
        }

        result = tool.execute(args)

        assert result["success"] is True
        # 验证自定义提示被使用
        call_args = mock_agent.add_multimodal_content.call_args[0][0]
        assert call_args[0]["text"] == "请详细描述这张图片："

    def test_add_url_image(self, tool, mock_agent):
        """测试添加 URL 图片"""
        args = {
            "images": [{"path": "https://example.com/image.png"}],
            "agent": mock_agent,
        }

        result = tool.execute(args)

        assert result["success"] is True
        assert "成功添加 1 张图片" in result["stdout"]
        # 验证 URL 被直接使用
        call_args = mock_agent.add_multimodal_content.call_args[0][0]
        assert call_args[1]["image_url"] == "https://example.com/image.png"

    def test_add_nonexistent_image(self, tool, mock_agent):
        """测试添加不存在的图片"""
        args = {
            "images": [{"path": "/nonexistent/image.png"}],
            "agent": mock_agent,
        }

        result = tool.execute(args)

        assert result["success"] is False
        assert "不存在" in result["stderr"]
        assert not mock_agent.add_multimodal_content.called

    def test_add_unsupported_format(self, tool, mock_agent):
        """测试添加不支持的格式"""
        # 创建一个 .txt 文件
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("not an image")
            txt_file = f.name

        try:
            args = {
                "images": [{"path": txt_file}],
                "agent": mock_agent,
            }

            result = tool.execute(args)

            assert result["success"] is False
            assert "格式不支持" in result["stderr"]
            assert not mock_agent.add_multimodal_content.called
        finally:
            if os.path.exists(txt_file):
                os.unlink(txt_file)

    def test_add_empty_images_list(self, tool, mock_agent):
        """测试空图片列表"""
        args = {
            "images": [],
            "agent": mock_agent,
        }

        result = tool.execute(args)

        assert result["success"] is False
        assert "不能为空" in result["stderr"]
        assert not mock_agent.add_multimodal_content.called

    def test_add_image_without_path(self, tool, mock_agent):
        """测试图片缺少 path 参数"""
        args = {
            "images": [{"description": "没有路径的图片"}],
            "agent": mock_agent,
        }

        result = tool.execute(args)

        assert result["success"] is False
        assert "缺少path参数" in result["stderr"]
        assert not mock_agent.add_multimodal_content.called

    def test_add_image_without_agent(self, tool, sample_image):
        """测试不提供 agent 参数"""
        args = {
            "images": [{"path": sample_image}],
        }

        result = tool.execute(args)

        # 应该仍然成功，只是不会调用 agent
        assert result["success"] is True
        assert "成功添加 1 张图片" in result["stdout"]

    def test_partial_success(self, tool, mock_agent, sample_image):
        """测试部分成功的情况"""
        args = {
            "images": [
                {"path": sample_image},  # 有效
                {"path": "/nonexistent/image.png"},  # 无效
            ],
            "agent": mock_agent,
        }

        result = tool.execute(args)

        assert result["success"] is True
        assert "成功添加 1 张图片" in result["stdout"]
        assert "部分错误" in result["stdout"]
        assert mock_agent.add_multimodal_content.called

    def test_validate_image_format(self, tool, sample_image):
        """测试图片格式验证"""
        # 有效的 PNG 格式
        assert tool._validate_image_format(sample_image) is True

        # 有效的 JPG 格式
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            jpg_file = f.name
        try:
            assert tool._validate_image_format(jpg_file) is True
        finally:
            if os.path.exists(jpg_file):
                os.unlink(jpg_file)

        # 无效的格式
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            txt_file = f.name
        try:
            assert tool._validate_image_format(txt_file) is False
        finally:
            if os.path.exists(txt_file):
                os.unlink(txt_file)

        # URL 应该总是返回 True
        assert tool._validate_image_format("https://example.com/image.png") is True
        assert tool._validate_image_format("data:image/png;base64,...") is True

    def test_validate_image_size(self, tool, sample_image):
        """测试图片大小验证"""
        # 小图片应该通过
        assert tool._validate_image_size(sample_image) is True

        # URL 应该总是返回 True
        assert tool._validate_image_size("https://example.com/image.png") is True

        # 不存在的文件应该返回 False
        assert tool._validate_image_size("/nonexistent/image.png") is False

    def test_encode_image_to_base64(self, tool, sample_image):
        """测试图片 base64 编码"""
        encoded = tool._encode_image_to_base64(sample_image)

        assert encoded is not None
        assert encoded.startswith("data:image/png;base64,")

        # URL 应该直接返回
        url = "https://example.com/image.png"
        assert tool._encode_image_to_base64(url) == url

        # 不存在的文件应该返回 None
        assert tool._encode_image_to_base64("/nonexistent/image.png") is None

    def test_image_with_detail_parameter(self, tool, mock_agent, sample_image):
        """测试图片 detail 参数"""
        args = {
            "images": [{"path": sample_image, "detail": "high"}],
            "agent": mock_agent,
        }

        result = tool.execute(args)

        assert result["success"] is True
        # 验证 detail 参数被传递
        call_args = mock_agent.add_multimodal_content.call_args[0][0]
        image_content = call_args[1]
        assert image_content["detail"] == "high"

    def test_expand_user_path(self, tool, mock_agent):
        """测试用户路径扩展（~）"""
        # 创建一个临时文件
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".png", delete=False) as f:
            f.write(b"fake image")
            temp_path = f.name

        try:
            # 使用 ~ 路径（如果可能）
            home_dir = os.path.expanduser("~")
            if temp_path.startswith(home_dir):
                relative_path = temp_path[len(home_dir) :].lstrip("/")
                tilde_path = f"~/{relative_path}"

                args = {
                    "images": [{"path": tilde_path}],
                    "agent": mock_agent,
                }

                result = tool.execute(args)

                # 应该能够正确解析路径
                assert result["success"] is True
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
