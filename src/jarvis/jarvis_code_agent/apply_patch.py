import re
from typing import Dict, Any, List, Tuple
import os
from jarvis.tools.read_code import ReadCodeTool
from jarvis.utils import OutputType, PrettyOutput


def _parse_patch(patch_str: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse patches from string with format:
    <PATCH>
    > /path/to/file [start_line, end_line)
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
        match = re.match(r'>\s*([^\[]+)\s*\[(\d+),\s*(\d+)\)', file_info)
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
    for filepath in result:
        result[filepath].sort(key=lambda x: x['start_line'], reverse=True)
    return result


def apply_patch(output_str: str) -> str:
    """Apply patches to files"""
    patches = _parse_patch(output_str)
    if not patches:
        return ""
        
    read_tool = ReadCodeTool()
    result = []
    
    for filepath, patch_info in patches.items():
        try:
            # Check if file exists
            if not os.path.exists(filepath):
                PrettyOutput.print(f"File not found: {filepath}", OutputType.WARNING)
                continue
                
            # Read original file content
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # Apply patch
            for patch in patch_info:
                start_line = patch['start_line']
                end_line = patch['end_line']
                new_content = patch['content'].split('\n')
                
                # Validate line numbers
                if start_line < 0 or end_line > len(lines) + 1 or start_line > end_line:
                    PrettyOutput.print(f"Invalid line range [{start_line}, {end_line}) for file: {filepath}", OutputType.WARNING)
                    continue
                    
                # Create new content
                result_lines = lines[:start_line]
                result_lines.extend(line + '\n' for line in new_content)
                result_lines.extend(lines[end_line:])
                
                # Write back to file
                open(filepath, 'w', encoding='utf-8').writelines(result_lines)

                verify_start_line = min(start_line-2, 0)
                verify_end_line = max(end_line+2, len(lines))

                verify_result = read_tool.execute({
                    "filepath": filepath,
                    "start_line": verify_start_line,
                    "end_line": verify_end_line
                })

                result.append(f"Applied patch to {filepath} successfully, new content:\n{verify_result['stdout']}\n")
                PrettyOutput.section(f"Applied patch to {filepath} successfully, new content:\n{verify_result['stdout']}\n", OutputType.SUCCESS)
            
        except Exception as e:
            PrettyOutput.print(f"Error applying patch to {filepath}: {str(e)}", OutputType.ERROR)
            continue
    
    return "\n".join(result) + "Please check the changes if they are correct."
    