# -*- coding: utf-8 -*-
"""
文件编辑工具类

功能概述:
1. 提供精确的文件内容搜索和替换功能，支持多组修改
2. 支持单个文件的编辑操作，包括创建新文件
3. 实现原子操作：所有修改要么全部成功，要么全部回滚
4. 严格匹配控制：每个搜索文本必须且只能匹配一次
5. 支持两种编辑模式：快速编辑(fast_edit)和AI辅助编辑(slow_edit)

核心特性:
- 支持不存在的文件和空文件处理
- 自动创建所需目录结构
- 完善的错误处理和回滚机制
- 严格的格式保持要求
- 支持大文件处理(自动上传到模型平台)
- 提供3次重试机制确保操作可靠性
"""
from typing import Any, Dict

from jarvis.jarvis_agent.edit_file_handler import EditFileHandler


class FileSearchReplaceTool:
    name = "edit_file"
    description = """代码编辑工具，用于精确修改一个或多个文件

# 文件编辑工具使用指南

## 基本使用
1. 指定需要修改的文件路径（单个或多个）
2. 提供一组或多组修改，每个修改包含:
   - reason: 修改原因描述
   - search: 需要查找的原始代码(必须包含足够上下文)
   - replace: 替换后的新代码
3. 工具会自动选择最适合的编辑模式

## 核心原则
1. **精准修改**: 只修改必要的代码部分，保持其他部分不变
2. **最小补丁原则**: 生成最小范围的补丁，包含必要的上下文
3. **唯一匹配**: 确保搜索文本在文件中唯一匹配
4. **格式保持**: 严格保持原始代码的格式风格
5. **部分成功**: 支持多个文件编辑，允许部分文件编辑成功

"""
    parameters = {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "description": "需要修改的文件路径列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"},
                        "changes": {
                            "type": "array",
                            "description": "一组或多组修改，每个修改必须包含1-2行上下文用于精确定位",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "reason": {
                                        "type": "string",
                                        "description": "修改的原因",
                                    },
                                    "search": {
                                        "type": "string",
                                        "description": "需要查找的原始代码",
                                    },
                                    "replace": {
                                        "type": "string",
                                        "description": "替换后的新代码",
                                    },
                                },
                            },
                        },
                    },
                    "required": ["path", "changes"],
                },
            },
        },
        "required": ["files"],
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行文件编辑操作，支持快速编辑和AI辅助编辑两种模式。

        主要功能:
        1. 处理多个文件的创建或修改，支持不存在的文件
        2. 每个文件独立处理，允许部分文件编辑成功
        3. 自动选择编辑模式(fast_edit或slow_edit)
        4. 保存修改前后的文件状态以便回滚
        5. 提供详细的执行状态输出

        参数:
            args: 包含以下键的字典:
                - files: 文件列表，每个文件包含(必填):
                    - path: 要修改的文件路径
                    - changes: 修改列表，每个修改包含:
                        - reason: 修改原因描述
                        - search: 需要查找的原始代码(必须包含足够上下文)
                        - replace: 替换后的新代码

        返回:
            Dict[str, Any] 包含:
                - success: 是否至少有一个文件编辑成功(True/False)
                - stdout: 成功时的输出消息
                - stderr: 失败时的错误消息
                - results: 每个文件的处理结果列表

        异常处理:
        1. 捕获并记录文件操作异常
        2. 失败的修改尝试回滚到原始状态
        3. 新创建的文件在失败时会被删除
        4. 提供3次重试机制确保操作可靠性
        5. 支持大文件处理(自动上传到模型平台)

        实现细节:
        1. 优先尝试fast_edit模式
        2. 如果fast_edit失败，则尝试slow_edit模式
        3. 严格检查搜索文本的唯一匹配性
        4. 保持原始代码的格式风格
        """
        import os

        from jarvis.jarvis_utils.output import OutputType, PrettyOutput

        stdout_messages = []
        stderr_messages = []
        overall_success = False
        file_results = []

        for file_info in args["files"]:
            file_path = os.path.abspath(file_info["path"])
            changes = file_info["changes"]
            agent = args.get("agent", None)

            # 创建已处理文件变量，用于失败时回滚
            original_content = None
            processed = False
            file_success = True

            try:
                file_exists = os.path.exists(file_path)
                content = ""

                try:
                    # 如果文件存在，则读取内容
                    if file_exists:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                            original_content = content

                    if file_exists and agent:
                        files = agent.get_user_data("files")
                        if not files or file_path not in files:
                            file_results.append(
                                {
                                    "file": file_path,
                                    "success": False,
                                    "stdout": "",
                                    "stderr": f"请先读取文件 {file_path} 的内容后再编辑",
                                }
                            )
                            continue

                    print(f"🔍 正在处理文件 {file_path}...")
                    # 首先尝试fast_edit模式
                    success, temp_content = EditFileHandler._fast_edit(
                        file_path, changes
                    )
                    if not success:
                        # 如果fast_edit失败，尝试slow_edit模式
                        success, temp_content = EditFileHandler._slow_edit(
                            file_path, changes, agent
                        )
                        if not success:
                            print(f"❌ 文件 {file_path} 处理失败")
                            file_results.append(
                                {
                                    "file": file_path,
                                    "success": False,
                                    "stdout": "",
                                    "stderr": temp_content,
                                }
                            )
                            continue
                        else:
                            print(f"✅ 文件 {file_path} 内容生成完成")
                    else:
                        print(f"✅ 文件 {file_path} 内容生成完成")

                    # 只有当所有替换操作都成功时，才写回文件
                    if success and (
                        temp_content != original_content or not file_exists
                    ):
                        # 确保目录存在
                        os.makedirs(
                            os.path.dirname(os.path.abspath(file_path)), exist_ok=True
                        )

                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(temp_content)

                        processed = True

                        action = "创建并写入" if not file_exists else "成功修改"
                        stdout_message = f"文件 {file_path} {action} 完成"
                        stdout_messages.append(stdout_message)
                        PrettyOutput.print(stdout_message, OutputType.SUCCESS)
                        overall_success = True

                        file_results.append(
                            {
                                "file": file_path,
                                "success": True,
                                "stdout": stdout_message,
                                "stderr": "",
                            }
                        )

                except Exception as e:
                    stderr_message = f"处理文件 {file_path} 时出错: {str(e)}"
                    stderr_messages.append(stderr_message)
                    PrettyOutput.print(stderr_message, OutputType.WARNING)
                    file_success = False
                    file_results.append(
                        {
                            "file": file_path,
                            "success": False,
                            "stdout": "",
                            "stderr": stderr_message,
                        }
                    )

            except Exception as e:
                error_msg = f"文件搜索替换操作失败: {str(e)}"
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

                file_results.append(
                    {
                        "file": file_path,
                        "success": False,
                        "stdout": "",
                        "stderr": error_msg,
                    }
                )

        # 整合所有错误信息到stderr
        all_stderr = []
        for result in file_results:
            if not result["success"]:
                all_stderr.append(f"文件 {result['file']} 处理失败: {result['stderr']}")

        return {
            "success": overall_success,
            "stdout": "\n".join(stdout_messages) if overall_success else "",
            "stderr": "\n".join(all_stderr) if not overall_success else "",
        }
