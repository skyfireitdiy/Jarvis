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
                file_extensions, exclude_dirs, analysis_depth
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
                             analysis_depth: int) -> str:
        """
        创建Agent的system prompt
        
        Args:
            function_name: 函数名称
            file_path: 函数所在文件路径
            root_dir: 代码库根目录
            file_extensions: 文件扩展名列表
            exclude_dirs: 排除目录列表
            analysis_depth: 子函数分析深度
            
        Returns:
            系统提示文本
        """
        file_ext_str = " ".join([f"*{ext}" for ext in file_extensions]) if file_extensions else ""
        exclude_str = " ".join([f"--glob '!{excl}'" for excl in exclude_dirs]) if exclude_dirs else ""
        
        depth_description = "不分析子函数" if analysis_depth == 0 else f"分析 {analysis_depth} 层子函数"
        file_info = f"已知文件路径: {file_path}" if file_path else "需要首先查找函数定义位置"
        
        return f"""你是一个代码分析专家，专门深入分析函数的内部实现。

## 当前任务
深入分析 `{function_name}` 函数的内部实现，包括子函数调用、全局变量使用等详细信息。

## 工作目录（当前目录）
{root_dir}

## 分析参数
- 函数名称: {function_name}
- {file_info}
- 分析深度: {depth_description}
- 文件类型限制: {file_ext_str if file_ext_str else "所有文件"}
- 排除目录: {", ".join(exclude_dirs) if exclude_dirs else "无"}

## 分析流程
请按照以下步骤进行函数分析:

1. **查找函数定义**
   - {"使用给定的文件路径查找函数定义" if file_path else "使用ripgrep(rg)或grep查找函数定义位置"}
   - 查找模式: `def\\s+{function_name}\\b`（对于Python）或使用其他语言的适当模式
   - 确认找到的是完整的函数定义，而非函数调用或注释

2. **分析函数签名**
   - 确定函数的参数类型和返回类型（如果有类型注解）
   - 记录默认参数值
   - 分析函数的文档字符串(docstring)，了解函数的目的和用法

3. **分析函数体**
   - 识别函数使用的局部变量
   - 查找函数使用的全局变量（通过`global`关键字或直接使用模块级变量）
   - 识别条件分支和循环结构
   - 确定异常处理模式

4. **分析子函数调用**
   - 识别函数中调用的所有其他函数
   - 区分标准库函数、第三方库函数和项目内部函数
   - {"对每个子函数进行类似的分析，深度不超过 " + str(analysis_depth) + " 层" if analysis_depth > 0 else "仅列出子函数，不进行深入分析"}

5. **识别数据流**
   - 追踪函数参数在函数体内的使用
   - 分析函数的返回值是如何构建的
   - 识别函数的副作用（如修改全局状态、文件IO等）

## 信息完整性要求
- 确保捕获函数的所有分支和执行路径，不遗漏条件处理
- 详细分析所有参数的使用方式和影响范围
- 完整识别所有子函数调用及其上下文
- 全面列出函数对外部状态的所有影响和依赖
- 不要忽略异常处理路径和边缘情况处理
- 特别关注函数内的复杂逻辑块和潜在性能瓶颈
- 对于复杂函数，确保分析递归调用、回调和异步执行模式

## 工具使用建议
- 使用 `execute_shell` 执行搜索命令:
  ```
  # 查找函数定义示例（Python）
  rg -n "def\\s+{function_name}\\b" {file_ext_str} {exclude_str}
  
  # 查找全局变量使用示例（Python）
  rg -n "global\\s+\\w+" --include="{file_path}"
  ```
  
- 使用 `read_code` 读取函数定义和相关代码:
  ```
  # 读取整个文件以获取上下文
  read_code {{
    "files": [
      {{
        "path": "{file_path or '找到的文件路径'}",
        "start_line": 1,
        "end_line": -1
      }}
    ]
  }}
  ```

分析完成后，请提供函数的详细分析报告，包括函数签名、全局变量使用、子函数调用等信息。
"""

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
        
        return f"""请提供 `{function_name}` 函数的完整分析报告，{depth_description}。报告应包含以下部分:

# 函数分析报告: `{function_name}`

## 基本信息
- 函数位置: 文件路径和行号
- 函数签名: 完整的函数定义，包括参数和返回类型
- 函数文档: 函数的文档字符串或注释说明

## 功能概述
简要描述函数的主要功能和目的

## 参数分析
- 参数列表及类型
- 默认值和可选参数
- 参数在函数中的使用方式

## 全局依赖
- 使用的全局变量列表
- 导入的模块和库
- 使用的环境变量或配置项

## 子函数调用
- 直接调用的函数列表
- 每个调用的目的和上下文
{"- 子函数的进一步分析（最多 " + str(analysis_depth) + " 层）" if analysis_depth > 0 else ""}

## 控制流程
- 主要条件分支
- 循环结构
- 异常处理模式

## 数据流分析
- 输入数据如何被处理
- 输出/返回值如何被构建
- 关键数据转换步骤

## 潜在问题与优化机会
- 识别的代码复杂性或潜在问题
- 可能的优化建议
- 安全性或性能考虑

请确保报告格式清晰，使用Markdown语法以便阅读。对于复杂函数，可以使用代码块和列表来增强可读性。重点关注函数的核心逻辑和关键依赖。
""" 