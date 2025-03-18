from typing import Dict, Any, List, Optional
import os
import logging
from yaspin import yaspin

from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_treesitter import (
    CodeDatabase, 
    SymbolType, 
    setup_default_grammars,
    DEFAULT_GRAMMAR_DIR
)

# 配置日志
logger = logging.getLogger(__name__)

class TreesitterAnalyzer:
    """Tree-sitter 代码分析工具，用于快速查找代码中的符号定义、引用和调用关系"""
    
    name = "treesitter_analyzer"
    description = "使用 Tree-sitter 分析代码，查找符号定义、引用和调用关系"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["find_symbol", "find_references", "find_callers"],
                "description": "分析操作类型: find_symbol(查找符号), find_references(查找引用), find_callers(查找调用者)"
            },
            "symbol_name": {
                "type": "string",
                "description": "要查找的符号名称，如函数名、类名、变量名等"
            },
            "directory": {
                "type": "string",
                "description": "要索引的代码目录，默认为当前目录",
                "default": "."
            },
            "extensions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要索引的文件扩展名列表，如 [\".py\", \".c\"]，不指定则索引所有支持的文件类型"
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数量",
                "default": 20
            }
        },
        "required": ["action", "symbol_name", "directory"]
    }
    
    def __init__(self):
        """初始化 Tree-sitter 分析器工具"""
        # 确保语法文件目录存在
        os.makedirs(DEFAULT_GRAMMAR_DIR, exist_ok=True)
        
        # 创建代码数据库实例
        self.db = None
        
    def _get_database(self) -> CodeDatabase:
        """获取 Tree-sitter 代码数据库实例，如果不存在则创建"""
        if self.db is None:
            self.db = CodeDatabase()
        return self.db
    
    def _index_directory(self, directory: str, extensions: Optional[List[str]] = None) -> Dict[str, Any]:
        """索引指定目录下的代码文件"""
        try:
            db = self._get_database()
            indexed_files = []
            skipped_files = []
            
            with yaspin(text=f"正在索引目录: {directory}...", color="cyan") as spinner:
                for root, _, files in os.walk(directory):
                    for file in files:
                        # 检查文件扩展名
                        if extensions and not any(file.endswith(ext) for ext in extensions):
                            continue
                            
                        file_path = os.path.join(root, file)
                        try:
                            db.index_file(file_path)
                            indexed_files.append(file_path)
                        except Exception as e:
                            skipped_files.append((file_path, str(e)))
                
                spinner.text = f"索引完成: {len(indexed_files)} 个文件"
                spinner.ok("✅")
                
                return {
                    "success": True,
                    "indexed_files": indexed_files,
                    "skipped_files": skipped_files,
                    "index_summary": f"已成功索引 {len(indexed_files)} 个文件，跳过 {len(skipped_files)} 个文件"
                }
                
        except Exception as e:
            logger.error(f"索引目录失败: {str(e)}")
            return {
                "success": False,
                "stderr": f"索引目录失败: {str(e)}"
            }
    
    def _find_symbol(self, symbol_name: str, directory: str, max_results: int = 20) -> Dict[str, Any]:
        """查找代码中的符号定义"""
        try:
            db = self._get_database()
            symbols = db.find_symbol(symbol_name)
            
            if not symbols:
                return {
                    "success": True,
                    "stdout": f"未找到名为 '{symbol_name}' 的符号",
                    "symbols": []
                }
            
            # 限制结果数量
            symbols = symbols[:max_results]
            
            # 构建结果
            result_list = []
            for symbol in symbols:
                result_list.append({
                    "name": symbol.name,
                    "type": symbol.type.value,
                    "file": symbol.location.file_path,
                    "line": symbol.location.start_line,
                    "column": symbol.location.start_column
                })
            
            # 构建输出文本
            output_text = f"找到 {len(symbols)} 个名为 '{symbol_name}' 的符号:\n\n"
            for i, symbol in enumerate(symbols, 1):
                output_text += (f"{i}. {symbol.type.value}: {symbol.name}\n"
                               f"   位置: {symbol.location.file_path}:{symbol.location.start_line}:{symbol.location.start_column}\n\n")
            
            return {
                "success": True,
                "stdout": output_text,
                "symbols": result_list
            }
            
        except Exception as e:
            logger.error(f"查找符号失败: {str(e)}")
            return {
                "success": False,
                "stderr": f"查找符号失败: {str(e)}"
            }
    
    def _find_references(self, symbol_name: str, directory: str, max_results: int = 20) -> Dict[str, Any]:
        """查找代码中符号的引用"""
        try:
            db = self._get_database()
            symbols = db.find_symbol(symbol_name)
            
            if not symbols:
                return {
                    "success": True,
                    "stdout": f"未找到名为 '{symbol_name}' 的符号",
                    "references": []
                }
            
            # 获取第一个匹配符号的所有引用
            references = db.find_references(symbols[0])
            
            # 限制结果数量
            references = references[:max_results]
            
            # 构建结果
            result_list = []
            for ref in references:
                result_list.append({
                    "file": ref.location.file_path,
                    "line": ref.location.start_line,
                    "column": ref.location.start_column
                })
            
            # 构建输出文本
            output_text = f"找到 {len(references)} 处对 '{symbol_name}' 的引用:\n\n"
            for i, ref in enumerate(references, 1):
                output_text += f"{i}. {ref.location.file_path}:{ref.location.start_line}:{ref.location.start_column}\n"
            
            return {
                "success": True,
                "stdout": output_text,
                "symbol": {
                    "name": symbols[0].name,
                    "type": symbols[0].type.value,
                    "file": symbols[0].location.file_path,
                    "line": symbols[0].location.start_line,
                    "column": symbols[0].location.start_column
                },
                "references": result_list
            }
            
        except Exception as e:
            logger.error(f"查找引用失败: {str(e)}")
            return {
                "success": False,
                "stderr": f"查找引用失败: {str(e)}"
            }
    
    def _find_callers(self, symbol_name: str, directory: str, max_results: int = 20) -> Dict[str, Any]:
        """查找代码中调用指定函数的位置"""
        try:
            db = self._get_database()
            symbols = db.find_symbol(symbol_name)
            
            if not symbols:
                return {
                    "success": True,
                    "stdout": f"未找到名为 '{symbol_name}' 的函数",
                    "callers": []
                }
            
            # 筛选出函数类型的符号
            function_symbols = [s for s in symbols if s.type == SymbolType.FUNCTION]
            if not function_symbols:
                return {
                    "success": True,
                    "stdout": f"'{symbol_name}' 不是一个函数",
                    "callers": []
                }
            
            # 获取第一个函数符号的所有调用者
            callers = db.find_callers(function_symbols[0])
            
            # 限制结果数量
            callers = callers[:max_results]
            
            # 构建结果
            result_list = []
            for caller in callers:
                result_list.append({
                    "file": caller.location.file_path,
                    "line": caller.location.start_line,
                    "column": caller.location.start_column
                })
            
            # 构建输出文本
            output_text = f"找到 {len(callers)} 处对函数 '{symbol_name}' 的调用:\n\n"
            for i, caller in enumerate(callers, 1):
                output_text += f"{i}. {caller.location.file_path}:{caller.location.start_line}:{caller.location.start_column}\n"
            
            return {
                "success": True,
                "stdout": output_text,
                "function": {
                    "name": function_symbols[0].name,
                    "file": function_symbols[0].location.file_path,
                    "line": function_symbols[0].location.start_line,
                    "column": function_symbols[0].location.start_column
                },
                "callers": result_list
            }
            
        except Exception as e:
            logger.error(f"查找调用者失败: {str(e)}")
            return {
                "success": False,
                "stderr": f"查找调用者失败: {str(e)}"
            }
    
    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行 Tree-sitter 代码分析
        
        参数:
            args: 包含操作参数的字典
            
        返回:
            Dict[str, Any]: 操作结果
        """
        try:
            action = args.get("action")
            symbol_name = args.get("symbol_name")
            directory = args.get("directory", ".")
            extensions = args.get("extensions", None)
            max_results = args.get("max_results", 20)
            
            # 确保 symbol_name 参数存在
            if not symbol_name:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "缺少必要参数: symbol_name"
                }
            
            # 确保语法目录存在
            os.makedirs(DEFAULT_GRAMMAR_DIR, exist_ok=True)
            
            # 先自动索引目录
            with yaspin(text="正在索引目录...") as spinner:
                index_result = self._index_directory(directory, extensions)
                if not index_result.get("success", False):
                    spinner.fail("✗")
                    return index_result
                spinner.ok("✓")
            
            # 根据不同的操作执行相应的函数
            result = None
            if action == "find_symbol":
                result = self._find_symbol(symbol_name, directory, max_results)
            elif action == "find_references":
                result = self._find_references(symbol_name, directory, max_results)
            elif action == "find_callers":
                result = self._find_callers(symbol_name, directory, max_results)
            else:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"不支持的操作: {action}"
                }
            
            # 将索引信息添加到结果中
            if result:
                if "stdout" in result:
                    result["stdout"] = f"{index_result.get('index_summary', '')}\n\n{result['stdout']}"
                else:
                    result["stdout"] = index_result.get('index_summary', '')
                    
            return result
                
        except Exception as e:
            logger.error(f"Tree-sitter 分析失败: {str(e)}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Tree-sitter 分析失败: {str(e)}"
            }

