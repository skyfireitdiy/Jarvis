from typing import Dict, Any, List
import os
import subprocess
import re
import platform

from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class SymbolTool:
    """
    符号查找工具
    直接使用 ripgrep/grep 查找代码库中的符号位置
    """
    
    name = "find_symbol"
    description = "查找代码符号在代码库中的位置"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "要查找的符号名称"
            },
            "root_dir": {
                "type": "string",
                "description": "代码库根目录路径（可选）",
                "default": "."
            },
            "file_extensions": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "要搜索的文件扩展名列表（如：['.py', '.js']）（可选）",
                "default": []
            },
            "exclude_dirs": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "要排除的目录列表（可选）",
                "default": []
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数量（可选）",
                "default": 100
            }
        },
        "required": ["symbol"]
    }
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行符号查找工具
        
        Args:
            args: 包含参数的字典
            
        Returns:
            包含执行结果的字典
        """
        # 存储原始目录
        original_dir = os.getcwd()
        
        try:
            # 解析参数
            symbol = args.get("symbol", "")
            root_dir = args.get("root_dir", ".")
            file_extensions = args.get("file_extensions", [])
            exclude_dirs = args.get("exclude_dirs", [])
            max_results = args.get("max_results", 100)
            
            # 验证参数
            if not symbol:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "必须提供符号名称"
                }
            
            # 切换到根目录
            os.chdir(root_dir)
            
            # 进行符号搜索
            search_result = self._find_symbol(symbol, file_extensions, exclude_dirs, max_results)
            
            # 格式化并返回结果
            formatted_result = self._format_results(symbol, search_result)
            
            return {
                "success": True,
                "stdout": formatted_result,
                "stderr": ""
            }
                
        except Exception as e:
            PrettyOutput.print(str(e), OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"符号查找失败: {str(e)}"
            }
        finally:
            # 恢复原始目录
            os.chdir(original_dir)
    
    def _find_symbol(self, symbol: str, file_extensions: List[str], exclude_dirs: List[str], max_results: int) -> str:
        """
        查找符号
        
        Args:
            symbol: 符号名称
            file_extensions: 文件扩展名列表
            exclude_dirs: 排除目录列表
            max_results: 最大结果数量
            
        Returns:
            查找结果字符串
        """
        # 使用单词边界匹配完整符号
        pattern = f"\\b{re.escape(symbol)}\\b"
        
        return self._execute_grep_command(pattern, file_extensions, exclude_dirs, max_results)
    
    def _execute_grep_command(self, pattern: str, file_extensions: List[str], exclude_dirs: List[str], max_results: int) -> str:
        """
        执行 grep 命令
        
        Args:
            pattern: 搜索模式
            file_extensions: 文件扩展名列表
            exclude_dirs: 排除目录列表
            max_results: 最大结果数量
            
        Returns:
            命令执行结果
        """
        # 检查是否存在 ripgrep (rg)
        has_rg = self._command_exists("rg")
        
        if has_rg:
            # 使用 ripgrep
            command = ["rg", "-n"]
            
            # 添加文件类型限制
            if file_extensions:
                for ext in file_extensions:
                    if not ext.startswith('.'):
                        ext = f".{ext}"
                    command.append("-g")
                    command.append(f"*{ext}")
            
            # 添加排除目录
            for excl in exclude_dirs:
                command.append("--glob")
                command.append(f"!{excl}")
            
            # 添加模式和最大结果数
            command.append(pattern)
            command.append("-m")
            command.append(str(max_results))
            
        else:
            # 回退到使用 grep
            command = ["grep", "-n", "-E"]
            
            # 添加递归搜索
            command.append("-r")
            
            # 添加文件类型限制
            if file_extensions:
                file_pattern = " --include=*".join([ext for ext in file_extensions])
                if file_pattern:
                    command.append(f"--include=*{file_pattern}")
            
            # 添加排除目录
            for excl in exclude_dirs:
                command.append(f"--exclude-dir={excl}")
            
            # 添加模式和搜索目录
            command.append(pattern)
            command.append(".")
        
        # 执行命令
        try:
            process = subprocess.run(
                command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            
            if process.returncode not in [0, 1]:  # rg/grep 返回 1 表示没有找到匹配项，这不是错误
                return f"搜索命令执行失败，错误码: {process.returncode}\n{process.stderr}"
            
            return process.stdout
        except Exception as e:
            return f"执行搜索命令时出错: {str(e)}"
    
    def _format_results(self, symbol: str, search_result: str) -> str:
        """
        格式化搜索结果
        
        Args:
            symbol: 符号名称
            search_result: 搜索结果
            
        Returns:
            格式化后的结果
        """
        # 解析结果并按文件分组
        results = self._parse_grep_results(search_result)
        
        # 构建格式化输出
        output = []
        output.append(f"# 符号搜索结果: `{symbol}`\n")
        
        # 搜索结果
        if not results:
            output.append("未找到符号\n")
        else:
            for file_path, lines in results.items():
                output.append(f"## {file_path}\n")
                for line_num, content in lines:
                    output.append(f"- 第 {line_num} 行: `{content.strip()}`\n")
        
        # 统计部分
        output.append("\n## 统计\n")
        total_occurrences = sum(len(lines) for lines in results.values())
        output.append(f"- 总出现次数: {total_occurrences} 处\n")
        output.append(f"- 出现文件数: {len(results)} 个\n")
        
        return "".join(output)
    
    def _parse_grep_results(self, results: str) -> Dict[str, List[tuple]]:
        """
        解析 grep/ripgrep 结果，按文件分组
        
        Args:
            results: grep/ripgrep 输出结果
            
        Returns:
            按文件分组的结果字典 {文件路径: [(行号, 内容), ...]}
        """
        parsed_results = {}
        
        if not results.strip():
            return parsed_results
            
        for line in results.splitlines():
            parts = line.split(":", 2)
            if len(parts) >= 3:
                file_path, line_num, content = parts[0], parts[1], parts[2]
                
                if file_path not in parsed_results:
                    parsed_results[file_path] = []
                    
                parsed_results[file_path].append((line_num, content))
                
        return parsed_results
    
    def _command_exists(self, command: str) -> bool:
        """
        检查命令是否存在
        
        Args:
            command: 命令名称
            
        Returns:
            命令是否存在
        """
        if platform.system() == "Windows":
            # Windows 检查命令
            try:
                subprocess.run(["where", command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                return True
            except Exception:
                return False
        else:
            # Unix/Linux/Mac 检查命令
            try:
                subprocess.run(["which", command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                return True
            except Exception:
                return False
