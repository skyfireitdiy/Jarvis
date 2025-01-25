from typing import Dict, Any
import os
from jarvis.utils import PrettyOutput, OutputType

class ChdirTool:
    """修改当前工作目录的工具"""
    
    name = "chdir"
    description = "修改当前工作目录"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要切换到的目录路径，支持相对路径和绝对路径"
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
                    "error": f"目录不存在: {path}"
                }
                
            # 检查是否是目录
            if not os.path.isdir(path):
                return {
                    "success": False,
                    "error": f"路径不是目录: {path}"
                }
                
            # 尝试切换目录
            old_path = os.getcwd()
            os.chdir(path)
            
            return {
                "success": True,
                "stdout": f"已切换工作目录:\n从: {old_path}\n到: {path}",
                "stderr": ""
            }
            
        except PermissionError:
            return {
                "success": False,
                "error": f"没有权限访问目录: {path}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"切换目录失败: {str(e)}"
            }
            
def main():
    """命令行直接运行工具"""
    import argparse
    
    parser = argparse.ArgumentParser(description='修改当前工作目录')
    parser.add_argument('path', help='要切换到的目录路径')
    args = parser.parse_args()
    
    tool = ChdirTool()
    result = tool.execute({"path": args.path})
    
    if result["success"]:
        PrettyOutput.print(result["stdout"], OutputType.SUCCESS)
    else:
        PrettyOutput.print(result["error"], OutputType.ERROR)
        
if __name__ == "__main__":
    main() 