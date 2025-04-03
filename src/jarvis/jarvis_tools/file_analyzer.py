from typing import Dict, Any, List
import os

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from yaspin import yaspin
from yaspin.spinners import Spinners

class FileAnalyzerTool:
    name = "file_analyzer"
    description = """分析文件内容并提取关键信息。支持的文件：文本文件、word文档、pdf文件、图片"""
    labels = ['file', 'analysis', 'code']
    parameters = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "要分析的文件路径列表"
            },
            "prompt": {
                "type": "string",
                "description": "分析文件的提示词，指导模型提取什么样的信息"
            }
        },
        "required": ["file_paths", "prompt"]
    }

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
            
            agent = args["agent"]
            agent.reset_tool_call_count()

            # 验证文件路径
            valid_files = []
            for file_path in file_paths:
                if os.path.exists(file_path):
                    valid_files.append(file_path)
                else:
                    PrettyOutput.print(f"文件不存在: {file_path}", OutputType.WARNING)
            
            if not valid_files:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "没有找到有效的文件"
                }

            # 创建thinking平台实例
            platform_registry = PlatformRegistry.get_global_platform_registry()
            platform = platform_registry.get_thinking_platform()
            
            if not platform:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "无法创建thinking平台实例"
                }
            
            # 设置系统消息
            system_message = """你是一个文件分析助手。你的任务是分析提供的文件内容，并根据用户的提示提取关键信息。
请保持客观，只关注文件中实际存在的内容。如果无法确定某些信息，请明确指出。
请以结构化的方式组织你的回答，使用标题、列表和代码块等格式来提高可读性。"""
            platform.set_system_message(system_message)
            
            # 上传文件
            with yaspin(Spinners.dots, text="正在上传文件...") as spinner:
                try:
                    with spinner.hidden():
                        upload_result = platform.upload_files(valid_files)
                    if not upload_result:
                        spinner.text = "文件上传失败"
                        spinner.fail("❌")
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": "文件上传失败"
                        }
                    spinner.text = "文件上传成功"
                    spinner.ok("✅")
                except Exception as e:
                    spinner.text = "文件上传失败"
                    spinner.fail("❌")
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": f"文件上传失败: {str(e)}"
                    }

            platform.set_suppress_output(False)
            
            # 构建分析请求
            analysis_request = f"""
请根据以下提示分析这些文件。
{prompt}

请提供详细的分析结果和理由。"""

            # 发送请求并获取分析结果
            with yaspin(Spinners.dots, text="正在分析文件...") as spinner:
                with spinner.hidden():
                    analysis_result = platform.chat_until_success(analysis_request)
                spinner.text = "分析完成"
                spinner.ok("✅")
            
            # 清理会话
            platform.delete_chat()
            
            return {
                "success": True,
                "stdout": analysis_result,
                "stderr": ""
            }

        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"文件分析失败: {str(e)}"
            }
