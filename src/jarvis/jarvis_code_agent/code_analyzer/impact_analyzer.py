"""编辑影响范围分析模块。

提供代码编辑影响范围分析功能，识别可能受影响的文件、函数、测试等。
"""

import ast
import os
import re
import subprocess
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Dict
from typing import List
from typing import Optional
from typing import Set

from .context_manager import ContextManager
from .file_ignore import filter_walk_dirs
from .symbol_extractor import Symbol


class ImpactType(Enum):
    """影响类型枚举"""

    REFERENCE = "reference"  # 符号引用
    DEPENDENT = "dependent"  # 依赖的符号
    TEST = "test"  # 测试文件
    INTERFACE_CHANGE = "interface_change"  # 接口变更
    DEPENDENCY_CHAIN = "dependency_chain"  # 依赖链


class RiskLevel(Enum):
    """风险等级枚举"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Impact:
    """表示一个影响项"""

    impact_type: ImpactType
    target: str  # 受影响的目标（文件路径、符号名等）
    description: str = ""
    line: Optional[int] = None
    severity: RiskLevel = RiskLevel.LOW


@dataclass
class InterfaceChange:
    """表示接口变更"""

    symbol_name: str
    change_type: str  # 'signature', 'return_type', 'parameter', 'removed', 'added'
    file_path: str
    line: int
    before: Optional[str] = None
    after: Optional[str] = None
    description: str = ""


@dataclass
class ImpactReport:
    """影响分析报告"""

    affected_files: List[str] = field(default_factory=list)
    affected_symbols: List[Symbol] = field(default_factory=list)
    affected_tests: List[str] = field(default_factory=list)
    interface_changes: List[InterfaceChange] = field(default_factory=list)
    impacts: List[Impact] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: List[str] = field(default_factory=list)

    def to_string(self, project_root: str = "") -> str:
        """生成可读的影响报告字符串"""
        lines = []
        lines.append("=" * 60)
        lines.append("编辑影响范围分析报告")
        lines.append("=" * 60)

        # 风险等级
        risk_emoji = {RiskLevel.LOW: "🟢", RiskLevel.MEDIUM: "🟡", RiskLevel.HIGH: "🔴"}
        lines.append(
            f"\n风险等级: {risk_emoji.get(self.risk_level, '⚪')} {self.risk_level.value.upper()}"
        )

        # 受影响文件
        if self.affected_files:
            lines.append(f"\n受影响文件 ({len(self.affected_files)}):")
            for file_path in self.affected_files[:10]:
                rel_path = (
                    os.path.relpath(file_path, project_root)
                    if project_root
                    else file_path
                )
                lines.append(f"  - {rel_path}")
            if len(self.affected_files) > 10:
                lines.append(f"  ... 还有 {len(self.affected_files) - 10} 个文件")

        # 受影响符号
        if self.affected_symbols:
            lines.append(f"\n受影响符号 ({len(self.affected_symbols)}):")
            for symbol in self.affected_symbols[:10]:
                lines.append(
                    f"  - {symbol.kind} {symbol.name} ({os.path.basename(symbol.file_path)}:{symbol.line_start})"
                )
            if len(self.affected_symbols) > 10:
                lines.append(f"  ... 还有 {len(self.affected_symbols) - 10} 个符号")

        # 受影响测试
        if self.affected_tests:
            lines.append(f"\n受影响测试 ({len(self.affected_tests)}):")
            for test_file in self.affected_tests[:10]:
                rel_path = (
                    os.path.relpath(test_file, project_root)
                    if project_root
                    else test_file
                )
                lines.append(f"  - {rel_path}")
            if len(self.affected_tests) > 10:
                lines.append(f"  ... 还有 {len(self.affected_tests) - 10} 个测试文件")

        # 接口变更
        if self.interface_changes:
            lines.append(f"\n接口变更 ({len(self.interface_changes)}):")
            for change in self.interface_changes[:10]:
                lines.append(f"  - {change.symbol_name}: {change.change_type}")
                if change.description:
                    lines.append(f"    {change.description}")
            if len(self.interface_changes) > 10:
                lines.append(
                    f"  ... 还有 {len(self.interface_changes) - 10} 个接口变更"
                )

        # 建议
        if self.recommendations:
            lines.append("\n建议:")
            for i, rec in enumerate(self.recommendations, 1):
                lines.append(f"  {i}. {rec}")

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


@dataclass
class Edit:
    """表示一个编辑操作"""

    file_path: str
    line_start: int
    line_end: int
    before: str = ""
    after: str = ""
    edit_type: str = "modify"  # 'modify', 'add', 'delete'


class TestDiscoverer:
    """测试文件发现器"""

    # 测试文件命名模式
    TEST_PATTERNS = {
        "python": [
            r"test_.*\.py$",
            r".*_test\.py$",
        ],
        "javascript": [
            r".*\.test\.(js|ts|jsx|tsx)$",
            r".*\.spec\.(js|ts|jsx|tsx)$",
        ],
        "rust": [
            r".*_test\.rs$",
        ],
        "java": [
            r".*Test\.java$",
            r".*Tests\.java$",
        ],
        "go": [
            r".*_test\.go$",
        ],
    }

    def __init__(self, project_root: str):
        self.project_root = project_root

    def find_test_files(self, file_path: str) -> List[str]:
        """查找与文件相关的测试文件"""
        test_files: List[str] = []

        # 检测语言
        language = self._detect_language(file_path)
        if not language:
            return test_files

        # 获取测试文件模式
        patterns = self.TEST_PATTERNS.get(language, [])
        if not patterns:
            return test_files

        # 获取文件的基础名称（不含扩展名）
        base_name = os.path.splitext(os.path.basename(file_path))[0]

        # 在项目根目录搜索测试文件
        for root, dirs, files in os.walk(self.project_root):
            # 跳过隐藏目录和常见忽略目录
            dirs[:] = filter_walk_dirs(dirs)

            for file in files:
                file_path_full = os.path.join(root, file)

                # 检查是否匹配测试文件模式
                for pattern in patterns:
                    if re.match(pattern, file, re.IGNORECASE):
                        # 检查测试文件是否可能测试目标文件
                        if self._might_test_file(file_path_full, file_path, base_name):
                            test_files.append(file_path_full)
                        break

        return list(set(test_files))

    def _might_test_file(
        self, test_file: str, target_file: str, base_name: str
    ) -> bool:
        """判断测试文件是否可能测试目标文件"""
        # 读取测试文件内容，查找目标文件的引用
        try:
            with open(test_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            # 检查是否导入或引用了目标文件
            # 简单的启发式方法：检查文件名、模块名等
            target_base = os.path.splitext(os.path.basename(target_file))[0]

            # 检查导入语句
            import_patterns = [
                rf"import\s+.*{re.escape(target_base)}",
                rf"from\s+.*{re.escape(target_base)}",
                rf"use\s+.*{re.escape(target_base)}",  # Rust
            ]

            for pattern in import_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    return True

            # 检查文件名是否出现在测试文件中
            if target_base.lower() in content.lower():
                return True

        except Exception:
            pass

        return False

    def _detect_language(self, file_path: str) -> Optional[str]:
        """检测文件语言"""
        ext = os.path.splitext(file_path)[1].lower()
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "javascript",
            ".jsx": "javascript",
            ".tsx": "javascript",
            ".rs": "rust",
            ".java": "java",
            ".go": "go",
        }
        return ext_map.get(ext)


class ImpactAnalyzer:
    """编辑影响范围分析器"""

    def __init__(self, context_manager: ContextManager):
        self.context_manager = context_manager
        self.project_root = context_manager.project_root
        self.test_discoverer = TestDiscoverer(self.project_root)

    def analyze_edit_impact(self, file_path: str, edits: List[Edit]) -> ImpactReport:
        """分析编辑的影响范围

        Args:
            file_path: 被编辑的文件路径
            edits: 编辑操作列表

        Returns:
            ImpactReport: 影响分析报告
        """
        impacts: List[Impact] = []
        affected_symbols: Set[Symbol] = set()
        affected_files: Set[str] = {file_path}
        interface_changes: List[InterfaceChange] = []

        # 1. 分析每个编辑的影响
        for edit in edits:
            # 分析符号影响
            symbols_in_edit = self._find_symbols_in_edit(file_path, edit)
            for symbol in symbols_in_edit:
                affected_symbols.add(symbol)
                symbol_impacts = self._analyze_symbol_impact(symbol, edit)
                impacts.extend(symbol_impacts)

                # 收集受影响的文件
                for impact in symbol_impacts:
                    if impact.impact_type == ImpactType.REFERENCE:
                        affected_files.add(impact.target)
                    elif impact.impact_type == ImpactType.DEPENDENT:
                        affected_files.add(impact.target)

        # 2. 分析依赖链影响
        dependency_impacts = self._analyze_dependency_chain(file_path)
        impacts.extend(dependency_impacts)
        for impact in dependency_impacts:
            affected_files.add(impact.target)

        # 3. 检测接口变更
        if edits:
            # 需要读取文件内容来比较
            interface_changes = self._detect_interface_changes(file_path, edits)
            for change in interface_changes:
                affected_files.add(change.file_path)

        # 4. 查找相关测试
        test_files = self.test_discoverer.find_test_files(file_path)
        for test_file in test_files:
            impacts.append(
                Impact(
                    impact_type=ImpactType.TEST,
                    target=test_file,
                    description=f"可能测试 {os.path.basename(file_path)} 的测试文件",
                )
            )
            affected_files.add(test_file)

        # 5. 评估风险等级
        risk_level = self._assess_risk(impacts, interface_changes)

        # 6. 生成建议
        recommendations = self._generate_recommendations(
            impacts, interface_changes, affected_files, test_files
        )

        return ImpactReport(
            affected_files=list(affected_files),
            affected_symbols=list(affected_symbols),
            affected_tests=test_files,
            interface_changes=interface_changes,
            impacts=impacts,
            risk_level=risk_level,
            recommendations=recommendations,
        )

    def _find_symbols_in_edit(self, file_path: str, edit: Edit) -> List[Symbol]:
        """查找编辑区域内的符号"""
        symbols = self.context_manager.symbol_table.get_file_symbols(file_path)

        # 找出在编辑范围内的符号
        affected_symbols = []
        for symbol in symbols:
            # 检查符号是否与编辑区域重叠
            if (
                symbol.line_start <= edit.line_end
                and symbol.line_end >= edit.line_start
            ):
                affected_symbols.append(symbol)

        return affected_symbols

    def _analyze_symbol_impact(self, symbol: Symbol, edit: Edit) -> List[Impact]:
        """分析符号编辑的影响"""
        impacts = []

        # 1. 查找所有引用该符号的位置
        references = self.context_manager.find_references(symbol.name, symbol.file_path)
        for ref in references:
            impacts.append(
                Impact(
                    impact_type=ImpactType.REFERENCE,
                    target=ref.file_path,
                    description=f"引用符号 {symbol.name}",
                    line=ref.line,
                    severity=RiskLevel.MEDIUM
                    if symbol.kind in ("function", "class")
                    else RiskLevel.LOW,
                )
            )

        # 2. 查找依赖该符号的其他符号（在同一文件中）
        if symbol.kind in ("function", "class"):
            dependents = self._find_dependent_symbols(symbol)
            for dep in dependents:
                impacts.append(
                    Impact(
                        impact_type=ImpactType.DEPENDENT,
                        target=dep.file_path,
                        description=f"依赖符号 {symbol.name}",
                        line=dep.line_start,
                        severity=RiskLevel.MEDIUM,
                    )
                )

        return impacts

    def _find_dependent_symbols(self, symbol: Symbol) -> List[Symbol]:
        """查找依赖该符号的其他符号"""
        dependents = []

        # 获取同一文件中的所有符号
        file_symbols = self.context_manager.symbol_table.get_file_symbols(
            symbol.file_path
        )

        # 查找在符号定义之后的符号（可能使用该符号）
        for other_symbol in file_symbols:
            if (
                other_symbol.line_start > symbol.line_end
                and other_symbol.name != symbol.name
            ):
                # 简单检查：如果符号名出现在其他符号的范围内，可能依赖
                # 这里使用简单的启发式方法
                content = self.context_manager._get_file_content(symbol.file_path)
                if content:
                    # 提取其他符号的代码区域
                    lines = content.split("\n")
                    if other_symbol.line_start <= len(
                        lines
                    ) and other_symbol.line_end <= len(lines):
                        region = "\n".join(
                            lines[other_symbol.line_start - 1 : other_symbol.line_end]
                        )
                        if symbol.name in region:
                            dependents.append(other_symbol)

        return dependents

    def _analyze_dependency_chain(self, file_path: str) -> List[Impact]:
        """分析依赖链，找出所有可能受影响的文件"""
        impacts = []

        # 获取依赖该文件的所有文件（传递闭包）
        visited = set()
        to_process = [file_path]

        while to_process:
            current = to_process.pop(0)
            if current in visited:
                continue
            visited.add(current)

            dependents = self.context_manager.dependency_graph.get_dependents(current)
            for dependent in dependents:
                if dependent not in visited:
                    impacts.append(
                        Impact(
                            impact_type=ImpactType.DEPENDENCY_CHAIN,
                            target=dependent,
                            description=f"间接依赖 {os.path.basename(file_path)}",
                            severity=RiskLevel.LOW,
                        )
                    )
                    to_process.append(dependent)

        return impacts

    def _detect_interface_changes(
        self, file_path: str, edits: List[Edit]
    ) -> List[InterfaceChange]:
        """检测接口变更（函数签名、类定义等）"""
        changes: List[InterfaceChange] = []

        # 读取文件内容
        content_before = self._get_file_content_before_edit(file_path, edits)
        content_after = self._get_file_content_after_edit(file_path, edits)

        if not content_before or not content_after:
            return changes

        # 解析AST并比较
        try:
            tree_before = ast.parse(content_before, filename=file_path)
            tree_after = ast.parse(content_after, filename=file_path)

            # 提取函数和类定义
            defs_before = self._extract_definitions(tree_before)
            defs_after = self._extract_definitions(tree_after)

            # 比较定义
            for name, def_before in defs_before.items():
                if name in defs_after:
                    def_after = defs_after[name]
                    change = self._compare_definition(
                        name, def_before, def_after, file_path
                    )
                    if change:
                        changes.append(change)
                else:
                    # 定义被删除
                    changes.append(
                        InterfaceChange(
                            symbol_name=name,
                            change_type="removed",
                            file_path=file_path,
                            line=def_before["line"],
                            description=f"符号 {name} 被删除",
                        )
                    )

            # 检查新增的定义
            for name, def_after in defs_after.items():
                if name not in defs_before:
                    changes.append(
                        InterfaceChange(
                            symbol_name=name,
                            change_type="added",
                            file_path=file_path,
                            line=def_after["line"],
                            description=f"新增符号 {name}",
                        )
                    )

        except SyntaxError:
            # 如果解析失败，跳过接口变更检测
            pass

        return changes

    def _extract_definitions(self, tree: ast.AST) -> Dict[str, Dict]:
        """从AST中提取函数和类定义"""
        definitions = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # 提取函数签名
                args = [arg.arg for arg in node.args.args]
                signature = f"{node.name}({', '.join(args)})"
                definitions[node.name] = {
                    "type": "function",
                    "line": node.lineno,
                    "signature": signature,
                    "args": args,
                    "node": node,
                }
            elif isinstance(node, ast.ClassDef):
                definitions[node.name] = {
                    "type": "class",
                    "line": node.lineno,
                    "signature": node.name,
                    "node": node,
                }

        return definitions

    def _compare_definition(
        self, name: str, def_before: Dict, def_after: Dict, file_path: str
    ) -> Optional[InterfaceChange]:
        """比较两个定义，检测接口变更"""
        if def_before["type"] != def_after["type"]:
            return InterfaceChange(
                symbol_name=name,
                change_type="signature",
                file_path=file_path,
                line=def_after["line"],
                before=def_before["signature"],
                after=def_after["signature"],
                description=f"符号 {name} 的类型从 {def_before['type']} 变为 {def_after['type']}",
            )

        if def_before["type"] == "function":
            # 比较函数参数
            args_before = def_before.get("args", [])
            args_after = def_after.get("args", [])

            if args_before != args_after:
                return InterfaceChange(
                    symbol_name=name,
                    change_type="signature",
                    file_path=file_path,
                    line=def_after["line"],
                    before=def_before["signature"],
                    after=def_after["signature"],
                    description=f"函数 {name} 的参数从 ({', '.join(args_before)}) 变为 ({', '.join(args_after)})",
                )

        return None

    def _get_file_content_before_edit(
        self, file_path: str, edits: List[Edit]
    ) -> Optional[str]:
        """获取编辑前的文件内容"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            return None

    def _get_file_content_after_edit(
        self, file_path: str, edits: List[Edit]
    ) -> Optional[str]:
        """获取编辑后的文件内容（模拟）"""
        # 这里应该根据edits模拟编辑后的内容
        # 为了简化，我们直接读取当前文件内容
        # 在实际使用中，应该根据edits应用变更
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            return None

    def _assess_risk(
        self, impacts: List[Impact], interface_changes: List[InterfaceChange]
    ) -> RiskLevel:
        """评估编辑风险等级"""
        # 统计高风险因素
        high_risk_count = 0
        medium_risk_count = 0

        # 接口变更通常是高风险
        if interface_changes:
            high_risk_count += len(interface_changes)

        # 统计影响数量
        reference_count = sum(
            1 for i in impacts if i.impact_type == ImpactType.REFERENCE
        )
        if reference_count > 10:
            high_risk_count += 1
        elif reference_count > 5:
            medium_risk_count += 1

        # 检查是否有高风险的影响
        for impact in impacts:
            if impact.severity == RiskLevel.HIGH:
                high_risk_count += 1
            elif impact.severity == RiskLevel.MEDIUM:
                medium_risk_count += 1

        # 评估风险等级
        if high_risk_count > 0 or medium_risk_count > 3:
            return RiskLevel.HIGH
        elif medium_risk_count > 0 or len(impacts) > 5:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def _generate_recommendations(
        self,
        impacts: List[Impact],
        interface_changes: List[InterfaceChange],
        affected_files: Set[str],
        test_files: List[str],
    ) -> List[str]:
        """生成修复建议"""
        recommendations = []

        # 如果有接口变更，建议检查所有调用点
        if interface_changes:
            recommendations.append(
                f"检测到 {len(interface_changes)} 个接口变更，请检查所有调用点并更新相关代码"
            )

        # 如果有测试文件，建议运行测试
        if test_files:
            recommendations.append(
                f"发现 {len(test_files)} 个相关测试文件，建议运行测试确保功能正常"
            )

        # 如果影响文件较多，建议增量测试
        if len(affected_files) > 5:
            recommendations.append(
                f"编辑影响了 {len(affected_files)} 个文件，建议进行增量测试"
            )

        # 如果有大量引用，建议代码审查
        reference_count = sum(
            1 for i in impacts if i.impact_type == ImpactType.REFERENCE
        )
        if reference_count > 10:
            recommendations.append(
                f"检测到 {reference_count} 个符号引用，建议进行代码审查"
            )

        if not recommendations:
            recommendations.append("编辑影响范围较小，建议进行基本测试")

        return recommendations


def parse_git_diff_to_edits(file_path: str, project_root: str) -> List[Edit]:
    """从git diff中解析编辑操作

    Args:
        file_path: 文件路径
        project_root: 项目根目录

    Returns:
        List[Edit]: 编辑操作列表
    """
    edits: List[Edit] = []

    try:
        # 获取文件的git diff
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            return edits

        # 检查是否有git仓库
        try:
            subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=project_root,
                check=True,
                capture_output=True,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            # 不是git仓库或git不可用，返回空列表
            return edits

        # 获取HEAD的hash
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
            )
            head_exists = result.returncode == 0 and result.stdout.strip()
        except Exception:
            head_exists = False

        # 临时添加文件到git索引（如果是新文件）
        subprocess.run(
            ["git", "add", "-N", "--", abs_path],
            cwd=project_root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            # 获取diff
            cmd = ["git", "diff"] + (["HEAD"] if head_exists else []) + ["--", abs_path]
            result = subprocess.run(
                cmd,
                cwd=project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            if result.returncode != 0 or not result.stdout:
                return edits

            diff_text = result.stdout

            # 解析diff文本
            lines = diff_text.split("\n")
            current_hunk_start = None
            current_line_num: Optional[int] = None
            before_lines: List[str] = []
            after_lines: List[str] = []
            in_hunk = False

            for line in lines:
                # 解析hunk header: @@ -start,count +start,count @@
                if line.startswith("@@"):
                    # 保存之前的hunk
                    if in_hunk and current_hunk_start is not None:
                        if before_lines or after_lines:
                            edits.append(
                                Edit(
                                    file_path=abs_path,
                                    line_start=current_hunk_start,
                                    line_end=current_hunk_start + len(after_lines) - 1
                                    if after_lines
                                    else current_hunk_start,
                                    before="\n".join(before_lines),
                                    after="\n".join(after_lines),
                                    edit_type="modify"
                                    if before_lines and after_lines
                                    else ("delete" if before_lines else "add"),
                                )
                            )

                    # 解析新的hunk
                    match = re.search(
                        r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line
                    )
                    if match:
                        old_start = int(match.group(1))
                        new_start = int(match.group(3))

                        current_hunk_start = new_start
                        current_line_num = old_start
                        before_lines = []
                        after_lines = []
                        in_hunk = True
                    continue

                if not in_hunk:
                    continue

                # 解析diff行
                if line.startswith("-") and not line.startswith("---"):
                    # 删除的行
                    before_lines.append(line[1:])
                    if current_line_num is not None:
                        current_line_num += 1
                elif line.startswith("+") and not line.startswith("+++"):
                    # 新增的行
                    after_lines.append(line[1:])
                elif line.startswith(" "):
                    # 未改变的行
                    before_lines.append(line[1:])
                    after_lines.append(line[1:])
                    if current_line_num is not None:
                        current_line_num += 1

            # 保存最后一个hunk
            if in_hunk and current_hunk_start is not None:
                if before_lines or after_lines:
                    edits.append(
                        Edit(
                            file_path=abs_path,
                            line_start=current_hunk_start,
                            line_end=current_hunk_start + len(after_lines) - 1
                            if after_lines
                            else current_hunk_start,
                            before="\n".join(before_lines),
                            after="\n".join(after_lines),
                            edit_type="modify"
                            if before_lines and after_lines
                            else ("delete" if before_lines else "add"),
                        )
                    )

        finally:
            # 清理临时添加的文件
            subprocess.run(
                ["git", "reset", "--", abs_path],
                cwd=project_root,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    except Exception:
        # 解析失败时返回空列表
        pass

    return edits
