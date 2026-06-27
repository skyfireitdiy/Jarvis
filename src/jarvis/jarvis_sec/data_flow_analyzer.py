"""
数据流分析器 - 基于tree-sitter实现轻量级数据流分析

参考项目：tree-climber (https://github.com/bstee615/tree-climber)

核心功能：
1. 指针状态追踪（ALLOCATED、FREED、NULLIFIED、UNKNOWN）
2. 控制流图（CFG）构建
3. 数据流分析（Def-Use链、Reaching Definitions）
4. 误报过滤（free后置NULL、if条件保护等）
"""

import re
from typing import Optional, TYPE_CHECKING

from enum import Enum
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from jarvis.jarvis_sec.project_database import ProjectDatabase

# tree-sitter依赖（已在pyproject.toml中配置）
try:
    import tree_sitter_c as tsc
    import tree_sitter_cpp as tscpp
    from tree_sitter import Language, Parser, Node

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


class PointerState(Enum):
    """指针状态枚举"""

    ALLOCATED = "allocated"  # 已分配
    FREED = "freed"  # 已释放
    NULLIFIED = "nullified"  # 已置NULL
    UNKNOWN = "unknown"  # 未知状态


@dataclass
class PointerInfo:
    """指针信息"""

    name: str
    state: PointerState
    line: int
    scope: str = "global"
    aliases: list[str] = field(default_factory=list)


@dataclass
class ConstraintInfo:
    """约束条件信息"""

    var_name: str
    constraint_type: str  # 'not_null', 'is_null', 'lt', 'gt', 'eq'
    line: int
    scope_start: int  # 约束作用范围起始行
    scope_end: int = -1  # 约束作用范围结束行（-1表示到文件末尾）


@dataclass
class DataFlowResult:
    """数据流分析结果"""

    pointer_states: dict[str, PointerInfo] = field(default_factory=dict)
    safe_accesses: set[int] = field(default_factory=set)  # 安全访问的行号
    unsafe_accesses: set[int] = field(default_factory=set)  # 不安全访问的行号
    null_checks: dict[str, set[int]] = field(default_factory=dict)  # NULL检查位置
    null_check_ranges: dict[str, list[tuple[int, int]]] = field(
        default_factory=dict
    )  # NULL检查保护的行号范围
    constraints: list[ConstraintInfo] = field(default_factory=list)  # 约束条件列表
    dead_code_lines: set[int] = field(default_factory=set)  # 死代码行号
    aliases: dict[str, list[str]] = field(default_factory=dict)  # 指针别名映射
    return_lines: set[int] = field(default_factory=set)  # return语句行号
    function_params: dict[str, set[str]] = field(
        default_factory=dict
    )  # 函数参数及其NULL检查状态
    ownership_transfer: set[str] = field(default_factory=set)  # 所有权转移的函数返回值


class DataFlowAnalyzer:
    """数据流分析器 - 基于tree-sitter实现"""

    def __init__(self):
        """初始化分析器"""
        if not TREE_SITTER_AVAILABLE:
            self.c_parser = None
            self.cpp_parser = None
            return

        # 初始化C和C++解析器
        try:
            self.c_language = Language(tsc.language())
            self.c_parser = Parser(self.c_language)
        except Exception:
            self.c_parser = None

        try:
            self.cpp_language = Language(tscpp.language())
            self.cpp_parser = Parser(self.cpp_language)
        except Exception:
            self.cpp_parser = None

    def analyze_code(
        self,
        code: str,
        is_cpp: bool = False,
        database: Optional["ProjectDatabase"] = None,
        file_path: Optional[str] = None,
    ) -> DataFlowResult:
        """
        分析代码，返回数据流分析结果

        Args:
            code: 源代码
            is_cpp: 是否为C++代码
            database: 项目数据库实例（可选）
            file_path: 文件路径（可选，用于数据库查询）

        Returns:
            DataFlowResult: 数据流分析结果
        """
        result = DataFlowResult()

        # 如果tree-sitter不可用，使用正则表达式回退方案
        if (
            not TREE_SITTER_AVAILABLE
            or (is_cpp and self.cpp_parser is None)
            or (not is_cpp and self.c_parser is None)
        ):
            return self._analyze_with_regex(code, result)

        # 使用tree-sitter解析
        parser = self.cpp_parser if is_cpp else self.c_parser
        if parser is None:
            return self._analyze_with_regex(code, result)

        try:
            tree = parser.parse(bytes(code, "utf8"))
            self._analyze_tree(tree.root_node, code, result)
        except Exception:
            # 解析失败，回退到正则表达式
            return self._analyze_with_regex(code, result)

        # 如果提供了数据库，进行跨文件分析
        if database is not None and file_path is not None:
            self._enhance_with_database(result, database, file_path)

        return result

    def _analyze_tree(self, node: Node, code: str, result: DataFlowResult):
        """
        分析AST树

        Args:
            node: AST节点
            code: 源代码
            result: 分析结果
        """
        if node is None:
            return

        # 遍历AST节点
        self._traverse_node(node, code, result)

    def _traverse_node(self, node: Node, code: str, result: DataFlowResult):
        """
        递归遍历AST节点

        Args:
            node: AST节点
            code: 源代码
            result: 分析结果
        """
        if node is None or node.type is None:
            return

        node_type = node.type

        # 处理函数定义
        if node_type == "function_definition":
            self._handle_function_definition(node, code, result)
        # 处理函数调用
        elif node_type == "call_expression":
            self._handle_call_expression(node, code, result)
        # 处理赋值表达式
        elif node_type == "assignment_expression":
            self._handle_assignment(node, code, result)
        # 处理if语句
        elif node_type == "if_statement":
            self._handle_if_statement(node, code, result)

        # 递归处理子节点
        for child in node.children:
            self._traverse_node(child, code, result)

    def _handle_function_definition(
        self, node: Node, code: str, result: DataFlowResult
    ):
        """
        处理函数定义

        Args:
            node: AST节点
            code: 源代码
            result: 分析结果
        """
        if node is None:
            return

        # 获取函数名
        declarator = node.child_by_field_name("declarator")
        if declarator is None:
            return

        # 提取函数名
        func_name_node = declarator.child_by_field_name("declarator")
        if func_name_node is None:
            return

        # 处理pointer_declarator包裹function_declarator的情况
        if func_name_node.type == "function_declarator":
            # 从function_declarator中提取identifier
            func_name = None
            for child in func_name_node.children:
                if child.type == "identifier":
                    func_name = self._get_node_text(child, code)
                    break
            if func_name is None:
                return
        else:
            func_name = self._get_node_text(func_name_node, code)
        # 提取函数参数
        # 处理pointer_declarator包裹function_declarator的情况
        func_declarator = declarator.child_by_field_name("declarator")
        if func_declarator and func_declarator.type == "function_declarator":
            params = func_declarator.child_by_field_name("parameters")
        else:
            params = declarator.child_by_field_name("parameters")

        if params:
            for param in params.children:
                if param.type == "parameter_declaration":
                    # 提取参数名
                    param_declarator = param.child_by_field_name("declarator")
                    if param_declarator:
                        param_name = self._get_node_text(param_declarator, code)
                        # 去除指针符号
                        param_name = param_name.replace("*", "").strip()
                        if param_name:
                            if func_name not in result.function_params:
                                result.function_params[func_name] = set()
                            result.function_params[func_name].add(param_name)

        # 检测所有权转移：函数返回malloc分配的变量
        # 在函数体内查找malloc和return
        body = node.child_by_field_name("body")
        if body:
            malloc_vars = set()
            self._find_malloc_and_return(body, code, malloc_vars, result)

    def _find_malloc_and_return(
        self, node: Node, code: str, malloc_vars: set, result: DataFlowResult
    ):
        """
        在函数体内查找malloc和return语句

        Args:
            node: AST节点
            code: 源代码
            malloc_vars: malloc分配的变量集合
            result: 分析结果
        """
        if node is None:
            return

        # 检测malloc分配 - 处理declaration类型
        if node.type == "declaration":
            # 查找init_declarator
            for child in node.children:
                if child.type == "init_declarator":
                    # 提取变量名（左侧）
                    declarator = child.child_by_field_name("declarator")
                    if declarator:
                        # 处理pointer_declarator
                        if declarator.type == "pointer_declarator":
                            var_declarator = declarator.child_by_field_name(
                                "declarator"
                            )
                            if var_declarator:
                                var_name = self._get_node_text(var_declarator, code)
                            else:
                                var_name = (
                                    self._get_node_text(declarator, code)
                                    .replace("*", "")
                                    .strip()
                                )
                        else:
                            var_name = self._get_node_text(declarator, code)

                        # 查找右侧的值（可能包含cast_expression）
                        value = child.child_by_field_name("value")
                        if value:
                            # 递归查找cast_expression内部的call_expression
                            call_expr = self._find_call_expression_in_cast(value)
                            if call_expr:
                                func_node = call_expr.child_by_field_name("function")
                                if func_node:
                                    func_name = self._get_node_text(func_node, code)
                                    if func_name in ["malloc", "calloc", "realloc"]:
                                        malloc_vars.add(var_name)

        # 检测malloc分配 - 处理assignment_expression类型
        elif node.type == "assignment_expression":
            right = node.child_by_field_name("right")
            if right:
                # 递归查找cast_expression内部的call_expression
                call_expr = self._find_call_expression_in_cast(right)
                if call_expr:
                    func_node = call_expr.child_by_field_name("function")
                    if func_node:
                        func_name = self._get_node_text(func_node, code)
                        if func_name in ["malloc", "calloc", "realloc"]:
                            left = node.child_by_field_name("left")
                            if left:
                                var_name = self._get_node_text(left, code)
                                malloc_vars.add(var_name)

        # 检测return语句
        if node.type == "return_statement":
            for child in node.children:
                if child.type == "identifier":
                    var_name = self._get_node_text(child, code)
                    if var_name in malloc_vars:
                        result.ownership_transfer.add(var_name)

        # 递归处理子节点
        for child in node.children:
            self._find_malloc_and_return(child, code, malloc_vars, result)

    def _find_call_expression_in_cast(self, node: Node) -> Optional[Node]:
        """
        在cast_expression中查找call_expression

        Args:
            node: AST节点

        Returns:
            Node: 找到的call_expression节点，或None
        """
        if node is None:
            return None

        if node.type == "call_expression":
            return node

        if node.type == "cast_expression":
            # 递归查找cast_expression内部的call_expression
            for child in node.children:
                result = self._find_call_expression_in_cast(child)
                if result:
                    return result

        return None

    def _handle_call_expression(self, node: Node, code: str, result: DataFlowResult):
        """
        处理函数调用表达式

        Args:
            node: AST节点
            code: 源代码
            result: 分析结果
        """
        if node is None:
            return

        # 获取函数名
        func_node = node.child_by_field_name("function")
        if func_node is None:
            return

        func_name = self._get_node_text(func_node, code)

        # 处理free调用
        if func_name == "free":
            args = node.child_by_field_name("arguments")
            if args:
                for child in args.children:
                    if child.type == "identifier":
                        var_name = self._get_node_text(child, code)
                        line = child.start_point[0] + 1
                        result.pointer_states[var_name] = PointerInfo(
                            name=var_name, state=PointerState.FREED, line=line
                        )

    def _handle_assignment(self, node: Node, code: str, result: DataFlowResult):
        """
        处理赋值表达式

        Args:
            node: AST节点
            code: 源代码
            result: 分析结果
        """
        if node is None:
            return

        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")

        if left is None or right is None:
            return

        left_name = self._get_node_text(left, code)
        right_text = self._get_node_text(right, code)
        line = node.start_point[0] + 1

        # 检测NULL赋值
        if right_text in ["NULL", "nullptr", "0"]:
            result.pointer_states[left_name] = PointerInfo(
                name=left_name, state=PointerState.NULLIFIED, line=line
            )

    def _handle_if_statement(self, node: Node, code: str, result: DataFlowResult):
        """
        处理if语句

        Args:
            node: AST节点
            code: 源代码
            result: 分析结果
        """
        if node is None:
            return

        condition = node.child_by_field_name("condition")
        if condition is None:
            return

        line = node.start_point[0] + 1

        # 获取if块的结束行号
        consequence = node.child_by_field_name("consequence")
        if consequence is None:
            return

        scope_end = consequence.end_point[0] + 1

        # 使用AST解析条件表达式
        self._parse_condition(condition, code, line, scope_end, result)

    def _parse_condition(
        self, node: Node, code: str, line: int, scope_end: int, result: DataFlowResult
    ):
        """
        递归解析条件表达式，识别NULL检查

        Args:
            node: AST节点
            code: 源代码
            line: 行号
            scope_end: if块结束行号
            result: 分析结果
        """
        if node is None:
            return

        node_type = node.type

        # 1. 处理括号表达式
        if node_type == "parenthesized_expression":
            # 递归处理内部表达式
            for child in node.children:
                if child.type not in ("(", ")"):
                    self._parse_condition(child, code, line, scope_end, result)
            return

        # 2. 简写形式：identifier（例如 if (buffer)）
        if node_type == "identifier":
            var_name = self._get_node_text(node, code)
            if var_name not in result.null_checks:
                result.null_checks[var_name] = set()
            result.null_checks[var_name].add(line)

            # 添加到null_check_ranges
            if var_name not in result.null_check_ranges:
                result.null_check_ranges[var_name] = []
            result.null_check_ranges[var_name].append((line, scope_end))
            return

        # 2.5. 指针解引用形式：pointer_expression（例如 if (*buffer)）
        if node_type == "pointer_expression":
            # 提取解引用的变量名
            var_name = self._extract_dereferenced_var(node, code)
            if var_name:
                # 记录为解引用检查（格式：*var_name）
                deref_name = f"*{var_name}"
                if deref_name not in result.null_checks:
                    result.null_checks[deref_name] = set()
                result.null_checks[deref_name].add(line)

                # 添加到null_check_ranges
                if deref_name not in result.null_check_ranges:
                    result.null_check_ranges[deref_name] = []
                result.null_check_ranges[deref_name].append((line, scope_end))
            return

        # 3. 比较表达式：binary_expression（例如 if (buffer != NULL)）
        if node_type == "binary_expression":
            operator_node = node.child_by_field_name("operator")
            if operator_node is None:
                return

            operator = self._get_node_text(operator_node, code)
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")

            if left is None or right is None:
                return

            # 处理逻辑运算符（&& 和 ||）
            if operator in ("&&", "||"):
                # 递归处理左右两个条件
                self._parse_condition(left, code, line, scope_end, result)
                self._parse_condition(right, code, line, scope_end, result)
                return

            left_text = self._get_node_text(left, code)
            right_text = self._get_node_text(right, code)

            # 检测 != NULL 或 == NULL（使用AST节点类型识别）
            if operator == "!=":
                # if (buffer != NULL) 或 if (NULL != buffer) 或 if (*buf != NULL)
                var_name = None
                is_deref = False

                if self._is_null_constant(left, code):
                    # NULL != buffer 或 NULL != *buf
                    if right.type == "identifier":
                        var_name = right_text
                    elif right.type == "pointer_expression":
                        var_name = self._extract_dereferenced_var(right, code)
                        is_deref = True
                elif self._is_null_constant(right, code):
                    # buffer != NULL 或 *buf != NULL
                    if left.type == "identifier":
                        var_name = left_text
                    elif left.type == "pointer_expression":
                        var_name = self._extract_dereferenced_var(left, code)
                        is_deref = True

                if var_name is None:
                    return

                # 如果是解引用检查，添加*前缀
                if is_deref:
                    var_name = f"*{var_name}"

                if var_name not in result.null_checks:
                    result.null_checks[var_name] = set()
                result.null_checks[var_name].add(line)

                # 添加到null_check_ranges
                if var_name not in result.null_check_ranges:
                    result.null_check_ranges[var_name] = []
                result.null_check_ranges[var_name].append((line, scope_end))

            elif operator == "==":
                # if (buffer == NULL) 或 if (NULL == buffer)
                # 记录NULL检查，用于误报过滤
                var_name = None
                is_deref = False

                if self._is_null_constant(left, code):
                    # NULL == buffer 或 NULL == *buf
                    if right.type == "identifier":
                        var_name = right_text
                    elif right.type == "pointer_expression":
                        var_name = self._extract_dereferenced_var(right, code)
                        is_deref = True
                elif self._is_null_constant(right, code):
                    # buffer == NULL 或 *buf == NULL
                    if left.type == "identifier":
                        var_name = left_text
                    elif left.type == "pointer_expression":
                        var_name = self._extract_dereferenced_var(left, code)
                        is_deref = True

                if var_name is None:
                    return

                # 如果是解引用检查，添加*前缀
                if is_deref:
                    var_name = f"*{var_name}"

                if var_name not in result.null_checks:
                    result.null_checks[var_name] = set()
                result.null_checks[var_name].add(line)

                # 添加到null_check_ranges
                if var_name not in result.null_check_ranges:
                    result.null_check_ranges[var_name] = []
                result.null_check_ranges[var_name].append((line, scope_end))

            return

        # 4. 否定形式：unary_expression（例如 if (!buffer)）
        if node_type == "unary_expression":
            operator_node = node.child_by_field_name("operator")
            if operator_node is None:
                return

            operator = self._get_node_text(operator_node, code)
            if operator == "!":
                operand = node.child_by_field_name("operand")
                if operand and operand.type == "identifier":
                    # if (!buffer) - 条件块内buffer为NULL，else块内buffer不为NULL
                    # 暂不处理，需要反向逻辑
                    pass

            return

    def _extract_dereferenced_var(self, node: Node, code: str) -> str | None:
        """
        从指针解引用表达式中提取变量名

        Args:
            node: AST节点（pointer_expression）
            code: 源代码

        Returns:
            str | None: 变量名，如果无法提取则返回None
        """
        if node is None or node.type != "pointer_expression":
            return None

        # tree-sitter-c的pointer_expression结构：
        # - 第一个子节点是 '*' (operator字段)
        # - 第二个子节点是identifier或另一个pointer_expression
        # 注意：operand字段可能不存在，需要遍历子节点

        # 尝试获取operand字段
        operand = node.child_by_field_name("operand")
        if operand is None:
            # 如果没有operand字段，遍历子节点找到非operator的节点
            for child in node.children:
                if child.type not in ("*", "operator"):
                    operand = child
                    break

        if operand is None:
            return None

        # 如果操作数是identifier，直接返回变量名
        if operand.type == "identifier":
            return self._get_node_text(operand, code)

        # 如果操作数是指针表达式（多重解引用），递归处理
        if operand.type == "pointer_expression":
            inner_var = self._extract_dereferenced_var(operand, code)
            if inner_var:
                return f"*{inner_var}"

        return None

    def _is_null_constant(self, node: Node, code: str) -> bool:
        """
        判断节点是否为NULL常量

        使用AST节点类型识别，而非字符串匹配：
        - NULL（C宏）→ identifier节点
        - nullptr（C++11）→ nullptr节点
        - 0（整数常量）→ number_literal节点

        Args:
            node: AST节点
            code: 源代码

        Returns:
            bool: 是否为NULL常量
        """
        if node is None:
            return False

        node_type = node.type

        # C++11 nullptr
        if node_type == "nullptr":
            return True

        # C语言 NULL 宏（null节点，tree-sitter-c特定）
        if node_type == "null":
            return True

        # C语言 NULL 宏（identifier节点）
        if node_type == "identifier":
            text = self._get_node_text(node, code)
            return text == "NULL"

        # 整数常量 0
        if node_type == "number_literal":
            text = self._get_node_text(node, code)
            return text == "0"

        return False

    def _get_node_text(self, node: Node, code: str) -> str:
        """
        获取AST节点对应的源代码文本

        Args:
            node: AST节点
            code: 源代码

        Returns:
            str: 节点文本
        """
        if node is None:
            return ""
        start_byte = node.start_byte
        end_byte = node.end_byte
        # 使用字节切片，避免多字节字符问题
        code_bytes = bytes(code, "utf8")
        return code_bytes[start_byte:end_byte].decode("utf8")

    def _analyze_with_regex(self, code: str, result: DataFlowResult) -> DataFlowResult:
        """
        使用正则表达式进行数据流分析（回退方案）

        Args:
            code: 源代码
            result: 分析结果

        Returns:
            DataFlowResult: 分析结果
        """
        lines = code.splitlines()

        # 第零遍：识别函数参数和所有权转移
        self._identify_function_info(lines, result)

        # 第一遍：收集基本信息
        for line_num, line in enumerate(lines, 1):
            # 检测free调用
            free_pattern = r"\bfree\s*\(\s*(\w+)\s*\)"
            for match in re.finditer(free_pattern, line):
                var_name = match.group(1)
                result.pointer_states[var_name] = PointerInfo(
                    name=var_name, state=PointerState.FREED, line=line_num
                )

            # 检测NULL赋值
            null_assign_pattern = r"(\w+)\s*=\s*(NULL|nullptr|0)\s*;"
            for match in re.finditer(null_assign_pattern, line):
                var_name = match.group(1)
                result.pointer_states[var_name] = PointerInfo(
                    name=var_name, state=PointerState.NULLIFIED, line=line_num
                )

            # 检测NULL检查
            null_check_pattern = (
                r"if\s*\(\s*(\w+)\s*(!=\s*(NULL|nullptr|0)|==\s*(NULL|nullptr|0))\s*\)"
            )
            for match in re.finditer(null_check_pattern, line):
                var_name = match.group(1)
                if var_name not in result.null_checks:
                    result.null_checks[var_name] = set()
                result.null_checks[var_name].add(line_num)

            # 检测指针别名
            alias_pattern = r"(\w+)\s*\*\s*(\w+)\s*=\s*(\w+)\s*;"
            for match in re.finditer(alias_pattern, line):
                alias_name = match.group(2)
                original_name = match.group(3)
                if original_name not in result.aliases:
                    result.aliases[original_name] = []
                result.aliases[original_name].append(alias_name)

            # 检测return语句
            if re.search(r"\breturn\b", line):
                result.return_lines.add(line_num)

        # 第二遍：识别死代码
        self._identify_dead_code(lines, result)

        # 第三遍：识别约束条件
        self._identify_constraints(lines, result)

        return result

    def _identify_dead_code(self, lines: list[str], result: DataFlowResult):
        """
        识别死代码

        Args:
            lines: 代码行列表
            result: 分析结果
        """
        # 识别return后的死代码
        for return_line in result.return_lines:
            # 查找return后的代码块（直到下一个}）
            brace_count = 0
            for line_num in range(return_line + 1, len(lines) + 1):
                line = lines[line_num - 1]
                brace_count += line.count("{") - line.count("}")
                if brace_count < 0:
                    break
                result.dead_code_lines.add(line_num)

        # 识别free后置NULL的死代码
        for var_name, pointer_info in result.pointer_states.items():
            if pointer_info.state == PointerState.NULLIFIED:
                # 查找置NULL后的if (var != NULL)块
                nullified_line = pointer_info.line
                for line_num in range(nullified_line + 1, len(lines) + 1):
                    line = lines[line_num - 1]
                    # 检测if (var != NULL)或if (var)
                    if re.search(
                        rf"if\s*\(\s*{var_name}\s*(!=\s*(NULL|nullptr|0)|\))", line
                    ):
                        # 标记if块内的代码为死代码
                        brace_count = 0
                        for inner_line_num in range(line_num, len(lines) + 1):
                            inner_line = lines[inner_line_num - 1]
                            brace_count += inner_line.count("{") - inner_line.count("}")
                            if inner_line_num > line_num:
                                result.dead_code_lines.add(inner_line_num)
                            if brace_count <= 0 and "{" in line:
                                break

    def _identify_function_info(self, lines: list[str], result: DataFlowResult):
        """
        识别函数参数和所有权转移信息

        Args:
            lines: 代码行列表
            result: 分析结果
        """
        # 检测函数定义（更宽松的匹配）
        # 匹配：void func_name(...) 或 int func_name(...) 等
        func_pattern = (
            r"(?:void|int|char|float|double|size_t|\w+)\s+\*?\s*(\w+)\s*\([^)]*\)\s*\{"
        )
        for line_num, line in enumerate(lines, 1):
            match = re.search(func_pattern, line)
            if match:
                func_name = match.group(1)
                # 提取函数参数（改进版本）
                # 匹配模式：char** buf, int* data, void* ptr 等
                # 提取括号内的参数列表
                params_start = line.find("(")
                params_end = line.find(")")
                if params_start != -1 and params_end != -1:
                    params_str = line[params_start + 1 : params_end]
                    # 分割参数，提取参数名
                    # 模式：type* name 或 type *name
                    param_matches = re.findall(r"\w+\s*\*+\s*(\w+)", params_str)
                    for param_name in param_matches:
                        if param_name:
                            if func_name not in result.function_params:
                                result.function_params[func_name] = set()
                            result.function_params[func_name].add(param_name)

                            # 检查函数开头是否有参数NULL检查（前10行内）
                            for check_line_num in range(
                                line_num, min(line_num + 10, len(lines) + 1)
                            ):
                                check_line = lines[check_line_num - 1]
                                # 模式1: if (param != NULL)
                                if re.search(
                                    rf"if\s*\(\s*{param_name}\s*!=\s*(NULL|nullptr|0)\s*\)",
                                    check_line,
                                ):
                                    if param_name not in result.null_checks:
                                        result.null_checks[param_name] = set()
                                    result.null_checks[param_name].add(check_line_num)
                                # 模式2: if (param == NULL) return
                                if re.search(
                                    rf"if\s*\(\s*{param_name}\s*==\s*(NULL|nullptr|0)\s*\)\s*{{?\s*return",
                                    check_line,
                                ):
                                    if param_name not in result.null_checks:
                                        result.null_checks[param_name] = set()
                                    result.null_checks[param_name].add(check_line_num)
                                # 模式3: if (param != NULL && *param != NULL) - 双重检查
                                if re.search(
                                    rf"if\s*\(\s*{param_name}\s*!=\s*(NULL|nullptr|0)\s*&&\s*\*{param_name}\s*!=\s*(NULL|nullptr|0)\s*\)",
                                    check_line,
                                ):
                                    if param_name not in result.null_checks:
                                        result.null_checks[param_name] = set()
                                    result.null_checks[param_name].add(check_line_num)
                                # 模式4: if (param == NULL || *param == NULL) return
                                if re.search(
                                    rf"if\s*\(\s*{param_name}\s*==\s*(NULL|nullptr|0)\s*\|\|\s*\*{param_name}\s*==\s*(NULL|nullptr|0)\s*\)\s*{{?\s*return",
                                    check_line,
                                ):
                                    if param_name not in result.null_checks:
                                        result.null_checks[param_name] = set()
                                    result.null_checks[param_name].add(check_line_num)
                                if param_name not in result.null_checks:
                                    result.null_checks[param_name] = set()
                                result.null_checks[param_name].add(check_line_num)

                # 检测所有权转移：函数返回malloc分配的变量
                # 在函数体内查找return语句
                func_start = line_num
                func_end = line_num
                brace_count = 0
                for end_line_num in range(line_num, len(lines) + 1):
                    func_line = lines[end_line_num - 1]
                    brace_count += func_line.count("{") - func_line.count("}")
                    if brace_count == 0 and "}" in func_line:
                        func_end = end_line_num
                        break

                # 在函数体内查找malloc和return
                malloc_vars = set()
                for body_line_num in range(func_start, func_end + 1):
                    body_line = lines[body_line_num - 1]
                    # 检测malloc分配
                    malloc_match = re.search(
                        r"(\w+)\s*=\s*(?:\([^)]*\))?\s*malloc\s*\(", body_line
                    )
                    if malloc_match:
                        malloc_vars.add(malloc_match.group(1))

                    # 检测return malloc变量
                    for malloc_var in malloc_vars:
                        if re.search(rf"return\s+{malloc_var}\s*;", body_line):
                            result.ownership_transfer.add(malloc_var)

    def _identify_constraints(self, lines: list[str], result: DataFlowResult):
        """
        识别约束条件

        Args:
            lines: 代码行列表
            result: 分析结果
        """
        for line_num, line in enumerate(lines, 1):
            # 检测if条件中的约束
            # 例如: if (len < 100)
            lt_pattern = r"if\s*\(\s*(\w+)\s*<\s*(\w+)\s*\)"
            for match in re.finditer(lt_pattern, line):
                var_name = match.group(1)
                constraint = ConstraintInfo(
                    var_name=var_name,
                    constraint_type="lt",
                    line=line_num,
                    scope_start=line_num,
                )
                result.constraints.append(constraint)

            # 检测if (ptr)或if (ptr != NULL)
            not_null_pattern = r"if\s*\(\s*(\w+)\s*(!=\s*(NULL|nullptr|0)|\))"
            for match in re.finditer(not_null_pattern, line):
                var_name = match.group(1)
                constraint = ConstraintInfo(
                    var_name=var_name,
                    constraint_type="not_null",
                    line=line_num,
                    scope_start=line_num,
                )
                result.constraints.append(constraint)

    def is_safe_access(
        self, var_name: str, access_line: int, result: DataFlowResult
    ) -> bool:
        """
        判断变量访问是否安全

        Args:
            var_name: 变量名
            access_line: 访问行号
            result: 数据流分析结果

        Returns:
            bool: 是否安全
        """
        # 如果变量没有被释放，则安全
        if var_name not in result.pointer_states:
            return True

        pointer_info = result.pointer_states[var_name]

        # 如果变量被置NULL，检查是否有NULL检查
        if pointer_info.state == PointerState.NULLIFIED:
            # 检查是否有NULL检查保护
            if var_name in result.null_checks:
                for check_line in result.null_checks[var_name]:
                    if check_line < access_line:
                        return True
            return False

        # 如果变量被释放，检查是否在释放后被置NULL
        if pointer_info.state == PointerState.FREED:
            # 检查是否在释放后被置NULL
            for name, info in result.pointer_states.items():
                if name == var_name and info.state == PointerState.NULLIFIED:
                    if info.line > pointer_info.line:
                        # 释放后置NULL，检查是否有NULL检查
                        if var_name in result.null_checks:
                            for check_line in result.null_checks[var_name]:
                                if check_line < access_line:
                                    return True
            return False

        return True

    def _enhance_with_database(
        self,
        result: DataFlowResult,
        database: "ProjectDatabase",
        file_path: str,
    ) -> None:
        """
        利用数据库信息增强数据流分析结果

        Args:
            result: 单文件分析结果
            database: 项目数据库实例
            file_path: 当前文件路径
        """
        if database is None or not file_path:
            return

        try:
            # 1. 跨文件指针状态追踪
            for var_name, ptr_info in result.pointer_states.items():
                # 查询数据库中的指针状态
                db_states = database.find_pointer_states(var_name)
                if db_states:
                    # 合并数据库中的指针状态信息
                    for state_record in db_states:
                        # 如果数据库中有其他文件的状态信息，更新结果
                        if state_record.file_path != file_path:
                            # 添加跨文件的指针状态信息
                            cross_file_key = f"{state_record.file_path}:{var_name}"
                            result.pointer_states[cross_file_key] = PointerInfo(
                                name=var_name,
                                state=PointerState(state_record.state),
                                line=state_record.line,
                                scope=state_record.scope or "global",
                            )

            # 2. 跨文件数据流分析
            for var_name in result.pointer_states.keys():
                # 查询数据库中的变量定义和使用
                definitions = database.find_variable_definitions(var_name)
                uses = database.find_variable_uses(var_name)

                # 添加跨文件的定义和使用信息
                for def_record in definitions:
                    if def_record.file_path != file_path:
                        # 记录跨文件定义
                        cross_def_key = f"{def_record.file_path}:{var_name}@def"
                        result.pointer_states[cross_def_key] = PointerInfo(
                            name=var_name,
                            state=PointerState.UNKNOWN,
                            line=def_record.line,
                            scope=def_record.scope or "global",
                        )

                for use_record in uses:
                    if use_record.file_path != file_path:
                        # 记录跨文件使用
                        cross_use_key = f"{use_record.file_path}:{var_name}@use"
                        result.pointer_states[cross_use_key] = PointerInfo(
                            name=var_name,
                            state=PointerState.UNKNOWN,
                            line=use_record.line,
                            scope=use_record.scope or "global",
                        )

            # 3. 跨文件调用关系分析
            # 查询当前文件中函数的调用者和被调用者
            # 这部分信息可以用于污点分析的跨函数追踪

        except Exception:
            # 数据库查询失败时静默忽略，不影响单文件分析结果
            pass


def analyze_c_cpp_text_with_dataflow(
    relpath: str, text: str
) -> tuple[list, DataFlowResult]:
    """
    分析C/C++代码，返回启发式问题和数据流分析结果

    Args:
        relpath: 文件路径
        text: 源代码

    Returns:
        tuple: (启发式问题列表, 数据流分析结果)
    """
    from .checkers.c_checker import analyze_c_cpp_text

    # 执行启发式扫描
    issues = analyze_c_cpp_text(relpath, text)

    # 执行数据流分析
    analyzer = DataFlowAnalyzer()
    is_cpp = relpath.endswith((".cpp", ".cxx", ".cc", ".hpp", ".hxx"))
    dataflow_result = analyzer.analyze_code(text, is_cpp)

    return issues, dataflow_result
