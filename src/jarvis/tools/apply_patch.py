from typing import Dict, Any
import os
from jarvis.tools.read_code import ReadCodeTool
from jarvis.utils import OutputType, PrettyOutput


class ApplyPatchTool:
    """Apply code patch tool with hexadecimal line numbers"""
    
    name = "apply_patch"
    description = "Apply code patch by replacing code within specified hexadecimal line range"
    parameters = {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Path to the file to patch"
            },
            "start_line": {
                "type": "integer",
                "description": "Start line number",
            },
            "end_line": {
                "type": "integer",
                "description": "End line number",
            },
            "new_code": {
                "type": "string",
                "description": "New code to replace the specified range"
            }
        },
        "required": ["filename", "start_line", "end_line", "new_code"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute patch application
        
        Args:
            args: Dictionary containing:
                - filename: Path to the file
                - start_line: Start line number
                - end_line: End line number
                - new_code: New code to insert
                
        Returns:
            Dict containing:
                - success: Boolean indicating success
                - stdout: Success message
                - stderr: Error message if any
        """
        try:
            filename = args["filename"].strip()
            start_line = int(args["start_line"])
            end_line = int(args["end_line"])
            new_code = args["new_code"]
            
            # Record the operation and the full path
            abs_path = os.path.abspath(filename)
            PrettyOutput.print(f"Applying patch to: {abs_path}", OutputType.INFO)
            if start_line == end_line:
                PrettyOutput.print(f"Inserting at line {start_line:04x}", OutputType.INFO)
            else:
                PrettyOutput.print(f"Replacing lines [{start_line:04x}, {end_line:04x})", OutputType.INFO)
            
            # Check if file exists
            if not os.path.exists(filename):
                PrettyOutput.print(f"File does not exist: {filename}", OutputType.WARNING)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"File does not exist: {filename}"
                }
                
            # Read file content
            try:
                lines = open(filename, 'r', encoding='utf-8').readlines()
                # auto add newline if not exists
                if lines and not lines[-1].endswith('\n'):
                    lines[-1] += '\n'
            except UnicodeDecodeError:
                PrettyOutput.print("Failed to decode file with UTF-8 encoding", OutputType.WARNING)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Failed to decode file with UTF-8 encoding"
                }
                
            # Validate line range
            if start_line < 0 or end_line < 0:
                PrettyOutput.print("Line numbers cannot be negative", OutputType.WARNING)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Line numbers cannot be negative"
                }
            
            if start_line > len(lines) or end_line > len(lines):
                PrettyOutput.print(f"Line range [{start_line}, {end_line}) out of bounds (file has {len(lines)} lines)", OutputType.WARNING)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Line range [{start_line}, {end_line}) out of bounds (file has {len(lines)} lines)"
                }
                
            if start_line > end_line:
                PrettyOutput.print(f"Invalid line range: [{start_line}, {end_line})", OutputType.WARNING)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Invalid line range: [{start_line}, {end_line})"
                }
            
            # Split new code into lines, ensuring it ends with a newline
            new_lines = new_code.splitlines(keepends=True)
            if new_lines and not new_lines[-1].endswith('\n'):
                new_lines[-1] += '\n'
            
            # Create new content by replacing the specified range
            new_content = lines[:start_line] + new_lines + lines[end_line:]
            
            # Write back to file
            try:
                open(filename, 'w', encoding='utf-8').writelines(new_content)
                new_start = max(0, start_line - 2)
                new_end = min(len(new_content), end_line + 2)
                read_code_tool = ReadCodeTool()
                code = read_code_tool.execute({
                    "filename": filename,
                    "start_line": new_start,
                    "end_line": new_end
                })
                # Update success message based on operation type
                if start_line == end_line:
                    message = f"Successfully inserted code at line {start_line:04x}"
                else:
                    message = f"Successfully replaced lines [{start_line:04x}, {end_line:04x})"

                if code["success"]:
                    message += f"\n\nCode after patch:\n{code['stdout']}\n\nPlease verify the code is correct."

                return {
                    "success": True,
                    "stdout": message,
                    "stderr": ""
                }
            except Exception as e:
                PrettyOutput.print(f"Failed to write file: {str(e)}", OutputType.WARNING)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Failed to write file: {str(e)}"
                }
            
            
        except ValueError as e:
            PrettyOutput.print(f"Invalid hexadecimal line number: {str(e)}", OutputType.WARNING)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Invalid hexadecimal line number: {str(e)}"
            }
        except Exception as e:
            PrettyOutput.print(f"Failed to apply patch: {str(e)}", OutputType.WARNING)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to apply patch: {str(e)}"
            }


def main():
    """Command line interface for the tool"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Apply code patch with hexadecimal line numbers')
    parser.add_argument('filename', help='Path to the file to patch')
    parser.add_argument('start', help='Start line number in hexadecimal (inclusive)')
    parser.add_argument('end', help='End line number in hexadecimal (exclusive)')
    parser.add_argument('code', help='New code to replace the specified range')
    
    args = parser.parse_args()
    
    tool = ApplyPatchTool()
    result = tool.execute({
        "filename": args.filename,
        "start_line": args.start,
        "end_line": args.end,
        "new_code": args.code
    })
    
    if result["success"]:
        PrettyOutput.print(result["stdout"], OutputType.SUCCESS)
    else:
        PrettyOutput.print(result["stderr"], OutputType.ERROR)
        return 1
        
    return 0


if __name__ == "__main__":
    main()
