# 多语言支持重构说明

## 重构目标

将多语言支持从集中式实现重构为插件化架构，便于扩展新的语言支持。

## 架构变化

### 重构前

- 所有语言实现在 `language_support.py` 中
- 使用全局字典注册语言支持
- 语言检测和工厂函数混在一起
- 不便于扩展新语言

### 重构后

- **基础抽象层**：`base_language.py` - 定义 `BaseLanguageSupport` 抽象类
- **注册表机制**：`language_registry.py` - 管理所有语言支持的注册和发现
- **独立语言实现**：`languages/` 目录下每个语言一个文件
- **插件化架构**：新语言只需实现 `BaseLanguageSupport` 接口并注册即可

## 新架构组件

### 1. BaseLanguageSupport (base_language.py)

定义所有语言支持需要实现的接口：

```python
class BaseLanguageSupport(ABC):
    @property
    @abstractmethod
    def language_name(self) -> str
    
    @property
    @abstractmethod
    def file_extensions(self) -> Set[str]
    
    @abstractmethod
    def create_symbol_extractor(self) -> Optional[SymbolExtractor]
    
    @abstractmethod
    def create_dependency_analyzer(self) -> Optional[DependencyAnalyzer]
```

### 2. LanguageRegistry (language_registry.py)

管理语言支持的注册表：

- `register()` - 注册语言支持
- `detect_language()` - 根据文件扩展名检测语言
- `get_symbol_extractor()` - 获取符号提取器
- `get_dependency_analyzer()` - 获取依赖分析器

### 3. 语言实现 (languages/)

每个语言一个独立的文件：

- `python_language.py` - Python语言支持
- `rust_language.py` - Rust语言支持
- `go_language.py` - Go语言支持
- `c_cpp_language.py` - C/C++语言支持

## 文件结构

```
code_analyzer/
├── base_language.py          # 基础抽象类
├── language_registry.py      # 语言注册表
├── language_support.py        # 语言支持模块（使用注册表）
├── languages/                # 语言实现目录
│   ├── __init__.py
│   ├── README.md            # 扩展指南
│   ├── python_language.py
│   ├── rust_language.py
│   ├── go_language.py
│   └── c_cpp_language.py
├── symbol_extractor.py
├── dependency_analyzer.py
└── context_manager.py
```

## 向后兼容性

重构保持了API的向后兼容性：

- `detect_language()` - 仍然可用
- `get_symbol_extractor()` - 仍然可用
- `get_dependency_analyzer()` - 仍然可用

所有现有代码无需修改即可使用新架构。

## 扩展新语言

添加新语言支持只需3步：

1. 在 `languages/` 目录创建新的语言支持类
2. 在 `languages/__init__.py` 中导出
3. 在 `language_support.py` 中注册

详细步骤请参考 `languages/README.md`。

## 优势

1. **解耦**：每个语言实现独立，互不影响
2. **易扩展**：添加新语言只需实现接口并注册
3. **清晰**：代码结构更清晰，职责分明
4. **可维护**：每个语言的代码独立维护
5. **可测试**：每个语言支持可以独立测试

## 迁移说明

所有旧的extractor文件已完全迁移到新的语言支持类结构。

已删除的旧文件：
- `c_cpp_extractor.py` → 已迁移到 `languages/c_cpp_language.py`
- `go_extractor.py` → 已迁移到 `languages/go_language.py`
- `rust_extractor.py` → 已迁移到 `languages/rust_language.py`

现在所有语言支持都统一在 `languages/` 目录下，使用 `*_language.py` 命名规范。

