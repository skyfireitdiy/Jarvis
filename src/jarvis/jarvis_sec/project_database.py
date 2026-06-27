# -*- coding: utf-8 -*-
"""
项目级数据库管理器 - 支持跨文件分析的持久化存储

核心功能：
1. 符号表存储（函数、变量、类型定义）
2. 调用关系图存储
3. 数据流图存储（Def-Use链）
4. 指针状态追踪
5. 类型信息存储
6. 文件元数据管理
7. 分析结果缓存

数据库Schema设计：
- files: 文件元数据（路径、哈希、修改时间）
- symbols: 符号表（函数、变量、类型）
- call_graph: 调用关系图
- data_flow: 数据流图（Def-Use链）
- pointer_states: 指针状态追踪
- type_info: 类型信息
- analysis_cache: 分析结果缓存
"""

import sqlite3
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from contextlib import contextmanager

from jarvis.jarvis_utils.output import PrettyOutput


# ============================================================================
# 数据结构定义
# ============================================================================


@dataclass
class FileInfo:
    """文件信息"""

    path: str
    hash: str  # 文件内容哈希
    last_modified: datetime
    language: str  # c, cpp, rust, etc.
    line_count: int


@dataclass
class SymbolInfo:
    """符号信息"""

    name: str
    kind: str  # function, variable, type, parameter, etc.
    file_path: str
    line_start: int
    line_end: int
    signature: Optional[str] = None  # 函数签名
    type_name: Optional[str] = None  # 变量类型
    scope: Optional[str] = None  # 作用域（函数名或global）
    is_external: bool = False  # 是否为外部符号


@dataclass
class CallRelation:
    """调用关系"""

    caller_name: str
    caller_file: str
    caller_line: int
    callee_name: str
    callee_file: Optional[str] = None  # 外部函数可能无文件
    callee_line: Optional[int] = None
    call_type: str = "direct"  # direct, virtual, function_pointer


@dataclass
class DataFlowNode:
    """数据流节点"""

    var_name: str
    file_path: str
    line: int
    node_type: str  # def, use, param_in, param_out, return
    scope: str  # 作用域（函数名）
    value_source: Optional[str] = None  # 值来源（如malloc、参数等）


@dataclass
class PointerStateRecord:
    """指针状态记录"""

    var_name: str
    file_path: str
    line: int
    state: str  # ALLOCATED, FREED, NULLIFIED, UNKNOWN
    scope: str
    allocator: Optional[str] = None  # 分配函数（malloc、calloc等）
    deallocator: Optional[str] = None  # 释放函数（free等）


@dataclass
class TypeInfo:
    """类型信息"""

    type_name: str
    kind: str  # struct, union, enum, typedef, class
    file_path: str
    line_start: int
    line_end: int
    definition: Optional[str] = None  # 类型定义文本
    members: Optional[List[Dict[str, Any]]] = None  # 成员列表


# ============================================================================
# 数据库管理器
# ============================================================================


class ProjectDatabase:
    """项目级数据库管理器"""

    def __init__(self, project_path: str, db_path: Optional[str] = None):
        """
        初始化数据库管理器

        Args:
            project_path: 项目根目录路径
            db_path: 数据库文件路径（默认为项目根目录下的.jarvis/jsec/analysis.db）
        """
        self.project_path = Path(project_path).resolve()
        self.db_path = (
            Path(db_path)
            if db_path
            else self.project_path / ".jarvis" / "jsec" / "analysis.db"
        )

        # 确保数据库目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 初始化数据库连接
        self._conn: Optional[sqlite3.Connection] = None
        self._init_database()

    def _init_database(self):
        """初始化数据库Schema"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 创建文件元数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    hash TEXT NOT NULL,
                    last_modified TIMESTAMP NOT NULL,
                    language TEXT NOT NULL,
                    line_count INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建符号表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS symbols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_start INTEGER NOT NULL,
                    line_end INTEGER NOT NULL,
                    signature TEXT,
                    type_name TEXT,
                    scope TEXT,
                    is_external BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_path) REFERENCES files(path)
                )
            """)

            # 创建调用关系图
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS call_graph (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    caller_name TEXT NOT NULL,
                    caller_file TEXT NOT NULL,
                    caller_line INTEGER NOT NULL,
                    callee_name TEXT NOT NULL,
                    callee_file TEXT,
                    callee_line INTEGER,
                    call_type TEXT DEFAULT 'direct',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (caller_file) REFERENCES files(path),
                    FOREIGN KEY (callee_file) REFERENCES files(path)
                )
            """)

            # 创建数据流图
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS data_flow (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    var_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    node_type TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    value_source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_path) REFERENCES files(path)
                )
            """)

            # 创建指针状态追踪表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pointer_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    var_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    allocator TEXT,
                    deallocator TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_path) REFERENCES files(path)
                )
            """)

            # 创建类型信息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS type_info (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type_name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_start INTEGER NOT NULL,
                    line_end INTEGER NOT NULL,
                    definition TEXT,
                    members TEXT,  -- JSON格式存储成员列表
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_path) REFERENCES files(path)
                )
            """)

            # 创建分析结果缓存表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analysis_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    analysis_type TEXT NOT NULL,
                    result TEXT NOT NULL,  -- JSON格式存储结果
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_path) REFERENCES files(path),
                    UNIQUE(file_path, analysis_type)
                )
            """)

            # 创建索引优化查询性能
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_call_graph_caller ON call_graph(caller_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_call_graph_callee ON call_graph(callee_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_call_graph_caller_file ON call_graph(caller_file)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_data_flow_var ON data_flow(var_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_data_flow_file ON data_flow(file_path)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_pointer_states_var ON pointer_states(var_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_pointer_states_file ON pointer_states(file_path)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_type_info_name ON type_info(type_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_type_info_file ON type_info(file_path)"
            )

            conn.commit()
            PrettyOutput.auto_print(
                f"[ProjectDatabase] 数据库初始化完成: {self.db_path}"
            )

    @contextmanager
    def _get_connection(self):
        """获取数据库连接（上下文管理器）"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # 使用Row工厂，支持字典式访问
        try:
            yield conn
        finally:
            conn.close()

    # ============================================================================
    # 文件管理
    # ============================================================================

    def add_file(self, file_info: FileInfo) -> int:
        """添加文件记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO files (path, hash, last_modified, language, line_count)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    file_info.path,
                    file_info.hash,
                    file_info.last_modified,
                    file_info.language,
                    file_info.line_count,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """获取文件记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files WHERE path = ?", (file_path,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_files(self) -> List[Dict[str, Any]]:
        """获取所有文件记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files ORDER BY path")
            return [dict(row) for row in cursor.fetchall()]

    def delete_file(self, file_path: str) -> bool:
        """删除文件记录及其关联数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 删除关联数据
            cursor.execute("DELETE FROM symbols WHERE file_path = ?", (file_path,))
            cursor.execute(
                "DELETE FROM call_graph WHERE caller_file = ? OR callee_file = ?",
                (file_path, file_path),
            )
            cursor.execute("DELETE FROM data_flow WHERE file_path = ?", (file_path,))
            cursor.execute(
                "DELETE FROM pointer_states WHERE file_path = ?", (file_path,)
            )
            cursor.execute("DELETE FROM type_info WHERE file_path = ?", (file_path,))
            cursor.execute(
                "DELETE FROM analysis_cache WHERE file_path = ?", (file_path,)
            )
            cursor.execute("DELETE FROM files WHERE path = ?", (file_path,))
            conn.commit()
            return True

    def file_exists(self, file_path: str) -> bool:
        """检查文件是否存在"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM files WHERE path = ?", (file_path,))
            return cursor.fetchone() is not None

    def file_hash_changed(self, file_path: str, new_hash: str) -> bool:
        """检查文件哈希是否变化"""
        file_record = self.get_file(file_path)
        if not file_record:
            return True  # 文件不存在，视为变化
        return file_record["hash"] != new_hash

    # ============================================================================
    # 符号管理
    # ============================================================================

    def add_symbol(self, symbol: SymbolInfo) -> int:
        """添加符号记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO symbols (name, kind, file_path, line_start, line_end, signature, type_name, scope, is_external)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    symbol.name,
                    symbol.kind,
                    symbol.file_path,
                    symbol.line_start,
                    symbol.line_end,
                    symbol.signature,
                    symbol.type_name,
                    symbol.scope,
                    symbol.is_external,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def add_symbols_batch(self, symbols: List[SymbolInfo]) -> int:
        """批量添加符号记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT INTO symbols (name, kind, file_path, line_start, line_end, signature, type_name, scope, is_external)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    (
                        s.name,
                        s.kind,
                        s.file_path,
                        s.line_start,
                        s.line_end,
                        s.signature,
                        s.type_name,
                        s.scope,
                        s.is_external,
                    )
                    for s in symbols
                ],
            )
            conn.commit()
            return len(symbols)

    def get_symbol(
        self, name: str, file_path: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """获取符号记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if file_path:
                cursor.execute(
                    "SELECT * FROM symbols WHERE name = ? AND file_path = ?",
                    (name, file_path),
                )
            else:
                cursor.execute("SELECT * FROM symbols WHERE name = ? LIMIT 1", (name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_symbols_by_file(self, file_path: str) -> List[Dict[str, Any]]:
        """获取文件的所有符号"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM symbols WHERE file_path = ? ORDER BY line_start",
                (file_path,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_symbols_by_kind(self, kind: str) -> List[Dict[str, Any]]:
        """获取指定类型的所有符号"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM symbols WHERE kind = ? ORDER BY name", (kind,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_functions(self) -> List[Dict[str, Any]]:
        """获取所有函数符号"""
        return self.get_symbols_by_kind("function")

    def get_variables(self) -> List[Dict[str, Any]]:
        """获取所有变量符号"""
        return self.get_symbols_by_kind("variable")

    def delete_symbols_by_file(self, file_path: str) -> int:
        """删除文件的所有符号"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM symbols WHERE file_path = ?", (file_path,))
            conn.commit()
            return cursor.rowcount

    # ============================================================================
    # 调用关系管理
    # ============================================================================

    def add_call_relation(self, call: CallRelation) -> int:
        """添加调用关系"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO call_graph (caller_name, caller_file, caller_line, callee_name, callee_file, callee_line, call_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    call.caller_name,
                    call.caller_file,
                    call.caller_line,
                    call.callee_name,
                    call.callee_file,
                    call.callee_line,
                    call.call_type,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def add_call_relations_batch(self, calls: List[CallRelation]) -> int:
        """批量添加调用关系"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT INTO call_graph (caller_name, caller_file, caller_line, callee_name, callee_file, callee_line, call_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    (
                        c.caller_name,
                        c.caller_file,
                        c.caller_line,
                        c.callee_name,
                        c.callee_file,
                        c.callee_line,
                        c.call_type,
                    )
                    for c in calls
                ],
            )
            conn.commit()
            return len(calls)

    def get_callers(self, callee_name: str) -> List[Dict[str, Any]]:
        """获取调用指定函数的所有调用者"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM call_graph WHERE callee_name = ? ORDER BY caller_file, caller_line
            """,
                (callee_name,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_callees(
        self, caller_name: str, caller_file: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取指定函数调用的所有函数"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if caller_file:
                cursor.execute(
                    """
                    SELECT * FROM call_graph WHERE caller_name = ? AND caller_file = ? ORDER BY caller_line
                """,
                    (caller_name, caller_file),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM call_graph WHERE caller_name = ? ORDER BY caller_file, caller_line
                """,
                    (caller_name,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_call_graph(self) -> List[Dict[str, Any]]:
        """获取完整的调用图"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM call_graph ORDER BY caller_file, caller_line")
            return [dict(row) for row in cursor.fetchall()]

    def delete_call_relations_by_file(self, file_path: str) -> int:
        """删除文件的所有调用关系"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM call_graph WHERE caller_file = ?", (file_path,))
            conn.commit()
            return cursor.rowcount

    # ============================================================================
    # 数据流管理
    # ============================================================================

    def add_data_flow_node(self, node: DataFlowNode) -> int:
        """添加数据流节点"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO data_flow (var_name, file_path, line, node_type, scope, value_source)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    node.var_name,
                    node.file_path,
                    node.line,
                    node.node_type,
                    node.scope,
                    node.value_source,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def add_data_flow_nodes_batch(self, nodes: List[DataFlowNode]) -> int:
        """批量添加数据流节点"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT INTO data_flow (var_name, file_path, line, node_type, scope, value_source)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                [
                    (
                        n.var_name,
                        n.file_path,
                        n.line,
                        n.node_type,
                        n.scope,
                        n.value_source,
                    )
                    for n in nodes
                ],
            )
            conn.commit()
            return len(nodes)

    def get_def_sites(
        self, var_name: str, scope: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取变量的定义位置"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if scope:
                cursor.execute(
                    """
                    SELECT * FROM data_flow WHERE var_name = ? AND node_type = 'def' AND scope = ?
                    ORDER BY file_path, line
                """,
                    (var_name, scope),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM data_flow WHERE var_name = ? AND node_type = 'def'
                    ORDER BY file_path, line
                """,
                    (var_name,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_use_sites(
        self, var_name: str, scope: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取变量的使用位置"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if scope:
                cursor.execute(
                    """
                    SELECT * FROM data_flow WHERE var_name = ? AND node_type = 'use' AND scope = ?
                    ORDER BY file_path, line
                """,
                    (var_name, scope),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM data_flow WHERE var_name = ? AND node_type = 'use'
                    ORDER BY file_path, line
                """,
                    (var_name,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_data_flow_by_file(self, file_path: str) -> List[Dict[str, Any]]:
        """获取文件的所有数据流节点"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM data_flow WHERE file_path = ? ORDER BY line",
                (file_path,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def delete_data_flow_by_file(self, file_path: str) -> int:
        """删除文件的所有数据流节点"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM data_flow WHERE file_path = ?", (file_path,))
            conn.commit()
            return cursor.rowcount

    # ============================================================================
    # 指针状态管理
    # ============================================================================

    def add_pointer_state(self, state: PointerStateRecord) -> int:
        """添加指针状态记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO pointer_states (var_name, file_path, line, state, scope, allocator, deallocator)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    state.var_name,
                    state.file_path,
                    state.line,
                    state.state,
                    state.scope,
                    state.allocator,
                    state.deallocator,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def add_pointer_states_batch(self, states: List[PointerStateRecord]) -> int:
        """批量添加指针状态记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT INTO pointer_states (var_name, file_path, line, state, scope, allocator, deallocator)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    (
                        s.var_name,
                        s.file_path,
                        s.line,
                        s.state,
                        s.scope,
                        s.allocator,
                        s.deallocator,
                    )
                    for s in states
                ],
            )
            conn.commit()
            return len(states)

    def get_pointer_states(
        self, var_name: str, file_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取指针的状态历史"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if file_path:
                cursor.execute(
                    """
                    SELECT * FROM pointer_states WHERE var_name = ? AND file_path = ?
                    ORDER BY line
                """,
                    (var_name, file_path),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM pointer_states WHERE var_name = ? ORDER BY file_path, line
                """,
                    (var_name,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_pointer_states_by_file(self, file_path: str) -> List[Dict[str, Any]]:
        """获取文件的所有指针状态"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM pointer_states WHERE file_path = ? ORDER BY line",
                (file_path,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def delete_pointer_states_by_file(self, file_path: str) -> int:
        """删除文件的所有指针状态"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM pointer_states WHERE file_path = ?", (file_path,)
            )
            conn.commit()
            return cursor.rowcount

    # ============================================================================
    # 类型信息管理
    # ============================================================================

    def add_type_info(self, type_info: TypeInfo) -> int:
        """添加类型信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            members_json = json.dumps(type_info.members) if type_info.members else None
            cursor.execute(
                """
                INSERT INTO type_info (type_name, kind, file_path, line_start, line_end, definition, members)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    type_info.type_name,
                    type_info.kind,
                    type_info.file_path,
                    type_info.line_start,
                    type_info.line_end,
                    type_info.definition,
                    members_json,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def add_type_infos_batch(self, type_infos: List[TypeInfo]) -> int:
        """批量添加类型信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            data = [
                (
                    t.type_name,
                    t.kind,
                    t.file_path,
                    t.line_start,
                    t.line_end,
                    t.definition,
                    json.dumps(t.members) if t.members else None,
                )
                for t in type_infos
            ]
            cursor.executemany(
                """
                INSERT INTO type_info (type_name, kind, file_path, line_start, line_end, definition, members)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                data,
            )
            conn.commit()
            return len(type_infos)

    def get_type_info(self, type_name: str) -> Optional[Dict[str, Any]]:
        """获取类型信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM type_info WHERE type_name = ? LIMIT 1", (type_name,)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result["members"]:
                    result["members"] = json.loads(result["members"])
                return result
            return None

    def get_type_infos_by_file(self, file_path: str) -> List[Dict[str, Any]]:
        """获取文件的所有类型信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM type_info WHERE file_path = ? ORDER BY line_start",
                (file_path,),
            )
            results = []
            for row in cursor.fetchall():
                result = dict(row)
                if result["members"]:
                    result["members"] = json.loads(result["members"])
                results.append(result)
            return results

    def delete_type_infos_by_file(self, file_path: str) -> int:
        """删除文件的所有类型信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM type_info WHERE file_path = ?", (file_path,))
            conn.commit()
            return cursor.rowcount

    # ============================================================================
    # 分析缓存管理
    # ============================================================================

    def cache_analysis_result(
        self, file_path: str, analysis_type: str, result: Dict[str, Any]
    ) -> int:
        """缓存分析结果"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            result_json = json.dumps(result)
            cursor.execute(
                """
                INSERT OR REPLACE INTO analysis_cache (file_path, analysis_type, result, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (file_path, analysis_type, result_json),
            )
            conn.commit()
            return cursor.lastrowid

    def get_cached_analysis(
        self, file_path: str, analysis_type: str
    ) -> Optional[Dict[str, Any]]:
        """获取缓存的分析结果"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT result, updated_at FROM analysis_cache WHERE file_path = ? AND analysis_type = ?
            """,
                (file_path, analysis_type),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "result": json.loads(row["result"]),
                    "updated_at": row["updated_at"],
                }
            return None

    def delete_cached_analysis(self, file_path: str) -> int:
        """删除文件的所有缓存分析结果"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM analysis_cache WHERE file_path = ?", (file_path,)
            )
            conn.commit()
            return cursor.rowcount

    # ============================================================================
    # 统计与查询
    # ============================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            stats = {}

            # 文件统计
            cursor.execute("SELECT COUNT(*) FROM files")
            stats["files_count"] = cursor.fetchone()[0]

            # 符号统计
            cursor.execute("SELECT COUNT(*) FROM symbols")
            stats["symbols_count"] = cursor.fetchone()[0]
            cursor.execute("SELECT kind, COUNT(*) FROM symbols GROUP BY kind")
            stats["symbols_by_kind"] = {row[0]: row[1] for row in cursor.fetchall()}

            # 调用关系统计
            cursor.execute("SELECT COUNT(*) FROM call_graph")
            stats["call_relations_count"] = cursor.fetchone()[0]

            # 数据流统计
            cursor.execute("SELECT COUNT(*) FROM data_flow")
            stats["data_flow_nodes_count"] = cursor.fetchone()[0]

            # 指针状态统计
            cursor.execute("SELECT COUNT(*) FROM pointer_states")
            stats["pointer_states_count"] = cursor.fetchone()[0]
            cursor.execute("SELECT state, COUNT(*) FROM pointer_states GROUP BY state")
            stats["pointer_states_by_state"] = {
                row[0]: row[1] for row in cursor.fetchall()
            }

            # 类型信息统计
            cursor.execute("SELECT COUNT(*) FROM type_info")
            stats["type_infos_count"] = cursor.fetchone()[0]
            cursor.execute("SELECT kind, COUNT(*) FROM type_info GROUP BY kind")
            stats["type_infos_by_kind"] = {row[0]: row[1] for row in cursor.fetchall()}

            return stats

    def clear_all(self):
        """清空数据库所有数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM analysis_cache")
            cursor.execute("DELETE FROM pointer_states")
            cursor.execute("DELETE FROM data_flow")
            cursor.execute("DELETE FROM call_graph")
            cursor.execute("DELETE FROM type_info")
            cursor.execute("DELETE FROM symbols")
            cursor.execute("DELETE FROM files")
            conn.commit()
            PrettyOutput.auto_print("[ProjectDatabase] 数据库已清空")

    # ============================================================================
    # 增量更新机制
    # ============================================================================

    def update_file(
        self, file_path: str, language: str, collector: Optional[Any] = None
    ) -> bool:
        """
        增量更新单个文件的数据

        Args:
            file_path: 文件路径
            language: 语言类型（c, cpp, rust）
            collector: 数据收集器实例（可选，如果不提供则自动创建）

        Returns:
            是否成功更新
        """
        from .data_collector import DataCollector

        # 计算新哈希
        new_hash = compute_file_hash(file_path)

        # 检查是否需要更新
        if not self.file_hash_changed(file_path, new_hash):
            PrettyOutput.auto_print(
                f"[ProjectDatabase] 文件未变化，跳过更新: {file_path}"
            )
            return False

        # 删除旧数据
        self.delete_file(file_path)

        # 创建数据收集器（如果未提供）
        if collector is None:
            collector = DataCollector(self)

        # 收集新数据
        try:
            result = collector.analyze_file(file_path, language)

            # 添加文件记录
            file_info = create_file_info(file_path, language)
            self.add_file(file_info)

            # 批量插入数据
            if result["symbols"]:
                self.add_symbols_batch(result["symbols"])
            if result["call_relations"]:
                self.add_call_relations_batch(result["call_relations"])
            if result["data_flow_nodes"]:
                self.add_data_flow_nodes_batch(result["data_flow_nodes"])
            if result["pointer_states"]:
                self.add_pointer_states_batch(result["pointer_states"])
            if result["type_infos"]:
                self.add_type_infos_batch(result["type_infos"])

            PrettyOutput.auto_print(f"[ProjectDatabase] 文件更新成功: {file_path}")
            return True

        except Exception as e:
            PrettyOutput.auto_print(
                f"[ProjectDatabase] 文件更新失败: {file_path}, 错误: {e}"
            )
            return False

    def update_files_batch(self, file_paths: List[Tuple[str, str]]) -> Dict[str, bool]:
        """
        批量增量更新多个文件

        Args:
            file_paths: 文件路径列表，每个元素为(file_path, language)

        Returns:
            更新结果字典 {file_path: success}
        """
        from .data_collector import DataCollector

        # 创建共享的数据收集器
        collector = DataCollector(self)

        results = {}
        for file_path, language in file_paths:
            results[file_path] = self.update_file(file_path, language, collector)

        return results

    def sync_files(self, current_files: List[Tuple[str, str]]) -> Dict[str, Any]:
        """
        同步文件列表，删除不存在的文件，更新变化的文件

        Args:
            current_files: 当前文件列表，每个元素为(file_path, language)

        Returns:
            同步结果统计
        """
        # 获取数据库中的所有文件
        db_files = self.get_all_files()
        db_file_paths = {f["path"] for f in db_files}

        # 当前文件路径集合
        current_file_paths = {fp for fp, _ in current_files}

        # 需要删除的文件（数据库中存在但当前不存在）
        deleted_files = db_file_paths - current_file_paths
        deleted_count = 0
        for file_path in deleted_files:
            self.delete_file(file_path)
            deleted_count += 1

        if deleted_count > 0:
            PrettyOutput.auto_print(
                f"[ProjectDatabase] 删除了 {deleted_count} 个不存在的文件"
            )

        # 需要更新的文件
        update_results = self.update_files_batch(current_files)
        updated_count = sum(1 for success in update_results.values() if success)
        skipped_count = len(current_files) - updated_count

        PrettyOutput.auto_print(
            f"[ProjectDatabase] 同步完成: 更新 {updated_count} 个文件, 跳过 {skipped_count} 个文件, 删除 {deleted_count} 个文件"
        )

        return {
            "deleted_count": deleted_count,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "total_files": len(current_files),
        }

    # ============================================================================
    # 跨文件分析查询接口
    # ============================================================================

    def find_symbol_definition(self, name: str) -> List[Dict[str, Any]]:
        """
        查找符号的所有定义位置

        Args:
            name: 符号名称

        Returns:
            符号定义列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM symbols 
                WHERE name = ? AND kind IN ('function', 'variable', 'type')
                ORDER BY file_path, line_start
                """,
                (name,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def find_symbol_references(self, name: str) -> List[Dict[str, Any]]:
        """
        查找符号的所有引用位置

        Args:
            name: 符号名称

        Returns:
            符号引用列表（包括定义和使用）
        """
        results = []

        # 查找符号定义
        definitions = self.find_symbol_definition(name)
        results.extend(definitions)

        # 查找调用关系中的引用
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 作为调用者
            cursor.execute(
                """
                SELECT caller_name, caller_file, caller_line, 'caller' as ref_type
                FROM call_graph WHERE callee_name = ?
                """,
                (name,),
            )
            results.extend([dict(row) for row in cursor.fetchall()])

            # 作为被调用者
            cursor.execute(
                """
                SELECT callee_name, callee_file, callee_line, 'callee' as ref_type
                FROM call_graph WHERE caller_name = ?
                """,
                (name,),
            )
            results.extend([dict(row) for row in cursor.fetchall()])

        return results

    def find_callers(self, function_name: str) -> List[Dict[str, Any]]:
        """
        查找函数的所有调用者（跨文件）

        Args:
            function_name: 函数名称

        Returns:
            调用者列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT caller_name, caller_file, caller_line, call_type
                FROM call_graph 
                WHERE callee_name = ?
                ORDER BY caller_file, caller_line
                """,
                (function_name,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def find_callees(
        self, function_name: str, file_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        查找函数调用的所有函数（跨文件）

        Args:
            function_name: 函数名称
            file_path: 文件路径（可选，用于区分同名函数）

        Returns:
            被调用函数列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if file_path:
                cursor.execute(
                    """
                    SELECT callee_name, callee_file, callee_line, call_type
                    FROM call_graph 
                    WHERE caller_name = ? AND caller_file = ?
                    ORDER BY caller_line
                    """,
                    (function_name, file_path),
                )
            else:
                cursor.execute(
                    """
                    SELECT callee_name, callee_file, callee_line, call_type
                    FROM call_graph 
                    WHERE caller_name = ?
                    ORDER BY caller_file, caller_line
                    """,
                    (function_name,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def trace_pointer_state(
        self, var_name: str, file_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        追踪指针状态变化（跨文件）

        Args:
            var_name: 变量名称
            file_path: 文件路径（可选，用于限定范围）

        Returns:
            指针状态变化列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if file_path:
                cursor.execute(
                    """
                    SELECT var_name, file_path, line, state, scope, allocator, deallocator
                    FROM pointer_states 
                    WHERE var_name = ? AND file_path = ?
                    ORDER BY line
                    """,
                    (var_name, file_path),
                )
            else:
                cursor.execute(
                    """
                    SELECT var_name, file_path, line, state, scope, allocator, deallocator
                    FROM pointer_states 
                    WHERE var_name = ?
                    ORDER BY file_path, line
                    """,
                    (var_name,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def find_data_flow(
        self, var_name: str, file_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        查找变量的数据流（定义-使用链）

        Args:
            var_name: 变量名称
            file_path: 文件路径（可选，用于限定范围）

        Returns:
            数据流节点列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if file_path:
                cursor.execute(
                    """
                    SELECT var_name, file_path, line, node_type, scope, value_source
                    FROM data_flow 
                    WHERE var_name = ? AND file_path = ?
                    ORDER BY line
                    """,
                    (var_name, file_path),
                )
            else:
                cursor.execute(
                    """
                    SELECT var_name, file_path, line, node_type, scope, value_source
                    FROM data_flow 
                    WHERE var_name = ?
                    ORDER BY file_path, line
                    """,
                    (var_name,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def analyze_cross_file_uaf(self, var_name: str) -> Dict[str, Any]:
        """
        跨文件UAF分析

        Args:
            var_name: 变量名称

        Returns:
            UAF分析结果
        """
        # 追踪指针状态
        states = self.trace_pointer_state(var_name)

        # 查找数据流
        data_flow = self.find_data_flow(var_name)

        # 分析UAF风险
        freed_locations = [s for s in states if s["state"] == "FREED"]
        use_locations = [df for df in data_flow if df["node_type"] == "use"]

        # 检测UAF：释放后使用
        uaf_risks = []
        for freed in freed_locations:
            for use in use_locations:
                # 简单判断：同一文件中，释放行号 < 使用行号
                if (
                    freed["file_path"] == use["file_path"]
                    and freed["line"] < use["line"]
                ):
                    uaf_risks.append(
                        {
                            "var_name": var_name,
                            "freed_file": freed["file_path"],
                            "freed_line": freed["line"],
                            "use_file": use["file_path"],
                            "use_line": use["line"],
                            "risk_type": "use_after_free",
                        }
                    )

        return {
            "var_name": var_name,
            "states": states,
            "data_flow": data_flow,
            "uaf_risks": uaf_risks,
            "has_risk": len(uaf_risks) > 0,
        }

    def analyze_cross_file_data_flow(self, var_name: str) -> Dict[str, Any]:
        """
        跨文件数据流分析

        Args:
            var_name: 变量名称

        Returns:
            数据流分析结果
        """
        # 获取数据流节点
        nodes = self.find_data_flow(var_name)

        # 按文件分组
        by_file = {}
        for node in nodes:
            file_path = node["file_path"]
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(node)

        # 构建数据流图
        flow_graph = []
        def_nodes = [n for n in nodes if n["node_type"] == "def"]
        use_nodes = [n for n in nodes if n["node_type"] == "use"]

        for def_node in def_nodes:
            for use_node in use_nodes:
                # 简单判断：同一作用域内，定义行号 < 使用行号
                if (
                    def_node["file_path"] == use_node["file_path"]
                    and def_node["scope"] == use_node["scope"]
                    and def_node["line"] < use_node["line"]
                ):
                    flow_graph.append(
                        {
                            "from": def_node,
                            "to": use_node,
                            "type": "def-use",
                        }
                    )

        return {
            "var_name": var_name,
            "nodes": nodes,
            "by_file": by_file,
            "flow_graph": flow_graph,
            "def_count": len(def_nodes),
            "use_count": len(use_nodes),
        }

    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None


# ============================================================================
# 辅助函数
# ============================================================================


def compute_file_hash(file_path: str) -> str:
    """计算文件内容哈希"""
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def create_file_info(file_path: str, language: str) -> FileInfo:
    """创建文件信息对象"""
    path_obj = Path(file_path)
    hash_value = compute_file_hash(file_path)
    last_modified = datetime.fromtimestamp(path_obj.stat().st_mtime)

    # 计算行数
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        line_count = sum(1 for _ in f)

    return FileInfo(
        path=str(path_obj.resolve()),
        hash=hash_value,
        last_modified=last_modified,
        language=language,
        line_count=line_count,
    )
