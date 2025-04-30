"""
Code embedding utility using Qodo-Embed-1-7B model.

This module provides functions to generate embeddings for code files using the
Qodo-Embed-1-7B model from Hugging Face.
"""

import os
import torch
import torch.nn.functional as F
from torch import Tensor
import functools
from typing import List, Union, Optional, Dict, Tuple, cast
from transformers import AutoTokenizer, AutoModel, PreTrainedTokenizer, PreTrainedModel, PreTrainedTokenizerFast

from jarvis.jarvis_utils.output import PrettyOutput, OutputType
from jarvis.jarvis_utils.config import get_code_embeding_model_dimension, get_code_embeding_model_name, get_data_dir
from jarvis.jarvis_utils.utils import init_env

# 全局缓存，避免重复加载模型和分词器
_global_tokenizers: Dict[str, Union[PreTrainedTokenizer, PreTrainedTokenizerFast]] = {}
_global_models: Dict[str, PreTrainedModel] = {}

# 检查是否可以使用flash-attn
_HAS_FLASH_ATTN = False
try:
    # 使用ignore_errors=True导入，处理linter错误
    import importlib.util
    if importlib.util.find_spec("flash_attn") is not None:
        import flash_attn  # type: ignore
        _HAS_FLASH_ATTN = True
        PrettyOutput.print("flash-attn库已加载，将使用快速注意力机制", OutputType.DEBUG)
except ImportError:
    PrettyOutput.print("flash-attn库未安装或无法加载，将使用标准注意力机制", OutputType.DEBUG)

# 设置PyTorch内存管理
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True,max_split_size_mb:128'

class CodeEmbedding:
    """Class for generating embeddings for code files using Qodo-Embed-1-7B model."""
    
    def __init__(self, model_name: str, dimension: int, device: Optional[str] = None):
        """
        Initialize the CodeEmbedding class.
        
        Args:
            model_name: The name of the model to use. Defaults to "Qodo/Qodo-Embed-1-7B".
            device: The device to use for inference. If None, will use CUDA if available.
        """
        self.model_name = model_name
        
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
            
        if self.device == "cuda" and not torch.cuda.is_available():
            PrettyOutput.print("CUDA不可用，将使用CPU进行推理", OutputType.WARNING)
            self.device = "cpu"
            
        # 加载分词器和模型
        self.tokenizer, self.model = load_model_and_tokenizer(model_name, self.device)
        
        # 设置模型的最大上下文窗口大小 - 减小以节省内存
        self.max_tokens = 8192  # 减小上下文窗口大小
        # 嵌入向量维度
        self.embedding_dim = dimension
        
        # 启用梯度检查点以节省内存
        if hasattr(self.model, 'gradient_checkpointing_enable'):
            self.model.gradient_checkpointing_enable()
        
        # 设置模型为评估模式
        self.model.eval()
        
        # 如果使用CUDA，清理缓存
        if self.device == "cuda":
            torch.cuda.empty_cache()
    
    def _last_token_pool(self, last_hidden_states: Tensor, attention_mask: Tensor) -> Tensor:
        """
        Extract the embedding from the last token.
        
        Args:
            last_hidden_states: The last hidden states from the model.
            attention_mask: The attention mask.
            
        Returns:
            The extracted embeddings.
        """
        left_padding = (attention_mask[:, -1].sum() == attention_mask.shape[0])
        if left_padding:
            return last_hidden_states[:, -1]
        else:
            sequence_lengths = attention_mask.sum(dim=1) - 1
            batch_size = last_hidden_states.shape[0]
            return last_hidden_states[torch.arange(batch_size, device=last_hidden_states.device), sequence_lengths]
    
    def _split_text_into_chunks(self, text: str, overlap: int = 100) -> List[str]:
        """
        Split the text into chunks that fit within the token limit.
        
        Args:
            text: The text to split.
            overlap: The number of tokens to overlap between chunks.
            
        Returns:
            A list of text chunks.
        """
        # For very long texts, we need to avoid tokenizing the entire text at once
        # First, split by newline to process in manageable segments
        lines = text.split('\n')
        
        # Initialize variables
        chunks = []
        current_chunk = ""
        current_chunk_tokens = 0
        # Allow a buffer of 3 tokens for safety (2 for special tokens + 1 for safety margin)
        max_chunk_tokens = self.max_tokens - 3  
        
        for line in lines:
            # Tokenize this line to get its token count
            line_tokens = len(self.tokenizer.encode(line, add_special_tokens=False))
            
            # If adding this line would exceed the token limit, save the current chunk and start a new one
            if current_chunk_tokens + line_tokens > max_chunk_tokens:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = line
                current_chunk_tokens = line_tokens
            else:
                # Add the line to the current chunk
                if current_chunk:
                    current_chunk += '\n' + line
                else:
                    current_chunk = line
                current_chunk_tokens += line_tokens
        
        # Add the last chunk if there is one
        if current_chunk:
            chunks.append(current_chunk)
        
        # If no chunks were created (e.g., empty input), return an empty list
        if not chunks:
            return []
            
        # Add some overlap between chunks if needed and possible
        if overlap > 0 and len(chunks) > 1:
            overlapped_chunks = [chunks[0]]
            
            for i in range(1, len(chunks)):
                prev_chunk = chunks[i-1]
                curr_chunk = chunks[i]
                
                # Get the last few tokens from the previous chunk to create overlap
                # This is a simple approach - for more advanced overlap, you might
                # want to ensure semantic boundaries are preserved
                prev_lines = prev_chunk.split('\n')
                overlap_text = ""
                
                # Add lines from the end of previous chunk until we reach desired overlap
                j = len(prev_lines) - 1
                overlap_token_count = 0
                
                while j >= 0 and overlap_token_count < overlap:
                    line_tokens = len(self.tokenizer.encode(prev_lines[j], add_special_tokens=False))
                    if overlap_token_count + line_tokens <= overlap:
                        overlap_text = prev_lines[j] + ('\n' + overlap_text if overlap_text else '')
                        overlap_token_count += line_tokens
                    else:
                        break
                    j -= 1
                
                # Prepend overlap text to current chunk if we have any
                if overlap_text:
                    overlapped_chunks.append(overlap_text + '\n' + curr_chunk)
                else:
                    overlapped_chunks.append(curr_chunk)
                    
            return overlapped_chunks
        
        return chunks
    
    def embed_code(self, code: str, normalize: bool = True) -> List[torch.Tensor]:
        """
        Generate embeddings for the given code.
        
        Args:
            code: The code to embed.
            normalize: Whether to normalize the embeddings. Defaults to True.
            
        Returns:
            A list of embeddings for each code chunk.
        """
        # Split the code into chunks
        code_chunks = self._split_text_into_chunks(code)
        embeddings = []
        
        # For large files, estimate total tokens instead of counting exactly
        if len(code) > 100000:  # If file is larger than ~100KB
            # Estimate based on a small sample
            sample_size = min(10000, len(code))
            sample = code[:sample_size]
            sample_tokens = len(self.tokenizer.encode(sample, add_special_tokens=False))
            estimated_tokens = int(sample_tokens * (len(code) / sample_size))
            PrettyOutput.print(f"源文件预估token数: ~{estimated_tokens}, 划分为 {len(code_chunks)} 个代码块", OutputType.INFO)
        else:
            total_tokens = len(self.tokenizer.encode(code, add_special_tokens=False, truncation=False))
            PrettyOutput.print(f"源文件总token数: {total_tokens}, 划分为 {len(code_chunks)} 个代码块", OutputType.INFO)
        
        # 如果处理较大文本且在CPU上运行，提供警告
        if len(code_chunks) > 1 and self.device == "cpu":
            PrettyOutput.print(f"警告: 在CPU上处理{len(code_chunks)}个代码块，这可能会很慢", OutputType.WARNING)
        
        # 使用torch.no_grad()上下文管理器
        with torch.no_grad():
            for i, chunk in enumerate(code_chunks):
                try:
                    # 清理GPU缓存
                    if self.device == "cuda":
                        torch.cuda.empty_cache()
                    
                    # Tokenize the chunk
                    inputs = self.tokenizer(chunk, return_tensors="pt", truncation=True, max_length=self.max_tokens)
                    inputs = {k: v.to(self.device) for k, v in inputs.items()}
                    
                    # Generate embeddings
                    outputs = self.model(**inputs)
                    
                    # Extract embeddings
                    attention_mask_tensor = cast(Tensor, inputs['attention_mask'])
                    embedding = self._last_token_pool(outputs.last_hidden_state, attention_mask_tensor)
                    
                    # Normalize if required
                    if normalize:
                        embedding = F.normalize(embedding, p=2, dim=1)
                    
                    # Move to CPU and detach
                    embedding = embedding.cpu().detach()
                    embeddings.append(embedding)
                    
                    # 清理GPU缓存
                    if self.device == "cuda":
                        torch.cuda.empty_cache()
                    
                    # 显示进度
                    if (i + 1) % 5 == 0 or (i + 1) == len(code_chunks):
                        PrettyOutput.print(f"已处理 {i + 1}/{len(code_chunks)} 个代码块", OutputType.INFO)
                        
                except RuntimeError as e:
                    if "CUDA out of memory" in str(e):
                        PrettyOutput.print(f"CUDA内存不足，尝试在CPU上处理此块", OutputType.WARNING)
                        # 尝试在CPU上处理
                        try:
                            # 将模型临时移到CPU
                            original_device = next(self.model.parameters()).device
                            self.model = cast(PreTrainedModel, self.model.cpu())
                            
                            # 重新处理输入
                            inputs = {k: v.cpu() for k, v in inputs.items()}
                            outputs = self.model(**inputs)
                            
                            # 提取嵌入
                            attention_mask_tensor = cast(Tensor, inputs['attention_mask'])
                            embedding = self._last_token_pool(outputs.last_hidden_state, attention_mask_tensor)
                            
                            if normalize:
                                embedding = F.normalize(embedding, p=2, dim=1)
                            
                            embeddings.append(embedding.cpu().detach())
                            
                            # 将模型移回原来的设备
                            self.model = cast(PreTrainedModel, self.model.to(original_device))
                            
                            # 清理GPU缓存
                            if self.device == "cuda":
                                torch.cuda.empty_cache()
                                
                        except Exception as cpu_e:
                            PrettyOutput.print(f"在CPU上处理也失败: {str(cpu_e)}", OutputType.ERROR)
                            raise
                    else:
                        PrettyOutput.print(f"处理代码块时出错: {str(e)}", OutputType.ERROR)
                        raise
                except Exception as e:
                    PrettyOutput.print(f"处理代码块时出错: {str(e)}", OutputType.ERROR)
                    raise
        
        return embeddings
    
    def embed_file(self, file_path: str, normalize: bool = True) -> List[torch.Tensor]:
        """
        Generate embeddings for the given file.
        
        Args:
            file_path: The path to the file to embed.
            normalize: Whether to normalize the embeddings. Defaults to True.
            
        Returns:
            A list of embeddings for each code chunk in the file.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            # Read the file
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            # Generate embeddings
            return self.embed_code(code, normalize)
        except UnicodeDecodeError:
            # 尝试以二进制模式读取
            PrettyOutput.print(f"使用UTF-8解码失败，尝试以二进制模式读取", OutputType.WARNING)
            try:
                with open(file_path, 'rb') as f:
                    code = f.read().decode('utf-8', errors='replace')
                return self.embed_code(code, normalize)
            except Exception as e:
                PrettyOutput.print(f"生成代码嵌入失败: {str(e)}", OutputType.ERROR)
                raise
        except Exception as e:
            PrettyOutput.print(f"生成代码嵌入失败: {str(e)}", OutputType.ERROR)
            raise


@functools.lru_cache(maxsize=2)
def load_model_and_tokenizer(model_name: str, device: str = "cuda") -> Tuple[Union[PreTrainedTokenizer, PreTrainedTokenizerFast], PreTrainedModel]:
    """
    加载模型和分词器，使用缓存避免重复加载。
    
    Args:
        model_name: 要加载的模型名称
        device: 运行设备，"cuda"或"cpu"
    
    Returns:
        Tuple[Union[PreTrainedTokenizer, PreTrainedTokenizerFast], PreTrainedModel]: 加载的分词器和模型
    """
    cache_dir = os.path.join(get_data_dir(), "huggingface", "hub")
    
    # 检查全局缓存中是否已有分词器
    if model_name in _global_tokenizers:
        tokenizer = _global_tokenizers[model_name]
        PrettyOutput.print(f"使用缓存的分词器: {model_name}", OutputType.DEBUG)
    else:
        try:
            # 先尝试从本地加载
            PrettyOutput.print(f"尝试从本地加载分词器: {model_name}", OutputType.DEBUG)
            tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                cache_dir=cache_dir,
                local_files_only=True,
                trust_remote_code=True
            )
        except Exception as e:
            # 本地加载失败，从网络加载
            PrettyOutput.print(f"本地加载分词器失败，从网络加载: {str(e)}", OutputType.DEBUG)
            tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                cache_dir=cache_dir,
                local_files_only=False,
                trust_remote_code=True
            )
        
        # 保存到全局缓存
        _global_tokenizers[model_name] = tokenizer
    
    # 检查全局缓存中是否已有模型
    if model_name in _global_models:
        model = _global_models[model_name]
        PrettyOutput.print(f"使用缓存的模型: {model_name}", OutputType.DEBUG)
    else:
        # 准备加载参数
        model_kwargs = {
            "cache_dir": cache_dir,
            "trust_remote_code": True,
        }
        
        # 如果有flash_attn且在CUDA上，添加相关参数
        if _HAS_FLASH_ATTN and device == "cuda":
            model_kwargs["attn_implementation"] = "flash_attention_2"
        
        try:
            # 先尝试从本地加载
            PrettyOutput.print(f"尝试从本地加载模型: {model_name}", OutputType.DEBUG)
            model_kwargs["local_files_only"] = True
            model = AutoModel.from_pretrained(model_name, **model_kwargs)
        except Exception as e:
            # 本地加载失败，从网络加载
            PrettyOutput.print(f"本地加载模型失败，从网络加载: {str(e)}", OutputType.DEBUG)
            model_kwargs["local_files_only"] = False
            model = AutoModel.from_pretrained(model_name, **model_kwargs)
        
        # 移至正确的设备
        # 使用适当的类型转换来避免类型错误
        model_with_device = cast(PreTrainedModel, model.to(device))
        model = model_with_device
        
        # 保存到全局缓存
        _global_models[model_name] = model
    
    return tokenizer, model


def embed_file(file_path: str, model_name: str, dimension: int,  normalize: bool = True) -> List[torch.Tensor]:
    """
    生成给定文件的代码嵌入向量，使用Qodo-Embed-1-7B模型。
    
    Args:
        file_path: 文件路径
        normalize: 是否对嵌入向量进行归一化，默认为True
        model_name: 使用的模型名称
        dimension: 嵌入向量的维度
        
    Returns:
        List[torch.Tensor]: 文件代码块的嵌入向量列表
    """
    embedder = CodeEmbedding(model_name, dimension)
    return embedder.embed_file(file_path, normalize)


if __name__ == "__main__":
    import sys

    init_env()
    
    if len(sys.argv) < 2:
        print("使用方法: python code_embeding.py <文件路径> <模型名称> <维度>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    embeddings = embed_file(file_path, get_code_embeding_model_name(), get_code_embeding_model_dimension())
    
    print(f"为 {file_path} 生成了 {len(embeddings)} 个嵌入向量")
    for i, embedding in enumerate(embeddings):
        print(f"嵌入向量 {i+1}: 形状={embedding.shape}")
