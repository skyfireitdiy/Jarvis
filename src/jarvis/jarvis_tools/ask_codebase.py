from typing import Dict, Any
import os


from jarvis.jarvis_agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.git_utils import find_git_root
from jarvis.jarvis_utils.utils import init_env

class AskCodebaseTool:
    """用于智能代码库查询和分析的工具

    适用场景：
    - 查询特定功能所在的文件位置（支持所有文件类型）
    - 了解单个功能点的实现原理（支持所有文件类型）
    - 查找特定API或接口的用法（支持所有文件类型）

    不适用场景：
    - 跨越多文件的大范围分析
    - 复杂系统架构的全面评估
    - 需要深入上下文理解的代码重构
    """

    name = "ask_codebase"
    description = "查询代码库中特定功能的位置和实现原理，适合定位功能所在文件和理解单点实现"
    labels = ['code', 'analysis', 'qa']
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "关于代码库的问题，例如'登录功能在哪个文件实现？'或'如何实现了JWT验证？'"
            },
            "root_dir": {
                "type": "string",
                "description": "代码库根目录路径（可选）",
                "default": "."
            }
        },
        "required": ["question"]
    }

    def __init__(self, auto_complete: bool = True):
        self.auto_complete = auto_complete

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute codebase analysis using an Agent with execute_script

        Args:
            args: Dictionary containing:
                - question: The question to answer, preferably about locating functionality
                  or understanding implementation details of a specific feature
                - top_k: Optional number of files to analyze
                - root_dir: Optional root directory of the codebase

        Returns:
            Dict containing:
                - success: Boolean indicating success
                - stdout: Analysis result
                - stderr: Error message if any

        Note:
            This tool works best for focused questions about specific features or implementations.
            It is not designed for comprehensive multi-file analysis or complex architectural questions.
        """
        try:
            question = args["question"]
            root_dir = args.get("root_dir", ".")

            # Store current directory
            original_dir = os.getcwd()

            try:
                # Change to root_dir
                os.chdir(root_dir)

                # Get git root directory
                git_root = find_git_root() or os.getcwd()

                # Create system prompt for the Agent
                system_prompt = self._create_system_prompt(question, git_root)

                # Create summary prompt for the Agent
                summary_prompt = self._create_summary_prompt(question)

                # Create tools registry
                from jarvis.jarvis_tools.registry import ToolRegistry
                tool_registry = ToolRegistry()
                tool_registry.use_tools(["execute_script", "read_code", "methodology"])

                # Create and run Agent
                analyzer_agent = Agent(
                    system_prompt=system_prompt,
                    name=f"CodebaseAnalyzer",
                    description=f"分析代码库中的功能实现和定位",
                    summary_prompt=summary_prompt,
                    platform=PlatformRegistry().get_normal_platform(),
                    output_handler=[tool_registry],
                    execute_tool_confirm=False,
                    auto_complete=self.auto_complete
                )

                # Run agent and get result
                task_input = f"回答关于代码库的问题: {question}"
                result = analyzer_agent.run(task_input)

                return {
                    "success": True,
                    "stdout": result,
                    "stderr": ""
                }
            finally:
                # Always restore original directory
                os.chdir(original_dir)
        except Exception as e:
            error_msg = f"分析代码库失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.WARNING)
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg
            }

    def _create_system_prompt(self, question: str, git_root: str) -> str:
        """创建Agent的system prompt

        Args:
            question: 用户问题
            git_root: Git仓库根目录

        Returns:
            系统提示文本
        """
        return f"""# 代码库分析专家

## 任务描述
分析代码库，找出与用户问题最相关的信息，提供准确、具体的回答。

## 问题信息
- 问题: {question}
- 代码库根目录: {git_root}

## 工具使用优先级
1. **绝对优先使用 execute_script**:
   - 使用 fd 查找文件: `fd -t f -e py` 查找Python文件等
   - 使用 rg 搜索代码: `rg "pattern" --type py` 在Python文件中搜索等
   - 使用 loc 统计代码: `loc"` 统计代码量

2. **优先使用 read_code**:
   - 找到相关文件后优先使用read_code读取文件内容
   - 对大文件使用行范围参数读取指定区域

## 分析策略
1. 首先理解问题，确定需要查找的关键信息和代码组件
2. 使用fd命令查找可能相关的文件
3. 使用rg命令搜索关键词和代码模式
4. 使用read_code工具直接读取和分析相关文件内容
5. 只有在fd、rg和read_code都无法解决问题时才考虑使用RAG工具
6. 根据文件内容提供具体、准确的回答
7. 确保分析的完整性，收集充分的信息后再得出结论，不要在只掌握部分信息就得出结论
8. 优先查阅README文件、文档目录和项目文档

## 分析步骤
1. **确定项目的编程语言**:
   - 使用loc命令: `loc` 统计各类文件数量
   - 查看构建文件和配置文件
   - 了解项目使用的框架和主要依赖

2. **探索代码库结构**:
   - 使用 `fd -t d` 了解目录结构
   - 使用 `fd README.md` 查找README文件
   - 使用 `fd -e md -g "doc*"` 查找文档文件

3. **定位相关文件**:
   - 使用fd和rg命令查找关键词
   - 示例: `rg -w "登录|login" --type py` 查找登录相关代码
   - 示例: `fd -e py -g "*auth*"` 查找认证相关文件

4. **深入分析代码**:
   - 使用read_code工具直接读取文件内容
   - 分析关键文件的实现细节
   - 使用rg识别功能的实现方式和关键逻辑

5. **回答问题**:
   - 提供基于直接分析代码的具体回答
   - 引用具体文件和代码片段作为依据

## 关于RAG工具使用
- RAG工具应作为最后选择，仅在fd、rg和read_code都无法解决问题时使用
- 必须通过查看实际代码文件验证RAG返回的每条重要信息
- 对于关键发现，始终使用`read_code`工具查看原始文件内容进行求证
- 如发现RAG结果与实际代码不符，以实际代码为准

## 输出要求
- 提供准确、具体的回答，避免模糊不清的描述
- 引用具体文件路径和代码片段作为依据
- 如果无法找到答案，明确说明并提供原因
- 组织信息的逻辑清晰，便于理解
- 对复杂概念提供简明解释
- 确保全面收集相关信息后再形成结论
- 明确区分已验证的信息和待验证的信息"""

    def _create_summary_prompt(self, question: str) -> str:
        """创建Agent的summary prompt

        Args:
            question: 用户问题

        Returns:
            总结提示文本
        """
        return f"""# 代码库分析报告

## 报告要求
生成关于以下问题的清晰、准确的分析报告:

**问题**: {question}

报告应包含:

1. **项目基本信息**:
   - 项目的主要编程语言和技术栈
   - 项目的主要框架和依赖
   - 项目的基本结构

2. **问题回答**:
   - 直接、具体地回答问题
   - 基于代码库中的实际代码
   - 避免模糊或推测性的回答

3. **核心发现**:
   - 相关文件和代码位置
   - 关键实现细节
   - 功能运作机制

4. **证据引用**:
   - 引用具体文件路径
   - 包含关键代码片段
   - 解释代码如何支持你的回答

5. **局限性**(如有):
   - 指出分析的任何局限
   - 说明任何无法确定的信息

6. **分析完整性**:
   - 确保在得出结论前已全面收集和分析相关信息
   - 避免基于部分信息形成不完整或偏颇的判断
   - 明确标识哪些是已确认的结论，哪些可能需要进一步验证

使用清晰的Markdown格式，重点突出对问题的回答和支持证据。"""


def main():
    """
    命令行入口点，允许将ask_codebase作为独立脚本运行

    用法示例:
    ```
    python -m jarvis.jarvis_tools.ask_codebase "登录功能在哪个文件实现？" --root_dir /path/to/codebase
    ```
    """
    import argparse
    import sys

    init_env()

    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description="智能代码库查询工具")
    parser.add_argument("question", help="关于代码库的问题")
    parser.add_argument("--root_dir", "-d", default=".", help="代码库根目录路径")

    # 解析命令行参数
    args = parser.parse_args()

    # 创建并执行工具
    tool = AskCodebaseTool(auto_complete=False)
    result = tool.execute({
        "question": args.question,
        "root_dir": args.root_dir
    })

    # 输出结果
    if result["success"]:
        PrettyOutput.print(result["stdout"], OutputType.SUCCESS)
    else:
        PrettyOutput.print(result["stderr"], OutputType.WARNING)
        sys.exit(1)


if __name__ == "__main__":
    main()
