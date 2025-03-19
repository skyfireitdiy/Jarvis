from typing import Dict, Any, List
import os

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class SymbolTool:
    """
    符号查找工具
    使用agent查找代码库中的符号引用、定义和声明位置
    """
    
    name = "find_symbol"
    description = "查找代码符号的引用、定义和声明位置"
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
                "default": 50
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
            max_results = args.get("max_results", 50)
            
            # 验证参数
            if not symbol:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "必须提供符号名称"
                }
            
            # 创建agent的system prompt
            system_prompt = self._create_system_prompt(
                symbol, root_dir, file_extensions, exclude_dirs, max_results
            )
            
            # 创建agent的summary prompt
            summary_prompt = self._create_summary_prompt(symbol)
            
            # 切换到根目录
            os.chdir(root_dir)
            
            # 构建使用的工具
            from jarvis.jarvis_tools.registry import ToolRegistry
            tool_registry = ToolRegistry()
            tool_registry.use_tools(["execute_shell", "read_code"])
            
            # 创建并运行agent
            symbol_agent = Agent(
                system_prompt=system_prompt,
                name=f"SymbolFinder-{symbol}",
                description=f"查找符号 '{symbol}' 的引用和定义位置",
                summary_prompt=summary_prompt,
                platform=PlatformRegistry().get_codegen_platform(),
                output_handler=[tool_registry],
                need_summary=True,
                is_sub_agent=True,
                use_methodology=False,
                record_methodology=False,
                execute_tool_confirm=False,
                auto_complete=True
            )
            
            # 运行agent并获取结果
            task_input = f"查找符号 '{symbol}' 在代码库中的引用、定义和声明位置"
            result = symbol_agent.run(task_input)
            
            return {
                "success": True,
                "stdout": result,
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
    
    def _create_system_prompt(self, symbol: str, root_dir: str, 
                             file_extensions: List[str], exclude_dirs: List[str],
                             max_results: int) -> str:
        """
        创建Agent的system prompt
        
        Args:
            symbol: 符号名称
            root_dir: 代码库根目录
            file_extensions: 文件扩展名列表
            exclude_dirs: 排除目录列表
            max_results: 最大结果数量
            
        Returns:
            系统提示文本
        """
        file_ext_str = " ".join([f"*{ext}" for ext in file_extensions]) if file_extensions else ""
        exclude_str = " ".join([f"--glob '!{excl}'" for excl in exclude_dirs]) if exclude_dirs else ""
        
        return f"""你是一个代码符号分析专家，专门查找代码库中的符号引用、定义和声明。

## 当前任务
查找符号 `{symbol}` 在代码库中的定义、声明和引用位置。

## 工作目录（当前目录）
{root_dir}

## 搜索参数
- 符号名称: {symbol}
- 文件类型限制: {file_ext_str if file_ext_str else "所有文件"}
- 排除目录: {", ".join(exclude_dirs) if exclude_dirs else "无"}
- 最大结果数: {max_results}

## 查找流程
请按照以下步骤进行符号分析:

1. **查找符号定义/声明**
   - 使用ripgrep(rg)或grep查找可能的定义和声明
   - 对于不同语言，定义模式会有所不同:
     - Python: `def {symbol}`, `class {symbol}`, `{symbol} =`
     - JavaScript/TypeScript: `function {symbol}`, `const {symbol}`, `let {symbol}`, `var {symbol}`, `class {symbol}`
     - C/C++: 函数定义、变量定义/声明、结构体/类定义
     - Java: 方法定义、变量定义/声明、类/接口定义
     - Go: `func {symbol}`, `type {symbol}`, `var {symbol}`, `const {symbol}`

2. **查找符号引用**
   - 使用精确匹配搜索所有引用位置
   - 确保使用单词边界(\\b)匹配完整符号，避免部分匹配

3. **结果分析**
   - 对于每个定义/声明，阅读上下文确认其准确性
   - 对于引用，按文件分组并排序
   - 过滤掉重复或不相关的结果
   - 如果结果过多，优先选择最相关的结果

## 信息完整性要求
- 确保找到所有符号的定义和声明位置，不遗漏任何重载或多态定义
- 完整捕获所有引用，包括不明显的引用方式（如通过别名或反射）
- 区分不同作用域下的同名符号，明确指出歧义情况
- 对于具有特殊用途的引用（如关键业务逻辑中的使用），予以特别标注
- 报告所有可能的引用模式变体和上下文
- 不要忽略注释、字符串或文档中的符号引用，但要区分代码引用和非代码引用

## 工具使用建议
- 使用 `execute_shell` 执行搜索命令:
  ```
  # 查找定义示例
  rg -n "def\\s+{symbol}\\b|class\\s+{symbol}\\b|{symbol}\\s*=" {file_ext_str} {exclude_str}
  
  # 查找引用示例
  rg -n "\\b{symbol}\\b" {file_ext_str} {exclude_str}
  ```
  
- 使用 `read_code` 读取相关代码上下文以确认结果的准确性

分析完成后，请提供符号的定义位置、所有引用点，并统计总体情况。
"""

    def _create_summary_prompt(self, symbol: str) -> str:
        """
        创建Agent的summary prompt
        
        Args:
            symbol: 符号名称
            
        Returns:
            总结提示文本
        """
        return f"""请提供符号 `{symbol}` 的完整分析报告，包含以下部分:

# 符号分析: `{symbol}`

## 定义/声明
提供所有找到的定义/声明位置，包括:
- 文件路径和行号
- 定义/声明的代码片段
- 定义类型(函数、类、变量等)

## 引用
按文件分组列出所有引用:
- 文件路径
- 每个引用的行号
- 引用的代码上下文

## 统计
- 定义/声明数量
- 引用总数
- 引用文件数量
- 分布情况分析

## 代码职责
简要分析符号在代码库中的职责和作用

请确保报告格式清晰，使用Markdown语法以便阅读。如果结果过多，可以只包含最重要的几个定义和引用示例。
"""
