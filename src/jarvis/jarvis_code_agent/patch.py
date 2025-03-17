import re
from typing import Dict, Any, List, Optional, Tuple
import os

from click import Option
from yaspin import yaspin

from jarvis.jarvis_agent.output_handler import OutputHandler
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_tools.git_commiter import GitCommitTool
from jarvis.jarvis_tools.execute_shell_script import ShellScriptTool
from jarvis.jarvis_tools.file_operation import FileOperationTool
from jarvis.jarvis_tools.read_code import ReadCodeTool
from jarvis.jarvis_utils.config import is_confirm_before_apply_patch
from jarvis.jarvis_utils.git_utils import get_commits_between, get_latest_commit_hash
from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import get_file_line_count, user_confirm

class PatchOutputHandler(OutputHandler):
    def name(self) -> str:
        return "PATCH"
    def handle(self, response: str) -> Tuple[bool, Any]:
        return False, apply_patch(response)
    
    def can_handle(self, response: str) -> bool:
        if _parse_patch(response):
            return True
        return False
    
    def prompt(self) -> str:
        return """
# 代码补丁规范

## 补丁格式定义
使用<PATCH>块来精确指定代码更改：
```
<PATCH>
File: [文件路径]
Reason: [修改原因]
[上下文代码片段]
</PATCH>
```

## 核心原则
1. **上下文完整性**：代码片段必须包含足够的上下文（修改前后各3行）
2. **精准修改**：只显示需要修改的代码部分，不需要展示整个文件内容
3. **格式保留**：严格保持原始代码的缩进、空行和格式规范
4. **新旧区分**：
   - 对于新文件：提供完整的代码内容
   - 对于现有文件：保留周围未更改的代码，突出显示变更部分
5. **理由说明**：每个补丁必须包含清晰的修改理由，解释为什么需要此更改

## 补丁示例
```
<PATCH>
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
</PATCH>
```

## 最佳实践
- 每个补丁专注于单一职责的修改
- 提供足够的上下文，但避免包含过多无关代码
- 确保修改理由清晰明确，便于理解变更目的
- 保持代码风格一致性，遵循项目现有的编码规范
"""

def _parse_patch(patch_str: str) -> Dict[str, str]:
    """解析新的上下文补丁格式"""
    result = {}
    patches = re.findall(r'<PATCH>\n?(.*?)\n?</PATCH>', patch_str, re.DOTALL)
    if patches:
        for patch in patches:
            first_line = patch.splitlines()[0]
            sm = re.match(r'^File:\s*(.+)$', first_line)
            if not sm:
                PrettyOutput.print("无效的补丁格式", OutputType.WARNING)
                continue
            filepath = sm.group(1).strip()
            result[filepath] = patch
    return result

def apply_patch(output_str: str) -> str:
    """Apply patches to files"""
    with yaspin(text="正在应用补丁...", color="cyan") as spinner:
        try:
            patches = _parse_patch(output_str)
        except Exception as e:
            PrettyOutput.print(f"解析补丁失败: {str(e)}", OutputType.ERROR)
            return ""
        
        # 获取当前提交hash作为起始点
        spinner.text= "开始获取当前提交hash..."
        start_hash = get_latest_commit_hash()
        spinner.write("✅ 当前提交hash获取完成")
        
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
                with spinner.hidden():
                    handle_large_code_operation(filepath, patch_content)
                    # fileline = get_file_line_count(filepath)
                    # if fileline < 300:
                    #     handle_small_code_operation(filepath, patch_content)
                    # else:
                    #     handle_large_code_operation(filepath, patch_content)
                spinner.write(f"✅ 文件 {filepath} 处理完成")
            except Exception as e:
                spinner.text = f"文件 {filepath} 处理失败: {str(e)}, 回滚文件"
                revert_file(filepath)  # 回滚单个文件
                spinner.write(f"✅ 文件 {filepath} 回滚完成")
        
        final_ret = ""
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
                    final_ret += "提交信息:\n"
                    for commit_hash, commit_message in commits:
                        final_ret += f"- {commit_hash[:7]}: {commit_message}\n"
                    
                    final_ret += f"应用补丁:\n{diff}"
                    
                else:
                    final_ret += "✅ 补丁已应用（没有新的提交）"
            else:
                final_ret += "❌ 我不想提交代码\n"
                final_ret += "补丁预览:\n"
                final_ret += diff
        else:
            final_ret += "❌ 没有要提交的更改\n"
        # 用户确认最终结果
        PrettyOutput.print(final_ret, OutputType.USER)
        if not is_confirm_before_apply_patch() or user_confirm("是否使用此回复？", default=True):
            return final_ret
        return get_multiline_input("请输入自定义回复")

def revert_file(filepath: str):
    """增强版git恢复，处理新文件"""
    import subprocess
    try:
        # 检查文件是否在版本控制中
        result = subprocess.run(
            ['git', 'ls-files', '--error-unmatch', filepath],
            stderr=subprocess.PIPE
        )
        if result.returncode == 0:
            subprocess.run(['git', 'checkout', 'HEAD', '--', filepath], check=True)
        else:
            if os.path.exists(filepath):
                os.remove(filepath)
        subprocess.run(['git', 'clean', '-f', '--', filepath], check=True)
    except subprocess.CalledProcessError as e:
        PrettyOutput.print(f"恢复文件失败: {str(e)}", OutputType.ERROR)
# 修改后的恢复函数
def revert_change():
    import subprocess
    subprocess.run(['git', 'reset', '--hard', 'HEAD'], check=True)
    subprocess.run(['git', 'clean', '-fd'], check=True)
# 修改后的获取差异函数
def get_diff() -> str:
    """使用git获取暂存区差异"""
    import subprocess
    try:
        subprocess.run(['git', 'add', '.'], check=True)
        result = subprocess.run(
            ['git', 'diff', '--cached'],
            capture_output=True,
            text=True,
            check=True
        )
        ret = result.stdout
        subprocess.run(['git', "reset", "--soft", "HEAD"], check=True)
        return ret
    except subprocess.CalledProcessError as e:
        return f"获取差异失败: {str(e)}"

def handle_commit_workflow()->bool:
    """Handle the git commit workflow and return the commit details.
    
    Returns:
        tuple[bool, str, str]: (continue_execution, commit_id, commit_message)
    """
    if is_confirm_before_apply_patch() and not user_confirm("是否要提交代码？", default=True):
        revert_change()
        return False
    git_commiter = GitCommitTool()
    commit_result = git_commiter.execute({})
    return commit_result["success"]


def handle_small_code_operation(filepath: str, patch_content: str) -> bool:
    """处理基于上下文的代码片段"""
    with yaspin(text=f"正在修改文件 {filepath}...", color="cyan") as spinner:
        try:
            with spinner.hidden():
                old_file_content = FileOperationTool().execute({"operation": "read", "files": [{"path": filepath}]})
                if not old_file_content["success"]:
                    spinner.write("❌ 文件读取失败")
                    return False
            
            prompt = f"""
# 代码合并专家指南

## 任务描述
你是一位精确的代码审查与合并专家，需要将补丁内容与原始代码智能合并。

## 输入资料
### 原始代码
```
{old_file_content["stdout"]}
```

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
- 仅在<MERGED_CODE>标签内输出合并后的完整代码
- 每次最多输出300行代码
- 不要使用markdown代码块（```）或反引号，除非修改的是markdown文件
- 除了合并后的代码，不要输出任何其他文本
- 所有代码输出完成后，输出<!!!FINISHED!!!>标记

## 输出模板
<MERGED_CODE>
[合并后的完整代码，包括所有空行和缩进]
</MERGED_CODE>
"""
            model = PlatformRegistry().get_codegen_platform()
            model.set_suppress_output(True)
            count = 30
            start_line = -1
            end_line = -1
            code = []
            finished = False
            while count>0:
                count -= 1
                response = model.chat_until_success(prompt).splitlines()
                try:
                    start_line = response.index("<MERGED_CODE>") + 1
                    try:
                        end_line = response.index("</MERGED_CODE>")
                        code = response[start_line:end_line]
                    except:
                        pass
                except:
                    pass

                try: 
                    response.index("<!!!FINISHED!!!>")
                    finished = True
                    break
                except:
                    prompt += f"""
# 继续输出

## 说明
请继续输出接下来的300行代码

## 要求
- 严格保留原始代码的格式、空行和缩进
- 仅在<MERGED_CODE>块中包含实际代码内容
- 不要使用markdown代码块（```）或反引号
- 除了合并后的代码，不要输出任何其他文本
- 所有代码输出完成后，输出<!!!FINISHED!!!>标记
"""
                    pass
            if not finished:
                spinner.text = "生成代码失败"
                spinner.fail("❌")
                return False
            # 写入合并后的代码
            spinner.text = "写入合并后的代码..."
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("\n".join(code)+"\n")
            spinner.write("✅ 合并后的代码写入完成")
            spinner.text = "代码修改完成"
            spinner.ok("✅")
            return True
        except Exception as e:
            spinner.text = "代码修改失败"
            spinner.fail("❌")
            return False


def split_large_file(filepath: str, patch_content: str) -> Optional[List[Tuple[int,int,str]]]:      
    line_count = get_file_line_count(filepath)
    old_file_content = ReadCodeTool().execute({"files": [{"path": filepath}]})
    if not old_file_content["success"]:
        return None
    # 使用大模型切分文件
    with yaspin(text="正在切分文件...", color="cyan") as spinner:
        try:
            model = PlatformRegistry().get_codegen_platform()
            model.set_suppress_output(True)
        
            split_prompt = f"""
    # 代码文件切分任务

    ## 任务描述
    请根据补丁内容，将源文件精确切分为"修改"区块和"不修改"区块。

    ## 输入资料
    ### 源文件内容
    ```
    {old_file_content["stdout"]}
    ```

    ### 补丁内容
    ```
    {patch_content}
    ```

    ## 核心概念
    - "修改"区块：包含需要被补丁修改、添加或删除代码的区域
    - "不修改"区块：补丁不影响的代码区域

    ## 切分要求与规则
    1. **语法完整性**：按照完整的语法单元（函数、类、方法等）进行切分，严禁将语法单元切分开
       - 正确示例：完整的函数作为一个区块
       - 错误示例：函数的一部分作为一个区块
    
    2. **区块类型交替**：相邻区块必须类型不同
       - 正确示例：[修改][不修改][修改]
       - 错误示例：[修改][修改] 或 [不修改][不修改]
    
    3. **修改判定规则**：
       - 如果补丁要在某处添加新代码，则该位置之前的完整语法单元应标记为"修改"
       - 如果补丁要修改现有代码，则包含该代码的完整语法单元应标记为"修改"
       - 如果补丁要删除代码，则包含该代码的完整语法单元应标记为"修改"
    
    4. **完整覆盖**：
       - 所有区块必须连续无间隔地覆盖整个文件
       - 第一个区块必须从第1行开始
       - 最后一个区块必须到文件最后一行结束
    
    5. **合理粒度**：
       - 在保证语法完整性的前提下，尽可能细致地区分修改和非修改区域
       - 不要将没有修改的函数归入修改区块
       - 不要将需要修改的函数归入非修改区块

    ## 输出格式
    仅输出如下格式的切分结果（不要包含其他任何解释或说明）：
    <SPLIT_FILE>
    [起始行,结束行]: 修改
    [起始行,结束行]: 不修改
    [起始行,结束行]: 修改
    ...
    </SPLIT_FILE>
    """
            with spinner.hidden():
                response = model.chat_until_success(split_prompt)
            split_match = re.search(r'<SPLIT_FILE>\n(.*?)\n</SPLIT_FILE>', response, re.DOTALL)
            
            if not split_match:
                spinner.text = "文件切分失败"
                spinner.fail("❌")
                return None
            spinner.text = "文件切分完成"
            spinner.ok("✅")
        except Exception:
            spinner.text = "文件切分失败"
            spinner.fail("❌")
            return None
    
    with yaspin(text="正在验证文件切分...", color="cyan") as spinner:
        split_content = split_match.group(1).strip().splitlines()
        file_sections = []
        
        for line in split_content:
            match = re.match(r'\[(\d+),(\d+)\]:\s*(.*)', line)
            if match:
                start_line = int(match.group(1))
                end_line = int(match.group(2))
                file_sections.append((start_line, end_line, match.group(3)))
        # 第一个块的起始位置为1
        if file_sections[0][0] != 1:
            spinner.text = "第一个块的起始位置不为1"
            spinner.fail("❌")
            return None
        # 最后一个块的结束位置为文件行数
        if file_sections[-1][1] != line_count:
            spinner.text = "最后一个块的结束位置不为文件行数"
            spinner.fail("❌")
            return None
        # 所有切分的块必须连续
        for i in range(len(file_sections)):
            if i == 0:
                continue
            if file_sections[i][0] != file_sections[i-1][1]+1:
                spinner.text = "文件切分块不连续"
                spinner.fail("❌")
                return None
        spinner.text = "文件切分验证通过"
        spinner.ok("✅")
    output = ""
    for i, (start_line, end_line, reason) in enumerate(file_sections):
        output += f"### 区块 {i+1} (行 {start_line}-{end_line}): {reason}\n"
    PrettyOutput.print(output, OutputType.SYSTEM)
    return file_sections

def handle_large_code_operation(filepath: str, patch_content: str) -> bool:
    """处理大型代码文件的补丁操作"""
    file_sections = split_large_file(filepath, patch_content)
    
    if not file_sections:
        return False
    
    with yaspin(text=f"正在修改文件 {filepath}...", color="cyan") as spinner:
        try:
            # 读取原始文件内容
            old_file_content = ReadCodeTool().execute({"files": [{"path": filepath}]})
            if not old_file_content["success"]:
                spinner.text = "文件读取失败"
                spinner.fail("❌")
                return False
            
            model = PlatformRegistry().get_codegen_platform()
            model.set_suppress_output(False)
            
            sections_info = []
            for i, (start_line, end_line, reason) in enumerate(file_sections):
                sections_info.append(f"### 区块 {i+1} (行 {start_line}-{end_line}): {reason}")
            
            sections_info = "\n".join(sections_info)

            prompt = f"""
# 代码修改专家指南

## 任务描述
你是一位精确的代码修改专家，需要根据补丁内容修改特定代码区块。

## 输入资料

### 原始代码
```
{old_file_content["stdout"]}
```

### 原始代码区块信息
{sections_info}

### 补丁内容
```
{patch_content}
```

## 修改要求
1. **精确性**：严格按照补丁的意图修改代码
2. **一致性**：保持原始代码的格式、空行和缩进风格
3. **完整性**：对每个标记为"修改"的区块，提供完整的替换代码
4. **语法完整性**：确保所有修改保持语法的完整性和正确性

## 处理规则
1. 仅修改那些标记为"修改"的区块，不需要修改标记为"不修改"的区块
2. 对于修改区块，必须提供完整的替换代码，不能只提供部分修改
3. 保持原有代码的风格、命名约定和格式
4. 确保修改后的代码能够正确编译和运行

## 输出格式规范
- 使用<REPLACE>标签包围每个修改区块的替换代码
- 每个<REPLACE>块必须指定区块编号
- 不要使用markdown代码块（```）标记
- 仅输出需要修改区块的替换代码，不要输出不需要修改的区块

## 输出模板示例
<REPLACE>
section: 1
// 区块1的完整替换代码
def example() 
    # 修改后的代码...
</REPLACE>

<REPLACE>
section: 3
// 区块3的完整替换代码
class Example 
    # 修改后的代码...
</REPLACE>
"""
            # 获取所有修改后的代码
            with spinner.hidden():
                response = model.chat_until_success(prompt)

            old_code = open(filepath, 'r', encoding='utf-8').readlines()
            
            # 解析响应，提取所有替换区块
            replace_sections = []
            for p in re.finditer(r'<REPLACE>\nsection: (\d+)\n?(.*?)</REPLACE>', response, re.DOTALL):
                replace_sections.append((p.group(1), p.group(2).splitlines(keepends=True)))

            replace_sections.sort(key=lambda x: int(x[0]), reverse=True)
            # 重建文件内容
            for section_num, modified_code in replace_sections:
                start_line = file_sections[int(section_num)-1][0]
                end_line = file_sections[int(section_num)-1][1]
                old_code[start_line-1:end_line] = modified_code
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(old_code)

            spinner.text = "文件修改完成"
            spinner.ok("✅")
            return True
            
        except Exception as e:
            spinner.text = f"文件修改失败: {str(e)}"
            spinner.fail("❌")
            return False