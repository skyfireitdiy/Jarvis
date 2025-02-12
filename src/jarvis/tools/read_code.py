from typing import Dict, Any
import os
from jarvis.utils import OutputType, PrettyOutput


class ReadCodeTool:
    """Read code file with hexadecimal line numbers"""
    
    name = "read_code"
    description = "Read code file with hexadecimal line numbers (4 digits)"
    parameters = {
        "type": "object",
        "properties": {
            "filepath": {
                "type": "string",
                "description": "Absolute or relative path to the file"
            },
            "start_line": {
                "type": "integer",
                "description": "Start line number (0-based, inclusive)",
                "default": 0
            },
            "end_line": {
                "type": "integer",
                "description": "End line number (0-based, exclusive). -1 means read to end",
                "default": -1
            }
        },
        "required": ["filepath"]
    }

    def execute(self, args: Dict) -> Dict[str, Any]:
        """Execute code reading with line numbers
        
        Args:
            args: Dictionary containing:
                - filepath: Path to the file
                - start_line: Start line number (optional)
                - end_line: End line number (optional)
                
        Returns:
            Dict containing:
                - success: Boolean indicating success
                - stdout: File content with line numbers
                - stderr: Error message if any
        """
        try:
            filepath = args["filepath"]
            start_line = args.get("start_line", 0)
            end_line = args.get("end_line", -1)
            
            # Record the operation and the full path
            abs_path = os.path.abspath(filepath)
            PrettyOutput.print(f"Reading code file: {abs_path}", OutputType.INFO)
            
            # Check if file exists
            if not os.path.exists(filepath):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"File does not exist: {filepath}"
                }
                
            # Check file size
            if os.path.getsize(filepath) > 10 * 1024 * 1024:  # 10MB
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "File too large (>10MB)"
                }
                
            # Read file content
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Failed to decode file with UTF-8 encoding"
                }
                
            # Validate line range
            if start_line < 0:
                start_line = 0
            if end_line == -1 or end_line > len(lines):
                end_line = len(lines)
            if start_line >= end_line:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Invalid line range: [{start_line}, {end_line})"
                }
                
            # Format lines with hexadecimal line numbers
            formatted_lines = []
            for i, line in enumerate(lines[start_line:end_line]):
                line_num = start_line + i
                formatted_lines.append(f"{line_num:04x}{line}")
                
            content = "".join(formatted_lines)
            
            return {
                "success": True,
                "stdout": content,
                "stderr": ""
            }
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to read code: {str(e)}"
            }


def main():
    """Command line interface for the tool"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Read code file with line numbers')
    parser.add_argument('filepath', help='Path to the code file')
    parser.add_argument('--start', type=int, default=0, help='Start line number (0-based)')
    parser.add_argument('--end', type=int, default=-1, help='End line number (0-based)')
    
    args = parser.parse_args()
    
    tool = ReadCodeTool()
    result = tool.execute({
        "filepath": args.filepath,
        "start_line": args.start,
        "end_line": args.end
    })
    
    if result["success"]:
        print(result["stdout"])
    else:
        PrettyOutput.print(result["stderr"], OutputType.ERROR)
        return 1
        
    return 0


if __name__ == "__main__":
    main()
