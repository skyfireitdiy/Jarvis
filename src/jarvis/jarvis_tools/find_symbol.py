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
            "objective": {
                "type": "string",
                "description": "描述本次符号查找的目标和用途，例如'了解该符号的使用模式以便重构'",
                "default": ""
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
            objective = args.get("objective", "")
            
            # 验证参数
            if not symbol:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "必须提供符号名称"
                }
            
            # 创建agent的system prompt
            system_prompt = self._create_system_prompt(
                symbol, root_dir, file_extensions, exclude_dirs, objective
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
                             objective: str) -> str:
        """
        创建Agent的system prompt
        
        Args:
            symbol: 符号名称
            root_dir: 代码库根目录
            file_extensions: 文件扩展名列表
            exclude_dirs: 排除目录列表
            objective: 分析目标
            
        Returns:
            系统提示文本
        """
        file_ext_str = " ".join([f"*{ext}" for ext in file_extensions]) if file_extensions else ""
        exclude_str = " ".join([f"--glob '!{excl}'" for excl in exclude_dirs]) if exclude_dirs else ""
        objective_text = f"\n\n## 分析目标\n{objective}" if objective else ""
        
        return f"""# 代码符号分析专家

## 任务描述
查找符号 `{symbol}` 在代码库中的定义、声明和引用位置，专注于分析目标所需的信息，生成有针对性的符号分析报告。{objective_text}

## 工作环境
- 工作目录: `{root_dir}`
- 文件类型: {file_ext_str if file_ext_str else "所有文件"}
- 排除目录: {", ".join(exclude_dirs) if exclude_dirs else "无"}

## 分析策略
1. 首先确定项目的主要编程语言和技术栈，以便更精确地查找符号
2. 理解分析目标，明确需要查找的信息类型
3. 使用适当的搜索模式查找符号定义和引用
4. 验证搜索结果，确认是目标符号的真正使用
5. 分析符号上下文，了解其用途和使用方式
6. 根据分析目标自行确定需要的分析深度和广度

## 输出要求
- 直接回应分析目标的关键问题
- 提供与目标相关的符号信息
- 分析内容应直接服务于分析目标
- 避免与目标无关的冗余信息
- 使用具体代码路径和使用示例支持分析结论
- 提供针对分析目标的具体见解和建议"""

    def _create_summary_prompt(self, symbol: str) -> str:
        """
        创建Agent的summary prompt
        
        Args:
            symbol: 符号名称
            
        Returns:
            总结提示文本
        """
        return f"""# 符号 `{symbol}` 分析报告

## 报告要求
生成一份完全以分析目标为导向的符号分析报告。不要遵循固定的报告模板，而是完全根据分析目标来组织内容：

- 首先简要说明项目的主要编程语言和技术栈
- 专注回答分析目标提出的问题
- 只包含与分析目标直接相关的符号发现和洞察
- 完全跳过与分析目标无关的内容，无需做全面分析
- 分析深度应与目标的具体需求匹配
- 使用具体的代码示例支持你的观点
- 以清晰的Markdown格式呈现，简洁明了

在分析中保持灵活性，避免固定思维模式。你的任务不是提供全面的符号概览，而是直接解决分析目标中提出的具体问题。"""
