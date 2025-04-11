"""代码修改规划工具模块

该模块提供CodePlanTool类，用于分析代码修改需求并制定详细的修改计划。
包含以下主要功能：
1. 需求理解与分析
2. 代码修改计划制定
3. 用户确认流程
4. 修改计划输出
"""

from typing import Dict, Any
import os
from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_agent import Agent
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.git_utils import find_git_root

class CodePlanTool:
    """用于代码修改规划和需求分析的工具

    适用场景：
    - 理解复杂代码修改需求
    - 制定详细的代码修改步骤
    - 协调多文件修改计划
    - 在修改前获取用户确认

    工作流程：
    1. 理解需求：通过多种方式(代码查询、用户交互、网络搜索)完全理解需求
    2. 制定计划：分析代码后制定详细的修改步骤
    3. 用户确认：将修改计划呈现给用户确认
    4. 输出计划：按照标准格式输出最终修改计划
    """

    name = "code_plan"
    description = "理解需求并制定详细的代码修改计划，在修改前获取用户确认"
    parameters = {
        "type": "object",
        "properties": {
            "requirement": {
                "type": "string",
                "description": "代码修改需求描述"
            },
            "root_dir": {
                "type": "string",
                "description": "代码库根目录路径（可选）",
                "default": "."
            }
        },
        "required": ["requirement"]
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行代码规划流程

        Args:
            args: 包含:
                - requirement: 代码修改需求描述
                - root_dir: 代码库根目录路径(可选)

        Returns:
            包含执行结果的字典:
                - success: 是否成功
                - stdout: 执行结果
                - stderr: 错误信息
        """
        try:
            requirement = args["requirement"]
            root_dir = args.get("root_dir", ".")

            # 存储当前目录
            original_dir = os.getcwd()

            try:
                # 切换到root_dir
                os.chdir(root_dir)

                # 获取git根目录
                git_root: str = find_git_root() or os.getcwd()

                # 创建系统提示
                system_prompt = self._create_system_prompt(requirement, git_root)

                # 创建总结提示
                summary_prompt = self._create_summary_prompt(requirement)

                # 创建工具注册表
                tool_registry: ToolRegistry = ToolRegistry()
                tool_registry.use_tools([
                    "execute_script", 
                    "read_code", 
                    "ask_codebase", 
                    "search_web", 
                    "ask_user"
                ])

                # 创建并运行Agent
                platform_registry: PlatformRegistry = PlatformRegistry()
                planner_agent = Agent(
                    system_prompt=system_prompt,
                    name="CodePlanner",
                    description="分析代码修改需求并制定详细计划",
                    summary_prompt=summary_prompt,
                    platform=platform_registry.get_normal_platform(),
                    output_handler=[tool_registry],
                    execute_tool_confirm=False,
                    auto_complete=False,
                )

                # 运行agent并获取结果
                task_input = f"分析并规划代码修改: {requirement}"
                result = planner_agent.run(task_input)

                return {
                    "success": True,
                    "stdout": result,
                    "stderr": ""
                }
            except (OSError, RuntimeError) as e:
                error_msg = f"代码规划失败: {str(e)}"
                PrettyOutput.print(error_msg, OutputType.WARNING)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": error_msg
                }
            finally:
                # 恢复原始目录
                os.chdir(original_dir)
        except (KeyError, ValueError) as e:
            error_msg = f"代码规划失败: {str(e)}"
            PrettyOutput.print(error_msg, OutputType.WARNING)
            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg
            }

    def _create_system_prompt(self, requirement: str, git_root: str) -> str:
        """创建Agent的system prompt"""
        return f"""# 代码修改规划专家

## 任务描述
分析代码修改需求，理解需求后制定详细的代码修改计划，并在执行前获取用户确认。

## 重要原则
- **禁止直接修改代码**：仅提供修改计划，不执行实际代码修改
- **只读分析**：所有代码分析必须基于现有代码，不得假设或虚构代码
- **配置变更优先**：优先考虑通过配置而非代码修改实现需求

## 需求信息
- 需求: {requirement}
- 代码库根目录: {git_root}

## 工作流程
1. **需求理解阶段**:
   - 使用ask_codebase工具查询相关代码
   - 必要时使用search_web搜索补充信息
   - 使用ask_user工具向用户确认模糊点

2. **代码分析阶段**:
   - 使用fd/rg查找相关文件
   - 使用read_code分析关键文件
   - 确定需要修改的文件和范围
   - **严格禁止修改代码**：仅分析不修改

3. **计划制定阶段**:
   - 制定最小变更方案
   - 按功能模块分组修改
   - 预估修改范围和影响
   - **仅输出计划**：不执行实际修改

4. **用户确认阶段**:
   - 将完整修改计划呈现给用户
   - 获取用户明确确认
   - 根据反馈调整计划

5. **计划输出阶段**:
   - 按照summary_prompt格式输出最终计划
   - 确保计划清晰、可执行
   - **明确标注**：所有修改需用户手动执行

## 工具使用优先级
1. **代码查询工具**:
   - ask_codebase: 查询功能位置和实现
   - fd/rg: 查找文件和代码模式
   - read_code: 读取文件内容

2. **信息补充工具**:
   - search_web: 搜索技术实现方案
   - ask_user: 确认需求细节

## 计划制定原则
- **只读原则**：所有分析必须基于现有代码，不得修改
- 最小变更原则: 保持现有代码结构
- 模块化修改: 按功能分组修改
- 影响分析: 评估修改的影响范围
- 风格一致: 保持代码风格统一"""

    def _create_summary_prompt(self, requirement: str) -> str:
        """创建Agent的summary prompt"""
        return f"""# 代码修改计划报告

## 报告要求
生成关于以下需求的清晰、可执行的代码修改计划:

**需求**: {requirement}

报告应包含:

1. **需求分析**:
   - 需求的完整理解
   - 关键功能点和边界条件
   - 任何假设和前提条件

2. **代码现状**:
   - 相关文件和模块
   - 现有实现分析
   - 需要修改的部分

3. **修改计划**:
   - 需要修改的文件列表
   - 每个文件的修改内容概述
   - 修改步骤和顺序
   - 预估影响范围

4. **验证方案**:
   - 如何验证修改的正确性
   - 需要添加的测试用例

5. **用户确认**:
   - 明确标记已获得用户确认
   - 记录用户的任何特殊要求

使用清晰的Markdown格式，重点突出修改计划和验证方案。"""



