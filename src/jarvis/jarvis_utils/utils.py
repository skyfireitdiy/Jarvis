import os
import time
import hashlib
from pathlib import Path
from typing import Union, List, Dict, Any, Callable, cast
import psutil
from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString, PageElement
from urllib.parse import urljoin
import re
from jarvis.jarvis_utils.config import get_max_token_count
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.input import get_single_line_input
from jarvis.jarvis_utils.output import PrettyOutput, OutputType
def init_env() -> None:
    """初始化环境变量从~/.jarvis/env文件

    功能：
    1. 创建不存在的.jarvis目录
    2. 加载环境变量到os.environ
    3. 处理文件读取异常
    """
    jarvis_dir = Path.home() / ".jarvis"
    env_file = jarvis_dir / "env"

    # Check if ~/.jarvis directory exists
    if not jarvis_dir.exists():
        jarvis_dir.mkdir(parents=True)
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith(("#", ";")):
                        try:
                            key, value = line.split("=", 1)
                            os.environ[key.strip()] = value.strip().strip("'").strip('"')
                        except ValueError:
                            continue
        except Exception as e:
            PrettyOutput.print(f"警告: 读取 {env_file} 失败: {e}", OutputType.WARNING)
def while_success(func: Callable[[], Any], sleep_time: float = 0.1) -> Any:
    """循环执行函数直到成功

    参数：
    func -- 要执行的函数
    sleep_time -- 每次失败后的等待时间（秒）

    返回：
    函数执行结果
    """
    while True:
        try:
            return func()
        except Exception as e:
            PrettyOutput.print(f"执行失败: {str(e)}, 等待 {sleep_time}s...", OutputType.ERROR)
            time.sleep(sleep_time)
            continue
def while_true(func: Callable[[], bool], sleep_time: float = 0.1) -> bool:
    """Loop execution function, until the function returns True"""
    while True:
        ret = func()
        if ret:
            break
        PrettyOutput.print(f"执行失败, 等待 {sleep_time}s...", OutputType.WARNING)
        time.sleep(sleep_time)
    return ret
def get_file_md5(filepath: str)->str:
    """Calculate the MD5 hash of a file's content.

    Args:
        filepath: Path to the file to hash

    Returns:
        str: MD5 hash of the file's content
    """
    return hashlib.md5(open(filepath, "rb").read(100*1024*1024)).hexdigest()
def user_confirm(tip: str, default: bool = True) -> bool:
    """Prompt the user for confirmation with a yes/no question.

    Args:
        tip: The message to show to the user
        default: The default response if user hits enter

    Returns:
        bool: True if user confirmed, False otherwise
    """
    suffix = "[Y/n]" if default else "[y/N]"
    ret = get_single_line_input(f"{tip} {suffix}: ")
    return default if ret == "" else ret.lower() == "y"

def get_file_line_count(filename: str) -> int:
    """Count the number of lines in a file.

    Args:
        filename: Path to the file to count lines for

    Returns:
        int: Number of lines in the file, 0 if file cannot be read
    """
    try:
        return len(open(filename, "r", encoding="utf-8", errors="ignore").readlines())
    except Exception as e:
        return 0


def is_long_context(files: List[str]) -> bool:
    """检查文件列表是否属于长上下文

    判断标准：
    当总token数超过最大上下文长度的80%时视为长上下文

    参数：
    files -- 要检查的文件路径列表

    返回：
    布尔值表示是否属于长上下文
    """
    max_token_count = get_max_token_count()
    threshold = max_token_count * 0.8
    total_tokens = 0

    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors="ignore") as f:
                content = f.read()
                total_tokens += get_context_token_count(content)

                if total_tokens > threshold:
                    return True
        except Exception as e:
            PrettyOutput.print(f"读取文件 {file_path} 失败: {e}", OutputType.WARNING)
            continue

    return total_tokens > threshold


def ot(tag_name: str) -> str:
    """生成HTML标签开始标记

    参数：
    tag_name -- HTML标签名称

    返回：
    格式化的开始标签字符串
    """
    return f"<{tag_name}>"

def ct(tag_name: str) -> str:
    """生成HTML标签结束标记

    参数：
    tag_name -- HTML标签名称

    返回：
    格式化的结束标签字符串
    """
    return f"</{tag_name}>"


def create_soup_element(content: Union[str, Tag, List[Any]]) -> List[Union[Tag, str]]:
    """Safely create a BeautifulSoup element, ensuring it's treated as markup
    
    Args:
        content: Input content to convert to BeautifulSoup elements
    Returns:
        List of BeautifulSoup elements or strings
    """
    if isinstance(content, str):
        # Create a wrapper tag to ensure proper parsing
        soup_div = BeautifulSoup(f"<div>{content}</div>", 'html.parser').div
        if soup_div is not None:
            return [cast(Union[Tag, str], el) for el in soup_div.contents]
        return []
    elif isinstance(content, list):
        return content
    return [content]

def html_to_markdown(html_content: str, base_url: str) -> str:
    """Convert HTML to Markdown format preserving the content structure"""
    soup: BeautifulSoup = BeautifulSoup(html_content, 'html.parser')

    def process_tag(tag: Tag) -> str:
        """Helper function to process individual tags"""
        if tag.name == 'a':
            href = str(tag.get('href', ''))
            text = tag.get_text().strip()
            if text and href:
                if href.startswith('/') and not href.startswith('//'):
                    href = urljoin(base_url, href)
                return f"[{text}]({href})"
        elif tag.name == 'img':
            src = str(tag.get('src', ''))
            alt = str(tag.get('alt', 'Image')).strip()
            if src.startswith('/') and not src.startswith('//'):
                src = urljoin(base_url, src)
            return f"![{alt}]({src})"
        elif tag.name == 'pre':
            return f"\n\n```\n{tag.get_text().strip()}\n```\n\n"
        elif tag.name == 'code':
            return f"`{tag.get_text().strip()}`"
        elif tag.name == 'br':
            return '\n'
        return tag.get_text().strip()

    # Remove unwanted elements
    for element in soup(['script', 'style', 'meta', 'noscript', 'head']):
        element.decompose()

    # Process all supported tags
    for tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'a', 'img', 'pre', 'code', 'br']:
        for tag in soup.find_all(tag_name):
            if isinstance(tag, Tag):
                processed = process_tag(tag)
                if processed:
                    # 直接创建新的Tag元素而不是使用字符串
                    new_tag = soup.new_tag("div")
                    new_tag.string = processed
                    tag.replace_with(new_tag)

    # Get the full text
    markdown_text = str(soup.get_text())

    # Clean up extra whitespace and line breaks
    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)
    markdown_text = re.sub(r'\s{2,}', ' ', markdown_text)

    # Process links again (for any that might have been missed)
    link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    all_links = re.findall(link_pattern, markdown_text)

    # Add a section with all links at the end
    if all_links:
        link_section = ["", "## Links", ""]
        seen_links = set()
        for text, href in all_links:
            link_entry = "[" + text + "](" + href + ")"
            if link_entry not in seen_links:
                link_section.append(link_entry)
                seen_links.add(link_entry)

        markdown_text += "\n\n" + "\n".join(link_section)

    return markdown_text.strip()
