import os
import time
import subprocess
import sys
import pkgutil
from pathlib import Path
from typing import Dict, Any, Optional
from ..utils import PrettyOutput, OutputType

class PythonScript:
    """Python脚本管理类"""
    SCRIPTS_DIR = "/tmp/ai_scripts"

    @classmethod
    def init_scripts_dir(cls):
        """初始化脚本目录"""
        Path(cls.SCRIPTS_DIR).mkdir(parents=True, exist_ok=True)

    @classmethod
    def generate_script_path(cls, name: Optional[str] = None) -> str:
        """生成脚本文件路径"""
        if name:
            safe_name = "".join(c for c in name if c.isalnum() or c in "._- ")
            filename = f"{int(time.time())}_{safe_name}.py"
        else:
            filename = f"{int(time.time())}_script.py"
        return str(Path(cls.SCRIPTS_DIR) / filename)

class PythonScriptTool:
    name = "execute_python"
    description = """Execute Python code and return the results.
    Notes:
    1. Use print() to output results
    2. Automatic dependency management
    3. Code saved to temporary file
    """
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute"
            },
            "dependencies": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Python package dependencies",
                "default": []
            },
            "name": {
                "type": "string",
                "description": "Script name",
                "default": ""
            }
        },
        "required": ["code"]
    }

    @staticmethod
    def _is_builtin_package(package_name: str) -> bool:
        package_name = package_name.split("==")[0].strip()
        if hasattr(sys.modules, package_name) or package_name in sys.stdlib_module_names:
            return True
        try:
            return pkgutil.find_spec(package_name) is not None
        except Exception:
            return False

    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行Python代码"""
        try:
            code = args["code"]
            dependencies = args.get("dependencies", [])
            script_name = args.get("name", "")
            
            # 初始化脚本目录
            PythonScript.init_scripts_dir()
            
            # 生成脚本路径
            script_path = PythonScript.generate_script_path(script_name)
            
            # 安装依赖
            missing_deps = []
            for dep in dependencies:
                if not self._is_builtin_package(dep):
                    missing_deps.append(dep)
            
            if missing_deps:
                PrettyOutput.print("正在安装依赖...", OutputType.INFO)
                try:
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install"] + missing_deps,
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    PrettyOutput.print("依赖安装完成", OutputType.INFO)
                except subprocess.CalledProcessError as e:
                    return {
                        "success": False,
                        "error": f"依赖安装失败: {e.stderr}"
                    }
            
            # 写入脚本文件
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(code)
            
            # 执行脚本
            PrettyOutput.print(f"执行脚本: {script_path}", OutputType.INFO)
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True
            )
            
            # 构建输出
            output = []
            
            # 添加脚本信息
            output.append(f"脚本路径: {script_path}")
            if dependencies:
                output.append(f"依赖项: {', '.join(dependencies)}")
            output.append("")
            
            # 添加执行结果
            if result.stdout:
                output.append("输出:")
                output.append(result.stdout)
            
            # 添加错误信息（如果有）
            if result.stderr:
                output.append("错误:")
                output.append(result.stderr)
            
            # 添加返回码
            output.append(f"返回码: {result.returncode}")
            
            return {
                "success": result.returncode == 0,
                "stdout": "\n".join(output),
                "stderr": result.stderr,
                "return_code": result.returncode,
                "script_path": script_path
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"执行Python代码失败: {str(e)}"
            }
