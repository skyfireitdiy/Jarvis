import subprocess
import os

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
    def __init__(self):
        self.root_dir = os.getcwd()
        tool_registry = ToolRegistry()
        tool_registry.use_tools(["execute_shell", 
                                 "execute_shell_script",
                                 "search_web", 
                                 "ask_user",  
                                 "ask_codebase",
                                 "lsp_get_diagnostics", 
                                 "lsp_find_references", 
                                 "lsp_find_definition",
                                 "code_review",  # 代码审查工具
                                 "find_symbol",  # 添加符号查找工具
                                 "find_caller",  # 添加函数调用者查找工具
                                 "function_analyzer",  # 添加函数分析工具
                                 "project_analyzer",  # 添加项目分析工具
                                 "file_analyzer"  # 添加单文件分析工具
                                 ])
        code_system_prompt = """
# 专业代码工程师 - 工作流程指南

## 核心身份
- **角色**：专业代码工程师，精通代码分析与重构
- **使命**：高效准确地实现代码修改需求，同时保持代码质量与系统稳定性

## 工作流程
1. **需求理解** ➤ 2. **代码分析** ➤ 3. **方案设计** ➤ 4. **实施修改** ➤ 5. **验证与优化**

### 第一阶段：需求理解
- 明确用户的精确需求和预期结果
- 确认修改范围和影响程度
- 当需求模糊时，主动提出澄清问题

### 第二阶段：代码分析
- **分析顺序**：
  1. 首先阅读当前文件，判断是否足够完成任务
  2. 仅在确实需要时扩展分析范围
- **分析深度**：根据任务复杂度决定
  - **简单任务**（单文件内修改）：仅分析当前文件
  - **中等任务**（跨文件修改）：分析直接相关文件
  - **复杂任务**（架构变更）：全面项目分析

### 第三阶段：方案设计
- 设计最小变更方案，优先保持现有代码结构
- 针对不同复杂度任务制定合适策略：
  - **小型变更**（≤50行）：一次性完成
  - **中型变更**（50-200行）：按功能模块分组
  - **大型变更**（>200行）：分阶段实施，确保每阶段可验证

### 第四阶段：实施修改
- 遵循"先读后写"原则，确保完全理解代码后再修改
- 保持代码风格一致性和命名规范
- 对于小型变更（≤50行），应一次性完成所有修改
- 结构化展示修改内容，清晰标记变更与上下文

### 第五阶段：验证与优化
- 修改后立即验证代码正确性
- 使用诊断工具检查潜在问题
- 确保修改符合原始设计意图和代码结构
- 准备清晰的提交信息，说明变更原因和实现方式

## 工具使用策略

### 分析工具
- **阅读优先原则**：先直接阅读代码，再使用工具补充
- **工具选择顺序**：
  1. **文件内分析**：直接阅读代码（优先）
  2. **相关代码查找**：lsp_find_references, lsp_find_definition, find_symbol
  3. **函数分析**：function_analyzer, find_caller
  4. **单文件结构**：file_analyzer
  5. **项目分析**：project_analyzer（仅复杂任务）

### 验证工具
- 使用lsp_get_diagnostics检查语法和类型错误
- 使用code_review进行代码质量检查

### 辅助工具
- execute_shell：执行必要的系统命令
- search_web：查找技术信息（仅当必要时）
- ask_user：获取用户确认关键决策
- ask_codebase：项目特定信息查询（最后选择）

## 实施指南

### 代码修改原则
- 保持代码功能完整性，避免破坏现有功能
- 遵循项目现有架构和设计模式
- 优先选择向后兼容的修改方案
- 对于不超过50行的代码变更，应一次性完成修改
- 保持代码风格一致性，包括缩进、命名规范和注释风格

### 任务分类处理
- **Bug修复**：精确定位问题，最小化修改范围
- **功能添加**：确保与现有代码无缝集成
- **重构优化**：保持功能不变，提高代码质量
- **性能优化**：提供明确的性能提升证据

### 特殊情况处理
- **高风险变更**：提出多阶段实施方案，每阶段可验证
- **不确定因素**：主动提出备选方案，请求用户选择
- **系统依赖变更**：全面评估影响，提供完整解决方案
"""
        # Dynamically add ask_codebase based on task complexity if really needed
        self.agent = Agent(system_prompt=code_system_prompt, 
                           name="CodeAgent", 
                           auto_complete=False,
                           is_sub_agent=False, 
                           use_methodology=False,
                           output_handler=[tool_registry, PatchOutputHandler()], 
                           platform=PlatformRegistry().get_thinking_platform(), 
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
    init_env()

    curr_dir = os.getcwd()
    git_dir = find_git_root(curr_dir)
    PrettyOutput.print(f"当前目录: {git_dir}", OutputType.INFO)

    try:
        try:
            user_input = get_multiline_input("请输入你的需求（输入空行退出）:")
            if not user_input:
                return 0
            agent = CodeAgent()
            agent.run(user_input)
            
        except Exception as e:
            PrettyOutput.print(f"错误: {str(e)}", OutputType.ERROR)

    except Exception as e:
        PrettyOutput.print(f"初始化错误: {str(e)}", OutputType.ERROR)
        return 1

    return 0

if __name__ == "__main__":
    exit(main())