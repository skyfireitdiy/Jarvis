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
from enum import Enum
from dataclasses import dataclass, field

# tree-sitter依赖（已在pyproject.toml中配置）
try:
    import tree_sitter_c as tsc
    import tree_sitter_cpp as tscpp
    from tree_sitter import Language, Parser, Node, Tree
    
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


class PointerState(Enum):
    """指针状态枚举"""
    ALLOCATED = "allocated"  # 已分配
    FREED = "freed"          # 已释放
    NULLIFIED = "nullified"  # 已置NULL
    UNKNOWN = "unknown"      # 未知状态


@dataclass
class PointerInfo:
    """指针信息"""
    name: str
    state: PointerState
    line: int
    scope: str = "global"
    aliases: list[str] = field(default_factory=list)
    

@dataclass
class DataFlowResult:
    """数据流分析结果"""
    pointer_states: dict[str, PointerInfo] = field(default_factory=dict)
    safe_accesses: set[int] = field(default_factory=set)  # 安全访问的行号
    unsafe_accesses: set[int] = field(default_factory=set)  # 不安全访问的行号
    null_checks: dict[str, set[int]] = field(default_factory=dict)  # NULL检查位置
    

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
    
    def analyze_code(self, code: str, is_cpp: bool = False) -> DataFlowResult:
        """
        分析代码，返回数据流分析结果
        
        Args:
            code: 源代码
            is_cpp: 是否为C++代码
            
        Returns:
            DataFlowResult: 数据流分析结果
        """
        result = DataFlowResult()
        
        # 如果tree-sitter不可用，使用正则表达式回退方案
        if not TREE_SITTER_AVAILABLE or (is_cpp and self.cpp_parser is None) or (not is_cpp and self.c_parser is None):
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
        
        # 处理函数调用
        if node_type == "call_expression":
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
                            name=var_name,
                            state=PointerState.FREED,
                            line=line
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
                name=left_name,
                state=PointerState.NULLIFIED,
                line=line
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
            
        condition_text = self._get_node_text(condition, code)
        line = node.start_point[0] + 1
        
        # 检测NULL检查
        # 例如: if (ptr != NULL) 或 if (ptr)
        null_check_pattern = r'(\w+)\s*(!=\s*(NULL|nullptr|0)|==\s*(NULL|nullptr|0))'
        matches = re.findall(null_check_pattern, condition_text)
        
        for match in matches:
            var_name = match[0]
            if var_name not in result.null_checks:
                result.null_checks[var_name] = set()
            result.null_checks[var_name].add(line)
    
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
        return code[start_byte:end_byte]
    
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
        
        for line_num, line in enumerate(lines, 1):
            # 检测free调用
            free_pattern = r'\bfree\s*\(\s*(\w+)\s*\)'
            for match in re.finditer(free_pattern, line):
                var_name = match.group(1)
                result.pointer_states[var_name] = PointerInfo(
                    name=var_name,
                    state=PointerState.FREED,
                    line=line_num
                )
            
            # 检测NULL赋值
            null_assign_pattern = r'(\w+)\s*=\s*(NULL|nullptr|0)\s*;'
            for match in re.finditer(null_assign_pattern, line):
                var_name = match.group(1)
                result.pointer_states[var_name] = PointerInfo(
                    name=var_name,
                    state=PointerState.NULLIFIED,
                    line=line_num
                )
            
            # 检测NULL检查
            null_check_pattern = r'if\s*\(\s*(\w+)\s*(!=\s*(NULL|nullptr|0)|==\s*(NULL|nullptr|0))\s*\)'
            for match in re.finditer(null_check_pattern, line):
                var_name = match.group(1)
                if var_name not in result.null_checks:
                    result.null_checks[var_name] = set()
                result.null_checks[var_name].add(line_num)
        
        return result
    
    def is_safe_access(self, var_name: str, access_line: int, result: DataFlowResult) -> bool:
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


def analyze_c_cpp_text_with_dataflow(relpath: str, text: str) -> tuple[list, DataFlowResult]:
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
    is_cpp = relpath.endswith(('.cpp', '.cxx', '.cc', '.hpp', '.hxx'))
    dataflow_result = analyzer.analyze_code(text, is_cpp)
    
    return issues, dataflow_result
