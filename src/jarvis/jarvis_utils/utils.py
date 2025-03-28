import os
import time
import hashlib
from pathlib import Path
from typing import Dict
import psutil
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin
import re
from jarvis.jarvis_utils.config import get_max_token_count
from jarvis.jarvis_utils.embedding import get_context_token_count
from jarvis.jarvis_utils.input import get_single_line_input
from jarvis.jarvis_utils.output import PrettyOutput, OutputType
def init_env():
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
def while_success(func, sleep_time: float = 0.1):
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
def while_true(func, sleep_time: float = 0.1):
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


def is_long_context(files: list) -> bool:
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


def create_soup_element(content):
    """Safely create a BeautifulSoup element, ensuring it's treated as markup"""
    if isinstance(content, str):
        # Create a wrapper tag to ensure proper parsing
        soup_div = BeautifulSoup(f"<div>{content}</div>", 'html.parser').div
        if soup_div is not None:
            return soup_div.contents
        # Return an empty list if the div is None
        return []
    return content

def html_to_markdown(html_content: str, base_url: str) -> str:
    """Convert HTML to Markdown format preserving the content structure"""
    soup = BeautifulSoup(html_content, 'html.parser')

    # Remove unwanted elements
    for element in soup(['script', 'style', 'meta', 'noscript', 'head']):
        element.decompose()

    # Process headings
    for level in range(1, 7):
        for heading in soup.find_all(f'h{level}'):
            text = heading.get_text().strip()
            heading_md = "\n\n" + "#" * level + " " + text + "\n\n"
            new_element = create_soup_element(heading_md)
            heading.replace_with(*new_element)

    # Process paragraphs
    for p in soup.find_all('p'):
        text = p.get_text().strip()
        if text:
            new_element = create_soup_element("\n\n" + text + "\n\n")
            p.replace_with(*new_element)

    # Process unordered lists
    for ul in soup.find_all('ul'):
        items = []
        for li in ul.find_all('li', recursive=False):
            items.append("* " + li.get_text().strip())
        new_element = create_soup_element("\n\n" + "\n".join(items) + "\n\n")
        ul.replace_with(*new_element)

    # Process ordered lists
    for ol in soup.find_all('ol'):
        items = []
        for i, li in enumerate(ol.find_all('li', recursive=False), 1):
            items.append(str(i) + ". " + li.get_text().strip())
        new_element = create_soup_element("\n\n" + "\n".join(items) + "\n\n")
        ol.replace_with(*new_element)

    # Process links (first pass)
    for a in soup.find_all('a', href=True):
        try:
            href = a['href']
            text = a.get_text().strip()
            if text and href:
                # Convert relative URLs to absolute
                if href.startswith('/') and not href.startswith('//'):
                    href = urljoin(base_url, href)
                link_md = "[" + text + "](" + href + ")"
                new_element = create_soup_element(link_md)
                a.replace_with(*new_element)
        except (KeyError, AttributeError):
            continue

    # Process images
    for img in soup.find_all('img', src=True):
        try:
            src = img['src']
            alt = img.get('alt', 'Image').strip()
            # Convert relative URLs to absolute
            if src.startswith('/') and not src.startswith('//'):
                src = urljoin(base_url, src)
            img_md = "![" + alt + "](" + src + ")"
            new_element = create_soup_element(img_md)
            img.replace_with(*new_element)
        except (KeyError, AttributeError, UnboundLocalError):
            continue

    # Process code blocks
    for pre in soup.find_all('pre'):
        code = pre.get_text().strip()
        pre_md = "\n\n```\n" + code + "\n```\n\n"
        new_element = create_soup_element(pre_md)
        pre.replace_with(*new_element)

    # Process inline code
    for code in soup.find_all('code'):
        text = code.get_text().strip()
        code_md = "`" + text + "`"
        new_element = create_soup_element(code_md)
        code.replace_with(*new_element)

    # Process line breaks
    for br in soup.find_all('br'):
        new_element = create_soup_element('\n')
        br.replace_with(*new_element)

    # Get the full text
    markdown_text = soup.get_text()

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
