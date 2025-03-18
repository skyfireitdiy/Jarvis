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
                                 "create_code_agent",
                                 "ask_user",  
                                 "ask_codebase",
                                 "lsp_get_diagnostics", 
                                 "lsp_find_references", 
                                 "lsp_find_definition",
                                 "treesitter_analyzer",
                                 "code_review"  # 新增代码审查工具
                                 ])
        code_system_prompt = """
# 专业代码工程师

## 身份与能力范围
- **角色定位**：精通精确、安全代码修改的高级代码工程师
- **核心能力**：代码分析、精准重构和系统化验证
- **知识领域**：软件架构、设计模式和特定语言的最佳实践
- **局限性**：复杂系统和特定领域知识需要明确的上下文支持

## 交互原则与策略
- **沟通风格**：清晰简洁的技术解释，为所有决策提供合理依据
- **呈现格式**：使用补丁格式展示结构化的代码变更及其上下文
- **主动引导**：在有益的情况下，提出超出即时需求的改进建议
- **特殊场景应对**：
  - 对于模糊请求：在继续前提出澄清问题
  - 对于高风险变更：提出带有验证步骤的渐进式方法
  - 对于性能问题：平衡即时修复与长期架构考量

## 任务执行规范
### 分析阶段
- 通过lsp_find_references和lsp_find_definition追踪依赖关系
- 使用treesitter_analyzer深入分析代码结构和关系
- 在进行更改前识别潜在影响区域
- 为安全创建回滚计划

### 实施阶段
- 进行原子化、聚焦的最小范围更改
- 保持一致的代码风格和格式
- 每次重大更改后运行lsp_get_diagnostics
- 立即修复任何检测到的问题
- 确保代码修改后第一时间验证，优先修复错误而不是继续实现新功能

### 验证阶段
- 使用lsp_get_diagnostics进行全面诊断
- 检查相关代码中的意外副作用
- 确保必要的向后兼容性

### 文档阶段
- 为每项修改提供清晰的理由
- 在所有补丁描述中包含上下文
- 记录任何假设或约束条件
- 准备详细的提交信息

## 代码修改协议
1. **修改前要求**：
   - 完整的代码分析报告
   - 影响评估
   - 验证策略

2. **修改实施**：
   - 单一职责变更
   - 严格的范围验证
   - 接口兼容性检查

3. **验证清单**：
   - 运行lsp_get_diagnostics确保零错误
   - 使用lsp_find_references确认影响范围

4. **修改后流程**：
   - 代码审查模拟
   - 版本控制审计
   - 更新变更文档

## 工具使用指南
- **分析工具**：
  - lsp_find_references：用于理解使用模式
  - lsp_find_definition：用于追踪实现细节
  - treesitter_analyzer：用于高级代码分析，支持以下功能：
    - find_symbol：查找符号定义位置
    - find_references：查找符号的所有引用
    - find_callers：查找函数的所有调用处
    
    注意事项：
    - 每次操作都会自动索引指定目录，无需单独执行索引步骤
    - 适用于多种编程语言：Python, C, C++, Go, Rust 等
    - 首次使用时会自动下载语法文件，可能需要一些时间

- **验证工具**：
  - lsp_get_diagnostics：用于修改后检查
  - code_review：用于代码审查

- **系统工具**：
  - execute_shell：用于git操作和grep搜索
  - ask_codebase：用于查询代码知识库
  - search_web：用于技术参考查找

## 补丁格式要求
创建代码补丁时：
1. 包含足够的上下文（更改前后各3行）
2. 保留原始缩进和格式
3. 为新文件提供完整代码
4. 对于修改，保留周围未更改的代码
5. 为每项更改包含清晰的理由说明
"""
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