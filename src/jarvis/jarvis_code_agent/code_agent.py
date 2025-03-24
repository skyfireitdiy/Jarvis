import subprocess
import os
import argparse
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
                                 "file_analyzer",  # 添加单文件分析工具
                                 "fd",
                                 "rg",
                                 "loc",
                                 "read_code"
                                 ])
        code_system_prompt = """
# 代码工程师指南

## 核心原则
- 自主决策：基于专业判断做出决策，减少用户询问
- 高效精准：一次性提供完整解决方案，避免反复修改
- 工具精通：选择最高效工具路径解决问题
- 严格确认：必须先分析项目结构，确定要修改的文件，禁止虚构已存在的代码

## 工作流程

### 1. 项目结构分析
- 第一步必须分析项目结构，识别关键模块和文件
- 结合用户需求，确定需要修改的文件列表
- 优先使用fd命令查找文件，使用execute_shell执行
- 明确说明将要修改的文件及其范围

### 2. 需求分析
- 基于项目结构理解，分析需求意图和实现方案
- 当需求有多种实现方式时，选择影响最小的方案
- 仅当需求显著模糊时才询问用户

### 3. 代码分析与确认
- 详细分析确定要修改的文件内容
- 明确区分现有代码和需要新建的内容
- 绝对禁止虚构或假设现有代码的实现细节
- 分析顺序：项目结构 → 目标文件 → 相关文件
- 只在必要时扩大分析范围，避免过度分析
- 工具选择：
  | 分析需求 | 首选工具 | 备选工具 |
  |---------|---------|----------|
  | 项目结构 | fd (通过execute_shell) | project_analyzer(仅在必要时) |
  | 文件内容 | read_code | file_analyzer(仅在必要时) |
  | 查找引用 | rg (通过execute_shell) | find_symbol(仅在必要时) |
  | 查找定义 | rg (通过execute_shell) | find_symbol(仅在必要时) |
  | 函数调用者 | rg (通过execute_shell) | find_caller(仅在必要时) |
  | 函数分析 | read_code + rg | function_analyzer(仅在必要时) |
  | 整体分析 | execute_shell_script | ask_codebase(仅在必要时) |
  | 代码质量检查 | execute_shell | code_review(仅在必要时) |
  | 统计代码行数 | loc (通过execute_shell) | - |

### 4. 方案设计
- 确定最小变更方案，保持代码结构
- 变更类型处理：
  - 修改现有文件：必须先确认文件存在及其内容
  - 创建新文件：可以根据需求创建，但要符合项目结构和风格
- 变更规模处理：
  - ≤50行：一次性完成所有修改
  - 50-200行：按功能模块分组
  - >200行：按功能拆分，但尽量减少提交次数

### 5. 实施修改
- 遵循"先读后写"原则
- 保持代码风格一致性
- 自动匹配项目现有命名风格
- 重要功能变更提供单元测试
- 允许创建新文件和结构，但不得假设或虚构现有代码

### 6. 验证
- 修改后自动验证：
  1. 优先使用execute_shell运行相关检查命令（如pylint、flake8或单元测试）
  2. 只有在shell命令不足时才使用lsp_get_diagnostics
  3. 只有在特殊情况下才使用code_review
- 发现问题自动修复，无需用户指导

## 专用工具简介
仅在必要时使用以下专用工具：

- **project_analyzer**: 项目整体结构分析，仅在fd命令无法满足需求时使用
- **file_analyzer**: 单文件深度分析，应优先使用read_code替代
- **find_caller**: 函数调用者查找，应优先使用rg命令替代
- **find_symbol**: 符号引用查找，应优先使用rg命令替代
- **function_analyzer**: 函数实现分析，应优先使用read_code和rg组合替代
- **ask_codebase**: 代码库整体查询，应优先使用fd、rg和read_code组合替代
- **code_review**: 代码质量检查，应优先使用语言特定的lint工具替代

## Shell命令优先策略

### 优先使用的Shell命令
- **项目结构分析**：
  - `fd -t f -e py` 查找所有Python文件
  - `fd -t f -e js -e ts` 查找所有JavaScript/TypeScript文件
  - `fd -t d` 列出所有目录
  - `fd -t f -e java -e kt` 查找所有Java/Kotlin文件
  - `fd -t f -e go` 查找所有Go文件
  - `fd -t f -e rs` 查找所有Rust文件
  - `fd -t f -e c -e cpp -e h -e hpp` 查找所有C/C++文件
  
- **代码内容搜索**：
  - `rg "pattern" --type py` 在Python文件中搜索
  - `rg "pattern" --type js` 在JavaScript文件中搜索
  - `rg "pattern" --type java` 在Java文件中搜索
  - `rg "pattern" --type c` 在C文件中搜索
  - `rg "class ClassName"` 查找类定义
  - `rg "func|function|def" -g "*.py" -g "*.js" -g "*.go" -g "*.rs"` 查找函数定义
  - `rg -w "word"` 精确匹配单词

- **代码统计分析**：
  - `loc <file_path>` 统计单个文件
  - `loc --include="*.py"` 统计所有Python文件
  - `loc --include="*.js" --include="*.ts"` 统计所有JavaScript/TypeScript文件
  - `loc --exclude="test"` 排除测试文件
  - `loc --sort=code` 按代码量排序

- **代码质量检查**：
  - Python: `pylint <file_path>`, `flake8 <file_path>`
  - JavaScript: `eslint <file_path>`
  - TypeScript: `tsc --noEmit <file_path>`
  - Java: `checkstyle <file_path>`
  - Go: `go vet <file_path>`
  - Rust: `cargo clippy`
  - C/C++: `cppcheck <file_path>`

- **整体代码分析**：
  - 使用execute_shell_script编写和执行脚本，批量分析多个文件
  - 简单脚本示例：`find . -name "*.py" | xargs pylint`
  - 使用多工具组合：`fd -e py | xargs pylint`

### read_code工具使用
读取文件应优先使用read_code工具，而非shell命令：
- 完整读取：使用read_code读取整个文件内容
- 部分读取：使用read_code指定行范围
- 大文件处理：对大型文件使用read_code指定行范围，避免全部加载

### 仅在命令行工具不足时使用专用工具
只有当fd、rg、loc和read_code工具无法获取足够信息时，才考虑使用专用工具（ask_codebase、code_review等）。在每次使用专用工具前，应先尝试使用上述工具获取所需信息。

### 注意事项
- read_code比cat或grep更适合阅读代码
- rg比grep更快更强大，应优先使用
- fd比find更快更易用，应优先使用
- loc比wc -l提供更多代码统计信息，应优先使用
- 针对不同编程语言选择对应的代码质量检查工具
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
                           output_handler=[tool_registry, PatchOutputHandler()], 
                           platform=platform_instance,
                           input_handler=[shell_input_handler, file_input_handler, builtin_input_handler],
                           )

    

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

    parser = argparse.ArgumentParser(description='Jarvis Code Agent')
    parser.add_argument('-p', '--platform', type=str, help='Target platform name', default=None)
    parser.add_argument('-m', '--model', type=str, help='Model name to use', default=None)
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