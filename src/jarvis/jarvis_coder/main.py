import os
import re
import threading
import time
from typing import Dict, Any, List, Tuple

import yaml
from jarvis.models.base import BasePlatform
from jarvis.utils import OutputType, PrettyOutput, find_git_root, get_max_context_length, get_multiline_input, load_env_from_file
from jarvis.models.registry import PlatformRegistry
from jarvis.jarvis_codebase.main import CodeBase
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
import fnmatch
from .patch_handler import PatchHandler
from .git_utils import has_uncommitted_files, generate_commit_message, save_edit_record

# 全局锁对象
index_lock = threading.Lock()

class JarvisCoder:
    def __init__(self, root_dir: str, language: str):
        """初始化代码修改工具"""
        self.root_dir = root_dir
        self.language = language
        self._init_directories()
        self._init_codebase()
        
    def _init_directories(self):
        """初始化目录"""
        self.max_context_length = get_max_context_length()

        self.root_dir = find_git_root(self.root_dir)
        if not self.root_dir:
            self.root_dir = self.root_dir

        PrettyOutput.print(f"Git根目录: {self.root_dir}", OutputType.INFO)

        # 1. 判断代码库路径是否存在，如果不存在，创建
        if not os.path.exists(self.root_dir):
            PrettyOutput.print(
                "Root directory does not exist, creating...", OutputType.INFO)
            os.makedirs(self.root_dir)

        os.chdir(self.root_dir)

        self.jarvis_dir = os.path.join(self.root_dir, ".jarvis-coder")
        if not os.path.exists(self.jarvis_dir):
            os.makedirs(self.jarvis_dir)

        self.record_dir = os.path.join(self.jarvis_dir, "record")
        if not os.path.exists(self.record_dir):
            os.makedirs(self.record_dir)

        # 2. 判断代码库是否是git仓库，如果不是，初始化git仓库
        if not os.path.exists(os.path.join(self.root_dir, ".git")):
            PrettyOutput.print(
                "Git repository does not exist, initializing...", OutputType.INFO)
            os.system(f"git init")
            # 2.1 添加所有的文件
            os.system(f"git add .")
            # 2.2 提交
            os.system(f"git commit -m 'Initial commit'")

            PrettyOutput.print("代码库有未提交的文件，提交一次", OutputType.INFO)
            os.system(f"git add .")
            os.system(f"git commit -m 'commit before code edit'")
        # 3. 查看代码库是否有未提交的文件，如果有，提交一次
        if self._has_uncommitted_files():
            PrettyOutput.print("代码库有未提交的文件，提交一次", OutputType.INFO)
            os.system(f"git add .")
            git_diff = os.popen("git diff --cached").read()
            commit_message = generate_commit_message(git_diff, "Pre-edit commit")
            os.system(f"git commit -m '{commit_message}'")
            PrettyOutput.print("代码库有未提交的文件，提交一次", OutputType.INFO)
            os.system(f"git add .")
            os.system(f"git commit -m 'commit before code edit'")

    def _init_codebase(self):
        """初始化代码库"""
        self._codebase = CodeBase(self.root_dir)

    def _new_model(self):
        """获取大模型"""
        model = PlatformRegistry().get_global_platform_registry().get_codegen_platform()
        return model

    def _has_uncommitted_files(self) -> bool:
        """判断代码库是否有未提交的文件"""
        # 获取未暂存的修改
        unstaged = os.popen("git diff --name-only").read()
        # 获取已暂存但未提交的修改
        staged = os.popen("git diff --cached --name-only").read()
        # 获取未跟踪的文件
        untracked = os.popen("git ls-files --others --exclude-standard").read()
        
        return bool(unstaged or staged or untracked)

    def _prepare_execution(self) -> None:
        """准备执行环境"""
        self.thinking_model = PlatformRegistry().get_global_platform_registry().get_thinking_platform()
        self.codegen_model = PlatformRegistry().get_global_platform_registry().get_codegen_platform()
        self._codebase.generate_codebase()

    def _get_modification_plan(self, feature: str, related_files: List[Dict]) -> str:
        """获取修改方案
        
        Args:
            feature: 功能描述
            related_files: 相关文件列表
            
        Returns:
            str: 修改方案，如果用户取消则返回 None
        """
        user_feedback = None
        
        while True:
            # 构建提示词
            prompt = "我需要你帮我分析如何实现以下功能:\n\n"
            prompt += f"{feature}\n\n"
            
            # 如果有用户反馈，添加到提示中
            if user_feedback:
                prompt += "用户对之前的方案有以下补充意见：\n"
                prompt += f"{user_feedback}\n\n"
            
            prompt += "以下是相关的代码文件:\n\n"
            
            for file in related_files:
                prompt += f"文件: {file['file_path']}\n```\n{file['file_content']}\n```\n\n"
            
            prompt += "\n请详细说明需要做哪些修改来实现这个功能。包括:\n"
            prompt += "1. 需要修改哪些文件\n"
            prompt += "2. 每个文件需要做什么修改\n"
            prompt += "3. 修改的主要逻辑和原因\n"
            
            # 获取修改方案
            plan = self.thinking_model.chat(prompt)
            
            # 显示修改方案并获取用户确认
            PrettyOutput.section("修改方案", OutputType.PLANNING)
            PrettyOutput.print(plan, OutputType.PLANNING)
            
            user_input = input("\n是否同意这个修改方案？(y/n/f) [y]: ").strip().lower() or 'y'
            if user_input == 'y':
                return plan
            elif user_input == 'n':
                return None
            else:  # 'f' - feedback
                # 获取用户反馈
                PrettyOutput.print("\n请输入您的补充意见或建议:", OutputType.INFO)
                user_feedback = get_multiline_input("")
                if user_feedback == "__interrupt__":
                    return None
                continue

    def _load_related_files(self, feature: str) -> List[Dict]:
        """加载相关文件内容"""
        ret = []
        # 确保索引数据库已生成
        if not self._codebase.is_index_generated():
            PrettyOutput.print("检测到索引数据库未生成，正在生成...", OutputType.WARNING)
            self._codebase.generate_codebase()
            
        related_files = self._codebase.search_similar(feature)
        for file, score, _ in related_files:
            PrettyOutput.print(f"相关文件: {file} 相关度: {score:.3f}", OutputType.SUCCESS)
            with open(file, "r", encoding="utf-8") as f:
                content = f.read()
            ret.append({"file_path": file, "file_content": content})
        return ret

    def _finalize_changes(self, feature: str) -> None:
        """完成修改并提交"""
        PrettyOutput.print("修改确认成功，提交修改", OutputType.INFO)

        # 只添加已经在 git 控制下的修改文件
        os.system("git add -u")
        
        # 然后获取 git diff
        git_diff = os.popen("git diff --cached").read()
        
        # 自动生成commit信息，传入feature
        commit_message = generate_commit_message(git_diff, feature)
        
        # 显示并确认commit信息
        PrettyOutput.print(f"自动生成的commit信息: {commit_message}", OutputType.INFO)
        user_confirm = input("是否使用该commit信息？(y/n) [y]: ") or "y"
        
        if user_confirm.lower() != "y":
            commit_message = input("请输入新的commit信息: ")
        
        # 不需要再次 git add，因为已经添加过了
        os.system(f"git commit -m '{commit_message}'")
        save_edit_record(self.record_dir, commit_message, git_diff)

    def _revert_changes(self) -> None:
        """回退所有修改"""
        PrettyOutput.print("修改已取消，回退更改", OutputType.INFO)
        os.system(f"git reset --hard")
        os.system(f"git clean -df")

    def execute(self, feature: str) -> Dict[str, Any]:
        """执行代码修改

        Args:
            feature: 要实现的功能描述

        Returns:
            Dict[str, Any]: 包含执行结果的字典
        """
        try:
            self._prepare_execution()
            related_files = self._load_related_files(feature)
            
            # 获取修改方案
            modification_plan = self._get_modification_plan(feature, related_files)
            if not modification_plan:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "用户取消修改",
                }
            
            # 执行修改
            patch_handler = PatchHandler(self.codegen_model)
            if patch_handler.handle_patch_application(related_files, feature):
                self._finalize_changes(feature)
                return {
                    "success": True,
                    "stdout": "代码修改成功",
                    "stderr": "",
                }
            else:
                self._revert_changes()
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "代码修改失败，请修改需求后重试",
                }
                
        except Exception as e:
            self._revert_changes()
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行失败: {str(e)}，请修改需求后重试",
                "error": e
            }

def main():
    """命令行入口"""
    import argparse

    load_env_from_file()
    
    parser = argparse.ArgumentParser(description='代码修改工具')
    parser.add_argument('-d', '--dir', help='项目根目录', default=os.getcwd())
    parser.add_argument('-l', '--language', help='编程语言', default="python")
    args = parser.parse_args()
    
    tool = JarvisCoder(args.dir, args.language)
    
    # 循环处理需求
    while True:
        try:
            # 获取需求，传入项目根目录
            feature = get_multiline_input("请输入开发需求 (输入空行退出):", tool.root_dir)
            
            if not feature or feature == "__interrupt__":
                break
                
            # 执行修改
            result = tool.execute(feature)
            
            # 显示结果
            if result["success"]:
                PrettyOutput.print(result["stdout"], OutputType.SUCCESS)
            else:
                if result.get("stderr"):
                    PrettyOutput.print(result["stderr"], OutputType.WARNING)
                if result.get("error"):  # 使用 get() 方法避免 KeyError
                    error = result["error"]
                    PrettyOutput.print(f"错误类型: {type(error).__name__}", OutputType.WARNING)
                    PrettyOutput.print(f"错误信息: {str(error)}", OutputType.WARNING)
                # 提示用户可以继续输入
                PrettyOutput.print("\n您可以修改需求后重试", OutputType.INFO)
                
        except KeyboardInterrupt:
            print("\n用户中断执行")
            break
        except Exception as e:
            PrettyOutput.print(f"执行出错: {str(e)}", OutputType.ERROR)
            PrettyOutput.print("\n您可以修改需求后重试", OutputType.INFO)
            continue
            
    return 0

if __name__ == "__main__":
    exit(main())

class FilePathCompleter(Completer):
    """文件路径自动完成器"""
    
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self._file_list = None
        
    def _get_files(self) -> List[str]:
        """获取git管理的文件列表"""
        if self._file_list is None:
            try:
                # 切换到项目根目录
                old_cwd = os.getcwd()
                os.chdir(self.root_dir)
                
                # 获取git管理的文件列表
                self._file_list = os.popen("git ls-files").read().splitlines()
                
                # 恢复工作目录
                os.chdir(old_cwd)
            except Exception as e:
                PrettyOutput.print(f"获取文件列表失败: {str(e)}", OutputType.WARNING)
                self._file_list = []
        return self._file_list
    
    def get_completions(self, document, complete_event):
        """获取补全建议"""
        text_before_cursor = document.text_before_cursor
        
        # 检查是否刚输入了@
        if text_before_cursor.endswith('@'):
            # 显示所有文件
            for path in self._get_files():
                yield Completion(path, start_position=0)
            return
            
        # 检查之前是否有@，并获取@后的搜索词
        at_pos = text_before_cursor.rfind('@')
        if at_pos == -1:
            return
            
        search = text_before_cursor[at_pos + 1:].lower().strip()
        
        # 提供匹配的文件建议
        for path in self._get_files():
            path_lower = path.lower()
            if (search in path_lower or  # 直接包含
                search in os.path.basename(path_lower) or  # 文件名包含
                any(fnmatch.fnmatch(path_lower, f'*{s}*') for s in search.split())): # 通配符匹配
                # 计算正确的start_position
                yield Completion(path, start_position=-(len(search)))

class SmartCompleter(Completer):
    """智能自动完成器，组合词语和文件路径补全"""
    
    def __init__(self, word_completer: WordCompleter, file_completer: FilePathCompleter):
        self.word_completer = word_completer
        self.file_completer = file_completer
        
    def get_completions(self, document, complete_event):
        """获取补全建议"""
        # 如果当前行以@结尾，使用文件补全
        if document.text_before_cursor.strip().endswith('@'):
            yield from self.file_completer.get_completions(document, complete_event)
        else:
            # 否则使用词语补全
            yield from self.word_completer.get_completions(document, complete_event)

def get_multiline_input(prompt_text: str, root_dir: str = None) -> str:
    """获取多行输入，支持文件路径自动完成功能
    
    Args:
        prompt_text: 提示文本
        root_dir: 项目根目录，用于文件补全
        
    Returns:
        str: 用户输入的文本
    """
    # 创建文件补全器
    file_completer = FilePathCompleter(root_dir or os.getcwd())
    
    # 创建提示样式
    style = Style.from_dict({
        'prompt': 'ansicyan bold',
        'input': 'ansiwhite',
    })
    
    # 创建会话
    session = PromptSession(
        completer=file_completer,
        style=style,
        multiline=False,
        enable_history_search=True,
        complete_while_typing=True
    )
    
    # 显示初始提示文本
    print(f"\n{prompt_text}")
    
    # 创建提示符
    prompt = FormattedText([
        ('class:prompt', ">>> ")
    ])
    
    # 获取输入
    lines = []
    try:
        while True:
            line = session.prompt(prompt).strip()
            if not line:  # 空行表示输入结束
                break
            lines.append(line)
    except KeyboardInterrupt:
        return "__interrupt__"
    except EOFError:
        pass
    
    return "\n".join(lines)