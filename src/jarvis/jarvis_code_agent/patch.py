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
# 📝 Code Modification Format
Use specific blocks for different operations:

# 🔄 REPLACE: Replace existing code
<REPLACE>
File: path/to/file
Lines: start-end
-----
new_content
</REPLACE>

# ➕ INSERT: Insert new code
<INSERT>
File: path/to/file
Line: position
-----
new_content
</INSERT>

# 🗑️ DELETE: Remove existing code
<DELETE>
File: path/to/file
Lines: start-end
</DELETE>

# 🆕 NEW_FILE: Create new file
<NEW_FILE>
File: path/to/file
-----
new_content
</NEW_FILE>

# ➡️ MOVE_FILE: Move a file to a new location
<MOVE_FILE>
File: path/to/source/file
NewPath: path/to/destination/file
</MOVE_FILE>
# ❌ REMOVE_FILE: Delete entire file
<REMOVE_FILE>
File: path/to/file
</REMOVE_FILE>

# 📋 Format Rules
1. File Path
   - Use relative path from project root
   - Must be exact and case-sensitive
   - Example: src/module/file.py

2. Line Numbers
   - Format: start-end (inclusive)
   - Line numbers are 0-based
   - Use single number for INSERT
   - Omit for NEW_FILE and REMOVE_FILE

3. Content
   - Use "-----" separator
   - Preserve indentation
   - Match existing code style

# 📌 Detailed Examples
## Example 1: Replace Code
<REPLACE>
File: src/utils.py
Lines: 9-13
-----
def new_function():
    # This replaces lines 9-13
    return "modified"
</REPLACE>

## Example 2: Insert Code
<INSERT>
File: src/main.py
Line: 19
-----
    # This inserts before line 19
    new_line_here()
</INSERT>

## Example 3: Create New File
<NEW_FILE>
File: src/new_file.py
-----
# This creates a new file
def new_function():
    pass
</NEW_FILE>

## Example 4: Delete Code
<DELETE>
File: src/utils.py
Lines: 9-13
</DELETE>

## Example 6: Move File
<MOVE_FILE>
File: src/old_location/file.py
NewPath: src/new_location/file.py
</MOVE_FILE>
## Example 5: Remove File
<REMOVE_FILE>
File: src/old_file.py
</REMOVE_FILE>

# ❗ Important Rules
1. ONE modification per block
2. Use correct block type for the operation
3. Match existing code style
4. Preserve indentation
5. Use exact file paths
6. Handle edge cases
7. Add proper error handling
8. Maintain code consistency
"""


def _parse_patch(patch_str: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse patches from string with optimized format"""
    result = {}
    patches = re.findall(r"<(REPLACE|INSERT|DELETE|NEW_FILE|REMOVE_FILE)>(.*?)</\1>", patch_str, re.DOTALL)
    
    for patch_type, patch in patches:
        lines = patch.strip().split('\n')
        if not lines:
            continue
            
        # Parse file path
        file_match = re.match(r"File:\s*([^\s]+)", lines[0])
        if not file_match:
            continue
        filepath = file_match.group(1).strip()
        
        # Initialize line numbers
        start_line = end_line = 0
        
        # Parse line numbers based on operation type
        if patch_type in ['REPLACE', 'DELETE']:
            line_match = re.match(r"Lines:\s*(\d+)-(\d+)", lines[1])
            if line_match:
                start_line = int(line_match.group(1))  # 0-based
                end_line = int(line_match.group(2))    # inclusive
        elif patch_type == 'INSERT':
            line_match = re.match(r"Line:\s*(\d+)", lines[1])
            if line_match:
                start_line = int(line_match.group(1))  # 0-based
                end_line = start_line
        
        # Get content (after separator)
        separator_index = next((i for i, line in enumerate(lines) if line.strip() == "-----"), -1)
        content = '\n'.join(lines[separator_index + 1:]) if separator_index != -1 else ''

        if filepath not in result:
            result[filepath] = []
        
        result[filepath].append({
            'type': patch_type,
            'start_line': start_line,
            'end_line': end_line,
            'content': content
        })
    
    # Sort patches by start line in reverse order to apply from bottom to top
    for filepath in result:
        result[filepath].sort(key=lambda x: x['start_line'], reverse=True)
    
    return result


def apply_patch(output_str: str)->str:
    """Apply patches to files"""
    patches = _parse_patch(output_str)

    for filepath, patch_info in patches.items():
        try:
            for patch in patch_info:
                patch_type = patch['type']
                start_line = patch['start_line']
                end_line = patch['end_line']
                new_content = patch['content'].splitlines(keepends=True)

                if new_content and new_content[-1] and new_content[-1][-1] != '\n':
                    new_content[-1] += '\n'

                # Handle different patch types
                if patch_type == 'NEW_FILE':
                    # Create directory if it doesn't exist
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    # Write new file
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.writelines(new_content)
                    PrettyOutput.print(f"成功创建新文件 {filepath}", OutputType.SUCCESS)
                    continue
                elif patch_type == 'REMOVE_FILE':
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        PrettyOutput.print(f"成功删除文件 {filepath}", OutputType.SUCCESS)
                    else:
                        PrettyOutput.print(f"文件不存在: {filepath}", OutputType.WARNING)
                    continue

                # For other operations, file must exist
                if not os.path.exists(filepath):
                    PrettyOutput.print(f"文件不存在: {filepath}", OutputType.WARNING)
                    continue
                    
                # Read original file content
                lines = open(filepath, 'r', encoding='utf-8').readlines()
                
                # Validate line numbers
                if start_line < 0 or end_line > len(lines) + 1 or start_line > end_line:
                    PrettyOutput.print(f"无效的行范围 [{start_line}, {end_line}) 对于文件: {filepath}", OutputType.WARNING)
                    continue
                    
                # Handle different patch types
                if patch_type == 'REPLACE':
                    lines[start_line:end_line] = new_content
                elif patch_type == 'DELETE':
                    lines[start_line:end_line] = []
                elif patch_type == 'INSERT':
                    lines[start_line:start_line] = new_content
                
                # Write back to file
                open(filepath, 'w', encoding='utf-8').writelines(lines)

                PrettyOutput.print(f"成功应用{patch_type}操作到 {filepath}", OutputType.SUCCESS)
            
        except Exception as e:
            PrettyOutput.print(f"应用{patch_type}操作到 {filepath} 失败: {str(e)}", OutputType.ERROR)
            continue
    ret = ""
    if has_uncommitted_changes():
        if handle_commit_workflow():
            ret += "Successfully applied the patch\n"
            # Get modified line ranges
            modified_ranges = get_modified_line_ranges()
            modified_code = ReadCodeTool().execute({"files": [{"path": filepath, "start_line": start, "end_line": end} for filepath, (start, end) in modified_ranges.items()]})
            if modified_code["success"]:
                ret += "New code:\n"
                ret += modified_code["stdout"]
        else:
            ret += "User rejected the patch"
        user_input = get_multiline_input("你可以继续输入: ")
        if user_input:
            ret += "\n" + user_input
        else:
            return ""
    return ret
    
def handle_commit_workflow()->bool:
    """Handle the git commit workflow and return the commit details.
    
    Returns:
        tuple[bool, str, str]: (continue_execution, commit_id, commit_message)
    """
    os.system("git add .")
    diff = os.popen("git diff HEAD").read()
    os.system("git reset HEAD")
    PrettyOutput.print(diff, OutputType.CODE, lang="diff")
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
        for modified sections. Line numbers are 0-based.
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
            start_line = int(range_match.group(1)) - 1  # Convert to 0-based
            line_count = int(range_match.group(2)) if range_match.group(2) else 1
            end_line = start_line + line_count
            result[current_file] = (start_line, end_line)
    
    return result
