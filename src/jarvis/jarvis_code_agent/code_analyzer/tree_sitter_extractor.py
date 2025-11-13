from abc import abstractmethod
from typing import List, Optional

from tree_sitter import Language, Parser, Node, Query, QueryCursor

from .symbol_extractor import Symbol, SymbolExtractor


class TreeSitterExtractor(SymbolExtractor):
    """
    A generic symbol extractor that uses tree-sitter for parsing.
    Subclasses must provide the language-specific details, such as the
    tree-sitter Language object and the symbol query.
    """

    def __init__(self, language: Language, symbol_query: str):
        # 如果传入的是 PyCapsule，需要转换为 Language 对象
        if not isinstance(language, Language):
            language = Language(language)
        self.language = language
        self.parser = Parser()
        # 使用 language 属性而不是 set_language 方法
        self.parser.language = self.language
        self.symbol_query = symbol_query

    def extract_symbols(self, file_path: str, content: str) -> List[Symbol]:
        """
        Parses the code with tree-sitter and extracts symbols based on the query.
        """
        try:
            tree = self.parser.parse(bytes(content, "utf8"))
            # 使用 Query 构造函数（新 API）
            query = Query(self.language, self.symbol_query)
            # 使用 QueryCursor 执行查询
            cursor = QueryCursor(query)
            matches = cursor.matches(tree.root_node)
            
            symbols = []
            # matches 返回格式: [(pattern_index, {capture_name: [nodes]})]
            for pattern_index, captures_dict in matches:
                for capture_name, nodes in captures_dict.items():
                    for node in nodes:
                        symbol = self._create_symbol_from_capture(node, capture_name, file_path)
                        if symbol:
                            symbols.append(symbol)
            return symbols
        except Exception as e:
            print(f"Error extracting symbols from {file_path} with tree-sitter: {e}")
            return []

    @abstractmethod
    def _create_symbol_from_capture(self, node: Node, name: str, file_path: str) -> Optional[Symbol]:
        """
        Creates a Symbol object from a tree-sitter query capture.
        This method must be implemented by subclasses to map capture names
        (e.g., "function.name") to Symbol attributes.
        """
        raise NotImplementedError