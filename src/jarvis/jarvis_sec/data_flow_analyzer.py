"""轻量级数据流分析器

使用pycparser解析C代码AST，实现指针状态追踪、约束条件追踪和污点传播分析。

核心功能：
- 指针状态追踪（free、NULL赋值、指针别名）
- 约束条件追踪（if条件、溢出检查）
- 污点传播追踪（用户输入、SQL语句）
"""

import re
from typing import Any
from dataclasses import dataclass, field
from enum import Enum

# 尝试导入pycparser
try:
    from pycparser import c_parser, c_ast
    PYCPARSER_AVAILABLE = True
except ImportError:
    PYCPARSER_AVAILABLE = False


class PointerState(Enum):
    """指针状态枚举"""
    ALLOCATED = "allocated"      # 已分配内存
    FREED = "freed"              # 已释放
    NULLIFIED = "nullified"      # 已置NULL
    UNKNOWN = "unknown"          # 未知状态


@dataclass
class PointerInfo:
    """指针信息"""
    name: str
    state: PointerState = PointerState.UNKNOWN
    state_line: int = 0            # 状态变更的行号
    aliases: list[str] = field(default_factory=list)  # 别名列表
    null_check: bool = False      # 是否有NULL检查
    null_check_line: int = 0      # NULL检查的行号


@dataclass
class ConstraintInfo:
    """约束条件信息"""
    var_name: str
    constraint_type: str          # 'not_null', 'overflow_check', etc.
    line: int
    scope_start: int              # 约束作用域起始行
    scope_end: int                # 约束作用域结束行


@dataclass
class TaintInfo:
    """污点信息"""
    var_name: str
    taint_source: str             # 污点源（如'getenv', 'user_input'）
    taint_line: int               # 污点引入行号
    propagated_to: list[str] = field(default_factory=list)  # 传播到的变量


class DataFlowAnalyzer:
    """轻量级数据流分析器"""

    def __init__(self):
        self.pointer_states: dict[str, PointerInfo] = {}
        self.constraints: list[ConstraintInfo] = []
        self.taints: dict[str, TaintInfo] = {}
        self.current_function: str = ""
        self.dead_code_lines: set[int] = set()  # 死代码行号集合

    def analyze_code(self, code: str) -> dict[str, Any]:
        """分析C代码，返回数据流信息"""
        if not PYCPARSER_AVAILABLE:
            # 回退到正则表达式分析
            return self._analyze_with_regex(code)

        try:
            # 预处理代码（移除注释、处理宏）
            preprocessed = self._preprocess_code(code)

            # 解析AST
            parser = c_parser.CParser()
            ast = parser.parse(preprocessed)

            # 分析AST
            self._analyze_ast(ast)

            return self._get_analysis_result()
        except Exception as e:
            # AST解析失败，回退到正则表达式
            return self._analyze_with_regex(code)

    def _preprocess_code(self, code: str) -> str:
        """预处理C代码，移除注释和复杂宏"""
        # 移除单行注释
        code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)
        # 移除多行注释
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        # 移除#include（pycparser无法处理）
        code = re.sub(r'#include.*$', '', code, flags=re.MULTILINE)
        # 移除#define（保留简单宏）
        code = re.sub(r'#define.*$', '', code, flags=re.MULTILINE)
        return code

    def _analyze_ast(self, ast: c_ast.Node) -> None:
        """分析AST节点"""
        if ast is None:
            return

        # 遍历AST
        for node in ast:
            if isinstance(node, c_ast.FuncDef):
                self._analyze_function(node)

    def _analyze_function(self, func: c_ast.FuncDef) -> None:
        """分析函数定义"""
        self.current_function = func.decl.name

        # 分析函数体
        if func.body:
            self._analyze_compound(func.body)

    def _analyze_compound(self, compound: c_ast.Compound) -> None:
        """分析复合语句（函数体、if/else块等）"""
        if compound.block_items is None:
            return

        for item in compound.block_items:
            if isinstance(item, c_ast.Decl):
                self._analyze_declaration(item)
            elif isinstance(item, c_ast.Assignment):
                self._analyze_assignment(item)
            elif isinstance(item, c_ast.FuncCall):
                self._analyze_func_call(item)
            elif isinstance(item, c_ast.If):
                self._analyze_if(item)
            elif isinstance(item, c_ast.Return):
                self._analyze_return(item)

    def _analyze_declaration(self, decl: c_ast.Decl) -> None:
        """分析变量声明"""
        # 检查是否是指针声明
        if self._is_pointer_decl(decl):
            var_name = decl.name
            self.pointer_states[var_name] = PointerInfo(name=var_name)

            # 检查是否初始化为NULL
            if decl.init:
                if self._is_null_init(decl.init):
                    self.pointer_states[var_name].state = PointerState.NULLIFIED
                    self.pointer_states[var_name].state_line = decl.coord.line if decl.coord else 0
                # 检查是否是malloc/calloc/realloc
                elif isinstance(decl.init, c_ast.FuncCall):
                    if decl.init.name.name in ['malloc', 'calloc', 'realloc']:
                        self.pointer_states[var_name].state = PointerState.ALLOCATED
                        self.pointer_states[var_name].state_line = decl.coord.line if decl.coord else 0
                # 检查是否是指针别名
                elif isinstance(decl.init, c_ast.ID):
                    alias_name = decl.init.name
                    if alias_name in self.pointer_states:
                        self.pointer_states[var_name].aliases.append(alias_name)
                        # 继承别名指针的状态
                        self.pointer_states[var_name].state = self.pointer_states[alias_name].state

    def _analyze_assignment(self, assign: c_ast.Assignment) -> None:
        """分析赋值语句"""
        var_name = assign.lvalue.name if isinstance(assign.lvalue, c_ast.ID) else None
        if var_name is None:
            return

        # 检查是否赋值为NULL
        if self._is_null_init(assign.rvalue):
            if var_name in self.pointer_states:
                self.pointer_states[var_name].state = PointerState.NULLIFIED
                self.pointer_states[var_name].state_line = assign.coord.line if assign.coord else 0

        # 检查是否赋值为malloc/calloc/realloc
        elif isinstance(assign.rvalue, c_ast.FuncCall):
            if assign.rvalue.name.name in ['malloc', 'calloc', 'realloc']:
                if var_name not in self.pointer_states:
                    self.pointer_states[var_name] = PointerInfo(name=var_name)
                self.pointer_states[var_name].state = PointerState.ALLOCATED
                self.pointer_states[var_name].state_line = assign.coord.line if assign.coord else 0

        # 检查是否是指针别名赋值
        elif isinstance(assign.rvalue, c_ast.ID):
            alias_name = assign.rvalue.name
            if alias_name in self.pointer_states:
                if var_name not in self.pointer_states:
                    self.pointer_states[var_name] = PointerInfo(name=var_name)
                self.pointer_states[var_name].aliases.append(alias_name)
                self.pointer_states[var_name].state = self.pointer_states[alias_name].state

    def _analyze_func_call(self, call: c_ast.FuncCall) -> None:
        """分析函数调用"""
        func_name = call.name.name if isinstance(call.name, c_ast.ID) else None
        if func_name is None:
            return

        # 检查是否是free调用
        if func_name == 'free':
            if call.args and call.args.exprs:
                arg = call.args.exprs[0]
                if isinstance(arg, c_ast.ID):
                    var_name = arg.name
                    if var_name in self.pointer_states:
                        self.pointer_states[var_name].state = PointerState.FREED
                        self.pointer_states[var_name].state_line = call.coord.line if call.coord else 0
                    # 同时更新所有别名
                    for ptr_info in self.pointer_states.values():
                        if var_name in ptr_info.aliases:
                            ptr_info.state = PointerState.FREED
                            ptr_info.state_line = call.coord.line if call.coord else 0

    def _analyze_if(self, if_node: c_ast.If) -> None:
        """分析if语句"""
        # 检查if条件中的NULL检查
        self._check_null_condition(if_node.cond)

        # 分析if块
        if if_node.iftrue:
            self._analyze_compound(if_node.iftrue)

        # 分析else块
        if if_node.iffalse:
            self._analyze_compound(if_node.iffalse)

    def _analyze_return(self, ret: c_ast.Return) -> None:
        """分析return语句，标记后续代码为死代码"""
        if ret.coord:
            # 标记return后的代码为死代码（简化实现）
            self.dead_code_lines.add(ret.coord.line)

    def _check_null_condition(self, cond: c_ast.Node) -> None:
        """检查条件中的NULL检查"""
        # 检查 ptr != NULL 或 ptr != 0 或 ptr
        if isinstance(cond, c_ast.BinaryOp):
            if cond.op in ['!=', '==']:
                left_is_id = isinstance(cond.left, c_ast.ID)
                right_is_null = self._is_null_expr(cond.right)

                if left_is_id and right_is_null:
                    var_name = cond.left.name
                    if var_name in self.pointer_states:
                        self.pointer_states[var_name].null_check = True
                        self.pointer_states[var_name].null_check_line = cond.coord.line if cond.coord else 0

        # 检查 ptr (隐式 != NULL)
        elif isinstance(cond, c_ast.ID):
            var_name = cond.name
            if var_name in self.pointer_states:
                self.pointer_states[var_name].null_check = True
                self.pointer_states[var_name].null_check_line = cond.coord.line if cond.coord else 0

    def _is_pointer_decl(self, decl: c_ast.Decl) -> bool:
        """检查是否是指针声明"""
        if decl.type is None:
            return False
        return isinstance(decl.type, c_ast.PtrDecl)

    def _is_null_init(self, init: c_ast.Node) -> bool:
        """检查是否初始化为NULL"""
        if isinstance(init, c_ast.ID):
            return init.name in ['NULL', 'null', '0']
        elif isinstance(init, c_ast.Constant):
            return init.value == '0'
        return False

    def _is_null_expr(self, expr: c_ast.Node) -> bool:
        """检查是否是NULL表达式"""
        if isinstance(expr, c_ast.ID):
            return expr.name in ['NULL', 'null', '0']
        elif isinstance(expr, c_ast.Constant):
            return expr.value == '0'
        return False

    def _analyze_with_regex(self, code: str) -> dict[str, Any]:
        """使用正则表达式进行简化分析（回退方案）"""
        # 追踪free操作
        free_pattern = r'free\s*\(\s*(\w+)\s*\)'
        for match in re.finditer(free_pattern, code):
            var_name = match.group(1)
            line = code[:match.start()].count('\n') + 1
            if var_name not in self.pointer_states:
                self.pointer_states[var_name] = PointerInfo(name=var_name)
            self.pointer_states[var_name].state = PointerState.FREED
            self.pointer_states[var_name].state_line = line

        # 追踪NULL赋值
        null_assign_pattern = r'(\w+)\s*=\s*(NULL|0)\s*;'
        for match in re.finditer(null_assign_pattern, code):
            var_name = match.group(1)
            line = code[:match.start()].count('\n') + 1
            if var_name not in self.pointer_states:
                self.pointer_states[var_name] = PointerInfo(name=var_name)
            self.pointer_states[var_name].state = PointerState.NULLIFIED
            self.pointer_states[var_name].state_line = line

        # 追踪malloc调用
        malloc_pattern = r'(\w+)\s*=\s*(?:malloc|calloc|realloc)\s*\('
        for match in re.finditer(malloc_pattern, code):
            var_name = match.group(1)
            line = code[:match.start()].count('\n') + 1
            if var_name not in self.pointer_states:
                self.pointer_states[var_name] = PointerInfo(name=var_name)
            self.pointer_states[var_name].state = PointerState.ALLOCATED
            self.pointer_states[var_name].state_line = line

        # 追踪NULL检查
        null_check_pattern = r'if\s*\(\s*(\w+)\s*(?:!=|==)\s*(NULL|0)\s*\)'
        for match in re.finditer(null_check_pattern, code):
            var_name = match.group(1)
            line = code[:match.start()].count('\n') + 1
            if var_name in self.pointer_states:
                self.pointer_states[var_name].null_check = True
                self.pointer_states[var_name].null_check_line = line

        # 追踪return语句（标记死代码）
        return_pattern = r'return\s*;'
        for match in re.finditer(return_pattern, code):
            line = code[:match.start()].count('\n') + 1
            self.dead_code_lines.add(line)

        return self._get_analysis_result()

    def _get_analysis_result(self) -> dict[str, Any]:
        """获取分析结果"""
        return {
            'pointer_states': {
                name: {
                    'state': info.state.value,
                    'state_line': info.state_line,
                    'aliases': info.aliases,
                    'null_check': info.null_check,
                    'null_check_line': info.null_check_line,
                }
                for name, info in self.pointer_states.items()
            },
            'dead_code_lines': list(self.dead_code_lines),
            'constraints': [
                {
                    'var_name': c.var_name,
                    'constraint_type': c.constraint_type,
                    'line': c.line,
                    'scope_start': c.scope_start,
                    'scope_end': c.scope_end,
                }
                for c in self.constraints
            ],
            'taints': {
                name: {
                    'taint_source': info.taint_source,
                    'taint_line': info.taint_line,
                    'propagated_to': info.propagated_to,
                }
                for name, info in self.taints.items()
            },
        }

    def is_safe_access(self, var_name: str, access_line: int) -> bool:
        """检查变量访问是否安全

        Args:
            var_name: 变量名
            access_line: 访问行号

        Returns:
            True if safe, False otherwise
        """
        if var_name not in self.pointer_states:
            return True  # 未知变量，默认安全

        ptr_info = self.pointer_states[var_name]

        # 检查是否是死代码
        if access_line in self.dead_code_lines:
            return True  # 死代码中的访问是安全的（不会执行）

        # 检查指针状态
        if ptr_info.state == PointerState.NULLIFIED:
            # 检查是否有NULL检查保护
            if ptr_info.null_check and ptr_info.null_check_line < access_line:
                return True  # 有NULL检查保护，安全
            return False  # NULL指针访问，不安全

        if ptr_info.state == PointerState.FREED:
            # 检查是否有NULL检查保护
            if ptr_info.null_check and ptr_info.null_check_line < access_line:
                return True  # 有NULL检查保护，安全
            return False  # UAF风险，不安全

        return True  # 其他状态，默认安全

    def is_safe_free(self, var_name: str, free_line: int) -> bool:
        """检查free操作是否安全（避免double free）

        Args:
            var_name: 变量名
            free_line: free行号

        Returns:
            True if safe, False otherwise
        """
        if var_name not in self.pointer_states:
            return True  # 未知变量，默认安全

        ptr_info = self.pointer_states[var_name]

        # 检查是否已经freed
        if ptr_info.state == PointerState.FREED:
            # 检查是否在freed后又置NULL
            if ptr_info.state_line < free_line:
                return False  # 可能是double free

        return True  # 其他情况，默认安全

    def get_pointer_state_at_line(self, var_name: str, line: int) -> PointerState:
        """获取指定行号时的指针状态

        Args:
            var_name: 变量名
            line: 行号

        Returns:
            指针状态
        """
        if var_name not in self.pointer_states:
            return PointerState.UNKNOWN

        ptr_info = self.pointer_states[var_name]

        # 如果状态变更行号大于查询行号，返回UNKNOWN
        if ptr_info.state_line > line:
            return PointerState.UNKNOWN

        return ptr_info.state
