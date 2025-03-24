import subprocess
import os
from token import OP
from typing import Optional

from yaspin import yaspin

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_agent.builtin_input_handler import builtin_input_handler
from jarvis.jarvis_agent.file_input_handler import file_input_handler
from jarvis.jarvis_agent.shell_input_handler import shell_input_handler
from jarvis.jarvis_agent.patch import PatchOutputHandler
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.git_commiter import GitCommitTool

from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.git_utils import find_git_root, get_commits_between, get_latest_commit_hash, has_uncommitted_changes
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env, user_confirm





class CodeAgent:
    def __init__(self, platform : Optional[str] = None, model: Optional[str] = None):
        self.root_dir = os.getcwd()
        tool_registry = ToolRegistry()
        tool_registry.use_tools(["execute_shell", 
                                 "execute_shell_script",
                                 "search_web", 
                                 "ask_user",  
                                 "ask_codebase",
                                 "lsp_get_diagnostics", 
                                 "code_review",  # 代码审查工具
                                 "find_symbol",  # 添加符号查找工具
                                 "find_caller",  # 添加函数调用者查找工具
                                 "function_analyzer",  # 添加函数分析工具
                                 "project_analyzer",  # 添加项目分析工具
                                 "file_analyzer"  # 添加单文件分析工具
                                 ])
        code_system_prompt = """
# 代码工程师指南

## 核心原则
- 自主决策：基于专业判断做出决策，减少用户询问
- 高效精准：一次性提供完整解决方案，避免反复修改
- 工具精通：选择最高效工具路径解决问题

## 工作流程

### 1. 需求分析
- 直接分析需求意图和范围，无需用户确认
- 当需求有多种实现方式时，选择影响最小的方案
- 仅当需求显著模糊时才询问用户

### 2. 代码分析
- 分析顺序：当前文件 → 相关文件 → 项目范围
- 只在必要时扩大分析范围，避免过度分析
- 工具选择：
  | 分析需求 | 首选工具 | 备选工具 |
  |---------|---------|----------|
  | 查找引用 | lsp_find_references | find_symbol |
  | 查找定义 | lsp_find_definition | find_symbol |
  | 函数调用者 | find_caller | lsp_find_references |
  | 函数分析 | function_analyzer | file_analyzer |
  | 文件结构 | file_analyzer | - |
  | 项目架构 | project_analyzer | - |

### 3. 方案设计
- 确定最小变更方案，保持代码结构
- 变更规模处理：
  - ≤50行：一次性完成所有修改
  - 50-200行：按功能模块分组
  - >200行：按功能拆分，但尽量减少提交次数

### 4. 实施修改
- 遵循"先读后写"原则
- 保持代码风格一致性
- 自动匹配项目现有命名风格
- 重要功能变更提供单元测试

### 5. 验证
- 修改后自动验证：
  1. lsp_get_diagnostics：检查语法错误
  2. code_review：评估代码质量
  3. execute_shell：运行测试（必要时）
- 发现问题自动修复，无需用户指导

## 专用工具详解

### 1. project_analyzer
**功能**：分析整体项目结构、入口点和模块划分
**适用场景**：
- 初次接触项目需要快速理解整体架构
- 需要进行跨模块的重大变更
- 评估重构或架构变更的影响范围
- 需要理解组件间的交互方式

**使用建议**：
- 指定root_dir参数作为项目根目录（默认为"."）
- 使用focus_dirs参数限定重点分析的目录
- 使用exclude_dirs参数排除不需要分析的目录
- 提供明确的objective参数说明分析目的
- 仅在必要时使用，因其分析范围广泛

### 2. file_analyzer
**功能**：深入分析单个文件的结构、实现细节和代码质量
**适用场景**：
- 需要全面理解文件整体结构和功能
- 准备重构或修改大型文件
- 需要理解文件内所有组件间的关系
- 评估文件的代码质量和可维护性

**使用建议**：
- 必须提供file_path参数指定要分析的文件
- 可选提供root_dir参数（默认为"."）
- 提供objective参数明确分析目标（如"准备重构该文件"）
- 结合function_analyzer分析文件中的关键函数

### 3. find_caller
**功能**：查找代码库中所有调用指定函数的位置
**适用场景**：
- 需要评估修改函数的影响范围
- 理解函数在项目中的使用模式
- 确定可以安全修改或移除的函数
- 寻找调用特定API的所有位置

**使用建议**：
- 必须提供function_name参数指定要查找调用者的函数名称
- 可选提供file_extensions参数限定搜索范围（如['.py', '.js']）
- 可选提供exclude_dirs参数排除目录
- 提供objective参数说明查找目的（如"评估修改影响范围"）

### 4. find_symbol
**功能**：查找代码库中的符号引用、定义和声明位置
**适用场景**：
- 需要找到变量、类或常量的所有使用位置
- 理解特定符号在项目中的作用范围
- 评估重命名或移动符号的影响
- 查找特定配置项或标识符的使用情况

**使用建议**：
- 必须提供symbol参数指定要查找的符号名称
- 可选提供file_extensions参数限定搜索范围
- 可选提供exclude_dirs参数排除目录
- 提供objective参数说明查找目的（如"准备重命名该符号"）

### 5. function_analyzer
**功能**：深入分析函数内部实现，包括子函数调用、全局变量使用等
**适用场景**：
- 需要理解复杂函数的内部实现
- 准备重构或修改函数逻辑
- 评估函数的性能瓶颈
- 分析函数的依赖关系

**使用建议**：
- 必须提供function_name参数指定要分析的函数名称
- 可选提供file_path参数如果已知函数位置
- 可选通过analysis_depth参数控制子函数分析深度（0-不分析子函数，1-仅直接子函数等）
- 提供objective参数说明分析目的（如"理解实现以便重构"）
- 与find_caller结合使用评估修改影响

## 工具选择策略

### 分析深度递进
1. **浅层分析**：直接阅读当前文件 → 使用lsp工具查找定义和引用
2. **中层分析**：file_analyzer了解文件结构 → function_analyzer分析核心函数
3. **深层分析**：find_caller确定影响范围 → project_analyzer了解项目架构

### 精确查找优于大范围搜索
- 已知文件位置时，优先使用file_analyzer而非project_analyzer
- 已知函数名时，优先使用function_analyzer而非file_analyzer
- 需要查找调用关系时，优先使用find_caller而非手动搜索

### 复杂任务工具组合
- **重构函数**：function_analyzer + find_caller
- **修改API**：function_analyzer + find_caller + file_analyzer
- **架构变更**：project_analyzer + find_symbol + find_caller
- **性能优化**：function_analyzer（带objective="评估性能瓶颈"）

### 避免工具滥用
- 简单任务勿用复杂工具（文件内小修改不需project_analyzer）
- 分析粒度由粗到细（先project_analyzer后function_analyzer）
- 减少分析重叠（已用file_analyzer后，不需对同一文件再用多个function_analyzer）
"""
        # Dynamically add ask_codebase based on task complexity if really needed
        # 处理platform参数
        platform_instance = (PlatformRegistry().create_platform(platform) 
                            if platform 
                            else PlatformRegistry().get_thinking_platform())
        if model:
            platform_instance.set_model_name(model) # type: ignore
        
        self.agent = Agent(system_prompt=code_system_prompt,
                           name="CodeAgent",
                           auto_complete=False,
                           is_sub_agent=False, 
                           use_methodology=False,
                           output_handler=[tool_registry, PatchOutputHandler()], 
                           platform=platform_instance,
                           record_methodology=False,
                           input_handler=[shell_input_handler, file_input_handler, builtin_input_handler],
                           need_summary=False)

    

    def _init_env(self):
        with yaspin(text="正在初始化环境...", color="cyan") as spinner: 
            curr_dir = os.getcwd()
            git_dir = find_git_root(curr_dir)
            self.root_dir = git_dir
            if has_uncommitted_changes():
                with spinner.hidden():
                    git_commiter = GitCommitTool()
                    git_commiter.execute({})
            spinner.text = "环境初始化完成"
            spinner.ok("✅")

    

    def run(self, user_input: str) :
        """Run the code agent with the given user input.
        
        Args:
            user_input: The user's requirement/request
            
        Returns:
            str: Output describing the execution result
        """
        try:
            self._init_env()
            
            start_commit = get_latest_commit_hash()
            
            try:
                self.agent.run(user_input)
            except Exception as e:
                PrettyOutput.print(f"执行失败: {str(e)}", OutputType.WARNING)
            
            end_commit = get_latest_commit_hash()
            # Print commit history between start and end commits
            if start_commit and end_commit:
                commits = get_commits_between(start_commit, end_commit)
            else:
                commits = []
            
            if commits:
                commit_messages = "检测到以下提交记录:\n" + "\n".join([f"- {commit_hash[:7]}: {message}" for commit_hash, message in commits])
                PrettyOutput.print(commit_messages, OutputType.INFO)

            if commits and user_confirm("是否接受以上提交记录？", True):
                if len(commits) > 1 and user_confirm("是否要合并为一个更清晰的提交记录？", True):
                    # Reset to start commit
                    subprocess.run(["git", "reset", "--mixed", start_commit], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    # Create new commit
                    git_commiter = GitCommitTool()
                    git_commiter.execute({})
            elif start_commit:
                os.system(f"git reset --hard {start_commit}")
                PrettyOutput.print("已重置到初始提交", OutputType.INFO)
                
        except Exception as e:
            return f"Error during execution: {str(e)}"
        


def main():
    """Jarvis main entry point"""
    # Add argument parser
    import argparse
    init_env()

    parser = argparse.ArgumentParser(description='Jarvis Code Agent')
    parser.add_argument('--platform', type=str, help='Target platform name', default=None)
    parser.add_argument('--model', type=str, help='Model name to use', default=None)
    args = parser.parse_args()

    curr_dir = os.getcwd()
    git_dir = find_git_root(curr_dir)
    PrettyOutput.print(f"当前目录: {git_dir}", OutputType.INFO)

    try:
        try:
            user_input = get_multiline_input("请输入你的需求（输入空行退出）:")
            if not user_input:
                return 0
            agent = CodeAgent(platform=args.platform, model=args.model)
            agent.run(user_input)
            
        except Exception as e:
            PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)

    except Exception as e:
        PrettyOutput.print(f"初始化错误: {str(e)}", OutputType.ERROR)
        return 1

    return 0

if __name__ == "__main__":
    exit(main())