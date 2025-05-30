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
import re
from typing import Any, Dict, List, Tuple

import yaml
from yaspin import yaspin
from yaspin.core import Yaspin

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.file_operation import FileOperationTool
from jarvis.jarvis_utils.git_utils import revert_file
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.tag import ct, ot
from jarvis.jarvis_utils.utils import is_context_overflow


class FileSearchReplaceTool:
    name = "edit_file"
    description = """代码编辑工具，用于精确修改单个文件

# 文件编辑工具使用指南


## 基本使用
1. 指定需要修改的文件路径
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
                        "search": {
                            "type": "string",
                            "description": "需要查找的原始代码"
                        },
                        "replace": {
                            "type": "string",
                            "description": "替换后的新代码"
                        }
                    },
                }
            }
        },
        "required": ["file", "changes"]
    }

    def __init__(self):
        """初始化文件搜索替换工具"""
        pass

    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行文件编辑操作，支持快速编辑和AI辅助编辑两种模式。

        主要功能:
        1. 处理文件创建或修改，支持不存在的文件
        2. 原子操作：所有修改要么全部成功，要么全部回滚
        3. 自动选择编辑模式(fast_edit或slow_edit)
        4. 保存修改前后的文件状态以便回滚
        5. 提供详细的执行状态输出

        参数:
            args: 包含以下键的字典:
                - file: 要修改的文件路径(必填)
                - changes: 修改列表，每个修改包含(必填):
                    - reason: 修改原因描述
                    - search: 需要查找的原始代码(必须包含足够上下文)
                    - replace: 替换后的新代码

        返回:
            Dict[str, Any] 包含:
                - success: 操作是否成功(True/False)
                - stdout: 成功时的输出消息
                - stderr: 失败时的错误消息

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
        success = True
        
        file_path = os.path.abspath(args["file"])
        changes = args["changes"]
        agent = args.get("agent", None)
        
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

                if file_exists and agent:
                    files = agent.get_user_data("files")
                    if not files or file_path not in files:
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": f"请先读取文件 {file_path} 的内容后再编辑"
                        }


                with yaspin(text=f"正在处理文件 {file_path}...", color="cyan") as spinner:
                    success, temp_content = fast_edit(file_path, changes, spinner)
                    if not success:
                        success, temp_content = slow_edit(file_path, yaml.safe_dump(changes, allow_unicode=True), spinner)
                        if not success:
                            spinner.text = f"文件 {file_path} 处理失败"
                            spinner.fail("❌")
                            return {
                                "success": False,
                                "stdout": "",
                                "stderr": temp_content
                            }
                        else:
                            spinner.text = f"文件 {file_path} 内容生成完成"
                            spinner.ok("✅")
                    else:
                        spinner.text = f"文件 {file_path} 内容生成完成"
                        spinner.ok("✅")


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
        


def slow_edit(filepath: str, patch_content: str, spinner: Yaspin) -> Tuple[bool, str]:
    """执行精确的文件编辑操作，使用AI模型生成差异补丁并应用。
    
    核心功能:
    1. 使用AI模型分析补丁内容并生成精确的代码差异
    2. 应用生成的差异补丁到目标文件
    3. 提供3次重试机制确保操作可靠性
    4. 支持大文件处理(自动上传到模型平台)
    5. 严格的格式一致性检查
    
    参数:
        filepath: 要编辑的文件路径(绝对或相对路径)
        patch_content: YAML格式的补丁内容，包含:
            - reason: 修改原因描述
            - search: 需要查找的原始代码(必须包含足够上下文)
            - replace: 替换后的新代码
        spinner: Yaspin实例，用于显示处理状态
    
    返回值:
        Tuple[bool, str]: 
            - 第一个元素表示操作是否成功(True/False)
            - 第二个元素是修改后的文件内容(成功时)或空字符串(失败时)
    
    异常处理:
    1. 文件不存在或权限不足时会捕获异常并返回失败
    2. 模型生成补丁失败时会自动重试最多3次
    3. 补丁应用失败时会自动回滚文件修改
    
    实现细节:
    1. 检查文件是否在工作目录下(影响版本控制)
    2. 根据文件大小决定是否上传到模型平台
    3. 使用精确的DIFF格式解析模型生成的补丁
    4. 确保补丁应用前进行唯一性匹配检查
    """
    import os
    work_dir = os.path.abspath(os.curdir)
    filepath = os.path.abspath(filepath)
    if not filepath.startswith(work_dir):
        PrettyOutput.print(f"文件 {filepath} 不在工作目录 {work_dir} 下，不会进行版本控制管理", OutputType.WARNING)
    model = PlatformRegistry().get_normal_platform()
    try:
        file_content = FileOperationTool().execute({"operation":"read", "files":[{"path":filepath}]})["stdout"]
        is_large_context = is_context_overflow(file_content)
        upload_success = False
        # 读取原始文件内容
        with spinner.hidden():  
            if is_large_context and model.support_upload_files() and model.upload_files([filepath]):
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
            if is_large_context:
                if upload_success:
                    response = model.chat_until_success(main_prompt)
                else:
                    file_prompt = f"""
# 原始代码
{file_content}
"""
                    response = model.chat_until_success(main_prompt + file_prompt)
            else:
                file_prompt = f"""
# 原始代码
{file_content}
"""
                response = model.chat_until_success(main_prompt + file_prompt)

            # 解析差异化补丁
            diff_blocks = re.finditer(ot("DIFF")+r'\s*>{4,} SEARCH\n?(.*?)\n?={4,}\n?(.*?)\s*<{4,} REPLACE\n?'+ct("DIFF"),
                                    response, re.DOTALL)

            patches = []
            for match in diff_blocks:
                patches.append({
                    "search": match.group(1).strip(),
                    "replace": match.group(2).strip()
                })

            success, modified_content_or_err = fast_edit(filepath, patches, spinner)
            if success:
                return True, modified_content_or_err
        spinner.text = f"文件 {filepath} 修改失败"
        spinner.fail("❌")
        return False, f"文件修改失败: {modified_content_or_err}"

    except Exception as e:
        spinner.text = f"文件修改失败: {str(e)}"
        spinner.fail("❌")
        return False, f"文件修改失败: {str(e)}"


def fast_edit(filepath: str, patches: List[Dict[str,str]], spinner: Yaspin) -> Tuple[bool, str]:
    """快速应用预先生成的补丁到目标文件。
    
    核心功能:
    1. 直接应用已生成的代码补丁
    2. 执行严格的唯一匹配检查
    3. 提供详细的补丁应用状态反馈
    4. 失败时自动回滚文件修改
    
    参数:
        filepath: 要编辑的文件路径(绝对或相对路径)
        patches: 补丁列表，每个补丁包含:
            - search: 需要查找的原始代码
            - replace: 替换后的新代码
        spinner: Yaspin实例，用于显示处理状态
    
    返回值:
        Tuple[bool, str]: 
            - 第一个元素表示操作是否成功(True/False)
            - 第二个元素是修改后的文件内容(成功时)或空字符串(失败时)
    
    异常处理:
    1. 文件不存在或权限不足时会捕获异常并返回失败
    2. 补丁不匹配或有多处匹配时会返回失败
    3. 失败时会自动回滚文件修改
    
    实现细节:
    1. 读取文件内容到内存
    2. 依次应用每个补丁，检查唯一匹配性
    3. 记录每个补丁的应用状态
    4. 所有补丁成功应用后才写入文件
    """
    # 读取原始文件内容
    with open(filepath, 'r', encoding='utf-8', errors="ignore") as f:
        file_content = f.read()

    # 应用所有差异化补丁
    modified_content = file_content
    patch_count = 0
    success = True
    err_msg = ""
    for patch in patches:
        search_text = patch["search"]
        replace_text = patch["replace"]
        patch_count += 1
        # 检查搜索文本是否存在于文件中
        if search_text in modified_content:
            # 如果有多处，报错
            if modified_content.count(search_text) > 1:
                success = False
                err_msg = f"搜索文本 {search_text} 在文件中存在多处，请检查补丁内容"
                break
            # 应用替换
            modified_content = modified_content.replace(
                search_text, replace_text)
            spinner.write(f"✅ 补丁 #{patch_count} 应用成功")
        else:
            # 尝试增加缩进重试
            found = False
            for space_count in range(1, 17):
                indented_search = '\n'.join(' ' * space_count + line for line in search_text.split('\n'))
                indented_replace = '\n'.join(' ' * space_count + line for line in replace_text.split('\n'))
                if indented_search in modified_content:
                    if modified_content.count(indented_search) > 1:
                        success = False
                        err_msg = f"搜索文本 {indented_search} 在文件中存在多处，请检查补丁内容"
                        break
                    modified_content = modified_content.replace(
                        indented_search, indented_replace)
                    spinner.write(f"✅ 补丁 #{patch_count} 应用成功 (自动增加 {space_count} 个空格缩进)")
                    found = True
                    break
            
            if not found:
                success = False
                err_msg = f"搜索文本 {search_text} 在文件中不存在，尝试增加1-16个空格缩进后仍未找到匹配"
                break
    if not success:
        revert_file(filepath)
        return False, err_msg


    spinner.text = f"文件 {filepath} 修改完成，应用了 {patch_count} 个补丁"
    spinner.ok("✅")
    return True, modified_content