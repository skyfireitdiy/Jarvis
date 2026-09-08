# -*- coding: utf-8 -*-
"""Java language symbol extractor."""

from typing import Any
from typing import Optional

from jarvis.jarvis_agent.file_context_handler import register_language_extractor


def create_java_extractor() -> Optional[Any]:
    """Create Java symbol extractor using tree-sitter."""
    try:
        from jarvis.jarvis_code_agent.code_analyzer.languages.java_language import (
            JavaSymbolExtractor,
        )

        return JavaSymbolExtractor()
    except (ImportError, RuntimeError, Exception):
        # 如果 code_analyzer 中没有 Java 支持，尝试直接使用 tree-sitter
        try:
            import tree_sitter_java
            from tree_sitter import Language
            from tree_sitter import Parser

            from jarvis.jarvis_code_agent.code_analyzer.symbol_extractor import Symbol

            JAVA_LANGUAGE = tree_sitter_java.language()
            JAVA_SYMBOL_QUERY = """
            (method_declaration
              name: (identifier) @method.name)
            
            (class_declaration
              name: (identifier) @class.name)
            
            (interface_declaration
              name: (identifier) @interface.name)
            
            (field_declaration
              (variable_declarator
                name: (identifier) @field.name))
            """

            class TreeSitterJavaSymbolExtractor:
                def __init__(self) -> None:
                    # 如果传入的是 PyCapsule，需要转换为 Language 对象
                    if not isinstance(JAVA_LANGUAGE, Language):
                        self.language = Language(JAVA_LANGUAGE)
                    else:
                        self.language = JAVA_LANGUAGE
                    self.parser = Parser()
                    # 使用 language 属性而不是 set_language 方法
                    self.parser.language = self.language
                    self.symbol_query = JAVA_SYMBOL_QUERY

                def extract_symbols(
                    self, file_path: str, content: str
                ) -> list[dict[str, str]]:
                    try:
                        from tree_sitter import Query, QueryCursor

                        tree = self.parser.parse(bytes(content, "utf8"))
                        query = Query(self.language, self.symbol_query)
                        cursor = QueryCursor(query)
                        captures = cursor.captures(tree.root_node)

                        kind_map = {
                            "method.name": "method",
                            "class.name": "class",
                            "interface.name": "interface",
                            "field.name": "field",
                        }
                        symbols = []
                        for name, nodes in captures.items():
                            symbol_kind = kind_map.get(name)
                            if not symbol_kind:
                                continue
                            for node in nodes:
                                symbol = Symbol(
                                    name=(node.text or b"").decode("utf8"),
                                    kind=symbol_kind,
                                    file_path=file_path,
                                    line_start=node.start_point[0] + 1,
                                    line_end=node.end_point[0] + 1,
                                )
                                symbols.append(
                                    {
                                        "name": symbol.name,
                                        "kind": symbol.kind,
                                        "file_path": symbol.file_path,
                                        "line_start": str(symbol.line_start),
                                        "line_end": str(symbol.line_end),
                                    }
                                )
                        return symbols
                    except Exception:
                        return []

            return TreeSitterJavaSymbolExtractor()
        except (ImportError, Exception):
            return None


def register_java_extractor() -> None:
    """Register Java extractor for .java files."""
    register_language_extractor(".java", create_java_extractor)
