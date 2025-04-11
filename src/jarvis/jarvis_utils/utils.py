import os
import time
import hashlib
from pathlib import Path
from typing import Union, List, Dict, Any, Callable, cast
from bs4 import BeautifulSoup, Tag
from jarvis.jarvis_utils.config import get_max_input_token_count
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

    # 检查~/.jarvis目录是否存在
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
def while_true(func: Callable[[], bool], sleep_time: float = 0.1) -> Any:
    """循环执行函数直到返回True"""
    while True:
        ret = func()
        if ret:
            break
        PrettyOutput.print(f"执行失败, 等待 {sleep_time}s...", OutputType.WARNING)
        time.sleep(sleep_time)
    return ret
def get_file_md5(filepath: str)->str:
    """计算文件内容的MD5哈希值

    参数:
        filepath: 要计算哈希的文件路径

    返回:
        str: 文件内容的MD5哈希值
    """
    return hashlib.md5(open(filepath, "rb").read(100*1024*1024)).hexdigest()
def user_confirm(tip: str, default: bool = True) -> bool:
    """提示用户确认是/否问题

    参数:
        tip: 显示给用户的消息
        default: 用户直接回车时的默认响应

    返回:
        bool: 用户确认返回True，否则返回False
    """
    suffix = "[Y/n]" if default else "[y/N]"
    ret = get_single_line_input(f"{tip} {suffix}: ")
    return default if ret == "" else ret.lower() == "y"

def get_file_line_count(filename: str) -> int:
    """计算文件中的行数

    参数:
        filename: 要计算行数的文件路径

    返回:
        int: 文件中的行数，如果文件无法读取则返回0
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
    max_input_token_count = get_max_input_token_count()
    threshold = max_input_token_count * 0.8
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

def extract_interactive_elements(html_content: str) -> List[Dict[str, Any]]:
    """从HTML内容中提取所有交互元素及其属性
    
    参数:
        html_content: 要解析的HTML内容
        
    返回:
        包含元素属性的字典列表:
        - xpath: 元素的XPath
        - tag: HTML标签名
        - text: 文本内容
        - is_clickable: 元素是否可点击
        - is_input: 元素是否是输入字段
        - is_select: 元素是否是下拉选择框
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    interactive_elements = []
    
    # Define interactive tags
    clickable_tags = {'a', 'button', 'input', 'select', 'textarea'}
    input_tags = {'input', 'textarea', 'select'}
    
    def get_xpath(element: Tag) -> str:
        """Generate XPath for an element"""
        components = []
        current = element
        
        while current and current.name:
            siblings = current.find_previous_siblings(current.name)
            index = len(siblings) + 1
            components.append(f"{current.name}[{index}]")
            current = current.parent
            
        return "/".join(reversed(components))
    
    def process_element(element: Tag) -> None:
        """Process a single element and add it to interactive_elements if it's interactive"""
        tag_name = element.name.lower()
        
        # Skip non-interactive elements
        if tag_name not in clickable_tags and not element.find_parent(clickable_tags):
            return
            
        # Get element properties
        element_info = {
            'xpath': get_xpath(element),
            'tag': tag_name,
            'text': element.get_text().strip(),
            'is_clickable': tag_name in clickable_tags or bool(element.find_parent('a')) or bool(element.find_parent('button')),
            'is_input': tag_name in input_tags,
            'is_select': tag_name == 'select'
        }
        
        # Add additional properties for input elements
        if element_info['is_input']:
            element_info['input_type'] = element.get('type', 'text')
            element_info['name'] = element.get('name', '')
            element_info['value'] = element.get('value', '')
            
        # Add options for select elements
        if element_info['is_select']:
            element_info['options'] = [
                {'value': opt.get('value', ''), 'text': opt.get_text().strip()}
                for opt in element.find_all('option')
                if isinstance(opt, Tag)
            ]
            
        interactive_elements.append(element_info)
    
    # Process all elements
    for element in soup.find_all():
        if isinstance(element, Tag):
            process_element(element)
    
    return interactive_elements

def extract_display_elements(html_content: str) -> List[Dict[str, Any]]:
    """从HTML内容中提取所有显示元素及其属性
    
    参数:
        html_content: 要解析的HTML内容
        
    返回:
        包含元素属性的字典列表:
        - xpath: 元素的XPath
        - tag: HTML标签名
        - text: 文本内容
        - heading_level: 如果是标题元素则返回标题级别(1-6)
        - is_list: 元素是否是列表
        - is_list_item: 元素是否是列表项
        - is_table: 元素是否是表格
        - is_table_cell: 元素是否是表格单元格
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    display_elements = []
    
    # Define display tags
    display_tags = {
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',  # Headings
        'p', 'div', 'span',                   # Text containers
        'ul', 'ol', 'li',                     # Lists
        'table', 'tr', 'td', 'th',            # Tables
        'article', 'section', 'main',         # Content sections
        'header', 'footer', 'nav',            # Layout sections
        'aside', 'figure', 'figcaption'       # Side content
    }
    
    # Define interactive tags to exclude
    interactive_tags = {'a', 'button', 'input', 'select', 'textarea', 'form'}
    
    def get_xpath(element: Tag) -> str:
        """Generate XPath for an element"""
        components = []
        current = element
        
        while current and current.name:
            siblings = current.find_previous_siblings(current.name)
            index = len(siblings) + 1
            components.append(f"{current.name}[{index}]")
            current = current.parent
            
        return "/".join(reversed(components))
    
    def process_element(element: Tag) -> None:
        """Process a single element and add it to display_elements if it's a display element"""
        tag_name = element.name.lower()
        
        # Skip non-display elements and interactive elements
        if tag_name not in display_tags or element.find_parent(interactive_tags):
            return
            
        # Get text content
        text = element.get_text().strip()
        if not text:  # Skip empty elements
            return
            
        # Get element properties
        element_info = {
            'xpath': get_xpath(element),
            'tag': tag_name,
            'text': text,
            'heading_level': int(tag_name[1]) if tag_name.startswith('h') and len(tag_name) == 2 else None,
            'is_list': tag_name in {'ul', 'ol'},
            'is_list_item': tag_name == 'li',
            'is_table': tag_name == 'table',
            'is_table_cell': tag_name in {'td', 'th'}
        }
        
        # Add list-specific properties
        if element_info['is_list']:
            element_info['list_items'] = [
                {'text': li.get_text().strip()}
                for li in element.find_all('li')
                if isinstance(li, Tag)
            ]
            
        # Add table-specific properties
        if element_info['is_table']:
            element_info['table_rows'] = [
                {
                    'cells': [
                        {'text': cell.get_text().strip(), 'is_header': cell.name == 'th'}
                        for cell in row.find_all(['td', 'th'])
                        if isinstance(cell, Tag)
                    ]
                }
                for row in element.find_all('tr')
                if isinstance(row, Tag)
            ]
            
        display_elements.append(element_info)
    
    # Process all elements
    for element in soup.find_all():
        if isinstance(element, Tag):
            process_element(element)
    
    return display_elements
