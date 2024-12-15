import os
from typing import Dict, Any

def write_to_file(content: str, filename: str, mode: str = 'w') -> Dict[str, Any]:
    """Write content to file"""
    try:
        with open(filename, mode, encoding='utf-8') as f:
            f.write(str(content))
            if not content.endswith('\n'):
                f.write('\n')
        return {
            "success": True,
            "message": f"Content written to file {filename}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to write file: {str(e)}"
        }

def read_from_file(filename: str) -> Dict[str, Any]:
    """Read content from file"""
    try:
        if not os.path.exists(filename):
            return {
                "success": False,
                "error": f"File not found: {filename}"
            }
        
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        return {
            "success": True,
            "content": content
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to read file: {str(e)}"
        } 