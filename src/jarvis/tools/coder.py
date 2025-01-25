import os
from typing import Dict, Any, Optional
from jarvis.jarvis_coder.main import JarvisCoder
from jarvis.utils import PrettyOutput, OutputType

class CoderTool:
    """代码修改工具"""
    
    name = "coder"
    description = "分析并修改现有代码，用于实现新功能、修复bug、重构代码等。能理解代码上下文并进行精确的代码编辑。"
    parameters = {
        "feature": {
            "type": "string",
            "description": "要实现的功能描述或需要修改的内容，例如：'添加日志功能'、'修复内存泄漏'、'优化性能'等",
            "required": True
        },
        "dir": {
            "type": "string", 
            "description": "项目根目录，默认为当前目录",
            "required": False
        },
        "language": {
            "type": "string",
            "description": "项目的主要编程语言，默认为python",
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
