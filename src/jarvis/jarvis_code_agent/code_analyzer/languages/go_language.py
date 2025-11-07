"""Go语言支持实现。"""

import os
import re
from typing import List, Optional, Set

from tree_sitter import Language, Node

from ..base_language import BaseLanguageSupport
from ..dependency_analyzer import Dependency, DependencyAnalyzer, DependencyGraph
from ..symbol_extractor import Symbol, SymbolExtractor
from ..tree_sitter_extractor import TreeSitterExtractor


# --- Go Symbol Query ---

GO_SYMBOL_QUERY = """
(function_declaration
  name: (identifier) @function.name)

(method_declaration
  name: (field_identifier) @method.name)

(type_declaration
  (type_spec
    name: (type_identifier) @type.name))

(interface_declaration
  name: (type_identifier) @interface.name)
"""

# --- Go Language Setup ---

try:
    import tree_sitter_go
    GO_LANGUAGE: Optional[Language] = tree_sitter_go.language()
except (ImportError, Exception):
    GO_LANGUAGE = None


# --- Go Symbol Extractor ---

class GoSymbolExtractor(TreeSitterExtractor):
    """Extracts symbols from Go code using tree-sitter."""

    def __init__(self):
        if not GO_LANGUAGE:
            raise RuntimeError("Go tree-sitter grammar not available.")
        super().__init__(GO_LANGUAGE, GO_SYMBOL_QUERY)

    def _create_symbol_from_capture(self, node: Node, name: str, file_path: str) -> Optional[Symbol]:
        """Maps a tree-sitter capture to a Symbol object."""
        kind_map = {
            "function.name": "function",
            "method.name": "method",
            "type.name": "type",
            "interface.name": "interface",
        }
        
        symbol_kind = kind_map.get(name)
        if not symbol_kind:
            return None

        return Symbol(
            name=node.text.decode('utf8'),
            kind=symbol_kind,
            file_path=file_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
        )


# --- Go Dependency Analyzer ---

class GoDependencyAnalyzer(DependencyAnalyzer):
    """Analyzes Go import dependencies."""

    def analyze_imports(self, file_path: str, content: str) -> List[Dependency]:
        """Analyzes Go import statements."""
        dependencies: List[Dependency] = []
        
        # Match import statements
        # Format: import "package" or import ( "package1" "package2" )
        # Also: import alias "package"
        import_pattern = re.compile(
            r'import\s+(?:\(([^)]+)\)|(?:"([^"]+)"|`([^`]+)`)|(\w+)\s+(?:"([^"]+)"|`([^`]+)`)))',
            re.MULTILINE
        )
        
        # Handle single import: import "package"
        single_import = re.compile(r'import\s+(?:"([^"]+)"|`([^`]+)`|(\w+)\s+(?:"([^"]+)"|`([^`]+)`))')
        
        # Handle block import: import ( ... )
        block_import = re.compile(r'import\s*\(([^)]+)\)', re.DOTALL)
        
        # Try block import first
        block_match = block_import.search(content)
        if block_match:
            block_content = block_match.group(1)
            for line in block_content.split('\n'):
                line = line.strip()
                if not line or line.startswith('//'):
                    continue
                # Extract package path
                pkg_match = re.search(r'(?:"([^"]+)"|`([^`]+)`|(\w+)\s+(?:"([^"]+)"|`([^`]+)`))', line)
                if pkg_match:
                    pkg = pkg_match.group(1) or pkg_match.group(2) or pkg_match.group(4) or pkg_match.group(5)
                    alias = pkg_match.group(3)
                    line_num = content[:block_match.start()].count('\n') + line.split('\n')[0].count('\n') + 1
                    dependencies.append(Dependency(
                        from_module=pkg,
                        imported_symbol=alias,
                        file_path=file_path,
                        line=line_num,
                    ))
        else:
            # Try single import
            for match in single_import.finditer(content):
                pkg = match.group(1) or match.group(2) or match.group(4) or match.group(5)
                alias = match.group(3)
                line_num = content[:match.start()].count('\n') + 1
                dependencies.append(Dependency(
                    from_module=pkg,
                    imported_symbol=alias,
                    file_path=file_path,
                    line=line_num,
                ))
        
        return dependencies

    def build_dependency_graph(self, project_root: str) -> DependencyGraph:
        """Builds a dependency graph for a Go project."""
        graph = DependencyGraph()
        
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'vendor']
            
            for file in files:
                if not file.endswith('.go'):
                    continue
                
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    
                    dependencies = self.analyze_imports(file_path, content)
                    for dep in dependencies:
                        # For Go, we can resolve to vendor or standard library
                        # For now, just track the module name
                        # In a real implementation, you'd resolve using go.mod
                        pass
                except Exception:
                    continue
        
        return graph

    def _is_source_file(self, file_path: str) -> bool:
        """Check if a file is a Go source file."""
        return file_path.endswith('.go')


class GoLanguageSupport(BaseLanguageSupport):
    """Go语言支持类。"""

    @property
    def language_name(self) -> str:
        return 'go'

    @property
    def file_extensions(self) -> Set[str]:
        return {'.go'}

    def create_symbol_extractor(self) -> Optional[SymbolExtractor]:
        try:
            return GoSymbolExtractor()
        except RuntimeError:
            return None

    def create_dependency_analyzer(self) -> Optional[DependencyAnalyzer]:
        return GoDependencyAnalyzer()

