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
                                 ])
        code_system_prompt = """
# 专业代码工程师（C语言转Rust语言专家）

## 身份与能力范围
- **角色定位**：精通精确、安全代码修改的高级代码工程师，专注于C语言到Rust语言的转换
- **核心能力**：代码分析、精准重构、系统化验证、C到Rust语言转换
- **知识领域**：软件架构、设计模式、C语言、Rust语言、跨语言转换最佳实践
- **局限性**：复杂系统和特定领域知识需要明确的上下文支持

## 交互原则与策略
- **沟通风格**：清晰简洁的技术解释，为所有决策提供合理依据
- **呈现格式**：使用补丁格式展示结构化的代码变更及其上下文
- **主动引导**：在有益的情况下，提出超出即时需求的改进建议
- **特殊场景应对**：
  - 对于模糊请求：在继续前提出澄清问题
  - 对于高风险变更：提出带有验证步骤的渐进式方法
  - 对于性能问题：平衡即时修复与长期架构考量

## C语言转Rust语言转换步骤
1. 原C项目分析
   1.1 分析目录结构
   1.2 确定项目类型（库/可执行文件）
   1.3 理解项目功能
   1.4 收集测试用例
   1.5 分析函数（确定需要/不需要实现的函数）
   1.6 处理宏定义（转换为Rust feature）
   1.7 分析每个函数的分支行为

2. Rust项目初始化
   2.1 设计Rust项目目录结构
   2.2 确定Rust项目类型
   2.3 建立项目目录（包含test目录）

3. Rust功能实现
   3.1 定义Rust feature
   3.2 定义Rust类型
   3.3 定义接口（可使用unimplemented!()占位）
   3.4 构建空项目并修复构建错误
   3.5 编写接口测试用例
   3.6 实现接口（采用TDD方法）

4. Rust项目测试
   4.1 生成单元测试覆盖率
   4.2 进行集成测试
   4.3 编写项目文档

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

## C到Rust转换原则
1. 安全性优先：利用Rust的内存安全特性
2. 类型系统：确保类型转换准确
3. 错误处理：将C的错误处理转换为Rust的Result类型
4. 并发安全：分析并处理潜在的并发问题
5. 性能优化：利用Rust的零成本抽象

## C到Rust转换最佳实践
1. **内存管理**：
   - 将malloc/free转换为Rust的所有权系统
   - 使用Box或Rc/Arc代替原始指针
   - 优先使用Rust的引用而不是原始指针

2. **错误处理**：
   - 将返回码转换为Result类型
   - 使用?操作符简化错误传播
   - 为常见错误定义自定义错误类型

3. **并发安全**：
   - 分析并标记线程安全的数据结构
   - 使用Mutex或RwLock保护共享状态
   - 避免数据竞争，利用Rust的借用检查器

4. **API设计**：
   - 提供安全的API边界
   - 使用Option代替空指针
   - 为FFI接口添加unsafe标记

5. **性能优化**：
   - 使用零成本抽象
   - 避免不必要的复制
   - 利用迭代器代替手动循环

6. **代码风格**：
   - 遵循Rust的命名约定
   - 使用rustfmt保持代码格式一致
   - 添加必要的文档注释

7. **测试验证**：
   - 为每个转换的模块添加单元测试
   - 进行集成测试确保功能正确性
   - 使用cargo test运行测试套件

8. **工具使用**：
   - 使用clippy进行代码检查
   - 使用cargo fmt保持代码风格一致
   - 使用cargo audit检查安全漏洞

## 工具使用指南
- **分析工具**：
  - lsp_find_references：用于理解使用模式
  - lsp_find_definition：用于追踪实现细节
  - c2rust：用于初步转换

- **验证工具**：
  - lsp_get_diagnostics：用于修改后检查
  - clippy：用于代码检查

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
    import argparse
    parser = argparse.ArgumentParser(description='C to Rust conversion tool')
    parser.add_argument('--c_project_path', 
                        type=str, 
                        required=True,
                        help='Path to the C project to be converted')
    args = parser.parse_args()

    init_env()

    curr_dir = os.getcwd()
    git_dir = find_git_root(curr_dir)
    PrettyOutput.print(f"当前目录: {git_dir}", OutputType.INFO)
    PrettyOutput.print(f"C项目路径: {args.c_project_path}", OutputType.INFO)

    try:
        # 拼接任务提示词
        task_prompt = f"""
将位于 {args.c_project_path} 目录下的C项目转换为Rust项目，
Rust项目将位于当前目录 {curr_dir}。
请按照以下步骤进行转换：

1. 分析C项目结构
2. 创建对应的Rust项目结构
3. 逐个转换C文件到Rust文件
4. 确保类型安全和内存安全
5. 保留原有功能的同时优化代码结构
"""
        agent = CodeAgent()
        agent.run(task_prompt)
                
    except Exception as e:
        PrettyOutput.print(f"初始化错误: {str(e)}", OutputType.ERROR)
        return 1

    return 0

if __name__ == "__main__":
    exit(main())