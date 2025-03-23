from typing import Dict, Any, List
import os

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class FunctionAnalyzerTool:
    """
    函数分析工具
    使用agent深入分析函数内部实现，包括子函数调用、全局变量使用等
    """
    
    name = "function_analyzer"
    description = "深入分析函数内部实现，查找子函数调用、全局变量使用等详细信息"
    parameters = {
        "type": "object",
        "properties": {
            "function_name": {
                "type": "string",
                "description": "要分析的函数名称"
            },
            "file_path": {
                "type": "string",
                "description": "函数所在文件路径（如果已知）",
                "default": ""
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
            "analysis_depth": {
                "type": "integer",
                "description": "子函数分析深度（可选），0表示不分析子函数，1表示分析直接子函数，以此类推",
                "default": 1
            },
            "objective": {
                "type": "string",
                "description": "描述本次函数分析的目标和用途，例如'理解函数实现以便重构'或'评估性能瓶颈'",
                "default": ""
            }
        },
        "required": ["function_name"]
    }
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行函数分析工具
        
        Args:
            args: 包含参数的字典
            
        Returns:
            包含执行结果的字典
        """
        # 存储原始目录
        original_dir = os.getcwd()
        
        try:
            # 解析参数
            function_name = args.get("function_name", "")
            file_path = args.get("file_path", "")
            root_dir = args.get("root_dir", ".")
            file_extensions = args.get("file_extensions", [])
            exclude_dirs = args.get("exclude_dirs", [])
            analysis_depth = args.get("analysis_depth", 1)
            objective = args.get("objective", "")
            
            # 验证参数
            if not function_name:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "必须提供函数名称"
                }
            
            # 创建agent的system prompt
            system_prompt = self._create_system_prompt(
                function_name, file_path, root_dir, 
                file_extensions, exclude_dirs, analysis_depth, objective
            )
            
            # 创建agent的summary prompt
            summary_prompt = self._create_summary_prompt(function_name, analysis_depth)
            
            # 切换到根目录
            os.chdir(root_dir)
            
            # 构建使用的工具
            from jarvis.jarvis_tools.registry import ToolRegistry
            tool_registry = ToolRegistry()
            tool_registry.use_tools(["execute_shell", "read_code"])
            
            # 创建并运行agent
            analyzer_agent = Agent(
                system_prompt=system_prompt,
                name=f"FunctionAnalyzer-{function_name}",
                description=f"分析 '{function_name}' 函数的内部实现",
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
            task_input = f"深入分析 '{function_name}' 函数的内部实现，包括子函数调用、全局变量使用等详细信息"
            result = analyzer_agent.run(task_input)
            
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
                "stderr": f"函数分析失败: {str(e)}"
            }
        finally:
            # 恢复原始目录
            os.chdir(original_dir)
    
    def _create_system_prompt(self, function_name: str, file_path: str, root_dir: str, 
                             file_extensions: List[str], exclude_dirs: List[str],
                             analysis_depth: int, objective: str) -> str:
        """
        创建Agent的system prompt
        
        Args:
            function_name: 函数名称
            file_path: 函数所在文件路径
            root_dir: 代码库根目录
            file_extensions: 文件扩展名列表
            exclude_dirs: 排除目录列表
            analysis_depth: 子函数分析深度
            objective: 分析目标
            
        Returns:
            系统提示文本
        """
        file_ext_str = " ".join([f"*{ext}" for ext in file_extensions]) if file_extensions else ""
        exclude_str = " ".join([f"--glob '!{excl}'" for excl in exclude_dirs]) if exclude_dirs else ""
        
        depth_description = "不分析子函数" if analysis_depth == 0 else f"分析 {analysis_depth} 层子函数"
        file_info = f"已知文件路径: {file_path}" if file_path else "需要首先查找函数定义位置"
        objective_text = f"\n\n## 分析目标\n{objective}" if objective else ""
        
        return f"""# 函数实现分析专家

## 任务描述
分析函数 `{function_name}` 的实现，专注于分析目标所需的信息，生成有针对性的函数分析报告。{objective_text}

## 函数信息
- 函数名称: `{function_name}`
- {file_info}
- 分析深度: {depth_description}
- 代码范围: {file_ext_str if file_ext_str else "所有文件"}
- 排除目录: {", ".join(exclude_dirs) if exclude_dirs else "无"}

## 分析策略
1. 首先确定项目的主要编程语言和技术栈，以便更准确地分析函数实现
2. 理解分析目标，明确需要查找的信息
3. {"在指定文件中定位函数定义" if file_path else "搜索代码库查找函数定义位置"}
4. 根据分析目标，确定重点分析的方面
5. 灵活调整分析深度，关注与目标相关的实现细节
6. 根据目标需要自行判断是否需要分析子函数

## 输出要求
- 直接回应分析目标的关键问题
- 提供与目标相关的函数实现信息
- 分析内容应直接服务于分析目标
- 避免与目标无关的冗余信息
- 使用具体代码片段和示例支持分析结论
- 提供针对分析目标的具体见解和建议"""

    def _create_summary_prompt(self, function_name: str, analysis_depth: int) -> str:
        """
        创建Agent的summary prompt
        
        Args:
            function_name: 函数名称
            analysis_depth: 子函数分析深度
            
        Returns:
            总结提示文本
        """
        depth_description = "不包含子函数分析" if analysis_depth == 0 else f"包含 {analysis_depth} 层子函数分析"
        
        return f"""# 函数分析报告: `{function_name}`

## 报告要求
生成一份完全以分析目标为导向的函数分析报告，{depth_description}。不要遵循固定的报告模板，而是完全根据分析目标来组织内容：

- 首先简要说明项目的主要编程语言和技术栈
- 专注回答分析目标提出的问题
- 只包含与分析目标直接相关的实现发现和洞察
- 完全跳过与分析目标无关的内容，无需做全面分析
- 分析深度应与目标的具体需求匹配
- 使用具体的代码片段支持你的观点
- 以清晰的Markdown格式呈现，简洁明了

在分析中保持灵活性，避免固定思维模式。你的任务不是提供全面的函数概览，而是直接解决分析目标中提出的具体问题。""" 