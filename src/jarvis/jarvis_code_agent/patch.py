import re
from typing import Dict, Any, List, Tuple
import os
from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_tools.git_commiter import GitCommitTool
from jarvis.jarvis_tools.read_code import ReadCodeTool
from jarvis.jarvis_utils import OutputType, PrettyOutput, get_multiline_input, has_uncommitted_changes, user_confirm


class PatchOutputHandler(OutputHandler):
    def name(self) -> str:
        return "PATCH"

    def handle(self, response: str) -> Tuple[bool, Any]:
        return False, apply_patch(response)
    
    def can_handle(self, response: str) -> bool:
        if _parse_patch(response):
            return True
        return False
    
    def prompt(self) -> str:
        return """
# 🛠️ Code Patch Specification

## Output Format:

Ouput multiple patches, each patch is a <PATCH> block.

--------------------------------
# [OPERATION] on [FILE]: Lines [RANGE]
# Reason: [CLEAR EXPLANATION]
<PATCH>
[FILE] [RANGE]
[CONTENT]
</PATCH>
--------------------------------

Explain:
- [OPERATION]: The operation to be performed, including:
  - INSERT: Insert code before the specified line, [RANGE] should be [m,m)
  - REPLACE: Replace code in the specified range, [RANGE] should be [m,n] or [m,n), n>m
  - DELETE: Delete code in the specified range, [RANGE] should be [m,n] or [m,n), n>m
  - NEW_FILE: Create a new file, [RANGE] should be [1,1)
- [FILE]: The path of the file to be modified
- [RANGE]: The range of the lines to be modified, [m,n] includes both m and n, [m,n) includes m but excludes n
- [CONTENT]: The content of the code to be modified, if the operation is delete, the [CONTENT] is empty

When making changes, you MUST:
0. Pay attention to context continuity, do not break the existing code structure, pay attention to boundary code situations, such as not including original code when inserting, and not including lines before the replacement when replacing
1. Maintain original code style and compatibility:
   - Preserve existing indentation levels
   - Keep surrounding empty lines
   - Match variable naming conventions
   - Maintain API compatibility
2. Strictly follow the exact patch format below
3. Use separate <PATCH> blocks for different files
4. Include ONLY modified lines in content
5. Line number provide rules:
   - [m,n] includes both m and n
   - [m,n) includes m but excludes n

Critical Rules:
- NEVER include unchanged code in patch content
- ONLY show lines that are being modified/added
- Maintain original line breaks around modified sections
- Preserve surrounding comments unless explicitly modifying them
"""


def _parse_patch(patch_str: str) -> Dict[str, List[Dict[str, Any]]]:
    """解析补丁格式"""
    result = {}
    # 更新正则表达式以更好地处理文件路径和范围
    header_pattern = re.compile(
        r'^\s*"?([^\n\r\[]+)"?\s*\[(\d+)(?:,(\d+))?([\]\)])\s*$',  # 匹配文件路径和行号
        re.ASCII
    )
    patches = re.findall(r'<PATCH>\n?(.*?)\n?</PATCH>', patch_str, re.DOTALL)
    
    for patch in patches:
        parts = patch.split('\n', 1)
        if len(parts) < 1:
            continue
        header_line = parts[0].strip()
        content = parts[1] if len(parts) > 1 else ''
        
        if content and not content.endswith('\n'):
            content += '\n'
            
        # 解析文件路径和行号
        header_match = header_pattern.match(header_line)
        if not header_match:
            PrettyOutput.print(f"无法解析补丁头: {header_line}", OutputType.WARNING)
            continue

        filepath = header_match.group(1).strip()
        
        try:
            start = int(header_match.group(2))  # 保持1-based行号
            end = int(header_match.group(3)) if header_match.group(3) else start
            range_type = header_match.group(4)  # ] 或 ) 表示范围类型
        except (ValueError, IndexError) as e:
            PrettyOutput.print(f"解析行号失败: {str(e)}", OutputType.WARNING)
            continue

        # 根据范围类型调整结束行号
        if range_type == ')':  # 对于 [m,n) 格式，不包括第n行
            end = end
        else:  # 对于 [m,n] 格式，包括第n行
            end = end + 1

        if filepath not in result:
            result[filepath] = []
        result[filepath].append({
            'filepath': filepath,
            'start': start,
            'end': end,
            'content': content
        })
    for filepath in result.keys():
        result[filepath] = sorted(result[filepath], key=lambda x: x['start'], reverse=True)
    return result


def apply_patch(output_str: str) -> str:
    """Apply patches to files"""
    try:
        patches = _parse_patch(output_str)
    except Exception as e:
        PrettyOutput.print(f"解析补丁失败: {str(e)}", OutputType.ERROR)
        return ""

    ret = ""
    
    for filepath, patch_list in patches.items():
        for i, patch in enumerate(patch_list):
            try:
                err = handle_code_operation(filepath, patch)
                if err:
                    PrettyOutput.print(err, OutputType.WARNING)
                    revert_change()
                    return err
                PrettyOutput.print(f"成功为文件{filepath}应用补丁{i+1}/{len(patch_list)}", OutputType.SUCCESS)
            except Exception as e:
                PrettyOutput.print(f"操作失败: {str(e)}", OutputType.ERROR)
    
    if has_uncommitted_changes():
        diff = get_diff()
        if handle_commit_workflow(diff):
            ret += "Successfully applied the patch\n"
            # Get modified line ranges
            modified_ranges = get_modified_line_ranges()
            modified_code = ReadCodeTool().execute({"files": [{"path": filepath, "start_line": start, "end_line": end} for filepath, (start, end) in modified_ranges.items()]})
            if modified_code["success"]:
                ret += "New code:\n"
                ret += modified_code["stdout"]
        else:
            ret += "User rejected the patch\nThis is your patch preview:\n"
            ret += diff
        user_input = get_multiline_input("你可以继续输入（输入空行重试，Ctrl+C退出）: ")
        if user_input:
            ret += "\n" + user_input
        else:
            ret = ""

    return ret  # Ensure a string is always returned

def get_diff() -> str:
    """使用更安全的subprocess代替os.system"""
    import subprocess
    try:
        subprocess.run(['git', 'add', '.'], check=True)
        result = subprocess.run(
            ['git', 'diff', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    finally:
        subprocess.run(['git', 'reset', 'HEAD'], check=True)

def revert_change():
    import subprocess
    subprocess.run(['git', 'reset', 'HEAD'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['git', 'checkout', '--', '.'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['git', 'clean', '-fd'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def handle_commit_workflow(diff:str)->bool:
    """Handle the git commit workflow and return the commit details.
    
    Returns:
        tuple[bool, str, str]: (continue_execution, commit_id, commit_message)
    """
    if not user_confirm("是否要提交代码？", default=True):
        revert_change()
        return False

    git_commiter = GitCommitTool()
    commit_result = git_commiter.execute({})
    return commit_result["success"]

def get_modified_line_ranges() -> Dict[str, Tuple[int, int]]:
    """Get modified line ranges from git diff for all changed files.
    
    Returns:
        Dictionary mapping file paths to tuple with (start_line, end_line) ranges
        for modified sections. Line numbers are 1-based.
    """
    # Get git diff for all files
    diff_output = os.popen("git show").read()
    
    # Parse the diff to get modified files and their line ranges
    result = {}
    current_file = None
    
    for line in diff_output.splitlines():
        # Match lines like "+++ b/path/to/file"
        file_match = re.match(r"^\+\+\+ b/(.*)", line)
        if file_match:
            current_file = file_match.group(1)
            continue
            
        # Match lines like "@@ -100,5 +100,7 @@" where the + part shows new lines
        range_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if range_match and current_file:
            start_line = int(range_match.group(1))  # Keep as 1-based
            line_count = int(range_match.group(2)) if range_match.group(2) else 1
            end_line = start_line + line_count - 1
            result[current_file] = (start_line, end_line)
    
    return result
# New handler functions below ▼▼▼

def handle_new_file(filepath: str, patch: Dict[str, Any]):
    """统一参数格式处理新文件"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(patch['content'])

def handle_code_operation(filepath: str, patch: Dict[str, Any]) -> str:
    """处理紧凑格式补丁"""
    try:
        # 新建文件时强制覆盖
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        if not os.path.exists(filepath):
            open(filepath, 'w', encoding='utf-8').close()
        with open(filepath, 'r+', encoding='utf-8') as f:
            lines = f.readlines()
            
            new_lines = validate_and_apply_changes(
                lines,
                patch['start'],
                patch['end'],
                patch['content']
            )
            
            f.seek(0)
            f.writelines(new_lines)
            f.truncate()
        PrettyOutput.print(f"成功更新 {filepath}", OutputType.SUCCESS)
        return ""
    except Exception as e:
        error_msg = f"Failed to handle code operation: {str(e)}"
        PrettyOutput.print(error_msg, OutputType.ERROR)
        return error_msg
def validate_and_apply_changes(
    lines: List[str],
    start: int,
    end: int,
    content: str
) -> List[str]:
    new_content = content.splitlines(keepends=True)
    
    # 插入操作处理
    if start == end:
        if start < 1 or start > len(lines)+1:
            raise ValueError(f"无效插入位置: {start}")
        return lines[:start-1] + new_content + lines[start-1:]
    
    # 范围替换/删除操作
    if start > end:
        raise ValueError(f"起始行{start}不能大于结束行{end}")
    
    max_line = len(lines)
    # 自动修正行号范围
    start = max(1, min(start, max_line+1))
    end = max(start, min(end, max_line+1))
    
    # 执行替换
    return lines[:start-1] + new_content + lines[end-1:]
