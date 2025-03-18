"""Symbol-related classes for the tree-sitter code database."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

class SymbolType(Enum):
    """Types of symbols that can be stored in the database."""
    FUNCTION = "function"
    CLASS = "class"
    VARIABLE = "variable"
    REFERENCE = "reference"
    FUNCTION_CALL = "function_call"

@dataclass
class SymbolLocation:
    """Location information for a symbol in source code."""
    file_path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int

@dataclass
class Symbol:
    """Represents a symbol in the code database."""
    name: str
    type: SymbolType
    location: SymbolLocation
    scope: Optional[str] = None  # Optional scope information
    parent: Optional['Symbol'] = None  # Optional parent symbol (e.g., class for methods) 