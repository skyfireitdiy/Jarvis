# -*- coding: utf-8 -*-
"""Go language symbol extractor."""

from typing import Any
from typing import Optional

from jarvis.jarvis_agent.file_context_handler import register_language_extractor


def create_go_extractor() -> Optional[Any]:
    """Create Go symbol extractor using tree-sitter."""
    try:
        from jarvis.jarvis_code_agent.code_analyzer.languages.go_language import (
            GoSymbolExtractor,
        )

        return GoSymbolExtractor()
    except (ImportError, RuntimeError, Exception):
        return None


def register_go_extractor() -> None:
    """Register Go extractor for .go files."""
    register_language_extractor(".go", create_go_extractor)
