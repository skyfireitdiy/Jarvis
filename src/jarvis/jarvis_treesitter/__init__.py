"""Tree-sitter based code database for fast symbol lookup."""

__version__ = "0.1.0"

from .database import CodeDatabase
from .symbol import Symbol, SymbolType, SymbolLocation
from .language import LanguageType, LanguageConfig
from .grammar_builder import GrammarBuilder, setup_default_grammars, DEFAULT_GRAMMAR_DIR

__all__ = [
    "CodeDatabase",
    "Symbol",
    "SymbolType",
    "SymbolLocation",
    "LanguageType",
    "LanguageConfig",
    "GrammarBuilder",
    "setup_default_grammars",
    "DEFAULT_GRAMMAR_DIR",
] 