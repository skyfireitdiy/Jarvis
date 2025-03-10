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
import os
from typing import Any, Dict, List, Optional, Tuple
import colorama
from rich.traceback import install as install_rich_traceback
# Re-export from new modules
# These imports are required for project functionality and may be used dynamically
from .globals import (  # noqa: F401
    global_agents,
    current_agent_name,
    console,
    make_agent_name,
    set_agent,
    get_agent_list,
    delete_agent
)
from .output import OutputType, PrettyOutput  # noqa: F401
from .input import get_single_line_input, get_multiline_input, FileCompleter  # noqa: F401
from .git_utils import (  # noqa: F401
    find_git_root,
    has_uncommitted_changes,
    get_commits_between,
    get_latest_commit_hash,
    get_modified_line_ranges
)
from .embedding import (  # noqa: F401
    load_embedding_model,
    get_embedding,
    get_embedding_batch,
    get_embedding_with_chunks
)
from .config import (  # noqa: F401
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
from .methodology import load_methodology  # noqa: F401
from .utils import (  # noqa: F401
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