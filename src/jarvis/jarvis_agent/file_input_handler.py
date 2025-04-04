

import os
import re
from typing import Any, Tuple

from yaspin import yaspin

from jarvis.jarvis_tools.file_operation import FileOperationTool
from jarvis.jarvis_utils.config import INPUT_WINDOW_REVERSE_SIZE, get_max_input_token_count
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


def file_input_handler(user_input: str, agent: Any) -> Tuple[str, bool]:
    prompt = user_input
    files = []

    file_refs = re.findall(r"'([^']+)'", user_input)
    for ref in file_refs:
        # Handle file:start,end or file:start:end format
        if ':' in ref:
            file_path, line_range = ref.split(':', 1)
            # Initialize with default values
            start_line = 1  # 1-based
            end_line = -1

            # Process line range if specified
            if ',' in line_range or ':' in line_range:
                try:
                    raw_start, raw_end = map(int, re.split(r'[,:]', line_range))

                    # Handle special values and Python-style negative indices
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors="ignore") as f:
                            total_lines = len(f.readlines())
                    except FileNotFoundError:
                        PrettyOutput.print(f"文件不存在: {file_path}", OutputType.WARNING)
                        continue
                    # Process start line
                    if raw_start == 0:  # 0表示整个文件
                        start_line = 1
                        end_line = total_lines
                    else:
                        start_line = raw_start if raw_start > 0 else total_lines + raw_start + 1

                    # Process end line
                    if raw_end == 0:  # 0表示整个文件（如果start也是0）
                        end_line = total_lines
                    else:
                        end_line = raw_end if raw_end > 0 else total_lines + raw_end + 1

                    # Auto-correct ranges
                    start_line = max(1, min(start_line, total_lines))
                    end_line = max(start_line, min(end_line, total_lines))

                    # Final validation
                    if start_line < 1 or end_line > total_lines or start_line > end_line:
                        raise ValueError

                except:
                    continue

            # Add file if it exists
            if os.path.isfile(file_path):
                files.append({
                    "path": file_path,
                    "start_line": start_line,
                    "end_line": end_line
                })
        else:
            # Handle simple file path
            if os.path.isfile(ref):
                files.append({
                    "path": ref,
                    "start_line": 1,  # 1-based
                    "end_line": -1
                })

    # Read and process files if any were found
    if files:
        with yaspin(text="正在读取文件...", color="cyan") as spinner:
            old_prompt = prompt
            result = FileOperationTool().execute({"operation":"read","files": files})
            if result["success"]:
                spinner.text = "文件读取完成"
                spinner.ok("✅")
                prompt = result["stdout"] + "\n" + prompt
                if get_context_token_count(prompt) > get_max_input_token_count() - INPUT_WINDOW_REVERSE_SIZE:
                    with spinner.hidden():
                        agent.model.upload_files([f["path"] for f in files])
                    return old_prompt, False

    return prompt, False

