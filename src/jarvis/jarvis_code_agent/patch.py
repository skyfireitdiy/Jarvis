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
# 🛠️ Simplified Patch Format
<PATCH>
File path [Operation position]
Code content
</PATCH>

Operation types:
- Replace/Delete: [Start line,End line) e.g. [5,8)
- Insert: Single line number [5] means insert before line 5
- New file: [0]

Examples:
<PATCH>
src/app.py [5,8)  # 替换5-7行（包含5，不包含8）
def new_feature():
    return result * 2
</PATCH>

<PATCH>
utils.py [3]  # Insert before line 3
logger.info("Inserted content")
</PATCH>

<PATCH>
config.yaml [0]  # Create/overwrite file
database:
  host: 127.0.0.1
</PATCH>

<PATCH>
src/old.py [10,16)  # 删除10-15行
</PATCH>
"""


def _parse_patch(patch_str: str) -> Dict[str, List[Dict[str, Any]]]:
    """解析左闭右开格式"""
    result = {}
    # 使用更精确的正则匹配，支持带空格路径
    header_pattern = re.compile(
        r'^"?(.+?)"?\s*\[(\d+)(?:,(\d+))?\]$'  # 支持带引号的路径
    )
    patches = re.findall(r'<PATCH>(.*?)</PATCH>', patch_str, re.DOTALL)
    
    for patch in patches:
        lines = [l.strip() for l in patch.strip().split('\n') if l.strip()]
        if len(lines) < 2:
            continue

        # 解析文件路径和行号
        header_match = header_pattern.match(lines[0])
        if not header_match:
            continue

        filepath = header_match.group(1)
        start = int(header_match.group(2))
        end = int(header_match.group(3)) + 1 if header_match.group(3) else start

        # 存储参数
        if filepath not in result:
            result[filepath] = []
        result[filepath].append({
            'filepath': filepath,
            'start': start,
            'end': end,
            'content': '\n'.join(lines[1:]) + '\n'
        })

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
        for patch in patch_list:
            try:
                handle_code_operation(filepath, patch)
                PrettyOutput.print(f"成功处理 操作", OutputType.SUCCESS)
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

def handle_commit_workflow(diff:str)->bool:
    """Handle the git commit workflow and return the commit details.
    
    Returns:
        tuple[bool, str, str]: (continue_execution, commit_id, commit_message)
    """
    if not user_confirm("是否要提交代码？", default=True):
        os.system("git reset HEAD")
        os.system("git checkout -- .")
        os.system("git clean -fd")
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

def handle_code_operation(filepath: str, patch: Dict[str, Any]):
    """处理紧凑格式补丁"""
    try:
        # 新建文件时强制覆盖
        if patch['start'] == 0:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            mode = 'w'  # 写模式覆盖文件
        else:
            mode = 'r+'
        
        with open(filepath, mode, encoding='utf-8') as f:
            lines = f.readlines() if mode == 'r+' else []
            
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

    except Exception as e:
        PrettyOutput.print(f"操作失败: {str(e)}", OutputType.ERROR)

def validate_and_apply_changes(
    lines: List[str],
    start: int,
    end: int,
    content: str
) -> List[str]:
    # 插入操作处理
    if start == end:  # 单个行号插入
        if start < 1 or start > len(lines)+1:
            raise ValueError(f"无效插入位置: {start}")
        lines.insert(start-1, content)
        return lines
    
    # 范围操作处理（保持左闭右开）
    if 1 <= start < end:  # 现在end是转换后的值
        # 新增行号范围校验
        if start < 0 or end < 0:
            raise ValueError(f"行号不能为负数: [{start}-{end}]")
        
        # 新增最大行号限制
        max_lines = len(lines)
        if max_lines > 0 and end > max_lines + 1:  # 允许插入到文件末尾之后
            raise ValueError(f"结束行号{end}超出文件范围({max_lines})")

        # 处理空文件插入
        if not lines and start == 1 and end == 1:
            return content.splitlines(keepends=True)
        
        # 处理删除全部内容
        if start == 1 and end >= len(lines):
            return []

        # 新建/覆盖文件
        if start == 0:
            # 返回新内容（覆盖旧内容）
            return content.splitlines(keepends=True)
        
        # 自动修正逻辑保持end为切片右边界
        if end > max_lines:
            new_end = max_lines
            PrettyOutput.print(f"警告：结束行号{end+1}超出文件范围，已自动修正为{new_end}", OutputType.WARNING)
            end = new_end
        
        if start <= end <= max_lines:
            lines[start-1:end-1] = content.splitlines(keepends=True)
            return lines
    
    raise ValueError(f"无效行范围 [{start}-{end})")
