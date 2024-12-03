# -*- coding: utf-8 -*-
"""Language extractors for file context handler.

This module automatically registers all language extractors.
"""

# Import all language extractors to trigger registration
try:
    from .python_extractor import register_python_extractor

    register_python_extractor()
except (ImportError, Exception):
    pass

try:
    from .rust_extractor import register_rust_extractor

    register_rust_extractor()
except (ImportError, Exception):
    pass

try:
    from .go_extractor import register_go_extractor

    register_go_extractor()
except (ImportError, Exception):
    pass

try:
    from .c_extractor import register_c_extractor

    register_c_extractor()
except (ImportError, Exception):
    pass

try:
    from .cpp_extractor import register_cpp_extractor

    register_cpp_extractor()
except (ImportError, Exception):
    pass

try:
    from .javascript_extractor import register_javascript_extractor

    register_javascript_extractor()
except (ImportError, Exception):
    pass

try:
    from .typescript_extractor import register_typescript_extractor

    register_typescript_extractor()
except (ImportError, Exception):
    pass

try:
    from .java_extractor import register_java_extractor

    register_java_extractor()
except (ImportError, Exception):
    pass

__all__ = []
