# -*- coding: utf-8 -*-
"""
文件重写工具类

功能概述:
1. 提供完整的文件重写功能
2. 支持创建新文件或完全重写现有文件
3. 实现原子操作：所有修改要么全部成功，要么全部回滚
4. 自动创建所需目录结构

核心特性:
- 支持不存在的文件和空文件处理
- 自动创建所需目录结构
- 完善的错误处理和回滚机制
- 保持文件格式和编码
"""
from typing import Any, Dict


class FileRewriteTool:
    name = "rewrite_file"
    description = """文件重写工具，用于完全重写或创建文件

# 文件重写规范

## 重要提示
此工具用于完全重写文件内容或创建新文件。与edit_file不同，此工具会替换文件的全部内容。

## 基本使用
1. 指定需要重写的文件路径
2. 提供新的文件内容
3. 所有操作要么全部成功，要么全部失败并回滚

## 核心原则
1. **完整重写**：提供完整的文件内容，将替换原文件的所有内容
2. **格式保持**：
   - 保持原始代码的缩进方式（空格或制表符）
   - 保持原始代码的空行数量和位置
   - 保持原始代码的行尾空格处理方式
   - 不改变原始代码的换行风格

## 最佳实践
1. 确保提供格式良好的完整文件内容
2. 创建新文件时提供完整、格式良好的内容
3. 不要出现未实现的代码，如：TODO
"""
    parameters = {
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "需要重写的文件路径"},
            "content": {
                "type": "string",
                "description": "新的文件内容，将完全替换原文件内容",
            },
        },
        "required": ["file", "content"],
    }

    def __init__(self):
        """初始化文件重写工具"""
        pass

    def execute(self, args: Dict) -> Dict[str, Any]:
        """
        执行文件重写操作，完全替换文件内容

        参数:
            file (str): 文件路径
            content (str): 新的文件内容

        返回:
            dict: 包含执行结果的字典
            {
                "success": bool,  # 是否成功完成重写
                "stdout": str,    # 标准输出信息
                "stderr": str     # 错误信息
            }
        """
        import os

        from jarvis.jarvis_utils.output import OutputType, PrettyOutput

        stdout_messages = []
        stderr_messages = []
        success = True

        file_path = args["file"]
        new_content = args["content"]
        agent = args.get("agent", None)
        abs_path = os.path.abspath(file_path)

        # 创建已处理文件变量，用于失败时回滚
        original_content = None
        processed = False

        try:
            file_exists = os.path.exists(file_path)

            try:
                # 如果文件存在，则读取原内容用于回滚
                if file_exists:
                    with open(abs_path, "r", encoding="utf-8") as f:
                        original_content = f.read()

                # 确保目录存在
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)

                # 写入新内容
                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                processed = True

                action = "创建并写入" if not file_exists else "成功重写"
                stdout_message = f"文件 {abs_path} {action}"
                stdout_messages.append(stdout_message)
                PrettyOutput.print(stdout_message, OutputType.SUCCESS)

            except Exception as e:
                stderr_message = f"处理文件 {file_path} 时出错: {str(e)}"
                stderr_messages.append(stderr_message)
                PrettyOutput.print(stderr_message, OutputType.WARNING)
                success = False

            # 如果操作失败，回滚已修改的文件
            if not success and processed:
                rollback_message = "操作失败，正在回滚修改..."
                stderr_messages.append(rollback_message)
                PrettyOutput.print(rollback_message, OutputType.WARNING)

                try:
                    if original_content is None:
                        # 如果是新创建的文件，则删除
                        if os.path.exists(abs_path):
                            os.remove(abs_path)
                        rollback_file_message = f"已删除新创建的文件: {abs_path}"
                    else:
                        # 如果是修改的文件，则恢复原内容
                        with open(abs_path, "w", encoding="utf-8") as f:
                            f.write(original_content)
                        rollback_file_message = f"已回滚文件: {abs_path}"

                    stderr_messages.append(rollback_file_message)
                    PrettyOutput.print(rollback_file_message, OutputType.INFO)
                except Exception as e:
                    rollback_error = f"回滚文件 {file_path} 失败: {str(e)}"
                    stderr_messages.append(rollback_error)
                    PrettyOutput.print(rollback_error, OutputType.WARNING)

            # 记录成功处理的文件（使用绝对路径）
            if success and agent:
                abs_path = os.path.abspath(file_path)
                files = agent.get_user_data("files")
                if files:
                    if abs_path not in files:
                        files.append(abs_path)
                else:
                    files = [abs_path]
                agent.set_user_data("files", files)

            return {
                "success": success,
                "stdout": "\n".join(stdout_messages),
                "stderr": "\n".join(stderr_messages),
            }

        except Exception as e:
            error_msg = f"文件重写操作失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.WARNING)

            # 如果有已修改的文件，尝试回滚
            if processed:
                rollback_message = "操作失败，正在回滚修改..."
                stderr_messages.append(rollback_message)
                PrettyOutput.print(rollback_message, OutputType.WARNING)

                try:
                    if original_content is None:
                        # 如果是新创建的文件，则删除
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        stderr_messages.append(f"已删除新创建的文件: {file_path}")
                    else:
                        # 如果是修改的文件，则恢复原内容
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(original_content)
                        stderr_messages.append(f"已回滚文件: {file_path}")
                except:
                    stderr_messages.append(f"回滚文件失败: {file_path}")

            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg + "\n" + "\n".join(stderr_messages),
            }
