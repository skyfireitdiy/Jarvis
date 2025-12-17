from abc import abstractmethod
from typing import List
from typing import Optional

from tree_sitter import Language
from tree_sitter import Node
from tree_sitter import Parser
from tree_sitter import Query
from tree_sitter import QueryCursor

from jarvis.jarvis_utils.output import PrettyOutput

from .symbol_extractor import Symbol
from .symbol_extractor import SymbolExtractor


class TreeSitterExtractor(SymbolExtractor):
    """
    A generic symbol extractor that uses tree-sitter for parsing.
    Subclasses must provide the language-specific details, such as the
    tree-sitter Language object and the symbol query.
    """

    def __init__(self, language: Language, symbol_query: str):
        self.language = language
        self.parser = Parser()
        # 设置language（tree-sitter的Parser需要Language对象）
        try:
            # 尝试使用set_language方法（如果可用）
            if hasattr(self.parser, "set_language"):
                self.parser.set_language(self.language)
            else:
                # 否则直接赋值language属性
                self.parser.language = self.language
        except (AttributeError, TypeError):
            # 如果都失败，尝试创建Language对象
            try:
                from tree_sitter import Language as LangClass

                try:
                    lang_obj = LangClass(language)
                    self.parser.language = lang_obj
                    self.language = lang_obj
                except Exception:
                    self.parser.language = language
            except Exception:
                # 最后的fallback：直接赋值
                self.parser.language = language
        self.symbol_query = symbol_query

    def extract_symbols(self, file_path: str, content: str) -> List[Symbol]:
        """
        Parses the code with tree-sitter and extracts symbols based on the query.
        """
        # 检查内容是否为空或只包含空白
        if not content or not content.strip():
            return []

        symbols = []

        try:
            # 解析代码（即使有语法错误，tree-sitter也能部分解析）
            tree = self.parser.parse(bytes(content, "utf8"))

            # tree-sitter parse方法总是返回有效的tree对象
            # 无需检查None值，继续处理

            # 尝试构造查询
            query = None
            try:
                query = Query(self.language, self.symbol_query)
            except Exception as query_error:
                # Query 构造失败（可能是查询语法问题），静默返回空列表
                import os

                if os.getenv("DEBUG_TREE_SITTER", "").lower() in ("1", "true", "yes"):
                    PrettyOutput.auto_print(
                        f"Error creating query for {file_path}: {query_error}"
                    )
                return []

            # 使用 QueryCursor 执行查询
            # 即使有语法错误，tree-sitter也能部分解析，所以可以提取部分符号
            cursor = QueryCursor(query)
            matches = cursor.matches(tree.root_node)

            # matches 返回格式: [(pattern_index, {capture_name: [nodes]})]
            for pattern_index, captures_dict in matches:
                for capture_name, nodes in captures_dict.items():
                    for node in nodes:
                        try:
                            # 跳过错误节点（tree-sitter会用ERROR节点标记语法错误）
                            # 错误节点通常没有有效的文本内容或位置信息
                            if node.type == "ERROR":
                                continue

                            symbol = self._create_symbol_from_capture(
                                node, capture_name, file_path
                            )
                            if symbol:
                                symbols.append(symbol)
                        except Exception:
                            # 单个符号提取失败，继续处理其他符号
                            # 这样可以确保即使部分符号提取失败，也能返回已成功提取的符号
                            continue

            # 即使有语法错误，也返回已成功提取的符号
            return symbols
        except Exception as e:
            # 如果解析完全失败（不是语法错误，而是其他严重错误），返回空列表
            # 只在调试模式下打印错误信息
            import os

            if os.getenv("DEBUG_TREE_SITTER", "").lower() in ("1", "true", "yes"):
                PrettyOutput.auto_print(
                    f"Error extracting symbols from {file_path} with tree-sitter: {e}"
                )
            # 即使解析失败，也返回已提取的符号（如果有的话）
            return symbols

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
