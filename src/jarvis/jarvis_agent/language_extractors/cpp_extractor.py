# -*- coding: utf-8 -*-
"""C++ language symbol extractor."""

from typing import Any
from typing import Optional

from jarvis.jarvis_agent.file_context_handler import register_language_extractor


def create_cpp_extractor() -> Optional[Any]:
    """Create C++ symbol extractor using tree-sitter."""
    try:
        from jarvis.jarvis_code_agent.code_analyzer.languages.c_cpp_language import (
            CppSymbolExtractor,
        )

        return CppSymbolExtractor()
    except (ImportError, RuntimeError, Exception):
        return None


def register_cpp_extractor() -> None:
    """Register C++ extractor for .cpp, .cc, .cxx, .hpp, .hxx files."""
    register_language_extractor(
        [".cpp", ".cc", ".cxx", ".hpp", ".hxx"], create_cpp_extractor
    )
