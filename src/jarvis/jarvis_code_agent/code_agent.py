import re
import subprocess
import os
from typing import Any, Tuple

from jarvis.jarvis_agent import Agent
from jarvis.jarvis_code_agent.shell_input_handler import shell_input_handler
from jarvis.jarvis_code_agent.patch import PatchOutputHandler
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.file_operation import FileOperationTool
from jarvis.jarvis_tools.git_commiter import GitCommitTool

from jarvis.jarvis_tools.registry import ToolRegistry
from jarvis.jarvis_utils.git_utils import find_git_root, get_commits_between, get_latest_commit_hash, has_uncommitted_changes
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env, user_confirm




def file_input_handler(user_input: str, agent: Any) -> Tuple[str, bool]:
    prompt = user_input
    files = []
    
    file_refs = re.findall(r"'([^']+)'", user_input)
    for ref in file_refs:
        # Handle file:start,end or file:start:end format
        if ':' in ref:
            file_path, line_range = ref.split(':', 1)
            # Initialize with default values
            start_line = 1  # 1-based
            end_line = -1
            
            # Process line range if specified
            if ',' in line_range or ':' in line_range:
                try:
                    raw_start, raw_end = map(int, re.split(r'[,:]', line_range))
                    
                    # Handle special values and Python-style negative indices
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            total_lines = len(f.readlines())
                    except FileNotFoundError:
                        PrettyOutput.print(f"文件不存在: {file_path}", OutputType.WARNING)
                        continue
                    # Process start line
                    if raw_start == 0:  # 0表示整个文件
                        start_line = 1
                        end_line = total_lines
                    else:
                        start_line = raw_start if raw_start > 0 else total_lines + raw_start + 1
                    
                    # Process end line
                    if raw_end == 0:  # 0表示整个文件（如果start也是0）
                        end_line = total_lines
                    else:
                        end_line = raw_end if raw_end > 0 else total_lines + raw_end + 1
                    
                    # Auto-correct ranges
                    start_line = max(1, min(start_line, total_lines))
                    end_line = max(start_line, min(end_line, total_lines))
                    
                    # Final validation
                    if start_line < 1 or end_line > total_lines or start_line > end_line:
                        raise ValueError

                except:
                    continue
            
            # Add file if it exists
            if os.path.isfile(file_path):
                files.append({
                    "path": file_path,
                    "start_line": start_line,
                    "end_line": end_line
                })
        else:
            # Handle simple file path
            if os.path.isfile(ref):
                files.append({
                    "path": ref,
                    "start_line": 1,  # 1-based
                    "end_line": -1
                })
    
    # Read and process files if any were found
    if files:
        result = FileOperationTool().execute({"operation":"read","files": files})
        if result["success"]:
            return result["stdout"] + "\n" + prompt, False
    
    return prompt, False



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
                                 "lsp_get_document_symbols", 
                                 "lsp_get_diagnostics", 
                                 "lsp_find_references", 
                                 "lsp_find_definition", 
                                 "lsp_prepare_rename"
                                 ])
        code_system_prompt = """
# 角色：高级代码工程师
精通安全、精确的代码修改，具有严格的验证流程。

## 核心原则
1. 安全第一：绝不破坏现有功能
2. 精准工程：最小化、针对性修改
3. 完整可追溯：记录所有决策
4. 验证驱动：在每个阶段进行验证

## 工具使用协议
1. 分析工具：
   - lsp_get_document_symbols：映射代码结构
   - lsp_find_references：理解使用模式
   - lsp_find_definition：追踪实现细节

2. 验证工具：
   - lsp_prepare_rename：安全重构检查
   - lsp_get_diagnostics：修改后检查

3. 系统工具：
   - execute_shell：用于git操作和grep搜索
   - ask_codebase：查询代码知识库
   - search_web：技术参考查找

## 工作流程（PDCA循环）
1. 计划：
   - 使用ask_user分析需求
   - 使用LSP工具映射现有代码
   - 使用find_references识别影响区域
   - 使用git创建回滚计划

2. 执行：
   - 在受保护的块中进行原子修改
   - 每次更改后自动运行lsp_get_diagnostics
   - 如果发现错误，使用lsp_find_references和lsp_find_definition进行即时修复
   - 每次更改后使用LSP验证语法

3. 检查：
   - 强制使用lsp_get_diagnostics进行完整诊断报告
   - 使用lsp_preprepare_rename验证所有重命名
   - 如果检测到错误，进入修复循环直到所有检查通过

4. 行动：
   - 使用git提交详细消息
   - 准备回滚脚本（如果需要）
   - 进行实施后审查

## 代码修改标准
1. 修改前要求：
   - 完整的代码分析报告
   - 影响评估矩阵
   - 回滚程序文档

2. 修改实施：
   - 单一职责修改
   - 严格的代码范围验证（±3行缓冲区）
   - 接口兼容性检查

3. 验证清单：
   [ ] 执行lsp_get_diagnostics并确保零错误
   [ ] 使用lsp_find_references确认影响范围
   [ ] 使用lsp_prepare_rename验证重命名安全性

4. 修改后：
   - 代码审查模拟
   - 版本控制审计
   - 更新变更日志

## 关键要求
1. 强制分析：
   - 修改前完整符号追踪
   - 跨文件影响分析
   - 依赖关系映射

2. 禁止操作：
   - 未通过lsp_get_diagnostics检查继续操作
   - 多个功能组合修改
   - 未经测试的接口修改

3. 紧急协议：
   - lsp_get_diagnostics出现错误时立即停止并回滚
   - 出现意外行为时通知用户
   - 对任何回归进行事后分析
"""
        self.agent = Agent(system_prompt=code_system_prompt, 
                           name="CodeAgent", 
                           auto_complete=False,
                           is_sub_agent=False, 
                           use_methodology=False,
                           output_handler=[tool_registry, PatchOutputHandler()], 
                           platform=PlatformRegistry().get_codegen_platform(), 
                           record_methodology=False,
                           input_handler=[shell_input_handler, file_input_handler],
                           need_summary=False)

    

    def _init_env(self):
        curr_dir = os.getcwd()
        git_dir = find_git_root(curr_dir)
        self.root_dir = git_dir
        if has_uncommitted_changes():
            git_commiter = GitCommitTool()
            git_commiter.execute({})

    

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
                    subprocess.run(["git", "reset", "--soft", start_commit], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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