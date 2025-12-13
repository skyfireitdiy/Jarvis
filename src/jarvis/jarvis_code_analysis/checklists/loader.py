# -*- coding: utf-8 -*-
"""
Utility module for loading language-specific code review checklists.
"""

from typing import Dict
from typing import Optional

# Import checklist modules
from jarvis.jarvis_code_analysis.checklists import c_cpp
from jarvis.jarvis_code_analysis.checklists import csharp
from jarvis.jarvis_code_analysis.checklists import data_format
from jarvis.jarvis_code_analysis.checklists import devops
from jarvis.jarvis_code_analysis.checklists import docs
from jarvis.jarvis_code_analysis.checklists import go
from jarvis.jarvis_code_analysis.checklists import infrastructure
from jarvis.jarvis_code_analysis.checklists import java
from jarvis.jarvis_code_analysis.checklists import javascript
from jarvis.jarvis_code_analysis.checklists import kotlin
from jarvis.jarvis_code_analysis.checklists import php
from jarvis.jarvis_code_analysis.checklists import python
from jarvis.jarvis_code_analysis.checklists import ruby
from jarvis.jarvis_code_analysis.checklists import rust
from jarvis.jarvis_code_analysis.checklists import shell
from jarvis.jarvis_code_analysis.checklists import sql
from jarvis.jarvis_code_analysis.checklists import swift
from jarvis.jarvis_code_analysis.checklists import web

# Map of language identifiers to their checklist content
CHECKLIST_MAP = {
    "c_cpp": c_cpp.CHECKLIST,
    "go": go.CHECKLIST,
    "python": python.CHECKLIST,
    "rust": rust.CHECKLIST,
    "java": java.CHECKLIST,
    "javascript": javascript.CHECKLIST,
    "typescript": javascript.CHECKLIST,  # TypeScript uses the same checklist as JavaScript
    "csharp": csharp.CHECKLIST,
    "swift": swift.CHECKLIST,
    "php": php.CHECKLIST,
    "shell": shell.CHECKLIST,
    "sql": sql.CHECKLIST,
    "ruby": ruby.CHECKLIST,
    "kotlin": kotlin.CHECKLIST,
    "html": web.CHECKLIST,
    "css": web.CHECKLIST,
    "xml": data_format.CHECKLIST,
    "json": data_format.CHECKLIST,
    "yaml": data_format.CHECKLIST,
    "docker": infrastructure.CHECKLIST,
    "terraform": infrastructure.CHECKLIST,
    "markdown": docs.CHECKLIST,
    "docs": docs.CHECKLIST,
    "makefile": devops.CHECKLIST,
    "devops": devops.CHECKLIST,
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
