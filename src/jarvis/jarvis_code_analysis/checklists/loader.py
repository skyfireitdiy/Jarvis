"""
Utility module for loading language-specific code review checklists.
"""
from typing import Dict, Optional

# Import checklist modules
from jarvis.jarvis_code_analysis.checklists import (
    c_cpp, 
    go, 
    python, 
    rust,
    java,
    javascript,
    csharp,
    swift,
    php,
    shell,
    sql,
    ruby,
    kotlin,
    web,
    data_format,
    infrastructure,
    docs,
    devops
)

# Map of language identifiers to their checklist content
CHECKLIST_MAP = {
    'c_cpp': c_cpp.CHECKLIST,
    'go': go.CHECKLIST,
    'python': python.CHECKLIST,
    'rust': rust.CHECKLIST,
    'java': java.CHECKLIST,
    'javascript': javascript.CHECKLIST,
    'typescript': javascript.CHECKLIST,  # TypeScript uses the same checklist as JavaScript
    'csharp': csharp.CHECKLIST,
    'swift': swift.CHECKLIST,
    'php': php.CHECKLIST,
    'shell': shell.CHECKLIST,
    'sql': sql.CHECKLIST,
    'ruby': ruby.CHECKLIST,
    'kotlin': kotlin.CHECKLIST,
    'html': web.CHECKLIST,
    'css': web.CHECKLIST,
    'xml': data_format.CHECKLIST,
    'json': data_format.CHECKLIST,
    'yaml': data_format.CHECKLIST,
    'docker': infrastructure.CHECKLIST,
    'terraform': infrastructure.CHECKLIST,
    'markdown': docs.CHECKLIST,
    'docs': docs.CHECKLIST,
    'makefile': devops.CHECKLIST,
    'devops': devops.CHECKLIST,
}

def get_language_checklist(language: str) -> Optional[str]:
    """
    Get the checklist for a specific language.
    
    Args:
        language: The language identifier ('c_cpp', 'go', 'python', 'rust', etc.)
        
    Returns:
        The checklist content as a string, or None if not found
    """
    return CHECKLIST_MAP.get(language)

def get_all_checklists() -> Dict[str, str]:
    """
    Get all available language checklists.
    
    Returns:
        Dictionary mapping language identifiers to their checklist content
    """
    return CHECKLIST_MAP 