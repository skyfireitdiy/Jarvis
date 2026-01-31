"""Split Module Refactoring Module

This module provides functionality to split large modules into smaller,
more manageable modules based on dependency analysis and functionality grouping.
"""

import ast
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from jarvis.jarvis_auto_fix.fix_history import FixHistory, FixRecord, generate_fix_id


@dataclass
class ModuleInfo:
    """Information about a module component (class or function)."""

    name: str
    component_type: str  # 'class' or 'function'
    start_line: int
    end_line: int
    dependencies: Set[str] = field(default_factory=set)
    dependents: Set[str] = field(default_factory=set)
    complexity: int = 0


@dataclass
class SplitGroup:
    """A group of components to be split into a new module."""

    components: List[str]  # Names of components
    new_module_name: str
    reason: str  # Why these components are grouped together


@dataclass
class SplitPlan:
    """Plan for splitting a module."""

    original_module: str
    groups: List[SplitGroup]
    remaining_components: List[str]  # Components staying in original module
    estimated_benefit: str  # Description of expected improvement


@dataclass
class ModuleSplitResult:
    """Result of a module split operation."""

    success: bool
    created_modules: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    error_message: str = ""
    split_plan: Optional[SplitPlan] = None


class ModuleDependencyAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze dependencies within a module."""

    def __init__(self) -> None:
        self.classes: Dict[str, ModuleInfo] = {}
        self.functions: Dict[str, ModuleInfo] = {}
        self.imports: Dict[str, str] = {}  # name -> source
        self._current_class: Optional[str] = None
        self._current_function: Optional[str] = None

    def analyze_module(self, tree: ast.Module) -> None:
        """Analyze a module to extract component information.

        Args:
            tree: The AST module node.
        """
        for node in tree.body:
            if isinstance(node, ast.Import):
                self._analyze_import(node)
            elif isinstance(node, ast.ImportFrom):
                self._analyze_import_from(node)
            elif isinstance(node, ast.ClassDef):
                self._analyze_class(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Only analyze top-level functions
                self._analyze_function(node)

        self._analyze_dependencies()

    def _analyze_import(self, node: ast.Import) -> None:
        """Analyze an import statement."""
        for alias in node.names:
            self.imports[alias.asname or alias.name] = alias.name

    def _analyze_import_from(self, node: ast.ImportFrom) -> None:
        """Analyze a from...import statement."""
        if node.module:
            for alias in node.names:
                imported_name = alias.asname or alias.name
                self.imports[imported_name] = f"{node.module}.{alias.name}"

    def _analyze_class(self, node: ast.ClassDef) -> None:
        """Analyze a class definition."""
        self.classes[node.name] = ModuleInfo(
            name=node.name,
            component_type="class",
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            complexity=self._calculate_complexity(node),
        )
        self._current_class = node.name
        self.visit(node)
        self._current_class = None

    def _analyze_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Analyze a function definition."""
        self.functions[node.name] = ModuleInfo(
            name=node.name,
            component_type="function",
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            complexity=self._calculate_complexity(node),
        )
        self._current_function = node.name
        self.visit(node)
        self._current_function = None

    def _calculate_complexity(self, node: ast.AST) -> int:
        """Calculate cyclomatic complexity of a node."""
        complexity = 1  # Base complexity
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity

    def visit_Name(self, node: ast.Name) -> None:
        """Track name usages for dependency analysis."""
        if self._current_class:
            if node.id in self.classes and node.id != self._current_class:
                self.classes[self._current_class].dependencies.add(node.id)
        elif self._current_function:
            if node.id in self.classes:
                self.functions[self._current_function].dependencies.add(node.id)
        self.generic_visit(node)

    def _analyze_dependencies(self) -> None:
        """Analyze and populate dependent relationships."""
        all_components = {**self.classes, **self.functions}

        for name, info in all_components.items():
            for dep in info.dependencies:
                if dep in all_components:
                    all_components[dep].dependents.add(name)


class SplitModuleRefactorer:
    """Refactorer to split large modules into smaller, more focused modules.

    This refactorer analyzes a module's structure and dependencies,
    then suggests and performs intelligent splits to improve code organization.
    """

    def __init__(self, history: Optional[FixHistory] = None) -> None:
        """Initialize the SplitModuleRefactorer.

        Args:
            history: Optional FixHistory instance for tracking changes.
        """
        self.history = history or FixHistory()
        self.analyzer = ModuleDependencyAnalyzer()

    def analyze_module(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Analyze a module to determine if it can be split.

        Args:
            file_path: Path to the module file.

        Returns:
            Dictionary with analysis results, or None if analysis fails.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)
            self.analyzer.analyze_module(tree)

            # Calculate metrics
            total_classes = len(self.analyzer.classes)
            total_functions = len(self.analyzer.functions)
            total_complexity = sum(
                info.complexity
                for info in {
                    **self.analyzer.classes,
                    **self.analyzer.functions,
                }.values()
            )

            return {
                "file_path": file_path,
                "total_classes": total_classes,
                "total_functions": total_functions,
                "total_components": total_classes + total_functions,
                "total_complexity": total_complexity,
                "classes": self.analyzer.classes,
                "functions": self.analyzer.functions,
                "imports": self.analyzer.imports,
                "can_split": (total_classes + total_functions) >= 3,
            }
        except Exception:
            return None

    def suggest_split_plan(self, file_path: str) -> Optional[SplitPlan]:
        """Suggest a split plan for a module.

        Args:
            file_path: Path to the module file.

        Returns:
            SplitPlan with suggested groups, or None if no split suggested.
        """
        analysis = self.analyze_module(file_path)
        if not analysis or not analysis["can_split"]:
            return None

        # Simple heuristic: group by dependency clusters
        components: Dict[str, ModuleInfo] = {
            **analysis["classes"],
            **analysis["functions"],
        }

        if len(components) < 3:
            return None

        # Group components with strong mutual dependencies
        groups = self._find_dependency_clusters(components)

        if len(groups) < 2:
            return None

        # Create split plan
        split_groups: List[SplitGroup] = []
        remaining: List[str] = []

        for i, group in enumerate(groups):
            if len(group) > 1:
                new_module_name = self._suggest_module_name(file_path, i)
                reason = f"Group of {len(group)} interdependent components"
                split_groups.append(
                    SplitGroup(
                        components=list(group),
                        new_module_name=new_module_name,
                        reason=reason,
                    )
                )
            else:
                remaining.extend(group)

        # Add remaining components
        all_grouped = set()
        for g in split_groups:
            all_grouped.update(g.components)

        for name in components:
            if name not in all_grouped:
                remaining.append(name)

        module_name = Path(file_path).stem
        benefit = f"Split {module_name} into {len(split_groups) + (1 if remaining else 0)} modules"

        return SplitPlan(
            original_module=file_path,
            groups=split_groups,
            remaining_components=remaining,
            estimated_benefit=benefit,
        )

    def _find_dependency_clusters(
        self, components: Dict[str, ModuleInfo]
    ) -> List[Set[str]]:
        """Find clusters of mutually dependent components.

        Args:
            components: Dictionary of component name to ModuleInfo.

        Returns:
            List of sets, each set is a cluster of component names.
        """
        clusters: List[Set[str]] = []
        assigned: Set[str] = set()

        for name, info in components.items():
            if name in assigned:
                continue

            # Start a new cluster
            cluster = {name}
            to_process = [name]

            while to_process:
                current = to_process.pop()
                current_info = components[current]

                # Add components that depend on current
                for dep in current_info.dependents:
                    if dep in components and dep not in cluster:
                        cluster.add(dep)
                        to_process.append(dep)

                # Add components that current depends on
                for dep in current_info.dependencies:
                    if dep in components and dep not in cluster:
                        cluster.add(dep)
                        to_process.append(dep)

            if cluster:
                clusters.append(cluster)
                assigned.update(cluster)

        return clusters

    def _suggest_module_name(self, original_file: str, group_index: int) -> str:
        """Suggest a name for a new module.

        Args:
            original_file: Original module file path.
            group_index: Index of the split group.

        Returns:
            Suggested module name.
        """
        original_name = Path(original_file).stem
        return f"{original_name}_part{group_index + 1}"

    def split_module(
        self, file_path: str, plan: Optional[SplitPlan] = None
    ) -> ModuleSplitResult:
        """Split a module according to a plan.

        Args:
            file_path: Path to the module to split.
            plan: Optional split plan. If None, will auto-generate.

        Returns:
            ModuleSplitResult with details of the operation.
        """
        if plan is None:
            plan = self.suggest_split_plan(file_path)
            if plan is None:
                return ModuleSplitResult(
                    success=False, error_message="No suitable split plan found"
                )

        try:
            # Read original file
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()

            tree = ast.parse(original_content)
            created_modules = []
            modified_files = [file_path]

            # Create new module files for each group
            for group in plan.groups:
                new_module_path = self._create_new_module(file_path, group, tree)
                if new_module_path:
                    created_modules.append(new_module_path)

            # Modify original module to remove split components
            modified_content = self._remove_split_components(original_content, plan)

            # Write modified original
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(modified_content)

            # Record fix
            record_id = generate_fix_id()
            record = FixRecord(
                record_id=record_id,
                file_path=file_path,
                issue_type="split_module",
                original_content=original_content,
                fixed_content=modified_content,
                timestamp=datetime.now().isoformat(),
                fix_applied=f"Split module into {len(created_modules) + 1} files",
                rollback_available=True,
            )
            self.history.record_fix(record)

            return ModuleSplitResult(
                success=True,
                created_modules=created_modules,
                modified_files=modified_files,
                split_plan=plan,
            )

        except Exception as e:
            return ModuleSplitResult(
                success=False, error_message=f"Error splitting module: {str(e)}"
            )

    def _create_new_module(
        self, original_file: str, group: SplitGroup, tree: ast.Module
    ) -> Optional[str]:
        """Create a new module file for a split group.

        Args:
            original_file: Original module file path.
            group: Split group to create module for.
            tree: Original module AST.

        Returns:
            Path to created module, or None on failure.
        """
        try:
            # Extract components for this group
            group_nodes: List[ast.stmt] = []
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name in group.components:
                    group_nodes.append(node)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name in group.components:
                        group_nodes.append(node)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    # Include all imports (will be pruned later)
                    group_nodes.append(node)

            if not group_nodes:
                return None

            # Create new module
            original_dir = Path(original_file).parent
            new_module_path = original_dir / f"{group.new_module_name}.py"

            # Generate code
            new_tree = ast.Module(body=group_nodes, type_ignores=[])
            code = ast.unparse(new_tree)

            # Write file
            with open(new_module_path, "w", encoding="utf-8") as f:
                f.write(code)

            return str(new_module_path)

        except Exception:
            return None

    def _remove_split_components(self, content: str, plan: SplitPlan) -> str:
        """Remove split components from original module.

        Args:
            content: Original module content.
            plan: Split plan.

        Returns:
            Modified module content.
        """
        lines = content.split("\n")
        to_remove = set()

        # Mark lines to remove for each group
        for group in plan.groups:
            for component in group.components:
                # Find and mark the component's lines
                for i, line in enumerate(lines):
                    if f"class {component}" in line or f"def {component}" in line:
                        # Found component start, find end
                        to_remove.add(i)
                        # Simple heuristic: remove until next class/def or empty line
                        for j in range(i + 1, len(lines)):
                            to_remove.add(j)
                            if lines[j].strip() and not lines[j].startswith(" "):
                                break
                        break

        # Build new content without removed lines
        new_lines = [line for i, line in enumerate(lines) if i not in to_remove]

        return "\n".join(new_lines)
