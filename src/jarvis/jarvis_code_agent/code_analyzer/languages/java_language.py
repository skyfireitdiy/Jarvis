"""Java语言支持实现。"""

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
    import tree_sitter_java
    from tree_sitter import Language
    from tree_sitter import Node

    JAVA_LANGUAGE: Optional[Language] = cast(
        Optional[Language], tree_sitter_java.language()
    )
except (ImportError, Exception):
    JAVA_LANGUAGE = None


# --- Java Symbol Extractor ---

JAVA_SYMBOL_QUERY = """
(method_declaration
  name: (identifier) @method.name)

(class_declaration
  name: (identifier) @class.name)

(interface_declaration
  name: (identifier) @interface.name)

(enum_declaration
  name: (identifier) @enum.name)

(annotation_type_declaration
  name: (identifier) @annotation.name)

(field_declaration
  (variable_declarator
    name: (identifier) @field.name))

(constructor_declaration
  name: (identifier) @constructor.name)
"""


class JavaSymbolExtractor(TreeSitterExtractor):
    """Extracts symbols from Java code using tree-sitter."""

    def __init__(self) -> None:
        if not JAVA_LANGUAGE:
            raise RuntimeError("Java tree-sitter grammar not available.")
        # 如果传入的是 PyCapsule，需要转换为 Language 对象
        lang = Language(JAVA_LANGUAGE)
        super().__init__(lang, JAVA_SYMBOL_QUERY)

    def _create_symbol_from_capture(
        self, node: Node, name: str, file_path: str
    ) -> Optional[Symbol]:
        """Maps a tree-sitter capture to a Symbol object."""
        kind_map = {
            "method.name": "method",
            "class.name": "class",
            "interface.name": "interface",
            "enum.name": "enum",
            "annotation.name": "annotation",
            "field.name": "field",
            "constructor.name": "constructor",
        }

        symbol_kind = kind_map.get(name)
        if not symbol_kind:
            return None

        if node.text is None:
            return None

        return Symbol(
            name=node.text.decode("utf8"),
            kind=symbol_kind,
            file_path=file_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
        )


# --- Java Dependency Analyzer ---


class JavaDependencyAnalyzer(DependencyAnalyzer):
    """Analyzes Java import dependencies."""

    def analyze_imports(self, file_path: str, content: str) -> List[Dependency]:
        """Analyzes Java import statements."""
        dependencies: List[Dependency] = []

        # Java import statements
        # import package.Class;
        # import package.*;
        # import static package.Class.method;
        import_pattern = re.compile(
            r"import\s+(?:static\s+)?([\w.]+)(?:\.\*)?\s*;", re.MULTILINE
        )

        for line_num, line in enumerate(content.split("\n"), start=1):
            import_match = import_pattern.search(line)
            if import_match:
                module_path = import_match.group(1)
                if module_path:
                    # Extract class name if it's a specific import
                    parts = module_path.split(".")
                    imported_symbol = None
                    if len(parts) > 1 and not line.strip().endswith(".*;"):
                        # Specific class import
                        imported_symbol = parts[-1]
                        module_path = ".".join(parts[:-1])

                    dependencies.append(
                        Dependency(
                            from_module=module_path,
                            imported_symbol=imported_symbol,
                            file_path=file_path,
                            line=line_num,
                        )
                    )

        return dependencies

    def build_dependency_graph(self, project_root: str) -> DependencyGraph:
        """Builds a dependency graph for a Java project."""
        graph = DependencyGraph()

        for root, dirs, files in os.walk(project_root):
            dirs[:] = filter_walk_dirs(dirs)

            for file in files:
                if not file.endswith(".java"):
                    continue

                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()

                    dependencies = self.analyze_imports(file_path, content)
                    for dep in dependencies:
                        # Skip java.* and javax.* standard library packages
                        if not dep.from_module.startswith(("java.", "javax.")):
                            dep_path = self._resolve_module_path(
                                project_root,
                                dep.from_module,
                                dep.imported_symbol,
                                file_path,
                            )
                            if dep_path and dep_path != file_path:
                                graph.add_dependency(file_path, dep_path)
                except Exception:
                    continue

        return graph

    def _resolve_module_path(
        self,
        project_root: str,
        package_name: str,
        class_name: Optional[str],
        from_file: str,
    ) -> Optional[str]:
        """Resolve a Java package name to a file path."""
        if not package_name:
            return None

        # Convert package name to directory path
        package_path = package_name.replace(".", os.sep)

        # Try to find the class file
        if class_name:
            # Specific class import
            class_file = class_name + ".java"
            resolved = os.path.normpath(
                os.path.join(
                    project_root, "src", "main", "java", package_path, class_file
                )
            )
            if os.path.exists(resolved) and os.path.isfile(resolved):
                return resolved

            # Try alternative source directories
            for src_dir in ["src", "source", "java"]:
                resolved = os.path.normpath(
                    os.path.join(project_root, src_dir, package_path, class_file)
                )
                if os.path.exists(resolved) and os.path.isfile(resolved):
                    return resolved
        else:
            # Wildcard import - try to find package-info.java or any class in the package
            package_dir = os.path.normpath(
                os.path.join(project_root, "src", "main", "java", package_path)
            )
            if os.path.exists(package_dir) and os.path.isdir(package_dir):
                # Return the first .java file found (or package-info.java if exists)
                for file in os.listdir(package_dir):
                    if file.endswith(".java"):
                        resolved = os.path.join(package_dir, file)
                        if os.path.isfile(resolved):
                            return resolved

        return None


# --- Java Language Support ---


class JavaLanguageSupport(BaseLanguageSupport):
    """Java语言支持。"""

    @property
    def language_name(self) -> str:
        return "java"

    @property
    def file_extensions(self) -> Set[str]:
        return {".java"}

    def create_symbol_extractor(self) -> Optional[SymbolExtractor]:
        if not JAVA_LANGUAGE:
            return None
        try:
            return JavaSymbolExtractor()
        except Exception:
            return None

    def create_dependency_analyzer(self) -> Optional[DependencyAnalyzer]:
        return JavaDependencyAnalyzer()
