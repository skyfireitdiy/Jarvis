import hashlib
from pathlib import Path
import time
import os
from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import colorama
from colorama import Fore, Style as ColoramaStyle
import numpy as np
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style as PromptStyle
from prompt_toolkit.formatted_text import FormattedText
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import torch
import yaml
import faiss
from pygments.lexers import guess_lexer
from pygments.util import ClassNotFound
import psutil
from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel
from rich.box import HEAVY
from rich.text import Text
from rich.traceback import install as install_rich_traceback
from rich.syntax import Syntax
from rich.style import Style as RichStyle

from prompt_toolkit.completion import Completer, Completion, PathCompleter
from prompt_toolkit.document import Document
from fuzzywuzzy import process
from prompt_toolkit.key_binding import KeyBindings

# 初始化colorama
colorama.init()

os.environ["TOKENIZERS_PARALLELISM"] = "false"

global_agents = set()
current_agent_name = ""

# Install rich traceback handler
install_rich_traceback()

# Create console with custom theme
custom_theme = Theme({
    "INFO": "yellow",
    "WARNING": "yellow",
    "ERROR": "red",
    "SUCCESS": "green",
    "SYSTEM": "cyan",
    "CODE": "green",
    "RESULT": "blue",
    "PLANNING": "magenta",
    "PROGRESS": "white",
    "DEBUG": "blue",
    "USER": "green",
    "TOOL": "yellow",
})

console = Console(theme=custom_theme)

def make_agent_name(agent_name: str):
    if agent_name in global_agents:
        i = 1
        while f"{agent_name}_{i}" in global_agents:
            i += 1
        return f"{agent_name}_{i}"
    else:
        return agent_name

def set_agent(agent_name: str, agent: Any):
    global_agents.add(agent_name)
    global current_agent_name
    current_agent_name = agent_name

def get_agent_list():
    return "[" + str(len(global_agents)) + "]" + current_agent_name if global_agents else ""

def delete_agent(agent_name: str):
    if agent_name in global_agents:
        global_agents.remove(agent_name)
        global current_agent_name
        current_agent_name = ""

class OutputType(Enum):
    SYSTEM = "SYSTEM"      # AI assistant message
    CODE = "CODE"         # Code related
    RESULT = "RESULT"     # Tool execution result
    ERROR = "ERROR"       # Error information
    INFO = "INFO"         # System prompt
    PLANNING = "PLANNING" # Task planning
    PROGRESS = "PROGRESS" # Execution progress
    SUCCESS = "SUCCESS"   # Success information
    WARNING = "WARNING"   # Warning information
    DEBUG = "DEBUG"       # Debug information
    USER = "USER"         # User input
    TOOL = "TOOL"         # Tool call

class PrettyOutput:
    """Pretty output using rich"""
    
    # Icons for different output types
    _ICONS = {
        OutputType.SYSTEM: "🤖",    # Robot - AI assistant
        OutputType.CODE: "📝",      # Notebook - Code
        OutputType.RESULT: "✨",    # Flash - Result
        OutputType.ERROR: "❌",     # Error - Error
        OutputType.INFO: "ℹ️",      # Info - Prompt
        OutputType.PLANNING: "📋",  # Clipboard - Planning
        OutputType.PROGRESS: "⏳",  # Hourglass - Progress
        OutputType.SUCCESS: "✅",   # Checkmark - Success
        OutputType.WARNING: "⚠️",   # Warning - Warning
        OutputType.DEBUG: "🔍",     # Magnifying glass - Debug
        OutputType.USER: "👤",      # User - User
        OutputType.TOOL: "🔧",      # Wrench - Tool
    }

    # Common language mapping dictionary
    _lang_map = {
        'Python': 'python',
        'JavaScript': 'javascript',
        'TypeScript': 'typescript',
        'Java': 'java',
        'C++': 'cpp',
        'C#': 'csharp',
        'Ruby': 'ruby',
        'PHP': 'php',
        'Go': 'go',
        'Rust': 'rust',
        'Bash': 'bash',
        'HTML': 'html',
        'CSS': 'css',
        'SQL': 'sql',
        'R': 'r',
        'Kotlin': 'kotlin',
        'Swift': 'swift',
        'Scala': 'scala',
        'Perl': 'perl',
        'Lua': 'lua',
        'YAML': 'yaml',
        'JSON': 'json',
        'XML': 'xml',
        'Markdown': 'markdown',
        'Text': 'text',
        'Shell': 'bash',
        'Dockerfile': 'dockerfile',
        'Makefile': 'makefile',
        'INI': 'ini',
        'TOML': 'toml',
    }

    @staticmethod
    def _detect_language(text: str, default_lang: str = 'markdown') -> str:
        """Helper method to detect language and map it to syntax highlighting name"""
        try:
            lexer = guess_lexer(text)
            detected_lang = lexer.name
            return PrettyOutput._lang_map.get(detected_lang, default_lang)
        except ClassNotFound:
            return default_lang
        except Exception:
            return default_lang

    @staticmethod
    def _format(output_type: OutputType, timestamp: bool = True) -> Text:
        """Format output text using rich Text"""
        # Create rich Text object
        formatted = Text()
        
        # Add timestamp and agent info
        if timestamp:
            formatted.append(f"[{datetime.now().strftime('%H:%M:%S')}][{output_type.value}]", style=output_type.value)
        agent_info = get_agent_list()
        if agent_info:  # Only add brackets if there's agent info
            formatted.append(f"[{agent_info}]", style="blue")
        # Add icon
        icon = PrettyOutput._ICONS.get(output_type, "")
        formatted.append(f" {icon} ", style=output_type.value)
        
        return formatted

    @staticmethod
    def print(text: str, output_type: OutputType, timestamp: bool = True, lang: Optional[str] = None, traceback: bool = False):
        """Print formatted output using rich console with styling
        
        Args:
            text: The text content to print
            output_type: The type of output (affects styling)
            timestamp: Whether to show timestamp
            lang: Language for syntax highlighting
            traceback: Whether to show traceback for errors
        """
        
        
        # Define styles for different output types
        # Define styles for different output types
        styles = {
            OutputType.SYSTEM: RichStyle(
                color="bright_cyan", 
                bold=True, 
            ),
            OutputType.CODE: RichStyle(
                color="green", 
                bgcolor="#1a1a1a",
                frame=True
            ),
            OutputType.RESULT: RichStyle(
                color="bright_blue",
                bold=True,
                bgcolor="navy_blue"
            ),
            OutputType.ERROR: RichStyle(
                color="red", 
                bold=True,
                blink=True,
                bgcolor="dark_red",
            ),
            OutputType.INFO: RichStyle(
                color="gold1",
                dim=True,
                bgcolor="grey11",
            ),
            OutputType.PLANNING: RichStyle(
                color="purple", 
                bold=True,
            ),
            OutputType.PROGRESS: RichStyle(
                color="white", 
                encircle=True,
            ),
            OutputType.SUCCESS: RichStyle(
                color="bright_green", 
                bold=True,
                strike=False,
                meta={"icon": "✓"},
            ),
            OutputType.WARNING: RichStyle(
                color="yellow", 
                bold=True,
                blink2=True,
                bgcolor="dark_orange",
            ),
            OutputType.DEBUG: RichStyle(
                color="grey58",
                dim=True,
                conceal=True
            ),
            OutputType.USER: RichStyle(
                color="spring_green2",
                reverse=True,
                frame=True,
            ),
            OutputType.TOOL: RichStyle(
                color="dark_sea_green4",
                bgcolor="grey19",
            )
        }
        
        # Get formatted header
        lang = lang if lang is not None else PrettyOutput._detect_language(text, default_lang='markdown')
        header = PrettyOutput._format(output_type, timestamp)
        
        # Create syntax highlighted content
        content = Syntax(
            text,
            lang,
            theme="monokai",
            word_wrap=True,
        )
        
        # Create panel with styling
        panel = Panel(
            content,
            style=styles[output_type],
            border_style=styles[output_type],
            title=header,
            title_align="left",
            padding=(0, 0),
            highlight=True,
            box=HEAVY,
        )
        
        # Print panel
        console.print(panel)
        
        # Print stack trace for errors if requested
        if traceback or output_type == OutputType.ERROR:
            console.print_exception()

    @staticmethod
    def section(title: str, output_type: OutputType = OutputType.INFO):
        """Print section title in a panel"""
        panel = Panel(
            Text(title, style=output_type.value, justify="center"),
            border_style=output_type.value
        )
        console.print()
        console.print(panel)
        console.print()

    @staticmethod
    def print_stream(text: str):
        """Print stream output without line break"""
        # 使用进度类型样式
        style = PrettyOutput._get_style(OutputType.SYSTEM)
        console.print(text, style=style, end="")

    @staticmethod
    def print_stream_end():
        """End stream output with line break"""
        # 结束符样式
        end_style = PrettyOutput._get_style(OutputType.SUCCESS)
        console.print("\n", style=end_style)
        console.file.flush()

    @staticmethod
    def _get_style(output_type: OutputType) -> RichStyle:
        """Get pre-defined RichStyle for output type"""
        return console.get_style(output_type.value)

def get_single_line_input(tip: str) -> str:
    """Get single line input, support direction key, history function, etc."""
    session = PromptSession(history=None)
    style = PromptStyle.from_dict({
        'prompt': 'ansicyan',
    })
    return session.prompt(f"{tip}", style=style)

class FileCompleter(Completer):
    """Custom completer for file paths with fuzzy matching."""
    def __init__(self):
        self.path_completer = PathCompleter()
        self.max_suggestions = 10
        self.min_score = 10
        
    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        cursor_pos = document.cursor_position
        
        # Find all @ positions in text
        at_positions = [i for i, char in enumerate(text) if char == '@']
        
        if not at_positions:
            return
            
        # Get the last @ position
        current_at_pos = at_positions[-1]
        
        # If cursor is not after the last @, don't complete
        if cursor_pos <= current_at_pos:
            return
            
        # Check if there's a space after @
        text_after_at = text[current_at_pos + 1:cursor_pos]
        if ' ' in text_after_at:
            return
            
        # Get the text after the current @
        file_path = text_after_at.strip()
        
        # 计算需要删除的字符数（包括@符号）
        replace_length = len(text_after_at) + 1  # +1 包含@符号
        
        # Get all possible files using git ls-files only
        all_files = []
        try:
            # Use git ls-files to get tracked files
            import subprocess
            result = subprocess.run(['git', 'ls-files'], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE,
                                   text=True)
            if result.returncode == 0:
                all_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except Exception:
            # If git command fails, just use an empty list
            pass
        
        # If no input after @, show all files
        # Otherwise use fuzzy matching
        if not file_path:
            scored_files = [(path, 100) for path in all_files[:self.max_suggestions]]
        else:
            scored_files_data = process.extract(file_path, all_files, limit=self.max_suggestions)
            scored_files = [
                (m[0], m[1])
                for m in scored_files_data
            ]
            # Sort by score and take top results
            scored_files.sort(key=lambda x: x[1], reverse=True)
            scored_files = scored_files[:self.max_suggestions]
        
        # Return completions for files
        for path, score in scored_files:
            if not file_path or score > self.min_score:
                display_text = path  # 显示时不带反引号
                if file_path and score < 100:
                    display_text = f"{path} ({score}%)"
                completion = Completion(
                    text=f"'{path}'",  # 添加单引号包裹路径
                    start_position=-replace_length,
                    display=display_text,
                    display_meta="File"
                )
                yield completion

def get_multiline_input(tip: str) -> str:
    """Get multi-line input with enhanced completion confirmation"""
    # 单行输入说明
    PrettyOutput.section("用户输入 - 使用 @ 触发文件补全，Tab 选择补全项，Ctrl+J 提交，按 Ctrl+C 取消输入", OutputType.USER)
    
    print(f"{Fore.GREEN}{tip}{ColoramaStyle.RESET_ALL}")
    
    # 自定义按键绑定
    bindings = KeyBindings()
    
    @bindings.add('enter')
    def _(event):
        # 当有补全菜单时，回车键确认补全
        if event.current_buffer.complete_state:
            event.current_buffer.apply_completion(event.current_buffer.complete_state.current_completion)
        else:
            # 没有补全菜单时插入换行
            event.current_buffer.insert_text('\n')

    @bindings.add('c-j')  # 修改为支持的按键组合
    def _(event):
        # 使用 Ctrl+J 提交输入
        event.current_buffer.validate_and_handle()

    style = PromptStyle.from_dict({
        'prompt': 'ansicyan',
    })

    try:
        session = PromptSession(
            history=None,
            completer=FileCompleter(),
            key_bindings=bindings,
            complete_while_typing=True,
            multiline=True,  # 启用原生多行支持
            vi_mode=False,
            mouse_support=False
        )
        
        prompt = FormattedText([
            ('class:prompt', '>>> ')
        ])
        
        # 单次获取多行输入
        text = session.prompt(
            prompt,
            style=style,
        ).strip()
        
        return text
        
    except KeyboardInterrupt:
        PrettyOutput.print("输入已取消", OutputType.INFO)
        return ""

def init_env():
    """Load environment variables from ~/.jarvis/env"""
    jarvis_dir = Path.home() / ".jarvis"
    env_file = jarvis_dir / "env"
    
    # Check if ~/.jarvis directory exists
    if not jarvis_dir.exists():
        jarvis_dir.mkdir(parents=True)

    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
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

def find_git_root(start_dir="."):
    """Change to git root directory of the given path"""
    os.chdir(start_dir)
    git_root = os.popen("git rev-parse --show-toplevel").read().strip()
    os.chdir(git_root)
    return git_root

def has_uncommitted_changes():
    import subprocess
    # Add all changes silently
    subprocess.run(["git", "add", "."], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Check working directory changes
    working_changes = subprocess.run(["git", "diff", "--exit-code"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0
    
    # Check staged changes
    staged_changes = subprocess.run(["git", "diff", "--cached", "--exit-code"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0
    
    # Reset changes silently
    subprocess.run(["git", "reset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    return working_changes or staged_changes
def get_commits_between(start_hash: str, end_hash: str) -> List[Tuple[str, str]]:
    """Get list of commits between two commit hashes
    
    Args:
        start_hash: Starting commit hash (exclusive)
        end_hash: Ending commit hash (inclusive)
        
    Returns:
        List[Tuple[str, str]]: List of (commit_hash, commit_message) tuples
    """
    try:
        import subprocess
        # Use git log with pretty format to get hash and message
        result = subprocess.run(
            ['git', 'log', f'{start_hash}..{end_hash}', '--pretty=format:%H|%s'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode != 0:
            PrettyOutput.print(f"获取commit历史失败: {result.stderr}", OutputType.ERROR)
            return []
            
        commits = []
        for line in result.stdout.splitlines():
            if '|' in line:
                commit_hash, message = line.split('|', 1)
                commits.append((commit_hash, message))
        return commits
        
    except Exception as e:
        PrettyOutput.print(f"获取commit历史异常: {str(e)}", OutputType.ERROR)
        return []
def get_latest_commit_hash() -> str:
    """Get the latest commit hash of the current git repository
    
    Returns:
        str: The commit hash, or empty string if not in a git repo or error occurs
    """
    try:
        import subprocess
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return ""
    except Exception:
        return ""

def load_embedding_model():
    model_name = "BAAI/bge-m3"
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    

    try:
        # Load model
        embedding_model = SentenceTransformer(
            model_name,
            cache_folder=cache_dir,
            local_files_only=True
        )
    except Exception as e:
        # Load model
        embedding_model = SentenceTransformer(
            model_name,
            cache_folder=cache_dir,
            local_files_only=False
        )
    
    return embedding_model

def load_tokenizer():
    """Load tokenizer"""
    model_name = "gpt2"
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    
    try:
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=True
        )
    except Exception as e:
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=False
        )
    
    return tokenizer

def load_rerank_model():
    """Load reranking model"""
    model_name = "BAAI/bge-reranker-v2-m3"
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    
    PrettyOutput.print(f"加载重排序模型: {model_name}...", OutputType.INFO)
    
    try:
        # Load model and tokenizer
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=True
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=True
        )
    except Exception as e:
        # Load model and tokenizer
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=False
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            cache_dir=cache_dir,
            local_files_only=False
        )
    
    # Use GPU if available
    if torch.cuda.is_available():
        model = model.cuda()
    model.eval()
    
    return model, tokenizer



def is_long_context(files: list) -> bool:
    """Check if the file list belongs to a long context (total characters exceed 80% of the maximum context length)"""
    max_token_count = get_max_token_count()
    threshold = max_token_count * 0.8
    total_tokens = 0
    
    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                total_tokens += get_context_token_count(content)
                
                if total_tokens > threshold:
                    return True
        except Exception as e:
            PrettyOutput.print(f"读取文件 {file_path} 失败: {e}", OutputType.WARNING)
            continue
            
    return total_tokens > threshold



def get_file_md5(filepath: str)->str:    
    return hashlib.md5(open(filepath, "rb").read(100*1024*1024)).hexdigest()




def _create_methodology_embedding(embedding_model: Any, methodology_text: str) -> np.ndarray:
    """Create embedding vector for methodology text"""
    try:
        # Truncate long text
        max_length = 512
        text = ' '.join(methodology_text.split()[:max_length])
        
        # 使用sentence_transformers模型获取嵌入向量
        embedding = embedding_model.encode([text], 
                                                convert_to_tensor=True,
                                                normalize_embeddings=True)
        vector = np.array(embedding.cpu().numpy(), dtype=np.float32)
        return vector[0]  # Return first vector, because we only encoded one text
    except Exception as e:
        PrettyOutput.print(f"创建方法论嵌入向量失败: {str(e)}", OutputType.ERROR)
        return np.zeros(1536, dtype=np.float32)


def load_methodology(user_input: str) -> str:
    """Load methodology and build vector index"""
    PrettyOutput.print("加载方法论...", OutputType.PROGRESS)
    user_jarvis_methodology = os.path.expanduser("~/.jarvis/methodology")
    if not os.path.exists(user_jarvis_methodology):
        return ""
    
    def make_methodology_prompt(data: Dict) -> str:
        ret = """This is the standard methodology for handling previous problems, if the current task is similar, you can refer to it, if not,just ignore it:\n""" 
        for key, value in data.items():
            ret += f"Problem: {key}\nMethodology: {value}\n"
        return ret

    try:
        with open(user_jarvis_methodology, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if dont_use_local_model():
            return make_methodology_prompt(data)

        # Reset data structure
        methodology_data = []
        vectors = []
        ids = []

        # Get embedding model
        embedding_model = load_embedding_model()
        
        # Create test embedding to get correct dimension
        test_embedding = _create_methodology_embedding(embedding_model, "test")
        embedding_dimension = len(test_embedding)

        # Create embedding vector for each methodology
        for i, (key, value) in enumerate(data.items()):
            methodology_text = f"{key}\n{value}"
            embedding = _create_methodology_embedding(embedding_model, methodology_text)
            vectors.append(embedding)
            ids.append(i)
            methodology_data.append({"key": key, "value": value})

        if vectors:
            vectors_array = np.vstack(vectors)
            # Use correct dimension from test embedding
            hnsw_index = faiss.IndexHNSWFlat(embedding_dimension, 16)
            hnsw_index.hnsw.efConstruction = 40
            hnsw_index.hnsw.efSearch = 16
            methodology_index = faiss.IndexIDMap(hnsw_index)
            methodology_index.add_with_ids(vectors_array, np.array(ids)) # type: ignore
            query_embedding = _create_methodology_embedding(embedding_model, user_input)
            k = min(3, len(methodology_data))
            PrettyOutput.print(f"检索方法论...", OutputType.INFO)
            distances, indices = methodology_index.search(
                query_embedding.reshape(1, -1), k
            ) # type: ignore

            relevant_methodologies = {}
            output_lines = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx >= 0:
                    similarity = 1.0 / (1.0 + float(dist))
                    methodology = methodology_data[idx]
                    output_lines.append(
                        f"Methodology '{methodology['key']}' similarity: {similarity:.3f}"
                    )
                    if similarity >= 0.5:
                        relevant_methodologies[methodology["key"]] = methodology["value"]
            
            if output_lines:
                PrettyOutput.print("\n".join(output_lines), OutputType.INFO)
                    
            if relevant_methodologies:
                return make_methodology_prompt(relevant_methodologies)
        return make_methodology_prompt(data)

    except Exception as e:
        PrettyOutput.print(f"加载方法论失败: {str(e)}", OutputType.ERROR)
        return ""


def user_confirm(tip: str, default: bool = True) -> bool:
    """Prompt the user for confirmation.
    
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
    try:
        return len(open(filename, "r", encoding="utf-8").readlines())
    except Exception as e:
        return 0
    

def init_gpu_config() -> Dict:
    """Initialize GPU configuration based on available hardware
    
    Returns:
        Dict: GPU configuration including memory sizes and availability
    """
    config = {
        "has_gpu": False,
        "shared_memory": 0,
        "device_memory": 0,
        "memory_fraction": 0.8  # 默认使用80%的可用内存
    }
    
    try:
        import torch
        if torch.cuda.is_available():
            # 获取GPU信息
            gpu_mem = torch.cuda.get_device_properties(0).total_memory
            config["has_gpu"] = True
            config["device_memory"] = gpu_mem
            
            # 估算共享内存 (通常是系统内存的一部分)
            
            system_memory = psutil.virtual_memory().total
            config["shared_memory"] = min(system_memory * 0.5, gpu_mem * 2)  # 取系统内存的50%或GPU内存的2倍中的较小值
            
            # 设置CUDA内存分配
            torch.cuda.set_per_process_memory_fraction(config["memory_fraction"])
            torch.cuda.empty_cache()
            
            PrettyOutput.print(
                f"GPU已初始化: {torch.cuda.get_device_name(0)}\n"
                f"设备内存: {gpu_mem / 1024**3:.1f}GB\n"
                f"共享内存: {config['shared_memory'] / 1024**3:.1f}GB", 
                output_type=OutputType.SUCCESS
            )
        else:
            PrettyOutput.print("没有GPU可用, 使用CPU模式", output_type=OutputType.WARNING)
    except Exception as e:
        PrettyOutput.print(f"GPU初始化失败: {str(e)}", output_type=OutputType.WARNING)
        
    return config


def get_embedding(embedding_model: Any, text: str) -> np.ndarray:
    """Get the vector representation of the text"""
    embedding = embedding_model.encode(text, 
                                        normalize_embeddings=True,
                                        show_progress_bar=False)
    return np.array(embedding, dtype=np.float32)

def get_embedding_batch(embedding_model: Any, texts: List[str]) -> np.ndarray:
    """Get embeddings for a batch of texts efficiently"""
    try:
        all_vectors = []
        for text in texts:
            vectors = get_embedding_with_chunks(embedding_model, text)
            all_vectors.extend(vectors)
        return np.vstack(all_vectors)
    except Exception as e:
        PrettyOutput.print(f"批量嵌入失败: {str(e)}", OutputType.ERROR)
        return np.zeros((0, embedding_model.get_sentence_embedding_dimension()), dtype=np.float32)


    
def get_max_token_count():
    return int(os.getenv('JARVIS_MAX_TOKEN_COUNT', '131072'))  # 默认128k
    
def get_thread_count():
    return int(os.getenv('JARVIS_THREAD_COUNT', '1'))  

def dont_use_local_model():
    return os.getenv('JARVIS_DONT_USE_LOCAL_MODEL', 'false') == 'true'
    
def is_auto_complete() -> bool:
    return os.getenv('JARVIS_AUTO_COMPLETE', 'false') == 'true'
    
def is_use_methodology() -> bool:
    return os.getenv('JARVIS_USE_METHODOLOGY', 'true') == 'true'

def is_record_methodology() -> bool:
    return os.getenv('JARVIS_RECORD_METHODOLOGY', 'true') == 'true'

def is_need_summary() -> bool:
    return os.getenv('JARVIS_NEED_SUMMARY', 'true') == 'true'

def get_min_paragraph_length() -> int:
    return int(os.getenv('JARVIS_MIN_PARAGRAPH_LENGTH', '50'))

def get_max_paragraph_length() -> int:
    return int(os.getenv('JARVIS_MAX_PARAGRAPH_LENGTH', '12800'))

def get_shell_name() -> str:
    return os.getenv('SHELL', 'bash')

def get_normal_platform_name() -> str:
    return os.getenv('JARVIS_PLATFORM', 'kimi')

def get_normal_model_name() -> str:
    return os.getenv('JARVIS_MODEL', 'kimi')

def get_codegen_platform_name() -> str:
    return os.getenv('JARVIS_CODEGEN_PLATFORM', os.getenv('JARVIS_PLATFORM', 'kimi'))

def get_codegen_model_name() -> str:
    return os.getenv('JARVIS_CODEGEN_MODEL', os.getenv('JARVIS_MODEL', 'kimi'))

def get_thinking_platform_name() -> str:
    return os.getenv('JARVIS_THINKING_PLATFORM', os.getenv('JARVIS_PLATFORM', 'kimi'))

def get_thinking_model_name() -> str:
    return os.getenv('JARVIS_THINKING_MODEL', os.getenv('JARVIS_MODEL', 'kimi'))

def get_cheap_platform_name() -> str:
    return os.getenv('JARVIS_CHEAP_PLATFORM', os.getenv('JARVIS_PLATFORM', 'kimi'))

def get_cheap_model_name() -> str:
    return os.getenv('JARVIS_CHEAP_MODEL', os.getenv('JARVIS_MODEL', 'kimi'))

def is_execute_tool_confirm() -> bool:
    return os.getenv('JARVIS_EXECUTE_TOOL_CONFIRM', 'false') == 'true'

def split_text_into_chunks(text: str, max_length: int = 512) -> List[str]:
    """Split text into chunks with overlapping windows"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_length
        # Find the nearest sentence boundary
        if end < len(text):
            while end > start and text[end] not in {'.', '!', '?', '\n'}:
                end -= 1
            if end == start:  # No punctuation found, hard cut
                end = start + max_length
        chunk = text[start:end]
        chunks.append(chunk)
        # Overlap 20% of the window
        start = end - int(max_length * 0.2)
    return chunks

def get_embedding_with_chunks(embedding_model: Any, text: str) -> List[np.ndarray]:
    """Get embeddings for text chunks"""
    chunks = split_text_into_chunks(text, 512)
    if not chunks:
        return []
    
    vectors = []
    for chunk in chunks:
        vector = get_embedding(embedding_model, chunk)
        vectors.append(vector)
    return vectors


def get_context_token_count(text: str) -> int:
    """Get the token count of the text using the tokenizer
    
    Args:
        text: The input text to count tokens for
        
    Returns:
        int: The number of tokens in the text
    """
    try:
        # Use a fast tokenizer that's good at general text
        tokenizer = load_tokenizer()
        chunks = split_text_into_chunks(text, 512)
        return sum([len(tokenizer.encode(chunk)) for chunk in chunks])
        
    except Exception as e:
        PrettyOutput.print(f"计算token失败: {str(e)}", OutputType.WARNING)
        # Fallback to rough character-based estimate
        return len(text) // 4  # Rough estimate of 4 chars per token



