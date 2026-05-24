# -*- coding: utf-8 -*-
"""
添加图片工具

支持大模型主动添加图片到当前对话上下文，用于图片分析场景。
"""

import base64
import os
from typing import Any, Dict, List, Optional

from jarvis.jarvis_platform.content_types import (
    ContentBlock,
    ImageURLContent,
    TextContent,
    CONTENT_CONFIG,
)
from jarvis.jarvis_utils.output import PrettyOutput


class AddImagesTool:
    """添加图片到对话上下文的工具"""

    name = "add_images"
    description = "添加图片到当前对话上下文，支持大模型主动识别图片内容"

    parameters = {
        "type": "object",
        "properties": {
            "images": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "图片文件路径（本地路径或URL）",
                        },
                        "description": {
                            "type": "string",
                            "description": "图片描述（可选）",
                            "default": "",
                        },
                        "detail": {
                            "type": "string",
                            "enum": ["low", "high", "auto"],
                            "description": "图片解析精度",
                            "default": "auto",
                        },
                    },
                    "required": ["path"],
                },
                "description": "图片列表",
            },
            "prompt": {
                "type": "string",
                "description": "添加图片后的提示文本（可选）",
                "default": "请分析以下图片内容：",
            },
        },
        "required": ["images"],
    }

    def _validate_image_format(self, path: str) -> bool:
        """验证图片格式

        Args:
            path: 图片路径

        Returns:
            bool: 格式是否支持
        """
        # 如果是URL或base64，假设格式正确
        if path.startswith(("http://", "https://", "data:")):
            return True

        # 检查文件扩展名
        supported_formats = CONTENT_CONFIG.get(
            "supported_image_formats", ["jpg", "jpeg", "png", "gif", "webp"]
        )
        # 确保 supported_formats 是列表
        if not isinstance(supported_formats, list):
            supported_formats = ["jpg", "jpeg", "png", "gif", "webp"]

        ext = os.path.splitext(path)[1].lower().lstrip(".")
        return ext in supported_formats

    def _validate_image_size(self, path: str) -> bool:
        """验证图片大小

        Args:
            path: 图片路径

        Returns:
            bool: 大小是否在限制内
        """
        # 如果是URL或base64，跳过大小检查
        if path.startswith(("http://", "https://", "data:")):
            return True

        try:
            max_size = CONTENT_CONFIG.get("max_image_size", 20 * 1024 * 1024)
            # 确保 max_size 是整数
            if not isinstance(max_size, int):
                max_size = 20 * 1024 * 1024

            file_size = os.path.getsize(path)
            return file_size <= max_size
        except OSError:
            return False

    def _encode_image_to_base64(self, path: str) -> Optional[str]:
        """将图片编码为base64

        Args:
            path: 图片路径

        Returns:
            Optional[str]: base64编码字符串，失败返回None
        """
        try:
            # 如果已经是URL或base64，直接返回
            if path.startswith(("http://", "https://", "data:")):
                return path

            # 读取文件并编码
            with open(path, "rb") as f:
                image_data = f.read()
                base64_data = base64.b64encode(image_data).decode("utf-8")

                # 获取MIME类型
                ext = os.path.splitext(path)[1].lower().lstrip(".")
                mime_map = {
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg",
                    "png": "image/png",
                    "gif": "image/gif",
                    "webp": "image/webp",
                }
                mime_type = mime_map.get(ext, "application/octet-stream")

                return f"data:{mime_type};base64,{base64_data}"
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 图片编码失败: {path} - {e}")
            return None

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行添加图片操作

        Args:
            args: 工具参数

        Returns:
            Dict[str, Any]: 执行结果
        """
        try:
            images = args.get("images", [])
            prompt = args.get("prompt", "请分析以下图片内容：")

            if not images:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "图片列表不能为空",
                }

            # 验证并处理每张图片
            processed_images: List[ContentBlock] = []
            errors = []

            for i, image_info in enumerate(images):
                try:
                    # 验证图片路径
                    path = image_info.get("path")
                    if not path:
                        errors.append(f"第{i + 1}张图片缺少path参数")
                        continue

                    # 检查图片是否存在（本地文件）
                    if not path.startswith(("http://", "https://", "data:")):
                        expanded_path = os.path.expanduser(path)
                        abs_path = os.path.abspath(expanded_path)
                        if not os.path.exists(abs_path):
                            errors.append(f"第{i + 1}张图片不存在: {path}")
                            continue
                        path = abs_path

                    # 验证图片格式
                    if not self._validate_image_format(path):
                        errors.append(f"第{i + 1}张图片格式不支持: {path}")
                        continue

                    # 验证图片大小
                    if not self._validate_image_size(path):
                        errors.append(f"第{i + 1}张图片大小超过限制: {path}")
                        continue

                    # 编码图片
                    encoded_image = self._encode_image_to_base64(path)
                    if not encoded_image:
                        errors.append(f"第{i + 1}张图片编码失败: {path}")
                        continue

                    # 添加描述（如果有）
                    description = image_info.get("description", "")
                    if description:
                        text_content: TextContent = {
                            "type": "text",
                            "text": description,
                        }
                        processed_images.append(text_content)

                    # 创建图片内容块
                    image_content: ImageURLContent = {
                        "type": "image_url",
                        "image_url": encoded_image,
                        "detail": image_info.get("detail", "auto"),
                    }
                    processed_images.append(image_content)

                except Exception as e:
                    errors.append(f"处理第{i + 1}张图片失败: {str(e)}")

            if not processed_images:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"没有有效的图片。错误: {'; '.join(errors)}",
                }

            # 构建最终的消息内容
            final_content: List[ContentBlock] = []
            if prompt:
                final_content.append({"type": "text", "text": prompt})
            final_content.extend(processed_images)

            # 将图片添加到当前对话上下文
            agent = args.get("agent")
            if agent and hasattr(agent, "add_multimodal_content"):
                agent.add_multimodal_content(final_content)

            # 构建返回结果
            success_count = len(
                [b for b in processed_images if b.get("type") == "image_url"]
            )
            result_msg = f"✅ 成功添加 {success_count} 张图片到对话上下文"
            if errors:
                result_msg += f"\n⚠ 部分错误: {'; '.join(errors)}"

            PrettyOutput.auto_print(result_msg)

            return {
                "success": True,
                "stdout": result_msg,
                "stderr": "",
                "processed_images": final_content,
            }

        except Exception as e:
            error_msg = f"添加图片失败: {str(e)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg,
            }
