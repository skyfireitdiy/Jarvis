import os
import re
import threading
import time
from typing import Dict, Any, List, Tuple

import yaml
from jarvis.models.base import BasePlatform
from jarvis.utils import OutputType, PrettyOutput, find_git_root, get_multiline_input, load_env_from_file
from jarvis.models.registry import PlatformRegistry
from jarvis.jarvis_codebase.main import CodeBase
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
import fnmatch

# 全局锁对象
index_lock = threading.Lock()

class JarvisCoder:
    def __init__(self, root_dir: str, language: str):
        """初始化代码修改工具"""
        
        self.platform = os.environ.get("JARVIS_CODEGEN_PLATFORM") or os.environ.get("JARVIS_PLATFORM")
        self.model = os.environ.get("JARVIS_CODEGEN_MODEL") or os.environ.get("JARVIS_MODEL")


        if not self.platform or not self.model:
            raise ValueError("JARVIS_CODEGEN_PLATFORM or JARVIS_CODEGEN_MODEL is not set")

        self.root_dir = find_git_root(root_dir)
        if not self.root_dir:
            self.root_dir = root_dir

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

        # 3. 查看代码库是否有未提交的文件，如果有，提交一次
        if self._has_uncommitted_files():
            PrettyOutput.print("代码库有未提交的文件，提交一次", OutputType.INFO)
            os.system(f"git add .")
            os.system(f"git commit -m 'commit before code edit'")

        # 4. 初始化代码库
        self._codebase = CodeBase(self.root_dir)

    def _new_model(self):
        """获取大模型"""
        model = PlatformRegistry().get_global_platform_registry().create_platform(self.platform)
        if self.model:
            model_name = self.model
            model.set_model_name(model_name)
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

    def _call_model_with_retry(self, model: BasePlatform, prompt: str, max_retries: int = 3, initial_delay: float = 1.0) -> Tuple[bool, str]:
        """调用模型并支持重试
        
        Args:
            prompt: 提示词
            max_retries: 最大重试次数
            initial_delay: 初始延迟时间(秒)
            
        Returns:
            Tuple[bool, str]: (是否成功, 响应内容)
        """
        delay = initial_delay
        for attempt in range(max_retries):
            try:
                response = model.chat(prompt)
                return True, response
            except Exception as e:
                if attempt == max_retries - 1:  # 最后一次尝试
                    PrettyOutput.print(f"调用模型失败: {str(e)}", OutputType.ERROR)
                    return False, str(e)
                    
                PrettyOutput.print(f"调用模型失败，{delay}秒后重试: {str(e)}", OutputType.WARNING)
                time.sleep(delay)
                delay *= 2  # 指数退避
                
    def _remake_patch(self, prompt: str) -> List[str]:
        success, response = self._call_model_with_retry(self.main_model, prompt, max_retries=5)  # 增加重试次数
        if not success:
            return []
            
        try:
            patches = re.findall(r'<PATCH_START>.*?<PATCH_END>', response, re.DOTALL)
            return [patch.replace('<PATCH_START>', '').replace('<PATCH_END>', '').strip() 
                   for patch in patches if patch.strip()]
        except Exception as e:
            PrettyOutput.print(f"解析patch失败: {str(e)}", OutputType.WARNING)
            return []
        
    def _make_patch(self, related_files: List[Dict], feature: str) -> List[str]:
        """生成修改方案"""
        prompt = """你是一个资深程序员，请根据需求描述，修改文件内容。

修改格式说明：
1. 每个修改块格式如下：
<PATCH_START>
>>>>>> path/to/file
要替换的内容
=======
新的内容
>>>>>>
<PATCH_END>

2. 如果是新文件或者替换整个文件内容，格式如下：
<PATCH_START>
>>>>>> path/to/new/file
=======
新文件的完整内容
>>>>>>
<PATCH_END>

3. 如果要删除文件中的某一段，格式如下：
<PATCH_START>
>>>>>> path/to/file
要删除的内容
=======
>>>>>>
<PATCH_END>

文件列表如下：
"""
        for i, file in enumerate(related_files):
            if len(prompt) > 30 * 1024:
                PrettyOutput.print(f'避免上下文超限，丢弃低相关度文件：{file["file_path"]}', OutputType.WARNING)
                continue
            prompt += f"""{i}. {file["file_path"]}\n"""
            prompt += f"""文件内容:\n"""
            prompt += f"<FILE_CONTENT_START>\n"
            prompt += f'{file["file_content"]}\n'
            prompt += f"<FILE_CONTENT_END>\n"
        
        prompt += f"\n需求描述: {feature}\n"
        prompt += """
注意事项：
1、仅输出补丁内容，不要输出任何其他内容，每个补丁必须用<PATCH_START>和<PATCH_END>标记
2、如果在大段代码中有零星修改，生成多个补丁
3、要替换的内容，一定要与文件内容完全一致，不要有任何多余或者缺失的内容
4、每个patch不超过20行，超出20行，请生成多个patch
"""
        
        success, response = self._call_model_with_retry(self.main_model, prompt)
        if not success:
            return []
            
        try:
            # 使用正则表达式匹配每个patch块
            patches = re.findall(r'<PATCH_START>.*?<PATCH_END>', response, re.DOTALL)
            return [patch.replace('<PATCH_START>', '').replace('<PATCH_END>', '').strip() 
                   for patch in patches if patch.strip()]
        except Exception as e:
            PrettyOutput.print(f"解析patch失败: {str(e)}", OutputType.WARNING)
            return []

    def _apply_patch(self, related_files: List[Dict], patches: List[str]) -> Tuple[bool, str]:
        """应用补丁"""
        error_info = []
        modified_files = set()

        # 创建文件内容映射
        file_map = {file["file_path"]: file["file_content"] for file in related_files}
        temp_map = file_map.copy()  # 创建临时映射用于尝试应用
        
        # 尝试应用所有补丁
        for i, patch in enumerate(patches):
            PrettyOutput.print(f"正在应用补丁 {i+1}/{len(patches)}", OutputType.INFO)
            
            try:
                # 解析补丁
                lines = patch.split("\n")
                if not lines:
                    continue
                    
                # 获取文件路径
                file_path_match = re.search(r'>>>>>> (.*)', lines[0])
                if not file_path_match:
                    error_info.append(f"无法解析文件路径: {lines[0]}")
                    return False, "\n".join(error_info)
                    
                file_path = file_path_match.group(1).strip()
                
                # 解析补丁内容
                patch_content = "\n".join(lines[1:])
                parts = patch_content.split("=======")
                
                if len(parts) != 2:
                    error_info.append(f"补丁格式错误: {file_path}")
                    return False, "\n".join(error_info)
                
                old_content = parts[0]
                new_content = parts[1].split(">>>>>>")[0]
                
                # 处理新文件
                if not old_content:
                    temp_map[file_path] = new_content
                    modified_files.add(file_path)
                    continue
                
                # 处理文件修改
                if file_path not in temp_map:
                    error_info.append(f"文件不存在: {file_path}")
                    return False, "\n".join(error_info)
                
                current_content = temp_map[file_path]
                
                # 查找并替换代码块
                if old_content not in current_content:
                    error_info.append(
                        f"补丁应用失败: {file_path}\n"
                        f"原因: 未找到要替换的代码\n"
                        f"期望找到的代码:\n{old_content}\n"
                        f"实际文件内容:\n{current_content[:200]}..."  # 只显示前200个字符
                    )
                    return False, "\n".join(error_info)
                
                # 应用更改
                temp_map[file_path] = current_content.replace(old_content, new_content)
                modified_files.add(file_path)
                
            except Exception as e:
                error_info.append(f"处理补丁时发生错误: {str(e)}")
                return False, "\n".join(error_info)
        
        # 所有补丁都应用成功，更新实际文件
        for file_path in modified_files:
            try:
                dir_path = os.path.dirname(file_path)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                    
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(temp_map[file_path])
                    
                PrettyOutput.print(f"成功修改文件: {file_path}", OutputType.SUCCESS)
                
            except Exception as e:
                error_info.append(f"写入文件失败 {file_path}: {str(e)}")
                return False, "\n".join(error_info)
        
        return True, ""

    def _save_edit_record(self, feature: str, patches: List[str]) -> None:
        """保存代码修改记录
        
        Args:
            feature: 需求描述
            patches: 补丁列表
        """
            
        # 获取下一个序号
        existing_records = [f for f in os.listdir(self.record_dir) if f.endswith('.yaml')]
        next_num = 1
        if existing_records:
            last_num = max(int(f[:4]) for f in existing_records)
            next_num = last_num + 1
        
        # 创建记录文件
        record = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "feature": feature,
            "patches": patches
        }
        
        record_path = os.path.join(self.record_dir, f"{next_num:04d}.yaml")
        with open(record_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(record, f, allow_unicode=True)
        
        PrettyOutput.print(f"已保存修改记录: {record_path}", OutputType.SUCCESS)




    def _prepare_execution(self) -> None:
        """准备执行环境"""
        self.main_model = self._new_model()
        self._codebase.generate_codebase()


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

    def _handle_patch_application(self, related_files: List[Dict], patches: List[str], feature: str) -> Dict[str, Any]:
        """处理补丁应用流程"""
        while True:
            PrettyOutput.print(f"生成{len(patches)}个补丁", OutputType.INFO)
            
            if not patches:
                retry_prompt = f"""未生成补丁，请重新生成补丁"""
                patches = self._remake_patch(retry_prompt)
                continue
            
            success, error_info = self._apply_patch(related_files, patches)
            
            if success:
                user_confirm = input("是否确认修改？(y/n)")
                if user_confirm.lower() == "y":
                    self._finalize_changes(feature, patches)
                    return {
                        "success": True,
                        "stdout": f"已完成功能开发{feature}",
                        "stderr": "",
                        "error": None
                    }
                else:
                    self._revert_changes()
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "修改被用户取消，文件未发生任何变化",
                        "error": UserWarning("用户取消修改")
                    }
            else:
                PrettyOutput.print(f"补丁应用失败，请求重新生成: {error_info}", OutputType.WARNING)
                retry_prompt = f"""补丁应用失败，请根据以下错误信息重新生成补丁：

错误信息：
{error_info}

请确保：
1. 准确定位要修改的代码位置
2. 正确处理代码缩进
3. 考虑代码上下文
4. 对新文件不要包含原始内容
"""
                patches = self._remake_patch(retry_prompt)




    def _generate_commit_message(self, patches: List[str]) -> str:
        """根据git diff生成commit信息
        
        Args:
            patches: 补丁列表
            
        Returns:
            str: 生成的commit信息
        """
        # 获取git diff --cached的输出
        git_diff = os.popen("git diff --cached").read()
        
        # 生成提示词
        prompt = """你是一个经验丰富的程序员，请根据以下代码变更生成简洁明了的commit信息：

代码变更：
"""
        # 添加git diff内容
        prompt += f"Git Diff:\n{git_diff}\n\n"
            
        prompt += """
请遵循以下规则：
1. 使用英文编写
2. 采用常规的commit message格式：<type>(<scope>): <subject>
3. 保持简洁，不超过50个字符
4. 准确描述代码变更的主要内容
5. 优先考虑git diff中的变更内容
"""
        
        # 使用normal模型生成commit信息
        model = PlatformRegistry().get_global_platform_registry().create_platform(self.platform)
        model.set_model(self.model)
        model.set_suppress_output(True)
        success, response = self._call_model_with_retry(model, prompt)
        if not success:
            return "Update code changes"
            
        # 清理响应内容
        return response.strip().split("\n")[0]

    def _finalize_changes(self, feature: str, patches: List[str]) -> None:
        """完成修改并提交"""
        PrettyOutput.print("修改确认成功，提交修改", OutputType.INFO)
        
        # 自动生成commit信息
        commit_message = self._generate_commit_message(patches)
        
        # 显示并确认commit信息
        PrettyOutput.print(f"自动生成的commit信息: {commit_message}", OutputType.INFO)
        user_confirm = input("是否使用该commit信息？(y/n) [y]: ") or "y"
        
        if user_confirm.lower() != "y":
            commit_message = input("请输入新的commit信息: ")
        
        os.system(f"git add .")
        os.system(f"git commit -m '{commit_message}'")
        self._save_edit_record(feature, patches)

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
                - success: 是否成功
                - stdout: 标准输出信息
                - stderr: 错误信息
                - error: 错误对象(如果有)
        """
        try:
            self._prepare_execution()
            related_files = self._load_related_files(feature)
            patches = self._make_patch(related_files, feature)
            return self._handle_patch_application(related_files, patches, feature)
                
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行失败: {str(e)}",
                "error": e
            }


def main():
    """命令行入口"""
    import argparse

    load_env_from_file()
    
    parser = argparse.ArgumentParser(description='代码修改工具')
    parser.add_argument('-p', '--platform', help='AI平台名称', default=os.environ.get('JARVIS_CODEGEN_PLATFORM'))
    parser.add_argument('-m', '--model', help='模型名称', default=os.environ.get('JARVIS_CODEGEN_MODEL'))
    parser.add_argument('-d', '--dir', help='项目根目录', default=os.getcwd())
    parser.add_argument('-l', '--language', help='编程语言', default="python")
    args = parser.parse_args()
    
    # 设置平台
    if not args.platform:
        print("错误: 未指定AI平台，请使用 -p 参数")
    # 设置模型
    if args.model:
        os.environ['JARVIS_CODEGEN_MODEL'] = args.model
        
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
                if result["stderr"]:
                    PrettyOutput.print(result["stderr"], OutputType.WARNING)
                if result["error"]:
                    PrettyOutput.print(f"错误类型: {type(result['error']).__name__}", OutputType.WARNING)
                
        except KeyboardInterrupt:
            print("\n用户中断执行")
            break
        except Exception as e:
            PrettyOutput.print(f"执行出错: {str(e)}", OutputType.ERROR)
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
