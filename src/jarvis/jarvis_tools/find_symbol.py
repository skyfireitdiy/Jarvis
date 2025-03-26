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
                platform=PlatformRegistry().get_normal_platform(),
                output_handler=[tool_registry],
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

## 工具使用优先级
1. **优先使用 execute_shell 执行 rg 命令**:
   - `rg -w "{symbol}" --type py` 查找Python文件中的符号
   - `rg "class\\s+{symbol}|def\\s+{symbol}" --type py` 查找定义
   - `rg -w "{symbol}" -A 2 -B 2` 查看符号上下文

2. **辅以 read_code**:
   - 找到符号位置后使用read_code阅读上下文
   - 读取符号定义和关键引用的完整实现

3. **避免使用专用分析工具**:
   - 只有当rg命令和read_code工具无法满足需求时才考虑

## 工作环境
- 工作目录: `{root_dir}`
- 文件类型: {file_ext_str if file_ext_str else "所有文件"}
- 排除目录: {", ".join(exclude_dirs) if exclude_dirs else "无"}

## 分析策略
1. 首先确定项目的主要编程语言和技术栈，以便更精确地查找符号
2. 理解分析目标，明确需要查找的信息类型
3. 使用适当的rg搜索模式查找符号定义和引用
4. 验证搜索结果，确认是目标符号的真正使用
5. 分析符号上下文，了解其用途和使用方式
6. 根据分析目标自行确定需要的分析深度和广度

## 符号查找工具指南

### execute_shell 搜索命令
- **基本搜索**:
  - `rg -w "{symbol}" --type=文件类型`
  - 示例: `rg -w "{symbol}" --type py` 搜索Python文件中的符号

- **查找定义**:
  - `rg "class\\s+{symbol}\\b|def\\s+{symbol}\\b|function\\s+{symbol}\\b" --type py` 查找Python定义
  - `rg "class\\s+{symbol}\\b|function\\s+{symbol}\\b" --type js` 查找JavaScript定义
  - `rg "const\\s+{symbol}\\b|let\\s+{symbol}\\b|var\\s+{symbol}\\b" --type js` 查找JavaScript变量声明

- **查看上下文**:
  - `rg -w "{symbol}" -A 5 -B 5` 显示符号前后5行
  - `rg -w "{symbol}" --context=10` 显示符号前后10行

- **排除目录**:
  - `rg -w "{symbol}" --type py -g '!tests/'` 排除测试目录
  - `rg -w "{symbol}" -g '!node_modules/'` 排除node_modules

- **统计引用**:
  - `rg -c -w "{symbol}" --type py` 统计每个Python文件中的引用次数
  - `rg -w "{symbol}" --count-matches --stats` 显示引用统计信息

### read_code
- **用途**：读取符号定义和使用的上下文
- **典型用法**：
  - 读取符号定义所在的文件区域
  - 读取关键使用位置的上下文
- **使用策略**：
  - 首先读取符号的定义以理解其属性和行为
  - 然后读取典型使用场景的代码
  - 重点关注频繁使用的模式和关键功能点

### 符号分析模式

1. **定义分析模式**：
   - 首先找到符号的所有定义位置
   - 分析定义的类型（类、函数、变量、常量等）
   - 理解符号的属性、参数、返回值等特性
   - 查看相关注释和文档字符串

2. **使用模式分析**：
   - 分类统计不同类型的使用方式
   - 识别典型的使用模式和上下文
   - 总结符号的主要用途和功能

3. **影响范围评估**：
   - 统计符号在不同模块中的使用频率
   - 分析符号修改可能影响的代码范围
   - 识别关键依赖点和潜在风险区域

4. **符号关系网络分析**：
   - 分析与目标符号相关的其他符号
   - 识别依赖该符号的组件
   - 了解该符号依赖的其他组件

## 编程范式适应

无论项目使用什么编程语言或范式，符号分析都应考虑以下方面：

### 对象导向程序
- 类定义、继承关系和实例化
- 方法重载和覆盖
- 成员变量和属性访问

### 函数式编程
- 高阶函数和函数传递
- 不可变数据结构
- 闭包和作用域

### 过程式编程
- 全局和局部变量
- 函数调用关系
- 数据流动

### 声明式编程
- 规则和约束定义
- 模式匹配
- 数据转换

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
