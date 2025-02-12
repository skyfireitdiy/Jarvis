from typing import Dict, Any
import os
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
                "type": "string",
                "description": "Start line number in hexadecimal (inclusive)",
                "pattern": "^[0-9a-fA-F]+$"
            },
            "end_line": {
                "type": "string",
                "description": "End line number in hexadecimal (exclusive)",
                "pattern": "^[0-9a-fA-F]+$"
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
                - start_line: Hex string of start line number (inclusive)
                - end_line: Hex string of end line number (exclusive)
                - new_code: New code to insert
                
        Returns:
            Dict containing:
                - success: Boolean indicating success
                - stdout: Success message
                - stderr: Error message if any
        """
        try:
            filename = args["filename"]
            # Convert hex strings to integers
            start_line = int(args["start_line"], 16)
            end_line = int(args["end_line"], 16)
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
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"File does not exist: {filename}"
                }
                
            # Read file content
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Failed to decode file with UTF-8 encoding"
                }
                
            # Validate line range
            if start_line < 0 or end_line < 0:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Line numbers cannot be negative"
                }
            
            if start_line > len(lines) or end_line > len(lines):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Line range [{start_line:04x}, {end_line:04x}) out of bounds (file has {len(lines)} lines)"
                }
                
            if start_line > end_line:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Invalid line range: [{start_line:04x}, {end_line:04x})"
                }
            
            # Split new code into lines, ensuring it ends with a newline
            new_lines = new_code.splitlines(keepends=True)
            if new_lines and not new_lines[-1].endswith('\n'):
                new_lines[-1] += '\n'
            
            # Create new content by replacing the specified range
            new_content = lines[:start_line] + new_lines + lines[end_line:]
            
            # Write back to file
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.writelines(new_content)
            except Exception as e:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Failed to write file: {str(e)}"
                }
            
            # Update success message based on operation type
            if start_line == end_line:
                message = f"Successfully inserted code at line {start_line:04x}"
            else:
                message = f"Successfully replaced lines [{start_line:04x}, {end_line:04x})"
            
            return {
                "success": True,
                "stdout": message,
                "stderr": ""
            }
            
        except ValueError as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Invalid hexadecimal line number: {str(e)}"
            }
        except Exception as e:
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
