# -*- coding: utf-8 -*-
import os
import subprocess
from typing import Any, Dict

from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class CtagsTool:
    name = "ctags"
    description = "符号定义查找工具，用于查找某个符号的定义位置，仅在CodeAgent模式下可用"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "要查找的符号名称（函数名、类名、变量名等）"
            },
            "file_pattern": {
                "type": "string",
                "description": "文件搜索模式（可选，如*.py表示只搜索Python文件）",
                "default": ""
            }
        },
        "required": ["symbol"]
    }
    
    @classmethod
    def check(cls) -> bool:
        """检查工具是否可用，仅在CodeAgent模式下启用"""
        return os.environ.get("JARVIS_CODE_AGENT") == "1"
    
    def _find_symbol_with_ctags(self, symbol: str, file_pattern: str = "") -> Dict[str, Any]:
        """使用ctags查找符号定义位置"""
        try:
            # 构建ctags命令
            cmd = ["ctags", "-x", "--sort=no", symbol]
            if file_pattern:
                cmd.extend(["--languages", "+python"])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"ctags执行失败: {result.stderr}"
                }
            
            if not result.stdout.strip():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未找到符号 '{symbol}' 的定义"
                }
            
            # 解析ctags输出
            lines = result.stdout.strip().split('\n')
            locations = []
            
            for line in lines:
                parts = line.split()
                if len(parts) >= 3:
                    symbol_name = parts[0]
                    symbol_type = parts[1]
                    file_path = parts[2]
                    line_number = parts[3] if len(parts) > 3 else "未知"
                    
                    locations.append({
                        "symbol": symbol_name,
                        "type": symbol_type,
                        "file": file_path,
                        "line": line_number
                    })
            
            # 格式化输出
            output_lines = [f"🔍 符号 '{symbol}' 的定义位置:"]
            output_lines.append("─" * 60)
            
            for loc in locations:
                output_lines.append(f"📄 文件: {loc['file']}")
                output_lines.append(f"📍 行号: {loc['line']}")
                output_lines.append(f"🔧 类型: {loc['type']}")
                output_lines.append("─" * 60)
            
            return {
                "success": True,
                "stdout": "\n".join(output_lines),
                "stderr": ""
            }
            
        except FileNotFoundError:
            return {
                "success": False,
                "stdout": "",
                "stderr": "ctags命令未找到，请先安装ctags工具"
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"ctags执行出错: {str(e)}"
            }
    
    def _find_symbol_with_grep(self, symbol: str, file_pattern: str = "") -> Dict[str, Any]:
        """使用grep作为备用方案查找符号定义"""
        try:
            # 构建grep命令
            grep_pattern = rf"^\s*(class|def)\s+{symbol}\b"
            cmd = ["grep", "-n", "-r", "--include", "*.py", grep_pattern, "."]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                output_lines = [f"🔍 符号 '{symbol}' 的定义位置（使用grep）:"]
                output_lines.append("─" * 60)
                
                for line in lines:
                    if ':' in line:
                        file_path, line_info = line.split(':', 1)
                        line_num, content = line_info.split(':', 1)
                        output_lines.append(f"📄 文件: {file_path}")
                        output_lines.append(f"📍 行号: {line_num}")
                        output_lines.append(f"📝 内容: {content.strip()}")
                        output_lines.append("─" * 60)
                
                return {
                    "success": True,
                    "stdout": "\n".join(output_lines),
                    "stderr": ""
                }
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"未找到符号 '{symbol}' 的定义"
                }
                
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"grep执行出错: {str(e)}"
            }
    
    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行符号查找操作"""
        try:
            # 检查是否在CodeAgent模式下
            if not self.check():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "ctags工具仅在CodeAgent模式下可用"
                }
            
            symbol = args.get("symbol", "").strip()
            file_pattern = args.get("file_pattern", "").strip()
            
            if not symbol:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "必须提供要查找的符号名称"
                }
            
            # 优先使用ctags查找
            result = self._find_symbol_with_ctags(symbol, file_pattern)
            
            # 如果ctags失败，尝试使用grep作为备用方案
            if not result["success"]:
                result = self._find_symbol_with_grep(symbol, file_pattern)
            
            return result
            
        except Exception as e:
            PrettyOutput.print(f"ctags工具执行失败: {str(e)}", OutputType.ERROR)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"ctags工具执行失败: {str(e)}"
            }
