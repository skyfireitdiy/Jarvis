from abc import abstractmethod
from typing import List, Optional

from tree_sitter import Language, Parser, Node

from .symbol_extractor import Symbol, SymbolExtractor


class TreeSitterExtractor(SymbolExtractor):
    """
    A generic symbol extractor that uses tree-sitter for parsing.
    Subclasses must provide the language-specific details, such as the
    tree-sitter Language object and the symbol query.
    """

    def __init__(self, language: Language, symbol_query: str):
        self.language = language
        self.parser = Parser()
        self.parser.set_language(self.language)
        self.symbol_query = symbol_query

    def extract_symbols(self, file_path: str, content: str) -> List[Symbol]:
        """
        Parses the code with tree-sitter and extracts symbols based on the query.
        """
        try:
            tree = self.parser.parse(bytes(content, "utf8"))
            query = self.language.query(self.symbol_query)
            captures = query.captures(tree.root_node)
            
            symbols = []
            for node, name in captures:
                symbol = self._create_symbol_from_capture(node, name, file_path)
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