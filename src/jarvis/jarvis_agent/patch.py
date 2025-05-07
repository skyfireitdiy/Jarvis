import re
from typing import Dict, Any, Tuple
import os

from yaspin import yaspin # type: ignore

from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_git_utils.git_commiter import GitCommitTool
from jarvis.jarvis_tools.file_operation import FileOperationTool
from jarvis.jarvis_utils.config import is_confirm_before_apply_patch
from jarvis.jarvis_utils.git_utils import get_commits_between, get_latest_commit_hash
from jarvis.jarvis_utils.globals import add_read_file_record, has_read_file
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import is_context_overflow, get_file_line_count, user_confirm
from jarvis.jarvis_utils.tag import ot, ct


class PatchOutputHandler(OutputHandler):
    def name(self) -> str:
        return "PATCH"

    def handle(self, response: str, agent: Any) -> Tuple[bool, Any]:
        return False, apply_patch(response, agent)

    def can_handle(self, response: str) -> bool:
        if _has_patch_block(response):
            return True
        return False

    def prompt(self) -> str:
        return f"""
# 代码补丁规范

## 重要提示
我可以看到完整的代码，所以不需要生成完整的代码，只需要提供修改的代码片段即可。请尽量精简补丁内容，只包含必要的上下文和修改部分。特别注意：不要提供完整文件内容，只提供需要修改的部分！

## 补丁格式定义
使用{ot("PATCH")}块来精确指定代码更改：
```
{ot("PATCH")}
File: [文件路径]
Reason: [修改原因]
[代码修改说明，不用输出完整的代码，仅输出修改的片段即可]
{ct("PATCH")}
```

## 核心原则
1. **精准修改**：只显示需要修改的代码部分，不需要展示整个文件内容
2. **最小补丁原则**：始终生成最小范围的补丁，只包含必要的上下文和实际修改
3. **格式严格保持**：
   - 严格保持原始代码的缩进方式（空格或制表符）
   - 保持原始代码的空行数量和位置
   - 保持原始代码的行尾空格处理方式
   - 不改变原始代码的换行风格
4. **新旧区分**：
   - 对于新文件：提供完整的代码内容
   - 对于现有文件：只提供修改部分，不要提供整个文件
5. **理由说明**：每个补丁必须包含清晰的修改理由，解释为什么需要此更改

## 格式兼容性要求
1. **缩进一致性**：
   - 如果原代码使用4个空格缩进，补丁也必须使用4个空格缩进
   - 如果原代码使用制表符缩进，补丁也必须使用制表符缩进
2. **空行保留**：
   - 如果原代码在函数之间有两个空行，补丁也必须保留这两个空行
   - 如果原代码在类方法之间有一个空行，补丁也必须保留这一个空行
3. **行尾处理**：
   - 如果原代码行尾没有空格，补丁也不应添加行尾空格
   - 如果原代码使用特定的行尾注释风格，补丁也应保持该风格

## 补丁示例
```
{ot("PATCH")}
File: src/utils/math.py
Reason: 修复除零错误，增加参数验证以提高函数健壮性
def safe_divide(a, b):
    # 添加参数验证
    if b == 0:
        raise ValueError("除数不能为零")
    return a / b
# 现有代码 ...
def add(a, b):
    return a + b
{ct("PATCH")}
```

## 最佳实践
- 每个补丁专注于单一职责的修改
- 避免包含过多无关代码
- 确保修改理由清晰明确，便于理解变更目的
- 保持代码风格一致性，遵循项目现有的编码规范
- 在修改前仔细分析原代码的格式风格，确保补丁与之完全兼容
- 绝不提供完整文件内容，除非是新建文件
- 每个文件的修改是独立的，不能出现“参照xxx文件的修改”这样的描述
- 不要出现未实现的代码，如：TODO
"""
    
def _has_patch_block(patch_str: str) -> bool:
    """判断是否存在补丁块"""
    return re.search(ot("PATCH")+r'\n?(.*?)\n?' +
                     ct("PATCH"), patch_str, re.DOTALL) is not None


def _parse_patch(patch_str: str) -> Tuple[Dict[str, str], str]:
    """解析新的上下文补丁格式"""
    result = {}
    patches = re.findall(ot("PATCH")+r'\n?(.*?)\n?' +
                         ct("PATCH"), patch_str, re.DOTALL)
    if patches:
        for patch in patches:
            first_line = patch.splitlines()[0]
            sm = re.match(r'^File:\s*(.+)$', first_line)
            if not sm:
                return ({}, f"""无效的补丁格式，正确格式应该为：
{ot("PATCH")}
File: [文件路径]
Reason: [修改原因]
[代码修改说明，不用输出完整的代码，仅输出修改的片段即可]
{ct("PATCH")}""")
            filepath = os.path.abspath(sm.group(1).strip())
            if filepath not in result:
                result[filepath] = patch
            else:
                result[filepath] += "\n\n" + patch
    return result, ""


def apply_patch(output_str: str, agent: Any) -> str:
    """Apply patches to files"""
    with yaspin(text="正在应用补丁...", color="cyan") as spinner:
        try:
            patches, error_msg = _parse_patch(output_str)
            if error_msg:
                spinner.text = "补丁格式错误"
                spinner.fail("❌")
                return error_msg
        except Exception as e:
            spinner.text = "解析补丁失败"
            spinner.fail("❌")
            return f"解析补丁失败: {str(e)}"

        # 获取当前提交hash作为起始点
        spinner.text = "开始获取当前提交hash..."
        start_hash = get_latest_commit_hash()
        spinner.write("✅ 当前提交hash获取完成")

        not_read_file = [
            f for f in patches.keys() 
            if not has_read_file(f) 
            and os.path.exists(f) 
            and os.path.getsize(f) > 0
        ]
        if not_read_file:
            spinner.text=f"以下文件未读取: {not_read_file}，应用补丁存在风险，将先读取文件后再生成补丁"
            spinner.fail("❌")
            return f"以下文件未读取: {not_read_file}，应用补丁存在风险，请先读取文件后再生成补丁"

        # 检查是否有文件在Git仓库外
        in_git_repo = True
        for filepath in patches.keys():
            if not _is_file_in_git_repo(filepath):
                in_git_repo = False
                break

        # 按文件逐个处理
        for filepath, patch_content in patches.items():
            try:
                spinner.text = f"正在处理文件: {filepath}"
                if not os.path.exists(filepath):
                    # 新建文件
                    spinner.text = "文件不存在，正在创建文件..."
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    open(filepath, 'w', encoding='utf-8').close()
                    spinner.write("✅ 文件创建完成")
                    add_read_file_record(filepath)
                with spinner.hidden():
                    while not handle_code_operation(filepath, patch_content):
                        if user_confirm("补丁应用失败，是否重试？", default=True):
                            pass
                        else:
                            raise Exception("补丁应用失败")
                spinner.write(f"✅ 文件 {filepath} 处理完成")
            except Exception as e:
                spinner.text = f"文件 {filepath} 处理失败: {str(e)}, 回滚文件"
                revert_file(filepath)  # 回滚单个文件
                spinner.write(f"✅ 文件 {filepath} 回滚完成")

        final_ret = ""
        if in_git_repo:
            diff = get_diff()
            if diff:
                PrettyOutput.print(diff, OutputType.CODE, lang="diff")
                with spinner.hidden():
                    commited = handle_commit_workflow()
                if commited:
                    # 获取提交信息
                    end_hash = get_latest_commit_hash()
                    commits = get_commits_between(start_hash, end_hash)

                    # 添加提交信息到final_ret
                    if commits:
                        final_ret += "✅ 补丁已应用\n"
                        final_ret += "# 提交信息:\n"
                        for commit_hash, commit_message in commits:
                            final_ret += f"- {commit_hash[:7]}: {commit_message}\n"

                        final_ret += f"# 应用补丁:\n```diff\n{diff}\n```"

                        # 修改后的提示逻辑
                        addon_prompt = f"如果用户的需求未完成，请继续生成补丁，如果已经完成，请终止，不要输出新的 {ot('PATCH')}，不要实现任何超出用户需求外的内容\n"
                        addon_prompt += "如果有任何信息不明确，调用工具获取信息\n"
                        addon_prompt += "每次响应必须且只能包含一个操作\n"

                        agent.set_addon_prompt(addon_prompt)

                    else:
                        final_ret += "✅ 补丁已应用（没有新的提交）"
                else:
                    final_ret += "❌ 补丁应用被拒绝\n"
                    final_ret += f"# 补丁预览:\n```diff\n{diff}\n```"
            else:
                commited = False
                final_ret += "❌ 没有要提交的更改\n"
        else:
            # 对于Git仓库外的文件，直接返回成功
            final_ret += "✅ 补丁已应用（文件不在Git仓库中）"
            commited = True
        # 用户确认最终结果
        with spinner.hidden():
            if commited:
                return final_ret
            PrettyOutput.print(final_ret, OutputType.USER, lang="markdown")
            if not is_confirm_before_apply_patch() or user_confirm("是否使用此回复？", default=True):
                return final_ret
            custom_reply = get_multiline_input("请输入自定义回复")
            if not custom_reply.strip():  # 如果自定义回复为空，返回空字符串
                return ""
            agent.set_addon_prompt(custom_reply)
            return final_ret


def _is_file_in_git_repo(filepath: str) -> bool:
    """检查文件是否在当前Git仓库中"""
    import subprocess
    try:
        # 获取Git仓库根目录
        repo_root = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True
        ).stdout.strip()
        
        # 检查文件路径是否在仓库根目录下
        return os.path.abspath(filepath).startswith(os.path.abspath(repo_root))
    except:
        return False

def revert_file(filepath: str):
    """增强版git恢复，处理新文件"""
    import subprocess
    try:
        # 检查文件是否在版本控制中
        result = subprocess.run(
            ['git', 'ls-files', '--error-unmatch', filepath],
            stderr=subprocess.PIPE,
            text=False  # 禁用自动文本解码
        )
        if result.returncode == 0:
            subprocess.run(['git', 'checkout', 'HEAD',
                           '--', filepath], check=True)
        else:
            if os.path.exists(filepath):
                os.remove(filepath)
        subprocess.run(['git', 'clean', '-f', '--', filepath], check=True)
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)
        PrettyOutput.print(f"恢复文件失败: {error_msg}", OutputType.ERROR)
# 修改后的恢复函数


def revert_change():
    """恢复所有未提交的修改到HEAD状态"""
    import subprocess
    try:
        # 检查是否为空仓库
        head_check = subprocess.run(
            ['git', 'rev-parse', '--verify', 'HEAD'],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE
        )
        if head_check.returncode == 0:
            subprocess.run(['git', 'reset', '--hard', 'HEAD'], check=True)
        subprocess.run(['git', 'clean', '-fd'], check=True)
    except subprocess.CalledProcessError as e:
        return f"恢复更改失败: {str(e)}"
# 修改后的获取差异函数


def get_diff() -> str:
    """使用git获取暂存区差异"""
    import subprocess
    
    # 初始化状态
    need_reset = False
    
    try:
        # 暂存所有修改
        subprocess.run(['git', 'add', '.'], check=True)
        need_reset = True
        
        # 获取差异
        result = subprocess.run(
            ['git', 'diff', '--cached'],
            capture_output=True,
            text=False,
            check=True
        )
        
        # 解码输出
        try:
            ret = result.stdout.decode('utf-8')
        except UnicodeDecodeError:
            ret = result.stdout.decode('utf-8', errors='replace')
        
        # 重置暂存区
        subprocess.run(['git', "reset", "--mixed"], check=False)
        return ret
        
    except subprocess.CalledProcessError as e:
        if need_reset:
            subprocess.run(['git', "reset", "--mixed"], check=False)
        return f"获取差异失败: {str(e)}"
    except Exception as e:
        if need_reset:
            subprocess.run(['git', "reset", "--mixed"], check=False)
        return f"发生意外错误: {str(e)}"


def handle_commit_workflow() -> bool:
    """Handle the git commit workflow and return the commit details.

    Returns:
        bool: 提交是否成功
    """
    if is_confirm_before_apply_patch() and not user_confirm("是否要提交代码？", default=True):
        revert_change()
        return False
    
    import subprocess
    try:
        # 获取当前分支的提交总数
        commit_count = subprocess.run(
            ['git', 'rev-list', '--count', 'HEAD'],
            capture_output=True,
            text=True
        )
        if commit_count.returncode != 0:
            return False
            
        commit_count = int(commit_count.stdout.strip())
        
        # 暂存所有修改
        subprocess.run(['git', 'add', '.'], check=True)
        
        # 提交变更
        subprocess.run(
            ['git', 'commit', '-m', f'CheckPoint #{commit_count + 1}'], 
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        return False


def handle_code_operation(filepath: str, patch_content: str) -> bool:
    """处理代码操作"""
    if get_file_line_count(filepath) < 5:
        return handle_small_code_operation(filepath, patch_content)
    else:
        retry_count = 5
        while retry_count > 0:
            retry_count -= 1
            if handle_large_code_operation(filepath, patch_content, PlatformRegistry().get_normal_platform() if retry_count > 2 else PlatformRegistry().get_thinking_platform()):
                return True
        return handle_small_code_operation(filepath, patch_content)


def handle_small_code_operation(filepath: str, patch_content: str) -> bool:
    """处理基于上下文的代码片段"""
    with yaspin(text=f"正在修改文件 {filepath}...", color="cyan") as spinner:
        try:
            model = PlatformRegistry().get_normal_platform()
            file_content = FileOperationTool().execute({"operation":"read", "files":[{"path":filepath}]})["stdout"]

            model.set_suppress_output(False)

            prompt = f"""
# 代码合并专家指南

## 任务描述
你是一位精确的代码审查与合并专家，需要将补丁内容与原始代码智能合并。

### 补丁内容
```
{patch_content}
```

## 合并要求
1. **精确性**：严格按照补丁的意图修改代码
2. **完整性**：确保所有需要的更改都被应用
3. **一致性**：严格保留原始代码的格式、空行和缩进风格
4. **上下文保留**：保持未修改部分的代码完全不变

## 输出格式规范
- 仅在{ot("MERGED_CODE")}标签内输出合并后的完整代码
- 每次最多输出300行代码
- 不要使用markdown代码块（```）或反引号，除非修改的是markdown文件
- 除了合并后的代码，不要输出任何其他文本
- 所有代码输出完成后，输出{ot("!!!FINISHED!!!")}标记

## 输出模板
{ot("MERGED_CODE")}
[合并后的完整代码，包括所有空行和缩进]
{ct("MERGED_CODE")}

# 原始代码
{file_content}
"""

            count = 30
            start_line = -1
            end_line = -1
            code = []
            finished = False
            while count > 0:
                count -= 1
                with spinner.hidden():
                    response = model.chat_until_success(prompt).splitlines()
                try:
                    start_line = response.index(ot("MERGED_CODE")) + 1
                    try:
                        end_line = response.index(ct("MERGED_CODE"))
                        code = response[start_line:end_line]
                    except:
                        pass
                except:
                    pass

                try:
                    response.index(ot("!!!FINISHED!!!"))
                    finished = True
                    break
                except:
                    prompt += f"""
# 继续输出

## 说明
请继续输出接下来的300行代码

## 要求
- 严格保留原始代码的格式、空行和缩进
- 仅在{ot("MERGED_CODE")}块中包含实际代码内容
- 不要使用markdown代码块（```）或反引号
- 除了合并后的代码，不要输出任何其他文本
- 所有代码输出完成后，输出{ot("!!!FINISHED!!!")}标记
"""
                    pass
            if not finished:
                spinner.text = "生成代码失败"
                spinner.fail("❌")
                return False
            # 写入合并后的代码
            spinner.text = "写入合并后的代码..."
            with open(filepath, 'w', encoding='utf-8', errors="ignore") as f:
                f.write("\n".join(code)+"\n")
            spinner.write("✅ 合并后的代码写入完成")
            spinner.text = "代码修改完成"
            spinner.ok("✅")
            return True
        except Exception as e:
            spinner.text = "代码修改失败"
            spinner.fail("❌")
            return False



def handle_large_code_operation(filepath: str, patch_content: str, model: BasePlatform) -> bool:
    """处理大型代码文件的补丁操作，使用差异化补丁格式"""
    with yaspin(text=f"正在处理文件 {filepath}...", color="cyan") as spinner:
        try:
            file_content = FileOperationTool().execute({"operation":"read", "files":[{"path":filepath}]})["stdout"]
            need_upload_file = is_context_overflow(file_content)
            upload_success = False
            # 读取原始文件内容
            with spinner.hidden():  
                if need_upload_file and model.upload_files([filepath]):
                    upload_success = True


            model.set_suppress_output(False)

            main_prompt = f"""
# 代码补丁生成专家指南

## 任务描述
你是一位精确的代码补丁生成专家，需要根据补丁描述生成精确的代码差异。

### 补丁内容
```
{patch_content}
```

## 补丁生成要求
1. **精确性**：严格按照补丁的意图修改代码
2. **格式一致性**：严格保持原始代码的格式风格
   - 缩进方式（空格或制表符）必须与原代码保持一致
   - 空行数量和位置必须与原代码风格匹配
   - 行尾空格处理必须与原代码一致
3. **最小化修改**：只修改必要的代码部分，保持其他部分不变
4. **上下文完整性**：提供足够的上下文，确保补丁能准确应用

## 输出格式规范
- 使用{ot("DIFF")}块包围每个需要修改的代码段
- 每个{ot("DIFF")}块必须包含SEARCH部分和REPLACE部分
- SEARCH部分是需要查找的原始代码
- REPLACE部分是替换后的新代码
- 确保SEARCH部分能在原文件中**唯一匹配**
- 如果修改较大，可以使用多个{ot("DIFF")}块

## 输出模板
{ot("DIFF")}
>>>>>> SEARCH
[需要查找的原始代码，包含足够上下文，避免出现可匹配多处的情况]
{'='*5}
[替换后的新代码]
<<<<<< REPLACE
{ct("DIFF")}

{ot("DIFF")}
>>>>>> SEARCH
[另一处需要查找的原始代码，包含足够上下文，避免出现可匹配多处的情况]
{'='*5}
[另一处替换后的新代码]
<<<<<< REPLACE
{ct("DIFF")}
"""
            
            for _ in range(3):
                file_prompt = ""
                if not need_upload_file:
                    file_prompt = f"""
    # 原始代码
    {file_content}
    """
                    with spinner.hidden():
                        response = model.chat_until_success(main_prompt + file_prompt)
                else:
                    if upload_success:
                        with spinner.hidden():
                            response = model.chat_until_success(main_prompt)
                    else:
                        with spinner.hidden():
                            response = model.chat_big_content(file_content, main_prompt)

                # 解析差异化补丁
                diff_blocks = re.finditer(ot("DIFF")+r'\s*>{4,} SEARCH\n?(.*?)\n?={4,}\n?(.*?)\s*<{4,} REPLACE\n?'+ct("DIFF"),
                                        response, re.DOTALL)

                # 读取原始文件内容
                with open(filepath, 'r', encoding='utf-8', errors="ignore") as f:
                    file_content = f.read()

                # 应用所有差异化补丁
                modified_content = file_content
                patch_count = 0
                success = True
                for match in diff_blocks:
                    search_text = match.group(1).strip()
                    replace_text = match.group(2).strip()
                    patch_count += 1
                    # 检查搜索文本是否存在于文件中
                    if search_text in modified_content:
                        # 如果有多处，报错
                        if modified_content.count(search_text) > 1:
                            spinner.write(f"❌ 补丁 #{patch_count} 应用失败：找到多个匹配的代码段")
                            success = False
                            break
                        # 应用替换
                        modified_content = modified_content.replace(
                            search_text, replace_text)
                        spinner.write(f"✅ 补丁 #{patch_count} 应用成功")
                    else:
                        spinner.write(f"❌ 补丁 #{patch_count} 应用失败：无法找到匹配的代码段")
                        success = False
                        break
                if not success:
                    revert_file(filepath)
                    continue

                # 写入修改后的内容
                with open(filepath, 'w', encoding='utf-8', errors="ignore") as f:
                    f.write(modified_content)

                spinner.text = f"文件 {filepath} 修改完成，应用了 {patch_count} 个补丁"
                spinner.ok("✅")
                return True
            spinner.text = f"文件 {filepath} 修改失败"
            spinner.fail("❌")
            return False

        except Exception as e:
            spinner.text = f"文件修改失败: {str(e)}"
            spinner.fail("❌")
            return False
