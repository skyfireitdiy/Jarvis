"""Python语言支持实现。"""

import ast
import os
from typing import List
from typing import Optional
from typing import Set
from typing import Union

from ..base_language import BaseLanguageSupport
from ..dependency_analyzer import Dependency
from ..dependency_analyzer import DependencyAnalyzer
from ..dependency_analyzer import DependencyGraph
from ..file_ignore import filter_walk_dirs
from ..symbol_extractor import Symbol
from ..symbol_extractor import SymbolExtractor


class PythonSymbolExtractor(SymbolExtractor):
    """Extracts symbols from Python code using the AST module."""

    def extract_symbols(self, file_path: str, content: str) -> List[Symbol]:
        symbols: List[Symbol] = []
        try:
            # 对于超大文件，限制解析内容长度（避免内存和性能问题）
            # 只解析前 50000 行，通常足够提取主要符号
            max_lines = 50000
            lines = content.split("\n")
            if len(lines) > max_lines:
                content = "\n".join(lines[:max_lines])

            tree = ast.parse(content, filename=file_path)
            self._traverse_node(tree, file_path, symbols, parent_name=None)
        except SyntaxError:
            # 静默跳过语法错误文件（可能是部分代码片段或测试文件）
            pass
        except Exception:
            # 静默跳过其他解析错误（如内存不足等）
            pass
        return symbols

    def _traverse_node(
        self,
        node: ast.AST,
        file_path: str,
        symbols: List[Symbol],
        parent_name: Optional[str],
    ) -> None:
        if isinstance(node, ast.FunctionDef):
            # Extract decorators before the function
            if node.decorator_list:
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name):
                        decorator_symbol = Symbol(
                            name=decorator.id,
                            kind="decorator",
                            file_path=file_path,
                            line_start=decorator.lineno,
                            line_end=decorator.lineno,
                            parent=parent_name,
                        )
                        symbols.append(decorator_symbol)
            symbol = self._create_symbol_from_func(node, file_path, parent_name)
            symbols.append(symbol)
            parent_name = node.name
        elif isinstance(node, ast.AsyncFunctionDef):
            # Extract decorators before the async function
            if node.decorator_list:
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name):
                        decorator_symbol = Symbol(
                            name=decorator.id,
                            kind="decorator",
                            file_path=file_path,
                            line_start=decorator.lineno,
                            line_end=decorator.lineno,
                            parent=parent_name,
                        )
                        symbols.append(decorator_symbol)
            symbol = self._create_symbol_from_func(
                node, file_path, parent_name, is_async=True
            )
            symbols.append(symbol)
            parent_name = node.name
        elif isinstance(node, ast.ClassDef):
            # Extract decorators before the class
            if node.decorator_list:
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name):
                        decorator_symbol = Symbol(
                            name=decorator.id,
                            kind="decorator",
                            file_path=file_path,
                            line_start=decorator.lineno,
                            line_end=decorator.lineno,
                            parent=parent_name,
                        )
                        symbols.append(decorator_symbol)
            symbol = self._create_symbol_from_class(node, file_path, parent_name)
            symbols.append(symbol)
            parent_name = node.name
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            symbols.extend(
                self._create_symbols_from_import(node, file_path, parent_name)
            )

        for child in ast.iter_child_nodes(node):
            self._traverse_node(child, file_path, symbols, parent_name=parent_name)

    def _create_symbol_from_func(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        file_path: str,
        parent: Optional[str],
        is_async: bool = False,
    ) -> Symbol:
        signature = f"{'async ' if is_async else ''}def {node.name}(...)"
        return Symbol(
            name=node.name,
            kind="function",
            file_path=file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            signature=signature,
            docstring=ast.get_docstring(node),
            parent=parent,
        )

    def _create_symbol_from_class(
        self, node: ast.ClassDef, file_path: str, parent: Optional[str]
    ) -> Symbol:
        return Symbol(
            name=node.name,
            kind="class",
            file_path=file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            docstring=ast.get_docstring(node),
            parent=parent,
        )

    def _create_symbols_from_import(
        self,
        node: Union[ast.Import, ast.ImportFrom],
        file_path: str,
        parent: Optional[str],
    ) -> List[Symbol]:
        symbols = []
        for alias in node.names:
            symbols.append(
                Symbol(
                    name=alias.asname or alias.name,
                    kind="import",
                    file_path=file_path,
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    parent=parent,
                )
            )
        return symbols


class PythonDependencyAnalyzer(DependencyAnalyzer):
    """Analyzes Python import dependencies using AST."""

    def analyze_imports(self, file_path: str, content: str) -> List[Dependency]:
        """Analyzes Python import statements."""
        dependencies: List[Dependency] = []

        try:
            tree = ast.parse(content, filename=file_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    # import module
                    for alias in node.names:
                        dependencies.append(
                            Dependency(
                                from_module=alias.name,
                                imported_symbol=None,
                                file_path=file_path,
                                line=node.lineno,
                            )
                        )
                elif isinstance(node, ast.ImportFrom):
                    # from module import symbol
                    module = node.module or ""
                    for alias in node.names:
                        dependencies.append(
                            Dependency(
                                from_module=module,
                                imported_symbol=alias.name,
                                file_path=file_path,
                                line=node.lineno,
                            )
                        )
        except SyntaxError:
            # Skip files with syntax errors
            pass

        return dependencies

    def build_dependency_graph(self, project_root: str) -> DependencyGraph:
        """Builds a dependency graph for a Python project."""
        graph = DependencyGraph()

        # Walk through all Python files
        for root, dirs, files in os.walk(project_root):
            # Skip hidden directories and common ignore patterns
            dirs[:] = filter_walk_dirs(dirs)

            for file in files:
                if not file.endswith(".py"):
                    continue

                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()

                    dependencies = self.analyze_imports(file_path, content)
                    for dep in dependencies:
                        # Resolve module to file path
                        dep_path = self._resolve_module_path(
                            project_root, dep.from_module, file_path
                        )
                        if dep_path and dep_path != file_path:
                            graph.add_dependency(file_path, dep_path)
                except Exception:
                    continue

        return graph

    def _resolve_module_path(
        self, project_root: str, module_name: str, from_file: str
    ) -> Optional[str]:
        """Resolve a Python module name to a file path."""
        if not module_name:
            return None

        # Handle relative imports
        if module_name.startswith("."):
            # Relative import - resolve from the importing file's directory
            base_dir = os.path.dirname(from_file)
            parts = module_name.split(".")
            depth = len([p for p in parts if p == ""])
            module_parts = [p for p in parts if p]

            # Navigate up directories
            current_dir = base_dir
            for _ in range(depth - 1):
                current_dir = os.path.dirname(current_dir)

            if module_parts:
                module_path = os.path.join(current_dir, *module_parts)
            else:
                module_path = current_dir

            # Try to find the module file
            if os.path.isdir(module_path):
                init_path = os.path.join(module_path, "__init__.py")
                if os.path.exists(init_path):
                    return init_path
            elif os.path.exists(module_path + ".py"):
                return module_path + ".py"
        else:
            # Absolute import
            parts = module_name.split(".")

            # Search in project root
            for root, dirs, files in os.walk(project_root):
                # Skip hidden directories and common ignore patterns
                dirs[:] = filter_walk_dirs(dirs)

                if parts[0] in dirs or f"{parts[0]}.py" in files:
                    module_path = os.path.join(root, *parts)

                    if os.path.isdir(module_path):
                        init_path = os.path.join(module_path, "__init__.py")
                        if os.path.exists(init_path):
                            return init_path
                    elif os.path.exists(module_path + ".py"):
                        return module_path + ".py"
                    break

        return None

    def _is_source_file(self, file_path: str) -> bool:
        """Check if a file is a Python source file."""
        return file_path.endswith(".py")


class PythonLanguageSupport(BaseLanguageSupport):
    """Python语言支持类。"""

    @property
    def language_name(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> Set[str]:
        return {".py", ".pyw", ".pyi"}

    def create_symbol_extractor(self) -> Optional[SymbolExtractor]:
        return PythonSymbolExtractor()

    def create_dependency_analyzer(self) -> Optional[DependencyAnalyzer]:
        return PythonDependencyAnalyzer()
