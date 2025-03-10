import os
import time
import hashlib
from pathlib import Path
from typing import Any, Dict, List
import psutil
import torch
from ..jarvis_utils.output import PrettyOutput, OutputType
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
def get_file_md5(filepath: str)->str:    
    return hashlib.md5(open(filepath, "rb").read(100*1024*1024)).hexdigest()
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