# -*- coding: utf-8 -*-
"""C language symbol extractor."""

from typing import Any
from typing import Optional

from jarvis.jarvis_agent.file_context_handler import register_language_extractor


def create_c_extractor() -> Optional[Any]:
    """Create C symbol extractor using tree-sitter."""
    try:
        from jarvis.jarvis_code_agent.code_analyzer.languages.c_cpp_language import (
            CSymbolExtractor,
        )

        return CSymbolExtractor()
    except (ImportError, RuntimeError, Exception):
        return None


def register_c_extractor() -> None:
    """Register C extractor for .c and .h files."""
    register_language_extractor([".c", ".h"], create_c_extractor)
