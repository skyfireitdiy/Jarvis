from typing import Dict, Any, List, Optional, Callable
import subprocess
import os
import json
import time
from pathlib import Path
from utils import PrettyOutput, OutputType
import sys
import pkgutil
from dotenv import load_dotenv
from tavily import TavilyClient

# 加载环境变量
load_dotenv()

# 初始化 Tavily 客户端
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

class PythonScript:
    """Python脚本管理类"""
    SCRIPTS_DIR = "temp_scripts"

    @classmethod
    def init_scripts_dir(cls):
        """初始化脚本目录"""
        Path(cls.SCRIPTS_DIR).mkdir(exist_ok=True)

    @classmethod
    def generate_script_path(cls, name: Optional[str] = None) -> str:
        """生成脚本文件路径"""
        if name:
            # 清理文件名，移除不安全字符
            safe_name = "".join(c for c in name if c.isalnum() or c in "._- ")
            filename = f"{int(time.time())}_{safe_name}.py"
        else:
            filename = f"{int(time.time())}_script.py"
        return str(Path(cls.SCRIPTS_DIR) / filename)

class Tool:
    def __init__(self, name: str, description: str, parameters: Dict, func: Callable):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func

    def to_dict(self) -> Dict:
        """转换为Ollama工具格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }

    def execute(self, arguments: Dict) -> Dict[str, Any]:
        """执行工具函数"""
        return self.func(arguments)

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        # 初始化脚本目录
        PythonScript.init_scripts_dir()
        self._register_default_tools()

    def _register_default_tools(self):
        """注册默认工具"""
        # 注册网络搜索工具
        self.register_tool(
            name="search",
            description="使用Tavily搜索引擎获取信息",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询内容"
                    },
                    "search_depth": {
                        "type": "string",
                        "description": "搜索深度，basic或comprehensive",
                        "enum": ["basic", "comprehensive"],
                        "default": "basic"
                    }
                },
                "required": ["query"]
            },
            func=self._search_tavily
        )

        # 注册shell命令执行工具
        self.register_tool(
            name="execute_shell",
            description="执行shell命令并返回结果",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的shell命令"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "命令执行超时时间（秒）",
                        "default": 30
                    }
                },
                "required": ["command"]
            },
            func=self._execute_shell
        )

        # 注册用户交互工具
        self.register_tool(
            name="ask_user",
            description="向用户询问信息，支持选项选择和多行输入",
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "要询问用户的问题"
                    },
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "可选的选项列表",
                        "default": []
                    },
                    "multiline": {
                        "type": "boolean",
                        "description": "是否允许多行输入",
                        "default": False
                    },
                    "description": {
                        "type": "string",
                        "description": "问题的补充说明",
                        "default": ""
                    }
                },
                "required": ["question"]
            },
            func=self._ask_user
        )

        self.register_tool(
            name="execute_python",
            description="""执行Python代码并返回结果。
            注意：
            1. 需要使用print输出结果，否则将看不到
            2. 支持自动管理依赖包
            3. 代码会保存到临时文件执行
            
            示例:
            # 错误写法 - 看不到结果
            result = 1 + 1
            
            # 正确写法 - 使用print输出
            result = 1 + 1
            print(f"计算结果: {result}")""",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的Python代码，记得使用print输出结果"
                    },
                    "dependencies": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "需要安装的Python包依赖列表，仅添加第三方包",
                        "default": []
                    },
                    "name": {
                        "type": "string",
                        "description": "脚本名称，用于保存脚本文件",
                        "default": ""
                    }
                },
                "required": ["code"]
            },
            func=self._execute_python
        )

        # 注册用户确认工具
        self.register_tool(
            name="ask_user_confirmation",
            description="向用户请求确认，返回yes/no",
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "要询问用户的问题"
                    },
                    "details": {
                        "type": "string",
                        "description": "提供给用户的详细信息或上下文",
                        "default": ""
                    }
                },
                "required": ["question"]
            },
            func=self._ask_user_confirmation
        )

    @staticmethod
    def _is_builtin_package(package_name: str) -> bool:
        """检查是否是Python内置包"""
        # 移除版本号
        package_name = package_name.split("==")[0].strip()
        
        # 检查是否是内置模块
        if hasattr(sys.modules, package_name) or package_name in sys.stdlib_module_names:
            return True
        
        # 检查是否已安装
        try:
            return pkgutil.find_spec(package_name) is not None
        except Exception:
            return False

    def _execute_python(self, args: Dict) -> Dict[str, Any]:
        """执行Python代码"""
        try:
            script_path = PythonScript.generate_script_path(args.get("name"))

            # 安装依赖
            install_output = []
            if "dependencies" in args and args["dependencies"]:
                # 过滤掉内置包和已安装的包
                packages_to_install = []
                
                for package in args["dependencies"]:
                    if self._is_builtin_package(package):
                        # 检查是否是平台特定的内置模块
                        try:
                            __import__(package)
                            install_output.append(f"使用系统内置包: {package}")
                        except ImportError:
                            install_output.append(f"警告: {package} 在当前系统上不可用")
                            continue
                    else:
                        packages_to_install.append(package)
                
                # 安装非内置包
                for package in packages_to_install:
                    try:
                        result = subprocess.run(
                            ["pip", "install", package],
                            capture_output=True,
                            text=True
                        )
                        if result.returncode == 0:
                            install_output.append(f"成功安装 {package}")
                        else:
                            install_output.append(f"安装 {package} 失败: {result.stderr}")
                    except Exception as e:
                        install_output.append(f"安装 {package} 时出错: {str(e)}")
            
            # 创建Python文件
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(args["code"])
            
            # 执行代码并捕获输出
            execution_result = subprocess.run(
                ["python", script_path],
                capture_output=True,
                text=True
            )
            
            # 构建输出
            output = []
            PrettyOutput.print(f"脚本保存为: {script_path}", OutputType.INFO)
            output.append("")

            if "dependencies" in args and args["dependencies"]:
                PrettyOutput.print("依赖安装结果:", OutputType.INFO)
                for msg in install_output:
                    PrettyOutput.print(msg, OutputType.INFO)
                output.extend(install_output)
                output.append("")  # 添加空行
            
            if execution_result.stdout:
                output.append(execution_result.stdout)
            
            return {
                "success": True,
                "stdout": "\n".join(output),
                "stderr": execution_result.stderr
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _ask_user_confirmation(self, args: Dict) -> Dict[str, Any]:
        """向用户请求确认"""
        try:
            # 打印问题和详细信息
            PrettyOutput.print("\n请确认:", OutputType.INFO)
            PrettyOutput.print(args["question"], OutputType.SYSTEM)
            
            if args.get("details"):
                PrettyOutput.print("\n详细信息:", OutputType.INFO)
                PrettyOutput.print(args["details"], OutputType.INFO)
            
            # 获取用户输入
            while True:
                response = input("\n请输入 (y/n): ").lower().strip()
                if response in ['y', 'n']:
                    break
                PrettyOutput.print("请输入 y 或 n", OutputType.ERROR)
            
            return {
                "success": True,
                "stdout": "yes" if response == 'y' else "no",
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _ask_user(self, args: Dict) -> Dict[str, Any]:
        """向用户询问信息"""
        try:
            # 打印问题
            PrettyOutput.print("\n需要补充信息:", OutputType.INFO)
            PrettyOutput.print(args["question"], OutputType.SYSTEM)
            
            # 显示补充说明
            if args.get("description"):
                PrettyOutput.print(args["description"], OutputType.INFO)
            
            # 如果有选项，显示选项列表
            if args.get("options"):
                PrettyOutput.print("\n可选项:", OutputType.INFO)
                for i, option in enumerate(args["options"], 1):
                    PrettyOutput.print(f"{i}. {option}", OutputType.INFO)
                
                # 获取用户选择
                while True:
                    try:
                        choice = input("\n请选择 (输入数字): ").strip()
                        idx = int(choice) - 1
                        if 0 <= idx < len(args["options"]):
                            response = args["options"][idx]
                            break
                        PrettyOutput.print("请输入有效的选项编号", OutputType.ERROR)
                    except ValueError:
                        PrettyOutput.print("请输入数字", OutputType.ERROR)
            
            # 如果是多行输入
            elif args.get("multiline"):
                PrettyOutput.print("(输入空行完成)", OutputType.INFO)
                lines = []
                while True:
                    line = input("... " if lines else "> ")
                    if not line and lines:
                        break
                    if line:
                        lines.append(line)
                response = "\n".join(lines)
            
            # 单行输入
            else:
                response = input("> ").strip()
            
            return {
                "success": True,
                "stdout": response,
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _execute_shell(self, args: Dict) -> Dict[str, Any]:
        """执行shell命令"""
        try:
            # 获取参数
            command = args["command"]
            timeout = args.get("timeout", 30)
            
            # 执行命令
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            # 构建输出
            output = []
            
            # 添加命令信息
            PrettyOutput.print(f"执行命令: {command}", OutputType.INFO)
            output.append(f"命令: {command}")
            output.append("")
            
            # 添加输出
            if result.stdout:
                output.append(result.stdout)
            
            return {
                "success": True,
                "stdout": "\n".join(output),
                "stderr": result.stderr,
                "return_code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"命令执行超时 (>{timeout}秒)"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _search_tavily(self, args: Dict) -> Dict[str, Any]:
        """使用Tavily API进行搜索"""
        try:
            if not os.getenv("TAVILY_API_KEY"):
                return {
                    "success": False,
                    "error": "未找到TAVILY_API_KEY环境变量"
                }

            # 发送请求
            PrettyOutput.print(f"搜索查询: {args['query']}", OutputType.INFO)
            result = tavily_client.search(
                query=args["query"],
                search_depth=args.get("search_depth", "basic"),
                max_results=5,
                include_answer=True,
                include_images=False
            )
            
            # 构建输出
            output = []
            
            # 添加AI生成的答案
            if result.get("answer"):
                output.append("AI回答:")
                output.append(result["answer"])
                output.append("")
            
            # 添加搜索结果
            if result.get("results"):
                output.append("搜索结果:")
                for i, item in enumerate(result["results"], 1):
                    output.append(f"\n{i}. {item['title']}")
                    output.append(f"   链接: {item['url']}")
                    # 检查不同可能的摘要字段
                    summary = item.get('snippet') or item.get('content') or item.get('summary') or "无摘要"
                    output.append(f"   摘要: {summary}")
            
            return {
                "success": True,
                "stdout": "\n".join(output),
                "stderr": ""
            }

        except Exception as e:
            # 添加更详细的错误信息
            error_msg = f"搜索失败: {str(e)}"
            if isinstance(e, AttributeError):
                error_msg += f"\n结果结构: {str(result)}"
            return {
                "success": False,
                "error": error_msg
            }

    def register_tool(self, name: str, description: str, parameters: Dict, func: Callable):
        """注册新工具"""
        self.tools[name] = Tool(name, description, parameters, func)

    def get_tool(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self.tools.get(name)

    def get_all_tools(self) -> List[Dict]:
        """获取所有工具的Ollama格式定义"""
        return [tool.to_dict() for tool in self.tools.values()]

    def execute_tool(self, name: str, arguments: Dict) -> Dict[str, Any]:
        """执行指定工具"""
        tool = self.get_tool(name)
        if tool is None:
            return {"success": False, "error": f"工具 {name} 不存在"}
        return tool.execute(arguments) 