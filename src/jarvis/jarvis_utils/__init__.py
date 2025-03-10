"""
Jarvis Utils Module
This module provides utility functions and classes used throughout the Jarvis system.
It includes various helper functions, configuration management, and common operations.
The module is organized into several submodules:
- config: Configuration management
- embedding: Text embedding utilities
- git_utils: Git repository operations
- input: User input handling
- methodology: Methodology management
- output: Output formatting
- utils: General utilities
"""
import hashlib
from pathlib import Path
import re
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
# Re-export from new modules
from .globals import (
    global_agents,
    current_agent_name,
    console,
    make_agent_name,
    set_agent,
    get_agent_list,
    delete_agent
)
from .output import OutputType, PrettyOutput
from .input import get_single_line_input, get_multiline_input, FileCompleter
from .git_utils import (
    find_git_root,
    has_uncommitted_changes,
    get_commits_between,
    get_latest_commit_hash,
    get_modified_line_ranges
)
from .embedding import (
    load_embedding_model,
    get_embedding,
    get_embedding_batch,
    get_embedding_with_chunks
)
from .config import (
    get_max_token_count,
    get_thread_count,
    dont_use_local_model,
    is_auto_complete,
    is_use_methodology,
    is_record_methodology,
    is_need_summary,
    get_min_paragraph_length,
    get_max_paragraph_length,
    get_shell_name,
    get_normal_platform_name,
    get_normal_model_name,
    get_codegen_platform_name,
    get_codegen_model_name,
    get_thinking_platform_name,
    get_thinking_model_name,
    get_cheap_platform_name,
    get_cheap_model_name,
    is_execute_tool_confirm,
    is_confirm_before_apply_patch
)
from .methodology import load_methodology
from .utils import (
    init_env,
    while_success,
    while_true,
    get_file_md5,
    user_confirm,
    get_file_line_count,
    init_gpu_config,
    split_text_into_chunks,
    get_context_token_count,
    is_long_context
)
# Initialize colorama for cross-platform colored text
colorama.init()
# Disable tokenizers parallelism to avoid issues with multiprocessing
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# Install rich traceback handler for better error messages
install_rich_traceback()