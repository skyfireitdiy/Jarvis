---
name: symbol_dependency_optimization_spec
description: 参照codegraph开源项目优化当前项目的符号依赖分析模块，使用SQLite3存储，增强符号级关系建模和图遍历能力
---

# 符号依赖优化规范

## 1. 功能概述

### 1.1 目标
参照codegraph开源项目的设计理念，优化当前项目的符号依赖分析模块，使用SQLite3数据库存储，增强符号级关系建模能力，支持更丰富的依赖关系类型和图遍历功能。

### 1.2 背景
当前项目的符号依赖分析存在以下局限：
- 仅有文件级依赖关系（dependencies/dependents）
- 缺少符号级的调用、继承、实现等关系
- 无图遍历能力（BFS/DFS）
- JSON缓存性能较低

codegraph项目提供了优秀的参考实现：
- SQLite3数据库存储（nodes、edges表）
- 12+种边类型（calls、imports、extends、implements等）
- 完整的图遍历算法（BFS/DFS）
- 类型层次结构分析
- 高性能索引和prepared statements

### 1.3 范围
**在范围内：**
- SQLite3数据库存储（替代JSON缓存）
- 扩展符号类型定义
- 添加符号级关系类型
- 实现基础图遍历功能
- 增强影响分析能力

**在范围外：**
- FTS5全文搜索功能
- 文件系统监控
- 增量同步机制

## 2. 数据库设计

### 2.1 数据库Schema

#### 2.1.1 nodes表（符号节点）
```sql
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    language TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    start_column INTEGER NOT NULL,
    end_column INTEGER NOT NULL,
    docstring TEXT,
    signature TEXT,
    visibility TEXT,
    is_exported INTEGER DEFAULT 0,
    is_async INTEGER DEFAULT 0,
    is_static INTEGER DEFAULT 0,
    parent_id TEXT,
    updated_at INTEGER NOT NULL
);
```

#### 2.1.2 edges表（关系边）
```sql
CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    kind TEXT NOT NULL,
    metadata TEXT,
    line INTEGER,
    col INTEGER,
    FOREIGN KEY (source) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (target) REFERENCES nodes(id) ON DELETE CASCADE
);
```

#### 2.1.3 files表（文件记录）
```sql
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    language TEXT NOT NULL,
    size INTEGER NOT NULL,
    modified_at INTEGER NOT NULL,
    indexed_at INTEGER NOT NULL,
    node_count INTEGER DEFAULT 0
);
```

### 2.2 索引设计
```sql
-- 节点索引
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_file_path ON nodes(file_path);
CREATE INDEX IF NOT EXISTS idx_nodes_language ON nodes(language);

-- 边索引
CREATE INDEX IF NOT EXISTS idx_edges_kind ON edges(kind);
CREATE INDEX IF NOT EXISTS idx_edges_source_kind ON edges(source, kind);
CREATE INDEX IF NOT EXISTS idx_edges_target_kind ON edges(target, kind);
```

### 2.3 数据库配置
```python
# 性能优化配置
db.pragma('foreign_keys = ON')
db.pragma('journal_mode = WAL')
db.pragma('busy_timeout = 120000')
db.pragma('synchronous = NORMAL')
db.pragma('cache_size = -64000')  # 64 MB page cache
db.pragma('temp_store = MEMORY')
```

## 3. 接口定义

### 3.1 符号类型枚举
```python
class SymbolKind(Enum):
    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    INTERFACE = "interface"
    STRUCT = "struct"
    ENUM = "enum"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    VARIABLE = "variable"
    CONSTANT = "constant"
    IMPORT = "import"
    EXPORT = "export"
```

### 3.2 边类型枚举
```python
class EdgeKind(Enum):
    CALLS = "calls"                 # 函数/方法调用
    IMPORTS = "imports"             # 导入关系
    EXTENDS = "extends"             # 继承关系
    IMPLEMENTS = "implements"       # 实现接口
    CONTAINS = "contains"           # 包含关系
    REFERENCES = "references"       # 引用关系
    OVERRIDES = "overrides"         # 方法重写
    USES = "uses"                   # 使用关系
    DEFINES = "defines"             # 定义关系
```

### 3.3 QueryBuilder类
```python
class QueryBuilder:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self._prepare_statements()
    
    # 节点操作
    def insert_node(self, node: Node) -> None: ...
    def get_node_by_id(self, id: str) -> Optional[Node]: ...
    def get_nodes_by_file(self, file_path: str) -> List[Node]: ...
    def get_nodes_by_kind(self, kind: SymbolKind) -> List[Node]: ...
    def get_nodes_by_name(self, name: str) -> List[Node]: ...
    def delete_node(self, id: str) -> None: ...
    
    # 边操作
    def insert_edge(self, edge: Edge) -> None: ...
    def get_outgoing_edges(self, source_id: str, kinds: Optional[List[EdgeKind]] = None) -> List[Edge]: ...
    def get_incoming_edges(self, target_id: str, kinds: Optional[List[EdgeKind]] = None) -> List[Edge]: ...
    def delete_edges_by_source(self, source_id: str) -> None: ...
    
    # 文件操作
    def upsert_file(self, file: FileRecord) -> None: ...
    def get_file_by_path(self, path: str) -> Optional[FileRecord]: ...
    def delete_file(self, path: str) -> None: ...
```

### 3.4 GraphTraverser类
```python
class GraphTraverser:
    def __init__(self, queries: QueryBuilder):
        self.queries = queries
    
    def traverse_bfs(
        self,
        start_id: str,
        max_depth: int = 3,
        edge_kinds: Optional[List[EdgeKind]] = None,
        direction: str = "outgoing",
        limit: int = 1000
    ) -> Subgraph:
        """BFS遍历图"""
        pass
    
    def traverse_dfs(
        self,
        start_id: str,
        max_depth: int = 3,
        edge_kinds: Optional[List[EdgeKind]] = None,
        direction: str = "outgoing"
    ) -> Subgraph:
        """DFS遍历图"""
        pass
    
    def get_type_hierarchy(self, node_id: str) -> Subgraph:
        """获取类型层次结构"""
        pass
    
    def get_call_graph(self, node_id: str, depth: int = 2) -> Subgraph:
        """获取调用图"""
        pass
    
    def get_callers(self, node_id: str, max_depth: int = 1) -> List[Node]:
        """获取调用者"""
        pass
    
    def get_callees(self, node_id: str, max_depth: int = 1) -> List[Node]:
        """获取被调用者"""
        pass
```

### 3.5 DatabaseConnection类
```python
class DatabaseConnection:
    @staticmethod
    def initialize(db_path: str) -> 'DatabaseConnection':
        """初始化新数据库"""
        pass
    
    @staticmethod
    def open(db_path: str) -> 'DatabaseConnection':
        """打开现有数据库"""
        pass
    
    def get_queries(self) -> QueryBuilder:
        """获取查询构建器"""
        pass
    
    def get_traverser(self) -> GraphTraverser:
        """获取图遍历器"""
        pass
    
    def close(self) -> None:
        """关闭数据库连接"""
        pass
```

## 4. 验收标准

### 4.1 数据库功能
- [ ] SQLite3数据库能正确创建
- [ ] nodes表能正确存储符号信息
- [ ] edges表能正确存储关系信息
- [ ] files表能正确存储文件记录
- [ ] 索引能正确创建和使用
- [ ] WAL模式能正确启用

### 4.2 符号类型支持
- [ ] 支持SymbolKind枚举定义的所有符号类型
- [ ] 能正确提取函数、类、方法等符号
- [ ] 能正确提取接口、枚举等高级类型

### 4.3 关系类型支持
- [ ] 支持EdgeKind枚举定义的所有边类型
- [ ] 能正确提取函数调用关系（calls）
- [ ] 能正确提取类继承关系（extends）
- [ ] 能正确提取接口实现关系（implements）
- [ ] 能正确提取包含关系（contains）

### 4.4 图遍历功能
- [ ] BFS遍历能正确返回指定深度的节点
- [ ] DFS遍历能正确返回指定深度的节点
- [ ] 边类型过滤能正确工作
- [ ] 方向控制能正确工作
- [ ] getTypeHierarchy能正确返回继承链
- [ ] getCallGraph能正确返回调用图

### 4.5 性能要求
- [ ] 数据库初始化时间 < 100ms
- [ ] 单节点查询时间 < 10ms
- [ ] 图遍历在万级节点下响应时间 < 100ms
- [ ] 批量插入性能 > 1000 nodes/s

## 5. 实现计划

### 5.1 阶段一：数据库基础设施
1. 实现DatabaseConnection类
2. 实现数据库schema创建
3. 实现基础配置（WAL、索引等）

### 5.2 阶段二：QueryBuilder实现
1. 实现节点CRUD操作
2. 实现边CRUD操作
3. 实现文件CRUD操作
4. 添加prepared statements优化

### 5.3 阶段三：数据结构定义
1. 定义SymbolKind和EdgeKind枚举
2. 定义Node、Edge、FileRecord类
3. 定义Subgraph类

### 5.4 阶段四：图遍历实现
1. 实现GraphTraverser类
2. 实现BFS遍历
3. 实现DFS遍历
4. 实现getTypeHierarchy
5. 实现getCallGraph

### 5.5 阶段五：符号提取增强
1. 更新各语言提取器
2. 添加关系提取逻辑
3. 集成到现有流程

### 5.6 阶段六：影响分析增强
1. 更新ImpactAnalyzer
2. 集成图遍历功能
3. 增强影响报告

## 6. 风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| SQLite依赖 | 低 | 确定 | 使用Python内置sqlite3模块 |
| 数据库损坏 | 中 | 低 | 使用WAL模式，定期备份 |
| 并发访问 | 中 | 中 | 使用busy_timeout，WAL模式 |
| 实现复杂度 | 中 | 中 | 参照codegraph实现，分阶段集成 |

## 7. 参考资料

- codegraph项目：https://github.com/colbymchenry/codegraph
- codegraph源码：/tmp/codegraph/
- codegraph数据库schema：/tmp/codegraph/src/db/schema.sql
- codegraph查询实现：/tmp/codegraph/src/db/queries.ts
- codegraph图遍历：/tmp/codegraph/src/graph/traversal.ts