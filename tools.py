from typing import Dict, Any, List, Optional, Callable
import subprocess
import os
import json
import time
from pathlib import Path
from utils import PrettyOutput, OutputType
import sys
import pkgutil
from duckduckgo_search import DDGS
import requests
from bs4 import BeautifulSoup
import re


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
            description="使用DuckDuckGo搜索引擎获取信息",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询内容"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "返回结果数量",
                        "default": 5
                    }
                },
                "required": ["query"]
            },
            func=self._search_ddg
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
                        "description": "要执行的Python代码，需要使用print来输出结果"
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

        # 注册网页读取工具
        self.register_tool(
            name="read_webpage",
            description="读取网页内容，支持提取正文、标题等信息",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要读取的网页URL"
                    },
                    "extract_type": {
                        "type": "string",
                        "description": "提取类型：'text'(正文文本), 'title'(标题), 'all'(所有信息)",
                        "enum": ["text", "title", "all"],
                        "default": "all"
                    }
                },
                "required": ["url"]
            },
            func=self._read_webpage
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

            # 尝试对code进行JSON解码，以处理可能的多次编码情况
            code = args["code"]
            while True:
                try:
                    decoded_code = json.loads(code)
                    if isinstance(decoded_code, str):
                        code = decoded_code
                except json.JSONDecodeError:
                    # 如果解码失败，使用原始code
                    break

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
                f.write(code)  # 使用可能解码后的code
            
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
                PrettyOutput.print("\n(输入空行或finish完成)", OutputType.INFO)
                lines = []
                while True:
                    line = input("... " if lines else ">>> ").strip()
                    if (not line and lines) or line.lower() == "finish":
                        break
                    if line:
                        lines.append(line)
                response = "\n".join(lines)
            
            # 单行输入
            else:
                PrettyOutput.print("\n请输入您的回答:", OutputType.INFO)
                response = input(">>> ").strip()
            
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

    def _search_ddg(self, args: Dict) -> Dict[str, Any]:
        """使用DuckDuckGo进行搜索"""
        try:
            # 打印搜索查询
            PrettyOutput.print(f"搜索查询: {args['query']}", OutputType.INFO)
            
            # 获取搜索结果
            with DDGS() as ddgs:
                results = ddgs.text(
                    keywords=args["query"],
                    max_results=args.get("max_results", 5)
                )
            
            return {
                "success": True,
                "stdout": results,
                "stderr": ""
            }

        except Exception as e:
            error_msg = f"搜索失败: {str(e)}"
            return {
                "success": False,
                "error": error_msg
            }

    def _read_webpage(self, args: Dict) -> Dict[str, Any]:
        """读取网页内容"""
        try:
            url = args["url"]
            extract_type = args.get("extract_type", "all")
            
            # 设置请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # 发送请求
            PrettyOutput.print(f"正在读取网页: {url}", OutputType.INFO)
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # 使用正确的编码
            response.encoding = response.apparent_encoding
            
            # 解析HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 移除script和style标签
            for script in soup(["script", "style"]):
                script.decompose()
            
            result = {}
            
            # 提取标题
            if extract_type in ["title", "all"]:
                title = soup.title.string if soup.title else ""
                result["title"] = title.strip() if title else "无标题"
            
            # 提取正文
            if extract_type in ["text", "all"]:
                # 获取正文内容
                text = soup.get_text(separator='\n', strip=True)
                # 清理空行
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                # 合并短行
                cleaned_lines = []
                current_line = ""
                for line in lines:
                    if len(current_line) < 80:  # 假设一行最大80字符
                        current_line += " " + line if current_line else line
                    else:
                        if current_line:
                            cleaned_lines.append(current_line)
                        current_line = line
                if current_line:
                    cleaned_lines.append(current_line)
                
                result["text"] = "\n".join(cleaned_lines)
            
            # 构建输出
            output = []
            if "title" in result:
                output.append(f"标题: {result['title']}")
                output.append("")
            
            if "text" in result:
                output.append("正文内容:")
                output.append(result["text"])
            
            return {
                "success": True,
                "stdout": "\n".join(output),
                "stderr": ""
            }

        except requests.RequestException as e:
            error_msg = f"网页请求失败: {str(e)}"
            return {
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"解析网页失败: {str(e)}"
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
    
    def tool_help_text(self) -> str:
        return """Working Principles:
1. Use search tool to obtain factual information
2. Use execute_shell to get system information
3. Use execute_python to process data
4. Use ask_user to inquire if information is missing
5. Must cite data sources before providing answers
6. For search-returned webpage links, use read_webpage tool to get detailed content

Tool Usage Guidelines:
1. First use search tool to find relevant information
2. If search results contain interesting webpages, use read_webpage tool to read their content
3. Provide more detailed answers based on webpage content

Prohibited Actions:
1. Do not guess or fabricate data
2. Do not use unverified information
3. If tool execution fails, explain the reason
4. If data cannot be obtained, honestly acknowledge it

Tool Call Format:
<tool_call>
{
    "name": "tool_name",
    "arguments": {
        "param1": "value1",
        "param2": "value2"
    }
}
</tool_call>

Examples:
1. Search and read webpage:
<tool_call>
{
    "name": "search",
    "arguments": {
        "query": "Python GIL",
        "max_results": 3
    }
}
</tool_call>

For interesting search results, use read_webpage:
<tool_call>
{
    "name": "read_webpage",
    "arguments": {
        "url": "https://example.com/python-gil",
        "extract_type": "all"
    }
}
</tool_call>"""
