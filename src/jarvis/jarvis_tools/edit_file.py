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
此工具可以查看和修改单个文件的代码，只需提供要修改的代码片段即可。应尽量精简内容，只包含必要的上下文和修改部分。特别注意：不要提供完整文件内容，只提供需要修改的部分！

## 基本使用
1. 指定需要修改的文件路径
2. 提供一组或多组"搜索文本"和"替换文本"对
3. 每个搜索文本需在目标文件中有且仅有一次精确匹配
4. 创建新文件时，使用空字符串("")作为搜索文本，替换文本作为完整文件内容
5. 所有修改要么全部成功，要么全部失败并回滚

## 核心原则
1. **精准修改**：只提供需要修改的代码部分，不需要展示整个文件内容
2. **最小补丁原则**：始终生成最小范围的补丁，只包含必要的上下文和实际修改
3. **格式严格保持**：
   - 严格保持原始代码的缩进方式（空格或制表符）
   - 保持原始代码的空行数量和位置
   - 保持原始代码的行尾空格处理方式
   - 不改变原始代码的换行风格
4. **新旧区分**：
   - 对于新文件：提供完整的代码内容
   - 对于现有文件：只提供修改部分，不要提供整个文件

## 格式兼容性要求
1. **缩进一致性**：
   - 如果原代码使用4个空格缩进，替换文本也必须使用4个空格缩进
   - 如果原代码使用制表符缩进，替换文本也必须使用制表符
2. **空行保留**：
   - 如果原代码在函数之间有两个空行，替换文本也必须保留这两个空行
   - 如果原代码在类方法之间有一个空行，替换文本也必须保留这一个空行
3. **行尾处理**：
   - 不要改变原代码的行尾空格或换行符风格
   - 保持原有的换行符类型(CR、LF或CRLF)

## 最佳实践
1. 每个修改应专注于单一职责，避免包含过多无关代码
2. 设计唯一的搜索文本，避免多处匹配的风险
3. 创建新文件时提供完整、格式良好的内容
4. 不要出现未实现的代码，如：TODO
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
                "description": "一组或多组搜索替换对",
                "items": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "修改的原因"
                        },
                        "search": {
                            "type": "string",
                            "description": "需要被替换的文本，必须在文件中唯一匹配，新文件用空字符串"
                        },
                        "replace": {
                            "type": "string", 
                            "description": "替换的目标文本，需保持与原代码相同的缩进和格式风格"
                        }
                    },
                    "required": ["search", "replace"]
                }
            }
        },
        "required": ["file", "changes"]
    }

    def __init__(self):
        """初始化文件搜索替换工具"""
        pass

    def execute(self, args: Dict) -> Dict[str, Any]:
        """
        执行文件搜索替换操作，每个搜索文本只允许有且只有一次匹配，否则失败
        特殊支持不存在的文件和空文件处理

        参数:
            file (str): 文件路径
            changes (list): 一组或多组搜索替换对，格式如下：
            [
                {
                    "search": "搜索文本1",
                    "replace": "替换文本1"
                },
                {
                    "search": "搜索文本2",
                    "replace": "替换文本2"
                }
            ]

        返回:
            dict: 包含执行结果的字典
            {
                "success": bool,  # 是否成功完成所有替换
                "stdout": str,    # 标准输出信息
                "stderr": str     # 错误信息
            }
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
                
                # 创建一个临时内容副本进行操作
                temp_content = content
                replaced_count = 0
                
                # 处理所有搜索替换对
                for change in changes:
                    search_text = change["search"]
                    replace_text = change["replace"]
                    
                    # 特殊处理不存在的文件或空文件
                    if not file_exists or content == "":
                        if search_text == "":
                            # 对于不存在的文件或空文件，如果搜索文本为空，则直接使用替换文本作为内容
                            temp_content = replace_text
                            replaced_count += 1
                            # 只允许有一个空字符串搜索
                            break
                        else:
                            stderr_message = f"文件 {file_path} {'不存在' if not file_exists else '为空'}，但搜索文本非空: '{search_text}'"
                            stderr_messages.append(stderr_message)
                            PrettyOutput.print(stderr_message, OutputType.WARNING)
                            success = False
                            break
                    else:
                        # 正常文件处理 - 检查匹配次数
                        match_count = temp_content.count(search_text)
                        
                        if match_count == 0:
                            stderr_message = f"文件 {file_path} 中未找到匹配文本: '{search_text}'"
                            stderr_messages.append(stderr_message)
                            PrettyOutput.print(stderr_message, OutputType.WARNING)
                            success = False
                            break
                        elif match_count > 1:
                            stderr_message = f"文件 {file_path} 中匹配到多个 ({match_count}) '{search_text}'，搜索文本只允许一次匹配"
                            stderr_messages.append(stderr_message)
                            PrettyOutput.print(stderr_message, OutputType.WARNING)
                            success = False
                            break
                        else:
                            # 只有一个匹配，执行替换
                            temp_content = temp_content.replace(search_text, replace_text, 1)
                            replaced_count += 1

                if not success:
                    PrettyOutput.print("快速编辑失败，尝试使用代码补丁编辑", OutputType.INFO)
                    success, temp_content = handle_code_patch(file_path, yaml.safe_dump(changes))

                # 只有当所有替换操作都成功时，才写回文件
                if success and (temp_content != original_content or not file_exists):
                    # 确保目录存在
                    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(temp_content)
                    
                    processed = True
                    
                    action = "创建并写入" if not file_exists else "成功替换"
                    stdout_message = f"文件 {file_path} {action} {replaced_count} 处"
                    stdout_messages.append(stdout_message)
                    PrettyOutput.print(stdout_message, OutputType.SUCCESS)
                elif success:
                    stdout_message = f"文件 {file_path} 没有找到需要替换的内容"
                    stdout_messages.append(stdout_message)
                    PrettyOutput.print(stdout_message, OutputType.INFO)
                
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
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        rollback_file_message = f"已删除新创建的文件: {file_path}"
                    else:
                        # 如果是修改的文件，则恢复原内容
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(original_content)
                        rollback_file_message = f"已回滚文件: {file_path}"
                        
                    stderr_messages.append(rollback_file_message)
                    PrettyOutput.print(rollback_file_message, OutputType.INFO)
                except Exception as e:
                    rollback_error = f"回滚文件 {file_path} 失败: {str(e)}"
                    stderr_messages.append(rollback_error)
                    PrettyOutput.print(rollback_error, OutputType.WARNING)

            return {
                "success": success,
                "stdout": "\n".join(stdout_messages),
                "stderr": "\n".join(stderr_messages)
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

            


def handle_code_patch(filepath: str, patch_content: str) -> Tuple[bool, str]:
    """处理大型代码文件的补丁操作，使用差异化补丁格式"""
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


            model.set_suppress_output(False)

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
2. **格式一致性**：严格保持原始代码的格式风格
   - 缩进方式（空格或制表符）必须与原代码保持一致
   - 空行数量和位置必须与原代码风格匹配
   - 行尾空格处理必须与原代码一致
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
                    with spinner.hidden():
                        response = model.chat_until_success(main_prompt + file_prompt)
                else:
                    if upload_success:
                        with spinner.hidden():
                            response = model.chat_until_success(main_prompt)
                    else:
                        with spinner.hidden():
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