import re
from typing import Dict, Any, List
import os
from jarvis.jarvis_tools.git_commiter import GitCommitTool
from jarvis.utils import OutputType, PrettyOutput, has_uncommitted_changes, user_confirm


def _parse_patch(patch_str: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse patches from string with format:
    <PATCH>
    > /path/to/file start_line,end_line
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
        if not file_info.startswith('>'):
            continue
            
        # Extract file path and line range
        match = re.match(r'>\s*([^\s]+)\s+(\d+),(\d+)', file_info)
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
                    PrettyOutput.print(f"Created new file {filepath} successfully\n", OutputType.SUCCESS)
                    continue

                # Regular patch logic for existing files
                if not os.path.exists(filepath):
                    PrettyOutput.print(f"File not found: {filepath}", OutputType.WARNING)
                    continue
                    
                # Read original file content
                lines = open(filepath, 'r', encoding='utf-8').readlines()
                
                # Validate line numbers
                if start_line < 0 or end_line > len(lines) + 1 or start_line > end_line:
                    PrettyOutput.print(f"Invalid line range [{start_line}, {end_line}) for file: {filepath}", OutputType.WARNING)
                    continue
                    
                # Create new content
                lines[start_line:end_line] = new_content
                
                # Write back to file
                open(filepath, 'w', encoding='utf-8').writelines(lines)

                PrettyOutput.print(f"Applied patch to {filepath} successfully\n", OutputType.SUCCESS)
            
        except Exception as e:
            PrettyOutput.print(f"Error applying patch to {filepath}: {str(e)}", OutputType.ERROR)
            continue
    
    if has_uncommitted_changes():
        handle_commit_workflow()
    return ""
    
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