"""Language-specific configurations for tree-sitter."""

from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

class LanguageType(Enum):
    """Supported programming languages."""
    PYTHON = "python"
    C = "c"
    CPP = "cpp"
    GO = "go"
    RUST = "rust"

@dataclass
class LanguageConfig:
    """Configuration for a specific programming language."""
    name: str
    grammar_file: str
    file_extensions: List[str]
    symbol_patterns: Dict[str, List[str]]  # Maps symbol types to tree-sitter node types

# Language-specific configurations
LANGUAGE_CONFIGS: Dict[LanguageType, LanguageConfig] = {
    LanguageType.PYTHON: LanguageConfig(
        name="python",
        grammar_file="python.so",
        file_extensions=[".py"],
        symbol_patterns={
            "function": ["function_definition"],
            "class": ["class_definition"],
            "variable": ["assignment"],
            "import": ["import_statement", "import_from_statement"],
            "method": ["function_definition"],
        }
    ),
    LanguageType.C: LanguageConfig(
        name="c",
        grammar_file="c.so",
        file_extensions=[".c", ".h"],
        symbol_patterns={
            "function": ["function_definition"],
            "struct": ["struct_specifier"],
            "enum": ["enum_specifier"],
            "typedef": ["type_definition"],
            "macro": ["preproc_def"],
            "variable": ["declaration"],
        }
    ),
    LanguageType.CPP: LanguageConfig(
        name="cpp",
        grammar_file="cpp.so",
        file_extensions=[".cpp", ".hpp", ".cc", ".hh"],
        symbol_patterns={
            "function": ["function_definition", "method_definition"],
            "class": ["class_specifier"],
            "struct": ["struct_specifier"],
            "enum": ["enum_specifier"],
            "namespace": ["namespace_definition"],
            "template": ["template_declaration"],
            "variable": ["declaration"],
        }
    ),
    LanguageType.GO: LanguageConfig(
        name="go",
        grammar_file="go.so",
        file_extensions=[".go"],
        symbol_patterns={
            "function": ["function_declaration", "method_declaration"],
            "struct": ["type_declaration"],
            "interface": ["type_declaration"],
            "package": ["package_clause"],
            "import": ["import_declaration"],
            "variable": ["var_declaration", "short_var_declaration"],
        }
    ),
    LanguageType.RUST: LanguageConfig(
        name="rust",
        grammar_file="rust.so",
        file_extensions=[".rs"],
        symbol_patterns={
            "function": ["function_item"],
            "struct": ["struct_item"],
            "enum": ["enum_item"],
            "trait": ["trait_item"],
            "impl": ["impl_item"],
            "module": ["mod_item"],
            "variable": ["let_declaration", "const_item", "static_item"],
        }
    ),
}

def detect_language(file_path: str) -> Optional[LanguageType]:
    """Detect the programming language of a file based on its extension.
    
    Args:
        file_path: Path to the source file
        
    Returns:
        The detected language type or None if not supported
    """
    extension = file_path.lower().split('.')[-1]
    for lang_type, config in LANGUAGE_CONFIGS.items():
        if f".{extension}" in config.file_extensions:
            return lang_type
    return None

def get_language_config(lang_type: LanguageType) -> LanguageConfig:
    """Get the configuration for a specific language.
    
    Args:
        lang_type: The language type
        
    Returns:
        The language configuration
    """
    return LANGUAGE_CONFIGS[lang_type] 