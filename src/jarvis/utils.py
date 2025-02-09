from ast import List, Str
import hashlib
from pathlib import Path
import sys
import time
import os
from enum import Enum
from datetime import datetime
from typing import Any, Dict
import colorama
from colorama import Fore, Style as ColoramaStyle
import numpy as np
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style as PromptStyle
from prompt_toolkit.formatted_text import FormattedText
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import torch
import yaml
import faiss

# 初始化colorama
colorama.init()

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

current_agent = []

def add_agent(agent_name: str):
    current_agent.append(agent_name)

def get_current_agent():
    return current_agent[-1] if current_agent else "No Agent"

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
    """美化输出类"""
    
    # 颜色方案 - 只使用前景色
    COLORS = {
        OutputType.SYSTEM: Fore.CYAN,      # Cyan - AI assistant
        OutputType.CODE: Fore.GREEN,       # Green - Code
        OutputType.RESULT: Fore.BLUE,      # Blue - Result
        OutputType.ERROR: Fore.RED,        # Red - Error
        OutputType.INFO: Fore.YELLOW,      # Yellow - Prompt
        OutputType.PLANNING: Fore.MAGENTA, # Magenta - Planning
        OutputType.PROGRESS: Fore.WHITE,   # White - Progress
        OutputType.SUCCESS: Fore.GREEN,    # Green - Success
        OutputType.WARNING: Fore.YELLOW,   # Yellow - Warning
        OutputType.DEBUG: Fore.BLUE,       # Blue - Debug
        OutputType.USER: Fore.GREEN,       # Green - User
        OutputType.TOOL: Fore.YELLOW,      # Yellow - Tool
    }
    
    # 图标方案
    ICONS = {
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
    
    # 前缀方案
    PREFIXES = {
        OutputType.SYSTEM: "Assistant",
        OutputType.CODE: "Code",
        OutputType.RESULT: "Result",
        OutputType.ERROR: "Error",
        OutputType.INFO: "Info",
        OutputType.PLANNING: "Plan",
        OutputType.PROGRESS: "Progress",
        OutputType.SUCCESS: "Success",
        OutputType.WARNING: "Warning",
        OutputType.DEBUG: "Debug",
        OutputType.USER: "User",
        OutputType.TOOL: "Tool",
    }

    @staticmethod
    def format(text: str, output_type: OutputType, timestamp: bool = True) -> str:
        """Format output text"""
        color = PrettyOutput.COLORS.get(output_type, "")
        icon = PrettyOutput.ICONS.get(output_type, "")
        prefix = PrettyOutput.PREFIXES.get(output_type, "")
        
        # 添加时间戳 - 使用白色
        time_str = f"{Fore.BLUE}[{get_current_agent()}]{ColoramaStyle.RESET_ALL}{Fore.WHITE}[{datetime.now().strftime('%H:%M:%S')}]{ColoramaStyle.RESET_ALL} " if timestamp else ""
        
        # 格式化输出
        formatted_text = f"{time_str}{color}{icon} {prefix}: {text}{ColoramaStyle.RESET_ALL}"
        
        return formatted_text

    @staticmethod
    def print(text: str, output_type: OutputType, timestamp: bool = True):
        """Print formatted output"""
        print(PrettyOutput.format(text, output_type, timestamp))
        if output_type == OutputType.ERROR:
            import traceback
            PrettyOutput.print(f"Error trace: {traceback.format_exc()}", OutputType.INFO)

    @staticmethod
    def section(title: str, output_type: OutputType = OutputType.INFO):
        """Print paragraph title with separator"""
        width = 100
        color = PrettyOutput.COLORS.get(output_type, "")
        print(f"\n{color}" + "=" * width + f"{ColoramaStyle.RESET_ALL}")
        PrettyOutput.print(title.center(width - 25), output_type, timestamp=False)
        print(f"{color}" + "=" * width + f"{ColoramaStyle.RESET_ALL}\n")

    @staticmethod
    def print_stream(text: str):
        """Print stream output, no line break"""
        color = PrettyOutput.COLORS.get(OutputType.SYSTEM, "")
        sys.stdout.write(f"{color}{text}{ColoramaStyle.RESET_ALL}")
        sys.stdout.flush()

    @staticmethod
    def print_stream_end():
        """Stream output end, print line break"""
        sys.stdout.write("\n")
        sys.stdout.flush()

def get_single_line_input(tip: str) -> str:
    """Get single line input, support direction key, history function, etc."""
    session = PromptSession(history=None)
    style = PromptStyle.from_dict({
        'prompt': 'ansicyan',
    })
    return session.prompt(f"{tip}", style=style)

def get_multiline_input(tip: str) -> str:
    """Get multi-line input, support direction key, history function, etc."""
    print(f"{Fore.GREEN}{tip}{ColoramaStyle.RESET_ALL}")
    
    # 创建输入会话，启用历史记录
    session = PromptSession(history=None)  # 使用默认历史记录
    
    # 定义提示符样式
    style = PromptStyle.from_dict({
        'prompt': 'ansicyan',
    })
    
    lines = []
    try:
        while True:
            # 设置提示符
            prompt = FormattedText([
                ('class:prompt', '... ' if lines else '>>> ')
            ])
            
            # 获取输入
            line = session.prompt(
                prompt,
                style=style,
            ).strip()
            
            # 空行处理
            if not line:
                if not lines:  # 第一行就输入空行
                    return ""
                break  # 结束多行输入
                
            lines.append(line)
            
    except KeyboardInterrupt:
        PrettyOutput.print("\nInput cancelled", OutputType.INFO)
        return "__interrupt__"
    
    return "\n".join(lines)

def load_env_from_file():
    """Load environment variables from ~/.jarvis/env"""
    env_file = Path.home() / ".jarvis" / "env"
    
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        try:
                            key, value = line.split("=", 1)
                            os.environ[key.strip()] = value.strip().strip("'").strip('"')
                        except ValueError:
                            continue
        except Exception as e:
            PrettyOutput.print(f"Warning: Failed to read ~/.jarvis/env: {e}", OutputType.WARNING)
    
    
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

def load_embedding_model():
    model_name = "BAAI/bge-m3"
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    model_dir = os.path.join(cache_dir, "models--" + model_name.replace("/", "--"))
    
    # Check if model exists
    if not os.path.exists(model_dir):
        PrettyOutput.print("Model not found locally, downloading using huggingface-cli...", OutputType.INFO)
        os.system(f'huggingface-cli download --repo-type model --local-dir {cache_dir} {model_name}' + f' --token {os.getenv("HF_TOKEN")}' if os.getenv("HF_TOKEN") else "")
    
    # Load model
    embedding_model = SentenceTransformer(
        model_name,
        cache_folder=cache_dir,
        local_files_only=True
    )
    
    return embedding_model

def load_rerank_model():
    """Load reranking model"""
    model_name = "BAAI/bge-reranker-v2-m3"
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    model_dir = os.path.join(cache_dir, "models--" + model_name.replace("/", "--"))
    
    PrettyOutput.print(f"Loading reranking model: {model_name}...", OutputType.INFO)
    
    # Check if model exists
    if not os.path.exists(model_dir):
        PrettyOutput.print("Model not found locally, downloading using huggingface-cli...", OutputType.INFO)
        os.system(f'huggingface-cli download --repo-type model --local-dir {cache_dir} {model_name}' + f' --token {os.getenv("HF_TOKEN")}' if os.getenv("HF_TOKEN") else "")
    
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
    
    # Use GPU if available
    if torch.cuda.is_available():
        model = model.cuda()
    model.eval()
    
    return model, tokenizer

def get_max_context_length():
    return int(os.getenv('JARVIS_MAX_CONTEXT_LENGTH', '131072'))  # 默认128k

def is_long_context(files: list) -> bool:
    """Check if the file list belongs to a long context (total characters exceed 80% of the maximum context length)"""
    max_length = get_max_context_length()
    threshold = max_length * 0.8
    total_chars = 0
    
    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                total_chars += len(content)
                
                if total_chars > threshold:
                    return True
        except Exception as e:
            PrettyOutput.print(f"Failed to read file {file_path}: {e}", OutputType.WARNING)
            continue
            
    return total_chars > threshold

def get_thread_count():
    return int(os.getenv('JARVIS_THREAD_COUNT', '1'))  

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

    try:
        with open(user_jarvis_methodology, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

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
            PrettyOutput.print(f"Vectorizing methodology: {key} ...", OutputType.INFO)
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
            k = min(5, len(methodology_data))
            PrettyOutput.print(f"Retrieving methodology...", OutputType.INFO)
            distances, indices = methodology_index.search(
                query_embedding.reshape(1, -1), k
            ) # type: ignore

            relevant_methodologies = {}
            for dist, idx in zip(distances[0], indices[0]):
                if idx >= 0:
                    similarity = 1.0 / (1.0 + float(dist))
                    methodology = methodology_data[idx]
                    PrettyOutput.print(
                        f"Methodology '{methodology['key']}' similarity: {similarity:.3f}",
                        OutputType.INFO
                    )
                    if similarity >= 0.5:
                        relevant_methodologies[methodology["key"]] = methodology["value"]
                    
            if relevant_methodologies:
                return f"""This is the standard methodology for handling previous problems, if the current task is similar, you can refer to it:
                        {relevant_methodologies}
                        """
        return ""

    except Exception as e:
        PrettyOutput.print(f"Error loading methodology: {str(e)}", OutputType.ERROR)
        import traceback
        PrettyOutput.print(f"Error trace: {traceback.format_exc()}", OutputType.INFO)
        return ""