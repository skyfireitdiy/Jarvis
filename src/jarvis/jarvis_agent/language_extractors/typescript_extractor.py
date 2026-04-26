# -*- coding: utf-8 -*-
"""TypeScript language symbol extractor."""

from typing import Any
from typing import List
from typing import Optional

from jarvis.jarvis_agent.file_context_handler import register_language_extractor


def create_typescript_extractor() -> Optional[Any]:
    """Create TypeScript symbol extractor using tree-sitter."""
    try:
        import tree_sitter_typescript
        from tree_sitter import Language
        from tree_sitter import Parser

        from jarvis.jarvis_code_agent.code_analyzer.symbol_extractor import Symbol

        # tree-sitter-typescript 使用 language_typescript() 和 language_tsx()
        TS_LANGUAGE = tree_sitter_typescript.language_typescript()
        TS_SYMBOL_QUERY = """
        (function_declaration
          name: (identifier) @function.name)
        
        (method_definition
          name: (property_identifier) @method.name)
        
        (class_declaration
          name: (type_identifier) @class.name)
        
        (interface_declaration
          name: (type_identifier) @interface.name)
        
        (variable_declaration
          (variable_declarator
            name: (identifier) @variable.name))
        """

        class TSSymbolExtractor:
            def __init__(self) -> None:
                # 如果传入的是 PyCapsule，需要转换为 Language 对象
                if not isinstance(TS_LANGUAGE, Language):
                    self.language = Language(TS_LANGUAGE)
                else:
                    self.language = TS_LANGUAGE
                self.parser = Parser()
                # 使用 language 属性而不是 set_language 方法
                self.parser.language = self.language
                self.symbol_query = TS_SYMBOL_QUERY

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
                            "interface.name": "interface",
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

        return TSSymbolExtractor()
    except (ImportError, Exception):
        return None


def register_typescript_extractor() -> None:
    """Register TypeScript extractor for .ts and .tsx files."""
    register_language_extractor([".ts", ".tsx"], create_typescript_extractor)
