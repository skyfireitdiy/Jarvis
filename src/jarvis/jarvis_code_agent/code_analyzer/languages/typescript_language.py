"""TypeScript语言支持实现。"""

import os
import re
from typing import List
from typing import Optional
from typing import Set
from typing import cast

from ..base_language import BaseLanguageSupport
from ..dependency_analyzer import Dependency
from ..dependency_analyzer import DependencyAnalyzer
from ..dependency_analyzer import DependencyGraph
from ..file_ignore import filter_walk_dirs
from ..symbol_extractor import Symbol
from ..symbol_extractor import SymbolExtractor
from ..tree_sitter_extractor import TreeSitterExtractor

try:
    import tree_sitter_typescript
    from tree_sitter import Language
    from tree_sitter import Node

    TS_LANGUAGE: Optional[Language] = cast(
        Optional[Language], tree_sitter_typescript.language_typescript()
    )
except (ImportError, Exception):
    TS_LANGUAGE = None


# --- TypeScript Symbol Extractor ---

TS_SYMBOL_QUERY = """
(function_declaration
  name: (identifier) @function.name)

(function_expression
  name: (identifier) @function.name)

(generator_function_declaration
  name: (identifier) @generator.name)

(generator_function
  name: (identifier) @generator.name)

(arrow_function) @arrow.function

(method_definition
  name: (property_identifier) @method.name)

(class_declaration
  name: (type_identifier) @class.name)

(class_expression
  name: (type_identifier) @class.name)

(interface_declaration
  name: (type_identifier) @interface.name)

(enum_declaration
  name: (identifier) @enum.name)

(type_alias_declaration
  name: (type_identifier) @type.name)

(namespace_declaration
  name: (identifier) @namespace.name)

(variable_declaration
  (variable_declarator
    name: (identifier) @variable.name))

(decorator) @decorator
"""


class TypeScriptSymbolExtractor(TreeSitterExtractor):
    """Extracts symbols from TypeScript code using tree-sitter."""

    def __init__(self) -> None:
        if not TS_LANGUAGE:
            raise RuntimeError("TypeScript tree-sitter grammar not available.")
        # 如果传入的是 PyCapsule，需要转换为 Language 对象
        lang = Language(TS_LANGUAGE)
        super().__init__(lang, TS_SYMBOL_QUERY)

    def _create_symbol_from_capture(
        self, node: Node, name: str, file_path: str
    ) -> Optional[Symbol]:
        """Maps a tree-sitter capture to a Symbol object."""
        kind_map = {
            "function.name": "function",
            "arrow.function": "function",
            "generator.name": "function",
            "method.name": "method",
            "class.name": "class",
            "interface.name": "interface",
            "enum.name": "enum",
            "type.name": "type",
            "namespace.name": "namespace",
            "variable.name": "variable",
            "decorator": "decorator",
        }

        symbol_kind = kind_map.get(name)
        if not symbol_kind:
            return None

        # For arrow functions without names, use a generated name
        if name == "arrow.function":
            symbol_name = "<anonymous_arrow_function>"
        elif name == "decorator":
            # Extract decorator name (e.g., @Component -> Component)
            if node.text is None:
                return None
            decorator_text = node.text.decode("utf8").strip()
            if decorator_text.startswith("@"):
                symbol_name = decorator_text[1:].split("(")[0].strip()
            else:
                symbol_name = decorator_text.split("(")[0].strip()
        elif name == "generator.name":
            if node.text is None:
                return None
            symbol_name = node.text.decode("utf8")
        else:
            if node.text is None:
                return None
            symbol_name = node.text.decode("utf8")

        if not symbol_name:
            return None

        return Symbol(
            name=symbol_name,
            kind=symbol_kind,
            file_path=file_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
        )


# --- TypeScript Dependency Analyzer ---


class TypeScriptDependencyAnalyzer(DependencyAnalyzer):
    """Analyzes TypeScript import dependencies."""

    def analyze_imports(self, file_path: str, content: str) -> List[Dependency]:
        """Analyzes TypeScript import statements."""
        dependencies: List[Dependency] = []

        # ES6 import statements (same as JavaScript)
        # import module from 'path'
        # import { symbol } from 'path'
        # import * as alias from 'path'
        # import type { Type } from 'path'
        import_pattern = re.compile(
            r'import\s+(?:type\s+)?(?:(?:\*\s+as\s+(\w+)|(\{[^}]*\})|(\w+))\s+from\s+)?["\']([^"\']+)["\']',
            re.MULTILINE,
        )

        # CommonJS require statements
        require_pattern = re.compile(
            r'(?:const|let|var)\s+\w+\s*=\s*require\(["\']([^"\']+)["\']\)|require\(["\']([^"\']+)["\']\)',
            re.MULTILINE,
        )

        for line_num, line in enumerate(content.split("\n"), start=1):
            # Check for ES6 imports
            import_match = import_pattern.search(line)
            if import_match:
                module_path = import_match.group(4) or import_match.group(5)
                if module_path:
                    # Extract imported symbols if any
                    symbols_group = import_match.group(2) or import_match.group(1)
                    imported_symbol = None
                    if symbols_group and symbols_group.startswith("{"):
                        # Extract first symbol from { symbol1, symbol2 }
                        symbol_match = re.search(r"\{([^}]+)\}", symbols_group)
                        if symbol_match:
                            first_symbol = symbol_match.group(1).split(",")[0].strip()
                            imported_symbol = first_symbol.split(" as ")[0].strip()

                    dependencies.append(
                        Dependency(
                            from_module=module_path,
                            imported_symbol=imported_symbol,
                            file_path=file_path,
                            line=line_num,
                        )
                    )

            # Check for require statements
            require_match = require_pattern.search(line)
            if require_match:
                module_path = require_match.group(1) or require_match.group(2)
                if module_path:
                    dependencies.append(
                        Dependency(
                            from_module=module_path,
                            imported_symbol=None,
                            file_path=file_path,
                            line=line_num,
                        )
                    )

        return dependencies

    def build_dependency_graph(self, project_root: str) -> DependencyGraph:
        """Builds a dependency graph for a TypeScript project."""
        graph = DependencyGraph()

        for root, dirs, files in os.walk(project_root):
            dirs[:] = filter_walk_dirs(dirs)

            for file in files:
                if not file.endswith((".ts", ".tsx", ".cts", ".mts")):
                    continue

                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()

                    dependencies = self.analyze_imports(file_path, content)
                    for dep in dependencies:
                        # Skip node_modules and external packages
                        if dep.from_module.startswith(
                            (".", "/")
                        ) or not dep.from_module.startswith("http"):
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
        """Resolve a TypeScript module name to a file path."""
        if not module_name:
            return None

        # Handle relative imports
        if module_name.startswith("."):
            base_dir = os.path.dirname(from_file)
            # Resolve relative path
            if module_name.endswith((".ts", ".tsx")):
                # Direct file reference
                resolved = os.path.normpath(os.path.join(base_dir, module_name))
            else:
                # Try with .ts extension
                resolved = os.path.normpath(os.path.join(base_dir, module_name + ".ts"))
                if not os.path.exists(resolved):
                    # Try with .tsx extension
                    resolved = os.path.normpath(
                        os.path.join(base_dir, module_name + ".tsx")
                    )
                if not os.path.exists(resolved):
                    # Try index.ts
                    resolved = os.path.normpath(
                        os.path.join(base_dir, module_name, "index.ts")
                    )
                    if not os.path.exists(resolved):
                        resolved = os.path.normpath(
                            os.path.join(base_dir, module_name, "index.tsx")
                        )

            if os.path.exists(resolved) and os.path.isfile(resolved):
                return resolved

        # Handle absolute imports (from project root)
        if module_name.startswith("/"):
            resolved = os.path.normpath(
                os.path.join(project_root, module_name.lstrip("/"))
            )
            if not resolved.endswith((".ts", ".tsx")):
                resolved += ".ts"
            if os.path.exists(resolved) and os.path.isfile(resolved):
                return resolved

        # For node_modules and external packages, we can't resolve without package.json
        # Return None to skip them
        return None


# --- TypeScript Language Support ---


class TypeScriptLanguageSupport(BaseLanguageSupport):
    """TypeScript语言支持。"""

    @property
    def language_name(self) -> str:
        return "typescript"

    @property
    def file_extensions(self) -> Set[str]:
        return {".ts", ".tsx", ".cts", ".mts"}

    def create_symbol_extractor(self) -> Optional[SymbolExtractor]:
        if not TS_LANGUAGE:
            return None
        try:
            return TypeScriptSymbolExtractor()
        except Exception:
            return None

    def create_dependency_analyzer(self) -> Optional[DependencyAnalyzer]:
        return TypeScriptDependencyAnalyzer()
