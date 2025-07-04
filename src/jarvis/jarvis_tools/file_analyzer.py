# -*- coding: utf-8 -*-
import os
from typing import Any, Dict


from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class FileAnalyzerTool:
    name = "file_analyzer"
    description = (
        """分析文件内容并提取关键信息。支持的文件：文本文件、word文档、pdf文件、图片"""
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要分析的文件路径列表",
            },
            "prompt": {
                "type": "string",
                "description": "分析文件的提示词，指导模型提取什么样的信息",
            },
        },
        "required": ["file_paths", "prompt"],
    }

    @staticmethod
    def check() -> bool:
        return PlatformRegistry().get_thinking_platform().support_upload_files()

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行文件分析操作

        Args:
            args: 包含文件路径列表和提示词的字典

        Returns:
            Dict: 包含分析结果的字典
        """
        try:
            file_paths = args["file_paths"]
            prompt = args["prompt"]

            # 验证文件路径
            valid_files = []
            for file_path in file_paths:
                if os.path.exists(file_path):
                    valid_files.append(file_path)
                else:
                    PrettyOutput.print(f"文件不存在: {file_path}", OutputType.WARNING)

            if not valid_files:
                return {"success": False, "stdout": "", "stderr": "没有找到有效的文件"}

            # 创建thinking平台实例
            platform = PlatformRegistry().get_thinking_platform()

            if not platform:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "无法创建thinking平台实例",
                }

            # 设置系统消息
            system_message = """你是一个文件分析助手。你的任务是分析提供的文件内容，并根据用户的提示提取关键信息。
请保持客观，只关注文件中实际存在的内容。如果无法确定某些信息，请明确指出。
请以结构化的方式组织你的回答，使用标题、列表和代码块等格式来提高可读性。"""
            platform.set_system_prompt(system_message)

            # 上传文件
            print(f"📤 正在上传文件...")
            try:
                upload_result = platform.upload_files(valid_files)
                if not upload_result:
                    print(f"❌ 文件上传失败")
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "文件上传失败",
                    }
                print(f"✅ 文件上传成功")
            except Exception as e:
                print(f"❌ 文件上传失败: {str(e)}")
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"文件上传失败: {str(e)}",
                }

            platform.set_suppress_output(False)

            # 构建分析请求
            analysis_request = f"""
请根据以下提示分析这些文件。
{prompt}

请提供详细的分析结果和理由。"""

            # 发送请求并获取分析结果
            print(f"🔍 正在分析文件...")
            analysis_result = platform.chat_until_success(analysis_request)
            print(f"✅ 分析完成")

            # 清理会话
            platform.delete_chat()

            return {"success": True, "stdout": analysis_result, "stderr": ""}

        except Exception as e:
            return {"success": False, "stdout": "", "stderr": f"文件分析失败: {str(e)}"}
