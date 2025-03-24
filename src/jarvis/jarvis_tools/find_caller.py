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
            "objective": {
                "type": "string",
                "description": "描述本次调用者查找的目标和用途，例如'评估修改函数的影响范围'",
                "default": ""
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
                function_name, root_dir, file_extensions, exclude_dirs, objective
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
                platform=PlatformRegistry().get_thinking_platform(),
                output_handler=[tool_registry],
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
                             objective: str) -> str:
        """
        创建Agent的system prompt
        
        Args:
            function_name: 函数名称
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
        
        search_pattern = f"\\b{function_name}\\s*\\("
        
        return f"""# 函数调用分析专家

## 任务描述
查找所有调用 `{function_name}` 函数的代码位置，专注于分析目标所需的信息，生成有针对性的调用分析报告。{objective_text}

## 工具使用优先级
1. **优先使用 execute_shell 执行 rg 命令**: 
   - `rg "\\b{function_name}\\s*\\(" --type py` 查找Python文件中的调用
   - `rg "\\b{function_name}\\s*\\(" --type js` 查找JavaScript文件中的调用
   - `rg -w "{function_name}" -A 2 -B 2` 查看调用上下文

2. **辅以 read_code**: 
   - 找到调用位置后使用read_code阅读上下文
   - 读取关键调用者的完整实现

3. **避免使用专用分析工具**:
   - 只有当rg命令和read_code工具无法满足需求时才考虑

## 工作环境
- 工作目录: `{root_dir}`
- 文件类型: {file_ext_str if file_ext_str else "所有文件"}
- 排除目录: {", ".join(exclude_dirs) if exclude_dirs else "无"}

## 分析策略
1. 首先确定项目的主要编程语言和技术栈，以便更精确地查找函数调用
2. 理解分析目标，明确需要查找的信息类型
3. 使用适当的rg搜索模式查找函数调用
4. 验证搜索结果，确认是对目标函数的真正调用
5. 分析调用上下文，了解调用的目的和方式
6. 根据分析目标自行确定需要的分析深度和广度

## 调用者查找工具指南

### execute_shell 搜索命令
- **基本搜索**: 
  - `rg "\\b{function_name}\\s*\\(" --type=文件类型`
  - 示例: `rg "\\b{function_name}\\s*\\(" --type py` 搜索Python文件中的调用

- **查看上下文**:
  - `rg "\\b{function_name}\\s*\\(" -A 5 -B 5` 显示调用前后5行
  - `rg "\\b{function_name}\\s*\\(" --context=10` 显示调用前后10行

- **排除目录**:
  - `rg "\\b{function_name}\\s*\\(" --type py -g '!tests/'` 排除测试目录
  - `rg "\\b{function_name}\\s*\\(" -g '!node_modules/'` 排除node_modules

- **统计调用**:
  - `rg -c "\\b{function_name}\\s*\\(" --type py` 统计每个Python文件中的调用次数
  - `rg "\\b{function_name}\\s*\\(" --count-matches --stats` 显示调用统计信息

### read_code
- **用途**：读取找到的调用点上下文
- **典型用法**：
  - 读取调用函数的整个方法或类
  - 读取调用点的上下文行（前后5-10行）
- **使用策略**：
  - 首先读取足够的上下文以理解调用目的
  - 对于复杂调用，可能需要读取整个调用函数
  - 关注调用前的参数准备和调用后的结果处理

### 调用者分析模式

1. **影响范围评估模式**：
   - 查找所有调用点: `rg -l "\\b{function_name}\\s*\\("`
   - 按模块/组件分类调用位置
   - 评估修改函数可能影响的范围和严重性

2. **使用模式分析**：
   - 分析各调用点的参数传递方式
   - 识别典型的调用模式和变体
   - 总结函数的不同使用场景

3. **依赖关系追踪**：
   - 识别直接调用者
   - 分析这些调用者自身被谁调用
   - 构建完整的调用链或调用树

4. **调用频率分析**：
   - 统计不同模块中的调用频率: `rg -c "\\b{function_name}\\s*\\(" --sort path`
   - 识别高频调用点和关键路径
   - 评估函数在系统中的重要性

5. **异常使用检测**：
   - 检查是否存在异常的调用模式
   - 识别可能存在问题的调用点
   - 提出优化或修正建议

## 搜索技巧
- 根据不同编程语言调整函数调用模式的搜索方式
- 考虑各种编程范式下的不同调用方式（面向对象、函数式等）
- 考虑函数可能通过变量或回调方式间接调用
- 检查可能存在的同名函数，确保找到的是目标函数的调用

## 输出要求
- 直接回应分析目标的关键问题
- 提供与目标相关的调用信息
- 分析内容应直接服务于分析目标
- 避免与目标无关的冗余信息
- 使用具体代码路径和调用示例支持分析结论
- 提供针对分析目标的具体见解和建议"""

    def _create_summary_prompt(self, function_name: str) -> str:
        """
        创建Agent的summary prompt
        
        Args:
            function_name: 函数名称
            
        Returns:
            总结提示文本
        """
        return f"""# 函数 `{function_name}` 调用分析报告

## 报告要求
生成一份完全以分析目标为导向的函数调用分析报告。不要遵循固定的报告模板，而是完全根据分析目标来组织内容：

- 首先简要说明项目的主要编程语言和技术栈
- 专注回答分析目标提出的问题
- 只包含与分析目标直接相关的调用发现和洞察
- 完全跳过与分析目标无关的内容，无需做全面分析
- 分析深度应与目标的具体需求匹配
- 使用具体的代码调用示例支持你的观点
- 以清晰的Markdown格式呈现，简洁明了

在分析中保持灵活性，避免固定思维模式。你的任务不是提供全面的函数调用概览，而是直接解决分析目标中提出的具体问题。"""
