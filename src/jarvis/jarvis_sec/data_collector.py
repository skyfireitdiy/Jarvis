# -*- coding: utf-8 -*-
"""
数据收集器 - 基于tree-sitter提取项目级分析数据

核心功能：
1. 符号提取（函数、变量、类型定义）
2. 调用关系提取（函数调用、参数传递）
3. 数据流提取（变量定义、使用、参数传递）
4. 指针状态提取（malloc、free、NULL赋值）
5. 类型信息提取（struct、union、enum、typedef）

输出到ProjectDatabase进行持久化存储
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jarvis.jarvis_utils.output import PrettyOutput

# tree-sitter依赖
try:
    import tree_sitter_c as tsc
    import tree_sitter_cpp as tscpp
    from tree_sitter import Language, Parser, Node

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    Node = None  # 类型回退

# Rust解析器
try:
    import tree_sitter_rust as tsrust

    TREE_SITTER_RUST_AVAILABLE = True
except ImportError:
    TREE_SITTER_RUST_AVAILABLE = False

from .project_database import (
    ProjectDatabase,
    SymbolInfo,
    CallRelation,
    DataFlowNode,
    PointerStateRecord,
    TypeInfo,
    create_file_info,
)


# ============================================================================
# 数据收集器
# ============================================================================


class DataCollector:
    """数据收集器 - 基于tree-sitter提取分析数据"""

    def __init__(self, database: ProjectDatabase):
        """
        初始化数据收集器

        Args:
            database: 项目数据库实例
        """
        self.database = database

        if not TREE_SITTER_AVAILABLE:
            PrettyOutput.auto_print(
                "[DataCollector] tree-sitter不可用，将使用正则表达式回退方案"
            )
            self.c_parser = None
            self.cpp_parser = None
            self.rust_parser = None
            return

        # 初始化C和C++解析器
        try:
            self.c_language = Language(tsc.language())
            self.c_parser = Parser(self.c_language)
        except Exception as e:
            PrettyOutput.auto_print(f"[DataCollector] C解析器初始化失败: {e}")
            self.c_parser = None

        try:
            self.cpp_language = Language(tscpp.language())
            self.cpp_parser = Parser(self.cpp_language)
        except Exception as e:
            PrettyOutput.auto_print(f"[DataCollector] C++解析器初始化失败: {e}")
            self.cpp_parser = None

        # 初始化Rust解析器
        if TREE_SITTER_RUST_AVAILABLE:
            try:
                self.rust_language = Language(tsrust.language())
                self.rust_parser = Parser(self.rust_language)
            except Exception as e:
                PrettyOutput.auto_print(f"[DataCollector] Rust解析器初始化失败: {e}")
                self.rust_parser = None
        else:
            self.rust_parser = None

    # ============================================================================
    # 文件分析入口
    # ============================================================================

    def analyze_file(self, file_path: str, language: str) -> Dict[str, Any]:
        """
        分析单个文件，提取所有数据

        Args:
            file_path: 文件路径
            language: 语言类型（c, cpp, rust）

        Returns:
            分析结果字典
        """
        result = {
            "symbols": [],
            "call_relations": [],
            "data_flow_nodes": [],
            "pointer_states": [],
            "type_infos": [],
        }

        # 检查文件是否存在
        if not Path(file_path).exists():
            PrettyOutput.auto_print(f"[DataCollector] 文件不存在: {file_path}")
            return result

        # 读取文件内容
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                code = f.read()
        except Exception as e:
            PrettyOutput.auto_print(f"[DataCollector] 读取文件失败: {e}")
            return result

        # 创建文件信息
        file_info = create_file_info(file_path, language)
        self.database.add_file(file_info)

        # 根据语言选择解析器
        if language == "rust":
            return self._analyze_rust_file(file_path, code, result)

        # 使用tree-sitter解析C/C++
        if TREE_SITTER_AVAILABLE and (self.c_parser or self.cpp_parser):
            parser = self.cpp_parser if language in ["cpp", "c++"] else self.c_parser
            if parser:
                try:
                    tree = parser.parse(bytes(code, "utf8"))
                    self._extract_from_ast(tree.root_node, code, file_path, result)
                except Exception as e:
                    PrettyOutput.auto_print(f"[DataCollector] AST解析失败: {e}")
                    # 回退到正则表达式
                    self._extract_with_regex(code, file_path, result)
            else:
                # 解析器不可用，使用正则表达式
                self._extract_with_regex(code, file_path, result)
        else:
            # tree-sitter不可用，使用正则表达式
            self._extract_with_regex(code, file_path, result)

        # 保存到数据库
        self._save_to_database(file_path, result)

        return result

    def analyze_files_batch(
        self, file_paths: List[str], language: str
    ) -> Dict[str, Any]:
        """
        批量分析文件

        Args:
            file_paths: 文件路径列表
            language: 语言类型

        Returns:
            总体分析结果
        """
        total_result = {
            "total_files": len(file_paths),
            "total_symbols": 0,
            "total_call_relations": 0,
            "total_data_flow_nodes": 0,
            "total_pointer_states": 0,
            "total_type_infos": 0,
            "failed_files": [],
        }

        for file_path in file_paths:
            try:
                result = self.analyze_file(file_path, language)
                total_result["total_symbols"] += len(result["symbols"])
                total_result["total_call_relations"] += len(result["call_relations"])
                total_result["total_data_flow_nodes"] += len(result["data_flow_nodes"])
                total_result["total_pointer_states"] += len(result["pointer_states"])
                total_result["total_type_infos"] += len(result["type_infos"])
            except Exception as e:
                total_result["failed_files"].append(
                    {"file": file_path, "error": str(e)}
                )

        PrettyOutput.auto_print(
            f"[DataCollector] 批量分析完成: {total_result['total_files']}个文件, "
            f"{total_result['total_symbols']}个符号, "
            f"{total_result['total_call_relations']}个调用关系"
        )

        return total_result

    # ============================================================================
    # Rust AST提取方法
    # ============================================================================

    def _analyze_rust_file(
        self, file_path: str, code: str, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        分析Rust文件

        Args:
            file_path: 文件路径
            code: 源代码
            result: 结果字典

        Returns:
            分析结果字典
        """
        if not self.rust_parser:
            PrettyOutput.auto_print("[DataCollector] Rust解析器不可用")
            return result

        try:
            tree = self.rust_parser.parse(bytes(code, "utf8"))
            self._extract_rust_from_ast(tree.root_node, code, file_path, result)
        except Exception as e:
            PrettyOutput.auto_print(f"[DataCollector] Rust AST解析失败: {e}")

        # 保存到数据库
        self._save_to_database(file_path, result)

        return result

    def _extract_rust_from_ast(
        self, node, code: str, file_path: str, result: Dict[str, Any]
    ):
        """
        从Rust AST提取数据

        Args:
            node: AST根节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
        """
        if node is None:
            return

        self._traverse_rust_ast(node, code, file_path, result)

    def _traverse_rust_ast(
        self,
        node,
        code: str,
        file_path: str,
        result: Dict[str, Any],
        scope: str = "global",
    ):
        """
        递归遍历Rust AST

        Args:
            node: AST节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
            scope: 当前作用域
        """
        if node is None or node.type is None:
            return

        node_type = node.type

        # 处理函数定义
        if node_type == "function_item":
            self._handle_rust_function_definition(node, code, file_path, result)
            # 进入函数作用域
            func_name = self._get_rust_function_name(node, code)
            new_scope = func_name if func_name else scope
            # 注意：不单独遍历body，由最后的for child递归统一处理
            # 但需要传递new_scope给子节点
            for child in node.children:
                self._traverse_rust_ast(child, code, file_path, result, new_scope)
            return  # 已递归子节点，跳过最后的for child

        # 处理结构体定义
        elif node_type == "struct_item":
            self._handle_rust_struct_definition(node, code, file_path, result)

        # 处理枚举定义
        elif node_type == "enum_item":
            self._handle_rust_enum_definition(node, code, file_path, result)

        # 处理impl块
        elif node_type == "impl_item":
            self._handle_rust_impl_block(node, code, file_path, result)

        # 处理extern块
        elif node_type == "extern_mod":
            self._handle_rust_extern_block(node, code, file_path, result)

        # 处理unsafe块
        elif node_type == "unsafe_block":
            self._handle_rust_unsafe_block(node, code, file_path, result, scope)

        # 处理let声明（变量绑定）
        elif node_type == "let_declaration":
            self._handle_rust_let_declaration(node, code, file_path, result, scope)

        # 处理函数调用
        elif node_type == "call_expression":
            self._handle_rust_call_expression(node, code, file_path, result, scope)

        # 处理方法调用
        elif node_type == "method_call_expression":
            self._handle_rust_method_call(node, code, file_path, result, scope)

        # 处理宏调用
        elif node_type == "macro_invocation":
            self._handle_rust_macro_invocation(node, code, file_path, result, scope)

        # 递归处理子节点
        for child in node.children:
            self._traverse_rust_ast(child, code, file_path, result, scope)

    # ============================================================================
    # AST提取方法
    # ============================================================================

    def _extract_from_ast(
        self, node: Node, code: str, file_path: str, result: Dict[str, Any]
    ):
        """
        从AST提取数据

        Args:
            node: AST根节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
        """
        if node is None:
            return

        self._traverse_ast(node, code, file_path, result)

    def _traverse_ast(
        self,
        node: Node,
        code: str,
        file_path: str,
        result: Dict[str, Any],
        scope: str = "global",
    ):
        """
        递归遍历AST

        Args:
            node: AST节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
            scope: 当前作用域
        """
        if node is None or node.type is None:
            return

        node_type = node.type

        # 处理函数定义
        if node_type == "function_definition":
            self._handle_function_definition(node, code, file_path, result)
            # 进入函数作用域
            func_name = self._get_function_name(node, code)
            new_scope = func_name if func_name else scope
            # 遍历函数体
            body_node = node.child_by_field_name("body")
            if body_node:
                self._traverse_ast(body_node, code, file_path, result, new_scope)

        # 处理类型定义
        elif node_type in [
            "struct_specifier",
            "union_specifier",
            "enum_specifier",
            "type_definition",
        ]:
            self._handle_type_definition(node, code, file_path, result)

        # 处理变量声明
        elif node_type == "declaration":
            self._handle_declaration(node, code, file_path, result, scope)

        # 处理函数调用
        elif node_type == "call_expression":
            self._handle_call_expression(node, code, file_path, result, scope)

        # 处理赋值表达式
        elif node_type == "assignment_expression":
            self._handle_assignment(node, code, file_path, result, scope)

        # 处理指针相关操作
        elif node_type in ["malloc_call", "calloc_call", "realloc_call", "free_call"]:
            self._handle_memory_operation(node, code, file_path, result, scope)

        # 处理if语句（提取条件表达式中的变量使用）
        elif node_type == "if_statement":
            self._handle_if_statement(node, code, file_path, result, scope)

        # 处理while/for循环（提取条件表达式中的变量使用）
        elif node_type in ["while_statement", "for_statement"]:
            self._handle_loop_statement(node, code, file_path, result, scope)

        # 处理return语句（检测所有权转移）
        elif node_type == "return_statement":
            self._handle_return_statement(node, code, file_path, result, scope)

        # 递归处理子节点
        for child in node.children:
            self._traverse_ast(child, code, file_path, result, scope)

    def _handle_function_definition(
        self, node: Node, code: str, file_path: str, result: Dict[str, Any]
    ):
        """
        处理函数定义

        Args:
            node: AST节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
        """
        # 获取函数名
        func_name = self._get_function_name(node, code)
        if not func_name:
            return

        # 获取函数签名
        signature = self._get_node_text(node, code)

        # 获取行号范围
        line_start = node.start_point[0] + 1  # tree-sitter行号从0开始
        line_end = node.end_point[0] + 1

        # 提取参数
        params = self._extract_function_params(node, code)

        # 创建符号信息
        symbol = SymbolInfo(
            name=func_name,
            kind="function",
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            signature=signature,
            scope="global",
            is_external=False,
        )
        result["symbols"].append(symbol)

        # 为参数创建数据流节点
        for param in params:
            param_node = DataFlowNode(
                var_name=param,
                file_path=file_path,
                line=line_start,
                node_type="param_in",
                scope=func_name,
                value_source="parameter",
            )
            result["data_flow_nodes"].append(param_node)

    def _handle_type_definition(
        self, node: Node, code: str, file_path: str, result: Dict[str, Any]
    ):
        """
        处理类型定义

        Args:
            node: AST节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
        """
        type_name = None
        kind = None
        members = []

        if node.type == "struct_specifier":
            kind = "struct"
            # 获取struct名
            name_node = node.child_by_field_name("name")
            if name_node:
                type_name = self._get_node_text(name_node, code)
        elif node.type == "union_specifier":
            kind = "union"
            name_node = node.child_by_field_name("name")
            if name_node:
                type_name = self._get_node_text(name_node, code)
        elif node.type == "enum_specifier":
            kind = "enum"
            name_node = node.child_by_field_name("name")
            if name_node:
                type_name = self._get_node_text(name_node, code)
        elif node.type == "type_definition":
            kind = "typedef"
            # typedef的别名在最后一个identifier
            identifiers = [
                child for child in node.children if child.type == "type_identifier"
            ]
            if identifiers:
                type_name = self._get_node_text(identifiers[-1], code)

        if not type_name:
            return

        # 提取成员（对于struct/union）
        if kind in ["struct", "union"]:
            body_node = node.child_by_field_name("body")
            if body_node:
                members = self._extract_struct_members(body_node, code)

        # 获取定义文本
        definition = self._get_node_text(node, code)
        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        type_info = TypeInfo(
            type_name=type_name,
            kind=kind,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            definition=definition,
            members=members,
        )
        result["type_infos"].append(type_info)

    def _handle_declaration(
        self, node: Node, code: str, file_path: str, result: Dict[str, Any], scope: str
    ):
        """
        处理变量声明

        Args:
            node: AST节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
            scope: 当前作用域
        """
        # 提取变量名和类型
        decls = self._extract_declarators(node, code)
        for var_name, type_name in decls:
            line = node.start_point[0] + 1

            # 创建符号信息
            symbol = SymbolInfo(
                name=var_name,
                kind="variable",
                file_path=file_path,
                line_start=line,
                line_end=line,
                type_name=type_name,
                scope=scope,
                is_external=False,
            )
            result["symbols"].append(symbol)

            # 创建数据流节点（定义）
            data_flow_node = DataFlowNode(
                var_name=var_name,
                file_path=file_path,
                line=line,
                node_type="def",
                scope=scope,
                value_source="declaration",
            )
            result["data_flow_nodes"].append(data_flow_node)

        # 检查声明中是否包含内存分配调用（如 char *p = malloc(100)）
        self._check_init_declarator_for_allocation(node, code, file_path, result, scope)

        # 检查是否是C++流对象构造函数声明（如 std::ifstream ifs(path)）
        # 这需要识别为调用关系
        type_node = node.child_by_field_name("type")
        if type_node:
            type_text = self._get_node_text(type_node, code)
            # 检查是否是std::ifstream/std::ofstream/std::fstream
            if type_text in [
                "std::ifstream",
                "std::ofstream",
                "std::fstream",
                "ifstream",
                "ofstream",
                "fstream",
            ]:
                # 获取变量名和参数
                declarator_node = node.child_by_field_name("declarator")
                if declarator_node:
                    # 获取变量名
                    var_name = None
                    for child in declarator_node.children:
                        if child.type == "identifier":
                            var_name = self._get_node_text(child, code)
                            break

                    if var_name:
                        line = node.start_point[0] + 1
                        # 创建调用关系（将构造函数声明视为调用）
                        call_relation = CallRelation(
                            caller_name=scope if scope != "global" else "unknown",
                            caller_file=file_path,
                            caller_line=line,
                            callee_name=type_text.split("::")[-1]
                            if "::" in type_text
                            else type_text,  # 提取基本名称
                            callee_file=None,
                            callee_line=None,
                            call_type="constructor",
                        )
                        result["call_relations"].append(call_relation)

    def _handle_call_expression(
        self, node: Node, code: str, file_path: str, result: Dict[str, Any], scope: str
    ):
        """
        处理函数调用

        Args:
            node: AST节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
            scope: 当前作用域
        """
        # 获取被调用函数名
        callee_name = self._get_call_target(node, code)
        if not callee_name:
            return

        line = node.start_point[0] + 1

        # 创建调用关系
        call_relation = CallRelation(
            caller_name=scope if scope != "global" else "unknown",
            caller_file=file_path,
            caller_line=line,
            callee_name=callee_name,
            callee_file=None,  # 外部函数，文件未知
            callee_line=None,
            call_type="direct",
        )
        result["call_relations"].append(call_relation)

        # 处理free调用
        if callee_name == "free":
            args_node = node.child_by_field_name("arguments")
            if args_node:
                # 获取free的参数（变量名）
                for child in args_node.children:
                    if (
                        child.type == "identifier"
                        or child.type == "expression_statement"
                    ):
                        var_name = self._get_node_text(child, code)
                        pointer_state = PointerStateRecord(
                            var_name=var_name,
                            file_path=file_path,
                            line=line,
                            state="FREED",
                            scope=scope,
                            allocator=None,
                            deallocator="free",
                        )
                        result["pointer_states"].append(pointer_state)
                        break

        # 提取参数中的变量使用
        args_node = node.child_by_field_name("arguments")
        if args_node:
            self._extract_call_arguments(
                args_node, code, file_path, result, scope, line
            )

    def _handle_assignment(
        self, node: Node, code: str, file_path: str, result: Dict[str, Any], scope: str
    ):
        """
        处理赋值表达式

        Args:
            node: AST节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
            scope: 当前作用域
        """
        # 获取左侧变量名
        left_node = node.child_by_field_name("left")
        if not left_node:
            return

        var_name = self._get_node_text(left_node, code)
        line = node.start_point[0] + 1

        # 检查是否为内存分配
        right_node = node.child_by_field_name("right")
        if right_node and right_node.type == "call_expression":
            call_name = self._get_call_target(right_node, code)
            if call_name in ["malloc", "calloc", "realloc"]:
                # 创建指针状态记录
                pointer_state = PointerStateRecord(
                    var_name=var_name,
                    file_path=file_path,
                    line=line,
                    state="ALLOCATED",
                    scope=scope,
                    allocator=call_name,
                    deallocator=None,
                )
                result["pointer_states"].append(pointer_state)

                # 创建数据流节点（定义）
                data_flow_node = DataFlowNode(
                    var_name=var_name,
                    file_path=file_path,
                    line=line,
                    node_type="def",
                    scope=scope,
                    value_source=call_name,
                )
                result["data_flow_nodes"].append(data_flow_node)
            else:
                # 普通赋值，创建数据流节点（定义）
                data_flow_node = DataFlowNode(
                    var_name=var_name,
                    file_path=file_path,
                    line=line,
                    node_type="def",
                    scope=scope,
                    value_source="assignment",
                )
                result["data_flow_nodes"].append(data_flow_node)

        # 检查是否为NULL赋值
        right_text = self._get_node_text(right_node, code) if right_node else ""
        if right_text in ["NULL", "nullptr", "0"]:
            pointer_state = PointerStateRecord(
                var_name=var_name,
                file_path=file_path,
                line=line,
                state="NULLIFIED",
                scope=scope,
                allocator=None,
                deallocator=None,
            )
            result["pointer_states"].append(pointer_state)

    def _handle_memory_operation(
        self, node: Node, code: str, file_path: str, result: Dict[str, Any], scope: str
    ):
        """
        处理内存操作（malloc、free等）

        Args:
            node: AST节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
            scope: 当前作用域
        """
        # 这个方法主要用于处理独立的内存操作调用
        # 实际的malloc/free通常在赋值表达式中处理
        pass

    def _handle_if_statement(
        self, node: Node, code: str, file_path: str, result: Dict[str, Any], scope: str
    ):
        """
        处理if语句，提取条件表达式中的变量使用，并记录consequence块内的受保护调用

        Args:
            node: AST节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
            scope: 当前作用域
        """
        # 获取条件表达式（parenthesized_expression）
        condition_node = node.child_by_field_name("condition")
        if not condition_node:
            return

        line = node.start_point[0] + 1

        # 递归提取条件表达式中的所有标识符
        self._extract_identifiers_from_condition(
            condition_node, code, file_path, result, scope, line
        )

        # 提取consequence块内的调用，标记为condition_protected
        consequence_node = node.child_by_field_name("consequence")
        if consequence_node:
            self._extract_protected_calls(
                consequence_node, code, file_path, result, scope
            )

    def _handle_loop_statement(
        self, node: Node, code: str, file_path: str, result: Dict[str, Any], scope: str
    ):
        """
        处理while/for循环，提取条件表达式中的变量使用，并记录body块内的受保护调用

        Args:
            node: AST节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
            scope: 当前作用域
        """
        # 获取条件表达式
        condition_node = node.child_by_field_name("condition")
        if not condition_node:
            return

        line = node.start_point[0] + 1

        # 递归提取条件表达式中的所有标识符
        self._extract_identifiers_from_condition(
            condition_node, code, file_path, result, scope, line
        )

        # 提取body块内的调用，标记为condition_protected
        body_node = node.child_by_field_name("body")
        if body_node:
            self._extract_protected_calls(body_node, code, file_path, result, scope)

    def _handle_return_statement(
        self, node: Node, code: str, file_path: str, result: Dict[str, Any], scope: str
    ):
        """
        处理return语句，检测所有权转移

        检测模式：
        - return malloc_ptr;  // 函数返回分配的内存，所有权转移给调用者
        - return ptr;         // 返回指针变量

        Args:
            node: AST节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
            scope: 当前作用域
        """
        line = node.start_point[0] + 1

        # 查找return语句中的标识符
        for child in node.children:
            if child.type == "identifier":
                var_name = self._get_node_text(child, code)
                # 创建ownership_transfer类型的数据流节点
                data_flow_node = DataFlowNode(
                    var_name=var_name,
                    file_path=file_path,
                    line=line,
                    node_type="use",
                    scope=scope,
                    value_source="return",
                    use_type="ownership_transfer",
                )
                result["data_flow_nodes"].append(data_flow_node)
            elif child.type == "call_expression":
                # return malloc(...); 直接返回分配结果
                call_name = self._get_call_target(child, code)
                if call_name in ["malloc", "calloc", "realloc"]:
                    # 返回分配结果，所有权转移
                    data_flow_node = DataFlowNode(
                        var_name=f"__return_{call_name}",
                        file_path=file_path,
                        line=line,
                        node_type="use",
                        scope=scope,
                        value_source="return",
                        use_type="ownership_transfer",
                    )
                    result["data_flow_nodes"].append(data_flow_node)

    def _extract_identifiers_from_condition(
        self,
        node: Node,
        code: str,
        file_path: str,
        result: Dict[str, Any],
        scope: str,
        line: int,
    ):
        """
        递归提取条件表达式中的所有标识符（变量使用），并检测NULL检查模式

        检测的NULL检查模式：
        - if (ptr != NULL) / if (ptr != nullptr)
        - if (ptr == NULL) / if (ptr == nullptr)
        - if (ptr) / if (!ptr)
        - if (ptr != NULL && ...) / if (ptr == NULL || ...)

        Args:
            node: AST节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
            scope: 当前作用域
            line: 行号
        """
        if node is None:
            return

        # 检测NULL检查模式：在二元表达式中检测 ptr == NULL / ptr != NULL
        if node.type == "binary_expression":
            self._detect_null_check_in_binary(
                node, code, file_path, result, scope, line
            )
        # 检测一元取反模式：!ptr
        elif node.type == "unary_expression":
            op_node = node.child_by_field_name("operator")
            if op_node and self._get_node_text(op_node, code) == "!":
                arg_node = node.child_by_field_name("argument")
                if arg_node and arg_node.type == "identifier":
                    var_name = self._get_node_text(arg_node, code)
                    self._add_null_check_node(var_name, file_path, line, scope, result)
        # 检测单独标识符作为条件：if (ptr)
        # 注意：只有当标识符直接作为整个条件时才是NULL检查
        # 例如 if (ptr) 是NULL检查，但 if (idx >= 0) 中的 idx 不是NULL检查
        elif node.type == "identifier":
            var_name = self._get_node_text(node, code)
            # 排除常见的非变量标识符
            if var_name not in [
                "NULL",
                "nullptr",
                "true",
                "false",
                "size_t",
                "int",
                "char",
                "void",
                "long",
                "short",
                "float",
                "double",
                "unsigned",
                "signed",
            ]:
                # 检查父节点类型，判断是否是真正的NULL检查
                # 只有当标识符直接作为条件（parenthesized_expression或condition_clause的直接子节点）时
                # 才是NULL检查
                parent = node.parent
                if parent and parent.type in [
                    "parenthesized_expression",
                    "condition_clause",
                ]:
                    # 检查父节点的父节点是否是if/while的条件
                    grandparent = parent.parent
                    if grandparent and grandparent.type in [
                        "if_statement",
                        "while_statement",
                    ]:
                        # 标识符直接作为条件，是NULL检查
                        data_flow_node = DataFlowNode(
                            var_name=var_name,
                            file_path=file_path,
                            line=line,
                            node_type="use",
                            scope=scope,
                            value_source="condition",
                            use_type="null_check",
                        )
                        result["data_flow_nodes"].append(data_flow_node)
                # 其他情况（如 idx >= 0 中的 idx）不标记为null_check
                # 避免误报
            return

        # 递归处理子节点
        for child in node.children:
            self._extract_identifiers_from_condition(
                child, code, file_path, result, scope, line
            )

    def _detect_null_check_in_binary(
        self,
        node: Node,
        code: str,
        file_path: str,
        result: Dict[str, Any],
        scope: str,
        line: int,
    ):
        """检测二元表达式中的NULL检查和值检查模式

        NULL检查：ptr == NULL, ptr != NULL
        值检查：fd >= 0, fd > -1, fd != -1, fd < 0 等
        """
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        op_node = node.child_by_field_name("operator")

        if not left or not right or not op_node:
            return

        op = self._get_node_text(op_node, code)
        left_text = self._get_node_text(left, code).strip()
        right_text = self._get_node_text(right, code).strip()

        # 检测 ptr == NULL / ptr != NULL
        null_literals = {"NULL", "nullptr", "0"}
        if op in ("==", "!="):
            if right_text in null_literals and left.type == "identifier":
                var_name = left_text
                self._add_null_check_node(var_name, file_path, line, scope, result)
            elif left_text in null_literals and right.type == "identifier":
                var_name = right_text
                self._add_null_check_node(var_name, file_path, line, scope, result)

        # 检测值检查：var >= 0, var > -1, var != -1, var < 0 等
        # 这些是IO返回值/错误码的有效性检查
        value_check_ops = {">=", "<=", "!=", "==", "<", ">"}
        value_check_constants = {"0", "-1", "1", "EOF"}
        if op in value_check_ops:
            if right_text in value_check_constants and left.type == "identifier":
                var_name = left_text
                self._add_value_check_node(var_name, file_path, line, scope, result)
            elif left_text in value_check_constants and right.type == "identifier":
                var_name = right_text
                self._add_value_check_node(var_name, file_path, line, scope, result)

    def _add_null_check_node(
        self,
        var_name: str,
        file_path: str,
        line: int,
        scope: str,
        result: Dict[str, Any],
    ):
        """添加一个null_check类型的数据流节点"""
        data_flow_node = DataFlowNode(
            var_name=var_name,
            file_path=file_path,
            line=line,
            node_type="use",
            scope=scope,
            value_source="condition",
            use_type="null_check",
        )
        result["data_flow_nodes"].append(data_flow_node)

    def _add_value_check_node(
        self,
        var_name: str,
        file_path: str,
        line: int,
        scope: str,
        result: Dict[str, Any],
    ):
        """添加一个value_check类型的数据流节点（如 fd >= 0, fd != -1 等）"""
        data_flow_node = DataFlowNode(
            var_name=var_name,
            file_path=file_path,
            line=line,
            node_type="use",
            scope=scope,
            value_source="condition",
            use_type="value_check",
        )
        result["data_flow_nodes"].append(data_flow_node)

    def _extract_protected_calls(
        self,
        block_node: Node,
        code: str,
        file_path: str,
        result: Dict[str, Any],
        scope: str,
    ):
        """提取if/while/for的consequence/body块内的调用，标记为condition_protected

        这些调用受条件保护，在误报过滤时可以排除。
        记录方式：为每个调用创建一个data_flow_node，use_type="condition_protected"。
        """

        def _find_calls(node: Node, calls: list):
            if node.type == "call_expression":
                func_node = node.child_by_field_name("function")
                if func_node:
                    func_name = self._get_node_text(func_node, code)
                    call_line = node.start_point[0] + 1
                    calls.append((func_name, call_line))
            for child in node.children:
                _find_calls(child, calls)

        calls = []
        _find_calls(block_node, calls)
        for func_name, call_line in calls:
            data_flow_node = DataFlowNode(
                var_name=func_name,
                file_path=file_path,
                line=call_line,
                node_type="use",
                scope=scope,
                value_source="condition_protected",
                use_type="condition_protected",
            )
            result["data_flow_nodes"].append(data_flow_node)

    # ============================================================================
    # 正则表达式回退方案
    # ============================================================================

    def _extract_with_regex(self, code: str, file_path: str, result: Dict[str, Any]):
        """
        使用正则表达式提取数据（tree-sitter不可用时的回退方案）

        Args:
            code: 源代码
            file_path: 文件路径
            result: 结果字典
        """
        lines = code.split("\n")

        # 提取函数定义
        func_pattern = re.compile(
            r"^(?:static\s+)?(?:inline\s+)?(?:const\s+)?(?:struct\s+)?(?:enum\s+)?(?:union\s+)?(?:\w+\s+\*?\s*)?(\w+)\s*\([^)]*\)\s*\{"
        )
        for i, line in enumerate(lines, 1):
            match = func_pattern.match(line.strip())
            if match:
                func_name = match.group(1)
                # 简单估计函数结束行（查找下一个函数或文件末尾）
                line_end = i
                for j in range(i, len(lines)):
                    if func_pattern.match(lines[j].strip()) and j > i:
                        line_end = j
                        break
                line_end = min(line_end, len(lines))

                symbol = SymbolInfo(
                    name=func_name,
                    kind="function",
                    file_path=file_path,
                    line_start=i,
                    line_end=line_end,
                    signature=line.strip(),
                    scope="global",
                    is_external=False,
                )
                result["symbols"].append(symbol)

        # 提取函数调用
        call_pattern = re.compile(r"(\w+)\s*\([^)]*\)")
        for i, line in enumerate(lines, 1):
            # 跳过函数定义行
            if func_pattern.match(line.strip()):
                continue
            for match in call_pattern.finditer(line):
                callee_name = match.group(1)
                # 排除常见关键字
                if callee_name in [
                    "if",
                    "while",
                    "for",
                    "switch",
                    "return",
                    "sizeof",
                    "typeof",
                ]:
                    continue

                call_relation = CallRelation(
                    caller_name="unknown",
                    caller_file=file_path,
                    caller_line=i,
                    callee_name=callee_name,
                    callee_file=None,
                    callee_line=None,
                    call_type="direct",
                )
                result["call_relations"].append(call_relation)

        # 提取malloc/free调用
        malloc_pattern = re.compile(
            r"(\w+)\s*=\s*(?:\([^)]*\))?\s*(malloc|calloc|realloc)\s*\("
        )
        free_pattern = re.compile(r"free\s*\(\s*(\w+)\s*\)")
        null_pattern = re.compile(r"(\w+)\s*=\s*(NULL|nullptr|0)")

        for i, line in enumerate(lines, 1):
            # malloc/calloc/realloc
            match = malloc_pattern.search(line)
            if match:
                var_name = match.group(1)
                allocator = match.group(2)
                pointer_state = PointerStateRecord(
                    var_name=var_name,
                    file_path=file_path,
                    line=i,
                    state="ALLOCATED",
                    scope="unknown",
                    allocator=allocator,
                    deallocator=None,
                )
                result["pointer_states"].append(pointer_state)

            # free
            match = free_pattern.search(line)
            if match:
                var_name = match.group(1)
                pointer_state = PointerStateRecord(
                    var_name=var_name,
                    file_path=file_path,
                    line=i,
                    state="FREED",
                    scope="unknown",
                    allocator=None,
                    deallocator="free",
                )
                result["pointer_states"].append(pointer_state)

            # NULL赋值
            match = null_pattern.search(line)
            if match:
                var_name = match.group(1)
                pointer_state = PointerStateRecord(
                    var_name=var_name,
                    file_path=file_path,
                    line=i,
                    state="NULLIFIED",
                    scope="unknown",
                    allocator=None,
                    deallocator=None,
                )
                result["pointer_states"].append(pointer_state)

        # 提取struct/union/enum定义
        struct_pattern = re.compile(r"(struct|union|enum)\s+(\w+)\s*\{")
        typedef_pattern = re.compile(r"typedef\s+.*\s+(\w+)\s*;")

        for i, line in enumerate(lines, 1):
            match = struct_pattern.search(line)
            if match:
                kind = match.group(1)
                type_name = match.group(2)
                # 简单估计结束行
                line_end = i
                brace_count = line.count("{") - line.count("}")
                for j in range(i, len(lines)):
                    brace_count += lines[j].count("{") - lines[j].count("}")
                    if brace_count <= 0:
                        line_end = j + 1
                        break

                type_info = TypeInfo(
                    type_name=type_name,
                    kind=kind,
                    file_path=file_path,
                    line_start=i,
                    line_end=line_end,
                    definition="",
                    members=[],
                )
                result["type_infos"].append(type_info)

            match = typedef_pattern.search(line)
            if match:
                type_name = match.group(1)
                type_info = TypeInfo(
                    type_name=type_name,
                    kind="typedef",
                    file_path=file_path,
                    line_start=i,
                    line_end=i,
                    definition=line.strip(),
                    members=[],
                )
                result["type_infos"].append(type_info)

    # ============================================================================
    # 辅助方法
    # ============================================================================

    def _get_node_text(self, node: Node, code: str) -> str:
        """
        获取节点文本

        Args:
            node: AST节点
            code: 源代码

        Returns:
            节点文本
        """
        if node is None:
            return ""
        start_byte = node.start_byte
        end_byte = node.end_byte
        # 使用字节索引，然后解码
        code_bytes = bytes(code, "utf-8")
        return code_bytes[start_byte:end_byte].decode("utf-8", errors="replace")

    def _get_function_name(self, node: Node, code: str) -> Optional[str]:
        """
        获取函数名

        Args:
            node: 函数定义节点
            code: 源代码

        Returns:
            函数名
        """
        # 函数名通常在declarator中
        declarator = node.child_by_field_name("declarator")
        if declarator:
            # 处理指针函数（如 int (*func)(int)）
            if declarator.type == "pointer_declarator":
                declarator = declarator.child_by_field_name("declarator")

            if declarator and declarator.type == "function_declarator":
                # 函数名在第一个identifier子节点
                for child in declarator.children:
                    if child.type == "identifier":
                        return self._get_node_text(child, code)
                    elif child.type == "parenthesized_declarator":
                        # 处理复杂声明
                        for subchild in child.children:
                            if subchild.type == "pointer_declarator":
                                for subsubchild in subchild.children:
                                    if subsubchild.type == "identifier":
                                        return self._get_node_text(subsubchild, code)
        return None

    def _extract_function_params(self, node: Node, code: str) -> List[str]:
        """
        提取函数参数名

        Args:
            node: 函数定义节点
            code: 源代码

        Returns:
            参数名列表
        """
        params = []
        declarator = node.child_by_field_name("declarator")
        if declarator and declarator.type == "function_declarator":
            params_node = declarator.child_by_field_name("parameters")
            if params_node:
                for child in params_node.children:
                    if child.type == "parameter_declaration":
                        # 提取参数名
                        param_declarator = child.child_by_field_name("declarator")
                        if param_declarator:
                            if param_declarator.type == "identifier":
                                params.append(
                                    self._get_node_text(param_declarator, code)
                                )
                            elif param_declarator.type == "pointer_declarator":
                                # 指针参数
                                for subchild in param_declarator.children:
                                    if subchild.type == "identifier":
                                        params.append(
                                            self._get_node_text(subchild, code)
                                        )
        return params

    def _extract_declarators(self, node: Node, code: str) -> List[Tuple[str, str]]:
        """
        提取声明中的变量名和类型

        Args:
            node: 声明节点
            code: 源代码

        Returns:
            (变量名, 类型名)列表
        """
        decls = []
        type_node = node.child_by_field_name("type")
        if not type_node:
            return decls

        type_name = self._get_node_text(type_node, code)

        # 处理声明符
        for child in node.children:
            if child.type in ["init_declarator", "declarator"]:
                if child.type == "init_declarator":
                    declarator = child.child_by_field_name("declarator")
                else:
                    declarator = child

                if declarator:
                    if declarator.type == "identifier":
                        decls.append((self._get_node_text(declarator, code), type_name))
                    elif declarator.type == "pointer_declarator":
                        for subchild in declarator.children:
                            if subchild.type == "identifier":
                                decls.append(
                                    (
                                        self._get_node_text(subchild, code),
                                        type_name + "*",
                                    )
                                )
                    elif declarator.type == "array_declarator":
                        for subchild in declarator.children:
                            if subchild.type == "identifier":
                                decls.append(
                                    (
                                        self._get_node_text(subchild, code),
                                        type_name + "[]",
                                    )
                                )

        return decls

    def _get_call_target(self, node: Node, code: str) -> Optional[str]:
        """
        获取函数调用的目标函数名

        Args:
            node: 调用表达式节点
            code: 源代码

        Returns:
            目标函数名
        """
        func_node = node.child_by_field_name("function")
        if func_node:
            if func_node.type == "identifier":
                return self._get_node_text(func_node, code)
            elif func_node.type == "field_expression":
                # 成员函数调用（如 obj.method()）
                field_node = func_node.child_by_field_name("field")
                if field_node:
                    return self._get_node_text(field_node, code)
        return None

    def _extract_call_arguments(
        self,
        args_node: Node,
        code: str,
        file_path: str,
        result: Dict[str, Any],
        scope: str,
        line: int,
    ):
        """
        提取函数调用参数中的变量使用

        Args:
            args_node: 参数列表节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
            scope: 当前作用域
            line: 调用行号
        """
        for child in args_node.children:
            if child.type == "identifier":
                var_name = self._get_node_text(child, code)
                # 创建数据流节点（使用）
                data_flow_node = DataFlowNode(
                    var_name=var_name,
                    file_path=file_path,
                    line=line,
                    node_type="use",
                    scope=scope,
                    value_source="call_argument",
                )
                result["data_flow_nodes"].append(data_flow_node)

    def _extract_struct_members(
        self, body_node: Node, code: str
    ) -> List[Dict[str, Any]]:
        """
        提取struct/union成员

        Args:
            body_node: struct体节点
            code: 源代码

        Returns:
            成员列表
        """
        members = []
        for child in body_node.children:
            if child.type == "field_declaration":
                # 提取成员名和类型
                type_node = child.child_by_field_name("type")
                declarator_node = child.child_by_field_name("declarator")

                if type_node and declarator_node:
                    type_name = self._get_node_text(type_node, code)
                    member_name = self._get_node_text(declarator_node, code)
                    members.append(
                        {
                            "name": member_name,
                            "type": type_name,
                        }
                    )
        return members

    # ============================================================================
    # 数据保存
    # ============================================================================

    def _save_to_database(self, file_path: str, result: Dict[str, Any]):
        """
        保存分析结果到数据库

        Args:
            file_path: 文件路径
            result: 分析结果字典
        """
        # 批量保存符号
        if result["symbols"]:
            self.database.add_symbols_batch(result["symbols"])

        # 批量保存调用关系
        if result["call_relations"]:
            self.database.add_call_relations_batch(result["call_relations"])

        # 批量保存数据流节点
        if result["data_flow_nodes"]:
            self.database.add_data_flow_nodes_batch(result["data_flow_nodes"])

        # 批量保存指针状态
        if result["pointer_states"]:
            self.database.add_pointer_states_batch(result["pointer_states"])

        # 批量保存类型信息
        if result["type_infos"]:
            self.database.add_type_infos_batch(result["type_infos"])

        PrettyOutput.auto_print(
            f"[DataCollector] 保存数据: {len(result['symbols'])}个符号, "
            f"{len(result['call_relations'])}个调用关系, "
            f"{len(result['data_flow_nodes'])}个数据流节点"
        )

    def _check_init_declarator_for_allocation(
        self, node: Node, code: str, file_path: str, result: Dict[str, Any], scope: str
    ):
        """
        检查声明中是否包含内存分配调用（如 char *p = malloc(100)）

        Args:
            node: AST节点
            code: 源代码
            file_path: 文件路径
            result: 结果字典
            scope: 当前作用域
        """
        # 遍历声明节点的子节点，查找init_declarator
        for child in node.children:
            if child.type == "init_declarator":
                # 获取声明变量名
                declarator = child.child_by_field_name("declarator")
                if not declarator:
                    continue

                # 处理指针声明符（如 char *p）
                var_name = None
                if declarator.type == "pointer_declarator":
                    for subchild in declarator.children:
                        if subchild.type == "identifier":
                            var_name = self._get_node_text(subchild, code)
                            break
                elif declarator.type == "identifier":
                    var_name = self._get_node_text(declarator, code)

                if not var_name:
                    continue

                # 检查初始化表达式是否为函数调用
                init_value = child.child_by_field_name("value")
                if init_value and init_value.type == "call_expression":
                    call_name = self._get_call_target(init_value, code)
                    line = node.start_point[0] + 1

                    # 检查是否为内存分配函数
                    if call_name in ["malloc", "calloc", "realloc", "new"]:
                        pointer_state = PointerStateRecord(
                            var_name=var_name,
                            file_path=file_path,
                            line=line,
                            state="ALLOCATED",
                            scope=scope,
                            allocator=call_name,
                            deallocator=None,
                        )
                        result["pointer_states"].append(pointer_state)
                    else:
                        # 非内存分配函数调用，记录为UNKNOWN状态
                        pointer_state = PointerStateRecord(
                            var_name=var_name,
                            file_path=file_path,
                            line=line,
                            state="UNKNOWN",
                            scope=scope,
                            allocator=None,
                            deallocator=None,
                        )
                        result["pointer_states"].append(pointer_state)

    # ============================================================================
    # Rust AST处理方法
    # ============================================================================

    def _handle_rust_function_definition(
        self, node, code: str, file_path: str, result: Dict[str, Any]
    ):
        """
        处理Rust函数定义
        """
        func_name = self._get_rust_function_name(node, code)
        if not func_name:
            return

        signature = self._get_node_text(node, code)
        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        # 检查是否是unsafe函数
        is_unsafe = False
        for child in node.children:
            if child.type == "unsafe" or (
                child.type == "identifier"
                and self._get_node_text(child, code) == "unsafe"
            ):
                is_unsafe = True
                break

        symbol = SymbolInfo(
            name=func_name,
            kind="function",
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            signature=signature,
            scope="global",
            is_external=False,
        )
        result["symbols"].append(symbol)

        if is_unsafe:
            unsafe_symbol = SymbolInfo(
                name=f"__unsafe_fn__{func_name}",
                kind="unsafe_block",
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                signature=f"unsafe fn {func_name}",
                scope="global",
                is_external=False,
            )
            result["symbols"].append(unsafe_symbol)

        params = self._extract_rust_function_params(node, code)
        for param in params:
            param_node = DataFlowNode(
                var_name=param,
                file_path=file_path,
                line=line_start,
                node_type="param_in",
                scope=func_name,
                value_source="parameter",
            )
            result["data_flow_nodes"].append(param_node)

    def _handle_rust_struct_definition(
        self, node, code: str, file_path: str, result: Dict[str, Any]
    ):
        """
        处理Rust结构体定义
        """
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        struct_name = self._get_node_text(name_node, code)
        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        members = []
        body_node = node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                if child.type == "field_declaration":
                    field_name_node = child.child_by_field_name("name")
                    field_type_node = child.child_by_field_name("type")
                    if field_name_node and field_type_node:
                        members.append(
                            {
                                "name": self._get_node_text(field_name_node, code),
                                "type": self._get_node_text(field_type_node, code),
                            }
                        )

        type_info = TypeInfo(
            type_name=struct_name,
            kind="struct",
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            definition=self._get_node_text(node, code),
            members=members,
        )
        result["type_infos"].append(type_info)

    def _handle_rust_enum_definition(
        self, node, code: str, file_path: str, result: Dict[str, Any]
    ):
        """
        处理Rust枚举定义
        """
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        enum_name = self._get_node_text(name_node, code)
        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        type_info = TypeInfo(
            type_name=enum_name,
            kind="enum",
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            definition=self._get_node_text(node, code),
            members=[],
        )
        result["type_infos"].append(type_info)

    def _handle_rust_impl_block(
        self, node, code: str, file_path: str, result: Dict[str, Any]
    ):
        """
        处理Rust impl块
        """
        is_unsafe = False
        for child in node.children:
            if child.type == "unsafe" or (
                child.type == "identifier"
                and self._get_node_text(child, code) == "unsafe"
            ):
                is_unsafe = True
                break

        if is_unsafe:
            line_start = node.start_point[0] + 1
            line_end = node.end_point[0] + 1
            type_node = node.child_by_field_name("type")
            type_name = self._get_node_text(type_node, code) if type_node else "unknown"

            unsafe_symbol = SymbolInfo(
                name=f"__unsafe_impl__{type_name}",
                kind="unsafe_block",
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                signature=f"unsafe impl {type_name}",
                scope="global",
                is_external=False,
            )
            result["symbols"].append(unsafe_symbol)

    def _handle_rust_extern_block(
        self, node, code: str, file_path: str, result: Dict[str, Any]
    ):
        """
        处理Rust extern块
        """
        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        abi = "C"
        for child in node.children:
            if child.type == "string_literal":
                abi = self._get_node_text(child, code).strip('"')
                break

        extern_symbol = SymbolInfo(
            name=f"__extern_block__{abi}",
            kind="extern_block",
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            signature=f'extern "{abi}"',
            scope="global",
            is_external=True,
        )
        result["symbols"].append(extern_symbol)

    def _handle_rust_unsafe_block(
        self, node, code: str, file_path: str, result: Dict[str, Any], scope: str
    ):
        """
        处理Rust unsafe块
        """
        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1

        unsafe_symbol = SymbolInfo(
            name=f"__unsafe_block__{line_start}",
            kind="unsafe_block",
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            signature="unsafe { ... }",
            scope=scope,
            is_external=False,
        )
        result["symbols"].append(unsafe_symbol)

    def _handle_rust_let_declaration(
        self, node, code: str, file_path: str, result: Dict[str, Any], scope: str
    ):
        """
        处理Rust let声明
        """
        # tree-sitter-rust中let_declaration的变量名不是"name"字段，
        # 而是identifier子节点（在mutable_specifier之后）
        name_node = node.child_by_field_name("name")
        if not name_node:
            # 回退：查找identifier子节点（跳过let/mutable_specifier）
            for child in node.children:
                if child.type == "identifier":
                    name_node = child
                    break
        if not name_node:
            return

        var_name = self._get_node_text(name_node, code)
        line = node.start_point[0] + 1

        type_node = node.child_by_field_name("type")
        type_name = self._get_node_text(type_node, code) if type_node else None

        symbol = SymbolInfo(
            name=var_name,
            kind="variable",
            file_path=file_path,
            line_start=line,
            line_end=line,
            type_name=type_name,
            scope=scope,
            is_external=False,
        )
        result["symbols"].append(symbol)

        data_flow_node = DataFlowNode(
            var_name=var_name,
            file_path=file_path,
            line=line,
            node_type="def",
            scope=scope,
            value_source="let_binding",
        )
        result["data_flow_nodes"].append(data_flow_node)

        if type_name and ("*mut" in type_name or "*const" in type_name):
            pointer_state = PointerStateRecord(
                var_name=var_name,
                file_path=file_path,
                line=line,
                state="RAW_POINTER",
                scope=scope,
                allocator=None,
                deallocator=None,
            )
            result["pointer_states"].append(pointer_state)

        # 检测type_cast_expression中的pointer_type（如 &mut num as *mut i32）
        if not type_name or ("*mut" not in type_name and "*const" not in type_name):
            value_node = node.child_by_field_name("value")
            if value_node and value_node.type == "type_cast_expression":
                # 遍历type_cast_expression子节点查找pointer_type
                for child in value_node.children:
                    if child.type == "pointer_type":
                        pointer_state = PointerStateRecord(
                            var_name=var_name,
                            file_path=file_path,
                            line=line,
                            state="RAW_POINTER",
                            scope=scope,
                            allocator=None,
                            deallocator=None,
                        )
                        result["pointer_states"].append(pointer_state)
                        break

        value_node = node.child_by_field_name("value")
        if value_node and value_node.type == "call_expression":
            call_name = self._get_rust_call_target(value_node, code)
            if call_name:
                call_relation = CallRelation(
                    caller_name=scope if scope != "global" else "unknown",
                    caller_file=file_path,
                    caller_line=line,
                    callee_name=call_name,
                    callee_file=None,
                    callee_line=None,
                    call_type="direct",
                )
                result["call_relations"].append(call_relation)

    def _handle_rust_call_expression(
        self, node, code: str, file_path: str, result: Dict[str, Any], scope: str
    ):
        """
        处理Rust函数调用
        """
        callee_name = self._get_rust_call_target(node, code)
        if not callee_name:
            return

        line = node.start_point[0] + 1

        call_relation = CallRelation(
            caller_name=scope if scope != "global" else "unknown",
            caller_file=file_path,
            caller_line=line,
            callee_name=callee_name,
            callee_file=None,
            callee_line=None,
            call_type="direct",
        )
        result["call_relations"].append(call_relation)

        args_node = node.child_by_field_name("arguments")
        if args_node:
            self._extract_rust_call_arguments(
                args_node, code, file_path, result, scope, line
            )

    def _handle_rust_method_call(
        self, node, code: str, file_path: str, result: Dict[str, Any], scope: str
    ):
        """
        处理Rust方法调用
        """
        method_node = node.child_by_field_name("method")
        if not method_node:
            return

        method_name = self._get_node_text(method_node, code)
        line = node.start_point[0] + 1

        object_node = node.child_by_field_name("object")
        object_name = self._get_node_text(object_node, code) if object_node else None

        call_relation = CallRelation(
            caller_name=scope if scope != "global" else "unknown",
            caller_file=file_path,
            caller_line=line,
            callee_name=method_name,
            callee_file=None,
            callee_line=None,
            call_type="method",
        )
        result["call_relations"].append(call_relation)

        if method_name in ["unwrap", "expect"]:
            data_flow_node = DataFlowNode(
                var_name=object_name if object_name else "__unknown__",
                file_path=file_path,
                line=line,
                node_type="use",
                scope=scope,
                value_source="method_call",
                use_type="unwrap",
            )
            result["data_flow_nodes"].append(data_flow_node)

    def _handle_rust_macro_invocation(
        self, node, code: str, file_path: str, result: Dict[str, Any], scope: str
    ):
        """
        处理Rust宏调用
        """
        # tree-sitter-rust中macro_invocation的宏名不是"name"字段，
        # 而是第一个identifier子节点
        macro_name_node = node.child_by_field_name("name")
        if not macro_name_node:
            # 回退：查找第一个identifier子节点
            for child in node.children:
                if child.type == "identifier":
                    macro_name_node = child
                    break
        if not macro_name_node:
            return

        macro_name = self._get_node_text(macro_name_node, code)
        line = node.start_point[0] + 1

        call_relation = CallRelation(
            caller_name=scope if scope != "global" else "unknown",
            caller_file=file_path,
            caller_line=line,
            callee_name=f"{macro_name}!",
            callee_file=None,
            callee_line=None,
            call_type="macro",
        )
        result["call_relations"].append(call_relation)

        if macro_name in ["panic", "unreachable"]:
            data_flow_node = DataFlowNode(
                var_name=macro_name,
                file_path=file_path,
                line=line,
                node_type="use",
                scope=scope,
                value_source="macro",
                use_type="panic",
            )
            result["data_flow_nodes"].append(data_flow_node)

    # ============================================================================
    # Rust辅助方法
    # ============================================================================

    def _get_rust_function_name(self, node, code: str) -> Optional[str]:
        """
        获取Rust函数名
        """
        name_node = node.child_by_field_name("name")
        if name_node:
            return self._get_node_text(name_node, code)
        return None

    def _extract_rust_function_params(self, node, code: str) -> List[str]:
        """
        提取Rust函数参数名
        """
        params = []
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type == "parameter":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        params.append(self._get_node_text(name_node, code))
                elif child.type == "self_parameter":
                    params.append("self")
        return params

    def _get_rust_call_target(self, node, code: str) -> Optional[str]:
        """
        获取Rust函数调用的目标函数名
        """
        func_node = node.child_by_field_name("function")
        if func_node:
            if func_node.type == "identifier":
                return self._get_node_text(func_node, code)
            elif func_node.type == "scoped_identifier":
                return self._get_node_text(func_node, code)
            elif func_node.type == "field_expression":
                field_node = func_node.child_by_field_name("field")
                if field_node:
                    return self._get_node_text(field_node, code)
        return None

    def _extract_rust_call_arguments(
        self,
        args_node,
        code: str,
        file_path: str,
        result: Dict[str, Any],
        scope: str,
        line: int,
    ):
        """
        提取Rust函数调用参数中的变量使用
        """
        for child in args_node.children:
            if child.type == "identifier":
                var_name = self._get_node_text(child, code)
                data_flow_node = DataFlowNode(
                    var_name=var_name,
                    file_path=file_path,
                    line=line,
                    node_type="use",
                    scope=scope,
                    value_source="call_argument",
                )
                result["data_flow_nodes"].append(data_flow_node)
