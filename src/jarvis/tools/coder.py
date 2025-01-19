import os
from typing import Dict, Any, Optional
from jarvis.jarvis_coder.main import JarvisCoder
from jarvis.utils import PrettyOutput, OutputType

class CoderTool:
    """代码修改工具"""
    
    name = "coder"
    description = "用于自动修改和生成代码的工具"
    parameters = {
        "feature": {
            "type": "string",
            "description": "要实现的功能描述",
            "required": True
        },
        "dir": {
            "type": "string", 
            "description": "项目根目录",
            "required": False
        },
        "language": {
            "type": "string",
            "description": "编程语言",
            "required": False
        }
    }


    def _init_coder(self, dir: Optional[str] = None, language: Optional[str] = "python") -> None:
        """初始化JarvisCoder实例"""
        if not self._coder:
            import os
            work_dir = dir or os.getcwd()
            self._coder = JarvisCoder(work_dir, language)

    def execute(self, **kwargs) -> Dict[str, Any]:
        """执行代码修改
        
        Args:
            feature: 要实现的功能描述
            dir: 可选，项目根目录
            language: 可选，编程语言
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        feature = kwargs.get("feature")
        dir = kwargs.get("dir")
        language = kwargs.get("language", "python")
        
        try:
            self.current_dir = os.getcwd()
            self._init_coder(dir, language)
            result = self._coder.execute(feature)
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
