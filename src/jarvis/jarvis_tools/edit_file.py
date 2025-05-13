# -*- coding: utf-8 -*-
"""
文件搜索替换工具类

功能概述:
1. 提供精确的文件内容搜索和替换功能
2. 支持单个文件的编辑操作，包括创建新文件
3. 实现原子操作：所有修改要么全部成功，要么全部回滚
4. 严格匹配控制：每个搜索文本必须且只能匹配一次

核心特性:
- 支持不存在的文件和空文件处理
- 自动创建所需目录结构
- 完善的错误处理和回滚机制
- 严格的格式保持要求
"""
import re
from typing import Any, Dict, Tuple

import yaml
from yaspin import yaspin

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.file_operation import FileOperationTool
from jarvis.jarvis_utils.git_utils import revert_file
from jarvis.jarvis_utils.tag import ct, ot
from jarvis.jarvis_utils.utils import is_context_overflow


class FileSearchReplaceTool:
    name = "edit_file"
    description = """代码编辑工具，用于编辑单个文件

# 代码编辑规范

## 重要提示
此工具可以查看和修改单个文件的代码，只需提供要修改的代码片段即可。应尽量精简内容，只包含必要的上下文和修改部分。特别注意：不要提供完整文件内容，只提供需要修改的部分及其上下文！

## 基本使用
1. 指定需要修改的文件路径
2. 提供一组或多组"reason"和"patch"对
3. 每个patch必须包含修改后的代码和1-2行上下文用于精确定位

## 核心原则
1. **精准修改**：只提供需要修改的代码部分及其上下文，不需要展示整个文件内容
2. **最小补丁原则**：始终生成最小范围的补丁，只包含必要的上下文和实际修改
3. **上下文定位**：确保提供的上下文能唯一标识修改位置

## 最佳实践
1. 每个修改应专注于单一职责，避免包含过多无关代码
2. 不要出现未实现的代码，如：TODO
3. 示例格式：
  ```
  # 原有上下文行
  if condition:  # 修改这行
      return new_value
  ```
"""
    parameters = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "需要修改的文件路径"
            },
            "changes": {
                "type": "array",
                "description": "一组或多组修改，每个修改必须包含1-2行上下文用于精确定位",
                "items": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "修改的原因"
                        },
                        "patch": {
                            "type": "string",
                            "description": "修改后的代码片段，必须包含1-2行上下文代码用于精确定位修改位置，不需要传入完整文件内容"
                        }
                    },
                    "required": ["reason", "patch"]
                }
            }
        },
        "required": ["file", "changes"]
    }

    def __init__(self):
        """初始化文件搜索替换工具"""
        pass

    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行文件编辑操作，包含错误处理和回滚机制。

        主要功能:
        1. 处理文件创建或修改
        2. 原子操作：所有修改要么全部成功，要么全部回滚
        3. 保存修改前后的文件状态以便回滚
        4. 提供详细的执行状态输出

        参数:
            args: 包含以下键的字典:
                - file: 要修改的文件路径
                - changes: 修改列表，每个修改包含:
                    - reason: 修改原因描述
                    - patch: 修改后的代码片段

        返回:
            Dict[str, Any] 包含:
                - success: 操作是否成功
                - stdout: 成功时的输出消息
                - stderr: 失败时的错误消息

        异常处理:
        1. 捕获并记录文件操作异常
        2. 失败的修改尝试回滚到原始状态
        3. 新创建的文件在失败时会被删除
        """
        import os
        from jarvis.jarvis_utils.output import PrettyOutput, OutputType
        
        stdout_messages = []
        stderr_messages = []
        success = True
        
        file_path = args["file"]
        changes = args["changes"]
        
        # 创建已处理文件变量，用于失败时回滚
        original_content = None
        processed = False

        try:
            file_exists = os.path.exists(file_path)
            content = ""
            
            try:
                # 如果文件存在，则读取内容
                if file_exists:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        original_content = content
                
                success, temp_content = patch_apply(file_path, yaml.safe_dump(changes))

                # 只有当所有替换操作都成功时，才写回文件
                if success and (temp_content != original_content or not file_exists):
                    # 确保目录存在
                    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(temp_content)
                    
                    processed = True
                    
                    action = "创建并写入" if not file_exists else "成功修改"
                    stdout_message = f"文件 {file_path} {action} 完成"
                    stdout_messages.append(stdout_message)
                    PrettyOutput.print(stdout_message, OutputType.SUCCESS)
                elif success:
                    stdout_message = f"文件 {file_path} 没有找到需要替换的内容"
                    stdout_messages.append(stdout_message)
                    PrettyOutput.print(stdout_message, OutputType.INFO)
                else:
                    stdout_message = f"文件 {file_path} 修改失败"
                    stdout_messages.append(stdout_message)
                
            except Exception as e:
                stderr_message = f"处理文件 {file_path} 时出错: {str(e)}"
                stderr_messages.append(stderr_message)
                PrettyOutput.print(stderr_message, OutputType.WARNING)
                success = False

            return {
                "success": success,
                "stdout": "\n".join(stdout_messages) if success else "",
                "stderr": "\n".join(stderr_messages) if not success else ""
            }
            
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
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(original_content)
                        stderr_messages.append(f"已回滚文件: {file_path}")
                except:
                    stderr_messages.append(f"回滚文件失败: {file_path}")
            
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg + "\n" + "\n".join(stderr_messages)
            }


def patch_apply(filepath: str, patch_content: str) -> Tuple[bool, str]:
    """执行精确的文件编辑操作，使用AI模型生成差异补丁并应用。

    功能概述:
    1. 使用AI模型分析补丁内容并生成精确的代码差异
    2. 应用生成的差异补丁到目标文件
    3. 提供重试机制确保操作可靠性

    参数:
        filepath: 要编辑的文件路径
        patch_content: YAML格式的补丁内容，包含修改原因和代码片段

    返回值:
        Tuple[bool, str]: 
            - 第一个元素表示操作是否成功
            - 第二个元素是修改后的文件内容(成功时)或错误信息(失败时)

    异常处理:
    1. 捕获并处理文件操作异常
    2. 失败时自动回滚文件修改
    3. 提供详细的执行状态输出
    """
    model = PlatformRegistry().get_normal_platform()
    with yaspin(text=f"正在处理文件 {filepath}...", color="cyan") as spinner:
        try:
            file_content = FileOperationTool().execute({"operation":"read", "files":[{"path":filepath}]})["stdout"]
            need_upload_file = is_context_overflow(file_content)
            upload_success = False
            # 读取原始文件内容
            with spinner.hidden():  
                if need_upload_file and model.upload_files([filepath]):
                    upload_success = True


            model.set_suppress_output(True)

            main_prompt = f"""
# 代码补丁生成专家指南

## 任务描述
你是一位精确的代码补丁生成专家，需要根据补丁描述生成精确的代码差异。

### 补丁内容
```
{patch_content}
```

## 补丁生成要求
1. **精确性**：严格按照补丁的意图修改代码
2. **格式一致性**：严格保持原始代码的格式风格，如果补丁中缩进或者空行与原代码不一致，则需要修正补丁中的缩进或者空行
3. **最小化修改**：只修改必要的代码部分，保持其他部分不变
4. **上下文完整性**：提供足够的上下文，确保补丁能准确应用

## 输出格式规范
- 使用{ot("DIFF")}块包围每个需要修改的代码段
- 每个{ot("DIFF")}块必须包含SEARCH部分和REPLACE部分
- SEARCH部分是需要查找的原始代码
- REPLACE部分是替换后的新代码
- 确保SEARCH部分能在原文件中**唯一匹配**
- 如果修改较大，可以使用多个{ot("DIFF")}块

## 输出模板
{ot("DIFF")}
{">" * 5} SEARCH
[需要查找的原始代码，包含足够上下文，避免出现可匹配多处的情况]
{'='*5}
[替换后的新代码]
{"<" * 5} REPLACE
{ct("DIFF")}

{ot("DIFF")}
{">" * 5} SEARCH
[另一处需要查找的原始代码，包含足够上下文，避免出现可匹配多处的情况]
{'='*5}
[另一处替换后的新代码]
{"<" * 5} REPLACE
{ct("DIFF")}
"""
            
            for _ in range(3):
                file_prompt = ""
                if not need_upload_file:
                    file_prompt = f"""
    # 原始代码
    {file_content}
    """
                    
                    response = model.chat_until_success(main_prompt + file_prompt)
                else:
                    if upload_success:
                        response = model.chat_until_success(main_prompt)
                    else:
                        response = model.chat_big_content(file_content, main_prompt)

                # 解析差异化补丁
                diff_blocks = re.finditer(ot("DIFF")+r'\s*>{4,} SEARCH\n?(.*?)\n?={4,}\n?(.*?)\s*<{4,} REPLACE\n?'+ct("DIFF"),
                                        response, re.DOTALL)

                # 读取原始文件内容
                with open(filepath, 'r', encoding='utf-8', errors="ignore") as f:
                    file_content = f.read()

                # 应用所有差异化补丁
                modified_content = file_content
                patch_count = 0
                success = True
                for match in diff_blocks:
                    search_text = match.group(1).strip()
                    replace_text = match.group(2).strip()
                    patch_count += 1
                    # 检查搜索文本是否存在于文件中
                    if search_text in modified_content:
                        # 如果有多处，报错
                        if modified_content.count(search_text) > 1:
                            spinner.write(f"❌ 补丁 #{patch_count} 应用失败：找到多个匹配的代码段")
                            success = False
                            break
                        # 应用替换
                        modified_content = modified_content.replace(
                            search_text, replace_text)
                        spinner.write(f"✅ 补丁 #{patch_count} 应用成功")
                    else:
                        spinner.write(f"❌ 补丁 #{patch_count} 应用失败：无法找到匹配的代码段")
                        success = False
                        break
                if not success:
                    revert_file(filepath)
                    continue


                spinner.text = f"文件 {filepath} 修改完成，应用了 {patch_count} 个补丁"
                spinner.ok("✅")
                return True, modified_content
            spinner.text = f"文件 {filepath} 修改失败"
            spinner.fail("❌")
            return False, ""

        except Exception as e:
            spinner.text = f"文件修改失败: {str(e)}"
            spinner.fail("❌")
            return False, ""