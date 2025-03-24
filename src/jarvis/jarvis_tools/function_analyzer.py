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
                platform=PlatformRegistry().get_thinking_platform(),
                output_handler=[tool_registry],
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

## 工具使用优先级
1. **首先使用 execute_shell 执行 rg 命令查找函数定义**: 
   - `rg "def\\s+{function_name}\\s*\\(" --type py` 查找Python函数定义
   - `rg "function\\s+{function_name}\\s*\\(" --type js` 查找JavaScript函数定义
   - `rg "func\\s+{function_name}\\s*\\(" --type go` 查找Go函数定义

2. **优先使用 read_code 阅读函数实现**: 
   - 找到函数位置后使用read_code阅读完整实现
   - 对于长函数可分段读取关键部分

3. **使用 rg 搜索子函数调用和使用模式**:
   - `rg -w "子函数名" --type py` 查找子函数调用
   - `rg "import|from" 函数所在文件` 查找导入模块

4. **避免使用专用分析工具**:
   - 只有当rg命令和read_code工具无法满足需求时才考虑

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

## 函数分析工具指南

### execute_shell 搜索命令
- **查找函数定义**:
  - `rg "def\\s+{function_name}\\s*\\(" --type py` 查找Python函数定义
  - `rg "function\\s+{function_name}\\s*\\(" --type js` 查找JavaScript函数定义
  - `rg "func\\s+{function_name}\\s*\\(" --type go` 查找Go函数定义

- **查找函数调用**:
  - `rg "\\b{function_name}\\s*\\(" --type py` 查找函数调用
  - `rg -w "{function_name}" -A 2 -B 2` 查看函数调用上下文

- **分析函数依赖**:
  - `rg "import|from" 函数所在文件` 查找Python导入语句
  - `rg "require\\(" 函数所在文件` 查找JavaScript导入语句
  - `rg "import " 函数所在文件` 查找Go导入语句

- **统计分析**:
  - `loc 函数所在文件` 获取文件代码统计
  - `rg -c "if|else|elif" 函数所在文件` 统计条件分支数量
  - `rg -c "for|while" 函数所在文件` 统计循环数量

### read_code
- **用途**：读取函数实现和相关代码
- **典型用法**：
  - 阅读完整函数实现，包括注释和文档
  - 阅读关键子函数的实现（根据analysis_depth）
  - 阅读使用到的关键变量和依赖组件定义
- **使用策略**：
  - 首先阅读整个函数以获取完整视图
  - 识别函数的主要逻辑分支和处理路径
  - 重点关注错误处理和边界条件检查
  - 对复杂子函数进行递归分析（不超过指定深度）

### 函数分析模式

1. **逻辑流程分析**：
   - 识别函数的主要执行路径
   - 分析条件分支和循环结构
   - 构建完整的逻辑流程图

2. **参数分析**：
   - 分析参数类型、默认值和约束条件
   - 了解参数在函数中的使用方式
   - 识别关键参数及其影响

3. **依赖与副作用分析**：
   - 识别函数使用的外部变量和组件
   - 分析函数对外部状态的修改
   - 评估函数的纯度和可测试性

4. **异常处理分析**：
   - 识别可能的异常和错误情况
   - 分析错误处理和恢复机制
   - 评估错误处理的完整性和合理性

5. **性能分析**：
   - 识别潜在的性能瓶颈
   - 分析循环和递归的效率
   - 评估算法复杂度

6. **子函数调用分析**：
   - 识别所有调用的子函数
   - 分析子函数的作用和调用模式
   - 在允许的深度内递归分析关键子函数

## 编程范式适应

针对不同的编程范式，函数分析应关注不同方面：

### 过程式/函数式
- 输入输出关系和纯函数特性
- 控制流程和数据转换
- 递归和迭代模式

### 面向对象
- 方法与类的交互
- 状态修改和实例变量访问
- 继承和多态特性

### 事件驱动/回调式
- 事件注册和触发机制
- 回调链和异步流程
- 状态管理和并发控制

### 声明式
- 规则和约束定义
- 表达式和模式匹配
- 执行上下文和环境

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