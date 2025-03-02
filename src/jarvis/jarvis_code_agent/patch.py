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

# 🔄 REPLACE: Modify existing code
<REPLACE>
File: path/to/file
Lines: [start,end] or [start,end)
-----
new_content
</REPLACE>

# ➕ INSERT: Add new code
<INSERT>
File: path/to/file
Line: position
-----
new_content
</INSERT>

# 🗑️ DELETE: Remove existing code
<DELETE>
File: path/to/file
Lines: [start,end] or [start,end)
</DELETE>

# 🆕 NEW_FILE: Create new file
<NEW_FILE>
File: path/to/file
-----
new_content
</NEW_FILE>

# ➡️ MOVE_FILE: Relocate a file
<MOVE_FILE>
File: path/to/source/file
NewPath: path/to/destination/file
</MOVE_FILE>

# ❌ REMOVE_FILE: Delete entire file
<REMOVE_FILE>
File: path/to/file
</REMOVE_FILE>

# 📋 Formatting Rules
1. File Paths
   - Use relative paths from project root
   - Must be exact and case-sensitive
   - Example: src/module/file.py
   
2. Line Numbers
   - Format: [start,end] (inclusive) or [start,end) (right-exclusive)
   - 1-based line numbers
   - Single number for INSERT
   - Omit for NEW_FILE/REMOVE_FILE

3. Content
   - Use "-----" separator
   - Maintain original indentation
   - Follow existing code style

# 📌 Usage Examples
## REPLACE Example (Closed Interval)
<REPLACE>
File: src/utils.py
Lines: [9,13]
-----
def updated_function():
    # Replaces lines 9-13 inclusive
    return "new_implementation"
</REPLACE>

## REPLACE Example (Left-Closed Right-Open)
<REPLACE>
File: src/calculator.py
Lines: [5,8)
-----
def new_calculation():
    # Replaces lines 5-7 (excludes line 8)
    return 42
</REPLACE>

## INSERT Example
<INSERT>
File: src/main.py
Line: 19
-----
    # Inserted before line 19
    new_feature()
</INSERT>

## NEW_FILE Example
<NEW_FILE>
File: src/new_module.py
-----
# New file creation
def feature_entry():
    pass
</NEW_FILE>

## DELETE Example
<DELETE>
File: src/utils.py
Lines: [9,13]
</DELETE>

## MOVE_FILE Example
<MOVE_FILE>
File: src/old_dir/file.py
NewPath: src/new_dir/file.py
</MOVE_FILE>

## REMOVE_FILE Example
<REMOVE_FILE>
File: src/obsolete.py
</REMOVE_FILE>

# 🚨 Critical Requirements
1. One change per block
2. Use correct operation type
3. Match existing code style
4. Preserve indentation levels
5. Exact file paths required
6. Handle edge cases properly
7. Include error handling
8. Maintain code consistency
"""


def _parse_patch(patch_str: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse patches from string with optimized format"""
    result = {}
    patches = re.findall(r"<(REPLACE|INSERT|DELETE|NEW_FILE|REMOVE_FILE|MOVE_FILE)>(.*?)</\1>", patch_str, re.DOTALL)
    
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
            # Support [m,n] (closed) and [m,n) (half-open)
            line_match = re.match(r"Lines:\s*\[(\d+),\s*(\d+)(\)?)\]", lines[1])
            if line_match:
                start_line = int(line_match.group(1))
                end_value = int(line_match.group(2))
                # 修复区间处理逻辑
                if line_match.group(3):  # 右开区间 [m,n)
                    end_line = end_value - 1  # 转换为闭区间 [m, n-1]
                else:  # 闭区间 [m,n]
                    end_line = end_value
                # 确保 end_line >= start_line
                end_line = max(end_line, start_line)
        elif patch_type == 'INSERT':
            line_match = re.match(r"Line:\s*(\d+)", lines[1])
            if line_match:
                start_line = int(line_match.group(1))  # 1-based
                end_line = start_line
        elif patch_type == 'MOVE_FILE':
            new_path_match = re.match(r"NewPath:\s*([^\s]+)", lines[1])
            if new_path_match:
                new_path = new_path_match.group(1).strip()
            else:
                continue
        
        # Get content (after separator)
        separator_index = next((i for i, line in enumerate(lines) if line.strip() == "-----"), -1)
        content = '\n'.join(lines[separator_index + 1:]) if separator_index != -1 else ''

        if filepath not in result:
            result[filepath] = []
        
        # Handle MOVE_FILE specially
        if patch_type == 'MOVE_FILE':
            result[filepath].append({
                'type': patch_type,
                'new_path': new_path,
                'content': content
            })
        else:
            result[filepath].append({
                'type': patch_type,
                'start_line': start_line,
                'end_line': end_line,
                'content': content
            })
    
    # Sort patches by start line in reverse order to apply from bottom to top
    for filepath in result:
        result[filepath].sort(key=lambda x: x.get('start_line', 0), reverse=True)
    
    return result


def apply_patch(output_str: str) -> str:
    """Apply patches to files"""
    patches = _parse_patch(output_str)
    ret = ""  # Initialize return value

    for filepath, patch_info in patches.items():
        try:
            for patch in patch_info:
                patch_type = patch['type']
                
                if patch_type == 'MOVE_FILE':
                    handle_move_file(filepath, patch)
                elif patch_type == 'NEW_FILE':
                    handle_new_file(filepath, patch)
                elif patch_type == 'REMOVE_FILE':
                    handle_remove_file(filepath)
                else:
                    handle_code_operation(filepath, patch)
            
        except Exception as e:
            PrettyOutput.print(f"Application of {patch_type} operation to {filepath} failed: {str(e)}", OutputType.ERROR)
            continue

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

    return ret  # Ensure a string is always returned
    
def handle_commit_workflow()->bool:
    """Handle the git commit workflow and return the commit details.
    
    Returns:
        tuple[bool, str, str]: (continue_execution, commit_id, commit_message)
    """
    os.system("git add .")
    diff = os.popen("git diff HEAD").read()
    os.system("git reset HEAD")
    PrettyOutput.print(diff, OutputType.CODE, lang="diff")
    if not user_confirm("Do you want to commit the code?", default=True):
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

# New handler functions below ▼▼▼

def handle_move_file(filepath: str, patch: Dict[str, Any]):
    """Handle file moving operation"""
    new_path = patch['new_path']
    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    if os.path.exists(filepath):
        os.rename(filepath, new_path)
        PrettyOutput.print(f"Successfully moved file {filepath} -> {new_path}", OutputType.SUCCESS)
    else:
        PrettyOutput.print(f"Source file does not exist: {filepath}", OutputType.WARNING)

def handle_new_file(filepath: str, patch: Dict[str, Any]):
    """Handle new file creation"""
    new_content = patch.get('content', '').splitlines(keepends=True)
    if new_content and new_content[-1] and new_content[-1][-1] != '\n':
        new_content[-1] += '\n'
    
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_content)
    PrettyOutput.print(f"Successfully created new file {filepath}", OutputType.SUCCESS)

def handle_remove_file(filepath: str):
    """Handle file removal"""
    if os.path.exists(filepath):
        os.remove(filepath)
        PrettyOutput.print(f"Successfully removed file {filepath}", OutputType.SUCCESS)
    else:
        PrettyOutput.print(f"File does not exist: {filepath}", OutputType.WARNING)

def handle_code_operation(filepath: str, patch: Dict[str, Any]):
    """Handle code modification operations (REPLACE/INSERT/DELETE)"""
    patch_type = patch['type']
    start_line = patch.get('start_line', 0)
    end_line = patch.get('end_line', 0)
    new_content = patch.get('content', '').splitlines(keepends=True)

    if new_content and new_content[-1] and new_content[-1][-1] != '\n':
        new_content[-1] += '\n'

    if not os.path.exists(filepath):
        PrettyOutput.print(f"File does not exist: {filepath}", OutputType.WARNING)
        return

    with open(filepath, 'r+', encoding='utf-8') as f:
        lines = f.readlines()
        validate_and_apply_changes(patch_type, lines, start_line, end_line, new_content)
        f.seek(0)
        f.writelines(lines)
        f.truncate()

    PrettyOutput.print(f"Successfully applied {patch_type} operation to {filepath}", OutputType.SUCCESS)

def validate_and_apply_changes(
    patch_type: str,
    lines: List[str],
    start_line: int,
    end_line: int,
    new_content: List[str]
):
    """Validate and apply code changes to in-memory file content"""
    if patch_type in ['REPLACE', 'DELETE']:
        if start_line < 1 or end_line > len(lines) or start_line > end_line:
            raise ValueError(f"Invalid line range [{start_line}, {end_line}] (total lines: {len(lines)})")
        
        if patch_type == 'REPLACE':
            lines[start_line-1:end_line] = new_content
        else:  # DELETE
            lines[start_line-1:end_line] = []
            
    elif patch_type == 'INSERT':
        if start_line < 1 or start_line > len(lines) + 1:
            raise ValueError(f"Invalid insertion position [{start_line}] (valid range: 1-{len(lines)+1})")
        
        lines[start_line-1:start_line-1] = new_content
