import os
import threading
from typing import Dict, Any, List, Optional
import re

from jarvis.utils import OutputType, PrettyOutput, find_git_root, get_max_context_length, load_env_from_file
from jarvis.models.registry import PlatformRegistry
from jarvis.jarvis_codebase.main import CodeBase
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
import fnmatch
from .patch_handler import PatchHandler
from .git_utils import generate_commit_message, save_edit_record
from .plan_generator import PlanGenerator

# 全局锁对象
index_lock = threading.Lock()

class JarvisCoder:
    def __init__(self, root_dir: str, language: Optional[str] = "python"):
        """初始化代码修改工具"""
        self.root_dir = root_dir
        self.language = language
        self._init_directories()
        self._init_codebase()
        
    def _init_directories(self):
        """初始化目录"""
        self.max_context_length = get_max_context_length()

        root_dir = find_git_root(self.root_dir)
        if not root_dir:
            root_dir = self.root_dir

        self.root_dir = root_dir

        PrettyOutput.print(f"Git根目录: {self.root_dir}", OutputType.INFO)

        # 1. 判断代码库路径是否存在，如果不存在，创建
        if not os.path.exists(self.root_dir):
            PrettyOutput.print(
                "Root directory does not exist, creating...", OutputType.INFO)
            os.makedirs(self.root_dir)

        os.chdir(self.root_dir)

        # 2. 创建 .jarvis-coder 目录
        self.jarvis_dir = os.path.join(self.root_dir, ".jarvis-coder")
        if not os.path.exists(self.jarvis_dir):
            os.makedirs(self.jarvis_dir)

        self.record_dir = os.path.join(self.jarvis_dir, "record")
        if not os.path.exists(self.record_dir):
            os.makedirs(self.record_dir)

        # 3. 处理 .gitignore 文件
        gitignore_path = os.path.join(self.root_dir, ".gitignore")
        gitignore_modified = False
        jarvis_ignore_pattern = ".jarvis-*"

        # 3.1 如果 .gitignore 不存在，创建它
        if not os.path.exists(gitignore_path):
            PrettyOutput.print("创建 .gitignore 文件", OutputType.INFO)
            with open(gitignore_path, "w", encoding="utf-8") as f:
                f.write(f"{jarvis_ignore_pattern}\n")
            gitignore_modified = True
        else:
            # 3.2 检查是否已经包含 .jarvis-* 模式
            with open(gitignore_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 检查是否需要添加 .jarvis-* 模式
            if jarvis_ignore_pattern not in content.split("\n"):
                PrettyOutput.print("将 .jarvis-* 添加到 .gitignore", OutputType.INFO)
                with open(gitignore_path, "a", encoding="utf-8") as f:
                    # 确保文件以换行符结尾
                    if not content.endswith("\n"):
                        f.write("\n")
                    f.write(f"{jarvis_ignore_pattern}\n")
                gitignore_modified = True

        # 4. 判断代码库是否是git仓库，如果不是，初始化git仓库
        if not os.path.exists(os.path.join(self.root_dir, ".git")):
            PrettyOutput.print("初始化 Git 仓库", OutputType.INFO)
            os.system("git init")
            os.system("git add .")
            os.system("git commit -m 'Initial commit'")
        # 5. 如果修改了 .gitignore，提交更改
        elif gitignore_modified:
            PrettyOutput.print("提交 .gitignore 更改", OutputType.INFO)
            os.system("git add .gitignore")
            os.system("git commit -m 'chore: update .gitignore to exclude .jarvis-* files'")
        # 6. 查看代码库是否有未提交的文件，如果有，提交一次
        elif self._has_uncommitted_files():
            PrettyOutput.print("提交未保存的更改", OutputType.INFO)
            os.system("git add .")
            git_diff = os.popen("git diff --cached").read()
            commit_message = generate_commit_message(git_diff, "Pre-edit commit")
            os.system(f"git commit -m '{commit_message}'")

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
        self.plan_generator = PlanGenerator(self.thinking_model)


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

    def _parse_file_selection(self, input_str: str, max_index: int) -> List[int]:
        """解析文件选择表达式
        
        支持的格式:
        - 单个数字: "1"
        - 逗号分隔: "1,3,5"
        - 范围: "1-5"
        - 组合: "1,3-5,7"
        
        Args:
            input_str: 用户输入的选择表达式
            max_index: 最大可选择的索引
            
        Returns:
            List[int]: 选中的索引列表（从0开始）
        """
        selected = set()
        
        # 移除所有空白字符
        input_str = "".join(input_str.split())
        
        # 处理逗号分隔的部分
        for part in input_str.split(","):
            if not part:
                continue
            
            # 处理范围（例如：3-6）
            if "-" in part:
                try:
                    start, end = map(int, part.split("-"))
                    # 转换为从0开始的索引
                    start = max(0, start - 1)
                    end = min(max_index, end - 1)
                    if start <= end:
                        selected.update(range(start, end + 1))
                except ValueError:
                    PrettyOutput.print(f"忽略无效的范围表达式: {part}", OutputType.WARNING)
            # 处理单个数字
            else:
                try:
                    index = int(part) - 1  # 转换为从0开始的索引
                    if 0 <= index < max_index:
                        selected.add(index)
                    else:
                        PrettyOutput.print(f"忽略超出范围的索引: {part}", OutputType.WARNING)
                except ValueError:
                    PrettyOutput.print(f"忽略无效的数字: {part}", OutputType.WARNING)
        
        return sorted(list(selected))

    def _get_file_completer(self) -> Completer:
        """创建文件路径补全器"""
        class FileCompleter(Completer):
            def __init__(self, root_dir: str):
                self.root_dir = root_dir
                
            def get_completions(self, document, complete_event):
                # 获取当前输入的文本
                text = document.text_before_cursor
                
                # 如果输入为空，返回根目录下的所有文件
                if not text:
                    for path in self._list_files(""):
                        yield Completion(path, start_position=0)
                    return
                    
                # 获取当前目录和部分文件名
                current_dir = os.path.dirname(text)
                file_prefix = os.path.basename(text)
                
                # 列出匹配的文件
                search_dir = os.path.join(self.root_dir, current_dir) if current_dir else self.root_dir
                if os.path.isdir(search_dir):
                    for path in self._list_files(current_dir):
                        if path.startswith(text):
                            yield Completion(path, start_position=-len(text))
            
            def _list_files(self, current_dir: str) -> List[str]:
                """列出指定目录下的所有文件（递归）"""
                files = []
                search_dir = os.path.join(self.root_dir, current_dir)
                
                for root, _, filenames in os.walk(search_dir):
                    for filename in filenames:
                        full_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(full_path, self.root_dir)
                        # 忽略 .git 目录和其他隐藏文件
                        if not any(part.startswith('.') for part in rel_path.split(os.sep)):
                            files.append(rel_path)
                
                return sorted(files)

        return FileCompleter(self.root_dir)

    def _fuzzy_match_files(self, pattern: str) -> List[str]:
        """模糊匹配文件路径
        
        Args:
            pattern: 匹配模式
            
        Returns:
            List[str]: 匹配的文件路径列表
        """
        matches = []
        
        # 将模式转换为正则表达式
        pattern = pattern.replace('.', r'\.').replace('*', '.*').replace('?', '.')
        pattern = f".*{pattern}.*"  # 允许部分匹配
        regex = re.compile(pattern, re.IGNORECASE)
        
        # 遍历所有文件
        for root, _, files in os.walk(self.root_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.root_dir)
                # 忽略 .git 目录和其他隐藏文件
                if not any(part.startswith('.') for part in rel_path.split(os.sep)):
                    if regex.match(rel_path):
                        matches.append(rel_path)
        
        return sorted(matches)

    def _select_files(self, related_files: List[Dict], feature: str) -> List[Dict]:
        """让用户选择和补充相关文件"""
        PrettyOutput.section("相关文件", OutputType.INFO)
        
        # 显示找到的文件
        selected_files = list(related_files)  # 默认全选
        for i, file in enumerate(related_files, 1):
            PrettyOutput.print(f"[{i}] {file['file_path']}", OutputType.INFO)
        
        # 询问用户是否需要调整
        user_input = input("\n是否需要调整文件列表？(y/n) [n]: ").strip().lower() or 'n'
        if user_input == 'y':
            # 让用户选择文件
            PrettyOutput.print("\n请输入要包含的文件编号（支持: 1,3-6 格式，直接回车保持当前选择）:", OutputType.INFO)
            numbers = input(">>> ").strip()
            if numbers:
                selected_indices = self._parse_file_selection(numbers, len(related_files))
                if selected_indices:
                    selected_files = [related_files[i] for i in selected_indices]
                else:
                    PrettyOutput.print("未选择任何有效文件，保持原有选择", OutputType.WARNING)
        
        # 询问是否需要补充文件
        user_input = input("\n是否需要补充其他文件？(y/n) [n]: ").strip().lower() or 'n'
        if user_input == 'y':
            # 创建文件补全会话
            session = PromptSession(
                completer=self._get_file_completer(),
                complete_while_typing=True
            )
            
            while True:
                PrettyOutput.print("\n请输入要补充的文件路径（支持Tab补全和*?通配符，输入空行结束）:", OutputType.INFO)
                try:
                    file_path = session.prompt(">>> ").strip()
                except KeyboardInterrupt:
                    break
                    
                if not file_path:
                    break
                    
                # 处理通配符匹配
                if '*' in file_path or '?' in file_path:
                    matches = self._fuzzy_match_files(file_path)
                    if not matches:
                        PrettyOutput.print("未找到匹配的文件", OutputType.WARNING)
                        continue
                        
                    # 显示匹配的文件
                    PrettyOutput.print("\n找到以下匹配的文件:", OutputType.INFO)
                    for i, path in enumerate(matches, 1):
                        PrettyOutput.print(f"[{i}] {path}", OutputType.INFO)
                        
                    # 让用户选择
                    numbers = input("\n请选择要添加的文件编号（支持: 1,3-6 格式，直接回车全选）: ").strip()
                    if numbers:
                        indices = self._parse_file_selection(numbers, len(matches))
                        if not indices:
                            continue
                        paths_to_add = [matches[i] for i in indices]
                    else:
                        paths_to_add = matches
                else:
                    paths_to_add = [file_path]
                
                # 添加选中的文件
                for path in paths_to_add:
                    full_path = os.path.join(self.root_dir, path)
                    if not os.path.isfile(full_path):
                        PrettyOutput.print(f"文件不存在: {path}", OutputType.ERROR)
                        continue
                    
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        selected_files.append({
                            "file_path": path,
                            "file_content": content
                        })
                        PrettyOutput.print(f"已添加文件: {path}", OutputType.SUCCESS)
                    except Exception as e:
                        PrettyOutput.print(f"读取文件失败: {str(e)}", OutputType.ERROR)
        
        return selected_files

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
        """执行代码修改"""
        try:
            self._prepare_execution()
            
            # 获取并选择相关文件
            initial_files = self._load_related_files(feature)
            selected_files = self._select_files(initial_files, feature)
            
            # 获取修改方案
            modification_plan = self.plan_generator.generate_plan(feature, selected_files)
            if not modification_plan:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "用户取消修改",
                }
            
            # 执行修改
            patch_handler = PatchHandler(self.codegen_model)
            if patch_handler.handle_patch_application(selected_files, feature, modification_plan):
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

def get_multiline_input(prompt_text: str, root_dir: Optional[str] = ".") -> str:
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