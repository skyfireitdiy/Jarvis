import hashlib
from pathlib import Path
import time
import os
from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional
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
from rich.text import Text
from rich.traceback import install as install_rich_traceback
from rich.syntax import Syntax

from prompt_toolkit.completion import Completer, Completion, PathCompleter
from prompt_toolkit.document import Document
from fuzzywuzzy import fuzz

# 初始化colorama
colorama.init()

os.environ["TOKENIZERS_PARALLELISM"] = "false"

current_agent = []

# Install rich traceback handler
install_rich_traceback()

# Create console with custom theme
custom_theme = Theme({
    "info": "yellow",
    "warning": "yellow",
    "error": "red",
    "success": "green",
    "system": "cyan",
    "code": "green",
    "result": "blue",
    "planning": "magenta",
    "progress": "white",
    "debug": "blue",
    "user": "green",
    "tool": "yellow",
})

console = Console(theme=custom_theme)

def add_agent(agent_name: str):
    current_agent.append(agent_name)

def get_agent_list():
    return ']['.join(current_agent) if current_agent else "No Agent"

def delete_current_agent():
    current_agent.pop()

class OutputType(Enum):
    SYSTEM = "system"      # AI assistant message
    CODE = "code"         # Code related
    RESULT = "result"     # Tool execution result
    ERROR = "error"       # Error information
    INFO = "info"         # System prompt
    PLANNING = "planning" # Task planning
    PROGRESS = "progress" # Execution progress
    SUCCESS = "success"   # Success information
    WARNING = "warning"   # Warning information
    DEBUG = "debug"       # Debug information
    USER = "user"         # User input
    TOOL = "tool"         # Tool call

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
    def _format(text: str, output_type: OutputType, timestamp: bool = True) -> Text:
        """Format output text using rich Text"""
        # Create rich Text object
        formatted = Text()
        
        # Add timestamp and agent info
        if timestamp:
            formatted.append(f"[{datetime.now().strftime('%H:%M:%S')}] ", style="white")
        formatted.append(f"[{get_agent_list()}]", style="blue")
        # Add icon
        icon = PrettyOutput._ICONS.get(output_type, "")
        formatted.append(f"{icon} ", style=output_type.value)
        
        return formatted

    @staticmethod
    def print(text: str, output_type: OutputType, timestamp: bool = True, lang: Optional[str] = None, traceback: bool = False):
        """Print formatted output using rich console"""
        # Get formatted header
        lang = lang if lang is not None else PrettyOutput._detect_language(text, default_lang='markdown')
        header = PrettyOutput._format("", output_type, timestamp)

        content = Syntax(text, lang, theme="monokai")
            
        # Print panel with appropriate border style
        border_style = "red" if output_type == OutputType.ERROR else output_type.value
        console.print(Panel(content, border_style=border_style, title=header, title_align="left", highlight=True))
        
        # Print stack trace for errors
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
        console.print(text, style="system", end="")

    @staticmethod
    def print_stream_end():
        """End stream output with line break"""
        console.print()

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
        self.max_suggestions = 10  # 增加显示数量
        self.min_score = 10  # 降低相似度阈值
        
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
        
        # Get all possible files from current directory
        all_files = []
        for root, _, files in os.walk('.'):
            for f in files:
                path = os.path.join(root, f)
                # Remove ./ from the beginning
                path = path[2:] if path.startswith('./') else path
                all_files.append(path)
        
        # If no input after @, show all files
        # Otherwise use fuzzy matching
        if not file_path:
            scored_files = [(path, 100) for path in all_files[:self.max_suggestions]]
        else:
            scored_files = [
                (path, fuzz.ratio(file_path.lower(), path.lower()))
                for path in all_files
            ]
            # Sort by score and take top results
            scored_files.sort(key=lambda x: x[1], reverse=True)
            scored_files = scored_files[:self.max_suggestions]
        
        # Return completions for files
        for path, score in scored_files:
            if not file_path or score > self.min_score:
                display_text = path
                if file_path and score < 100:
                    display_text = f"{path} ({score}%)"
                completion = Completion(
                    text=path,
                    start_position=-len(file_path),
                    display=display_text,
                    display_meta="File"
                )
                yield completion

def get_multiline_input(tip: str) -> str:
    """Get multi-line input, support direction key, history function, and file completion.
    
    Args:
        tip: The prompt tip to display
        
    Returns:
        str: The entered text
    """
    print(f"{Fore.GREEN}{tip}{ColoramaStyle.RESET_ALL}")
    
    # Define prompt style
    style = PromptStyle.from_dict({
        'prompt': 'ansicyan',
    })
    
    lines = []
    try:
        while True:
            # Set prompt
            prompt = FormattedText([
                ('class:prompt', '... ' if lines else '>>> ')
            ])
            
            # Create new session with new completer for each line
            session = PromptSession(
                history=None,  # Use default history
                completer=FileCompleter()  # New completer instance for each line
            )
            
            # Get input with completion support
            line = session.prompt(
                prompt,
                style=style,
            ).strip()
            
            # Handle empty line
            if not line:
                if not lines:  # First line is empty
                    return ""
                break  # End multi-line input
                
            lines.append(line)
            
    except KeyboardInterrupt:
        PrettyOutput.print("Input cancelled", OutputType.INFO)
        return ""
    
    return "\n".join(lines)

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
            PrettyOutput.print(f"Warning: Failed to read {env_file}: {e}", OutputType.WARNING)
    
    
def while_success(func, sleep_time: float = 0.1):
    while True:
        try:
            return func()
        except Exception as e:
            PrettyOutput.print(f"Execution failed: {str(e)}, retry in {sleep_time}s...", OutputType.ERROR)
            time.sleep(sleep_time)
            continue

def while_true(func, sleep_time: float = 0.1):
    """Loop execution function, until the function returns True"""
    while True:
        ret = func()
        if ret:
            break
        PrettyOutput.print(f"Execution failed, retry in {sleep_time}s...", OutputType.WARNING)
        time.sleep(sleep_time)
    return ret

def find_git_root(dir="."):
    curr_dir = os.getcwd()
    os.chdir(dir)
    ret = os.popen("git rev-parse --show-toplevel").read().strip()
    os.chdir(curr_dir)
    return ret

def has_uncommitted_changes():
    os.system("git add .")
    # Check working directory changes
    working_changes = os.popen("git diff --exit-code").read().strip() != ""
    # Check staged changes
    staged_changes = os.popen("git diff --cached --exit-code").read().strip() != ""
    os.system("git reset HEAD")
    return working_changes or staged_changes

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
    
    PrettyOutput.print(f"Loading reranking model: {model_name}...", OutputType.INFO)
    
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
            PrettyOutput.print(f"Failed to read file {file_path}: {e}", OutputType.WARNING)
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
        PrettyOutput.print(f"Failed to create methodology embedding vector: {str(e)}", OutputType.ERROR)
        return np.zeros(1536, dtype=np.float32)


def load_methodology(user_input: str) -> str:
    """Load methodology and build vector index"""
    PrettyOutput.print("Loading methodology...", OutputType.PROGRESS)
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
            PrettyOutput.print(f"Retrieving methodology...", OutputType.INFO)
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
        PrettyOutput.print(f"Error loading methodology: {str(e)}", OutputType.ERROR)
        import traceback
        PrettyOutput.print(f"Error trace: {traceback.format_exc()}", OutputType.INFO)
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
                f"GPU initialized: {torch.cuda.get_device_name(0)}\n"
                f"Device Memory: {gpu_mem / 1024**3:.1f}GB\n"
                f"Shared Memory: {config['shared_memory'] / 1024**3:.1f}GB", 
                output_type=OutputType.SUCCESS
            )
        else:
            PrettyOutput.print("No GPU available, using CPU mode", output_type=OutputType.WARNING)
    except Exception as e:
        PrettyOutput.print(f"GPU initialization failed: {str(e)}", output_type=OutputType.WARNING)
        
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
        PrettyOutput.print(f"Batch embedding failed: {str(e)}", OutputType.ERROR)
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
        chunks = split_text_into_chunks(text, 1024)
        return sum([len(tokenizer.encode(chunk)) for chunk in chunks])
        
    except Exception as e:
        PrettyOutput.print(f"Error counting tokens: {str(e)}", OutputType.WARNING)
        # Fallback to rough character-based estimate
        return len(text) // 4  # Rough estimate of 4 chars per token



