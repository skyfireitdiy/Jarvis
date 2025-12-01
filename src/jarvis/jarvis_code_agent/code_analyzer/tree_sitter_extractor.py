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
        # 检查内容是否为空或只包含空白
        if not content or not content.strip():
            return []
        
        try:
            # 解析代码
            tree = self.parser.parse(bytes(content, "utf8"))
            
            # 检查解析是否成功（tree.root_node 应该存在）
            if not tree or not tree.root_node:
                return []
            
            # 尝试构造查询
            try:
                query = Query(self.language, self.symbol_query)
            except Exception as query_error:
                # Query 构造失败（可能是查询语法问题），静默返回空列表
                import os
                if os.getenv("DEBUG_TREE_SITTER", "").lower() in ("1", "true", "yes"):
                    print(f"Error creating query for {file_path}: {query_error}")
                return []
            
            # 使用 QueryCursor 执行查询
            cursor = QueryCursor(query)
            matches = cursor.matches(tree.root_node)

            symbols = []
            # matches 返回格式: [(pattern_index, {capture_name: [nodes]})]
            for pattern_index, captures_dict in matches:
                for capture_name, nodes in captures_dict.items():
                    for node in nodes:
                        try:
                            symbol = self._create_symbol_from_capture(
                                node, capture_name, file_path
                            )
                            if symbol:
                                symbols.append(symbol)
                        except Exception:
                            # 单个符号提取失败，继续处理其他符号
                            continue
            return symbols
        except Exception as e:
            # 静默处理解析错误（可能是语法错误、文件损坏等）
            # 只在调试模式下打印错误信息
            import os
            if os.getenv("DEBUG_TREE_SITTER", "").lower() in ("1", "true", "yes"):
                print(f"Error extracting symbols from {file_path} with tree-sitter: {e}")
            return []

    @abstractmethod
    def _create_symbol_from_capture(
        self, node: Node, name: str, file_path: str
    ) -> Optional[Symbol]:
        """
        Creates a Symbol object from a tree-sitter query capture.
        This method must be implemented by subclasses to map capture names
        (e.g., "function.name") to Symbol attributes.
        """
        raise NotImplementedError
