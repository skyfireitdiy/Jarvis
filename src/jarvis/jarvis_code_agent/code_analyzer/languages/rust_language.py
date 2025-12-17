"""Rust语言支持实现。"""

import os
import re
from typing import List
from typing import Optional
from typing import Set
from typing import cast

from tree_sitter import Language
from tree_sitter import Node

from ..base_language import BaseLanguageSupport
from ..dependency_analyzer import Dependency
from ..dependency_analyzer import DependencyAnalyzer
from ..dependency_analyzer import DependencyGraph
from ..file_ignore import filter_walk_dirs
from ..symbol_extractor import Symbol
from ..symbol_extractor import SymbolExtractor
from ..tree_sitter_extractor import TreeSitterExtractor

# --- Rust Symbol Query ---

RUST_SYMBOL_QUERY = """
(function_item
  name: (identifier) @function.name)

(struct_item
  name: (type_identifier) @struct.name)
  
(trait_item
  name: (type_identifier) @trait.name)

(impl_item
  type: (type_identifier) @impl.name)

(mod_item
  name: (identifier) @module.name)

(enum_item
  name: (type_identifier) @enum.name)

(union_item
  name: (type_identifier) @union.name)

(macro_definition
  name: (identifier) @macro.name)

(const_item
  name: (identifier) @const.name)

(static_item
  name: (identifier) @static.name)

(type_item
  name: (type_identifier) @type.name)

(attribute_item) @attribute
"""

# --- Rust Language Setup ---

try:
    import tree_sitter_rust

    RUST_LANGUAGE: Optional[Language] = cast(
        Optional[Language], tree_sitter_rust.language()
    )
except (ImportError, Exception):
    RUST_LANGUAGE = None


# --- Rust Symbol Extractor ---


class RustSymbolExtractor(TreeSitterExtractor):
    """Extracts symbols from Rust code using tree-sitter."""

    def __init__(self) -> None:
        if not RUST_LANGUAGE:
            raise RuntimeError("Rust tree-sitter grammar not available.")
        super().__init__(RUST_LANGUAGE, RUST_SYMBOL_QUERY)

    def _create_symbol_from_capture(
        self, node: Node, name: str, file_path: str
    ) -> Optional[Symbol]:
        """Maps a tree-sitter capture to a Symbol object."""
        kind_map = {
            "function.name": "function",
            "struct.name": "struct",
            "trait.name": "trait",
            "impl.name": "impl",
            "module.name": "module",
            "enum.name": "enum",
            "union.name": "union",
            "macro.name": "macro",
            "const.name": "const",
            "static.name": "static",
            "type.name": "type",
            "extern": "extern",
            "attribute": "attribute",
        }

        symbol_kind = kind_map.get(name)
        if not symbol_kind:
            return None

        # 对于 attribute，提取属性内容作为名称
        if symbol_kind == "attribute":
            # 提取属性文本
            if node.text is None:
                return None
            attr_text = node.text.decode("utf8").strip()
            # 移除开头的 # 或 #!
            if attr_text.startswith("#!"):
                attr_text = attr_text[2:].strip()
            elif attr_text.startswith("#"):
                attr_text = attr_text[1:].strip()
            # 移除外层的 []
            if attr_text.startswith("[") and attr_text.endswith("]"):
                attr_text = attr_text[1:-1].strip()

            # 提取属性名称（可能是 test, derive(Debug), cfg(test) 等）
            # 对于简单属性如 #[test]，直接使用 test
            # 对于复杂属性如 #[derive(Debug)]，使用 derive
            # 对于路径属性如 #[cfg(test)]，使用 cfg
            attr_name = (
                attr_text.split("(")[0]
                .split("[")[0]
                .split("=")[0]
                .split(",")[0]
                .strip()
            )

            # 如果属性名称为空或只包含空白，使用整个属性文本（去掉括号）
            if not attr_name or attr_name == "":
                symbol_name = attr_text if attr_text else "attribute"
            else:
                # 使用属性名称，但保留完整文本用于显示
                symbol_name = attr_name
        elif symbol_kind == "extern":
            # 对于 extern 块，提取 extern 关键字后的内容作为名称
            if node.text is None:
                return None
            extern_text = node.text.decode("utf8").strip()
            # 提取 extern "C" 或 extern "Rust" 等
            if '"' in extern_text:
                # 提取引号中的内容
                start = extern_text.find('"')
                end = extern_text.find('"', start + 1)
                if end > start:
                    symbol_name = f"extern_{extern_text[start + 1 : end]}"
                else:
                    symbol_name = "extern"
            else:
                symbol_name = "extern"
        else:
            if node.text is None:
                return None
            symbol_name = node.text.decode("utf8")

        return Symbol(
            name=symbol_name,
            kind=symbol_kind,
            file_path=file_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
        )


# --- Rust Dependency Analyzer ---


class RustDependencyAnalyzer(DependencyAnalyzer):
    """Analyzes Rust use and mod dependencies."""

    def analyze_imports(self, file_path: str, content: str) -> List[Dependency]:
        """Analyzes Rust use and mod statements."""
        dependencies: List[Dependency] = []

        # Match use statements: use crate::module or use std::collections
        use_pattern = re.compile(r"use\s+([^;]+);")

        # Match mod declarations: mod module_name;
        mod_pattern = re.compile(r"mod\s+(\w+)\s*;")

        for line_num, line in enumerate(content.split("\n"), start=1):
            # Check for use statements
            use_match = use_pattern.search(line)
            if use_match:
                use_path = use_match.group(1).strip()
                # Extract the crate/module name
                parts = use_path.split("::")
                if parts:
                    crate_name = parts[0]
                    symbol = "::".join(parts[1:]) if len(parts) > 1 else None
                    dependencies.append(
                        Dependency(
                            from_module=crate_name,
                            imported_symbol=symbol,
                            file_path=file_path,
                            line=line_num,
                        )
                    )

            # Check for mod declarations
            mod_match = mod_pattern.search(line)
            if mod_match:
                mod_name = mod_match.group(1)
                dependencies.append(
                    Dependency(
                        from_module=mod_name,
                        imported_symbol=None,
                        file_path=file_path,
                        line=line_num,
                    )
                )

        return dependencies

    def build_dependency_graph(self, project_root: str) -> DependencyGraph:
        """Builds a dependency graph for a Rust project."""
        graph = DependencyGraph()

        for root, dirs, files in os.walk(project_root):
            dirs[:] = filter_walk_dirs(dirs)

            for file in files:
                if not file.endswith(".rs"):
                    continue

                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()

                    dependencies = self.analyze_imports(file_path, content)
                    for dep in dependencies:
                        # For Rust, resolve mod declarations to file paths
                        if not dep.from_module.startswith(
                            ("std", "core", "alloc", "proc_macro")
                        ):
                            # Try to resolve local modules
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
        """Resolve a Rust module name to a file path."""
        # Rust modules can be:
        # 1. mod.rs in a directory
        # 2. module_name.rs in the same directory
        # 3. module_name/mod.rs

        base_dir = os.path.dirname(from_file)

        # Try module_name.rs in same directory
        module_file = os.path.join(base_dir, f"{module_name}.rs")
        if os.path.exists(module_file):
            return module_file

        # Try module_name/mod.rs
        module_dir = os.path.join(base_dir, module_name)
        mod_rs = os.path.join(module_dir, "mod.rs")
        if os.path.exists(mod_rs):
            return mod_rs

        # Try in parent directories (for nested modules)
        current_dir = base_dir
        while current_dir != project_root and current_dir != os.path.dirname(
            current_dir
        ):
            module_file = os.path.join(current_dir, f"{module_name}.rs")
            if os.path.exists(module_file):
                return module_file
            module_dir = os.path.join(current_dir, module_name)
            mod_rs = os.path.join(module_dir, "mod.rs")
            if os.path.exists(mod_rs):
                return mod_rs
            current_dir = os.path.dirname(current_dir)

        return None

    def _is_source_file(self, file_path: str) -> bool:
        """Check if a file is a Rust source file."""
        return file_path.endswith(".rs")


class RustLanguageSupport(BaseLanguageSupport):
    """Rust语言支持类。"""

    @property
    def language_name(self) -> str:
        return "rust"

    @property
    def file_extensions(self) -> Set[str]:
        return {".rs"}

    def create_symbol_extractor(self) -> Optional[SymbolExtractor]:
        try:
            return RustSymbolExtractor()
        except RuntimeError:
            return None

    def create_dependency_analyzer(self) -> Optional[DependencyAnalyzer]:
        return RustDependencyAnalyzer()
