from typing import Dict, Any, List
import os

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class FindCallerTool:
    """
    函数调用者查找工具
    使用agent查找代码库中所有调用指定函数的位置
    """
    
    name = "find_caller"
    description = "查找所有调用指定函数的代码位置"
    parameters = {
        "type": "object",
        "properties": {
            "function_name": {
                "type": "string",
                "description": "要查找调用者的函数名称"
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
        "required": ["function_name"]
    }
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行调用者查找工具
        
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
            root_dir = args.get("root_dir", ".")
            file_extensions = args.get("file_extensions", [])
            exclude_dirs = args.get("exclude_dirs", [])
            max_results = args.get("max_results", 50)
            
            # 验证参数
            if not function_name:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "必须提供函数名称"
                }
            
            # 创建agent的system prompt
            system_prompt = self._create_system_prompt(
                function_name, root_dir, file_extensions, exclude_dirs, max_results
            )
            
            # 创建agent的summary prompt
            summary_prompt = self._create_summary_prompt(function_name)
            
            # 切换到根目录
            os.chdir(root_dir)
            
            # 构建使用的工具
            from jarvis.jarvis_tools.registry import ToolRegistry
            tool_registry = ToolRegistry()
            tool_registry.use_tools(["execute_shell", "read_code"])
            
            # 创建并运行agent
            caller_agent = Agent(
                system_prompt=system_prompt,
                name=f"CallerFinder-{function_name}",
                description=f"查找 '{function_name}' 函数的所有调用位置",
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
            task_input = f"查找所有调用 '{function_name}' 函数的代码位置"
            result = caller_agent.run(task_input)
            
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
                "stderr": f"查找调用者失败: {str(e)}"
            }
        finally:
            # 恢复原始目录
            os.chdir(original_dir)
    
    def _create_system_prompt(self, function_name: str, root_dir: str, 
                             file_extensions: List[str], exclude_dirs: List[str],
                             max_results: int) -> str:
        """
        创建Agent的system prompt
        
        Args:
            function_name: 函数名称
            root_dir: 代码库根目录
            file_extensions: 文件扩展名列表
            exclude_dirs: 排除目录列表
            max_results: 最大结果数量
            
        Returns:
            系统提示文本
        """
        file_ext_str = " ".join([f"*{ext}" for ext in file_extensions]) if file_extensions else ""
        exclude_str = " ".join([f"--glob '!{excl}'" for excl in exclude_dirs]) if exclude_dirs else ""
        
        search_pattern = f"\\b{function_name}\\s*\\("
        
        return f"""你是一个代码分析专家，专门查找代码库中的函数调用关系。

## 当前任务
查找所有调用 `{function_name}` 函数的代码位置。

## 工作目录（当前目录）
{root_dir}

## 搜索参数
- 函数名称: {function_name}
- 文件类型限制: {file_ext_str if file_ext_str else "所有文件"}
- 排除目录: {", ".join(exclude_dirs) if exclude_dirs else "无"}
- 最大结果数: {max_results}

## 查找流程
请按照以下步骤进行函数调用者分析:

1. **查找直接调用**
   - 使用ripgrep(rg)或grep查找可能的函数调用位置
   - 查找模式: `{search_pattern}`
   - 确保使用单词边界(\\b)匹配完整函数名，避免部分匹配
   - 注意许多函数可能同名，需要分析上下文确定是否是目标函数

2. **验证调用**
   - 检查每个匹配位置的上下文，确认是真正的函数调用而非相似字符串或注释
   - 分析函数调用的上下文和参数，以确定是否与目标函数的签名匹配
   - 对于同名函数，可能需要分析导入语句或模块前缀来确认

3. **结果分析**
   - 按文件分组并整理调用位置
   - 过滤掉重复或不相关的结果
   - 对于每个调用位置，提供足够的上下文，以便理解调用方式和目的
   - 如果结果过多，优先列出最明确的调用，最多展示 {max_results} 个结果

## 信息完整性要求
- 确保找出所有可能的函数调用，不遗漏任何可能的调用代码
- 识别并报告不同调用模式（直接调用、回调传递、间接引用等）
- 区分同名函数，确保准确识别目标函数的调用
- 捕获所有调用上下文和调用方式的变体
- 即使是不寻常或易被忽视的调用模式也要报告
- 对于复杂的调用关系，提供清晰的解释以避免遗漏关键信息

## 工具使用建议
- 使用 `execute_shell` 执行搜索命令:
  ```
  # 查找函数调用示例
  rg -n "{search_pattern}" {file_ext_str} {exclude_str}
  ```
  
- 使用 `read_code` 读取相关代码上下文，以确认调用关系并理解调用方式
- 可能需要检查函数定义以确认正确的函数签名

分析完成后，请提供所有函数调用位置、调用方式，并统计总体情况。
"""

    def _create_summary_prompt(self, function_name: str) -> str:
        """
        创建Agent的summary prompt
        
        Args:
            function_name: 函数名称
            
        Returns:
            总结提示文本
        """
        return f"""请提供 `{function_name}` 函数调用分析的完整报告，包含以下部分:

# 函数调用分析: `{function_name}`

## 函数定义
简要描述函数的定义位置和作用(如果能找到)：
- 所在文件和行号
- 函数签名
- 函数功能摘要

## 直接调用者
列出所有直接调用该函数的位置:
- 调用者文件路径和行号
- 调用上下文代码片段
- 调用方式(如何传参、调用目的等)

## 统计信息
- 直接调用次数
- 调用者文件数量
- 最常见的调用模式

## 使用模式分析
分析函数被调用的主要使用模式：
- 函数在代码库中扮演的角色
- 典型的调用场景和目的
- 常见的参数传递模式

请确保报告格式清晰，使用Markdown语法以便阅读。如果结果过多，可以只包含最重要的几个调用示例，并重点关注高频调用模式。
"""
