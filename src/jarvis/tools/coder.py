import os
from typing import Dict, Any, Optional
from jarvis.jarvis_coder.main import JarvisCoder
from jarvis.utils import PrettyOutput, OutputType

class CoderTool:
    """代码修改工具"""
    
    name = "coder"
    description = "Analyze and modify existing code for implementing new features, fixing bugs, refactoring code, etc. Can understand code context and perform precise code edits."
    parameters = {
        "feature": {
            "type": "string",
            "description": "Description of the feature to implement or content to modify, e.g., 'add logging functionality', 'fix memory leak', 'optimize performance', etc.",
            "required": True
        },
        "dir": {
            "type": "string", 
            "description": "Project root directory, defaults to current directory",
            "required": False
        },
        "language": {
            "type": "string",
            "description": "Main programming language of the project, defaults to python",
            "required": False
        }
    }

    def __init__(self):
        self._coder = None


    def _init_coder(self, dir: Optional[str] = None, language: Optional[str] = "python") -> None:
        """初始化JarvisCoder实例"""
        if not self._coder:
            import os
            work_dir = dir or os.getcwd()
            self._coder = JarvisCoder(work_dir, language)

    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行代码修改
        
        Args:
            feature: 要实现的功能描述
            dir: 可选，项目根目录
            language: 可选，编程语言
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        feature = args.get("feature")
        dir = args.get("dir")
        language = args.get("language", "python")
        
        try:
            self.current_dir = os.getcwd()
            self._init_coder(dir, language)
            result = self._coder.execute(str(feature)) # type: ignore
            return result
        except Exception as e:
            PrettyOutput.print(f"代码修改失败: {str(e)}", OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行失败: {str(e)}",
                "error": e
            } 
        finally:
            os.chdir(self.current_dir)
