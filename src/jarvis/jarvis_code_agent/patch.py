import re
from typing import Dict, Any, List, Tuple
import os
from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_tools.git_commiter import GitCommitTool
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
# 📝 Patch Format
Use patch blocks to specify code changes:

```
<PATCH>
path/to/file start,end
new_content
</PATCH>
```

# 📋 Format Rules
1. File Path
   - Use relative path from project root
   - Must be exact and case-sensitive
   - Example: src/module/file.py

2. Line Numbers
   - Format: start,end
   - start: First line to modify (included)
   - end: Line after last modified line
   - Both numbers are based on original file

3. Special Cases
   - Insert: Use same number for start,end
   - New File: Use 0,0
   - Example: "5,5" inserts before line 5

# 📌 Detailed Examples
## Example 1: Modify Existing Code
```
<PATCH>
src/utils.py 10,15
def new_function():
    # This replaces lines 10-14 in src/utils.py
    return "modified"
</PATCH>
```
Explanation:
- File: src/utils.py
- Lines: 10-14 (inclusive)
- Action: Replace existing code with new content
- Note: Line numbers are 1-based

## Example 2: Insert New Code
```
<PATCH>
src/main.py 20,20
    # This inserts before line 20
    new_line_here()
</PATCH>
```
Explanation:
- File: src/main.py
- Lines: 20,20 (same number)
- Action: Insert new code before line 20
- Note: Indentation must match surrounding code

## Example 3: Create New File
```
<PATCH>
src/new_file.py 0,0
# This creates a new file
def new_function():
    pass
</PATCH>
```
Explanation:
- File: src/new_file.py
- Lines: 0,0 (special case)
- Action: Create new file with content
- Note: Parent directories will be created if needed

## Example 4: Complex Modification
```
<PATCH>
src/controller.py 50,55
def process_request(request):
    # New implementation
    try:
        validate_request(request)
        return handle_request(request)
    except Exception as e:
        log_error(e)
        raise
</PATCH>
```
Explanation:
- File: src/controller.py
- Lines: 50-54 (inclusive)
- Action: Replace existing code with new implementation
- Note: Preserve indentation and style

# ❗ Important Rules
1. ONE modification per patch block
2. Include necessary context
3. Match existing code style
4. Preserve indentation
5. Use exact file paths
6. Handle edge cases
7. Add proper error handling
8. Maintain code consistency

# 💡 Best Practices
- Test changes locally before applying
- Keep patches focused and small
- Document complex changes
- Follow project coding standards
- Handle edge cases properly
- Preserve existing functionality
"""


def _parse_patch(patch_str: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse patches from string with format:
    <PATCH>
    path/to/file start_line,end_line
    content_line1
    content_line2
    ...
    </PATCH>
    """
    result = {}
    patches = re.findall(r"<PATCH>(.*?)</PATCH>", patch_str, re.DOTALL)
    
    for patch in patches:
        lines = patch.strip().split('\n')
        if not lines:
            continue
            
        # Parse file path and line range
        file_info = lines[0].strip()
            
        # Extract file path and line range
        match = re.match(r'([^\s]+)\s+(\d+),(\d+)', file_info)
        if not match:
            continue
            
        filepath = match.group(1).strip()
        start_line = int(match.group(2))
        end_line = int(match.group(3))
        
        # Get content lines (skip the first line with file info)
        content = '\n'.join(lines[1:])

        if filepath not in result:
            result[filepath] = []
        
        # Store in result dictionary
        result[filepath].append({
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
                start_line = patch['start_line']
                end_line = patch['end_line']
                new_content = patch['content'].splitlines(keepends=True)

                if new_content and new_content[-1] and new_content[-1][-1] != '\n':
                    new_content[-1] += '\n'

                # Handle file creation when start=end=0
                if start_line == 0 and end_line == 0:
                    # Create directory if it doesn't exist
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    # Write new file
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.writelines(new_content)
                    PrettyOutput.print(f"成功创建新文件 {filepath}", OutputType.SUCCESS)
                    continue

                # Regular patch logic for existing files
                if not os.path.exists(filepath):
                    PrettyOutput.print(f"文件不存在: {filepath}", OutputType.WARNING)
                    continue
                    
                # Read original file content
                lines = open(filepath, 'r', encoding='utf-8').readlines()
                
                # Validate line numbers
                if start_line < 0 or end_line > len(lines) + 1 or start_line > end_line:
                    PrettyOutput.print(f"无效的行范围 [{start_line}, {end_line}) 对于文件: {filepath}", OutputType.WARNING)
                    continue
                    
                # Create new content
                lines[start_line:end_line] = new_content
                
                # Write back to file
                open(filepath, 'w', encoding='utf-8').writelines(lines)

                PrettyOutput.print(f"成功应用补丁到 {filepath}", OutputType.SUCCESS)
            
        except Exception as e:
            PrettyOutput.print(f"应用补丁到 {filepath} 失败: {str(e)}", OutputType.ERROR)
            continue
    ret = ""
    if has_uncommitted_changes():
        if handle_commit_workflow():
            ret += "Successfully applied the patch\n"
            # Get modified line ranges
            modified_ranges = get_modified_line_ranges()
            read_tool = ReadCodeTool()
            modified_code = ""
            
            # Read modified sections
            for filepath, (start, end) in modified_ranges.items():
                result = read_tool._read_single_file(filepath, start, end)
                if result["success"]:
                    modified_code += f"\nModified code in {filepath}:\n{result['stdout']}\n"
            
            # Get commit details
            commit_hash = os.popen("git rev-parse HEAD").read().strip()
            commit_details = os.popen(f"git show {commit_hash} --stat").read()
            ret += f"Commit details:\n{commit_details}\nModified code sections:\n{modified_code}"
            ret += f"Commit details:\n{commit_details}"
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
