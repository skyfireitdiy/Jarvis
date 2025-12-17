# -*- coding: utf-8 -*-
"""JavaScript language symbol extractor."""

from typing import Any
from typing import List
from typing import Optional

from jarvis.jarvis_agent.file_context_handler import register_language_extractor


def create_javascript_extractor() -> Optional[Any]:
    """Create JavaScript symbol extractor using tree-sitter."""
    try:
        import tree_sitter_javascript
        from tree_sitter import Language
        from tree_sitter import Parser

        from jarvis.jarvis_code_agent.code_analyzer.symbol_extractor import Symbol

        JS_LANGUAGE = tree_sitter_javascript.language()
        JS_SYMBOL_QUERY = """
        (function_declaration
          name: (identifier) @function.name)
        
        (method_definition
          name: (property_identifier) @method.name)
        
        (class_declaration
          name: (identifier) @class.name)
        
        (variable_declaration
          (variable_declarator
            name: (identifier) @variable.name))
        """

        class JSSymbolExtractor:
            def __init__(self) -> None:
                # 如果传入的是 PyCapsule，需要转换为 Language 对象
                if not isinstance(JS_LANGUAGE, Language):
                    self.language = Language(JS_LANGUAGE)
                else:
                    self.language = JS_LANGUAGE
                self.parser = Parser()
                # 使用 language 属性而不是 set_language 方法
                self.parser.language = self.language
                self.symbol_query = JS_SYMBOL_QUERY

            def extract_symbols(self, file_path: str, content: str) -> List[Any]:
                try:
                    tree = self.parser.parse(bytes(content, "utf8"))
                    query = self.language.query(self.symbol_query)
                    captures = query.captures(tree.root_node)  # type: ignore[attr-defined]

                    symbols = []
                    for node, name in captures:
                        kind_map = {
                            "function.name": "function",
                            "method.name": "method",
                            "class.name": "class",
                            "variable.name": "variable",
                        }
                        symbol_kind = kind_map.get(name)
                        if symbol_kind:
                            symbols.append(
                                Symbol(
                                    name=node.text.decode("utf8"),
                                    kind=symbol_kind,
                                    file_path=file_path,
                                    line_start=node.start_point[0] + 1,
                                    line_end=node.end_point[0] + 1,
                                )
                            )
                    return symbols
                except Exception:
                    return []

        return JSSymbolExtractor()
    except (ImportError, Exception):
        return None


def register_javascript_extractor() -> None:
    """Register JavaScript extractor for .js and .jsx files."""
    register_language_extractor([".js", ".jsx"], create_javascript_extractor)
