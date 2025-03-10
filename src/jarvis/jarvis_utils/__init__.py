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
import colorama
from rich.traceback import install as install_rich_traceback
# Re-export from new modules
# These imports are required for project functionality and may be used dynamically
# Initialize colorama for cross-platform colored text
colorama.init()
# Disable tokenizers parallelism to avoid issues with multiprocessing
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# Install rich traceback handler for better error messages
install_rich_traceback()