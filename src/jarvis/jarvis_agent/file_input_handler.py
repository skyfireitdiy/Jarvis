# -*- coding: utf-8 -*-


import os
import re
from typing import Any, Tuple

from yaspin import yaspin

from jarvis.jarvis_tools.file_operation import FileOperationTool
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import is_context_overflow


def file_input_handler(user_input: str, agent: Any) -> Tuple[str, bool]:
    """处理包含文件引用的用户输入并读取文件内容。
    
    参数:
        user_input: 可能包含文件引用的输入字符串，格式为:
            - 'file_path' (整个文件)
            - 'file_path:start_line,end_line' (行范围)
            - 'file_path:start_line:end_line' (替代范围格式)
        agent: 用于进一步处理的Agent对象(当前未使用)
        
    返回:
        Tuple[str, bool]: 
            - 处理后的提示字符串，前面附加文件内容
            - 布尔值，指示是否发生上下文溢出
    """
    prompt = user_input
    files = []

    file_refs = re.findall(r"'([^'\n]+)'", user_input)
    for ref in file_refs:
        # 处理 file:start,end 或 file:start:end 格式
        if ':' in ref:
            file_path, line_range = ref.split(':', 1)
            # 使用默认值初始化
            start_line = 1  # 1-based
            end_line = -1

            # 如果指定了行范围则进行处理
            if ',' in line_range or ':' in line_range:
                try:
                    raw_start, raw_end = map(int, re.split(r'[,:]', line_range))

                    # 处理特殊值和Python风格的负索引
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors="ignore") as f:
                            total_lines = len(f.readlines())
                    except FileNotFoundError:
                        PrettyOutput.print(f"文件不存在: {file_path}", OutputType.WARNING)
                        continue
                    # 处理起始行(0表示整个文件，负数表示从末尾开始)
                    if raw_start == 0:  # 0表示整个文件
                        start_line = 1
                        end_line = total_lines
                    else:
                        start_line = raw_start if raw_start > 0 else total_lines + raw_start + 1

                    # 处理结束行
                    if raw_end == 0:  # 0表示整个文件（如果start也是0）
                        end_line = total_lines
                    else:
                        end_line = raw_end if raw_end > 0 else total_lines + raw_end + 1

                    # 自动校正范围
                    start_line = max(1, min(start_line, total_lines))
                    end_line = max(start_line, min(end_line, total_lines))

                    # 最终验证
                    if start_line < 1 or end_line > total_lines or start_line > end_line:
                        raise ValueError

                except:
                    continue

            # 如果文件存在则添加
            if os.path.isfile(file_path):
                files.append({
                    "path": file_path,
                    "start_line": start_line,
                    "end_line": end_line
                })
        else:
            # 处理简单文件路径
            if os.path.isfile(ref):
                files.append({
                    "path": ref,
                    "start_line": 1,  # 1-based
                    "end_line": -1
                })

    # 如果找到文件则读取并处理
    if files:
        with yaspin(text="正在读取文件...", color="cyan") as spinner:
            old_prompt = prompt
            result = FileOperationTool().execute({"operation":"read","files": files, "agent": agent})
            if result["success"]:
                spinner.text = "文件读取完成"
                spinner.ok("✅")
                # Prepend file contents to prompt and check for overflow
                prompt = f"""{prompt} 

<file_context>
{result["stdout"]}
</file_context>"""
                if is_context_overflow(prompt):
                    return old_prompt, False

    return prompt, False

