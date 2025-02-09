from typing import Dict, Any
import os
from jarvis.utils import PrettyOutput, OutputType

class ChdirTool:
    """修改当前工作目录的工具"""
    
    name = "chdir"
    description = "Change current working directory"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to switch to, supports both relative and absolute paths"
            }
        },
        "required": ["path"]
    }
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行目录切换
        
        Args:
            args: 包含 path 参数的字典
            
        Returns:
            执行结果字典，包含:
            - success: 是否成功
            - stdout: 成功时的输出信息
            - error: 失败时的错误信息
        """
        try:
            path = os.path.expanduser(args["path"])  # 展开 ~ 等路径
            path = os.path.abspath(path)  # 转换为绝对路径
            
            # 检查目录是否存在
            if not os.path.exists(path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Directory does not exist: {path}"
                }
                
            # 检查是否是目录
            if not os.path.isdir(path):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"The path is not a directory: {path}"
                }
                
            # 尝试切换目录
            old_path = os.getcwd()
            os.chdir(path)
            
            return {
                "success": True,
                "stdout": f"Changed working directory:\nFrom: {old_path}\nTo: {path}",
                "stderr": ""
            }
            
        except PermissionError:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"No permission to access directory: {path}"
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Failed to switch directory: {str(e)}"
            }
            
def main():
    """命令行直接运行工具"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Change current working directory')
    parser.add_argument('path', help='Directory path to switch to, supports both relative and absolute paths')
    args = parser.parse_args()
    
    tool = ChdirTool()
    result = tool.execute({"path": args.path})
    
    if result["success"]:
        PrettyOutput.print(result["stdout"], OutputType.SUCCESS)
    else:
        PrettyOutput.print(result["stderr"], OutputType.ERROR)
        
if __name__ == "__main__":
    main() 