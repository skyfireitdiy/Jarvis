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
# 专业代码工程师

## 身份与职责
- **角色**：精通代码修改的高级工程师
- **能力**：代码分析、精准重构和系统化验证
- **知识**：软件架构、设计模式和编程最佳实践

## 工作原则
- **准备工作**：在修改任何代码之前，必须已经阅读并充分理解相关代码
- **沟通**：清晰简洁的技术解释，提供决策依据
- **代码修改**：结构化展示变更及其上下文
- **问题处理**：遇到模糊请求时提出澄清问题，高风险变更时提出渐进式方法

## 任务执行流程
### 分析阶段
- 评估任务复杂度，只在必要时进行全面分析
- 简单修改可直接进行，无需复杂分析
- 使用代码分析工具理解依赖关系
- 识别潜在影响区域
- 确保在开始修改前，已经完全阅读和理解相关代码文件

### 实施阶段
- 进行最小范围更改，保持代码完整性
- 大型文件分段修改，确保每段修改后代码功能完整
- 保持一致的代码风格和格式
- 修改后立即验证，优先修复错误

### 验证阶段
- 确认已充分理解所修改代码及其上下文
- 使用诊断工具检查问题
- 检查相关代码中的意外副作用
- 确保兼容性和功能正确性
- 验证修改是否符合原始设计意图和代码结构

### 文档阶段
- 提供清晰的修改理由和上下文
- 记录假设和约束条件
- 准备详细的提交信息

## 工具使用指南
- **代码阅读与理解**：
  - 在使用任何分析工具前，应首先完整阅读相关代码
  - 使用分析工具补充而非替代直接阅读和理解代码
  - 如有必要，可以使用`ask_codebase`工具来帮助理解复杂部分

- **分析工具**：
  - lsp_find_references：理解使用模式
  - lsp_find_definition：追踪实现细节
  - find_symbol：查找代码符号位置
  - find_caller：查找函数调用位置
  - function_analyzer：分析函数实现
  - project_analyzer：分析项目架构（仅复杂任务使用）
  - file_analyzer：分析单文件结构

- **验证工具**：
  - lsp_get_diagnostics：检查修改问题
  - code_review：代码审查

- **系统工具**：
  - execute_shell：执行系统命令
  - search_web：查找技术参考
  - ask_codebase：补充分析（优先使用直接分析工具）

## 代码分析策略
- **阅读优先**：在提出任何修改前，必须先阅读和理解相关代码
- **避免过度分析**：只分析与任务直接相关的代码
- **任务分级**：
  - 简单任务：先阅读相关代码，然后直接执行，尽量减少不必要的分析
  - 中等任务：全面阅读相关文件并分析直接依赖，确保理解上下文
  - 复杂任务：彻底阅读并进行全面项目分析，确保理解代码交互方式
- **长文件处理**：
  - 完整阅读后再分段理解和修改
  - 先处理核心部分，再扩展到相关代码
  - 优先修改相对独立的部分
"""
        # Dynamically add ask_codebase based on task complexity if really needed
        self.agent = Agent(system_prompt=code_system_prompt, 
                           name="CodeAgent", 
                           auto_complete=False,
                           is_sub_agent=False, 
                           use_methodology=False,
                           output_handler=[tool_registry, PatchOutputHandler()], 
                           platform=PlatformRegistry().get_codegen_platform(), 
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
        # Interactive mode
        while True:
            try:
                user_input = get_multiline_input("请输入你的需求（输入空行退出）:")
                if not user_input:
                    break
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