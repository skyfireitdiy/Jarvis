# -*- coding: utf-8 -*-
"""
Shared types for jarvis.jarvis_sec to avoid circular imports.
"""

from dataclasses import dataclass


@dataclass
class Issue:
    language: str
    category: str
    pattern: str
    file: str
    line: int
    evidence: str
    description: str
    suggestion: str
    confidence: float
    severity: str = "medium"


__all__ = ["Issue"]
