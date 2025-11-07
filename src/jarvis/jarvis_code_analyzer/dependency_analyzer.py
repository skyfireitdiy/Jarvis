import os
import ast
from dataclasses import dataclass
from typing import Dict, List, Set, Optional, Type

@dataclass
class Dependency:
    """Represents an import dependency."""
    from_module: str
    imported_symbol: Optional[str] = None  # None means import entire module
    file_path: str = ""
    line: int = 0

class DependencyGraph:
    """Represents the dependency graph of a project."""

    def __init__(self):
        # file_path -> set of file_paths it depends on
        self.dependencies: Dict[str, Set[str]] = {}
        # file_path -> set of file_paths that depend on it
        self.dependents: Dict[str, Set[str]] = {}

    def add_dependency(self, file_path: str, dependency_path: str):
        """Adds a dependency from file_path to dependency_path."""
        if file_path not in self.dependencies:
            self.dependencies[file_path] = set()
        self.dependencies[file_path].add(dependency_path)

        if dependency_path not in self.dependents:
            self.dependents[dependency_path] = set()
        self.dependents[dependency_path].add(file_path)

    def get_dependencies(self, file_path: str) -> List[str]:
        """Gets the list of files that file_path depends on."""
        return list(self.dependencies.get(file_path, set()))

    def get_dependents(self, file_path: str) -> List[str]:
        """Gets the list of files that depend on file_path."""
        return list(self.dependents.get(file_path, set()))

    def clear_file_dependencies(self, file_path: str):
        """Removes all dependency information for a specific file."""
        if file_path in self.dependencies:
            # Remove this file's dependencies on others
            deps_to_remove = self.dependencies.pop(file_path)
            for dep in deps_to_remove:
                if dep in self.dependents and file_path in self.dependents[dep]:
                    self.dependents[dep].remove(file_path)
                    if not self.dependents[dep]:
                        del self.dependents[dep]

        # Remove other files' dependencies on this file
        if file_path in self.dependents:
            dependents_to_remove = self.dependents.pop(file_path)
            for dep_file in dependents_to_remove:
                if dep_file in self.dependencies and file_path in self.dependencies[dep_file]:
                    self.dependencies[dep_file].remove(file_path)
                    if not self.dependencies[dep_file]:
                        del self.dependencies[dep_file]


class DependencyAnalyzer:
    """Analyzes import dependencies in a source code file."""

    def analyze_imports(self, file_path: str, content: str) -> List[Dependency]:
        """
        Analyzes the import statements in the code.
        This method should be implemented by language-specific subclasses.
        """
        raise NotImplementedError("Subclasses must implement this method.")

    def build_dependency_graph(self, project_root: str) -> DependencyGraph:
        """
        Builds a dependency graph for the entire project.
        This would involve iterating over all source files.
        """
        graph = DependencyGraph()
        
        # Walk through all source files in the project
        for root, dirs, files in os.walk(project_root):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                file_path = os.path.join(root, file)
                if not self._is_source_file(file_path):
                    continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    
                    dependencies = self.analyze_imports(file_path, content)
                    for dep in dependencies:
                        # Resolve dependency path (this should be done by language-specific analyzer)
                        # For now, we'll just store the module name
                        pass
                except Exception as e:
                    # Skip files that can't be read or parsed
                    continue
        
        return graph

    def _is_source_file(self, file_path: str) -> bool:
        """Check if a file is a source file that should be analyzed."""
        # This should be overridden by subclasses
        return False


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
                        dependencies.append(Dependency(
                            from_module=alias.name,
                            imported_symbol=None,
                            file_path=file_path,
                            line=node.lineno,
                        ))
                elif isinstance(node, ast.ImportFrom):
                    # from module import symbol
                    module = node.module or ""
                    for alias in node.names:
                        dependencies.append(Dependency(
                            from_module=module,
                            imported_symbol=alias.name,
                            file_path=file_path,
                            line=node.lineno,
                        ))
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
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules', 'venv', 'env']]
            
            for file in files:
                if not file.endswith('.py'):
                    continue
                
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    
                    dependencies = self.analyze_imports(file_path, content)
                    for dep in dependencies:
                        # Resolve module to file path
                        dep_path = self._resolve_module_path(project_root, dep.from_module, file_path)
                        if dep_path and dep_path != file_path:
                            graph.add_dependency(file_path, dep_path)
                except Exception:
                    continue
        
        return graph

    def _resolve_module_path(self, project_root: str, module_name: str, from_file: str) -> Optional[str]:
        """Resolve a Python module name to a file path."""
        if not module_name:
            return None
        
        # Handle relative imports
        if module_name.startswith('.'):
            # Relative import - resolve from the importing file's directory
            base_dir = os.path.dirname(from_file)
            parts = module_name.split('.')
            depth = len([p for p in parts if p == ''])
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
                init_path = os.path.join(module_path, '__init__.py')
                if os.path.exists(init_path):
                    return init_path
            elif os.path.exists(module_path + '.py'):
                return module_path + '.py'
        else:
            # Absolute import
            parts = module_name.split('.')
            
            # Search in project root
            for root, dirs, files in os.walk(project_root):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                if parts[0] in dirs or f"{parts[0]}.py" in files:
                    module_path = os.path.join(root, *parts)
                    
                    if os.path.isdir(module_path):
                        init_path = os.path.join(module_path, '__init__.py')
                        if os.path.exists(init_path):
                            return init_path
                    elif os.path.exists(module_path + '.py'):
                        return module_path + '.py'
                    break
        
        return None

    def _is_source_file(self, file_path: str) -> bool:
        """Check if a file is a Python source file."""
        return file_path.endswith('.py')