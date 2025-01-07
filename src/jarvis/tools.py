from typing import Dict, Any, List, Optional, Callable
import subprocess
import os
import json
import time
from pathlib import Path
from .utils import PrettyOutput, OutputType
import sys
import pkgutil
from duckduckgo_search import DDGS
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime


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
        """Register default tools"""
        # Register search tool
        self.register_tool(
            name="search",
            description="Search for information using DuckDuckGo search engine",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 5
                    }
                },
                "required": ["query"]
            },
            func=self._search_ddg
        )

        # Register shell command execution tool
        self.register_tool(
            name="execute_shell",
            description="Execute shell commands and return the results",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Command execution timeout in seconds",
                        "default": 30
                    }
                },
                "required": ["command"]
            },
            func=self._execute_shell
        )

        # Register user interaction tool
        self.register_tool(
            name="ask_user",
            description="Ask user for information, supports option selection and multiline input",
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Question to ask the user"
                    },
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "List of options for user to choose from",
                        "default": []
                    },
                    "multiline": {
                        "type": "boolean",
                        "description": "Allow multiline input",
                        "default": False
                    },
                    "description": {
                        "type": "string",
                        "description": "Additional description or context for the question",
                        "default": ""
                    }
                },
                "required": ["question"]
            },
            func=self._ask_user
        )

        # Register Python execution tool
        self.register_tool(
            name="execute_python",
            description="""Execute Python code and return the results.
            Notes:
            1. Use print() to output results, otherwise they won't be visible
            2. Automatic dependency management is supported
            3. Code will be saved to a temporary file for execution
            
            Example:
            # Incorrect - result not visible
            result = 1 + 1
            
            # Correct - using print
            result = 1 + 1
            print(f"Result: {result}")""",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute, must use print() for output"
                    },
                    "dependencies": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "List of Python package dependencies to install (third-party only)",
                        "default": []
                    },
                    "name": {
                        "type": "string",
                        "description": "Script name for the saved file",
                        "default": ""
                    }
                },
                "required": ["code"]
            },
            func=self._execute_python
        )

        # Register user confirmation tool
        self.register_tool(
            name="ask_user_confirmation",
            description="Request confirmation from user, returns yes/no",
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Question to ask for confirmation"
                    },
                    "details": {
                        "type": "string",
                        "description": "Additional details or context for the confirmation",
                        "default": ""
                    }
                },
                "required": ["question"]
            },
            func=self._ask_user_confirmation
        )

        # Register webpage reader tool
        self.register_tool(
            name="read_webpage",
            description="Read webpage content, supporting extraction of main text, title, and other information",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the webpage to read"
                    },
                    "extract_type": {
                        "type": "string",
                        "description": "Type of content to extract: 'text' (main content), 'title', or 'all' (everything)",
                        "enum": ["text", "title", "all"],
                        "default": "all"
                    }
                },
                "required": ["url"]
            },
            func=self._read_webpage
        )

        # Register file operations tool
        self.register_tool(
            name="file_operation",
            description="""Perform file operations including reading and writing files.
            
Capabilities:
1. Read file content
2. Write content to file
3. Append content to existing file
4. Check if file exists
            
Note: 
- Supports operations on any accessible file path
- Creates directories automatically when writing files
- Binary files are not supported
- Large files (>10MB) should be processed in chunks
- All operations are logged for security tracking""",
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["read", "write", "append", "exists"],
                        "description": "Type of file operation to perform"
                    },
                    "filepath": {
                        "type": "string",
                        "description": "Absolute or relative path to the file"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write (required for write/append operations)",
                        "default": ""
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding (default: utf-8)",
                        "default": "utf-8"
                    }
                },
                "required": ["operation", "filepath"]
            },
            func=self._file_operation
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

    def _file_operation(self, args: Dict) -> Dict[str, Any]:
        """Execute file operations"""
        try:
            operation = args["operation"]
            filepath = args["filepath"]
            encoding = args.get("encoding", "utf-8")
            
            # Log operation with full path for tracking
            abs_path = os.path.abspath(filepath)
            PrettyOutput.print(f"File operation: {operation} - {abs_path}", OutputType.INFO)
            
            if operation == "exists":
                exists = os.path.exists(filepath)
                return {
                    "success": True,
                    "stdout": str(exists),
                    "stderr": ""
                }
                
            elif operation == "read":
                if not os.path.exists(filepath):
                    return {
                        "success": False,
                        "error": f"File not found: {filepath}"
                    }
                    
                # Check file size
                if os.path.getsize(filepath) > 10 * 1024 * 1024:  # 10MB
                    return {
                        "success": False,
                        "error": "File too large (>10MB)"
                    }
                    
                with open(filepath, 'r', encoding=encoding) as f:
                    content = f.read()
                return {
                    "success": True,
                    "stdout": content,
                    "stderr": ""
                }
                
            elif operation in ["write", "append"]:
                if not args.get("content"):
                    return {
                        "success": False,
                        "error": "Content parameter is required for write/append operations"
                    }
                
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
                    
                mode = 'a' if operation == "append" else 'w'
                with open(filepath, mode, encoding=encoding) as f:
                    f.write(args["content"])
                    
                return {
                    "success": True,
                    "stdout": f"Successfully {operation}ed content to {filepath}",
                    "stderr": ""
                }
                
            else:
                return {
                    "success": False,
                    "error": f"Unknown operation: {operation}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"File operation failed: {str(e)}"
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
            return {"success": False, "error": f"Tool {name} does not exist"}
        return tool.execute(arguments)

    def tool_help_text(self) -> str:
        return """Available Tools:

1. search: Search for information using DuckDuckGo
2. read_webpage: Extract content from webpages
3. execute_python: Run Python code with dependency management
4. execute_shell: Execute shell commands
5. ask_user: Get input from user with options support
6. ask_user_confirmation: Get yes/no confirmation from user
7. file_operation: Read/write files in workspace directory

Guidelines:
1. Always verify information through tools
2. Use search + read_webpage for research
3. Use Python/shell for data processing
4. Ask user when information is missing

Tool Call Format:
<tool_call>
{
    "name": "tool_name",
    "arguments": {
        "param1": "value1"
    }
}
</tool_call>

Example:
<tool_call>
{
    "name": "search",
    "arguments": {
        "query": "Python GIL",
        "max_results": 3
    }
}
</tool_call>"""

    def handle_tool_calls(self, tool_calls: List[Dict]) -> str:
        """处理工具调用"""
        def save_long_output(stdout: str, stderr: str = "", name: str = "", args: Any = None) -> str:
            """保存长输出到文件并返回引用信息"""
            output_dir = "/tmp/ai_outputs"
            os.makedirs(output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{output_dir}/{name}_{timestamp}.txt"
            
            # 组织文件内容
            content = []
            # 添加工具调用信息
            content.append("=== Tool Call Information ===")
            content.append(f"Tool Name: {name}")
            content.append(f"Arguments: {json.dumps(args, ensure_ascii=False, indent=2)}")
            content.append("")  # 空行分隔
            
            if stdout:
                content.append("=== Standard Output ===")
                content.append(stdout)
            if stderr:
                content.append("\n=== Error Output ===")
                content.append(stderr)
            
            # 写入文件
            with open(filename, "w", encoding="utf-8") as f:
                f.write("\n".join(content))
            
            # 生成预览信息
            preview_parts = []
            if stdout:
                preview_parts.append(f"Standard output preview: {stdout[:100]}...")
            if stderr:
                preview_parts.append(f"Error output preview: {stderr[:100]}...")
            
            return f"Output was too long and has been saved to file: {filename}\n" + \
                   "\n".join(preview_parts)

        results = []
        for tool_call in tool_calls:
            name = tool_call["function"]["name"]
            args = tool_call["function"]["arguments"]
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    return f"Invalid JSON in arguments for tool {name}"

            # 打印工具调用信息
            PrettyOutput.print(f"Calling tool: {name}", OutputType.INFO)
            if isinstance(args, dict):
                for key, value in args.items():
                    PrettyOutput.print(f"  - {key}: {value}", OutputType.INFO)
            else:
                PrettyOutput.print(f"  Arguments: {args}", OutputType.INFO)
            PrettyOutput.print("", OutputType.INFO)  # 空行
            
            result = self.execute_tool(name, args)
            if result["success"]:
                stdout = result["stdout"]
                stderr = result.get("stderr", "")
                
                # 如果任一输出超过1024字符，则保存到文件
                if len(stdout) > 1024 or len(stderr) > 1024:
                    output = save_long_output(stdout, stderr, name, args)
                else:
                    output_parts = []
                    output_parts.append(f"Result:\n{stdout}")
                    if stderr:
                        output_parts.append(f"Errors:\n{stderr}")
                    output = "\n\n".join(output_parts)
            else:
                error_msg = result["error"]
                if len(error_msg) > 1024:
                    output = save_long_output(stderr=error_msg, name=name, args=args)
                else:
                    output = f"Execution failed: {error_msg}"
                    
            results.append(output)
        return "\n".join(results)
