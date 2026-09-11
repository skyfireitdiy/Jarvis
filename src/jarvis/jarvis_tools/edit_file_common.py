"""文件编辑工具公共逻辑：编码检测、备份回滚、引号归一化匹配、diff 预览等。

本模块仅提供可复用的函数，不定义工具类（避免被工具注册表误加载）。
"""

import os
import shutil
import sys
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_utils.config import (
    detect_file_encoding,
    get_default_encoding,
    read_text_file,
    save_exception,
)


def get_preferred_encodings() -> List[str]:
    """获取工具级优先编码顺序。Windows 优先 gbk，其他平台优先 utf-8。"""
    if sys.platform == "win32":
        return ["gbk", "utf-8"]
    return ["utf-8", "gbk"]


def read_text_with_preferred_encoding(
    file_path: str,
) -> Tuple[str, Optional[str]]:
    """使用 detect_file_encoding 直接识别编码并读取文本文件。"""
    detected_encoding = detect_file_encoding(file_path)
    if detected_encoding:
        try:
            content = read_text_file(
                file_path,
                encoding=detected_encoding,
                detect_encoding=False,
                errors="strict",
            )
            return content, detected_encoding
        except (UnicodeDecodeError, LookupError):
            pass

    # 回退到默认读取方式
    content = read_text_file(file_path)
    return content, detected_encoding


def read_file_with_backup(
    file_path: str,
) -> Tuple[str, Optional[str], Optional[str]]:
    """读取文件并创建备份

    Args:
        file_path: 文件路径

    Returns:
        (文件内容, 备份文件路径或None, 检测到的编码或None)
    """
    abs_path = os.path.abspath(file_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    file_content = ""
    backup_path = None
    detected_encoding = None
    if os.path.exists(abs_path):
        file_content, detected_encoding = read_text_with_preferred_encoding(abs_path)
        # 创建备份文件
        backup_path = abs_path + ".bak"
        try:
            shutil.copy2(abs_path, backup_path)
        except Exception:
            # 备份失败不影响主流程
            backup_path = None

    return file_content, backup_path, detected_encoding


def write_file_with_rollback(
    abs_path: str,
    content: str,
    backup_path: Optional[str],
    encoding: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """写入文件，失败时回滚

    Args:
        abs_path: 文件绝对路径
        content: 要写入的内容
        backup_path: 备份文件路径或None
        encoding: 指定编码，若为None则自动检测

    Returns:
        (是否成功, 错误信息或None)
    """
    enc = encoding or get_default_encoding()
    try:
        with open(abs_path, "w", encoding=enc, errors="replace") as f:
            f.write(content)
        return (True, None)
    except Exception as write_error:
        # 写入失败，尝试回滚
        if backup_path and os.path.exists(backup_path):
            try:
                shutil.copy2(backup_path, abs_path)
                os.remove(backup_path)
            except Exception as e:
                save_exception(
                    e,
                    module="jarvis_tools.edit_file",
                    function="write_file_with_rollback",
                )
                pass
        error_msg = f"文件写入失败: {str(write_error)}"
        return (False, error_msg)


def normalize_line_endings(text: str) -> str:
    """统一换行符，便于进行保守的等价匹配。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_quotes(text: str) -> str:
    """归一化常见引号风格，便于在文件中定位实际匹配文本。"""
    return text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")


def find_actual_search_text(content: str, search_text: str) -> Optional[str]:
    """查找文件中的实际匹配文本。

    先尝试精确匹配；若失败，再尝试基于换行和引号归一化后的定位，
    并从原始文件内容中截取实际匹配片段。
    """
    if not search_text:
        return search_text

    if search_text in content:
        return search_text

    normalized_content = normalize_quotes(normalize_line_endings(content))
    normalized_search = normalize_quotes(normalize_line_endings(search_text))
    search_index = normalized_content.find(normalized_search)
    if search_index == -1:
        return None
    return content[search_index : search_index + len(search_text)]


def is_opening_quote_context(characters: List[str], index: int) -> bool:
    """判断当前位置的引号是否处于开引号上下文。"""
    if index == 0:
        return True
    previous_character = characters[index - 1]
    return previous_character in {" ", "\t", "\n", "\r", "(", "[", "{", "—", "–"}


def apply_curly_double_quotes(text: str) -> str:
    """将直双引号转换为弯双引号。"""
    characters = list(text)
    result: List[str] = []
    for index, character in enumerate(characters):
        if character == '"':
            result.append("“" if is_opening_quote_context(characters, index) else "”")
        else:
            result.append(character)
    return "".join(result)


def apply_curly_single_quotes(text: str) -> str:
    """将直单引号转换为弯单引号，同时保留常见缩写中的撇号。"""
    characters = list(text)
    result: List[str] = []
    for index, character in enumerate(characters):
        if character != "'":
            result.append(character)
            continue

        previous_character = characters[index - 1] if index > 0 else ""
        next_character = characters[index + 1] if index < len(characters) - 1 else ""
        if previous_character.isalpha() and next_character.isalpha():
            result.append("’")
            continue

        result.append("‘" if is_opening_quote_context(characters, index) else "’")
    return "".join(result)


def preserve_quote_style(
    search_text: str, actual_search_text: str, replace_text: str
) -> str:
    """当 search 因引号归一化匹配到实际文本时，尽量保持实际文本中的弯引号风格。"""
    if search_text == actual_search_text:
        return replace_text

    has_curly_double_quotes = "“" in actual_search_text or "”" in actual_search_text
    has_curly_single_quotes = "‘" in actual_search_text or "’" in actual_search_text

    styled_replace_text = replace_text
    if has_curly_double_quotes:
        styled_replace_text = apply_curly_double_quotes(styled_replace_text)
    if has_curly_single_quotes:
        styled_replace_text = apply_curly_single_quotes(styled_replace_text)
    return styled_replace_text


def count_matches(content: str, search_text: str) -> int:
    """统计文本在内容中的匹配次数

    Args:
        content: 文件内容
        search_text: 要搜索的文本

    Returns:
        匹配次数
    """
    if not search_text:
        return 0
    return content.count(search_text)


def is_file_in_workspace_subdir(file_path: str) -> bool:
    """检查文件是否在当前工作目录的子级目录下

    Args:
        file_path: 文件路径（可以是绝对路径或相对路径）

    Returns:
        True 如果文件在当前工作目录的子级目录下，False 否则
    """
    try:
        abs_file_path = os.path.abspath(file_path)
        abs_workspace_path = os.path.abspath(os.getcwd())

        # 检查文件路径是否以工作目录路径开头
        # 使用 os.path.commonpath 来正确处理路径
        try:
            common_path = os.path.commonpath([abs_file_path, abs_workspace_path])
            # 如果公共路径等于工作目录路径，说明文件在工作目录或其子目录下
            return os.path.abspath(common_path) == abs_workspace_path
        except ValueError:
            # 如果路径不在同一驱动器上（Windows），commonpath 会抛出 ValueError
            return False
    except Exception:
        # 如果出现任何异常，默认返回 False
        return False


def generate_diff_preview(
    original_content: str,
    modified_content: str,
    file_path: str,
) -> str:
    """生成修改后的预览diff

    Args:
        original_content: 原始文件内容
        modified_content: 修改后的文件内容
        file_path: 文件路径

    Returns:
        预览diff字符串
    """
    import difflib

    # 生成统一的diff格式
    original_lines = original_content.splitlines(keepends=True)
    modified_lines = modified_content.splitlines(keepends=True)

    # 使用difflib生成统一的diff
    diff = list(
        difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )
    )

    diff_preview = "".join(diff)
    return diff_preview
