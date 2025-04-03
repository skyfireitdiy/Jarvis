"""
方法论管理模块
该模块提供了加载和搜索方法论的实用工具。
包含以下功能：
- 加载和处理方法论数据
- 生成方法论临时文件
- 上传方法论文件到大模型
"""
import os
import json
import tempfile
from typing import Dict, Optional

from jarvis.jarvis_utils.config import INPUT_WINDOW_REVERSE_SIZE, get_max_input_token_count
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.output import PrettyOutput, OutputType
from jarvis.jarvis_platform.registry import PlatformRegistry

def _get_methodology_directory() -> str:
    """
    获取方法论目录路径，如果不存在则创建

    返回：
        str: 方法论目录的路径
    """
    methodology_dir = os.path.expanduser("~/.jarvis/methodologies")
    if not os.path.exists(methodology_dir):
        try:
            os.makedirs(methodology_dir, exist_ok=True)
        except Exception as e:
            PrettyOutput.print(f"创建方法论目录失败: {str(e)}", OutputType.ERROR)
    return methodology_dir

def _load_all_methodologies() -> Dict[str, str]:
    """
    加载所有方法论文件

    返回：
        Dict[str, str]: 方法论字典，键为问题类型，值为方法论内容
    """
    methodology_dir = _get_methodology_directory()
    all_methodologies = {}

    if not os.path.exists(methodology_dir):
        return all_methodologies

    import glob
    for filepath in glob.glob(os.path.join(methodology_dir, "*.json")):
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                methodology = json.load(f)
                problem_type = methodology.get("problem_type", "")
                content = methodology.get("content", "")
                if problem_type and content:
                    all_methodologies[problem_type] = content
        except Exception as e:
            filename = os.path.basename(filepath)
            PrettyOutput.print(f"加载方法论文件 {filename} 失败: {str(e)}", OutputType.WARNING)

    return all_methodologies

def _create_methodology_temp_file(methodologies: Dict[str, str]) -> Optional[str]:
    """
    创建包含所有方法论的临时文件

    参数：
        methodologies: 方法论字典，键为问题类型，值为方法论内容

    返回：
        Optional[str]: 临时文件路径，如果创建失败则返回None
    """
    if not methodologies:
        return None
    
    try:
        # 创建临时文件
        fd, temp_path = tempfile.mkstemp(suffix='.md', prefix='methodologies_')
        os.close(fd)
        
        # 写入方法论内容
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write("# 方法论集合\n\n")
            for problem_type, content in methodologies.items():
                f.write(f"## {problem_type}\n\n")
                f.write(f"{content}\n\n")
                f.write("---\n\n")
            f.flush()
        
        return temp_path
    except Exception as e:
        PrettyOutput.print(f"创建方法论临时文件失败: {str(e)}", OutputType.ERROR)
        return None

def load_methodology(user_input: str) -> str:
    """
    加载方法论并上传到大模型。

    参数：
        user_input: 用户输入文本，用于提示大模型

    返回：
        str: 相关的方法论提示，如果未找到方法论则返回空字符串
    """
    from yaspin import yaspin

    # 获取方法论目录
    methodology_dir = _get_methodology_directory()
    if not os.path.exists(methodology_dir):
        return ""

    try:
        # 加载所有方法论
        with yaspin(text="加载方法论文件...", color="yellow") as spinner:
            methodologies = _load_all_methodologies()
            if not methodologies:
                spinner.text = "没有找到方法论文件"
                spinner.fail("❌")
                return ""
            spinner.text = f"加载方法论文件完成 (共 {len(methodologies)} 个)"
            spinner.ok("✅")

        # 获取当前平台
        platform = PlatformRegistry().get_normal_platform()
        
        upload_result = False
        if get_context_token_count(user_input) > get_max_input_token_count() - INPUT_WINDOW_REVERSE_SIZE:
            # 创建临时文件
            with yaspin(text="创建方法论临时文件...", color="yellow") as spinner:
                temp_file_path = _create_methodology_temp_file(methodologies)
                if not temp_file_path:
                    spinner.text = "创建方法论临时文件失败"
                    spinner.fail("❌")
                    return ""
                spinner.text = f"创建方法论临时文件完成: {temp_file_path}"
                spinner.ok("✅")
            if platform.upload_files([temp_file_path]):
                upload_result = True
            
            spinner.text = "上传方法论文件成功"
            spinner.ok("✅")
        
        platform.set_suppress_output(False)
        # 构建提示信息
        prompt = f"""根据用户需求: {user_input}

请按以下格式回复：

### 方法论步骤
1. [步骤1描述]
2. [步骤2描述]

如果没有匹配的方法论，请输出：没有历史方法论可参考
除以上要求外，不要输出任何内容
"""
        if not upload_result:
            prompt += f"""
# 方法论内容
"""
            for problem_type, content in methodologies.items():
                prompt += f"## {problem_type}\n\n{content}\n\n---\n\n"
        return platform.chat_until_success(prompt)
    
    except Exception as e:
        PrettyOutput.print(f"加载方法论失败: {str(e)}", OutputType.ERROR)
        # 清理临时文件
        if 'temp_file_path' in locals() and temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass
        return ""
    finally:
        # 确保清理临时文件
        if 'temp_file_path' in locals() and temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass
